# ScriptGeneration

Azure Function en Python para generar scripts de reportes, empaquetarlos como WebJob (`.zip` con `settings.job`) y publicarlos en Azure Blob Storage, con despliegue opcional a Azure WebJobs (Kudu).

## Arquitectura

![Arquitectura Correos WigaIO](Arquitectura%20Correos%20WigaIO.drawio.png)

## Funcionalidades

- Genera scripts por tipo de reporte a partir de `idReporte` + `idSchedule`.
- Crea artefactos zip para ejecución programada (`settings.job`).
- Sube artefactos a Blob Storage con metadata de trazabilidad.
- Despliega y elimina WebJobs (opcional, controlado por configuración).
- Expone endpoints HTTP para crear, actualizar y eliminar.

## Tipos de reporte soportados

| idReporte | Tipo | Código |
|---|---|---|
| `HJx-yCRnRI` | Grafica Versus con Colores | `GVC` |
| `rJls0xsi8w` | Grafica Versus sin Colores | `GVS` |
| `H1xqWLg6Uw` | Grafica Versus | `GV` |
| `BkL5kC4ww` | Resumen Empresa | `RS` |

## Endpoints

Base local típica: `http://localhost:7071/api`

- `POST /GraphsVersusCreate`
- `PUT /GraphsVersusUpdate`
- `DELETE /GraphsVersusDelete`

Los tres endpoints reciben JSON.

### Body esperado

```json
{
  "idReporte": "HJx-yCRnRI",
  "idSchedule": "12345",
  "cron": "0 */15 * * * *"
}
```

Notas:
- `cron` debe tener **6 campos** (formato WebJobs).
- En `DELETE` se usan `idReporte` e `idSchedule` (`cron` no es requerido).

## Variables de entorno

Definir en `local.settings.json` (local) y en App Settings (Azure):

| Variable | Requerida | Descripción |
|---|---|---|
| `FUNCTIONS_WORKER_RUNTIME` | Sí | Debe ser `python`. |
| `AzureWebJobsStorage` | Sí* | Storage principal. También puede usarse para Blob de scripts. |
| `SCRIPT_BLOB_CONNECTION_STRING` | No | Connection string específica para Blob de scripts (si no existe, usa `AzureWebJobsStorage`). |
| `SCRIPT_BLOB_CONTAINER` | No | Contenedor destino. Default: `generated-scripts`. |
| `SCRIPT_BLOB_SAS_HOURS` | No | Horas de vigencia del SAS generado. Default: `24`. |
| `WEBJOB_DEPLOY_ENABLED` | No | `true/false` para habilitar despliegue/eliminación WebJob. |
| `WEBJOB_FLOW_MODE` | No | `blob_first_with_status` (default) o `deploy_first`. |
| `WEBJOB_APP_NAME` | Condicional | Nombre del App Service para Kudu (requerida si `WEBJOB_DEPLOY_ENABLED=true`). |
| `WEBJOB_SCM_USER` | Condicional | Usuario SCM/Kudu (requerida si `WEBJOB_DEPLOY_ENABLED=true`). |
| `WEBJOB_SCM_PASSWORD` | Condicional | Password SCM/Kudu (requerida si `WEBJOB_DEPLOY_ENABLED=true`). |

## Flujo de publicación

`WEBJOB_FLOW_MODE` controla el orden:

- `blob_first_with_status` (recomendado):
  1. Sube zip a Blob.
  2. Intenta desplegar WebJob.
  3. Actualiza metadata del blob con `deploy_status=success|failed`.

- `deploy_first`:
  1. Despliega WebJob.
  2. Sube zip a Blob.
  3. Guarda metadata de despliegue exitoso.

## Desarrollo local

### 1) Instalar dependencias

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Configurar settings locales

Crear/editar `local.settings.json` con tus valores (no subir secretos reales al repositorio).

### 3) Ejecutar

```bash
func start
```

## Ejemplos de uso

Crear:

```bash
curl -X POST "http://localhost:7071/api/GraphsVersusCreate" \
  -H "Content-Type: application/json" \
  -d '{
    "idReporte": "HJx-yCRnRI",
    "idSchedule": "12345",
    "cron": "0 */15 * * * *"
  }'
```

Actualizar:

```bash
curl -X PUT "http://localhost:7071/api/GraphsVersusUpdate" \
  -H "Content-Type: application/json" \
  -d '{
    "idReporte": "HJx-yCRnRI",
    "idSchedule": "12345",
    "cron": "0 */30 * * * *"
  }'
```

Eliminar:

```bash
curl -X DELETE "http://localhost:7071/api/GraphsVersusDelete" \
  -H "Content-Type: application/json" \
  -d '{
    "idReporte": "HJx-yCRnRI",
    "idSchedule": "12345"
  }'
```

## Estructura del proyecto

```text
.
├── function_app.py
├── requirements.txt
├── host.json
├── Arquitectura Correos WigaIO.drawio.png
└── utils
    ├── helpers
    │   ├── artifact_utils.py
    │   ├── blob_utils.py
    │   ├── http_utils.py
    │   ├── report_api.py
    │   ├── script_builder.py
    │   ├── template_loader.py
    │   └── webjob_utils.py
    └── templates
        ├── GV.py
        ├── GVC.py
        ├── GVS.py
        └── RS.py
```

## Seguridad

- No expongas `local.settings.json` con credenciales reales.
- Usa Key Vault/App Settings para secretos en ambientes cloud.
- Rota credenciales si alguna se filtró en historial o commits.
