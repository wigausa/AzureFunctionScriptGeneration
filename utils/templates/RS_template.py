
import sys
import subprocess

def install_and_import(package):
    try:
        __import__(package)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", package])

        user_site = subprocess.check_output([sys.executable, "-m", "site", "--user-site"]).strip().decode('utf-8')
        if user_site not in sys.path:
            sys.path.append(user_site)
        globals()[package] = __import__(package)

install_and_import('requests')

import requests
import json

JSREPORT_USER = "wiga"
JSREPORT_PASSWORD = "wiga123*"
TOKEN_USERS = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyIjoiYWRtaW53aWdhIiwiaWQiOjI3MCwiZXhwaXJlZERhdGUiOiIyMDE5LTA3LTIyVDExOjAwOjMyLjA2NzU2ODYtMDU6MDAifQ.BXMx2BKIbkJyD_jRrfhY6Sj_SJbo8gWM8wHghzFvrT0"

def make_request(method, url, headers=None, json_body=None):
    try:
        if json_body:
            response = requests.request(method, url, headers=headers, json=json_body)
        else:
            response = requests.request(method, url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print("Error during request: {{}}".format(e))
        return None
    
def get_data_informe():
    url = "https://superwicloudapi.azurewebsites.net/api/v1/reports/{report_id}"
    headers = {{'Content-Type': 'application/json', 'token': TOKEN_USERS}}
    return make_request('GET', url, headers=headers) or []
    
def get_dataSemnal():
    informe = get_data_informe()
    if not informe:
        return []
    url = "https://superwicloudapi.azurewebsites.net/api/v1/reports/weeklyReport"
    headers = {{'token': informe['configuration']['token']}}
    body = {{
        "sensorsId": informe['configuration']['sensores'],
        "startDate": informe['configuration']['fechas']['fechaInicial'],
        "endDate": informe['configuration']['fechas']['fechaFinal'],
        "typeSensors": informe['configuration']['typeSensors'],
    }}
    return make_request('POST', url, headers=headers, json_body=body) or []

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
    headers = {{'Content-Type': 'application/json'}}

    try:
        response = requests.post("https://jsreportwiga.azurewebsites.net/api/report", headers=headers, auth=(JSREPORT_USER, JSREPORT_PASSWORD), data=json.dumps(report_data))
        response.raise_for_status()
        print("Conexion exitosa y reporte generado.")
    except requests.RequestException as e:
        print("Error al generar el reporte: {{}}".format(e))

if __name__ == "__main__":
    generate_report()
