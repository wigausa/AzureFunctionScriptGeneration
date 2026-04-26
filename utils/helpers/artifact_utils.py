import json
import os
import tempfile
from typing import Any, Callable, Dict


def get_artifact_names(
    script_generators: Dict[str, Dict[str, Any]],
    id_reporte: str,
    id_schedule: str,
) -> Dict[str, Any]:
    mapping = script_generators.get(id_reporte)
    if not mapping:
        raise ValueError(
            json.dumps(
                {
                    "ok": False,
                    "message": f"idReporte no soportado: {id_reporte}",
                    "supported": list(script_generators.keys()),
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
