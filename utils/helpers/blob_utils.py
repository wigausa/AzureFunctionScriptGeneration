import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.storage.blob import BlobSasPermissions, BlobServiceClient, generate_blob_sas


def get_blob_connection_string() -> str:
    connection_string = os.getenv("SCRIPT_BLOB_CONNECTION_STRING") or os.getenv("AzureWebJobsStorage")
    if not connection_string:
        raise ValueError("No se encontro connection string para Blob Storage.")
    return connection_string


def upload_zip_to_blob(zip_bytes: bytes, zip_name: str, report_code: str) -> Dict[str, str]:
    connection_string = get_blob_connection_string()
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


def set_blob_metadata(container_name: str, blob_name: str, metadata: Dict[str, str]) -> None:
    connection_string = get_blob_connection_string()
    blob_service_client = BlobServiceClient.from_connection_string(connection_string)
    blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
    blob_client.set_blob_metadata(metadata=metadata)


def find_blob_by_schedule(report_code: str, id_reporte: str, id_schedule: str) -> Optional[Dict[str, Any]]:
    connection_string = get_blob_connection_string()
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


def delete_blob(container_name: str, blob_name: str) -> Dict[str, Any]:
    connection_string = get_blob_connection_string()
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


def sanitize_metadata_value(value: str, max_len: int = 512) -> str:
    clean = " ".join(str(value).replace("\n", " ").replace("\r", " ").split())
    return clean[:max_len]


def build_blob_metadata(
    *,
    deploy_status: str,
    webjob_name: str,
    flow_mode: str,
    id_reporte: str,
    id_schedule: str,
    cron_expression: str,
    timestamp_key: str,
    timestamp_value: str,
    deploy_error: str = "",
) -> Dict[str, str]:
    metadata: Dict[str, str] = {
        "deploy_status": deploy_status,
        "webjob_name": webjob_name,
        "flow_mode": flow_mode,
        "id_reporte": id_reporte,
        "id_schedule": id_schedule,
        "cron": sanitize_metadata_value(cron_expression, 64),
        timestamp_key: timestamp_value,
    }
    if deploy_error:
        metadata["deploy_error"] = sanitize_metadata_value(deploy_error)
    return metadata
