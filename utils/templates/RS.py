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


def create_script(report_id: str, output_dir: str = ".") -> str:
    return build_script_from_template(
        report_id=report_id,
        output_dir=output_dir,
        prefix="RS",
        template_name="RS_template.py",
        logger=logger,
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        logger.error("Uso: python RS.py <report_id>")
        sys.exit(1)

    report_id = sys.argv[1]
    create_script(report_id)
