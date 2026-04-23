import json
import logging
import os
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional

import azure.functions as func
import requests
from azure.storage.blob import BlobSasPermissions, BlobServiceClient, generate_blob_sas
from azure.core.exceptions import ResourceExistsError

from utils.GV import create_script as create_gv_script
from utils.GVC import create_script as create_gvc_script
from utils.GVS import create_script as create_gvs_script
from utils.RS import create_script as create_rs_script

app = func.FunctionApp()

SCRIPT_GENERATORS: Dict[str, Dict[str, Any]] = {
    "HJx-yCRnRI": {
        "name": "Grafica Versus con Colores",
        "code": "GVC",
        "generator": create_gvc_script,
    },
    "rJls0xsi8w": {
        "name": "Grafica Versus sin Colores",
        "code": "GVS",
        "generator": create_gvs_script,
    },
    "H1xqWLg6Uw": {
        "name": "Grafica Versus",
        "code": "GV",
        "generator": create_gv_script,
    },
    "BkL5kC4ww": {
        "name": "Resumen empresa",
        "code": "RS",
        "generator": create_rs_script,
    },
}

def _get_query_param(req: func.HttpRequest, key: str) -> str:
    return (req.params.get(key) or "").strip()


def _get_blob_connection_string() -> str:
    connection_string = os.getenv("SCRIPT_BLOB_CONNECTION_STRING") or os.getenv("AzureWebJobsStorage")
    if not connection_string:
        raise ValueError("No se encontro connection string para Blob Storage.")
    return connection_string


def _normalize_webjob_cron(cron_expression: str) -> str:
    cron = " ".join(cron_expression.strip().split())
    return cron


def _is_valid_webjob_cron(cron_expression: str) -> bool:
    return len(cron_expression.split(" ")) == 6


def _build_webjob_zip_bytes(file_path: str, cron_expression: str) -> bytes:
    script_name = os.path.basename(file_path)
    zip_path = f"{file_path}.zip"
    settings_job = json.dumps({"schedule": cron_expression}, ensure_ascii=False, indent=2) + "\n"

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.write(file_path, arcname=script_name)
        zip_file.writestr("settings.job", settings_job)

    with open(zip_path, "rb") as zip_file:
        return zip_file.read()


def _build_webjob_deploy_zip_bytes(file_path: str, cron_expression: str) -> bytes:
    script_name = os.path.basename(file_path)
    zip_path = f"{file_path}.deploy.zip"
    run_cmd = f'@echo off\r\npython "{script_name}"\r\n'
    settings_job = json.dumps({"schedule": cron_expression}, ensure_ascii=False, indent=2) + "\n"

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.write(file_path, arcname=script_name)
        zip_file.writestr("run.cmd", run_cmd)
        zip_file.writestr("settings.job", settings_job)

    with open(zip_path, "rb") as zip_file:
        return zip_file.read()


def _upload_zip_to_blob(zip_bytes: bytes, zip_name: str, report_code: str) -> Dict[str, str]:
    connection_string = _get_blob_connection_string()
    container_name = os.getenv("SCRIPT_BLOB_CONTAINER", "generated-scripts")
    sas_hours = int(os.getenv("SCRIPT_BLOB_SAS_HOURS", "24"))
    utc_now = datetime.now(timezone.utc)
    blob_name = f"{report_code}/{zip_name}"

    blob_service_client = BlobServiceClient.from_connection_string(connection_string)
    container_client = blob_service_client.get_container_client(container_name)
    try:
        container_client.create_container()
    except ResourceExistsError:
        pass

    blob_client = container_client.get_blob_client(blob_name)
    blob_client.upload_blob(zip_bytes, overwrite=True, content_type="application/zip")

    result: Dict[str, str] = {
        "container": container_name,
        "blobName": blob_name,
        "blobUrl": blob_client.url,
    }

    credential = blob_service_client.credential
    account_key = getattr(credential, "account_key", None)
    if account_key:
        sas_token = generate_blob_sas(
            account_name=blob_service_client.account_name,
            container_name=container_name,
            blob_name=blob_name,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=utc_now + timedelta(hours=sas_hours),
        )
        result["downloadUrl"] = f"{blob_client.url}?{sas_token}"
        result["expiresAtUtc"] = (utc_now + timedelta(hours=sas_hours)).isoformat()

    return result


def _set_blob_metadata(container_name: str, blob_name: str, metadata: Dict[str, str]) -> None:
    connection_string = _get_blob_connection_string()
    blob_service_client = BlobServiceClient.from_connection_string(connection_string)
    blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
    blob_client.set_blob_metadata(metadata=metadata)


def _sanitize_metadata_value(value: str, max_len: int = 512) -> str:
    clean = " ".join(str(value).replace("\n", " ").replace("\r", " ").split())
    return clean[:max_len]


def _deploy_to_webjob(zip_bytes: bytes, job_name: str) -> Optional[Dict[str, Any]]:
    deploy_enabled = os.getenv("WEBJOB_DEPLOY_ENABLED", "false").strip().lower() == "true"
    if not deploy_enabled:
        return None

    app_name = os.getenv("WEBJOB_APP_NAME", "").strip()
    scm_user = os.getenv("WEBJOB_SCM_USER", "").strip()
    scm_password = os.getenv("WEBJOB_SCM_PASSWORD", "").strip()
    if not app_name or not scm_user or not scm_password:
        raise ValueError(
            "Faltan variables WEBJOB_APP_NAME, WEBJOB_SCM_USER o WEBJOB_SCM_PASSWORD para publicar el WebJob."
        )

    kudu_url = f"https://{app_name}.scm.azurewebsites.net/api/triggeredwebjobs/{job_name}"
    zip_filename = f"{job_name}.zip"
    response = requests.put(
        kudu_url,
        data=zip_bytes,
        headers={
            "Content-Type": "application/zip",
            "Content-Disposition": f'attachment; filename="{zip_filename}"', # Comentando esta linea se pueden probar fallos al deploy en el webjob
        },
        auth=(scm_user, scm_password),
        timeout=60,
    )
    if not response.ok:
        raise ValueError(
            f"Error Kudu {response.status_code} al publicar {job_name}: {response.text}"
        )

    payload: Dict[str, Any] = {
        "jobName": job_name,
        "kuduUrl": kudu_url,
        "statusCode": response.status_code,
    }

    try:
        payload["response"] = response.json()
    except ValueError:
        payload["responseText"] = response.text

    return payload


@app.route(route="GraphsVersus", auth_level=func.AuthLevel.FUNCTION)
def graphs_versus(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Processing script generation request.")

    if req.method != "GET":
        return func.HttpResponse(
            json.dumps(
                {
                    "ok": False,
                    "message": "Metodo no permitido. Usa GET.",
                }
            ),
            status_code=405,
            mimetype="application/json",
        )

    id_reporte = _get_query_param(req, "idReporte")
    id_schedule = _get_query_param(req, "idSchedule")
    cron_expression = _normalize_webjob_cron(_get_query_param(req, "cron"))
    if not id_reporte:
        return func.HttpResponse(
            json.dumps(
                {
                    "ok": False,
                    "message": "El parametro 'idReporte' es requerido.",
                }
            ),
            status_code=400,
            mimetype="application/json",
        )

    if not id_schedule:
        return func.HttpResponse(
            json.dumps(
                {
                    "ok": False,
                    "message": "El parametro 'idSchedule' es requerido.",
                }
            ),
            status_code=400,
            mimetype="application/json",
        )

    if not cron_expression:
        return func.HttpResponse(
            json.dumps(
                {
                    "ok": False,
                    "message": "El parametro 'cron' es requerido.",
                }
            ),
            status_code=400,
            mimetype="application/json",
        )

    if not _is_valid_webjob_cron(cron_expression):
        return func.HttpResponse(
            json.dumps(
                {
                    "ok": False,
                    "message": "El parametro 'cron' debe tener 6 campos para WebJobs.",
                    "cron": cron_expression,
                }
            ),
            status_code=400,
            mimetype="application/json",
        )

    mapping = SCRIPT_GENERATORS.get(id_reporte)
    if not mapping:
        return func.HttpResponse(
            json.dumps(
                {
                    "ok": False,
                    "message": f"idReporte no soportado: {id_reporte}",
                    "supported": list(SCRIPT_GENERATORS.keys()),
                }
            ),
            status_code=400,
            mimetype="application/json",
        )

    generator: Callable[..., str] = mapping["generator"]

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            script_path = generator(id_schedule, output_dir=temp_dir)
            zip_bytes = _build_webjob_zip_bytes(script_path, cron_expression)
            zip_name = f"{os.path.splitext(os.path.basename(script_path))[0]}.zip"
            webjob_name = os.path.splitext(os.path.basename(script_path))[0].replace("_", "")
            deploy_zip_bytes = _build_webjob_deploy_zip_bytes(script_path, cron_expression)
            flow_mode = os.getenv("WEBJOB_FLOW_MODE", "blob_first_with_status").strip().lower()

            if flow_mode == "deploy_first":
                webjob_deploy_info = _deploy_to_webjob(deploy_zip_bytes, webjob_name)
                blob_info = _upload_zip_to_blob(zip_bytes, zip_name, mapping["code"])
                _set_blob_metadata(
                    container_name=blob_info["container"],
                    blob_name=blob_info["blobName"],
                    metadata={
                        "deploy_status": "success",
                        "webjob_name": webjob_name,
                        "flow_mode": flow_mode,
                        "id_reporte": id_reporte,
                        "id_schedule": id_schedule,
                        "cron": _sanitize_metadata_value(cron_expression, 64),
                        "deployed_at_utc": datetime.now(timezone.utc).isoformat(),
                    },
                )
            elif flow_mode == "blob_first_with_status":
                blob_info = _upload_zip_to_blob(zip_bytes, zip_name, mapping["code"])
                try:
                    webjob_deploy_info = _deploy_to_webjob(deploy_zip_bytes, webjob_name)
                    _set_blob_metadata(
                        container_name=blob_info["container"],
                        blob_name=blob_info["blobName"],
                        metadata={
                            "deploy_status": "success",
                            "webjob_name": webjob_name,
                            "flow_mode": flow_mode,
                            "id_reporte": id_reporte,
                            "id_schedule": id_schedule,
                            "cron": _sanitize_metadata_value(cron_expression, 64),
                            "deployed_at_utc": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                except Exception as deploy_exc:
                    _set_blob_metadata(
                        container_name=blob_info["container"],
                        blob_name=blob_info["blobName"],
                        metadata={
                            "deploy_status": "failed",
                            "webjob_name": webjob_name,
                            "flow_mode": flow_mode,
                            "id_reporte": id_reporte,
                            "id_schedule": id_schedule,
                            "cron": _sanitize_metadata_value(cron_expression, 64),
                            "deploy_error": _sanitize_metadata_value(str(deploy_exc)),
                            "failed_at_utc": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                    return func.HttpResponse(
                        body=json.dumps(
                            {
                                "ok": False,
                                "message": "Error al desplegar WebJob. El zip se guardo en Blob con estado failed.",
                                "error": str(deploy_exc),
                                "flowMode": flow_mode,
                                "blob": blob_info,
                                "webjobName": webjob_name,
                            }
                        ),
                        status_code=502,
                        mimetype="application/json",
                    )
            else:
                return func.HttpResponse(
                    body=json.dumps(
                        {
                            "ok": False,
                            "message": "Valor invalido en WEBJOB_FLOW_MODE. Usa deploy_first o blob_first_with_status.",
                            "flowMode": flow_mode,
                        }
                    ),
                    status_code=500,
                    mimetype="application/json",
                )
    except Exception as exc:
        logging.exception("Error creating script.")
        return func.HttpResponse(
            json.dumps(
                {
                    "ok": False,
                    "message": "Error al generar script.",
                    "error": str(exc),
                }
            ),
            status_code=500,
            mimetype="application/json",
        )

    return func.HttpResponse(
        body=json.dumps(
            {
                "ok": True,
                "idReporte": id_reporte,
                "idSchedule": id_schedule,
                "scriptType": mapping["name"],
                "zipFileName": zip_name,
                "cron": cron_expression,
                "webjobName": webjob_name,
                "flowMode": flow_mode,
                "blob": blob_info,
                "webjobDeploy": webjob_deploy_info,
                "message": "Script generado y cargado en Blob Storage.",
            }
        ),
        status_code=200,
        mimetype="application/json",
    )
