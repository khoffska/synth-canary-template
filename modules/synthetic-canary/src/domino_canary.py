import json
import os
import socket
import time
import traceback

import boto3
import botocore
import urllib3
from aws_synthetics.common import synthetics_logger as logger

# Domino Data Lab API canary.
#
# DEBUG BUILD (2026-08-22): extra logging to find a 60s Lambda timeout.
# Logs: env presence (names only, never secret values), SSM resolution,
# DNS resolution, request timing, and full tracebacks.

# Hard request timeouts so a stalled connection fails fast with a real error
# instead of hanging until the Lambda timeout kills the canary mid-run.
REQUEST_TIMEOUT = urllib3.Timeout(connect=5, read=15)
# boto3 defaults to 60s timeouts - pin them hard so SSM resolution can't hang.
BOTO_TIMEOUT = botocore.config.Config(connect_timeout=5, read_timeout=5)

DEFAULT_PATHS = {
    "job": {"start": "/v4/jobs/start", "stop": "/v4/jobs/stop"},
    "workspace": {"start": "/v4/workspaces", "stop": "/v4/workspaces/stop"},
}

# Env vars the canary reads - we log which are SET (never their values).
ENV_CHECKS = [
    "DOMINO_HOST",
    "DOMINO_PROJECT_ID",
    "DOMINO_API_KEY_SSM_NAME",
    "DOMINO_API_KEY",
    "DOMINO_API_KEY_SECRET_ID",
    "DOMINO_ACTION",
    "DOMINO_RUN_COMMAND",
    "DOMINO_CLEANUP",
    "DOMINO_MAX_LATENCY_MS",
]


def _log_env():
    """Log which relevant env vars are set/present (names only, not values)."""
    present, missing = [], []
    for name in ENV_CHECKS:
        val = os.environ.get(name)
        if val is None:
            missing.append(name)
        elif name in ("DOMINO_API_KEY",):
            present.append(f"{name}=<set,len={len(val)}>")
        else:
            present.append(f"{name}=<set>")
    logger.info(f"[DEBUG] env present: {', '.join(present)}")
    if missing:
        logger.info(f"[DEBUG] env MISSING: {', '.join(missing)}")


def _resolve_api_key():
    """Prefer an SSM Parameter Store SecureString; fall back to a plaintext env var."""
    param_name = os.environ.get("DOMINO_API_KEY_SSM_NAME")
    if not param_name:
        logger.info("[DEBUG] _resolve_api_key: no DOMINO_API_KEY_SSM_NAME, using DOMINO_API_KEY env")
        return os.environ.get("DOMINO_API_KEY")

    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    logger.info(f"[DEBUG] _resolve_api_key: reading SSM parameter '{param_name}' in region '{region}'")
    start = time.monotonic()
    try:
        ssm = boto3.client("ssm", region_name=region, config=BOTO_TIMEOUT)
        value = ssm.get_parameter(Name=param_name, WithDecryption=True)["Parameter"]["Value"]
        logger.info(f"[DEBUG] _resolve_api_key: SSM get_parameter OK in {(time.monotonic()-start)*1000:.0f} ms (len={len(value)})")
        return value
    except Exception as e:
        logger.info(f"[DEBUG] _resolve_api_key: SSM get_parameter FAILED after {(time.monotonic()-start)*1000:.0f} ms: {type(e).__name__}: {e}")
        raise


def _resolve_host(host, port=443):
    """Explicit DNS resolution check so we can see if resolution hangs or fails."""
    logger.info(f"[DEBUG] _resolve_host: resolving '{host}' ...")
    start = time.monotonic()
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
        ips = sorted({i[4][0] for i in infos})
        logger.info(f"[DEBUG] _resolve_host: resolved in {(time.monotonic()-start)*1000:.0f} ms -> {ips}")
        return ips
    except Exception as e:
        logger.info(f"[DEBUG] _resolve_host: FAILED after {(time.monotonic()-start)*1000:.0f} ms: {type(e).__name__}: {e}")
        raise


def _request(http, method, url, headers, body):
    logger.info(f"[DEBUG] _request: {method} {url} (timeout={REQUEST_TIMEOUT})")
    start = time.monotonic()
    try:
        resp = http.request(
            method, url, headers=headers, body=None if body is None else json.dumps(body),
            timeout=REQUEST_TIMEOUT,
        )
        latency_ms = (time.monotonic() - start) * 1000
        logger.info(f"[DEBUG] _request: response {resp.status} in {latency_ms:.0f} ms")
        return resp, latency_ms
    except Exception as e:
        latency_ms = (time.monotonic() - start) * 1000
        logger.info(f"[DEBUG] _request: EXCEPTION after {latency_ms:.0f} ms: {type(e).__name__}: {e}")
        raise


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
    _log_env()

    host = os.environ.get("DOMINO_HOST")
    project_id = os.environ.get("DOMINO_PROJECT_ID")
    logger.info(f"[DEBUG] main: DOMINO_HOST={'<set>' if host else '<MISSING>'}, DOMINO_PROJECT_ID={'<set>' if project_id else '<MISSING>'}")

    api_key = _resolve_api_key()
    if not host or not api_key or not project_id:
        raise Exception(
            "DOMINO_HOST, DOMINO_PROJECT_ID and an API key "
            "(DOMINO_API_KEY_SSM_NAME or DOMINO_API_KEY) must all be set"
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

    logger.info(f"[DEBUG] main: action={action}, start_url={start_url}, stop_url={stop_url}")
    _resolve_host(host)

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
    logger.info("Domino Data Lab API canary. [DEBUG BUILD]")
    try:
        return main()
    except Exception:
        logger.info(f"[DEBUG] handler caught exception:\n{traceback.format_exc()}")
        raise
