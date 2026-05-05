#!/usr/bin/env python3
"""Generador de scripts RS para Azure WebJobs."""

import logging
import sys

from utils.helpers.script_builder import build_script_from_template

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def create_script(report_id: str, output_dir: str = "../GraficaVersus") -> str:
    return build_script_from_template(
        report_id=report_id,
        output_dir=output_dir,
        prefix="RS",
        template_name="RS_template.py",
        logger=logger,
        template_vars={
            "report_code": "RS",
            "function_env_var": "AZURE_FUNCTION_RS_URL",
            "function_default_url": "http://localhost:7071/api/RS",
            "reportes_endpoint_path": "v1/reports/weeklyReport",
            "reportes_label": "reporte semanal",
        },
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        logger.error("Uso: python RS.py <report_id>")
        logger.info("Ejemplo: python RS.py FrWIIiRcXalzNUB7")
        sys.exit(1)

    report_id = sys.argv[1]
    logger.info("Iniciando generacion de script RS para report_id: %s", report_id)

    try:
        create_script(report_id)
        logger.info("Proceso completado exitosamente")
    except Exception as exc:
        logger.error("Error durante la generacion: %s", exc)
        sys.exit(1)
