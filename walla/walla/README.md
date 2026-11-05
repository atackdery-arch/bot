# Bot de Telegram para Automatización de Wallapop

Bot de Telegram en Python que automatiza la creación y verificación completa de cuentas en Wallapop utilizando Selenium.

- **En tu PC (Windows)**: Abre Microsoft Edge de forma visible y maximizada para que puedas ver todo en pantalla.
- **En la Nube (Render / Linux)**: Ejecuta Google Chrome en modo Headless con `--no-sandbox` y `--disable-dev-shm-usage` optimizado para contenedores.

---

## 🚀 Despliegue en Render (Cloud 24/7)

El error `Chrome instance exited` en Render ocurre porque Render es un contenedor Linux sin pantalla y necesita Google Chrome instalado con permisos de contenedor (`--no-sandbox`).

Tienes **2 formas** de desplegarlo en Render:

### Opción A (Recomendada y 100% Automática): Desplegar con Docker
1. En Render, crea un nuevo **Background Worker** (o **Web Service**) conectado a tu repositorio de GitHub.
2. En **Environment / Runtime**, selecciona **Docker**.
3. Render detectará automáticamente el archivo [`Dockerfile`](file:///c:/Users/PedroSeoCampello/Desktop/walla/Dockerfile) que ya hemos creado, instalará Google Chrome y arrancará el bot sin que tengas que configurar nada más.

### Opción B: Desplegar con Python Nativo
1. En Render, crea un **Background Worker** seleccionando **Python**.
2. En **Build Command**, pon:
   ```bash
   chmod +x ./render-build.sh && ./render-build.sh
   ```
3. En **Start Command**, pon:
   ```bash
   python bot.py
   ```
4. En **Environment Variables**, añade:
   - `RENDER` = `true`
   - `CHROME_BIN` = `/opt/render/project/.render/chrome/opt/google/chrome/google-chrome`

---

## ▶️ Ejecución en tu Ordenador (Local con Edge visible)

1. Haz doble clic en [`run_bot.bat`](file:///c:/Users/PedroSeoCampello/Desktop/walla/run_bot.bat) (o ejecuta `python bot.py` en tu terminal).
2. Se abrirá Edge en tu pantalla para que veas todas las acciones en tiempo real.

---

## ⚡ Flujo de Automatización

1. **/start**: Presenta al bot y muestra el botón **🆕 New Account**.
2. **Botón "New Account"**:
   - Abre el navegador y accede a `https://es.wallapop.com/auth/onboarding?redirectUrl=%2F`.
   - Clica automáticamente en el botón `<span part="button-text">Regístrate</span>`.
   - Espera al formulario y te pide tu **correo electrónico** por Telegram.
3. **Email y Contraseña**:
   - Escribe el correo en `#email`.
   - Clica y enfoca el campo `#password`, te pide la contraseña por Telegram y la escribe.
4. **Nombre aleatorio y Checkboxes**:
   - Genera un nombre y apellidos español aleatorio y único, lo escribe en `#fullname`.
   - Marca las casillas de condiciones (`#termsAccepted`) y comunicaciones (`#commsAccepted`).
   - Clica el botón de envío **Crear una cuenta** (`#kc-register`).
5. **Verificación de Email (OTP 6 dígitos)**:
   - Detecta el input OTP, te pide el código de 6 dígitos enviado a tu correo, lo rellena y pulsa **Verificar**.
6. **Verificación de Teléfono**:
   - Detecta el campo `<input id="phone_number">`.
   - Te pide tu **teléfono de 9 dígitos** (ej: `682991122`), lo escribe y clica en `<span part="button-text">Enviar código</span>`.
7. **Verificación de SMS (OTP 6 dígitos)**:
   - Te pide el **código de 6 dígitos recibido por SMS**, lo rellena y pulsa **Verificar**.
   - Te envía el **resumen final completo con toda la información**.
