import logging
import os
from typing import Any, Dict, Optional

from utils.helpers.report_api import get_data_informe
from utils.helpers.template_loader import load_template


def build_script_from_template(
    report_id: str,
    output_dir: str,
    prefix: str,
    template_name: str,
    logger: logging.Logger,
    template_vars: Optional[Dict[str, Any]] = None,
) -> str:
    informe_data = get_data_informe(report_id, logger=logger)
    if not informe_data or "id" not in informe_data:
        file_name = f"{prefix}_{report_id}.py"
    else:
        file_name = f"{prefix}_{informe_data['id']}.py"

    os.makedirs(output_dir, exist_ok=True)
    file_path = os.path.join(output_dir, file_name)

    template = load_template(template_name)
    format_vars: Dict[str, Any] = {"report_id": report_id}
    if template_vars:
        format_vars.update(template_vars)
    content = template.format(**format_vars)

    with open(file_path, "w", encoding="utf-8") as file:
        file.write(content)

    logger.info("Script %s generado exitosamente", file_name)
    logger.info("Ubicacion: %s", os.path.abspath(file_path))
    return file_path
