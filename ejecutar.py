#!/usr/bin/env python3
"""
Orquestador Principal del Sistema (ejecutar.py)
================================================
Unifica y coordina todos los módulos del proyecto:
1. probarproxie.py       -> Validación de proxies con proxy_config.py
2. configurarwhatsapp.py -> Vinculación QR y configuración de WhatsApp
3. main.py               -> Automatización de login en Visor Clientes Movistar
4. probarteletrabajo.py  -> Automatización de login en Teletrabajo Movistar

Incluye:
- Detección y recuperación automática de sesiones interrumpidas (Checkpoints).
- Notificaciones de eventos por WhatsApp (Login exitoso, resumen y errores críticos).
"""

import os
import sys
import time
import json
import logging
from pathlib import Path
from datetime import datetime

# Configuración de rutas
PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

# Importar gestores del sistema
from state_manager import cargar_checkpoint, limpiar_checkpoint
from whatsapp_notifier import esta_configurado, obtener_numero_destino
from proxy_config import SUPERPROXY_CONFIG


def mostrar_banner():
    print("""
============================================================
  🚀 SISTEMA INTEGRAL DE AUTOMATIZACIÓN MOVISTAR
  Orquestador Principal (ejecutar.py)
============================================================
""")


def verificar_checkpoint_previo() -> bool:
    """
    Verifica si existe una sesión previa interrumpida y ofrece reanudarla.
    Retorna True si el usuario decidió reanudar y se ejecutó la sesión guardada.
    """
    checkpoint = cargar_checkpoint()
    if not checkpoint:
        return False

    print("\n" + "!"*65)
    print("⚠️  SE HA DETECTADO UNA SESIÓN PREVIA INTERRUMPIDA / PAUSADA:")
    print("!"*65)
    print(f"  • Portal:            {checkpoint.get('portal', 'Desconocido')}")
    print(f"  • Script:            {checkpoint.get('script', 'N/A')}")
    print(f"  • Fecha de Pausa:    {checkpoint.get('timestamp', 'N/A')}")
    print(f"  • Progreso:          {checkpoint.get('task_idx', 0)} / {checkpoint.get('total_tasks', 0)} tareas")
    print(f"  • Tareas Pendientes: {checkpoint.get('tareas_restantes', 0)}")
    print(f"  • Motivo de Pausa:   {checkpoint.get('motivo', 'N/A')}")
    if checkpoint.get("ultimo_error"):
        print(f"  • Último Error:      {checkpoint.get('ultimo_error')}")
    print("!"*65)

    opcion = input("\n¿Desea reanudar la ejecución en el punto exacto donde se quedó? (s/n, default=s): ").strip().lower()

    if opcion != "n":
        script_name = checkpoint.get("script", "")
        if "main" in script_name:
            import main as mod_main
            mod_main.main(checkpoint_data=checkpoint)
            return True
        elif "teletrabajo" in script_name:
            import probarteletrabajo as mod_teletrabajo
            mod_teletrabajo.main(checkpoint_data=checkpoint)
            return True
        else:
            print(f"❌ Script desconocido en checkpoint: {script_name}")
            return False
    else:
        descartar = input("¿Desea descartar la sesión guardada y volver al menú principal? (s/n, default=s): ").strip().lower()
        if descartar != "n":
            limpiar_checkpoint()
            print("🗑️ Sesión previa descartada.")
        return False


def menu_principal():
    while True:
        mostrar_banner()

        # Estado de integraciones
        wa_status = "✅ ACTIVO (+{})".format(obtener_numero_destino()) if esta_configurado() else "⚠️ NO CONFIGURADO"
        proxy_info = f"{SUPERPROXY_CONFIG['host']}:{SUPERPROXY_CONFIG['port']} ({SUPERPROXY_CONFIG['country'].upper()})"

        print(f"  [Estado WhatsApp]: {wa_status}")
        print(f"  [Proxy Central]:   {proxy_info}")
        print("-" * 60)
        print("  1. 🔍 Probar Conexión de Proxies (probarproxie.py)")
        print("  2. 📱 Configurar Notificaciones WhatsApp (configurarwhatsapp.py)")
        print("  3. 🏢 Validar Visor Clientes Movistar (main.py)")
        print("  4. 💻 Validar Teletrabajo Movistar (probarteletrabajo.py)")
        print("  5. 🚪 Salir")
        print("=" * 60)

        opcion = input("\nSeleccione una opción [1-5]: ").strip()

        if opcion == "1":
            print("\n" + "="*60)
            print("🔍 EJECUTANDO PRUEBA DE PROXIES...")
            print("="*60)
            import probarproxie
            probarproxie.probar_dos_proxies(headless=True)
            input("\nPresione ENTER para volver al menú...")

        elif opcion == "2":
            print("\n" + "="*60)
            print("📱 CONFIGURACIÓN DE NOTIFICACIONES WHATSAPP...")
            print("="*60)
            import configurarwhatsapp
            configurarwhatsapp.configurar_whatsapp()
            input("\nPresione ENTER para volver al menú...")

        elif opcion == "3":
            print("\n" + "="*60)
            print("🏢 INICIANDO VALIDADOR VISOR CLIENTES MOVISTAR...")
            print("="*60)
            import main as mod_main
            mod_main.main()
            input("\nPresione ENTER para volver al menú...")

        elif opcion == "4":
            print("\n" + "="*60)
            print("💻 INICIANDO VALIDADOR TELETRABAJO MOVISTAR...")
            print("="*60)
            import probarteletrabajo as mod_teletrabajo
            mod_teletrabajo.main()
            input("\nPresione ENTER para volver al menú...")

        elif opcion == "5":
            print("\n👋 ¡Hasta pronto!\n")
            sys.exit(0)

        else:
            print("\n❌ Opción no válida. Ingrese un número del 1 al 5.")
            time.sleep(1)


def main():
    # 1. Comprobar si hay un checkpoint guardado
    reanudado = verificar_checkpoint_previo()
    if reanudado:
        return

    # 2. Si no hay o se descartó, abrir menú principal
    menu_principal()


if __name__ == "__main__":
    main()
