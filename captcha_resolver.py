"""
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
            if captcha_data.startswith("data:image"):
                b64_part = captcha_data.split(",", 1)[1]
                img_bytes = base64.b64decode(b64_part)
            elif len(captcha_data) > 100:
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
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass

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
            except Exception as e:
                logger.error(f"Error guardando captcha: {e}")

        print("\n" + "=" * 50)
        print("🔢 CAPTCHA - Ingrese el valor visualizado")
        print("=" * 50)
        text = input("Captcha: ").strip()
        print("=" * 50 + "\n")
        return text

    # ========== 2CAPTCHA ==========
    def _resolve_2captcha(self, captcha_data: str) -> str:
        """Resolución con 2Captcha API."""
        if not self.api_key:
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
                return self._resolve_manual(captcha_data)

            for _ in range(30):
                time.sleep(3)
                resp = requests.get(
                    f"https://2captcha.com/res.php?key={self.api_key}&action=get&id={captcha_id}",
                    timeout=15
                )
                text = resp.text.strip()
                if text.startswith("OK|"):
                    result = text[3:]
                    digits = "".join([c for c in result if c.isdigit()])
                    return digits[:4] if len(digits) >= 4 else digits
                elif text == "CAPCHA_NOT_READY":
                    continue
                else:
                    break

            return self._resolve_manual(captcha_data)

        except Exception as e:
            logger.error(f"Error 2Captcha: {e}")
            return self._resolve_manual(captcha_data)

    # ========== ANTI-CAPTCHA ==========
    def _resolve_anticaptcha(self, captcha_data: str) -> str:
        """Resolución con Anti-Captcha API."""
        if not self.api_key:
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
                        "charWhitelist": "0123456789"
                    }
                },
                timeout=15
            )

            task_id = create_resp.json().get("taskId")
            if not task_id:
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
                    digits = "".join([c for c in text if c.isdigit()])
                    return digits[:4] if len(digits) >= 4 else digits

            return self._resolve_manual(captcha_data)

        except Exception as e:
            logger.error(f"Error Anti-Captcha: {e}")
            return self._resolve_manual(captcha_data)

    # ========== DDDDOCR ==========
    def _resolve_ddddocr(self, captcha_data: str) -> str:
        """Resolución automática local instantánea (4 dígitos 0-9)."""
        try:
            if captcha_data.startswith("data:image"):
                b64_part = captcha_data.split(",", 1)[1]
                img_bytes = base64.b64decode(b64_part)
            elif len(captcha_data) > 100:
                img_bytes = base64.b64decode(captcha_data)
            else:
                import requests
                resp = requests.get(captcha_data, timeout=10)
                img_bytes = resp.content

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

    # ========== DISPATCHER PRINCIPAL ==========
    def resolve(self, captcha_data: str) -> str:
        """
        Resuelve el captcha usando el método configurado.
        """
        if self.method == "ddddocr":
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
            return self._resolve_ddddocr(captcha_data)
