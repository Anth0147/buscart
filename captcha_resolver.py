"""
<<<<<<< HEAD
Módulo de Resolución de Captcha (captcha_resolver.py)
=====================================================
Motor de resolución de captchas numéricos:
1. DDDDOCR — OCR local offline (Ultra rápido, ~0.05s)
2. Tesseract OCR
3. 2Captcha / Anti-Captcha (Servicios externos)
4. Manual (Entrada por consola)
"""

import os
import sys
import time
import json
import base64
import logging
import tempfile
import subprocess
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger("CaptchaResolver")


class CaptchaResolver:
    """Resolvedor de captchas con múltiples backends."""

    def __init__(self, method: str = "ddddocr", api_key: str = None):
        """
        Args:
            method: 'ddddocr' (por defecto, local ultra rápido), 'tesseract', '2captcha', 'anticaptcha', 'manual'
            api_key: API key para servicios externos
        """
        self.method = method.lower()
        self.api_key = api_key
        self._ocr = None

        if self.method == "ddddocr":
            self._init_ddddocr()
        elif self.method == "tesseract":
            self._check_tesseract()

    def _init_ddddocr(self):
        """Inicializa la instancia de ddddocr para resolución local instantánea."""
        try:
            import ddddocr
            self._ocr = ddddocr.DdddOcr(show_ad=False)
            logger.info("✅ Resolutor local DDDDOCR inicializado (0.05s / offline)")
        except Exception as e:
            logger.warning(f"Error inicializando ddddocr: {e}")
            self.method = "manual"

    # ========== TESSERACT ==========
    def _check_tesseract(self):
        """Verifica si Tesseract OCR está instalado en el sistema."""
        try:
            result = subprocess.run(
                ["tesseract", "--version"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                logger.info("✅ Tesseract OCR disponible")
            else:
                self.method = "manual"
        except Exception:
            self.method = "manual"

    def _resolve_tesseract(self, captcha_data: str) -> str:
        """Resolución con Tesseract OCR."""
        temp_path = None
        try:
=======
Módulo de Resolución de Captcha
=================================
Soporta múltiples métodos:
1. VLM/AI (z-ai vision) — AUTOMÁTICO, sin intervención humana
2. Manual (input por consola)
3. OCR con Tesseract
4. Servicios API (2Captcha, Anti-Captcha)
"""

import logging
import base64
import json
import subprocess
import tempfile
import os
import time
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger(__name__)

# Prompt optimizado para resolver captchas numéricos/digitales
CAPTCHA_PROMPT = (
    "This is a CAPTCHA image from a login page. "
    "Read EXACTLY the text/characters shown in the captcha image. "
    "Output ONLY the captcha text, nothing else. "
    "No quotes, no spaces, no explanation. "
    "If there are letters and numbers, transcribe them exactly as shown, including case."
)


class CaptchaResolver:
    """Resolvedor de captcha con múltiples backends."""

    def __init__(self, method: str = "vlm", api_key: str = None):
        """
        Args:
            method: 'vlm', 'manual', 'tesseract', '2captcha', 'anticaptcha'
            api_key: API key para servicios de captcha
        """
        self.method = method.lower()
        self.api_key = api_key

        if self.method == "tesseract":
            self._check_tesseract()
        elif self.method == "vlm":
            self._check_vlm()
        elif self.method == "ddddocr":
            self._check_ddddocr()

    # ========== VLM (AI Vision) ==========
    def _check_vlm(self):
        """Verifica si z-ai CLI está disponible. Si no, usa ddddocr como fallback."""
        try:
            result = subprocess.run(
                ["z-ai", "vision", "--help"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                logger.info("✅ z-ai vision disponible para resolución automática de captcha")
                return
        except Exception:
            pass

        # Fallback a ddddocr si está disponible
        try:
            import ddddocr
            logger.info("🔄 z-ai CLI no disponible. Usando ddddocr como resolvedor automático")
            self.method = "ddddocr"
        except ImportError:
            logger.warning("z-ai CLI ni ddddocr disponibles, usando manual")
            self.method = "manual"

    # ========== DDDDOCR ==========
    def _check_ddddocr(self):
        """Verifica si la librería ddddocr está disponible."""
        try:
            import ddddocr
            logger.info("✅ ddddocr disponible para resolución automática local de captcha")
        except ImportError:
            logger.warning("Librería ddddocr no está instalada, usando manual")
            self.method = "manual"

    def _resolve_vlm(self, captcha_data: str) -> str:
        """
        Resolución automática usando z-ai vision (VLM).
        Soporta:
        - Base64 puro
        - data:image/...;base64,...
        - URL de imagen
        """
        temp_path = None

        try:
            # 1. Convertir captcha_data a archivo temporal
>>>>>>> 896283b8ed693c96dfe6c769ed049a4dc051282d
            if captcha_data.startswith("data:image"):
                b64_part = captcha_data.split(",", 1)[1]
                img_bytes = base64.b64decode(b64_part)
            elif len(captcha_data) > 100:
<<<<<<< HEAD
                img_bytes = base64.b64decode(captcha_data)
            else:
                import requests
                resp = requests.get(captcha_data, timeout=10)
                img_bytes = resp.content

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                f.write(img_bytes)
                temp_path = f.name

            result = subprocess.run(
                ["tesseract", temp_path, "stdout",
                 "-c", "tessedit_char_whitelist=0123456789",
                 "--psm", "8"],
                capture_output=True, text=True, timeout=30
            )

            text = result.stdout.strip().replace(" ", "")
            digits = "".join([c for c in text if c.isdigit()])
            return digits[:4] if len(digits) >= 4 else digits

        except Exception as e:
            logger.error(f"Error con Tesseract: {e}")
            return self._resolve_manual(captcha_data)
=======
                # Base64 puro
                img_bytes = base64.b64decode(captcha_data)
            else:
                # Es URL, pasar directo
                img_bytes = None

            if img_bytes:
                # Guardar archivo temporal
                with tempfile.NamedTemporaryFile(
                    suffix=".png", delete=False, prefix="captcha_"
                ) as f:
                    f.write(img_bytes)
                    temp_path = f.name
                image_arg = temp_path
            else:
                image_arg = captcha_data

            # 2. Ejecutar z-ai vision
            logger.info("🧠 Resolviendo captcha con AI Vision...")
            result = subprocess.run(
                [
                    "z-ai", "vision",
                    "-p", CAPTCHA_PROMPT,
                    "-i", image_arg
                ],
                capture_output=True, text=True, timeout=60
            )

            # 3. Parsear respuesta JSON
            # z-ai vision imprime logs en stderr y JSON en stdout
            output = result.stdout.strip()
            if not output:
                logger.error(f"VLM no retornó respuesta (stderr: {result.stderr[:200]})")
                return self._resolve_manual(captcha_data)

            # Extraer JSON de la salida (puede tener texto extra)
            # Buscar el primer { y el último }
            json_start = output.find('{')
            json_end = output.rfind('}') + 1
            if json_start == -1 or json_end == 0:
                logger.error(f"No se encontró JSON en respuesta: {output[:200]}")
                return self._resolve_manual(captcha_data)

            json_str = output[json_start:json_end]
            resp = json.loads(json_str)
            content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")

            # Limpiar: solo dígitos y letras, sin espacios ni comillas
            captcha_text = content.strip().strip('"').strip("'").replace(" ", "")

            if captcha_text:
                logger.info(f"✅ VLM captcha resuelto: [{captcha_text}]")
                # Guardar para debugging
                self._last_vlm_raw = content
                return captcha_text
            else:
                logger.warning("VLM retornó texto vacío")
                return self._resolve_manual(captcha_data)

        except json.JSONDecodeError as e:
            logger.error(f"Error parseando respuesta VLM: {e}")
            logger.error(f"Raw output: {output[:200]}")
            return self._resolve_manual(captcha_data)

        except subprocess.TimeoutExpired:
            logger.error("Timeout resolviendo captcha con VLM")
            return self._resolve_manual(captcha_data)

        except Exception as e:
            logger.error(f"Error con VLM: {e}")
            return self._resolve_manual(captcha_data)

>>>>>>> 896283b8ed693c96dfe6c769ed049a4dc051282d
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass

<<<<<<< HEAD
=======
    # ========== TESSERACT ==========
    def _check_tesseract(self):
        """Verifica si Tesseract OCR está instalado."""
        try:
            result = subprocess.run(
                ["tesseract", "--version"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                version = result.stdout.split("\n")[0]
                logger.info(f"Tesseract disponible: {version}")
            else:
                logger.warning("Tesseract no funciona correctamente, usando manual")
                self.method = "manual"
        except FileNotFoundError:
            logger.warning("Tesseract no instalado. Instalar con: apt install tesseract-ocr")
            self.method = "manual"
        except Exception as e:
            logger.warning(f"Error verificando Tesseract: {e}")
            self.method = "manual"

    def _resolve_tesseract(self, captcha_data: str) -> str:
        """Resolución con Tesseract OCR."""
        try:
            # Decodificar imagen
            if captcha_data.startswith("data:image"):
                b64_part = captcha_data.split(",", 1)[1]
                img_bytes = base64.b64decode(b64_part)
            elif len(captcha_data) > 100:
                img_bytes = base64.b64decode(captcha_data)
            else:
                # Es URL, descargar
                import requests
                resp = requests.get(captcha_data, timeout=10)
                img_bytes = resp.content

            # Guardar archivo temporal
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                f.write(img_bytes)
                temp_path = f.name

            # Ejecutar Tesseract
            result = subprocess.run(
                ["tesseract", temp_path, "stdout",
                 "-c", "tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
                 "--psm", "8"],
                capture_output=True, text=True, timeout=30
            )

            os.unlink(temp_path)

            text = result.stdout.strip().replace(" ", "")
            logger.info(f"Tesseract result: {text}")
            return text

        except Exception as e:
            logger.error(f"Error con Tesseract: {e}")
            return self._resolve_manual(captcha_data)

>>>>>>> 896283b8ed693c96dfe6c769ed049a4dc051282d
    # ========== MANUAL ==========
    def _resolve_manual(self, captcha_data: str) -> str:
        """Resolución manual: muestra la imagen y pide input."""
        if captcha_data.startswith("data:") or len(captcha_data) > 100:
            img_bytes = base64.b64decode(captcha_data) if not captcha_data.startswith("data:") \
                else base64.b64decode(captcha_data.split(",", 1)[1])

            temp_path = Path(tempfile.gettempdir()) / "captcha_current.png"
            try:
                with open(temp_path, "wb") as f:
                    f.write(img_bytes)
                logger.info(f"Captcha guardado en: {temp_path}")
<<<<<<< HEAD
=======
                try:
                    if os.name == 'posix':
                        subprocess.Popen(['xdg-open', str(temp_path)],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception:
                    pass
>>>>>>> 896283b8ed693c96dfe6c769ed049a4dc051282d
            except Exception as e:
                logger.error(f"Error guardando captcha: {e}")

        print("\n" + "=" * 50)
<<<<<<< HEAD
        print("🔢 CAPTCHA - Ingrese el valor visualizado")
=======
        print("🤖 CAPTCHA - Ingrese el valor visualizado")
>>>>>>> 896283b8ed693c96dfe6c769ed049a4dc051282d
        print("=" * 50)
        text = input("Captcha: ").strip()
        print("=" * 50 + "\n")
        return text

    # ========== 2CAPTCHA ==========
    def _resolve_2captcha(self, captcha_data: str) -> str:
        """Resolución con 2Captcha API."""
        if not self.api_key:
<<<<<<< HEAD
=======
            logger.error("API key de 2Captcha no configurada")
>>>>>>> 896283b8ed693c96dfe6c769ed049a4dc051282d
            return self._resolve_manual(captcha_data)

        try:
            import requests

            if captcha_data.startswith("data:image"):
                b64_part = captcha_data.split(",", 1)[1]
                img_bytes = base64.b64decode(b64_part)
            else:
                img_bytes = base64.b64decode(captcha_data)

            files = {"file": ("captcha.png", img_bytes, "image/png")}
            data = {"key": self.api_key, "method": "post"}
            resp = requests.post("https://2captcha.com/in.php", files=files, data=data, timeout=30)
            captcha_id = resp.text.split("|")[-1].strip()

            if not captcha_id.isdigit():
<<<<<<< HEAD
                return self._resolve_manual(captcha_data)

            for _ in range(30):
                time.sleep(3)
=======
                logger.error(f"Error 2Captcha: {resp.text}")
                return self._resolve_manual(captcha_data)

            for _ in range(30):
                time.sleep(5)
>>>>>>> 896283b8ed693c96dfe6c769ed049a4dc051282d
                resp = requests.get(
                    f"https://2captcha.com/res.php?key={self.api_key}&action=get&id={captcha_id}",
                    timeout=15
                )
                text = resp.text.strip()
                if text.startswith("OK|"):
                    result = text[3:]
<<<<<<< HEAD
                    digits = "".join([c for c in result if c.isdigit()])
                    return digits[:4] if len(digits) >= 4 else digits
                elif text == "CAPCHA_NOT_READY":
                    continue
                else:
=======
                    logger.info(f"2Captcha resuelto: {result}")
                    return result
                elif text == "CAPCHA_NOT_READY":
                    continue
                else:
                    logger.error(f"Error 2Captcha: {text}")
>>>>>>> 896283b8ed693c96dfe6c769ed049a4dc051282d
                    break

            return self._resolve_manual(captcha_data)

        except Exception as e:
            logger.error(f"Error 2Captcha: {e}")
            return self._resolve_manual(captcha_data)

    # ========== ANTI-CAPTCHA ==========
    def _resolve_anticaptcha(self, captcha_data: str) -> str:
        """Resolución con Anti-Captcha API."""
        if not self.api_key:
<<<<<<< HEAD
=======
            logger.error("API key de Anti-Captcha no configurada")
>>>>>>> 896283b8ed693c96dfe6c769ed049a4dc051282d
            return self._resolve_manual(captcha_data)

        try:
            import requests

            img_bytes = base64.b64decode(
                captcha_data.split(",", 1)[1] if captcha_data.startswith("data:")
                else captcha_data
            )

            create_resp = requests.post(
                "https://api.anti-captcha.com/createTask",
                json={
                    "clientKey": self.api_key,
                    "task": {
                        "type": "ImageToTextTask",
                        "body": base64.b64encode(img_bytes).decode(),
                        "case": False,
<<<<<<< HEAD
                        "charWhitelist": "0123456789"
=======
                        "charWhitelist": "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
>>>>>>> 896283b8ed693c96dfe6c769ed049a4dc051282d
                    }
                },
                timeout=15
            )

            task_id = create_resp.json().get("taskId")
            if not task_id:
<<<<<<< HEAD
=======
                logger.error(f"Error Anti-Captcha: {create_resp.text}")
>>>>>>> 896283b8ed693c96dfe6c769ed049a4dc051282d
                return self._resolve_manual(captcha_data)

            for _ in range(30):
                time.sleep(3)
                result_resp = requests.post(
                    "https://api.anti-captcha.com/getTaskResult",
                    json={"clientKey": self.api_key, "taskId": task_id},
                    timeout=15
                )
                data = result_resp.json()
                if data.get("status") == "ready":
                    text = data.get("solution", {}).get("text", "")
<<<<<<< HEAD
                    digits = "".join([c for c in text if c.isdigit()])
                    return digits[:4] if len(digits) >= 4 else digits
=======
                    logger.info(f"Anti-Captcha resuelto: {text}")
                    return text
>>>>>>> 896283b8ed693c96dfe6c769ed049a4dc051282d

            return self._resolve_manual(captcha_data)

        except Exception as e:
            logger.error(f"Error Anti-Captcha: {e}")
            return self._resolve_manual(captcha_data)

    # ========== DDDDOCR ==========
    def _resolve_ddddocr(self, captcha_data: str) -> str:
<<<<<<< HEAD
        """Resolución automática local instantánea (4 dígitos 0-9)."""
        try:
=======
        """Resolución automática usando la librería local ddddocr."""
        try:
            # 1. Convertir captcha_data a bytes
>>>>>>> 896283b8ed693c96dfe6c769ed049a4dc051282d
            if captcha_data.startswith("data:image"):
                b64_part = captcha_data.split(",", 1)[1]
                img_bytes = base64.b64decode(b64_part)
            elif len(captcha_data) > 100:
<<<<<<< HEAD
                img_bytes = base64.b64decode(captcha_data)
            else:
=======
                # Base64 puro
                img_bytes = base64.b64decode(captcha_data)
            else:
                # Es URL, descargar
>>>>>>> 896283b8ed693c96dfe6c769ed049a4dc051282d
                import requests
                resp = requests.get(captcha_data, timeout=10)
                img_bytes = resp.content

<<<<<<< HEAD
            if not self._ocr:
                import ddddocr
                self._ocr = ddddocr.DdddOcr(show_ad=False)

            raw_text = self._ocr.classification(img_bytes) or ""
            raw_text = raw_text.strip().replace(" ", "")

            # Mapeo de caracteres comunes
            mapped = ""
            for char in raw_text:
                c = char.upper()
                if c in ('O', 'D', 'Q'):
                    mapped += '0'
                elif c in ('I', 'L', 'J', '|', '!'):
                    mapped += '1'
                elif c == 'Z':
                    mapped += '2'
                elif c == 'S':
                    mapped += '5'
                elif c in ('B', '&'):
                    mapped += '8'
                elif c == 'G':
                    mapped += '6'
                elif c.isdigit():
                    mapped += c

            digits = "".join([c for c in mapped if c.isdigit()])
            if len(digits) >= 4:
                return digits[:4]
            elif digits:
                return digits

            return raw_text or "0000"
        except Exception as e:
            logger.error(f"Error resolviendo con ddddocr: {e}")
            return "0000"
=======
            # 2. Ejecutar ddddocr
            from ddddocr import DdddOcr
            ocr = DdddOcr(show_ad=False)
            captcha_text = ocr.classification(img_bytes)

            captcha_text = captcha_text.strip().replace(" ", "")
            if captcha_text:
                logger.info(f"✅ ddddocr captcha resuelto: [{captcha_text}]")
                return captcha_text
            else:
                logger.warning("ddddocr retornó texto vacío")
                return self._resolve_manual(captcha_data)
        except Exception as e:
            logger.error(f"Error resolviendo con ddddocr: {e}")
            return self._resolve_manual(captcha_data)
>>>>>>> 896283b8ed693c96dfe6c769ed049a4dc051282d

    # ========== DISPATCHER PRINCIPAL ==========
    def resolve(self, captcha_data: str) -> str:
        """
        Resuelve el captcha usando el método configurado.
<<<<<<< HEAD
        """
        if self.method == "ddddocr":
=======

        Args:
            captcha_data: Base64 de la imagen, data URI, o URL

        Returns:
            Texto del captcha resuelto
        """
        if self.method == "vlm":
            return self._resolve_vlm(captcha_data)
        elif self.method == "ddddocr":
>>>>>>> 896283b8ed693c96dfe6c769ed049a4dc051282d
            return self._resolve_ddddocr(captcha_data)
        elif self.method == "manual":
            return self._resolve_manual(captcha_data)
        elif self.method == "tesseract":
            return self._resolve_tesseract(captcha_data)
        elif self.method == "2captcha":
            return self._resolve_2captcha(captcha_data)
        elif self.method == "anticaptcha":
            return self._resolve_anticaptcha(captcha_data)
        else:
<<<<<<< HEAD
            return self._resolve_ddddocr(captcha_data)
=======
            logger.error(f"Método de captcha no soportado: {self.method}")
            return self._resolve_manual(captcha_data)
>>>>>>> 896283b8ed693c96dfe6c769ed049a4dc051282d
