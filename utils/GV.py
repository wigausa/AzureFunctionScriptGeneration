#!/usr/bin/env python3
"""
Generador de scripts GV para Azure WebJobs
Versión Python 3.12+ con Azure Functions
"""
import sys
import os
import logging
import requests
from typing import Optional, Dict, Any

# Configurar logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Constantes
TOKEN_USERS = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyIjoiYWRtaW53aWdhIiwiaWQiOjI3MCwiZXhwaXJlZERhdGUiOiIyMDE5LTA3LTIyVDExOjAwOjMyLjA2NzU2ODYtMDU6MDAifQ.BXMx2BKIbkJyD_jRrfhY6Sj_SJbo8gWM8wHghzFvrT0"
BASE_URL = "https://superwicloudapi.azurewebsites.net/api/v1"

def make_request(method: str, url: str, headers: Optional[Dict[str, str]] = None, json_body: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Realiza una petición HTTP y retorna la respuesta JSON."""
    try:
        logger.debug(f"Realizando petición {method} a: {url}")
        response = requests.request(method, url, headers=headers, json=json_body, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Error en petición {method} {url}: {e}")
        return None

def get_data_informe(report_id: str) -> Optional[Dict[str, Any]]:
    """Obtiene los datos del informe desde la API."""
    url = f"{BASE_URL}/reports/{report_id}"
    headers = {'Content-Type': 'application/json', 'token': TOKEN_USERS}
    result = make_request('GET', url, headers=headers)
    
    if result and 'configuration' in result:
        logger.info(f"Configuración del informe {report_id} obtenida exitosamente")
        return result
    
    logger.error(f"No se pudo obtener configuración del informe {report_id}")
    return None

TEMPLATE = '''#!/usr/bin/env python3
"""
Script de generación de reportes GV para Azure WebJobs
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
BASE_URL_V1 = "https://superwicloudapi.azurewebsites.net/api/v1"
BASE_URL = "https://superwicloudapi.azurewebsites.net/api"
AZURE_FUNCTION_URL = os.getenv("AZURE_FUNCTION_GV_URL", "http://localhost:7071/api/GV")

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
    """Obtiene los datos del informe GV desde la API."""
    url = f"{{BASE_URL_V1}}/reports/{report_id}"
    headers = {{'Content-Type': 'application/json', 'token': TOKEN_USERS}}
    result = make_request('GET', url, headers=headers)
    
    if result and 'configuration' in result:
        logger.info("Configuración del informe GV obtenida exitosamente")
        return result
    
    logger.error("No se pudo obtener configuración del informe GV")
    return None

def get_reportes_graficos() -> Optional[Dict[str, Any]]:
    """Obtiene los reportes gráficos desde la API."""
    informe = get_data_informe()
    if not informe:
        return None
    
    try:
        config = informe['configuration']
        # Nota: Endpoint específico para TableReport (sin v1)
        url = f"{{BASE_URL}}/TableReport"
        headers = {{'token': config['token']}}
        body = {{
            "sensorsId": config['sensores'],
            "startDate": config['fechas']['fechaInicial'],
            "endDate": config['fechas']['fechaFinal'],
            "typeSensors": config['typeSensors'],
            "configurationSendingData": informe['configurationSendingData']
        }}
        
        logger.info(f"Obteniendo reportes gráficos para período: {{body['startDate']}} - {{body['endDate']}}")
        result = make_request('POST', url, headers=headers, json_body=body)
        
        if result:
            logger.info("Datos de gráficos obtenidos exitosamente")
            return result
        
        logger.error("No se pudieron obtener datos de gráficos")
        return None
    except KeyError as e:
        logger.error(f"Falta configuración GV: {{e}}")
        return None

def get_stats() -> Optional[Dict[str, Any]]:
    """Obtiene las estadísticas desde la API."""
    informe = get_data_informe()
    if not informe:
        return None
    
    try:
        config = informe['configuration']
        fecha_inicial = config['fechas']['fechaInicial']
        fecha_final = config['fechas']['fechaFinal']
        url = f"{{BASE_URL_V1}}/reports/stats/{{fecha_inicial}}/{{fecha_final}}"
        headers = {{'token': config['token']}}
        
        logger.info(f"Obteniendo estadísticas GV para período: {{fecha_inicial}} - {{fecha_final}}")
        result = make_request('POST', url, headers=headers, json_body=config['sensores'])
        
        if result:
            logger.info("Estadísticas obtenidas exitosamente")
            return result
        
        logger.error("No se pudieron obtener estadísticas")
        return None
    except KeyError as e:
        logger.error(f"Falta configuración GV: {{e}}")
        return None

def send_to_azure_function(stats: Any, versus: Any, datos_usuario: Any) -> Optional[bytes]:
    """Envía los datos a la Azure Function GV y retorna el contenido de la respuesta."""
    payload = {{
        "stats": stats,
        "versus": versus,
        "datosUsuario": datos_usuario
    }}
    
    try:
        logger.info("Enviando datos a Azure Function GV...")
        response = requests.post(AZURE_FUNCTION_URL, json=payload, timeout=60)
        response.raise_for_status()
        logger.info("Datos enviados correctamente a Azure Function GV")
        return response.content
    except requests.RequestException as e:
        logger.error(f"Error al enviar datos a Azure Function GV: {{e}}")
        return None

def generate_report() -> bool:
    """Función principal para generar el reporte GV."""
    logger.info("=== Iniciando generación de reporte GV ===")
    
    try:
        # Obtener todos los datos necesarios
        stats = get_stats()
        versus = get_reportes_graficos()
        datos_usuario = get_data_informe()
        
        # Validar que tengamos al menos algunos datos
        if not any([stats, versus, datos_usuario]):
            logger.error("No se pudo obtener ningún dato para el reporte GV")
            return False
        
        # Mostrar resumen de datos obtenidos
        logger.info(f"Datos obtenidos - Stats: {{'✓' if stats else '✗'}}, "
                   f"Gráficos: {{'✓' if versus else '✗'}}, "
                   f"Usuario: {{'✓' if datos_usuario else '✗'}}")
        
        # Enviar a Azure Function
        pdf_data = send_to_azure_function(stats, versus, datos_usuario)
        
        if pdf_data:
            logger.info("=== Reporte GV generado exitosamente ===")
            return True
        else:
            logger.error("Error al generar el reporte GV")
            return False
            
    except Exception as e:
        logger.error(f"Error inesperado durante la generación del reporte GV: {{e}}")
        return False

if __name__ == "__main__":
    success = generate_report()
    if not success:
        sys.exit(1)
'''

def create_script(report_id: str, output_dir: str = "../GraficaVersus") -> str:
    """Crea un script GV personalizado para el report_id especificado."""
    try:
        # Obtener datos del informe para generar el nombre del archivo
        informe_data = get_data_informe(report_id)
        if not informe_data or 'id' not in informe_data:
            logger.error(f"No se pudo obtener información del informe {report_id}")
            file_name = f"GV_{report_id}.py"
        else:
            file_name = f"GV_{informe_data['id']}.py"
        
        os.makedirs(output_dir, exist_ok=True)
        file_path = os.path.join(output_dir, file_name)
        
        # Generar el contenido del script
        content = TEMPLATE.format(report_id=report_id)
        
        # Escribir el archivo
        with open(file_path, "w", encoding="utf-8") as file:
            file.write(content)
        
        logger.info(f"✅ Script {file_name} generado exitosamente")
        logger.info(f"📁 Ubicación: {os.path.abspath(file_path)}")
        return file_path
        
    except Exception as e:
        logger.error(f"Error al crear el script: {e}")
        raise

if __name__ == "__main__":
    if len(sys.argv) != 2:
        logger.error("Uso: python GV.py <report_id>")
        logger.info("Ejemplo: python GV.py Db05ARa75ljZ9cDS")
        sys.exit(1)
    
    report_id = sys.argv[1]
    logger.info(f"🚀 Iniciando generación de script GV para report_id: {report_id}")
    
    try:
        create_script(report_id)
        logger.info("✅ Proceso completado exitosamente")
    except Exception as e:
        logger.error(f"❌ Error durante la generación: {e}")
        sys.exit(1)
