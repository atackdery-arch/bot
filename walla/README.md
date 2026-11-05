# Bot de Telegram para Automatización de Wallapop

Bot de Telegram en Python que automatiza la creación y verificación completa de cuentas en Wallapop utilizando Microsoft Edge y Selenium de forma visible.

## 🚀 Flujo Completo

1. **/start**:
   - Presenta al bot, explica qué hace y muestra el botón **🆕 New Account**.
2. **Botón "New Account"**:
   - Abre **Microsoft Edge** visible y maximizado.
   - Accede a `https://es.wallapop.com/auth/onboarding?redirectUrl=%2F`.
   - Clica automáticamente en el botón `<span part="button-text">Regístrate</span>`.
   - Espera a que cargue el formulario y solicita al usuario por Telegram su **correo electrónico**.
3. **Flujo de Formulario**:
   - Escribe el correo electrónico introducido en el input `<input id="email">`.
   - Clica y enfoca el input de contraseña `<input id="password">`, y solicita la **contraseña** en Telegram.
   - Escribe la contraseña introducida.
   - Clica en el input de **Nombre y apellidos** `<input id="fullname">` e inserta un nombre y apellidos realista generado aleatoriamente (siempre único).
   - Marca la casilla de **Condiciones de uso y política de privacidad** (`#termsAccepted`).
   - Marca la casilla de **Comunicaciones comerciales** (`#commsAccepted`).
   - Clica el botón de envío **Crear una cuenta** (`#kc-register`).
4. **Verificación de Email (OTP 6 dígitos)**:
   - Detecta la pantalla de código OTP (`input[data-input-otp="true"]`).
   - Pide en Telegram el **código de 6 dígitos** recibido por correo.
   - Escribe los 6 dígitos en el input OTP y pulsa **Verificar**.
5. **Verificación de Teléfono**:
   - Detecta el campo `<input id="phone_number">`.
   - Pide en Telegram el **número de teléfono de 9 dígitos** (ej: `682991122`, sin +34).
   - Escribe el número y clica el botón `<span part="button-text">Enviar código</span>`.
6. **Verificación de SMS (OTP 6 dígitos)**:
   - Pide en Telegram el **código de 6 dígitos recibido por SMS**.
   - Escribe el código en el input OTP y pulsa **Verificar**.
   - Envía por Telegram el **resumen final completo con toda la información generada y verificada** (Nombre y apellidos, Email, Contraseña, Teléfono, Códigos).
7. **/cancel**:
   - Cancela la operación en curso y cierra el navegador Edge.

## 🛡️ Prevención de Conflictos (Anti-Lag / Single-Instance)

El bot implementa un bloqueo de instancia única por socket (`127.0.0.1:47891`). Si intentas abrir el bot dos veces por error, la segunda ventana se cerrará automáticamente para evitar errores 409 de conflicto en Telegram ("se bugea").

## ▶️ Cómo Ejecutarlo

1. **Haciendo doble clic** en `run_bot.bat`.
2. O desde la terminal en esta carpeta:
```bash
python bot.py
```
