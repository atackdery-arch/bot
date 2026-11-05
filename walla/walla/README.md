# Bot de Telegram para Automatización de Wallapop (Chromium Headless)

Bot de Telegram desarrollado en Python para automatizar el registro y verificación de cuentas en Wallapop, optimizado para ejecutarse en la nube en **Render** como **Background Worker** utilizando **Chromium** en modo sin interfaz gráfica (**Headless**).

---

## 🛠️ Los 4 Cambios Implementados

### 1. Sustituir Microsoft Edge por Chromium
- Se ha eliminado toda dependencia de Edge.
- El bot ahora utiliza **Chromium / Chrome** mediante `webdriver.Chrome()`.

### 2. Instalar Chromium y ChromeDriver en Render
- **Dockerfile optimizado:** Instala `chromium` y `chromium-driver` oficiales de Linux en el contenedor.
- **Rutas configuradas:** El bot detecta automáticamente `/usr/bin/chromium` y `/usr/bin/chromedriver`.

### 3. Configurar Selenium sin Interfaz Gráfica (Headless)
- Opciones configuradas en `bot.py`:
  - `--headless=new` (ejecución sin interfaz gráfica)
  - `--no-sandbox` (obligatorio para contenedores Docker/Render)
  - `--disable-dev-shm-usage` (evita problemas de memoria compartida en Render)
  - `--disable-gpu`
  - `--disable-blink-features=AutomationControlled` (anti-detección)
  - User-Agent realista para evitar bloqueos 403 de CloudFront.

### 4. Mantener el Bot como Background Worker en Render
- Diseñado para funcionar 24/7 procesando las solicitudes de Telegram.
- Se incluye [`render.yaml`](file:///c:/Users/PedroSeoCampello/Desktop/walla/render.yaml) y [`Dockerfile`](file:///c:/Users/PedroSeoCampello/Desktop/walla/Dockerfile).

---

## 🚀 Cómo Desplegar en Render (Paso a Paso)

### Paso 1: Subir los cambios a tu repositorio de GitHub
Para que Render actualice el código y no siga ejecutando el antiguo, abre una terminal en esta carpeta y haz:
```bash
git add .
git commit -m "Cambio a Chromium Headless para Render"
git push origin main
```

### Paso 2: Configurar en Render
En tu panel de [Render Dashboard](https://dashboard.render.com):

1. **Si creas un servicio nuevo:**
   - Pulsa **New +** -> **Background Worker**.
   - Conecta tu repositorio de GitHub.
   - En **Environment / Runtime**, selecciona **Docker**.
   - ¡Listo! Render leerá el `Dockerfile`, instalará Chromium y ChromeDriver automáticamente y pondrá el bot en marcha.

2. **Si ya tienes un Background Worker existente creado:**
   - Ve a la pestaña **Settings** de tu servicio.
   - En **Environment**, si tienes seleccionado **Docker**, simplemente haz clic en **Manual Deploy** -> **Clear build cache & deploy**.
   - Si tu servicio es de tipo **Python**:
     - En **Build Command**: `chmod +x ./render-build.sh && ./render-build.sh`
     - En **Start Command**: `python bot.py`
     - En **Environment Variables**:
       - `RENDER` = `true`
       - `CHROME_BIN` = `/opt/render/project/.render/chrome/opt/google/chrome/google-chrome`
     - Pulsa **Save Changes** y luego **Manual Deploy** -> **Clear build cache & deploy**.
