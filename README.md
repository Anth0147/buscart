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
