# Bot de Telegram para Contratación Automática de eSIMs Simyo

Bot de Telegram desarrollado en Python con `python-telegram-bot` y `Selenium` (Microsoft Edge) para automatizar el proceso de solicitud de eSIMs prepago con número nuevo en [Simyo](https://www.simyo.es/tarifas-movil.html).

## 🚀 Características y Flujo del Bot

1. **Comando `/start`**:
   - Envía un mensaje resumido explicando lo que hace el bot.
   - Presenta un único botón inline: `🚀 Empezar`.
2. **Solicitud de Datos Iniciales**:
   - Pide un **correo electrónico** y un **número de teléfono móvil español** (9 dígitos).
   - Pregunta con botones `Sí` y `No` si se desean guardar para próximas veces (almacenamiento en `users_data.json`).
3. **Datos Personales y Configuración**:
   - Solicita número de **DNI o NIE**.
   - Solicita el **nombre completo**, aplicando la regla de separación:
     - 4 palabras: Las 2 primeras son el Nombre, la 3ª el Apellido 1 y la 4ª el Apellido 2 (ej: *Ana Maria Ramos Castillon* -> Nombre: *Ana Maria*, Apellido 1: *Ramos*, Apellido 2: *Castillon*).
     - 3 palabras: La 1ª es el Nombre, la 2ª el Apellido 1 y la 3ª el Apellido 2 (ej: *Ana Romero Mendoza* -> Nombre: *Ana*, Apellido 1: *Romero*, Apellido 2: *Mendoza*).
     - 2 palabras: La 1ª es el Nombre y la 2ª el Apellido 1.
   - Solicita la **fecha de nacimiento** (`DD/MM/AAAA`).
   - Pregunta la **cantidad de eSIMs** deseadas (máximo 3) mediante botones interactivos `[ 1 eSIM ]`, `[ 2 eSIMs ]`, `[ 3 eSIMs ]`.
4. **Automatización con Selenium Edge**:
   - Abre Microsoft Edge y accede a `https://www.simyo.es/tarifas-movil.html`.
   - Clica en `Comprar ya` (`a.js-buyNow`).
   - En la ventana emergente de "¿Eres cliente?", clica en el botón `No` (`notUserFixedSubmit()`).
   - Ajusta la cantidad de líneas con el botón `+` (`js-counter-add`) según el número de eSIMs solicitado.
   - Clica en `Tramitar pedido` (`button.js-order-cart`).
   - Selecciona **Prepago**, **Número nuevo** y **eSIM**.
   - Clica en `Continuar` (`#nextButton`).
   - Gestiona y cierra el popup informativo de seguridad de eSIM (`#popupEsimDeterrentMessage`).
   - Rellena el formulario con:
     - Tipo de documento: `DNI` (código `02`).
     - Documento: DNI/NIE recibido.
     - Espera 3 segundos.
     - Nombre, Primer Apellido y Segundo Apellido.
     - Correo electrónico y Confirmación de correo.
     - Teléfono de contacto (9 dígitos sin +34).
     - Fecha de nacimiento (Día, Mes indexado 0-11, Año).
     - Dirección: `Avenida Fuente Nueva, San Sebastián de los Reyes, España` seleccionando la primera opción de Google Places.
     - Checkbox `sinNumero`.
     - Genera contraseña segura y la confirma en `Repite Clave`.
     - Activa los switches (`<div class="overlay"></div>`) hasta posicionar en `<span class="switched" style="left: 0px;"></span>`.
     - Clica en el botón final `Continuar` (`#nextButton`).
   - Envía actualizaciones en tiempo real y la captura de pantalla final de confirmación a través de Telegram.

## 📁 Estructura del Proyecto

- `bot.py`: Código principal del bot de Telegram y gestión de estados de conversación.
- `selenium_worker.py`: Módulo de automatización con Selenium y Microsoft Edge.
- `name_parser.py`: Lógica de separación de nombres y apellidos según las especificaciones.
- `storage.py`: Persistencia de usuarios para recordar correo y teléfono.
- `config.py`: Token de Telegram, binarios de Edge y configuraciones.
- `start_bot.bat`: Script de Windows para iniciar el bot con un clic.
- `requirements.txt`: Dependencias del proyecto.

## ⚙️ Cómo Ejecutar

1. Abre una terminal en esta carpeta o haz doble clic en `start_bot.bat`.
2. O ejecuta en la consola:
   ```bash
   python bot.py
   ```
3. Ve a Telegram y busca el bot `@simyospbot`. Escribe `/start` y ¡listo!
