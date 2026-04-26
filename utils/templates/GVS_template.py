#!/usr/bin/env python3
"""
Script de generación de reportes GVS (mensuales) para Azure WebJobs
Versión Python 3.12+ - Generado automáticamente
Report ID: {report_id}
"""
import sys
import os
import subprocess
import logging

# Función para instalar dependencias automáticamente
def install_dependencies():
    """Instala las dependencias desde requirements.txt si no están disponibles."""
    requirements_path = "/home/site/wwwroot/requirements.txt"
    
    print("Verificando dependencias...")
    
    # Verificar si las dependencias críticas están instaladas
    missing_dependencies = False
    
    try:
        import requests
        print("✓ requests está disponible")
    except ImportError:
        missing_dependencies = True
        print("✗ requests no está disponible")
    
    try:
        import dotenv
        print("✓ python-dotenv está disponible")
    except ImportError:
        missing_dependencies = True
        print("✗ python-dotenv no está disponible")
    
    # Si faltan dependencias, instalar desde requirements.txt
    if missing_dependencies:
        if os.path.exists(requirements_path):
            print(f"Instalando dependencias desde {{requirements_path}}...")
            try:
                subprocess.check_call([
                    sys.executable, "-m", "pip", "install", "-r", requirements_path, 
                    "--user", "--no-warn-script-location"
                ])
                print("✓ Todas las dependencias se instalaron correctamente desde requirements.txt")
            except subprocess.CalledProcessError as e:
                print(f"✗ Error al instalar dependencias desde requirements.txt: {{e}}")
                sys.exit(1)
        else:
            print(f"✗ No se encontró requirements.txt en {{requirements_path}}")
            print("Instalando dependencias individuales...")
            required_packages = ['requests==2.32.4', 'python-dotenv==1.1.1']
            try:
                for package in required_packages:
                    subprocess.check_call([
                        sys.executable, "-m", "pip", "install", package, 
                        "--user", "--no-warn-script-location"
                    ])
                print("✓ Dependencias instaladas individualmente")
            except subprocess.CalledProcessError as e:
                print(f"✗ Error al instalar dependencias: {{e}}")
                sys.exit(1)
    else:
        print("✓ Todas las dependencias están disponibles")

# Instalar dependencias antes de continuar
install_dependencies()

# Ahora importar las dependencias ya instaladas
# Forzar recarga de módulos si fueron instalados recientemente
try:
    import requests
    import json
    from typing import Optional, Dict, Any
    from dotenv import load_dotenv
except ImportError as e:
    print(f"Error al importar después de instalación: {{e}}")
    print("Reiniciando intérprete para reconocer nuevos módulos...")
    import importlib
    import sys
    
    # Limpiar cache de módulos
    if 'requests' in sys.modules:
        del sys.modules['requests']
    if 'dotenv' in sys.modules:
        del sys.modules['dotenv']
    
    # Actualizar el path de Python
    import site
    site.main()
    
    # Intentar importar nuevamente
    try:
        import requests
        from dotenv import load_dotenv
        import json
        from typing import Optional, Dict, Any
        print("✓ Importaciones exitosas después de recargar módulos")
    except ImportError as e2:
        print(f"✗ Error crítico: No se pudieron importar las dependencias: {{e2}}")
        sys.exit(1)

# Cargar variables de entorno
load_dotenv()

# Configurar logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Constantes
TOKEN_USERS = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyIjoiYWRtaW53aWdhIiwiaWQiOjI3MCwiZXhwaXJlZERhdGUiOiIyMDE5LTA3LTIyVDExOjAwOjMyLjA2NzU2ODYtMDU6MDAifQ.BXMx2BKIbkJyD_jRrfhY6Sj_SJbo8gWM8wHghzFvrT0"
BASE_URL = "https://superwicloudapi.azurewebsites.net/api/v1"
AZURE_FUNCTION_URL = os.getenv("AZURE_FUNCTION_GVS_URL", "http://localhost:7071/api/GVS")

def make_request(method: str, url: str, headers: Optional[Dict[str, str]] = None, json_body: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Realiza una petición HTTP y retorna la respuesta JSON."""
    try:
        logger.debug(f"Realizando petición {{method}} a: {{url}}")
        response = requests.request(method, url, headers=headers, json=json_body, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Error en petición {{method}} {{url}}: {{e}}")
        return None
    
def get_data_informe() -> Optional[Dict[str, Any]]:
    """Obtiene los datos del informe GVS desde la API."""
    url = f"{{BASE_URL}}/reports/{report_id}"
    headers = {{'Content-Type': 'application/json', 'token': TOKEN_USERS}}
    result = make_request('GET', url, headers=headers)
    
    if result and 'configuration' in result:
        logger.info("Configuración del informe GVS obtenida exitosamente")
        return result
    
    logger.error("No se pudo obtener configuración del informe GVS")
    return None

def get_reportes_graficos() -> Optional[Dict[str, Any]]:
    """Obtiene los reportes gráficos mensuales desde la API."""
    informe = get_data_informe()
    if not informe:
        return None
    
    try:
        config = informe['configuration']
        # Nota: Endpoint específico para reportes mensuales
        url = f"{{BASE_URL}}/reports/multipleTableMensualReport"
        headers = {{'token': config['token']}}
        body = {{
            "sensorsId": config['sensores'],
            "startDate": config['fechas']['fechaInicial'],
            "endDate": config['fechas']['fechaFinal'],
            "typeSensors": config['typeSensors'],
            "configurationSendingData": informe['configurationSendingData']
        }}
        
        logger.info(f"Obteniendo reportes mensuales para período: {{body['startDate']}} - {{body['endDate']}}")
        return make_request('POST', url, headers=headers, json_body=body)
    except KeyError as e:
        logger.error(f"Falta configuración GVS: {{e}}")
        return None

def get_stats() -> Optional[Dict[str, Any]]:
    """Obtiene las estadísticas GVS desde la API."""
    informe = get_data_informe()
    if not informe:
        return None
    
    try:
        config = informe['configuration']
        fecha_inicial = config['fechas']['fechaInicial']
        fecha_final = config['fechas']['fechaFinal']
        url = f"{{BASE_URL}}/reports/stats/{{fecha_inicial}}/{{fecha_final}}"
        headers = {{'token': config['token']}}
        
        logger.info(f"Obteniendo estadísticas GVS para período: {{fecha_inicial}} - {{fecha_final}}")
        return make_request('POST', url, headers=headers, json_body=config['sensores'])
    except KeyError as e:
        logger.error(f"Falta configuración GVS: {{e}}")
        return None

def send_to_azure_function(stats: Any, versus: Any, datos_usuario: Any) -> Optional[bytes]:
    """Envía los datos a la Azure Function GVS y retorna el contenido de la respuesta."""
    payload = {{
        "stats": stats,
        "versus": versus,
        "datosUsuario": datos_usuario
    }}
    
    try:
        logger.info("Enviando datos a Azure Function GVS...")
        response = requests.post(AZURE_FUNCTION_URL, json=payload, timeout=60)
        response.raise_for_status()
        logger.info("Datos enviados correctamente a Azure Function GVS")
        return response.content
    except requests.RequestException as e:
        logger.error(f"Error al enviar datos a Azure Function GVS: {{e}}")
        return None

def generate_report() -> bool:
    """Función principal para generar el reporte GVS."""
    logger.info("=== Iniciando generación de reporte GVS (mensual) ===")
    
    try:
        # Obtener todos los datos necesarios
        stats = get_stats()
        versus = get_reportes_graficos()
        datos_usuario = get_data_informe()
        
        # Validar que tengamos al menos algunos datos
        if not any([stats, versus, datos_usuario]):
            logger.error("No se pudo obtener ningún dato para el reporte GVS")
            return False
        
        # Mostrar resumen de datos obtenidos
        logger.info(f"Datos obtenidos - Stats: {{'✓' if stats else '✗'}}, "
                   f"Gráficos mensuales: {{'✓' if versus else '✗'}}, "
                   f"Usuario: {{'✓' if datos_usuario else '✗'}}")
        
        # Enviar a Azure Function
        pdf_data = send_to_azure_function(stats, versus, datos_usuario)
        
        if pdf_data:
            logger.info("=== Reporte GVS generado exitosamente ===")
            return True
        else:
            logger.error("Error al generar el reporte GVS")
            return False
            
    except Exception as e:
        logger.error(f"Error inesperado durante la generación del reporte GVS: {{e}}")
        return False

if __name__ == "__main__":
    success = generate_report()
    if not success:
        sys.exit(1)
