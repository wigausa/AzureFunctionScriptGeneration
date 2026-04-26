import logging
import os
import time
from typing import Any, Dict, Optional

import requests

DEFAULT_TOKEN_USERS = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyIjoiYWRtaW53aWdhIiwiaWQiOjI3MCwiZXhwaXJlZERhdGUiOiIyMDE5LTA3LTIyVDExOjAwOjMyLjA2NzU2ODYtMDU6MDAifQ.BXMx2BKIbkJyD_jRrfhY6Sj_SJbo8gWM8wHghzFvrT0"
DEFAULT_BASE_URL = "https://superwicloudapi.azurewebsites.net/api"


def _get_report_api_base_url() -> str:
    base_url = os.getenv("REPORT_API_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    if base_url.endswith("/v1"):
        return base_url
    return f"{base_url}/v1"


def _get_report_api_token() -> str:
    return os.getenv("REPORT_API_TOKEN_USERS", DEFAULT_TOKEN_USERS)


def make_request(
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    logger: Optional[logging.Logger] = None,
) -> Optional[Dict[str, Any]]:
    timeout_seconds = int(os.getenv("REPORT_API_TIMEOUT_SECONDS", "30"))
    retries = int(os.getenv("REPORT_API_RETRIES", "3"))
    backoff = float(os.getenv("REPORT_API_BACKOFF", "0.5"))
    attempts = max(retries, 1)

    for attempt in range(1, attempts + 1):
        try:
            response = requests.request(method, url, headers=headers, json=json_body, timeout=timeout_seconds)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            if logger:
                logger.error("Error en peticion %s %s (intento %s/%s): %s", method, url, attempt, attempts, exc)
            if attempt < attempts:
                time.sleep(backoff * attempt)
    return None


def get_data_informe(report_id: str, logger: Optional[logging.Logger] = None) -> Optional[Dict[str, Any]]:
    base_url = _get_report_api_base_url()
    url = f"{base_url}/reports/{report_id}"
    headers = {"Content-Type": "application/json", "token": _get_report_api_token()}
    result = make_request("GET", url, headers=headers, logger=logger)

    if result and "configuration" in result:
        if logger:
            logger.info("Configuracion del informe %s obtenida exitosamente", report_id)
        return result

    if logger:
        logger.error("No se pudo obtener configuracion del informe %s", report_id)
    return None
