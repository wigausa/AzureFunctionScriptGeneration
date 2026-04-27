import json
from typing import Any, Dict


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

    code = mapping["code"]
    base_name = f"{code}_{id_schedule}"
    zip_name = f"{base_name}.zip"
    webjob_name = base_name.replace("_", "")

    return {
        "mapping": mapping,
        "zipName": zip_name,
        "webjobName": webjob_name,
    }
