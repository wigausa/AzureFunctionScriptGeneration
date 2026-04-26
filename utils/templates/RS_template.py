#!/usr/bin/env python3

import json
import importlib
import os
import site
import subprocess
import sys
import time


def _ensure_user_site_in_path():
    try:
        user_site = subprocess.check_output([sys.executable, "-m", "site", "--user-site"]).strip().decode("utf-8")
    except Exception:
        user_site = site.getusersitepackages()
    if user_site and user_site not in sys.path:
        sys.path.append(user_site)


def install_and_import(package):
    _ensure_user_site_in_path()
    try:
        __import__(package)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", package])
        _ensure_user_site_in_path()
        importlib.invalidate_caches()
        globals()[package] = __import__(package)


install_and_import("requests")

import requests

DEFAULT_TOKEN_USERS = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyIjoiYWRtaW53aWdhIiwiaWQiOjI3MCwiZXhwaXJlZERhdGUiOiIyMDE5LTA3LTIyVDExOjAwOjMyLjA2NzU2ODYtMDU6MDAifQ.BXMx2BKIbkJyD_jRrfhY6Sj_SJbo8gWM8wHghzFvrT0"
DEFAULT_REPORT_API_BASE_URL = "https://superwicloudapi.azurewebsites.net/api"
DEFAULT_JSREPORT_URL = "https://jsreportwiga.azurewebsites.net/api/report"

TOKEN_USERS = os.getenv("REPORT_API_TOKEN_USERS", DEFAULT_TOKEN_USERS)
BASE_URL_RAW = os.getenv("REPORT_API_BASE_URL", DEFAULT_REPORT_API_BASE_URL).rstrip("/")
BASE_URL_V1 = BASE_URL_RAW if BASE_URL_RAW.endswith("/v1") else f"{{BASE_URL_RAW}}/v1"

REPORT_HTTP_TIMEOUT_SECONDS = int(os.getenv("REPORT_HTTP_TIMEOUT_SECONDS", "30"))
REPORT_HTTP_RETRIES = max(int(os.getenv("REPORT_HTTP_RETRIES", "3")), 1)
REPORT_API_BACKOFF = float(os.getenv("REPORT_API_BACKOFF", "0.5"))

JSREPORT_USER = os.getenv("JSREPORT_USER", "wiga")
JSREPORT_PASSWORD = os.getenv("JSREPORT_PASSWORD", "wiga123*")
JSREPORT_TIMEOUT_SECONDS = int(os.getenv("JSREPORT_TIMEOUT_SECONDS", "60"))
JSREPORT_URL = os.getenv("JSREPORT_URL", DEFAULT_JSREPORT_URL)


def make_request(method, url, headers=None, json_body=None):
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
            print("Error during request (attempt {}/{}): {}".format(attempt, REPORT_HTTP_RETRIES, exc))
            if attempt < REPORT_HTTP_RETRIES:
                time.sleep(REPORT_API_BACKOFF * attempt)
    return None


def get_data_informe():
    url = f"{{BASE_URL_V1}}/reports/{report_id}"
    headers = {{"Content-Type": "application/json", "token": TOKEN_USERS}}
    return make_request("GET", url, headers=headers) or []


def get_dataSemnal():
    informe = get_data_informe()
    if not informe:
        return []

    url = f"{{BASE_URL_V1}}/reports/weeklyReport"
    headers = {{"token": informe["configuration"]["token"]}}
    body = {{
        "sensorsId": informe["configuration"]["sensores"],
        "startDate": informe["configuration"]["fechas"]["fechaInicial"],
        "endDate": informe["configuration"]["fechas"]["fechaFinal"],
        "typeSensors": informe["configuration"]["typeSensors"],
    }}
    return make_request("POST", url, headers=headers, json_body=body) or []


def generate_report():
    report_data = {{
        "template": {{
            "shortid": "BkL5kC4ww",
            "engine": "handlebars"
        }},
        "data": {{
            "resumen": get_dataSemnal(),
            "datosUsuario": get_data_informe()
        }},
        "options": {{
            "Preview": True
        }}
    }}
    headers = {{"Content-Type": "application/json"}}

    try:
        response = requests.post(
            JSREPORT_URL,
            headers=headers,
            auth=(JSREPORT_USER, JSREPORT_PASSWORD),
            data=json.dumps(report_data),
            timeout=JSREPORT_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        print("Conexion exitosa y reporte generado.")
    except requests.RequestException as exc:
        print("Error al generar el reporte: {}".format(exc))


if __name__ == "__main__":
    generate_report()
