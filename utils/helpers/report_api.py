import logging
from typing import Any, Dict, Optional

import requests

TOKEN_USERS = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyIjoiYWRtaW53aWdhIiwiaWQiOjI3MCwiZXhwaXJlZERhdGUiOiIyMDE5LTA3LTIyVDExOjAwOjMyLjA2NzU2ODYtMDU6MDAifQ.BXMx2BKIbkJyD_jRrfhY6Sj_SJbo8gWM8wHghzFvrT0"
BASE_URL = "https://superwicloudapi.azurewebsites.net/api/v1"


def make_request(
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    logger: Optional[logging.Logger] = None,
) -> Optional[Dict[str, Any]]:
    try:
        response = requests.request(method, url, headers=headers, json=json_body, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        if logger:
            logger.error("Error en peticion %s %s: %s", method, url, exc)
        return None


def get_data_informe(report_id: str, logger: Optional[logging.Logger] = None) -> Optional[Dict[str, Any]]:
    url = f"{BASE_URL}/reports/{report_id}"
    headers = {"Content-Type": "application/json", "token": TOKEN_USERS}
    result = make_request("GET", url, headers=headers, logger=logger)

    if result and "configuration" in result:
        if logger:
            logger.info("Configuracion del informe %s obtenida exitosamente", report_id)
        return result

    if logger:
        logger.error("No se pudo obtener configuracion del informe %s", report_id)
    return None
