<<<<<<< HEAD
# Sistema de Automatización y Validación de Accesos Movistar

Sistema modular y concurrente para la validación de credenciales en portales de Movistar (**Visor Clientes** y **Teletrabajo**), integrado con proxies rotativos residenciales de Perú, resolución local automática de captchas, sistema de auto-recuperación ante interrupciones (Checkpoints) y notificaciones en tiempo real por WhatsApp.

---

## 🚀 Inicio Rápido

Para iniciar el sistema completo y acceder al menú interactivo:

```bash
python ejecutar.py
```

---

## 📋 Requisitos e Instalación

### 1. Requisitos Previos
- **Python 3.10** o superior instalado en el sistema.
- Navegador Google Chrome instalado.

### 2. Instalación de Dependencias

1. Clonar el repositorio o descargar el proyecto:
   ```bash
   git clone <URL_DEL_REPOSITORIO>
   cd buscart
   ```

2. Instalar los paquetes requeridos:
   ```bash
   pip install -r requirements.txt
   ```

3. Instalar los binarios del navegador para Playwright:
   ```bash
   playwright install chromium
   ```

---

## 🎛️ Menú del Orquestador (`ejecutar.py`)

Al ejecutar `python ejecutar.py`, tendrás acceso a las siguientes opciones:

```text
============================================================
  🚀 SISTEMA INTEGRAL DE AUTOMATIZACIÓN MOVISTAR
  Orquestador Principal (ejecutar.py)
============================================================
  1. 🔍 Probar Conexión de Proxies (probarproxie.py)
  2. 📱 Configurar Notificaciones WhatsApp (configurarwhatsapp.py)
  3. 🏢 Validar Visor Clientes Movistar (main.py)
  4. 💻 Validar Teletrabajo Movistar (probarteletrabajo.py)
  5. 🚪 Salir
============================================================
```

---

## 📂 Descripción de Módulos y Funcionalidades

### 1. `probarproxie.py` — Validación de Proxies
- Prueba la conexión HTTP básica y la navegación directa contra los portales de Movistar.
- Utiliza la configuración centralizada de [`proxy_config.py`](file:///c:/Users/marco/OneDrive/proyectos/buscart/proxy_config.py) (SuperProxy con IPs rotativas residenciales de Perú).
- Evalúa el estado del WAF, tiempos de respuesta y carga de elementos interactivos.

### 2. `configurarwhatsapp.py` — Gestión de WhatsApp
- Permite vincular tu cuenta de WhatsApp Web escaneando un código QR interactivo.
- Almacena la sesión persistente en `datawp/whatsapp_session/` para que los envíos automáticos no requieran volver a escanear.
- Incluye opciones para **enviar mensajes de prueba** y actualizar el número de teléfono receptor.

### 3. `main.py` — Validador Visor Clientes Movistar
- Automatiza el flujo de autenticación en `https://visorclientes.movistar.com.pe/login` con formularios OAuth (Azure AD B2C).
- **Selección de Procedencia:** Permite elegir entre *Usuario Interno*, *Usuario Externo* o *Ambos*.
- **Orden de Iteración:**
  ```text
  Procedencia (C) ➔ Contraseña (B) ➔ Usuario (A)
  ```
  Prueba cada contraseña en todos los usuarios antes de rotar a la siguiente clave.
- **Resolución de Captcha Local:** Resuelve automáticamente los captchas numéricos de 4 dígitos en ~0.05 segundos de forma offline con `ddddocr`.
- **Detección Inmediata:** Monitorea en tiempo real la aparición del buscador del portal para declarar el éxito de inmediato sin esperas innecesarias.

### 4. `probarteletrabajo.py` — Validador Teletrabajo Movistar
- Automatiza la validación masiva en el portal `https://teletrabajo.movistar.pe`.
- Soporte para ejecución multi-hilo, modo headless o visual, y tiempo de espera entre rondas de contraseñas.
- Detección precisa de respuestas exitosas, credenciales inválidas y bloqueos WAF.

---

## 💾 Sistema de Checkpoints y Auto-Recuperación (`state_manager.py`)

Si la ejecución se detiene por interrupción manual (`Ctrl+C`) o por **detección de un error crítico**:
- Se guardan en memoria todas las tareas pendientes, estadísticas y configuraciones en `data/estado_ejecucion.json`.
- Al volver a ejecutar `python ejecutar.py`, el orquestador detectará la sesión y te preguntará:
  ```text
  ¿Desea reanudar la ejecución en el punto exacto donde se quedó? (s/n, default=s):
  ```

---

## 📲 Notificaciones en Tiempo Real (`whatsapp_notifier.py`)

El sistema envía alertas automáticas a tu número de WhatsApp para los siguientes eventos:

1. **Login Exitoso:** Envía credenciales confirmadas, portal, procedencia, IP y captura de pantalla de evidencia.
2. **Resumen de Ejecución:** Envía estadísticas totales (probadas, exitosas, fallidas y duración).
3. **Alerta de Error Crítico:** Se dispara y pausa la ejecución si ocurren:
   - 🚨 2 Bloqueos WAF consecutivos.
   - 🚨 2 Pantallas en blanco consecutivas.
   - 🚨 2 Timeouts o demoras excesivas consecutivas.

---

## 📁 Estructura de Archivos y Carpetas

```text
buscart/
├── ejecutar.py                 # Orquestador principal
├── main.py                     # Validador Visor Clientes Movistar
├── probarteletrabajo.py        # Validador Teletrabajo Movistar
├── probarproxie.py             # Probador de conectividad de proxies
├── configurarwhatsapp.py       # Gestor y vinculador QR de WhatsApp
├── whatsapp_notifier.py        # Módulo de envío de notificaciones WhatsApp
├── proxy_config.py             # Configuración centralizada de SuperProxy
├── state_manager.py            # Gestor de checkpoints y memoria de estado
├── captcha_resolver.py         # Resolvedor local de captchas numéricos
├── login_automation.py         # Motor de navegación para Visor Clientes
├── requirements.txt            # Dependencias de Python
├── data/
│   ├── usuarios.csv            # Lista de usuarios a probar
│   ├── contraseñas.csv         # Lista de contraseñas a probar
│   ├── login_correcto.csv      # Log de logins exitosos
│   └── login_incorrecto.csv    # Log de intentos fallidos
└── datawp/
    ├── whatsapp_config.json    # Configuración de número destino
    └── whatsapp_session/       # Sesión persistente de WhatsApp Web
```
=======
# Ejecución

Para ejecutar:
```bash
python ejecutar.py
```
>>>>>>> 896283b8ed693c96dfe6c769ed049a4dc051282d
