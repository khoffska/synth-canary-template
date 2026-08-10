import json
import os
import time

import boto3
import urllib3
from aws_synthetics.common import synthetics_logger as logger

# Domino Data Lab API canary.
#
# Confirms the platform can accept an API request to launch compute -- a Job or a
# Workspace -- and (by default) stops what it started so the canary does not leave
# paid compute running every cycle.
#
# Config (env vars built in main.tf from each type = "domino" cloudwatch_map entry):
#   DOMINO_HOST            (required) base URL, e.g. https://domino.example.com
#   DOMINO_PROJECT_ID      (required) target project id
#   The API key (X-Domino-Api-Key) is resolved from, in order of preference:
#     DOMINO_API_KEY_SECRET_ID        Secrets Manager secret id/ARN to read at runtime (preferred)
#     DOMINO_API_KEY_SECRET_JSON_KEY  if the secret is JSON, the key holding the api key
#     DOMINO_API_KEY                  plaintext fallback (avoid for real secrets)
#   DOMINO_ACTION          "job" | "workspace"  (default "job")
#   DOMINO_RUN_COMMAND     job run command       (default "main.py")
#   DOMINO_CLEANUP         "true" | "false" -- stop what we started (default "true")
#   DOMINO_MAX_LATENCY_MS  optional ms ceiling on the start request
#   DOMINO_JOB_START_PATH / DOMINO_JOB_STOP_PATH / DOMINO_WORKSPACE_START_PATH /
#   DOMINO_WORKSPACE_STOP_PATH  override the defaults below if your Domino version differs
#
# The endpoint paths follow Domino's v4 REST API; confirm them against your
# deployment's API docs and override via the *_PATH env vars if they differ.

DEFAULT_PATHS = {
    "job": {"start": "/v4/jobs/start", "stop": "/v4/jobs/stop"},
    "workspace": {"start": "/v4/workspaces", "stop": "/v4/workspaces/stop"},
}


def _resolve_api_key():
    """Prefer a Secrets Manager secret; fall back to a plaintext env var."""
    secret_id = os.environ.get("DOMINO_API_KEY_SECRET_ID")
    if not secret_id:
        return os.environ.get("DOMINO_API_KEY")

    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    secret = boto3.client("secretsmanager", region_name=region).get_secret_value(
        SecretId=secret_id
    )["SecretString"]

    json_key = os.environ.get("DOMINO_API_KEY_SECRET_JSON_KEY")
    return json.loads(secret)[json_key] if json_key else secret


def _request(http, method, url, headers, body):
    start = time.monotonic()
    resp = http.request(
        method, url, headers=headers, body=None if body is None else json.dumps(body)
    )
    latency_ms = (time.monotonic() - start) * 1000
    return resp, latency_ms


def _extract_id(resp):
    try:
        data = json.loads(resp.data.decode("utf-8", errors="replace"))
    except (ValueError, AttributeError):
        return None
    if not isinstance(data, dict):
        return None
    for key in ("id", "jobId", "runId", "workspaceId"):
        if data.get(key):
            return data[key]
    return None


def _cleanup(http, url, headers, action, project_id, started_id):
    id_field = "jobId" if action == "job" else "workspaceId"
    body = {"projectId": project_id, id_field: started_id}
    try:
        resp, _ = _request(http, "POST", url, headers, body)
        logger.info(f"Cleanup stop response: {resp.status}")
    except Exception as e:  # cleanup must never mask an otherwise-successful check
        logger.info(f"Cleanup stop failed (non-fatal): {e}")


def main():
    host = os.environ.get("DOMINO_HOST")
    project_id = os.environ.get("DOMINO_PROJECT_ID")
    api_key = _resolve_api_key()
    if not host or not api_key or not project_id:
        raise Exception(
            "DOMINO_HOST, DOMINO_PROJECT_ID and an API key "
            "(DOMINO_API_KEY_SECRET_ID or DOMINO_API_KEY) must all be set"
        )

    action = os.environ.get("DOMINO_ACTION", "job")
    if action not in DEFAULT_PATHS:
        raise Exception(f'DOMINO_ACTION must be "job" or "workspace", got "{action}"')

    host = host.rstrip("/")
    headers = {"X-Domino-Api-Key": api_key, "Content-Type": "application/json"}
    http = urllib3.PoolManager()

    prefix = f"DOMINO_{action.upper()}"
    start_url = host + os.environ.get(f"{prefix}_START_PATH", DEFAULT_PATHS[action]["start"])
    stop_url = host + os.environ.get(f"{prefix}_STOP_PATH", DEFAULT_PATHS[action]["stop"])

    start_body = {"projectId": project_id}
    if action == "job":
        start_body["runCommand"] = os.environ.get("DOMINO_RUN_COMMAND", "main.py")

    logger.info(f"Starting Domino {action} in project {project_id}")
    resp, latency_ms = _request(http, "POST", start_url, headers, start_body)
    logger.info(f"Start response: {resp.status} in {latency_ms:.0f} ms")

    if resp.status < 200 or resp.status > 299:
        raise Exception(
            f"Domino {action} start returned status {resp.status}: "
            f"{resp.data[:500].decode('utf-8', errors='replace')}"
        )

    max_latency = os.environ.get("DOMINO_MAX_LATENCY_MS")
    if max_latency and latency_ms > float(max_latency):
        raise Exception(
            f"Start took {latency_ms:.0f} ms, exceeding the {max_latency} ms threshold"
        )

    started_id = _extract_id(resp)
    logger.info(f"Domino {action} started with id: {started_id}")

    if os.environ.get("DOMINO_CLEANUP", "true").lower() == "true" and started_id:
        _cleanup(http, stop_url, headers, action, project_id, started_id)

    logger.info("Domino canary successfully executed.")


def handler(event, context):
    logger.info("Domino Data Lab API canary.")
    return main()
