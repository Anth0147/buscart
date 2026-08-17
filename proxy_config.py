"""
Módulo de Configuración Centralizada de Proxies
================================================
Define los parámetros de conexión, credenciales y generador de sesiones
para proxies residenciales / ISP (BrightData / SuperProxy / Oxylabs)
con geolocalización en Perú.

Este archivo es el punto central de configuración para:
- main.py
- probarproxie.py
- probarteletrabajo.py
- Otros módulos que requieran conexión por proxy
"""

import time
from typing import Dict, Optional, Tuple

# ============================================================
# CONFIGURACIÓN SUPERPROXY / RESIDENCIAL (PERÚ)
# ============================================================
SUPERPROXY_CONFIG = {
    "host": "brd.superproxy.io",
    "port": "44445",
    "customer": "brd-customer-hl_5bafdcb9",
    "zone": "zone-isp_proxy1",
    "password": "669zvtxm6e5h",
    "country": "pe",  # Perú
}

# Alias para compatibilidad
PROXY_CONFIG = SUPERPROXY_CONFIG

_session_counter = 0


def generate_session_id() -> str:
    """
    Genera un ID de sesión único (solo alfanumérico).
    BrightData requiere formato alfanumérico sin caracteres especiales.
    """
    global _session_counter
    _session_counter += 1
    return f"s{_session_counter}t{int(time.time())}"


def get_proxy_config(session_id: Optional[str] = None, country: Optional[str] = None) -> Dict:
    """
    Genera el diccionario con la configuración del proxy para la sesión indicada.
    
    Retorna un diccionario con:
      - server: URL completa http://user:pass@host:port
      - username: Usuario con zone, country y session
      - password: Password del proxy
      - host: Hostname del servidor
      - port: Puerto del servidor
      - session_id: ID único de sesión
      - ip: Etiqueta descriptiva de la sesión
      - country: País configurado (por defecto 'pe')
    """
    cfg = SUPERPROXY_CONFIG
    if session_id is None:
        session_id = generate_session_id()
    
    target_country = country or cfg.get("country", "pe")
    
    # Formato de usuario con país y sesión para rotación de IP
    username = f"{cfg['customer']}-{cfg['zone']}-country-{target_country}-session-{session_id}"
    
    # URL completa con autenticación
    proxy_url = f"http://{username}:{cfg['password']}@{cfg['host']}:{cfg['port']}"
    
    return {
        "server": proxy_url,
        "username": username,
        "password": cfg["password"],
        "host": cfg["host"],
        "port": cfg["port"],
        "session_id": session_id,
        "country": target_country,
        "ip": f"SuperProxy-{target_country.upper()}-{session_id[:8]}"
    }


def get_browser_proxy_dict(proxy_cfg: Optional[Dict]) -> Optional[Dict]:
    """
    Retorna el diccionario de configuración de proxy listo para Playwright / Patchright.
    Si proxy_cfg es None, retorna None (para usar IP local).
    """
    if not proxy_cfg:
        return None
    
    return {
        "server": f"http://{proxy_cfg['host']}:{proxy_cfg['port']}",
        "username": proxy_cfg["username"],
        "password": proxy_cfg["password"],
    }


def get_requests_proxies(proxy_cfg: Optional[Dict]) -> Tuple[Optional[Dict], Optional[Tuple[str, str]]]:
    """
    Retorna (proxies_dict, auth_tuple) para la librería requests.
    """
    if not proxy_cfg:
        return None, None
    
    server_url = proxy_cfg.get("server") or f"http://{proxy_cfg['host']}:{proxy_cfg['port']}"
    proxies = {
        "http": server_url,
        "https": server_url,
    }
    auth = (proxy_cfg["username"], proxy_cfg["password"])
    return proxies, auth

