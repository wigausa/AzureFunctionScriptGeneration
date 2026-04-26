import json
import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict

import azure.functions as func
from utils.helpers.artifact_utils import get_artifact_names
from utils.helpers.blob_utils import (
    build_blob_metadata,
    delete_blob,
    find_blob_by_schedule,
    set_blob_metadata,
    upload_zip_to_blob,
)
from utils.helpers.http_utils import (
    get_request_param,
    is_valid_webjob_cron,
    json_response,
    normalize_webjob_cron,
    parse_exception_payload,
    validation_error_response,
)
from utils.helpers.webjob_utils import (
    build_webjob_deploy_zip_bytes,
    build_webjob_zip_bytes,
    delete_webjob,
    deploy_to_webjob,
)

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


def _generate_and_publish_script(id_reporte: str, id_schedule: str, cron_expression: str) -> Dict[str, Any]:
    artifact_names = get_artifact_names(
        script_generators=SCRIPT_GENERATORS,
        id_reporte=id_reporte,
        id_schedule=id_schedule,
    )
    mapping = artifact_names["mapping"]
    generator: Callable[..., str] = mapping["generator"]

    with tempfile.TemporaryDirectory() as temp_dir:
        script_path = generator(id_schedule, output_dir=temp_dir)
        zip_bytes = build_webjob_zip_bytes(script_path, cron_expression)
        zip_name = f"{os.path.splitext(os.path.basename(script_path))[0]}.zip"
        webjob_name = os.path.splitext(os.path.basename(script_path))[0].replace("_", "")
        deploy_zip_bytes = build_webjob_deploy_zip_bytes(script_path, cron_expression)
        flow_mode = os.getenv("WEBJOB_FLOW_MODE", "blob_first_with_status").strip().lower()

        if flow_mode == "deploy_first":
            webjob_deploy_info = deploy_to_webjob(deploy_zip_bytes, webjob_name)
            blob_info = upload_zip_to_blob(zip_bytes, zip_name, mapping["code"])
            set_blob_metadata(
                container_name=blob_info["container"],
                blob_name=blob_info["blobName"],
                metadata=build_blob_metadata(
                    deploy_status="success",
                    webjob_name=webjob_name,
                    flow_mode=flow_mode,
                    id_reporte=id_reporte,
                    id_schedule=id_schedule,
                    cron_expression=cron_expression,
                    timestamp_key="deployed_at_utc",
                    timestamp_value=datetime.now(timezone.utc).isoformat(),
                ),
            )
        elif flow_mode == "blob_first_with_status":
            blob_info = upload_zip_to_blob(zip_bytes, zip_name, mapping["code"])
            try:
                webjob_deploy_info = deploy_to_webjob(deploy_zip_bytes, webjob_name)
                set_blob_metadata(
                    container_name=blob_info["container"],
                    blob_name=blob_info["blobName"],
                    metadata=build_blob_metadata(
                        deploy_status="success",
                        webjob_name=webjob_name,
                        flow_mode=flow_mode,
                        id_reporte=id_reporte,
                        id_schedule=id_schedule,
                        cron_expression=cron_expression,
                        timestamp_key="deployed_at_utc",
                        timestamp_value=datetime.now(timezone.utc).isoformat(),
                    ),
                )
            except Exception as deploy_exc:
                set_blob_metadata(
                    container_name=blob_info["container"],
                    blob_name=blob_info["blobName"],
                    metadata=build_blob_metadata(
                        deploy_status="failed",
                        webjob_name=webjob_name,
                        flow_mode=flow_mode,
                        id_reporte=id_reporte,
                        id_schedule=id_schedule,
                        cron_expression=cron_expression,
                        timestamp_key="failed_at_utc",
                        timestamp_value=datetime.now(timezone.utc).isoformat(),
                        deploy_error=str(deploy_exc),
                    ),
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
        return json_response(
            {
                "ok": False,
                "operationId": operation_id,
                "message": f"Metodo no permitido. Usa {expected_method}.",
            },
            status_code=405,
        )

    id_reporte = get_request_param(req, "idReporte")
    id_schedule = get_request_param(req, "idSchedule")
    cron_expression = normalize_webjob_cron(get_request_param(req, "cron"))
    _trace_log(operation_id, "create_or_update", "started", method=expected_method, idReporte=id_reporte, idSchedule=id_schedule)

    if not id_reporte:
        return validation_error_response(
            operation_id=operation_id,
            message="El parametro 'idReporte' es requerido en el body JSON.",
            field="idReporte",
            action="create_or_update",
            trace_log=_trace_log,
        )

    if not id_schedule:
        return validation_error_response(
            operation_id=operation_id,
            message="El parametro 'idSchedule' es requerido en el body JSON.",
            field="idSchedule",
            action="create_or_update",
            trace_log=_trace_log,
        )

    if not cron_expression:
        return validation_error_response(
            operation_id=operation_id,
            message="El parametro 'cron' es requerido en el body JSON.",
            field="cron",
            action="create_or_update",
            trace_log=_trace_log,
        )

    if not is_valid_webjob_cron(cron_expression):
        _trace_log(operation_id, "create_or_update", "validation_error", field="cron", reason="invalid_webjob_cron")
        return json_response(
            {
                "ok": False,
                "operationId": operation_id,
                "message": "El parametro 'cron' debe tener 6 campos para WebJobs.",
                "cron": cron_expression,
            },
            status_code=400,
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
        parsed_payload = parse_exception_payload(value_exc)
        if parsed_payload is not None:
            return json_response(parsed_payload, status_code=400)
        return json_response(
            {
                "ok": False,
                "operationId": operation_id,
                "message": "Error de validacion.",
                "error": str(value_exc),
            },
            status_code=400,
        )
    except Exception as exc:
        logging.exception("Error creating/updating script.")
        _trace_log(operation_id, "create_or_update", "unexpected_error", error=str(exc))
        return json_response(
            {
                "ok": False,
                "operationId": operation_id,
                "message": "Error al generar script.",
                "error": str(exc),
            },
            status_code=500,
        )

    return json_response(
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
        },
        status_code=200,
    )


def _execute_graphs_versus_delete(req: func.HttpRequest) -> func.HttpResponse:
    operation_id = str(uuid.uuid4())

    if req.method != "DELETE":
        _trace_log(operation_id, "delete", "method_not_allowed", currentMethod=req.method)
        return json_response(
            {
                "ok": False,
                "operationId": operation_id,
                "message": "Metodo no permitido. Usa DELETE.",
            },
            status_code=405,
        )

    id_reporte = get_request_param(req, "idReporte")
    id_schedule = get_request_param(req, "idSchedule")
    _trace_log(operation_id, "delete", "started", idReporte=id_reporte, idSchedule=id_schedule)

    if not id_reporte:
        return validation_error_response(
            operation_id=operation_id,
            message="El parametro 'idReporte' es requerido en el body JSON.",
            field="idReporte",
            action="delete",
            trace_log=_trace_log,
        )

    if not id_schedule:
        return validation_error_response(
            operation_id=operation_id,
            message="El parametro 'idSchedule' es requerido en el body JSON.",
            field="idSchedule",
            action="delete",
            trace_log=_trace_log,
        )

    try:
        artifact_names = get_artifact_names(
            script_generators=SCRIPT_GENERATORS,
            id_reporte=id_reporte,
            id_schedule=id_schedule,
        )
        mapping = artifact_names["mapping"]
        webjob_name = artifact_names["webjobName"]

        blob_info = find_blob_by_schedule(mapping["code"], id_reporte, id_schedule)
        if blob_info:
            metadata = blob_info.get("metadata", {})
            webjob_name = metadata.get("webjob_name") or webjob_name
            blob_delete_result = delete_blob(blob_info["container"], blob_info["blobName"])
        else:
            inferred_blob_name = f"{mapping['code']}/{artifact_names['zipName']}"
            container_name = os.getenv("SCRIPT_BLOB_CONTAINER", "generated-scripts")
            blob_delete_result = delete_blob(container_name, inferred_blob_name)

        _trace_log(
            operation_id,
            "delete",
            "blob_processed",
            blobStatus=blob_delete_result.get("status"),
            blobName=blob_delete_result.get("blobName"),
        )

        webjob_delete_result = delete_webjob(webjob_name)
        _trace_log(
            operation_id,
            "delete",
            "webjob_processed",
            webjobStatus=webjob_delete_result.get("status"),
            webjobName=webjob_name,
        )

        return json_response(
            {
                "ok": True,
                "operationId": operation_id,
                "idReporte": id_reporte,
                "idSchedule": id_schedule,
                "blobDelete": blob_delete_result,
                "webjobDelete": webjob_delete_result,
                "message": "Proceso de eliminacion completado.",
            },
            status_code=200,
        )
    except ValueError as value_exc:
        _trace_log(operation_id, "delete", "validation_error", error=str(value_exc))
        parsed_payload = parse_exception_payload(value_exc)
        if parsed_payload is not None:
            return json_response(parsed_payload, status_code=400)
        return json_response(
            {
                "ok": False,
                "operationId": operation_id,
                "message": "Error de validacion en delete.",
                "error": str(value_exc),
            },
            status_code=400,
        )
    except Exception as exc:
        logging.exception("Error deleting script artifacts.")
        _trace_log(operation_id, "delete", "unexpected_error", error=str(exc))
        return json_response(
            {
                "ok": False,
                "operationId": operation_id,
                "message": "Error al eliminar artefactos.",
                "error": str(exc),
            },
            status_code=500,
        )


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
