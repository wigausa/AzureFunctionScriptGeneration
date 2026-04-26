import json
import logging
import os
import tempfile
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional

import azure.functions as func
import requests
from azure.storage.blob import BlobSasPermissions, BlobServiceClient, generate_blob_sas
from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError

from utils.templates.GV import create_script as create_gv_script
from utils.templates.GVC import create_script as create_gvc_script
from utils.templates.GVS import create_script as create_gvs_script
from utils.templates.RS import create_script as create_rs_script

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
        "name": "Resumen Empresa",
        "code": "RS",
        "generator": create_rs_script,
    },
}


def _trace_log(operation_id: str, action: str, status: str, **fields: Any) -> None:
    payload: Dict[str, Any] = {
        "operationId": operation_id,
        "action": action,
        "status": status,
        "timestampUtc": datetime.now(timezone.utc).isoformat(),
    }
    payload.update(fields)
    logging.info(json.dumps(payload, ensure_ascii=False))

def _get_body_param(req: func.HttpRequest, key: str) -> str:
    try:
        body = req.get_json()
    except ValueError:
        return ""

    if not isinstance(body, dict):
        return ""

    return str(body.get(key) or "").strip()


def _get_request_param(req: func.HttpRequest, key: str) -> str:
    return _get_body_param(req, key)


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


def _find_blob_by_schedule(report_code: str, id_reporte: str, id_schedule: str) -> Optional[Dict[str, Any]]:
    connection_string = _get_blob_connection_string()
    container_name = os.getenv("SCRIPT_BLOB_CONTAINER", "generated-scripts")

    blob_service_client = BlobServiceClient.from_connection_string(connection_string)
    container_client = blob_service_client.get_container_client(container_name)

    blobs = container_client.list_blobs(name_starts_with=f"{report_code}/", include=["metadata"])
    for blob in blobs:
        metadata = blob.metadata or {}
        if metadata.get("id_schedule") == id_schedule and metadata.get("id_reporte") == id_reporte:
            return {
                "container": container_name,
                "blobName": blob.name,
                "blobUrl": container_client.get_blob_client(blob.name).url,
                "metadata": metadata,
            }
    return None


def _delete_blob(container_name: str, blob_name: str) -> Dict[str, Any]:
    connection_string = _get_blob_connection_string()
    blob_service_client = BlobServiceClient.from_connection_string(connection_string)
    blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)

    try:
        blob_client.delete_blob(delete_snapshots="include")
        return {
            "status": "deleted",
            "container": container_name,
            "blobName": blob_name,
            "blobUrl": blob_client.url,
        }
    except ResourceNotFoundError:
        return {
            "status": "not_found",
            "container": container_name,
            "blobName": blob_name,
            "blobUrl": blob_client.url,
        }


def _get_artifact_names(id_reporte: str, id_schedule: str) -> Dict[str, Any]:
    mapping = SCRIPT_GENERATORS.get(id_reporte)
    if not mapping:
        raise ValueError(
            json.dumps(
                {
                    "ok": False,
                    "message": f"idReporte no soportado: {id_reporte}",
                    "supported": list(SCRIPT_GENERATORS.keys()),
                }
            )
        )

    generator: Callable[..., str] = mapping["generator"]
    with tempfile.TemporaryDirectory() as temp_dir:
        script_path = generator(id_schedule, output_dir=temp_dir)
        zip_name = f"{os.path.splitext(os.path.basename(script_path))[0]}.zip"
        webjob_name = os.path.splitext(os.path.basename(script_path))[0].replace("_", "")

    return {
        "mapping": mapping,
        "zipName": zip_name,
        "webjobName": webjob_name,
    }


def _sanitize_metadata_value(value: str, max_len: int = 512) -> str:
    clean = " ".join(str(value).replace("\n", " ").replace("\r", " ").split())
    return clean[:max_len]


def _generate_and_publish_script(id_reporte: str, id_schedule: str, cron_expression: str) -> Dict[str, Any]:
    artifact_names = _get_artifact_names(id_reporte=id_reporte, id_schedule=id_schedule)
    mapping = artifact_names["mapping"]
    generator: Callable[..., str] = mapping["generator"]

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
                raise RuntimeError(
                    json.dumps(
                        {
                            "ok": False,
                            "message": "Error al desplegar WebJob. El zip se guardo en Blob con estado failed.",
                            "error": str(deploy_exc),
                            "flowMode": flow_mode,
                            "blob": blob_info,
                            "webjobName": webjob_name,
                        }
                    )
                )
        else:
            raise ValueError(
                json.dumps(
                    {
                        "ok": False,
                        "message": "Valor invalido en WEBJOB_FLOW_MODE. Usa deploy_first o blob_first_with_status.",
                        "flowMode": flow_mode,
                    }
                )
            )

    return {
        "mapping": mapping,
        "zipName": zip_name,
        "webjobName": webjob_name,
        "flowMode": flow_mode,
        "blob": blob_info,
        "webjobDeploy": webjob_deploy_info,
    }


def _execute_graphs_versus(req: func.HttpRequest, expected_method: str, success_message: str) -> func.HttpResponse:
    operation_id = str(uuid.uuid4())

    if req.method != expected_method:
        _trace_log(operation_id, "create_or_update", "method_not_allowed", expectedMethod=expected_method, currentMethod=req.method)
        return func.HttpResponse(
            json.dumps(
                {
                    "ok": False,
                    "operationId": operation_id,
                    "message": f"Metodo no permitido. Usa {expected_method}.",
                }
            ),
            status_code=405,
            mimetype="application/json",
        )

    id_reporte = _get_request_param(req, "idReporte")
    id_schedule = _get_request_param(req, "idSchedule")
    cron_expression = _normalize_webjob_cron(_get_request_param(req, "cron"))
    _trace_log(operation_id, "create_or_update", "started", method=expected_method, idReporte=id_reporte, idSchedule=id_schedule)

    if not id_reporte:
        _trace_log(operation_id, "create_or_update", "validation_error", field="idReporte")
        return func.HttpResponse(
            json.dumps(
                {
                    "ok": False,
                    "operationId": operation_id,
                    "message": "El parametro 'idReporte' es requerido en el body JSON.",
                }
            ),
            status_code=400,
            mimetype="application/json",
        )

    if not id_schedule:
        _trace_log(operation_id, "create_or_update", "validation_error", field="idSchedule")
        return func.HttpResponse(
            json.dumps(
                {
                    "ok": False,
                    "operationId": operation_id,
                    "message": "El parametro 'idSchedule' es requerido en el body JSON.",
                }
            ),
            status_code=400,
            mimetype="application/json",
        )

    if not cron_expression:
        _trace_log(operation_id, "create_or_update", "validation_error", field="cron")
        return func.HttpResponse(
            json.dumps(
                {
                    "ok": False,
                    "operationId": operation_id,
                    "message": "El parametro 'cron' es requerido en el body JSON.",
                }
            ),
            status_code=400,
            mimetype="application/json",
        )

    if not _is_valid_webjob_cron(cron_expression):
        _trace_log(operation_id, "create_or_update", "validation_error", field="cron", reason="invalid_webjob_cron")
        return func.HttpResponse(
            json.dumps(
                {
                    "ok": False,
                    "operationId": operation_id,
                    "message": "El parametro 'cron' debe tener 6 campos para WebJobs.",
                    "cron": cron_expression,
                }
            ),
            status_code=400,
            mimetype="application/json",
        )

    try:
        _trace_log(operation_id, "create_or_update", "publishing_started")
        result = _generate_and_publish_script(
            id_reporte=id_reporte,
            id_schedule=id_schedule,
            cron_expression=cron_expression,
        )
        _trace_log(operation_id, "create_or_update", "publishing_completed", webjobName=result["webjobName"], blobName=result["blob"]["blobName"])
    except RuntimeError as runtime_exc:
        _trace_log(operation_id, "create_or_update", "webjob_deploy_error", error=str(runtime_exc))
        payload = str(runtime_exc)
        return func.HttpResponse(payload, status_code=502, mimetype="application/json")
    except ValueError as value_exc:
        _trace_log(operation_id, "create_or_update", "validation_error", error=str(value_exc))
        payload = str(value_exc)
        try:
            json.loads(payload)
            return func.HttpResponse(payload, status_code=400, mimetype="application/json")
        except ValueError:
            return func.HttpResponse(
                json.dumps(
                    {
                        "ok": False,
                        "operationId": operation_id,
                        "message": "Error de validacion.",
                        "error": payload,
                    }
                ),
                status_code=400,
                mimetype="application/json",
            )
    except Exception as exc:
        logging.exception("Error creating/updating script.")
        _trace_log(operation_id, "create_or_update", "unexpected_error", error=str(exc))
        return func.HttpResponse(
            json.dumps(
                {
                    "ok": False,
                    "operationId": operation_id,
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
                "operationId": operation_id,
                "idReporte": id_reporte,
                "idSchedule": id_schedule,
                "scriptType": result["mapping"]["name"],
                "zipFileName": result["zipName"],
                "cron": cron_expression,
                "webjobName": result["webjobName"],
                "flowMode": result["flowMode"],
                "blob": result["blob"],
                "webjobDeploy": result["webjobDeploy"],
                "message": success_message,
            }
        ),
        status_code=200,
        mimetype="application/json",
    )


def _delete_webjob(job_name: str) -> Dict[str, Any]:
    deploy_enabled = os.getenv("WEBJOB_DEPLOY_ENABLED", "false").strip().lower() == "true"
    if not deploy_enabled:
        return {
            "status": "skipped",
            "reason": "WEBJOB_DEPLOY_ENABLED=false",
            "jobName": job_name,
        }

    app_name = os.getenv("WEBJOB_APP_NAME", "").strip()
    scm_user = os.getenv("WEBJOB_SCM_USER", "").strip()
    scm_password = os.getenv("WEBJOB_SCM_PASSWORD", "").strip()
    if not app_name or not scm_user or not scm_password:
        raise ValueError(
            "Faltan variables WEBJOB_APP_NAME, WEBJOB_SCM_USER o WEBJOB_SCM_PASSWORD para eliminar el WebJob."
        )

    kudu_url = f"https://{app_name}.scm.azurewebsites.net/api/triggeredwebjobs/{job_name}"
    response = requests.delete(kudu_url, auth=(scm_user, scm_password), timeout=60)

    if response.status_code == 404:
        return {
            "status": "not_found",
            "jobName": job_name,
            "kuduUrl": kudu_url,
            "statusCode": response.status_code,
        }

    if not response.ok:
        raise ValueError(
            f"Error Kudu {response.status_code} al eliminar {job_name}: {response.text}"
        )

    payload: Dict[str, Any] = {
        "status": "deleted",
        "jobName": job_name,
        "kuduUrl": kudu_url,
        "statusCode": response.status_code,
    }

    try:
        payload["response"] = response.json()
    except ValueError:
        payload["responseText"] = response.text

    return payload


def _execute_graphs_versus_delete(req: func.HttpRequest) -> func.HttpResponse:
    operation_id = str(uuid.uuid4())

    if req.method != "DELETE":
        _trace_log(operation_id, "delete", "method_not_allowed", currentMethod=req.method)
        return func.HttpResponse(
            json.dumps(
                {
                    "ok": False,
                    "operationId": operation_id,
                    "message": "Metodo no permitido. Usa DELETE.",
                }
            ),
            status_code=405,
            mimetype="application/json",
        )

    id_reporte = _get_request_param(req, "idReporte")
    id_schedule = _get_request_param(req, "idSchedule")
    _trace_log(operation_id, "delete", "started", idReporte=id_reporte, idSchedule=id_schedule)

    if not id_reporte:
        _trace_log(operation_id, "delete", "validation_error", field="idReporte")
        return func.HttpResponse(
            json.dumps(
                {
                    "ok": False,
                    "operationId": operation_id,
                    "message": "El parametro 'idReporte' es requerido en el body JSON.",
                }
            ),
            status_code=400,
            mimetype="application/json",
        )

    if not id_schedule:
        _trace_log(operation_id, "delete", "validation_error", field="idSchedule")
        return func.HttpResponse(
            json.dumps(
                {
                    "ok": False,
                    "operationId": operation_id,
                    "message": "El parametro 'idSchedule' es requerido en el body JSON.",
                }
            ),
            status_code=400,
            mimetype="application/json",
        )

    try:
        artifact_names = _get_artifact_names(id_reporte=id_reporte, id_schedule=id_schedule)
        mapping = artifact_names["mapping"]
        webjob_name = artifact_names["webjobName"]

        blob_info = _find_blob_by_schedule(mapping["code"], id_reporte, id_schedule)
        if blob_info:
            metadata = blob_info.get("metadata", {})
            webjob_name = metadata.get("webjob_name") or webjob_name
            blob_delete_result = _delete_blob(blob_info["container"], blob_info["blobName"])
        else:
            inferred_blob_name = f"{mapping['code']}/{artifact_names['zipName']}"
            container_name = os.getenv("SCRIPT_BLOB_CONTAINER", "generated-scripts")
            blob_delete_result = _delete_blob(container_name, inferred_blob_name)

        _trace_log(
            operation_id,
            "delete",
            "blob_processed",
            blobStatus=blob_delete_result.get("status"),
            blobName=blob_delete_result.get("blobName"),
        )

        webjob_delete_result = _delete_webjob(webjob_name)
        _trace_log(
            operation_id,
            "delete",
            "webjob_processed",
            webjobStatus=webjob_delete_result.get("status"),
            webjobName=webjob_name,
        )

        return func.HttpResponse(
            json.dumps(
                {
                    "ok": True,
                    "operationId": operation_id,
                    "idReporte": id_reporte,
                    "idSchedule": id_schedule,
                    "blobDelete": blob_delete_result,
                    "webjobDelete": webjob_delete_result,
                    "message": "Proceso de eliminacion completado.",
                }
            ),
            status_code=200,
            mimetype="application/json",
        )
    except ValueError as value_exc:
        _trace_log(operation_id, "delete", "validation_error", error=str(value_exc))
        payload = str(value_exc)
        try:
            json.loads(payload)
            return func.HttpResponse(payload, status_code=400, mimetype="application/json")
        except ValueError:
            return func.HttpResponse(
                json.dumps(
                    {
                        "ok": False,
                        "operationId": operation_id,
                        "message": "Error de validacion en delete.",
                        "error": payload,
                    }
                ),
                status_code=400,
                mimetype="application/json",
            )
    except Exception as exc:
        logging.exception("Error deleting script artifacts.")
        _trace_log(operation_id, "delete", "unexpected_error", error=str(exc))
        return func.HttpResponse(
            json.dumps(
                {
                    "ok": False,
                    "operationId": operation_id,
                    "message": "Error al eliminar artefactos.",
                    "error": str(exc),
                }
            ),
            status_code=500,
            mimetype="application/json",
        )


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


@app.route(route="GraphsVersusCreate", auth_level=func.AuthLevel.FUNCTION)
def graphs_versus_create(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Processing script generation request.")

    return _execute_graphs_versus(
        req=req,
        expected_method="POST",
        success_message="Script generado y cargado en Blob Storage.",
    )


@app.route(route="GraphsVersusUpdate", auth_level=func.AuthLevel.FUNCTION)
def graphs_versus_update(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Processing script update request.")

    return _execute_graphs_versus(
        req=req,
        expected_method="PUT",
        success_message="Script actualizado en Blob Storage y WebJob.",
    )


@app.route(route="GraphsVersusDelete", auth_level=func.AuthLevel.FUNCTION)
def graphs_versus_delete(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Processing script delete request.")
    return _execute_graphs_versus_delete(req)
