import json
import os
import time
import traceback

import boto3
import botocore
import urllib3
from aws_synthetics.common import synthetics_logger as logger

# Domino Data Lab API canary.
#
# DEBUG BUILD (2026-08-22): logs env presence (names only, never secret
# values), SSM resolution, request timing, and full tracebacks.
#
# Workspace sessions use Domino's v1 projects API:
#   POST   /api/projects/v1/projects/{projectId}/workspaces/{workspaceId}/sessions
#   GET    .../sessions/{sessionId}        (status poll)
#   DELETE .../sessions/{sessionId}        (stop)
# Jobs use the v4 API:
#   POST /v4/jobs/start  |  POST /v4/jobs/stop
#
# Behaviour: start the workspace session, POLL until it reaches a Running
# state (so we know it actually started), then stop it - leaving the next
# scheduled run free to start a fresh session. Paths can be overridden via
# DOMINO_*_START_PATH / _STATUS_PATH / _STOP_PATH / _STOP_METHOD; {projectId},
# {workspaceId} and {sessionId} placeholders are substituted.

# Hard request timeouts so a stalled connection fails fast with a real error
# instead of hanging until the Lambda timeout kills the canary mid-run.
REQUEST_TIMEOUT = urllib3.Timeout(connect=5, read=15)
# boto3 defaults to 60s timeouts - pin them hard so SSM resolution can't hang.
BOTO_TIMEOUT = botocore.config.Config(connect_timeout=5, read_timeout=5)

DEFAULT_PATHS = {
    "job": {
        "start": "/v4/jobs/start",
        "stop": "/v4/jobs/stop",
        "stop_method": "POST",
    },
    "workspace": {
        "start": "/api/projects/v1/projects/{projectId}/workspaces/{workspaceId}/sessions",
        "status": "/api/projects/v1/projects/{projectId}/workspaces/{workspaceId}/sessions/{sessionId}",
        "stop": "/workspace/project/{projectId}/workspace/{workspaceId}/stop",
        "stop_method": "POST",
    },
}

# Statuses we treat as "the workspace is successfully up". Domino workspace
# sessions report these (case-insensitive). Override via
# DOMINO_WORKSPACE_READY_STATUSES (comma-separated).
DEFAULT_READY_STATUSES = ("running", "started", "ready", "active")

# Terminal failure statuses - if the session lands here before Running, fail.
FAILED_STATUSES = ("failed", "error", "terminated", "stopped", "cancelled", "canceled")

# Env vars the canary reads - we log which are SET (never their values).
ENV_CHECKS = [
    "DOMINO_HOST",
    "DOMINO_PROJECT_ID",
    "DOMINO_WORKSPACE_ID",
    "DOMINO_API_KEY_SSM_NAME",
    "DOMINO_API_KEY",
    "DOMINO_API_KEY_SECRET_ID",
    "DOMINO_ACTION",
    "DOMINO_RUN_COMMAND",
    "DOMINO_CLEANUP",
    "DOMINO_MAX_LATENCY_MS",
    "DOMINO_WORKSPACE_POLL_INTERVAL_SECONDS",
    "DOMINO_WORKSPACE_POLL_TIMEOUT_SECONDS",
    "DOMINO_WORKSPACE_READY_STATUSES",
    "DOMINO_WORKSPACE_START_BODY",
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


def _render_path(path, project_id, workspace_id, session_id=None):
    """Substitute {projectId}, {workspaceId}, {sessionId} placeholders."""
    return (path
            .replace("{projectId}", project_id)
            .replace("{workspaceId}", workspace_id or "")
            .replace("{sessionId}", session_id or ""))


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
    for key in ("id", "sessionId", "jobId", "runId", "workspaceId"):
        if data.get(key):
            return data[key]
    return None


def _get_status(resp):
    """Pull a status string out of a session/job detail response."""
    try:
        data = json.loads(resp.data.decode("utf-8", errors="replace"))
    except (ValueError, AttributeError):
        return None
    if not isinstance(data, dict):
        return None
    for key in ("status", "state", "lifecycleState", "sessionStatus"):
        val = data.get(key)
        if isinstance(val, str) and val:
            return val
    return None


def _wait_until_running(http, url, headers, session_id):
    """Poll the session until it is Running (or a terminal failure / timeout)."""
    interval = float(os.environ.get("DOMINO_WORKSPACE_POLL_INTERVAL_SECONDS", "10"))
    timeout = float(os.environ.get("DOMINO_WORKSPACE_POLL_TIMEOUT_SECONDS", "240"))
    ready_raw = os.environ.get("DOMINO_WORKSPACE_READY_STATUSES")
    ready = {s.strip().lower() for s in ready_raw.split(",")} if ready_raw else set(DEFAULT_READY_STATUSES)

    deadline = time.monotonic() + timeout
    last_status = None
    logger.info(f"[DEBUG] _wait_until_running: polling {url} every {interval:.0f}s up to {timeout:.0f}s (ready={sorted(ready)})")

    while time.monotonic() < deadline:
        try:
            resp, _ = _request(http, "GET", url, headers, None)
            status = _get_status(resp)
            last_status = status
            logger.info(f"Workspace session {session_id} status: {status} (http {resp.status})")
            if status is not None and status.strip().lower() in ready:
                logger.info(f"Workspace session {session_id} is READY.")
                return True
            if status is not None and status.strip().lower() in FAILED_STATUSES:
                raise Exception(
                    f"Workspace session {session_id} entered terminal state before ready: '{status}'"
                )
        except Exception as e:
            if isinstance(e, urllib3.exceptions.HTTPError) or "timed out" in str(e).lower():
                # transient poll error - keep polling until deadline
                logger.info(f"[DEBUG] _wait_until_running: poll error (retrying): {type(e).__name__}: {e}")
            else:
                raise
        time.sleep(interval)

    raise Exception(
        f"Workspace session {session_id} did not reach a ready state within {timeout:.0f}s "
        f"(last status: {last_status})"
    )


def _cleanup(http, method, url, headers, action, project_id, workspace_id, started_id):
    # Job stop takes {projectId, jobId} in the body (v4 API). Workspace stop
    # takes projectId + workspaceId in the PATH (Swagger: POST .../workspace/stop)
    # so it gets an empty body.
    body = {"projectId": project_id, "jobId": started_id} if action == "job" else {}
    try:
        resp, _ = _request(http, method, url, headers, body)
        logger.info(f"Cleanup stop response: {resp.status}")
    except Exception as e:  # cleanup must never mask an otherwise-successful check
        logger.info(f"Cleanup stop failed (non-fatal): {e}")


def main():
    _log_env()

    host = os.environ.get("DOMINO_HOST")
    project_id = os.environ.get("DOMINO_PROJECT_ID")
    workspace_id = os.environ.get("DOMINO_WORKSPACE_ID")
    logger.info(f"[DEBUG] main: DOMINO_HOST={'<set>' if host else '<MISSING>'}, "
                f"DOMINO_PROJECT_ID={'<set>' if project_id else '<MISSING>'}, "
                f"DOMINO_WORKSPACE_ID={'<set>' if workspace_id else '<MISSING>'}")

    api_key = _resolve_api_key()
    if not host or not api_key or not project_id:
        raise Exception(
            "DOMINO_HOST, DOMINO_PROJECT_ID and an API key "
            "(DOMINO_API_KEY_SSM_NAME or DOMINO_API_KEY) must all be set"
        )

    action = os.environ.get("DOMINO_ACTION", "job")
    if action not in DEFAULT_PATHS:
        raise Exception(f'DOMINO_ACTION must be "job" or "workspace", got "{action}"')
    if action == "workspace" and not workspace_id:
        raise Exception("DOMINO_WORKSPACE_ID must be set when DOMINO_ACTION=workspace")

    host = host.rstrip("/")
    headers = {"X-Domino-Api-Key": api_key, "Content-Type": "application/json"}
    http = urllib3.PoolManager()

    prefix = f"DOMINO_{action.upper()}"
    start_path = os.environ.get(f"{prefix}_START_PATH", DEFAULT_PATHS[action]["start"])
    status_path = os.environ.get(f"{prefix}_STATUS_PATH", DEFAULT_PATHS[action].get("status"))
    stop_path = os.environ.get(f"{prefix}_STOP_PATH", DEFAULT_PATHS[action]["stop"])
    stop_method = os.environ.get(f"{prefix}_STOP_METHOD", DEFAULT_PATHS[action]["stop_method"])

    start_url = host + _render_path(start_path, project_id, workspace_id)
    stop_url = host + _render_path(stop_path, project_id, workspace_id)

    # Request bodies:
    # - job:       {projectId, runCommand}  (v4 API)
    # - workspace: {externalVolumeMounts, netAppVolumeMounts}  (v1 sessions API -
    #   projectId lives in the path, and the API rejects a body missing the
    #   mount fields with "error.path.missing"). Override via
    #   DOMINO_WORKSPACE_START_BODY (JSON string) if your deployment needs
    #   specific mounts.
    if action == "workspace":
        override = os.environ.get("DOMINO_WORKSPACE_START_BODY")
        start_body = json.loads(override) if override else {
            "externalVolumeMounts": [],
            "netAppVolumeMounts": [],
        }
    else:
        start_body = {"projectId": project_id}
        start_body["runCommand"] = os.environ.get("DOMINO_RUN_COMMAND", "main.py")

    logger.info(f"[DEBUG] main: action={action}, start_url={start_url}, stop_url={stop_url} (stop_method={stop_method})")

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

    # Workspace: wait until the session is actually Running before we stop it,
    # so the next scheduled run starts from a clean (stopped) workspace.
    if action == "workspace" and status_path and started_id:
        status_url = host + _render_path(status_path, project_id, workspace_id, started_id)
        _wait_until_running(http, status_url, headers, started_id)
        logger.info("Workspace confirmed running; proceeding to cleanup.")

    if os.environ.get("DOMINO_CLEANUP", "true").lower() == "true" and started_id:
        stop_url_final = host + _render_path(stop_path, project_id, workspace_id, started_id)
        _cleanup(http, stop_method, stop_url_final, headers, action, project_id, workspace_id, started_id)

    logger.info("Domino canary successfully executed.")


def handler(event, context):
    logger.info("Domino Data Lab API canary. [DEBUG BUILD]")
    try:
        return main()
    except Exception:
        logger.info(f"[DEBUG] handler caught exception:\n{traceback.format_exc()}")
        raise
