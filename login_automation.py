"""
Módulo de Automatización de Login - Movistar Visor Clientes
============================================================
Automatiza el flujo de login en el portal de Movistar usando Patchright.
Soporta usuario interno/externo, captura de pantalla y detección de WAF.
"""

import os
import time
import logging
import base64
import random
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict
from urllib.parse import urlparse

try:
    from patchright.sync_api import (
        sync_playwright,
        Browser,
        BrowserContext,
        Page,
        TimeoutError as PlaywrightTimeout,
    )
except ImportError:
    from playwright.sync_api import (
        sync_playwright,
        Browser,
        BrowserContext,
        Page,
        TimeoutError as PlaywrightTimeout,
    )


logger = logging.getLogger(__name__)

# ============================================================
# URLs DEL PORTAL
# ============================================================
# Página 1: portal de Movistar con el botón "Ingresar"
LOGIN_BASE_URL = "https://visorclientes.movistar.com.pe/login"

# Dominio del formulario OAuth (Azure AD B2C)
OAUTH_DOMAIN = "login.integratel.com.pe"

# ============================================================
# XPATH DE ELEMENTOS
# ============================================================
XPATHS = {
    "btn_ingreso":         '//*[@id="contenedor-botones"]/div',
    "procedencia_usuario": '//*[@id="procedencia_usuario"]',
    "signInName":          '//*[@id="signInName"]',
    "captcha_img":         '//*[@id="captcha"]',
    "codeInput":           '//*[@id="codeInput"]',
    "password":            '//*[@id="password"]',
    "btn_continuar":       '/html/body/div[3]/div/div/div/div/button',
    "btn_login":           '//*[@id="login"]',
    "error_password":      '//*[@id="claimVerificationServerError"]',
    "error_captcha":       '//*[@id="codeInput-error"]',
    "error_captcha_magic": '//*[@id="erro-captcha"]',
    "search_input":        '//*[@id="contenedor-buscar"]/visor-search-form/form/visor-search-bar/div/input',
}


# ============================================================
# INDICADORES DE WAF BLOCK
# ============================================================
WAF_BLOCK_INDICATORS = [
    "418", "intercepted because it appears to be an attack",
    "request has been intercepted", "waf console", "event id:",
    "web application firewall", "blocked by waf", "access denied",
    "request blocked", "your request has been blocked",
    "访问被拦截", "cloudwaf",
    "blocked by cloudwaf", "your request has been blocked by waf",
]

# ============================================================
# CLASE PRINCIPAL
# ============================================================

class LoginAutomation:
    """Automatización del login al portal Movistar con Patchright."""

    # Configuración por defecto de timeouts (en milisegundos)
    DEFAULT_OAUTH_TIMEOUT = 60000  # 1 minuto de espera tras el clic en el botón de ingreso

    def __init__(
        self,
        screenshot_dir: str = "screenshots",
        headless: bool = True,
        oauth_timeout_ms: int = DEFAULT_OAUTH_TIMEOUT,
    ):
        self.screenshot_dir = Path(screenshot_dir)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless
        self.oauth_timeout_ms = oauth_timeout_ms
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._results: List[Dict] = []

    # ------------------------------------------------------------
    # INICIAR NAVEGADOR CON PROXY
    # ------------------------------------------------------------
    def start_browser(self, proxy_config: Optional[dict] = None):
        """
        Inicia el navegador Patchright con configuración de proxy.
        proxy_config puede tener:
          - "server"   : URL del proxy (requerido)
          - "username" : usuario (para autenticación HTTP 407)
          - "password" : contraseña del proxy
        """
        self.playwright = sync_playwright().start()

        launch_options = {
            "headless": self.headless,
            # Patchright aplica sus parches stealth internamente.
            # Usar args limpios sin alterar TLS ni banderas sospechosas de automatización.
            "args": [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-infobars",
                "--start-maximized",
            ],
        }

        # Las credenciales van en el dict de proxy para que Patchright
        # responda automáticamente al challenge HTTP 407.
        if proxy_config and "server" in proxy_config:
            proxy_entry = {"server": proxy_config["server"]}
            if proxy_config.get("username"):
                proxy_entry["username"] = proxy_config["username"]
            if proxy_config.get("password"):
                proxy_entry["password"] = proxy_config["password"]
            launch_options["proxy"] = proxy_entry
            logger.info(
                f"🌐 Proxy: {proxy_config['server'][:55]}... "
                f"| usuario: {proxy_config.get('username', 'en URL')[:45]}"
            )
        else:
            logger.warning("⚠️ Sin proxy configurado (se usará IP local)")

        # Intentar lanzar Google Chrome nativo para máxima fidelidad TLS
        try:
            self.browser = self.playwright.chromium.launch(channel="chrome", **launch_options)
            logger.info("🚀 Lanzado Google Chrome (modo stealth)")
        except Exception:
            self.browser = self.playwright.chromium.launch(**launch_options)
            logger.info("🚀 Lanzado Chromium (modo stealth)")

        context_options = {
            "viewport": {"width": 1366, "height": 768},
            "locale": "es-PE",
            "timezone_id": "America/Lima",
        }

        self.context = self.browser.new_context(**context_options)
        self.page = self.context.new_page()
        logger.info("✅ Navegador Patchright iniciado correctamente")

    # ------------------------------------------------------------
    # CERRAR NAVEGADOR
    # ------------------------------------------------------------
    def close_browser(self):
        """Cierra el navegador y limpia recursos."""
        try:
            if self.page:
                self.page.close()
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
        except Exception as e:
            logger.error(f"Error cerrando navegador: {e}")
        finally:
            self.page = None
            self.context = None
            self.browser = None
            self.playwright = None
            logger.info("Navegador cerrado")

    # ------------------------------------------------------------
    # NAVEGACIÓN ROBUSTA
    # ------------------------------------------------------------
    def _safe_goto(self, url: str, max_retries: int = 3) -> bool:
        """
        Navega a la URL con reintentos.
        Usa domcontentloaded (HTML listo) en vez de 'load' para no
        quedar bloqueado esperando analytics/tracking lentos.
        Luego espera activamente al btn_ingreso para confirmar que
        el contenido interactivo está disponible.
        """
        for attempt in range(max_retries):
            try:
                logger.info(f"Navegando... (intento {attempt + 1}/{max_retries})")

                # domcontentloaded = HTML parseado + JS initial ejecutado.
                # Mucho más rápido que 'load' y no cuelga con tracking lento.
                self.page.goto(url, wait_until="domcontentloaded", timeout=90000)
                logger.info(f"📍 URL tras goto: {self.page.url[:80]}")

                # Ahora esperar hasta 20s a que aparezca el botón de ingreso.
                # Si aparece, la página está lista; si no, puede ser página en blanco.
                logger.info("⏳ Esperando botón de ingreso en la página...")
                try:
                    self.page.wait_for_selector(
                        f"xpath={XPATHS['btn_ingreso']}",
                        timeout=20000,
                    )
                    current_url = self.page.url
                    logger.info(f"✅ Página lista con botón de ingreso: {current_url[:80]}")
                    return True
                except PlaywrightTimeout:
                    # El botón no apareció — puede ser página en blanco o error
                    current_url = self.page.url
                    logger.warning(f"⚠️ Botón de ingreso no apareció. URL: {current_url[:80]}")
                    if current_url.startswith("chrome-error://") or current_url == "about:blank":
                        logger.warning("🔄 Página en blanco/error, reintentando...")
                        if attempt < max_retries - 1:
                            time.sleep(3)
                            continue
                        return False
                    # Si la página cargó pero no hay botón, retornar False
                    return False

            except Exception as e:
                error_msg = str(e)
                logger.warning(f"⚠️ Error en intento {attempt + 1}: {error_msg[:120]}")

                if "407" in error_msg:
                    logger.error("🚫 ERROR 407: Credenciales de proxy incorrectas")
                    raise Exception("Proxy Authentication Failed (407)")

                if attempt < max_retries - 1:
                    logger.info("Reintentando en 3 segundos...")
                    time.sleep(3)
                else:
                    raise

        return False

    # ------------------------------------------------------------
    # CLIC EN BOTÓN DE INGRESO Y ESPERA DE NAVEGACIÓN OAUTH
    # ------------------------------------------------------------
    def _click_ingreso_and_wait(self, timeout: Optional[int] = None) -> bool:
        """
        Hace clic en btn_ingreso y espera a que la página navegue
        al dominio OAuth (login.integratel.com.pe).
        El timeout por defecto es configurable (por defecto 60000ms / 1 min).
        """
        if timeout is None:
            timeout = self.oauth_timeout_ms
        try:
            element = self.page.wait_for_selector(
                f"xpath={XPATHS['btn_ingreso']}", timeout=15000
            )
            if not element:
                logger.warning("Botón de ingreso no encontrado")
                return False

            element.click()
            logger.info("🖱️ Clic en botón de ingreso realizado, esperando navegación OAuth...")

            # Esperar activamente a que el dominio cambie a login.integratel.com.pe.
            # El redirect OAuth tiene varios pasos: JS → Azure B2C → formulario.
            # Puede tardar 15-25 segundos con proxies lentos.
            deadline = time.time() + timeout / 1000
            last_url = ""
            while time.time() < deadline:
                current_url = self.page.url
                parsed = urlparse(current_url)

                # Loguear cambios de URL para seguimiento
                if current_url != last_url:
                    logger.info(f"🔄 URL: {current_url[:90]}")
                    last_url = current_url

                if parsed.netloc == OAUTH_DOMAIN:
                    logger.info(f"✅ Navegado a OAuth: {current_url[:80]}")
                    return True

                # Si el formulario de login ya apareció en el DOM (en la misma URL o redirección)
                try:
                    if (self.page.locator(f"xpath={XPATHS['procedencia_usuario']}").is_visible() or 
                        self.page.locator(f"xpath={XPATHS['signInName']}").is_visible()):
                        logger.info("✅ Formulario de login detectado en el DOM.")
                        return True
                except:
                    pass

                # Si redirigió al dashboard (sesión activa)
                if parsed.netloc == "visorclientes.movistar.com.pe":
                    path = parsed.path.rstrip("/")
                    if not path.endswith("/login"):
                        logger.info(f"ℹ️ Sesión activa detectada, en dashboard: {current_url[:60]}")
                        return True  # Señal para que attempt_login maneje esto

                time.sleep(0.5)

            logger.warning(f"⚠️ No navegó a {OAUTH_DOMAIN} en {timeout/1000:.0f}s. URL final: {self.page.url[:80]}")
            return False

        except PlaywrightTimeout:
            logger.error("❌ Timeout esperando botón de ingreso")
            return False
        except Exception as e:
            logger.error(f"❌ Error en clic de ingreso: {e}")
            return False

    # ------------------------------------------------------------
    # ESPERA AL FORMULARIO DE LOGIN
    # ------------------------------------------------------------
    def _wait_for_login_form(self, timeout: int = 20000) -> bool:
        """
        Espera a que aparezca el elemento 'procedencia_usuario'.
        Solo aplica cuando ya estamos en login.integratel.com.pe.
        """
        logger.info("⏳ Esperando formulario de login (puede tardar hasta 20s)...")
        try:
            self.page.wait_for_selector(
                f"xpath={XPATHS['procedencia_usuario']}",
                timeout=20000,
            )
            logger.info("✅ Formulario de login visible")
            return True
        except PlaywrightTimeout:
            logger.error(f"❌ Formulario no apareció en 20s. URL: {self.page.url[:80]}")
            return False
        except Exception as e:
            logger.error(f"❌ Error esperando formulario: {e}")
            return False

    # ------------------------------------------------------------
    # MÉTODOS DE INTERACCIÓN CON LA PÁGINA
    # ------------------------------------------------------------
    def _random_mouse_move(self):
        """Mueve el mouse a una posición aleatoria para simular actividad humana."""
        try:
            x = random.randint(100, 1000)
            y = random.randint(100, 600)
            self.page.mouse.move(x, y, steps=random.randint(5, 12))
        except:
            pass

    def _wait_and_fill(self, xpath: str, value: str, timeout: int = 15000) -> bool:
        """Espera un elemento, simula hover y tipeo humano carácter por carácter con enfoque asegurado (delays acelerados)."""
        try:
            element = self.page.wait_for_selector(f"xpath={xpath}", timeout=timeout)
            if element:
                # Simular movimiento del mouse hasta el elemento
                element.hover()
                time.sleep(random.uniform(0.07, 0.17))
                
                # Clic humano
                element.click()
                time.sleep(random.uniform(0.05, 0.12))
                
                # Limpiar campo
                element.fill("")
                time.sleep(random.uniform(0.07, 0.15))
                
                # Asegurar enfoque (focus) tras la limpieza
                element.focus()
                time.sleep(random.uniform(0.05, 0.1))
                
                # Escribir directamente en el elemento carácter por carácter con velocidad humana acelerada
                for char in value:
                    element.type(char)
                    time.sleep(random.uniform(0.02, 0.06))  # Entre 20ms y 60ms por tecla (muy veloz)
                
                # Pequeña pausa después de escribir
                time.sleep(random.uniform(0.1, 0.2))
                logger.info(f"⌨️ Campo llenado exitosamente: {xpath}")
                return True
        except PlaywrightTimeout:
            logger.warning(f"Timeout esperando: {xpath}")
        except Exception as e:
            logger.error(f"Error llenando {xpath}: {e}")
        return False

    def _wait_and_click(self, xpath: str, timeout: int = 10000) -> bool:
        """Espera un elemento, hace hover y clic con delays acelerados."""
        try:
            element = self.page.wait_for_selector(f"xpath={xpath}", timeout=timeout)
            if element:
                # Simular hover y retraso rápido antes de hacer click
                element.hover()
                time.sleep(random.uniform(0.1, 0.25))
                
                element.click()
                time.sleep(random.uniform(0.08, 0.15))
                return True
        except PlaywrightTimeout:
            logger.warning(f"Timeout esperando clic: {xpath}")
        except Exception as e:
            logger.error(f"Error clic en {xpath}: {e}")
        return False

    def _get_element_text(self, xpath: str, timeout: int = 5000) -> str:
        """Obtiene el texto de un elemento (vacío si no existe)."""
        try:
            element = self.page.wait_for_selector(f"xpath={xpath}", timeout=timeout)
            if element:
                return element.text_content() or ""
        except:
            pass
        return ""

    def _select_procedencia(self, procedencia: str) -> bool:
        """Selecciona la procedencia en el dropdown mapeando a usuario_interno o usuario_externo (delays acelerados)."""
        try:
            element = self.page.wait_for_selector(
                f"xpath={XPATHS['procedencia_usuario']}", timeout=15000
            )
            if element:
                # Hover al dropdown
                element.hover()
                time.sleep(random.uniform(0.08, 0.15))
                
                # Clic para enfocar el dropdown
                element.click()
                time.sleep(random.uniform(0.1, 0.2))
                
                # Determinar el valor exacto esperado del dropdown de Azure B2C
                target_val = "usuario_interno" if procedencia.lower() == "interno" else "usuario_externo"
                
                logger.info(f"Seleccionando procedencia: {target_val}")
                element.select_option(value=target_val)
                
                time.sleep(random.uniform(0.2, 0.38))
                return True
        except Exception as e:
            logger.error(f"Error seleccionando procedencia: {e}")
        return False

    def _get_captcha_image_b64(self) -> Optional[str]:
        """Extrae la imagen del captcha en base64."""
        try:
            captcha_element = self.page.wait_for_selector(
                f"xpath={XPATHS['captcha_img']}", timeout=10000
            )
            if captcha_element:
                tag = captcha_element.evaluate("el => el.tagName.toLowerCase()")
                if tag == "img":
                    src = captcha_element.get_attribute("src")
                    if src and src.startswith("data:image"):
                        return src.split(",", 1)[1] if "," in src else src
                # Fallback: screenshot del elemento
                img_bytes = captcha_element.screenshot()
                return base64.b64encode(img_bytes).decode("utf-8")
        except:
            pass
        return None

    def _click_captcha_reload(self) -> bool:
        """Hace clic en el botón de recarga/magia del captcha si no aparece."""
        xpath_svg = '//*[@id="captcha-magic"]/table/tbody/tr/td[4]/a/svg'
        xpath_a = '//*[@id="captcha-magic"]/table/tbody/tr/td[4]/a'
        logger.info("🔄 Captcha no apareció o no cargó. Intentando hacer clic en el botón de recarga...")
        try:
            # Intentar clickear el SVG
            if self._wait_and_click(xpath_svg, timeout=5000):
                logger.info("✅ Clic en botón de recarga (SVG) realizado")
                return True
            # Fallback al link parent <a>
            if self._wait_and_click(xpath_a, timeout=3000):
                logger.info("✅ Clic en botón de recarga (Link) realizado")
                return True
        except Exception as e:
            logger.warning(f"⚠️ No se pudo clickear el botón de recarga del captcha: {e}")
        return False

    def _check_error_password(self) -> str:
        return self._get_element_text(XPATHS["error_password"]).strip()

    def _check_error_captcha(self) -> str:
        err1 = self._get_element_text(XPATHS["error_captcha"]).strip()
        err2 = self._get_element_text(XPATHS["error_captcha_magic"]).strip()
        return err1 or err2

    def _take_screenshot(self, name: str) -> str:
        """Toma captura de pantalla y retorna la ruta, adaptada para modo headless."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = self.screenshot_dir / f"{name}_{timestamp}.png"
        try:
            # En modo headless, el viewport a veces no se renderiza correctamente al hacer full_page=True.
            # Nos aseguramos de fijar el viewport del context y forzar a que cargue.
            self.page.set_viewport_size({"width": 1366, "height": 768})
            time.sleep(0.5) # Pequeño respiro para renderizado
            self.page.screenshot(path=str(filepath), full_page=False) # Usar full_page=False es más seguro en headless
            logger.info(f"Captura guardada en: {filepath}")
            return str(filepath)
        except Exception as e:
            logger.error(f"⚠️ Error tomando captura de pantalla ({name}): {e}")
            return ""

    # ------------------------------------------------------------
    # DETECCIÓN DE WAF BLOCK
    # ------------------------------------------------------------
    def check_waf_block(self) -> Dict:
        """Detecta si la página actual muestra un bloqueo WAF."""
        result = {"blocked": False, "reason": "", "screenshot": ""}
        try:
            body_text = (self.page.text_content("body") or "").lower()
            page_title = (self.page.title() or "").lower()

            matched = [
                ind for ind in WAF_BLOCK_INDICATORS
                if ind.lower() in body_text or ind.lower() in page_title
            ]

            if matched:
                result["blocked"] = True
                result["reason"] = f"WAF: {', '.join(matched)}"
                result["screenshot"] = self._take_screenshot(
                    f"waf_{datetime.now().strftime('%H%M%S')}"
                )
                logger.warning(f"🚫 WAF BLOCK — URL: {self.page.url} | {matched}")
        except:
            pass
        return result

    # ------------------------------------------------------------
    # INTENTO DE LOGIN PRINCIPAL
    # ------------------------------------------------------------
    def attempt_login(
        self,
        usuario: str,
        contraseña: str,
        procedencia: str,
        captcha_resolver=None,
        max_retries_captcha: int = 3,
    ) -> Dict:
        """
        Intenta realizar el login con las credenciales dadas.

        Returns dict con:
          - exito: bool
          - error: str
          - screenshot: str (ruta)
          - url_final: str
          - waf_blocked: bool
        """
        result = {
            "usuario": usuario,
            "contraseña": contraseña,
            "procedencia": procedencia,
            "timestamp": datetime.now().isoformat(),
            "exito": False,
            "error": "",
            "screenshot": "",
            "url_final": "",
            "waf_blocked": False,
        }

        try:
            logger.info(f"🔑 Login: {usuario} ({procedencia})")

            # ── PASO 1: Cargar página inicial ──────────────────────────────
            if not self._safe_goto(LOGIN_BASE_URL):
                result["error"] = "No se pudo cargar la página inicial del portal"
                return result

            # Simular mirada/movimiento al cargar la página inicial
            self._random_mouse_move()
            time.sleep(random.uniform(0.2, 0.45))

            # ── PASO 2: Clic en botón de ingreso → esperar OAuth ───────────
            logger.info(f"🖱️ Haciendo clic en botón de ingreso (espera máx: {self.oauth_timeout_ms/1000:.0f}s)...")
            if not self._click_ingreso_and_wait(timeout=self.oauth_timeout_ms):
                result["error"] = "No se pudo navegar a la página de autenticación"
                result["screenshot"] = self._take_screenshot("no_oauth")
                return result

            # Verificar dónde aterrizamos después del clic
            current_url = self.page.url
            parsed = urlparse(current_url)

            # Si ya está en el dashboard (sesión activa previa)
            if (parsed.netloc == "visorclientes.movistar.com.pe"
                    and not parsed.path.rstrip("/").endswith("/login")):
                logger.info(f"ℹ️ Sesión activa — limpiando y reintentando login fresco")
                self.context.clear_cookies()
                try:
                    self.page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")
                except:
                    pass
                time.sleep(1)
                # Recargar la página inicial y volver a intentar el clic
                if not self._safe_goto(LOGIN_BASE_URL):
                    result["error"] = "No se pudo recargar tras limpiar sesión"
                    return result
                if not self._click_ingreso_and_wait(timeout=self.oauth_timeout_ms):
                    result["error"] = "No se pudo navegar a OAuth tras limpiar sesión"
                    result["screenshot"] = self._take_screenshot("no_oauth_clean")
                    return result

            # ── PASO 3: Esperar formulario de login ────────────────────────
            if not self._wait_for_login_form(timeout=20000):
                result["error"] = "Formulario de login no disponible"
                result["screenshot"] = self._take_screenshot("no_formulario")
                return result

            # Simular movimiento al aparecer el formulario
            self._random_mouse_move()
            time.sleep(random.uniform(0.3, 0.8))

            # ── PASO 4: Verificar WAF ──────────────────────────────────────
            waf = self.check_waf_block()
            if waf["blocked"]:
                result["waf_blocked"] = True
                result["error"] = waf["reason"]
                result["screenshot"] = waf["screenshot"]
                return result

            # ── PASO 5: Seleccionar procedencia ───────────────────────────
            if not self._select_procedencia(procedencia):
                result["error"] = "No se pudo seleccionar procedencia"
                return result
            time.sleep(0.2)

            # ── PASO 6: Ingresar usuario ───────────────────────────────────
            if not self._wait_and_fill(XPATHS["signInName"], usuario):
                result["error"] = "No se pudo ingresar usuario"
                return result
            time.sleep(0.2)

            # ── PASO 7: Ingresar contraseña (MOVIDO ANTES DEL CAPTCHA) ──────
            waf = self.check_waf_block()
            if waf["blocked"]:
                result["waf_blocked"] = True
                result["error"] = waf["reason"]
                result["screenshot"] = waf["screenshot"]
                return result

            if not self._wait_and_fill(XPATHS["password"], contraseña, timeout=10000):
                current_url = self.page.url
                if "visorclientes.movistar.com.pe" in current_url:
                    result["exito"] = True
                    result["url_final"] = current_url
                    result["screenshot"] = self._take_screenshot(f"exito_{usuario}")
                    logger.info(f"✅ Login exitoso (sesión activa sin pass): {usuario}")
                    return result
                result["error"] = "No se encontró campo de contraseña"
                result["screenshot"] = self._take_screenshot("no_password_field")
                return result
            time.sleep(0.2)

            # ── PASO 8: Captcha con reintentos (MOVIDO DESPUÉS DE LA CONTRASEÑA) ──
            captcha_ok = False
            for retry in range(max_retries_captcha):
                # Validar de forma proactiva si ya apareció el mensaje de contraseña incorrecta antes del captcha
                error_pass = self._check_error_password()
                if error_pass:
                    result["error"] = f"Contraseña incorrecta: {error_pass}"
                    return result

                captcha_b64 = self._get_captcha_image_b64()

                if not captcha_b64:
                    # Si no aparece, hacer clic en el botón mágico
                    self._click_captcha_reload()
                    time.sleep(random.uniform(1.0, 1.8))
                    # Volver a validar si hay error de pass visible
                    error_pass = self._check_error_password()
                    if error_pass:
                        result["error"] = f"Contraseña incorrecta: {error_pass}"
                        return result
                    captcha_b64 = self._get_captcha_image_b64()

                # Requisito 2: Si el captcha no se pudo encontrar tras los intentos, abortar para reintentar con la misma IP
                if not captcha_b64:
                    result["error"] = "No se encontró captcha, intentando continuar..."
                    logger.warning("⚠️ No se pudo obtener la imagen base64 del captcha. Abortando intento.")
                    return result

                captcha_text = ""
                if captcha_resolver and callable(captcha_resolver):
                    # Resolver captcha
                    raw_text = captcha_resolver(captcha_b64) or ""
                    
                    # Corrección temprana de similitud: mapear caracteres visualmente similares que suelen ser números
                    # Reemplazamos 'D' o 'd' por '0', 'O' u 'o' por '0', 'I' o 'l' por '1', etc.
                    mapped_text = ""
                    for char in raw_text:
                        c_upper = char.upper()
                        if c_upper == 'D' or c_upper == 'O':
                            mapped_text += '0'
                        elif c_upper == 'I' or c_upper == 'L':
                            mapped_text += '1'
                        elif c_upper == 'Z':
                            mapped_text += '2'
                        elif c_upper == 'S':
                            mapped_text += '5'
                        elif c_upper == 'B':
                            mapped_text += '8'
                        else:
                            mapped_text += char

                    # Filtrar solo dígitos y validar que sean exactamente 4
                    digits_only = "".join([c for c in mapped_text if c.isdigit()])
                    if len(digits_only) == 4:
                        captcha_text = digits_only
                        logger.info(f"✅ Resolutor captcha mapeado y verificado (4 dígitos): [{captcha_text}]")
                    else:
                        logger.warning(f"⚠️ Captcha resuelto '{raw_text}' (mapeado: '{mapped_text}') no cumple con 4 dígitos. Recargando...")
                        self._click_captcha_reload()
                        time.sleep(random.uniform(1.0, 1.8))
                        continue
                else:
                    logger.info(f"📷 CAPTCHA (intento {retry+1}/{max_retries_captcha})")
                    captcha_text = input("Ingrese el valor del captcha: ").strip()

                if captcha_text:
                    self._wait_and_fill(XPATHS["codeInput"], captcha_text)
                    time.sleep(0.2)

                self._wait_and_click(XPATHS["btn_continuar"])
                time.sleep(1.5)

                # Validar inmediatamente después de hacer clic en Continuar si se reportó contraseña incorrecta
                error_pass = self._check_error_password()
                if error_pass:
                    result["error"] = f"Contraseña incorrecta: {error_pass}"
                    return result

                captcha_error = self._check_error_captcha()
                if not captcha_error:
                    captcha_ok = True
                    break
                else:
                    logger.warning(f"⚠️ Captcha incorrecto (intento {retry+1}): {captcha_error}")
                    self.page.reload(wait_until="load")
                    time.sleep(1.0)
                    self._select_procedencia(procedencia)
                    time.sleep(0.2)
                    self._wait_and_fill(XPATHS["signInName"], usuario)
                    time.sleep(0.2)
                    self._wait_and_fill(XPATHS["password"], contraseña)
                    time.sleep(0.2)

            if not captcha_ok:
                result["error"] = f"Captcha falló después de {max_retries_captcha} intentos"
                result["screenshot"] = self._take_screenshot("captcha_fail")
                return result

            # ── PASO 9: Clic en login ──────────────────────────────────────
            error_pass = self._check_error_password()
            if error_pass:
                result["error"] = f"Contraseña incorrecta: {error_pass}"
                return result

            self._wait_and_click(XPATHS["btn_login"])

            # ── PASO 10: Detección instantánea de resultado ────────────────
            start_detect = time.time()
            while time.time() - start_detect < 15:
                # 1. Detección instantánea de buscador de Visor Clientes (ÉXITO CONFIRMADO)
                try:
                    search_elem = self.page.locator(f"xpath={XPATHS['search_input']}")
                    if search_elem.is_visible():
                        result["exito"] = True
                        result["url_final"] = self.page.url
                        safe_user = usuario.replace("@", "_").replace(".", "_")
                        safe_pass = contraseña.replace("@", "_").replace(".", "_")
                        result["screenshot"] = self._take_screenshot(f"exito_{safe_user}_pass_{safe_pass}")
                        logger.info(f"✅ LOGIN EXITOSO DETECTADO AL INSTANTE (Buscador visible): {usuario}")
                        return result
                except:
                    pass

                # 2. Detección por URL de dashboard
                current_url = self.page.url
                if "visorclientes.movistar.com.pe" in current_url and not current_url.rstrip("/").endswith("/login"):
                    result["exito"] = True
                    result["url_final"] = current_url
                    safe_user = usuario.replace("@", "_").replace(".", "_")
                    safe_pass = contraseña.replace("@", "_").replace(".", "_")
                    result["screenshot"] = self._take_screenshot(f"exito_{safe_user}_pass_{safe_pass}")
                    logger.info(f"✅ LOGIN EXITOSO DETECTADO (Dashboard URL): {usuario}")
                    return result

                # 3. Detección de error de contraseña
                error_pass = self._check_error_password()
                if error_pass:
                    result["error"] = f"Contraseña incorrecta: {error_pass}"
                    return result

                # 4. Detección WAF
                waf = self.check_waf_block()
                if waf["blocked"]:
                    result["waf_blocked"] = True
                    result["error"] = waf["reason"]
                    result["screenshot"] = waf["screenshot"]
                    return result

                time.sleep(0.25)

            # Si terminó el tiempo de detección
            current_url = self.page.url
            if "visorclientes.movistar.com.pe" in current_url:
                result["exito"] = True
                result["url_final"] = current_url
                safe_user = usuario.replace("@", "_").replace(".", "_")
                safe_pass = contraseña.replace("@", "_").replace(".", "_")
                result["screenshot"] = self._take_screenshot(f"exito_{safe_user}_pass_{safe_pass}")
                logger.info(f"✅ LOGIN EXITOSO: {usuario}")
            else:
                result["url_final"] = current_url
                error_pass = self._check_error_password()
                if error_pass:
                    result["error"] = f"Contraseña incorrecta: {error_pass}"
                else:
                    result["error"] = f"Login no completado. URL: {current_url[:80]}"


        except Exception as e:
            error_msg = str(e)
            result["error"] = f"Error: {error_msg[:120]}"
            logger.error(f"Error en login de {usuario}: {error_msg}")
            if "407" in error_msg:
                result["waf_blocked"] = True

        # Eliminar capturas temporales si no es exitoso para mantener limpia la carpeta screenshots
        if not result["exito"]:
            # Buscamos en la carpeta screenshots cualquier archivo que comience con los nombres temporales o el usuario
            try:
                # Archivos generados temporalmente durante este intento fallido
                for file_path in self.screenshot_dir.glob("*"):
                    if file_path.is_file():
                        # Si contiene el email del usuario, o es de error genérico del intento actual
                        if (usuario in file_path.name or 
                            "no_oauth" in file_path.name or 
                            "no_formulario" in file_path.name or 
                            "captcha_fail" in file_path.name or 
                            "waf_" in file_path.name):
                            file_path.unlink()
            except Exception as e:
                logger.error(f"Error limpiando capturas fallidas: {e}")
        else:
            # Si fue exitoso, limpiar cualquier captura de error/captcha previo
            try:
                for file_path in self.screenshot_dir.glob("*"):
                    if file_path.is_file():
                        if usuario in file_path.name and "exito_" not in file_path.name:
                            file_path.unlink()
                        elif ("no_oauth" in file_path.name or 
                              "no_formulario" in file_path.name or 
                              "captcha_fail" in file_path.name or 
                              "waf_" in file_path.name):
                            # Limpiar temporales huérfanas
                            file_path.unlink()
            except Exception as e:
                logger.error(f"Error limpiando capturas temporales tras éxito: {e}")

        self._results.append(result)
        return result

    def get_results(self) -> List[Dict]:
        return self._results

    def get_successful_logins(self) -> List[Dict]:
        return [r for r in self._results if r.get("exito")]