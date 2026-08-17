"""
Módulo de Rotación de IP + Blacklist + Pre-validación
=======================================================
- Proxy HTTP/HTTPS con pre-testeo de conectividad
- VPN / TOR / ScraperAPI / Bright Data
- Blacklist automática por WAF/418
- Pre-validación: prueba todas las IPs, malas → ipneg.txt, buenas → ipgood.txt
- Soporte multihilo: get_proxy_for_thread(thread_idx)
"""

import subprocess
import time
import logging
import requests
import socket
import os
import sys
import json
import concurrent.futures
from pathlib import Path
from typing import Optional, Tuple, List, Dict
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


def _clean_bom(text: str) -> str:
    """Elimina BOM (Byte Order Mark) al inicio del texto."""
    return text.lstrip("\ufeff\ufffe\ufeff")


class IPBlacklist:
    """
    Gestor de blacklist de IPs bloqueadas por WAF.
    Persiste en data/ip_blacklist.json.
    """

    def __init__(self, blacklist_path: str = "data/ip_blacklist.json"):
        self.blacklist_path = Path(blacklist_path)
        self.blacklist_path.parent.mkdir(parents=True, exist_ok=True)
        self._entries: List[dict] = self._load()
        self._blocked_ips: set = {e["ip"] for e in self._entries}
        logger.info(f"Blacklist cargada: {len(self._blocked_ips)} IPs bloqueadas")

    def _load(self) -> List[dict]:
        if not self.blacklist_path.exists():
            return []
        try:
            with open(self.blacklist_path, "r", encoding="utf-8-sig") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error cargando blacklist: {e}")
            return []

    def _save(self):
        try:
            with open(self.blacklist_path, "w", encoding="utf-8") as f:
                json.dump(self._entries, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error guardando blacklist: {e}")

    def add(self, ip: str, reason: str = "WAF block", screenshot: str = "") -> bool:
        if ip in self._blocked_ips or ip in ("desconocida", "", "N/A"):
            return False
        entry = {
            "ip": ip, "reason": reason,
            "timestamp": datetime.now().isoformat(),
            "screenshot": screenshot,
        }
        self._entries.append(entry)
        self._blocked_ips.add(ip)
        self._save()
        logger.warning(f"BLACKLIST IP: {ip} | {reason} | Total: {len(self._blocked_ips)}")
        return True

    def is_blacklisted(self, ip: str) -> bool:
        return ip in self._blocked_ips

    def get_blacklisted_ips(self) -> List[str]:
        return list(self._blocked_ips)

    def remove(self, ip: str):
        if ip in self._blocked_ips:
            self._blocked_ips.discard(ip)
            self._entries = [e for e in self._entries if e["ip"] != ip]
            self._save()

    def clear(self):
        self._entries = []
        self._blocked_ips = set()
        self._save()

    def get_count(self) -> int:
        return len(self._blocked_ips)

    def get_summary(self) -> dict:
        return {
            "total_blocked": len(self._blocked_ips),
            "ips": list(self._blocked_ips),
            "entries": self._entries[-20:],
        }


class IPRotator:
    """Gestor de rotación de IP con múltiples backends + blacklist + multihilo."""

    def __init__(self, config_path: str = "data/ip.txt", blacklist: IPBlacklist = None):
        self.config_path = Path(config_path)
        self.current_ip = self._get_current_ip()
        self.rotation_count = 0
        self.config = self._parse_config()
        self.rotation_enabled = self._is_rotation_enabled()
        self.blacklist = blacklist or IPBlacklist(
            str(self.config_path.parent / "ip_blacklist.json")
        )
        self._skip_blacklisted_on_rotate = True
        # Para multihilo: lista de proxies válidos con su IP real resuelta
        self._validated_proxies: List[Dict] = []  # [{cfg, ip, proxy_url}]
        self._current_proxy_idx = 0

        logger.info(f"IP actual: {self.current_ip}")
        logger.info(f"Rotacion de IP: {'ACTIVADA' if self.rotation_enabled else 'DESACTIVADA'}")
        logger.info(f"Blacklist: {self.blacklist.get_count()} IPs bloqueadas")

    # ===================== PARSER (con fix BOM) =====================

    def _parse_config(self) -> dict:
        """Parsea ip.txt. Soporta BOM, comentarios #, lineas vacias."""
        if not self.config_path.exists():
            logger.warning(f"No se encontro {self.config_path}")
            return {"type": "none", "enabled": False}

        configs = []
        with open(self.config_path, "r", encoding="utf-8-sig") as f:
            for raw_line in f:
                line = raw_line.strip()
                # Eliminar BOM residual por si acaso
                line = _clean_bom(line)
                # Saltar vacios y comentarios
                if not line or line.startswith("#"):
                    continue
                # Saltar "none"
                if line.lower() == "none":
                    continue

                parts = line.split(":")
                method = parts[0].strip().lower()

                if not method or method == "none":
                    continue

                config = {"type": method, "raw": line}

                if method == "proxy":
                    if len(parts) >= 5:
                        config["host"] = parts[1].strip()
                        config["port"] = int(parts[2].strip())
                        config["username"] = parts[3].strip()
                        config["password"] = parts[4].strip()
                    elif len(parts) >= 3:
                        config["host"] = parts[1].strip()
                        config["port"] = int(parts[2].strip())
                        config["username"] = None
                        config["password"] = None
                    else:
                        logger.warning(f"Linea de proxy mal formada: {line}")
                        continue

                elif method == "vpn":
                    config["name"] = parts[1].strip() if len(parts) > 1 else "default"

                elif method == "tor":
                    config["control_port"] = int(parts[1]) if len(parts) > 1 else 9051
                    config["socks_port"] = int(parts[2]) if len(parts) > 2 else 9050
                    config["password"] = parts[3].strip() if len(parts) > 3 else ""

                elif method == "scraperapi":
                    config["api_key"] = parts[1].strip() if len(parts) > 1 else ""

                elif method == "brightdata":
                    config["token"] = parts[1].strip() if len(parts) > 1 else ""

                else:
                    logger.warning(f"Metodo no reconocido (ignorado): '{method}' en linea: {line}")
                    continue

                configs.append(config)

        if not configs:
            return {"type": "none", "enabled": False}

        return {"type": configs[0]["type"], "configs": configs, "enabled": True}

    def _is_rotation_enabled(self) -> bool:
        return self.config.get("enabled", False)

    def _get_current_ip(self) -> str:
        try:
            r = requests.get("https://api.ipify.org?format=json", timeout=10)
            return r.json().get("ip", "desconocida")
        except Exception:
            try:
                r = requests.get("https://httpbin.org/ip", timeout=10)
                return r.json().get("origin", "desconocida")
            except Exception:
                return "desconocida"

    # ============ PRE-VALIDACION DE IPS ============

    def pre_validate_proxies(self, max_workers: int = 20, timeout: int = 12) -> Tuple[List[Dict], List[Dict]]:
        """
        Testea TODOS los proxies en paralelo.
        Retorna: (good_proxies, bad_proxies)
        Cada uno es [{cfg, ip, proxy_url, latency}]
        Guarda resultados en ipgood.txt e ipneg.txt.
        """
        configs = self.config.get("configs", [])
        if not configs:
            logger.error("No hay proxies para validar")
            return [], []

        print(f"\n{'='*60}")
        print(f"🔍 PRE-VALIDACION DE PROXIES ({len(configs)} proxies, {max_workers} hilos)")
        print(f"{'='*60}")

        good = []
        bad = []
        total = len(configs)
        completed = 0

        def test_one(idx_cfg):
            idx, cfg = idx_cfg
            proxy_url = f"http://{cfg['host']}:{cfg['port']}"
            if cfg.get("username"):
                proxy_url = f"http://{cfg['username']}:{cfg['password']}@{cfg['host']}:{cfg['port']}"

            proxies = {"http": proxy_url, "https": proxy_url}
            auth = (cfg["username"], cfg["password"]) if cfg.get("username") else None

            start = time.time()
            err_msg = ""
            try:
                r = requests.get(
                    "https://api.ipify.org?format=json",
                    proxies=proxies, auth=auth, timeout=timeout
                )
                ip = r.json().get("ip", "")
                latency = round(time.time() - start, 2)
                if ip:
                    return {"ok": True, "cfg": cfg, "ip": ip, "proxy_url": proxy_url, "latency": latency, "idx": idx}
            except Exception as e:
                latency = round(time.time() - start, 2)
                err_msg = str(e)
            return {"ok": False, "cfg": cfg, "ip": "", "proxy_url": proxy_url, "latency": latency, "idx": idx, "error": err_msg}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(test_one, (i, c)): i for i, c in enumerate(configs)}
            for future in as_completed(futures):
                result = future.result()
                completed += 1
                if result["ok"]:
                    good.append(result)
                else:
                    bad.append(result)
                
                percent = int(completed * 100 / total)
                bar_length = 25
                filled_length = int(bar_length * completed // total)
                bar = '█' * filled_length + '-' * (bar_length - filled_length)
                
                sys.stdout.write(f"\rProgreso: [{bar}] {percent}% ({completed}/{total}) | Buenas: {len(good)} | Malas: {len(bad)}")
                sys.stdout.flush()
        
        print()  # Nueva línea al terminar

        # Guardar resultados
        self._save_ip_files(good, bad)

        # Guardar buenas en cache interno
        self._validated_proxies = good

        print(f"\n  Resultado: {len(good)} BUENAS / {len(bad)} MALAS de {len(configs)} totales")
        if bad:
            print(f"  📁 IPs negativas guardadas en: data/ipneg.txt")
        if good:
            print(f"  📁 IPs validadas guardadas en: data/ipgood.txt")

        return good, bad

    def _save_ip_files(self, good: List[Dict], bad: List[Dict]):
        """Guarda ipgood.txt e ipneg.txt."""
        data_dir = self.config_path.parent

        # ipgood.txt - solo las lineas proxy originales que funcionan
        good_path = data_dir / "ipgood.txt"
        with open(good_path, "w", encoding="utf-8") as f:
            for item in good:
                f.write(f"{item['cfg']['raw']}\n")

        # ipneg.txt - las que no funcionan con motivo
        neg_path = data_dir / "ipneg.txt"
        with open(neg_path, "w", encoding="utf-8") as f:
            f.write(f"# IPs NO VALIDAS - generado {datetime.now().isoformat()}\n")
            for item in bad:
                err = item.get('error', 'timeout')[:80]
                f.write(f"# ERROR: {err}\n")
                f.write(f"{item['cfg']['raw']}\n")

    # ============ ROTACION POR INDICE (multihilo) ============

    def get_proxy_for_batch(self, batch_idx: int) -> Optional[Dict]:
        """
        Retorna el proxy config para un batch de hilos.
        Siempre retorna el siguiente proxy VALIDO que no este en blacklist.
        """
        if not self._validated_proxies:
            return None

        n = len(self._validated_proxies)
        for attempt in range(n):
            idx = (batch_idx + attempt) % n
            vp = self._validated_proxies[idx]
            if not self.blacklist.is_blacklisted(vp["ip"]):
                self._current_proxy_idx = idx
                self.current_ip = vp["ip"]
                return vp

        logger.error("Todos los proxies validados estan en blacklist")
        return None

    def get_proxy_config_for_playwright(self, validated_proxy: Dict) -> Optional[dict]:
        """Convierte un validated_proxy a config de Playwright."""
        if not validated_proxy:
            return None
        cfg = validated_proxy["cfg"]
        return {
            "server": f"http://{cfg['host']}:{cfg['port']}",
            "username": cfg.get("username"),
            "password": cfg.get("password"),
        }

    # ============ ROTACION CLASICA (secuencial) ============

    def rotate_ip(self, skip_blacklisted: bool = True) -> Tuple[bool, str]:
        if not self.rotation_enabled:
            return True, self.current_ip

        self._skip_blacklisted_on_rotate = skip_blacklisted
        method = self.config["type"]

        try:
            if method == "proxy":
                success, new_ip = self._rotate_proxy()
            elif method == "vpn":
                success, new_ip = self._rotate_vpn()
            elif method == "tor":
                success, new_ip = self._rotate_tor()
            elif method == "scraperapi":
                success, new_ip = self._rotate_scraperapi()
            elif method == "brightdata":
                success, new_ip = self._rotate_brightdata()
            else:
                logger.warning(f"Metodo no soportado: {method}")
                return False, self.current_ip

            if success:
                if skip_blacklisted and self.blacklist.is_blacklisted(new_ip):
                    logger.warning(f"IP {new_ip} en BLACKLIST, re-rotando...")
                    self.rotation_count += 1
                    return self.rotate_ip(skip_blacklisted=True)
                self.current_ip = new_ip
                self.rotation_count += 1
                logger.info(f"Rotacion #{self.rotation_count} OK. Nueva IP: {new_ip}")
            else:
                logger.error("Rotacion de IP fallo")

            return success, new_ip

        except Exception as e:
            logger.error(f"Error en rotacion de IP: {e}")
            return False, self.current_ip

    def blacklist_current_ip(self, reason: str = "WAF 418", screenshot: str = "") -> bool:
        logger.warning(f"BLACKLISTEANDO IP: {self.current_ip} | {reason}")
        self.blacklist.add(self.current_ip, reason=reason, screenshot=screenshot)
        success, new_ip = self.rotate_ip(skip_blacklisted=True)
        if success and new_ip != self.current_ip:
            logger.info(f"Nueva IP obtenida: {new_ip}")
            return True
        logger.error(f"No se pudo obtener nueva IP. Blacklist: {self.blacklist.get_blacklisted_ips()}")
        return False

    def _rotate_proxy(self, max_attempts: int = 20) -> Tuple[bool, str]:
        configs = self.config.get("configs", [])
        if not configs:
            return False, self.current_ip

        for attempt in range(min(max_attempts, len(configs) * 3)):
            idx = (self.rotation_count + attempt) % len(configs)
            cfg = configs[idx]

            proxy_url = f"http://{cfg['host']}:{cfg['port']}"
            if cfg.get("username"):
                proxy_url = f"http://{cfg['username']}:{cfg['password']}@{cfg['host']}:{cfg['port']}"

            try:
                proxies = {"http": proxy_url, "https": proxy_url}
                auth = (cfg["username"], cfg["password"]) if cfg.get("username") else None
                resp = requests.get("https://api.ipify.org?format=json",
                                   proxies=proxies, auth=auth, timeout=15)
                new_ip = resp.json().get("ip", self.current_ip)

                if self._skip_blacklisted_on_rotate and self.blacklist.is_blacklisted(new_ip):
                    logger.warning(f"Proxy {cfg['host']}:{cfg['port']} -> IP {new_ip} en BLACKLIST, saltando...")
                    self.rotation_count += 1
                    continue

                logger.info(f"Proxy activo: {cfg['host']}:{cfg['port']} -> IP: {new_ip}")
                self._last_proxy_cfg = cfg
                return True, new_ip

            except Exception as e:
                logger.error(f"Proxy {cfg['host']}:{cfg['port']} no responde: {e}")
                self.rotation_count += 1
                continue

        logger.error("Todos los proxies en blacklist o no responden")
        return False, self.current_ip

    def _rotate_vpn(self) -> Tuple[bool, str]:
        configs = self.config.get("configs", [])
        if not configs:
            return False, self.current_ip
        idx = self.rotation_count % len(configs)
        cfg = configs[idx]
        try:
            subprocess.run(["sudo", "killall", "openvpn"], capture_output=True, timeout=10)
        except Exception:
            pass
        vpn_path = Path(f"/etc/openvpn/{cfg.get('name', 'default')}.conf")
        if vpn_path.exists():
            try:
                subprocess.Popen(["sudo", "openvpn", "--config", str(vpn_path)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                time.sleep(10)
                new_ip = self._get_current_ip()
                return new_ip != self.current_ip, new_ip
            except Exception as e:
                logger.error(f"Error VPN: {e}")
        return False, self.current_ip

    def _rotate_tor(self) -> Tuple[bool, str]:
        configs = self.config.get("configs", [])
        cfg = configs[0] if configs else {"control_port": 9051, "socks_port": 9050, "password": ""}
        try:
            from stem import Signal
            from stem.control import Controller
            with Controller.from_port(port=cfg["control_port"]) as ctrl:
                ctrl.authenticate(password=cfg.get("password") or None)
                ctrl.signal(Signal.NEWNYM)
            time.sleep(10)
            proxies = {"http": f"socks5h://127.0.0.1:{cfg.get('socks_port', 9050)}",
                       "https": f"socks5h://127.0.0.1:{cfg.get('socks_port', 9050)}"}
            r = requests.get("https://api.ipify.org?format=json", proxies=proxies, timeout=15)
            return True, r.json().get("ip", self.current_ip)
        except ImportError:
            logger.warning("stem no instalada. pip install stem")
        except Exception as e:
            logger.error(f"Error TOR: {e}")
        return False, self.current_ip

    def _rotate_scraperapi(self) -> Tuple[bool, str]:
        configs = self.config.get("configs", [])
        cfg = configs[0] if configs else {"api_key": ""}
        if not cfg["api_key"]:
            return False, self.current_ip
        try:
            url = f"http://api.scraperapi.com?api_key={cfg['api_key']}&url=https://api.ipify.org?format=json"
            return True, requests.get(url, timeout=15).json().get("ip", self.current_ip)
        except Exception as e:
            logger.error(f"ScraperAPI error: {e}")
            return False, self.current_ip

    def _rotate_brightdata(self) -> Tuple[bool, str]:
        configs = self.config.get("configs", [])
        cfg = configs[0] if configs else {"token": ""}
        if not cfg["token"]:
            return False, self.current_ip
        try:
            p = f"http://lum-customer-{cfg['token']}-zone-residential:brd_proxy@zproxy.lum-superproxy.io:22225"
            r = requests.get("https://api.ipify.org?format=json", proxies={"http": p, "https": p}, timeout=15)
            return True, r.json().get("ip", self.current_ip)
        except Exception as e:
            logger.error(f"Bright Data error: {e}")
            return False, self.current_ip

    # ============ HELPERS ============

    def get_playwright_proxy_config(self) -> Optional[dict]:
        if not self.rotation_enabled:
            return None
        configs = self.config.get("configs", [])
        if not configs:
            return None
        method = self.config["type"]
        if method == "proxy":
            cfg = configs[self.rotation_count % len(configs)]
            return {"server": f"http://{cfg['host']}:{cfg['port']}",
                    "username": cfg.get("username"), "password": cfg.get("password")}
        elif method == "tor":
            cfg = configs[0]
            return {"server": f"socks5://127.0.0.1:{cfg.get('socks_port', 9050)}"}
        return None

    def has_available_ips(self) -> bool:
        if not self.rotation_enabled:
            return True
        if self._validated_proxies:
            return any(not self.blacklist.is_blacklisted(vp["ip"]) for vp in self._validated_proxies)
        return True

    def get_validated_count(self) -> int:
        return len(self._validated_proxies)

    def get_status(self) -> dict:
        return {
            "current_ip": self.current_ip,
            "rotation_count": self.rotation_count,
            "enabled": self.rotation_enabled,
            "method": self.config.get("type", "none"),
            "total_configs": len(self.config.get("configs", [])),
            "validated_good": len(self._validated_proxies),
            "blacklist_count": self.blacklist.get_count(),
            "blacklisted_ips": self.blacklist.get_blacklisted_ips(),
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rotator = IPRotator("data/ip.txt")
    print(json.dumps(rotator.get_status(), indent=2, ensure_ascii=False))
