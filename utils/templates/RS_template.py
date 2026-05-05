#!/usr/bin/env python3
"""
Script de generación de reportes {report_code} para Azure WebJobs
Versión Python 3.12+ - Generado automáticamente
Report ID: {report_id}
"""
import logging
import importlib
import os
import site
import subprocess
import sys
import time


def _ensure_user_site_in_path() -> None:
    try:
        user_site = subprocess.check_output([sys.executable, "-m", "site", "--user-site"]).strip().decode("utf-8")
    except Exception:
        user_site = site.getusersitepackages()
    if user_site and user_site not in sys.path:
        sys.path.append(user_site)


def _module_available(name: str) -> bool:
    try:
        importlib.import_module(name)
        return True
    except ImportError:
        return False


def install_dependencies():
    _ensure_user_site_in_path()
    requirements_path = "/home/site/wwwroot/requirements.txt"
    missing_dependencies = (not _module_available("requests")) or (not _module_available("dotenv"))

    if not missing_dependencies:
        return

    if os.path.exists(requirements_path):
        subprocess.check_call(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "-r",
                requirements_path,
                "--user",
                "--no-warn-script-location",
            ]
        )
    else:
        required_packages = ["requests==2.32.4", "python-dotenv==1.1.1"]
        for package in required_packages:
            subprocess.check_call(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    package,
                    "--user",
                    "--no-warn-script-location",
                ]
            )

    _ensure_user_site_in_path()
    importlib.invalidate_caches()

    if (not _module_available("requests")) or (not _module_available("dotenv")):
        raise RuntimeError("No se pudieron cargar requests/python-dotenv despues de instalar dependencias.")


install_dependencies()

import json
from typing import Any, Dict, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

TOKEN_USERS = os.getenv("REPORT_API_TOKEN_USERS")
BASE_URL = os.getenv("REPORT_API_BASE_URL").rstrip("/")

REPORT_HTTP_TIMEOUT_SECONDS = int(os.getenv("REPORT_HTTP_TIMEOUT_SECONDS"))
REPORT_HTTP_RETRIES = max(int(os.getenv("REPORT_HTTP_RETRIES")), 1)
REPORT_API_BACKOFF = float(os.getenv("REPORT_API_BACKOFF"))
AZURE_FUNCTION_TIMEOUT_SECONDS = int(os.getenv("AZURE_FUNCTION_TIMEOUT_SECONDS"))

AZURE_FUNCTION_URL = os.getenv("{function_env_var}", "{function_default_url}")


def make_request(
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    json_body: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    for attempt in range(1, REPORT_HTTP_RETRIES + 1):
        try:
            response = requests.request(
                method,
                url,
                headers=headers,
                json=json_body,
                timeout=REPORT_HTTP_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            logger.error(
                "Error en petición %s %s (intento %s/%s): %s",
                method,
                url,
                attempt,
                REPORT_HTTP_RETRIES,
                exc,
            )
            if attempt < REPORT_HTTP_RETRIES:
                time.sleep(REPORT_API_BACKOFF * attempt)
    return None


def get_data_informe() -> Optional[Dict[str, Any]]:
    url = f"{{BASE_URL}}/v1/reports/{report_id}"
    headers = {{"Content-Type": "application/json", "token": TOKEN_USERS}}
    result = make_request("GET", url, headers=headers)

    if result and "configuration" in result:
        logger.info("Configuración del informe {report_code} obtenida exitosamente")
        return result

    logger.error("No se pudo obtener configuración del informe {report_code}")
    return None


def get_reportes_graficos() -> Optional[Dict[str, Any]]:
    informe = get_data_informe()
    if not informe:
        return None

    try:
        config = informe["configuration"]
        url = f"{{BASE_URL}}/{reportes_endpoint_path}"
        headers = {{"token": config["token"]}}
        body = {{
            "sensorsId": config["sensores"],
            "startDate": config["fechas"]["fechaInicial"],
            "endDate": config["fechas"]["fechaFinal"],
            "typeSensors": config["typeSensors"],
            "configurationSendingData": informe["configurationSendingData"],
        }}
        logger.info(
            "Obteniendo {reportes_label} para período: %s - %s",
            body["startDate"],
            body["endDate"],
        )
        result = make_request("POST", url, headers=headers, json_body=body)
        if result:
            return result
        logger.error("No se pudieron obtener {reportes_label}")
        return None
    except KeyError as exc:
        logger.error("Falta configuración {report_code}: %s", exc)
        return None


def send_to_azure_function(resumen: Any, datos_usuario: Any) -> Optional[bytes]:
    payload = {{
        "resumen": resumen,
        "datosUsuario": datos_usuario,
    }}

    try:
        logger.info("Enviando datos a Azure Function {report_code}...")
        response = requests.post(
            AZURE_FUNCTION_URL,
            json=payload,
            timeout=AZURE_FUNCTION_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        logger.info("Datos enviados correctamente a Azure Function {report_code}")
        return response.content
    except requests.RequestException as exc:
        logger.error("Error al enviar datos a Azure Function {report_code}: %s", exc)
        return None


def generate_report() -> bool:
    logger.info("=== Iniciando generación de reporte {report_code} ===")

    try:
        resumen = get_reportes_graficos()
        datos_usuario = get_data_informe()

        if not any([resumen, datos_usuario]):
            logger.error("No se pudo obtener ningún dato para el reporte {report_code}")
            return False

        logger.info(
            "Datos obtenidos - Resumen: %s, Usuario: %s",
            "✓" if resumen else "✗",
            "✓" if datos_usuario else "✗",
        )

        pdf_data = send_to_azure_function(resumen, datos_usuario)
        if pdf_data:
            logger.info("=== Reporte {report_code} generado exitosamente ===")
            return True
        logger.error("Error al generar el reporte {report_code}")
        return False
    except Exception as exc:
        logger.error("Error inesperado durante la generación del reporte {report_code}: %s", exc)
        return False


if __name__ == "__main__":
    success = generate_report()
    if not success:
        sys.exit(1)
