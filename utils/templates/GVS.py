#!/usr/bin/env python3
"""Generador de scripts GVS para Azure WebJobs."""

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
        prefix="GVS",
        template_name="GVS_template.py",
        logger=logger,
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        logger.error("Uso: python GVS.py <report_id>")
        logger.info("Ejemplo: python GVS.py FrWIIiRcXalzNUB7")
        sys.exit(1)

    report_id = sys.argv[1]
    logger.info("Iniciando generacion de script GVS para report_id: %s", report_id)

    try:
        create_script(report_id)
        logger.info("Proceso completado exitosamente")
    except Exception as exc:
        logger.error("Error durante la generacion: %s", exc)
        sys.exit(1)
