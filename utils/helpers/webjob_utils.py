import json
import os
import zipfile
from typing import Any, Dict, Optional

import requests


def build_webjob_zip_bytes(file_path: str, cron_expression: str) -> bytes:
    script_name = os.path.basename(file_path)
    zip_path = f"{file_path}.zip"
    settings_job = json.dumps({"schedule": cron_expression}, ensure_ascii=False, indent=2) + "\n"

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.write(file_path, arcname=script_name)
        zip_file.writestr("settings.job", settings_job)

    with open(zip_path, "rb") as zip_file:
        return zip_file.read()


def build_webjob_deploy_zip_bytes(file_path: str, cron_expression: str) -> bytes:
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


def deploy_to_webjob(zip_bytes: bytes, job_name: str) -> Optional[Dict[str, Any]]:
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
            "Content-Disposition": f'attachment; filename="{zip_filename}"',
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


def delete_webjob(job_name: str) -> Dict[str, Any]:
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
