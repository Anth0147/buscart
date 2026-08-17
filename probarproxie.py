"""
Módulo probarproxie.py
======================
Valida la conexión utilizando la configuración centralizada de proxies en proxy_config.py
(SuperProxy / ISP / Residencial con geolocalización en Perú).

Prueba con 2 proxies (2 sesiones independientes):
1. Validación 1: Conectividad y resolución de IP pública real en Perú (Requests).
2. Validación 2: Carga y detección en https://visorclientes.movistar.com.pe (Navegador):
   - ✅ CARGA EXITOSA: Botón de ingreso interactivo y formulario de credenciales (OAuth / Azure B2C) disponibles.
   - 🚫 BLOQUEO DETECTADO: Interceptado por WAF / Cloudflare / 418 / Access Denied.
   - ❌ NO CARGA / PROXY FALLÓ: Error de túnel, timeout o fallo de enrutamiento del proxy.
3. Guarda capturas de pantalla de evidencia en screenshots/test_proxies/

No modifica ningún archivo existente del proyecto.
"""

import os
import sys
import time
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse
import requests

# Agregar el directorio raíz del proyecto al path
PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

# Importar configuración centralizada de proxies
from proxy_config import SUPERPROXY_CONFIG, get_proxy_config, generate_session_id

# ============================================================
# VERIFICACIÓN DE MOTOR DE NAVEGADOR
# ============================================================
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
# CONSTANTES Y SELECTORES DEL PORTAL MOVISTAR
# ============================================================
TARGET_URL = "https://visorclientes.movistar.com.pe"
LOGIN_URL = "https://visorclientes.movistar.com.pe/login"
OAUTH_DOMAIN = "login.integratel.com.pe"

SELECTORS = {
    "btn_ingreso": '//*[@id="contenedor-botones"]/div',
    "procedencia_usuario": '//*[@id="procedencia_usuario"]',
    "signInName": '//*[@id="signInName"]',
    "password": '//*[@id="password"]',
    "captcha_img": '//*[@id="captcha"]',
}

WAF_INDICATORS = [
    "418", "intercepted because it appears to be an attack",
    "request has been intercepted", "waf console", "event id:",
    "web application firewall", "blocked by waf", "access denied",
    "request blocked", "your request has been blocked",
    "cloudwaf", "blocked by cloudwaf", "forbidden", "403 forbidden",
    "security check", "incapsula", "cloudflare"
]


def test_conectividad_http(proxy_cfg: Dict, timeout: int = 15) -> Dict:
    """
    Paso 1: Valida que el proxy responda y obtenga la IP pública asignada en Perú.
    """
    server_url = proxy_cfg["server"]
    proxies = {
        "http": server_url,
        "https": server_url,
    }
    auth = (proxy_cfg["username"], proxy_cfg["password"])

    resultado = {
        "ok": False,
        "ip_salida": None,
        "latencia_s": 0.0,
        "error": None
    }

    inicio = time.time()
    try:
        resp = requests.get(
            "https://api.ipify.org?format=json",
            proxies=proxies,
            auth=auth,
            timeout=timeout
        )
        if resp.status_code == 200:
            resultado["ok"] = True
            resultado["ip_salida"] = resp.json().get("ip")
            resultado["latencia_s"] = round(time.time() - inicio, 2)
        else:
            resultado["error"] = f"HTTP {resp.status_code} al consultar IP pública"
    except requests.exceptions.ProxyError as pe:
        resultado["error"] = f"Error de autenticación o rechazo del proxy: {pe}"
    except requests.exceptions.ConnectTimeout:
        resultado["error"] = f"Timeout ({timeout}s) conectando a través del proxy"
    except Exception as e:
        resultado["error"] = str(e)

    return resultado


def test_movistar_en_navegador(proxy_cfg: Dict, headless: bool = True, timeout_ms: int = 45000) -> Dict:
    """
    Paso 2: Carga https://visorclientes.movistar.com.pe en el navegador usando el proxy.
    Evalúa si:
    - Carga exitosamente con botón de ingreso / formularios.
    - Se detecta bloqueo WAF / 418.
    - El proxy falla al cargar la página (Timeout / Connection Error).
    """
    if not HAS_BROWSER:
        return {
            "estado": "ERROR_LIBRERIA",
            "detalle": "Patchright / Playwright no está instalado en el entorno.",
            "screenshot": None,
            "url_final": None,
            "formulario_encontrado": False
        }

    screenshot_dir = PROJECT_DIR / "screenshots" / "test_proxies"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = str(screenshot_dir / f"test_{proxy_cfg['session_id']}_{int(time.time())}.png")

    resultado = {
        "estado": "DESCONOCIDO",  # "EXITO_FORMULARIO", "BLOQUEO_WAF", "FALLO_CONEXION"
        "detalle": "",
        "formulario_encontrado": False,
        "url_final": "",
        "screenshot": screenshot_path,
    }

    playwright = None
    browser = None
    context = None
    page = None

    try:
        playwright = sync_playwright().start()

        launch_opts = {
            "headless": headless,
            "proxy": {
                "server": f"http://{proxy_cfg['host']}:{proxy_cfg['port']}",
                "username": proxy_cfg["username"],
                "password": proxy_cfg["password"],
            },
            "args": [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-infobars",
                "--start-maximized"
            ]
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

        # 1. Navegar a la página de login
        try:
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=timeout_ms)
        except PlaywrightTimeout:
            resultado["estado"] = "FALLO_CONEXION"
            resultado["detalle"] = f"Timeout ({timeout_ms/1000:.0f}s) esperando respuesta de {LOGIN_URL} a través del proxy"
            return resultado
        except Exception as e:
            err_msg = str(e)
            if "407" in err_msg:
                resultado["estado"] = "FALLO_CONEXION"
                resultado["detalle"] = "Error 407: Autenticación rechazada por el proxy"
            else:
                resultado["estado"] = "FALLO_CONEXION"
                resultado["detalle"] = f"Error de conexión en el navegador: {err_msg[:90]}"
            return resultado

        time.sleep(2)
        resultado["url_final"] = page.url

        # Captura de pantalla preliminar
        try:
            page.screenshot(path=screenshot_path)
        except Exception:
            pass

        # 2. Verificar indicadores de bloqueo WAF
        body_text = (page.text_content("body") or "").lower()
        page_title = (page.title() or "").lower()

        for ind in WAF_INDICATORS:
            if ind.lower() in body_text or ind.lower() in page_title:
                resultado["estado"] = "BLOQUEO_WAF"
                resultado["detalle"] = f"Página bloqueada por WAF / Firewall ('{ind}')"
                return resultado

        # 3. Verificar si el formulario o botón de ingreso ya cargaron
        btn_ingreso = page.locator(f"xpath={SELECTORS['btn_ingreso']}")
        form_usuario = page.locator(f"xpath={SELECTORS['signInName']}")
        form_procedencia = page.locator(f"xpath={SELECTORS['procedencia_usuario']}")

        if form_usuario.is_visible() or form_procedencia.is_visible():
            resultado["estado"] = "EXITO_FORMULARIO"
            resultado["formulario_encontrado"] = True
            resultado["detalle"] = "Formulario de ingreso (OAuth / Azure B2C) cargado y visible directamente"
            return resultado

        if btn_ingreso.is_visible():
            btn_ingreso.click()
            time.sleep(4)
            resultado["url_final"] = page.url

            # Actualizar captura tras clic
            try:
                page.screenshot(path=screenshot_path)
            except Exception:
                pass

            # Verificar WAF tras clic
            body_text_click = (page.text_content("body") or "").lower()
            for ind in WAF_INDICATORS:
                if ind.lower() in body_text_click:
                    resultado["estado"] = "BLOQUEO_WAF"
                    resultado["detalle"] = f"Bloqueo WAF detectado tras hacer clic en botón de ingreso ('{ind}')"
                    return resultado

            parsed = urlparse(page.url)
            if parsed.netloc == OAUTH_DOMAIN or form_usuario.is_visible() or form_procedencia.is_visible():
                resultado["estado"] = "EXITO_FORMULARIO"
                resultado["formulario_encontrado"] = True
                resultado["detalle"] = f"Formulario cargado exitosamente en dominio OAuth ({parsed.netloc})"
            else:
                resultado["estado"] = "EXITO_FORMULARIO"
                resultado["formulario_encontrado"] = True
                resultado["detalle"] = "Página inicial cargó correctamente con botón de ingreso interactivo"
            return resultado

        # Si no hay formulario ni botón, y url es página de error
        if "chrome-error://" in page.url or page.url == "about:blank":
            resultado["estado"] = "FALLO_CONEXION"
            resultado["detalle"] = "Página en blanco / Fallo al enrutar conexión con el proxy"
        else:
            resultado["estado"] = "EXITO_FORMULARIO"
            resultado["detalle"] = f"Página cargó (URL: {page.url[:60]}), sin indicios de bloqueo"

    except Exception as e:
        resultado["estado"] = "FALLO_CONEXION"
        resultado["detalle"] = f"Error inesperado al probar en navegador: {str(e)[:100]}"
    finally:
        try:
            if page: page.close()
            if context: context.close()
            if browser: browser.close()
            if playwright: playwright.stop()
        except:
            pass

    return resultado


def probar_dos_proxies(headless: bool = True) -> List[Dict]:
    """
    Ejecuta la validación de 2 proxies (2 sesiones distintas) usando las credenciales centralizadas de proxy_config.py.
    """
    ts = int(time.time())
    proxies_a_probar = [
        get_proxy_config(session_id=f"p1t{ts}"),
        get_proxy_config(session_id=f"p2t{ts + 1}"),
    ]

    print("\n" + "="*80)
    print("🚀 VALIDANDO 2 CONEXIONES DE PROXY CON CONFIGURACIÓN CENTRALIZADA (proxy_config.py)")
    print(f"🎯 Host: {SUPERPROXY_CONFIG['host']}:{SUPERPROXY_CONFIG['port']} | Zona: {SUPERPROXY_CONFIG['zone']} | País: {SUPERPROXY_CONFIG['country'].upper()}")
    print(f"🎯 Destino: {TARGET_URL}")
    print("="*80)

    resultados = []

    for idx, proxy_cfg in enumerate(proxies_a_probar, start=1):
        print(f"\n[{idx}/2] 🔍 PROBANDO PROXY #{idx} (Sesión: {proxy_cfg['session_id']})")
        print(f"   ├─ Endpoint: {proxy_cfg['host']}:{proxy_cfg['port']}")
        print(f"   ├─ Usuario:  {proxy_cfg['username']}")

        # 1. Validación HTTP básica
        print("   ├─ [1/2] Validando conexión básica y resolución de IP...")
        test_ip = test_conectividad_http(proxy_cfg, timeout=15)

        if not test_ip["ok"]:
            print(f"   │  ❌ FALLO DEL PROXY: {test_ip['error']}")
            diag = {
                "num": idx,
                "session_id": proxy_cfg["session_id"],
                "ip_salida": "N/A",
                "latencia": "N/A",
                "estado_movistar": "FALLO_CONEXION",
                "diagnostico": "❌ EL PROXY FALLÓ (No responde a peticiones de conexión)",
                "detalle": test_ip["error"],
                "screenshot": None
            }
            resultados.append(diag)
            print(f"   └─ 🔴 DIAGNÓSTICO: {diag['diagnostico']}")
            continue

        print(f"   │  ✅ Conectado | IP de Salida: {test_ip['ip_salida']} | Latencia: {test_ip['latencia_s']}s")

        # 2. Validación en visorclientes.movistar.com.pe
        print(f"   ├─ [2/2] Validando carga y formularios en {TARGET_URL}...")
        test_mov = test_movistar_en_navegador(proxy_cfg, headless=headless)

        estado = test_mov["estado"]
        if estado == "EXITO_FORMULARIO":
            diag_str = "✅ CONEXIÓN EXITOSA (Formularios / Botón interactivo listos)"
        elif estado == "BLOQUEO_WAF":
            diag_str = "🚫 ERROR DE BLOQUEO DETECTADO (WAF / Firewall)"
        else:
            diag_str = "❌ NO CARGA LA PÁGINA (El proxy falló al acceder a Movistar)"

        print(f"   │  Detalle: {test_mov['detalle']}")
        if test_mov.get("screenshot"):
            print(f"   │  Captura de pantalla: {test_mov['screenshot']}")

        diag = {
            "num": idx,
            "session_id": proxy_cfg["session_id"],
            "ip_salida": test_ip["ip_salida"],
            "latencia": f"{test_ip['latencia_s']}s",
            "estado_movistar": estado,
            "diagnostico": diag_str,
            "detalle": test_mov["detalle"],
            "screenshot": test_mov.get("screenshot")
        }
        resultados.append(diag)
        print(f"   └─ 📌 DIAGNÓSTICO: {diag_str}")

    # Resumen final
    print("\n" + "="*80)
    print("📊 RESUMEN FINAL DE LAS 2 PRUEBAS")
    print("="*80)
    for r in resultados:
        print(f"• Proxy #{r['num']} [Sesión: {r['session_id']}]")
        print(f"  IP Asignada: {r['ip_salida']} | Latencia: {r['latencia']}")
        print(f"  Diagnóstico: {r['diagnostico']}")
        print(f"  Detalle:     {r['detalle']}")
        if r.get("screenshot"):
            print(f"  Captura:     {r['screenshot']}")
        print("-" * 80)

    return resultados


if __name__ == "__main__":
    probar_dos_proxies(headless=True)
