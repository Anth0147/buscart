"""
Configurador de Notificaciones WhatsApp (configurarwhatsapp.py)
================================================================
Permite vincular tu cuenta de WhatsApp mediante código QR y configurar
el número de teléfono receptor para las notificaciones de login y resúmenes.

La sesión queda guardada localmente en datawp/whatsapp_session/ para que los
envíos automáticos posteriores no requieran volver a escanear el QR.
"""

import os
import sys
import json
import time
import urllib.parse
from pathlib import Path

# Directorios de configuración y sesión de WhatsApp
PROJECT_DIR = Path(__file__).parent
DATAWP_DIR = PROJECT_DIR / "datawp"
SESSION_DIR = DATAWP_DIR / "whatsapp_session"
CONFIG_FILE = DATAWP_DIR / "whatsapp_config.json"

DATAWP_DIR.mkdir(parents=True, exist_ok=True)
SESSION_DIR.mkdir(parents=True, exist_ok=True)

# Importar Playwright / Patchright
try:
    from patchright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
except ImportError:
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    except ImportError:
        print("❌ Error: Ni Playwright ni Patchright están instalados.")
        print("Por favor instala playwright ejecutando: pip install playwright")


def limpiar_numero(numero: str) -> str:
    """Limpia el número de teléfono dejando solo dígitos."""
    return "".join(c for c in str(numero) if c.isdigit())


def cargar_configuracion() -> dict:
    """Carga la configuración guardada si existe."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"numero_destino": "", "activo": False}


def guardar_configuracion(config: dict):
    """Guarda la configuración en datawp/whatsapp_config.json."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def vincular_qr():
    """Abre el navegador para escanear el código QR."""
    config_actual = cargar_configuracion()
    num_default = config_actual.get("numero_destino", "")

    prompt_num = "Ingrese el número de teléfono destino con código de país\n(Ejemplo Perú: 51987654321)"
    if num_default:
        prompt_num += f" [Default: {num_default}]: "
    else:
        prompt_num += ": "

    entrada = input(prompt_num).strip()
    numero = limpiar_numero(entrada) or num_default

    if not numero:
        print("❌ Debe ingresar un número válido (ej: 51987654321).")
        return

    print(f"\n✅ Número destino: +{numero}")
    print("\n" + "="*60)
    print("🌐 ABRIENDO NAVEGADOR PARA ESCANEAR CÓDIGO QR...")
    print("Por favor, abre WhatsApp en tu celular:")
    print("  1. Ve a Ajustes / Menú (tres puntos)")
    print("  2. Selecciona 'Dispositivos vinculados'")
    print("  3. Toca 'Vincular un dispositivo'")
    print("  4. Escanea el código QR que aparecerá en la ventana.")
    print("="*60 + "\n")

    with sync_playwright() as p:
        browser_context = p.chromium.launch_persistent_context(
            user_data_dir=str(SESSION_DIR),
            headless=False,
            viewport={"width": 1280, "height": 800},
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )

        page = browser_context.pages[0] if browser_context.pages else browser_context.new_page()

        print("⏳ Navegando a WhatsApp Web...")
        try:
            page.goto("https://web.whatsapp.com", wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"⚠️ Error cargando WhatsApp Web: {e}")

        print("⏳ Esperando escaneo de código QR (tienes hasta 2 minutos)...")
        logueado = False
        start_time = time.time()

        while time.time() - start_time < 120:
            try:
                if page.locator("div#side").is_visible() or page.locator("div[contenteditable='true']").is_visible():
                    logueado = True
                    break
            except Exception:
                pass
            time.sleep(2)

        if not logueado:
            print("\n❌ Tiempo de espera agotado. No se detectó inicio de sesión con el QR.")
            browser_context.close()
            return

        print("\n🎉 ¡Inicio de sesión en WhatsApp Web detectado con éxito!")

        config_actual["numero_destino"] = numero
        config_actual["activo"] = True
        config_actual["ultima_vinculacion"] = time.strftime("%Y-%m-%d %H:%M:%S")
        guardar_configuracion(config_actual)
        print(f"💾 Configuración guardada en: {CONFIG_FILE}")

        # Enviar mensaje de prueba inmediato
        print(f"\n📤 Enviando mensaje de confirmación a +{numero}...")
        try:
            texto_prueba = "🤖 *Bot Movistar Activado*\n\n✅ Las notificaciones por WhatsApp han sido vinculadas exitosamente."
            url_send = f"https://web.whatsapp.com/send?phone={numero}&text={urllib.parse.quote(texto_prueba)}"
            page.goto(url_send, wait_until="domcontentloaded", timeout=45000)
            time.sleep(4)

            send_btn = page.locator('span[data-icon="send"]').first
            if send_btn.is_visible():
                send_btn.click()
            else:
                page.keyboard.press("Enter")

            time.sleep(3)
            print("✅ Mensaje de prueba enviado exitosamente.")
        except Exception as e:
            print(f"⚠️ Aviso enviando mensaje de prueba: {e}")

        browser_context.close()

    print("\n" + "="*60)
    print("✨ ¡CONFIGURACIÓN COMPLETADA CON ÉXITO!")
    print("="*60 + "\n")


def probar_envio_whatsapp():
    """Envía un mensaje de prueba para validar que el servicio está activo."""
    from whatsapp_notifier import enviar_whatsapp, obtener_numero_destino, esta_configurado

    if not esta_configurado():
        print("⚠️ WhatsApp no está configurado. Primero selecciona la opción 1 para vincular el QR.")
        return

    num = obtener_numero_destino()
    print(f"\n📤 Enviando mensaje de prueba a +{num}...")
    ahora = time.strftime("%Y-%m-%d %H:%M:%S")
    msg = f"🔔 *Prueba de Conexión Bot Movistar*\n\n✅ El servicio de notificaciones está activo y funcionando correctamente.\n⏰ Hora: {ahora}"
    
    exito = enviar_whatsapp(msg)
    if exito:
        print(f"✅ ¡Mensaje de prueba entregado exitosamente a +{num}!")
    else:
        print("❌ No se pudo enviar el mensaje. Es posible que la sesión de WhatsApp haya expirado. Intente re-vincular el QR.")


def configurar_whatsapp():
    """Menú interactivo de configuración de WhatsApp."""
    while True:
        cfg = cargar_configuracion()
        num = cfg.get("numero_destino", "No configurado")
        activo = "✅ ACTIVO" if cfg.get("activo") and SESSION_DIR.exists() else "⚠️ NO VINCULADO"

        print("""
============================================================
  📱 PANEL DE GESTIÓN WHATSAPP (configurarwhatsapp.py)
============================================================
""")
        print(f"  • Estado:         {activo}")
        print(f"  • Número Destino: +{num}")
        print(f"  • Carpeta Datos:  {DATAWP_DIR}")
        print("-" * 60)
        print("  1. 📲 Vincular / Re-escanear código QR (WhatsApp Web)")
        print("  2. ✉️  Enviar mensaje de prueba para verificar estado")
        print("  3. ✏️  Modificar número de teléfono receptor")
        print("  4. 🔙 Volver")
        print("=" * 60)

        op = input("\nSeleccione una opción [1-4]: ").strip()

        if op == "1":
            vincular_qr()
            input("\nPresione ENTER para continuar...")
        elif op == "2":
            probar_envio_whatsapp()
            input("\nPresione ENTER para continuar...")
        elif op == "3":
            nuevo_num = input(f"Ingrese nuevo número con código de país (actual: +{num}): ").strip()
            limpio = limpiar_numero(nuevo_num)
            if limpio:
                cfg["numero_destino"] = limpio
                guardar_configuracion(cfg)
                print(f"✅ Número actualizado a: +{limpio}")
            else:
                print("❌ Número inválido.")
            time.sleep(1)
        elif op == "4":
            break
        else:
            print("Opción no válida.")


if __name__ == "__main__":
    configurar_whatsapp()
