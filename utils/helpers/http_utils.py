import json
from typing import Any, Callable, Dict, Optional

import azure.functions as func


def json_response(payload: Dict[str, Any], status_code: int) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(payload),
        status_code=status_code,
        mimetype="application/json",
    )


def parse_exception_payload(value: Exception) -> Optional[Dict[str, Any]]:
    payload = str(value)
    try:
        parsed = json.loads(payload)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def get_body_param(req: func.HttpRequest, key: str) -> str:
    try:
        body = req.get_json()
    except ValueError:
        return ""

    if not isinstance(body, dict):
        return ""

    return str(body.get(key) or "").strip()


def get_request_param(req: func.HttpRequest, key: str) -> str:
    return get_body_param(req, key)


def normalize_webjob_cron(cron_expression: str) -> str:
    return " ".join(cron_expression.strip().split())


def is_valid_webjob_cron(cron_expression: str) -> bool:
    return len(cron_expression.split(" ")) == 6


def validation_error_response(
    *,
    operation_id: str,
    message: str,
    field: Optional[str] = None,
    action: str = "create_or_update",
    trace_log: Optional[Callable[..., None]] = None,
) -> func.HttpResponse:
    if field and trace_log:
        trace_log(operation_id, action, "validation_error", field=field)
    return json_response(
        {
            "ok": False,
            "operationId": operation_id,
            "message": message,
        },
        status_code=400,
    )
