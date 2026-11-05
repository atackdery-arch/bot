import asyncio
import logging
import os
import random
import re
import socket
import sys
import time
from typing import Dict, Any

# Asegurar compatibilidad de consola en Windows con UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ==========================================
# CONFIGURACIÓN Y CONSTANTES
# ==========================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8651428976:AAEoES1Hi_quOJ_Fmd1cxmlJzSpybiBGldw")

WALLAPOP_ONBOARDING_URL = "https://es.wallapop.com/auth/onboarding?redirectUrl=%2F"

# Nombres y apellidos españoles para generación aleatoria y realista
NOMBRES = [
    "Alejandro", "Mateo", "Lucas", "Santiago", "Daniel", "Hugo", "Álvaro", "Adrián",
    "David", "Pablo", "Diego", "Javier", "Mario", "Manuel", "Marcos", "Sergio",
    "Carlos", "Iván", "Gonzalo", "Rubén", "Bruno", "Jorge", "Darío", "Ángel",
    "Miguel", "Antonio", "Fernando", "Pedro", "Raúl", "Víctor", "Alberto", "Guillermo",
    "Lucía", "Sofía", "Martina", "María", "Paula", "Julia", "Emma", "Valeria",
    "Daniela", "Alba", "Sara", "Carla", "Claudia", "Noa", "Vega", "Carmen",
    "Elena", "Irene", "Marta", "Laura", "Aitana", "Celia", "Alicia", "Rocío",
    "Clara", "Patricia", "Cristina", "Beatriz", "Silvia", "Natalia", "Marina", "Andrea",
    "Nuria", "Lorena", "Miriam", "Mónica", "Esther", "Yolanda", "Tamara", "Inés"
]

APELLIDOS = [
    "García", "Rodríguez", "González", "Fernández", "López", "Martínez", "Sánchez", "Pérez",
    "Gómez", "Martín", "Jiménez", "Ruiz", "Hernández", "Díaz", "Moreno", "Muñoz",
    "Álvarez", "Romero", "Alonso", "Gutiérrez", "Navarro", "Torres", "Domínguez", "Vázquez",
    "Ramos", "Gil", "Ramírez", "Serrano", "Blanco", "Molina", "Morales", "Suárez",
    "Ortega", "Delgado", "Castro", "Ortiz", "Rubio", "Marín", "Sanz", "Núñez",
    "Iglesias", "Medina", "Garrido", "Santos", "Castillo", "Cortés", "Lozano", "Guerrero",
    "Cano", "Prieto", "Méndez", "Calvo", "Cruz", "Gallego", "Herrera", "Márquez",
    "Peña", "Vidal", "León", "Cabrera", "Flores", "Campos", "Vega", "Fuentes",
    "Carrasco", "Diez", "Caballero", "Reyes", "Nieto", "Aguilar", "Pascual", "Santana"
]

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Almacenamiento de sesiones en memoria por chat_id
user_sessions: Dict[int, Dict[str, Any]] = {}
lock_socket = None

IS_CLOUD = os.environ.get("RENDER") is not None or sys.platform.startswith("linux")


def check_single_instance():
    """Garantiza que sólo una instancia del bot se ejecute en local."""
    if IS_CLOUD:
        return
    global lock_socket
    try:
        lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lock_socket.bind(("127.0.0.1", 47891))
    except socket.error:
        print("\n=======================================================")
        print("⚠️ AVISO: Ya hay otra instancia de bot.py ejecutándose.")
        print("Para evitar que Telegram se bugee por conflicto de sesiones,")
        print("esta nueva instancia se cerrará automáticamente.")
        print("=======================================================\n")
        sys.exit(0)


def generate_random_fullname() -> str:
    """Genera un nombre y dos apellidos aleatorios y siempre diferentes."""
    nombre = random.choice(NOMBRES)
    apellido1 = random.choice(APELLIDOS)
    apellido2 = random.choice(APELLIDOS)
    while apellido2 == apellido1:
        apellido2 = random.choice(APELLIDOS)
    return f"{nombre} {apellido1} {apellido2}"


def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("🆕 New Account", callback_data="new_account")]
    ]
    return InlineKeyboardMarkup(keyboard)


# ==========================================
# CONFIGURACIÓN DE CHROMIUM / CHROMEDRIVER (HEADLESS)
# ==========================================
def get_chromium_driver():
    """Inicia Chromium en modo Headless (sin interfaz gráfica) adaptado para Render Linux y entornos cloud."""
    options = webdriver.ChromeOptions()
    
    # 1. Configuración Headless y Contenedores Linux
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--remote-debugging-port=9222")

    # 2. Opciones Anti-Detección
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument(
        "user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )

    # 3. Detección de binario de Chromium en Render o Linux
    chromium_bin_paths = [
        os.environ.get("CHROME_BIN", ""),
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/opt/render/project/.render/chrome/opt/google/chrome/google-chrome",
    ]
    for bin_path in chromium_bin_paths:
        if bin_path and os.path.exists(bin_path):
            options.binary_location = bin_path
            logger.info(f"Binario de Chromium localizado en: {bin_path}")
            break

    # 4. Detección de ChromeDriver en el sistema
    driver_paths = [
        "/usr/bin/chromedriver",
        "/usr/lib/chromium/chromedriver",
        "/usr/lib/chromium-browser/chromedriver",
    ]
    service = None
    for d_path in driver_paths:
        if os.path.exists(d_path):
            service = Service(executable_path=d_path)
            logger.info(f"ChromeDriver localizado en: {d_path}")
            break

    if service:
        driver = webdriver.Chrome(service=service, options=options)
    else:
        driver = webdriver.Chrome(options=options)

    # Inyección de scripts para enmascarar navegación headless
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                window.navigator.chrome = {
                    runtime: {},
                };
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['es-ES', 'es', 'en-US', 'en'],
                });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                });
            """
        })
    except Exception as e:
        logger.warning(f"No se pudo inyectar script CDP: {e}")

    return driver


def open_and_navigate_to_onboarding(url: str):
    """Inicia Chromium Headless y pulsa en Regístrate."""
    driver = get_chromium_driver()
    driver.get(url)

    # 1. Esperar al botón de 'Regístrate'
    wait = WebDriverWait(driver, 25)
    reg_btn = wait.until(
        lambda d: d.find_element(
            By.CSS_SELECTOR,
            "walla-button[text*='Regístrate'], walla-button[text*='Registrate'], walla-button[button-type='link']"
        )
    )
    time.sleep(1)

    # 2. Clicar en <span part="button-text">Regístrate</span> dentro del shadowRoot o botón
    clicked = False
    try:
        btn_inside = driver.execute_script(
            "return arguments[0].shadowRoot ? arguments[0].shadowRoot.querySelector('button, [part=\"button-text\"]') : null;",
            reg_btn,
        )
        if btn_inside:
            driver.execute_script("arguments[0].click();", btn_inside)
            clicked = True
            logger.info("Clic en shadow button 'Regístrate' realizado con éxito.")
    except Exception as e:
        logger.warning(f"Error clicando elemento shadow de Regístrate: {e}")

    if not clicked:
        driver.execute_script("arguments[0].click();", reg_btn)
        logger.info("Clic directo en walla-button 'Regístrate' realizado.")

    # 3. Esperar a que cargue la página con el input de email
    WebDriverWait(driver, 25).until(EC.presence_of_element_located((By.ID, "email")))
    time.sleep(1)
    return driver


def safe_click_and_type(driver, element_id: str, text: str = None):
    """Hace clic de forma segura en un input (evitando intercepciones de label) y opcionalmente escribe texto."""
    el = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, element_id)))
    driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});", el)
    time.sleep(0.3)
    try:
        el.click()
    except Exception:
        try:
            label = driver.find_element(By.CSS_SELECTOR, f"label[for='{element_id}']")
            label.click()
        except Exception:
            driver.execute_script("arguments[0].click();", el)
    driver.execute_script("arguments[0].focus();", el)
    if text is not None:
        el.clear()
        el.send_keys(text)
    return el


def safe_check_checkbox(driver, element_id: str):
    """Marca un checkbox si no está seleccionado."""
    el = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, element_id)))
    driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});", el)
    time.sleep(0.3)
    if not el.is_selected():
        try:
            el.click()
        except Exception:
            try:
                driver.find_element(By.CSS_SELECTOR, f"label[for='{element_id}']").click()
            except Exception:
                driver.execute_script("arguments[0].click();", el)
    return el.is_selected()


def click_submit_button(driver):
    """Localiza y pulsa el botón de 'Crear una cuenta' de Wallapop."""
    try:
        reg_btn = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, "kc-register"))
        )
        driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});", reg_btn)
        time.sleep(0.5)
        btn_inside = driver.execute_script(
            "return arguments[0].shadowRoot ? arguments[0].shadowRoot.querySelector('button') : null;",
            reg_btn,
        )
        if btn_inside:
            try:
                btn_inside.click()
            except Exception:
                driver.execute_script("arguments[0].click();", btn_inside)
        else:
            try:
                reg_btn.click()
            except Exception:
                driver.execute_script("arguments[0].click();", reg_btn)
    except Exception as e:
        logger.warning(f"Error pulsando #kc-register, intentando fallback CSS: {e}")
        submit_btn = driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]')
        driver.execute_script("arguments[0].click();", submit_btn)


def wait_for_otp_screen(driver):
    """Espera a que aparezca la pantalla/input del código de verificación OTP."""
    wait = WebDriverWait(driver, 25)
    return wait.until(
        lambda d: d.find_element(
            By.CSS_SELECTOR,
            "input[data-input-otp='true'], input[autocomplete='one-time-code'], input#_r_0_, input[inputmode='numeric'][maxlength='6']"
        )
    )


def fill_otp_and_verify(driver, code: str):
    """Rellena el código de verificación de 6 dígitos y pulsa el botón Verificar."""
    wait = WebDriverWait(driver, 20)
    otp_input = wait.until(
        lambda d: d.find_element(
            By.CSS_SELECTOR,
            "input[data-input-otp='true'], input[autocomplete='one-time-code'], input#_r_0_, input[inputmode='numeric'][maxlength='6']"
        )
    )
    driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});", otp_input)
    time.sleep(0.3)

    try:
        otp_input.click()
    except Exception:
        driver.execute_script("arguments[0].click();", otp_input)
    driver.execute_script("arguments[0].focus();", otp_input)
    time.sleep(0.2)

    otp_input.clear()
    for char in code:
        otp_input.send_keys(char)
        time.sleep(0.05)

    driver.execute_script("""
        const input = arguments[0];
        const val = arguments[1];
        try {
            const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            nativeSetter.call(input, val);
        } catch(e) {}
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
    """, otp_input, code)

    time.sleep(0.8)
    click_verificar_button(driver)
    time.sleep(3)


def click_verificar_button(driver):
    """Localiza y pulsa el botón 'Verificar'."""
    wait = WebDriverWait(driver, 15)
    try:
        wb = wait.until(
            lambda d: d.find_element(
                By.CSS_SELECTOR,
                "walla-button[text*='Verificar'], walla-button[text*='verificar']"
            )
        )
        driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});", wb)
        time.sleep(0.3)
        btn_inside = driver.execute_script(
            "return arguments[0].shadowRoot ? arguments[0].shadowRoot.querySelector('button') : null;",
            wb
        )
        if btn_inside:
            try:
                btn_inside.click()
            except Exception:
                driver.execute_script("arguments[0].click();", btn_inside)
        else:
            try:
                wb.click()
            except Exception:
                driver.execute_script("arguments[0].click();", wb)
        logger.info("Botón Verificar clicado exitosamente.")
        return
    except Exception as e:
        logger.warning(f"No se localizó walla-button Verificar directamente: {e}")

    try:
        btn = driver.find_element(
            By.XPATH,
            "//button[contains(., 'Verificar')] | //*[@part='button'][contains(., 'Verificar')] | //button[@type='submit']"
        )
        driver.execute_script("arguments[0].click();", btn)
        logger.info("Botón Verificar clicado por XPath.")
    except Exception as e:
        logger.error(f"Error clicando botón Verificar: {e}")


def wait_for_phone_screen(driver):
    """Espera a que aparezca la pantalla del número de teléfono."""
    wait = WebDriverWait(driver, 25)
    return wait.until(
        lambda d: d.find_element(
            By.CSS_SELECTOR,
            "#phone_number, input[name='phone_number'], label[for='phone_number']"
        )
    )


def click_enviar_codigo_button(driver):
    """Localiza y pulsa el botón 'Enviar código'."""
    wait = WebDriverWait(driver, 15)
    try:
        wb = wait.until(
            lambda d: d.find_element(
                By.CSS_SELECTOR,
                "walla-button[text*='Enviar código'], walla-button[text*='Enviar codigo'], walla-button[text*='Enviar']"
            )
        )
        driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});", wb)
        time.sleep(0.3)
        btn_inside = driver.execute_script(
            "return arguments[0].shadowRoot ? arguments[0].shadowRoot.querySelector('button, [part=\"button-text\"]') : null;",
            wb
        )
        if btn_inside:
            try:
                btn_inside.click()
            except Exception:
                driver.execute_script("arguments[0].click();", btn_inside)
        else:
            try:
                wb.click()
            except Exception:
                driver.execute_script("arguments[0].click();", wb)
        logger.info("Botón Enviar código clicado.")
        return
    except Exception as e:
        logger.warning(f"walla-button Enviar código no encontrado directamente: {e}")

    try:
        btn = driver.find_element(
            By.XPATH,
            "//button[contains(., 'Enviar código') or contains(., 'Enviar codigo')] | //*[contains(text(), 'Enviar código')] | //button[@type='submit']"
        )
        driver.execute_script("arguments[0].click();", btn)
        logger.info("Botón Enviar código clicado por XPath.")
    except Exception as e:
        logger.error(f"Error clicando botón Enviar código: {e}")


def write_phone_and_send_code(driver, phone_str: str):
    """Escribe el teléfono en el input phone_number, pulsa Enviar código y espera al OTP."""
    safe_click_and_type(driver, "phone_number", phone_str)
    time.sleep(0.5)
    click_enviar_codigo_button(driver)
    time.sleep(2)
    wait_for_otp_screen(driver)


def cleanup_session_driver(chat_id: int):
    """Cierra el driver de Chromium si existe para este usuario."""
    session = user_sessions.get(chat_id)
    if session and "driver" in session and session["driver"]:
        try:
            session["driver"].quit()
        except Exception as e:
            logger.warning(f"Error cerrando driver para chat {chat_id}: {e}")
        session["driver"] = None


# ==========================================
# HANDLERS DE TELEGRAM
# ==========================================
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start: explica el bot y ofrece el botón New Account."""
    chat_id = update.effective_chat.id
    cleanup_session_driver(chat_id)
    user_sessions[chat_id] = {"state": "IDLE"}

    welcome_text = (
        "🤖 **¡Bienvenido al Bot de Registro de Wallapop!**\n\n"
        "Este bot automatiza la creación y verificación de cuentas en Wallapop mediante "
        "Chromium sin interfaz gráfica (Headless).\n\n"
        "⚡ **Flujo completo del proceso:**\n"
        "1️⃣ Pulsa el botón **New Account**.\n"
        "2️⃣ Se iniciará Chromium y accederá a Wallapop.\n"
        "3️⃣ Clicará automáticamente en **Regístrate**.\n"
        "4️⃣ Te pide tu **correo electrónico** y lo escribe en el formulario.\n"
        "5️⃣ Te pide tu **contraseña** y la escribe en su campo.\n"
        "6️⃣ Genera automáticamente un **nombre y apellidos** realista y aleatorio.\n"
        "7️⃣ Acepta **términos de uso** y **comunicaciones comerciales**.\n"
        "8️⃣ Pulsa el botón **Crear una cuenta**.\n"
        "9️⃣ Te pide el **código de verificación por email (6 dígitos)** y pulsa **Verificar**.\n"
        "🔟 Te pide tu **número de teléfono (9 dígitos)**, lo introduce y pulsa **Enviar código**.\n"
        "1️⃣1️⃣ Te pide el **código de verificación por SMS (6 dígitos)** y pulsa **Verificar**.\n"
        "1️⃣2️⃣ Te envía el **resumen final completo con todos los datos de la cuenta**.\n\n"
        "👇 *Para empezar, haz clic en el siguiente botón:*"
    )

    await update.message.reply_text(
        welcome_text,
        reply_markup=get_main_keyboard(),
        parse_mode=ParseMode.MARKDOWN,
    )


async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /cancel: cancela la operación y cierra Chromium si está abierto."""
    chat_id = update.effective_chat.id
    cleanup_session_driver(chat_id)
    user_sessions[chat_id] = {"state": "IDLE"}
    await update.message.reply_text(
        "🛑 Proceso cancelado y navegador cerrado.\n"
        "Cuando quieras volver a empezar, pulsa el botón:",
        reply_markup=get_main_keyboard(),
    )


async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el clic en el botón 'New Account'."""
    query = update.callback_query
    await query.answer()

    if query.data != "new_account":
        return

    chat_id = update.effective_chat.id

    existing_session = user_sessions.get(chat_id, {})
    if existing_session.get("state") not in ["IDLE", None] and existing_session.get("driver"):
        await query.message.reply_text(
            "⚠️ Ya tienes una sesión de registro activa.\n"
            "Si deseas reiniciar desde cero, envía /cancel.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    cleanup_session_driver(chat_id)

    user_sessions[chat_id] = {
        "state": "OPENING_BROWSER",
        "driver": None,
        "email": None,
        "password": None,
        "fullname": None,
        "email_code": None,
        "phone": None,
        "phone_code": None,
    }

    status_msg = await query.message.reply_text(
        "🚀 **Iniciando Chromium en segundo plano...**\n"
        "Accediendo a Wallapop Onboarding y pulsando en **Regístrate**, por favor espera unos segundos...",
        parse_mode=ParseMode.MARKDOWN,
    )

    try:
        driver = await asyncio.to_thread(open_and_navigate_to_onboarding, WALLAPOP_ONBOARDING_URL)
        user_sessions[chat_id]["driver"] = driver
        user_sessions[chat_id]["state"] = "WAITING_EMAIL"

        await status_msg.edit_text(
            "🌐 **¡Página de registro lista en Chromium!**\n\n"
            "📧 Por favor, **escribe el correo electrónico** que deseas usar para esta cuenta:",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        logger.error(f"Error al iniciar Chromium: {e}", exc_info=True)
        cleanup_session_driver(chat_id)
        user_sessions[chat_id] = {"state": "IDLE"}
        await status_msg.edit_text(
            f"❌ *Error al iniciar Chromium o cargar la página:*\n`{str(e)}`\n\n"
            "Por favor, inténtalo de nuevo pulsando el botón:",
            reply_markup=get_main_keyboard(),
            parse_mode=ParseMode.MARKDOWN,
        )


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja los mensajes de texto según el estado de la sesión."""
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    session = user_sessions.get(chat_id, {})
    state = session.get("state", "IDLE")
    driver = session.get("driver")

    # ----------------------------------------------------
    # 1. ESTADO: ESPERANDO EMAIL
    # ----------------------------------------------------
    if state == "WAITING_EMAIL":
        if not driver:
            await update.message.reply_text(
                "⚠️ No hay ninguna sesión activa. Pulsa el botón para iniciar:",
                reply_markup=get_main_keyboard(),
            )
            return

        session["email"] = text
        session["state"] = "PROCESSING_EMAIL"
        status_msg = await update.message.reply_text(
            f"✍️ Escribiendo correo `{text}` en Wallapop y seleccionando campo de contraseña...",
            parse_mode=ParseMode.MARKDOWN,
        )

        try:
            def write_email_and_focus_pwd(drv, email_val):
                safe_click_and_type(drv, "email", email_val)
                safe_click_and_type(drv, "password")

            await asyncio.to_thread(write_email_and_focus_pwd, driver, text)

            session["state"] = "WAITING_PASSWORD"
            await status_msg.edit_text(
                "✅ Correo introducido correctamente.\n"
                "👉 El campo de **contraseña** ya está enfocado.\n\n"
                "🔒 Ahora, **escribe la contraseña** que deseas para la cuenta:",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            logger.error(f"Error escribiendo email: {e}", exc_info=True)
            await status_msg.edit_text(
                f"❌ Error al interactuar con el formulario: `{str(e)}`",
                parse_mode=ParseMode.MARKDOWN,
            )

    # ----------------------------------------------------
    # 2. ESTADO: ESPERANDO CONTRASEÑA
    # ----------------------------------------------------
    elif state == "WAITING_PASSWORD":
        if not driver:
            await update.message.reply_text(
                "⚠️ No hay ninguna sesión activa. Pulsa el botón para iniciar:",
                reply_markup=get_main_keyboard(),
            )
            return

        session["password"] = text
        session["state"] = "PROCESSING_FORM"
        fullname = generate_random_fullname()
        session["fullname"] = fullname

        status_msg = await update.message.reply_text(
            "⚙️ **Completando formulario y enviando registro...**\n"
            "• Escribiendo contraseña...\n"
            f"• Generando y escribiendo nombre: `{fullname}`...\n"
            "• Aceptando términos y condiciones...\n"
            "• Aceptando comunicaciones comerciales...\n"
            "• Pulsando 'Crear una cuenta'...",
            parse_mode=ParseMode.MARKDOWN,
        )

        try:
            def submit_form_and_wait_otp(drv, pwd_val, name_val):
                safe_click_and_type(drv, "password", pwd_val)
                safe_click_and_type(drv, "fullname", name_val)
                safe_check_checkbox(drv, "termsAccepted")
                safe_check_checkbox(drv, "commsAccepted")
                click_submit_button(drv)
                wait_for_otp_screen(drv)

            await asyncio.to_thread(submit_form_and_wait_otp, driver, text, fullname)

            session["state"] = "WAITING_EMAIL_OTP"
            await status_msg.edit_text(
                "📩 **¡Código de verificación enviado a tu correo!**\n\n"
                f"Wallapop ha enviado un código de 6 dígitos a `{session['email']}`.\n\n"
                "🔢 Por favor, **escribe aquí el código de 6 dígitos**:",
                parse_mode=ParseMode.MARKDOWN,
            )

        except Exception as e:
            logger.error(f"Error completando el registro: {e}", exc_info=True)
            await status_msg.edit_text(
                f"❌ Error al enviar el formulario o esperar pantalla de verificación: `{str(e)}`",
                reply_markup=get_main_keyboard(),
                parse_mode=ParseMode.MARKDOWN,
            )
            session["state"] = "IDLE"

    # ----------------------------------------------------
    # 3. ESTADO: ESPERANDO CÓDIGO OTP DE EMAIL
    # ----------------------------------------------------
    elif state == "WAITING_EMAIL_OTP":
        if not driver:
            await update.message.reply_text(
                "⚠️ No hay ninguna sesión activa. Pulsa el botón para iniciar:",
                reply_markup=get_main_keyboard(),
            )
            return

        clean_code = re.sub(r"\D", "", text)
        if len(clean_code) != 6:
            await update.message.reply_text(
                "⚠️ El código debe ser de **6 dígitos numéricos** (por ejemplo: `123456`).\n"
                "Por favor, escríbelo de nuevo:",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        session["email_code"] = clean_code
        session["state"] = "PROCESSING_EMAIL_OTP"

        status_msg = await update.message.reply_text(
            f"🔢 Rellenando código `{clean_code}`, pulsando **Verificar** y esperando pantalla de teléfono...",
            parse_mode=ParseMode.MARKDOWN,
        )

        try:
            def verify_email_and_wait_phone(drv, otp_val):
                fill_otp_and_verify(drv, otp_val)
                wait_for_phone_screen(drv)

            await asyncio.to_thread(verify_email_and_wait_phone, driver, clean_code)

            session["state"] = "WAITING_PHONE_NUMBER"
            await status_msg.edit_text(
                "📱 **¡Email verificado con éxito!**\n\n"
                "Ahora Wallapop solicita vincular un número de teléfono.\n\n"
                "📞 Por favor, **introduce el número de teléfono** (9 dígitos, ejemplo: `682991122`, sin el +34):",
                parse_mode=ParseMode.MARKDOWN,
            )

        except Exception as e:
            logger.error(f"Error verificando email o esperando teléfono: {e}", exc_info=True)
            await status_msg.edit_text(
                f"❌ Error al verificar email o cargar pantalla de teléfono: `{str(e)}`",
                reply_markup=get_main_keyboard(),
                parse_mode=ParseMode.MARKDOWN,
            )
            session["state"] = "IDLE"

    # ----------------------------------------------------
    # 4. ESTADO: ESPERANDO NÚMERO DE TELÉFONO
    # ----------------------------------------------------
    elif state == "WAITING_PHONE_NUMBER":
        if not driver:
            await update.message.reply_text(
                "⚠️ No hay ninguna sesión activa. Pulsa el botón para iniciar:",
                reply_markup=get_main_keyboard(),
            )
            return

        clean_phone = re.sub(r"\D", "", text)
        if clean_phone.startswith("34") and len(clean_phone) == 11:
            clean_phone = clean_phone[2:]

        if len(clean_phone) != 9:
            await update.message.reply_text(
                "⚠️ El número de teléfono debe tener **9 dígitos** (por ejemplo: `682991122`).\n"
                "Por favor, escríbelo de nuevo sin el +34:",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        session["phone"] = clean_phone
        session["state"] = "PROCESSING_PHONE"

        status_msg = await update.message.reply_text(
            f"📱 Escribiendo teléfono `{clean_phone}` y pulsando **Enviar código**...",
            parse_mode=ParseMode.MARKDOWN,
        )

        try:
            await asyncio.to_thread(write_phone_and_send_code, driver, clean_phone)

            session["state"] = "WAITING_PHONE_OTP"
            await status_msg.edit_text(
                "📲 **¡Código SMS enviado al teléfono!**\n\n"
                f"Wallapop ha enviado un código de 6 dígitos a `{clean_phone}`.\n\n"
                "🔢 Por favor, **escribe aquí el código de 6 dígitos** recibido por SMS:",
                parse_mode=ParseMode.MARKDOWN,
            )

        except Exception as e:
            logger.error(f"Error introduciendo teléfono o enviando SMS: {e}", exc_info=True)
            await status_msg.edit_text(
                f"❌ Error al introducir teléfono o enviar código SMS: `{str(e)}`",
                reply_markup=get_main_keyboard(),
                parse_mode=ParseMode.MARKDOWN,
            )
            session["state"] = "IDLE"

    # ----------------------------------------------------
    # 5. ESTADO: ESPERANDO CÓDIGO OTP DE TELÉFONO (SMS)
    # ----------------------------------------------------
    elif state == "WAITING_PHONE_OTP":
        if not driver:
            await update.message.reply_text(
                "⚠️ No hay ninguna sesión activa. Pulsa el botón para iniciar:",
                reply_markup=get_main_keyboard(),
            )
            return

        clean_code = re.sub(r"\D", "", text)
        if len(clean_code) != 6:
            await update.message.reply_text(
                "⚠️ El código debe ser de **6 dígitos numéricos** (por ejemplo: `123456`).\n"
                "Por favor, escríbelo de nuevo:",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        session["phone_code"] = clean_code
        session["state"] = "PROCESSING_PHONE_OTP"

        status_msg = await update.message.reply_text(
            f"🔢 Rellenando código SMS `{clean_code}` y pulsando **Verificar**...",
            parse_mode=ParseMode.MARKDOWN,
        )

        try:
            await asyncio.to_thread(fill_otp_and_verify, driver, clean_code)

            # Mensaje final con TODA la información
            final_message = (
                "🎉 **¡Cuenta de Wallapop completamente registrada y verificada!**\n\n"
                "📋 **Resumen de todos los datos de la cuenta:**\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 **Nombre y Apellidos:** `{session.get('fullname')}`\n"
                f"📧 **Email:** `{session.get('email')}`\n"
                f"🔑 **Contraseña:** `{session.get('password')}`\n"
                f"📱 **Teléfono:** `{session.get('phone')}`\n"
                f"🔢 **Código Email:** `{session.get('email_code')}`\n"
                f"🔢 **Código SMS:** `{session.get('phone_code')}`\n"
                "☑️ **Condiciones de uso:** Aceptadas\n"
                "☑️ **Comunicaciones:** Aceptadas\n"
                "✅ **Verificación Email:** Completada\n"
                "✅ **Verificación Teléfono:** Completada\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "✨ Todo el proceso ha finalizado correctamente en Chromium.\n"
                "¿Deseas registrar otra cuenta?"
            )

            await status_msg.edit_text(
                final_message,
                reply_markup=get_main_keyboard(),
                parse_mode=ParseMode.MARKDOWN,
            )

            session["state"] = "IDLE"

        except Exception as e:
            logger.error(f"Error verificando código SMS: {e}", exc_info=True)
            await status_msg.edit_text(
                f"❌ Error al rellenar el código SMS o pulsar Verificar: `{str(e)}`",
                reply_markup=get_main_keyboard(),
                parse_mode=ParseMode.MARKDOWN,
            )
            session["state"] = "IDLE"

    # ----------------------------------------------------
    # OTROS MENSAJES FUERA DE FLUJO
    # ----------------------------------------------------
    else:
        await update.message.reply_text(
            "👋 Pulsa **New Account** para comenzar un nuevo registro:",
            reply_markup=get_main_keyboard(),
            parse_mode=ParseMode.MARKDOWN,
        )


def main():
    check_single_instance()

    print("==================================================")
    print("Iniciando Bot de Telegram para Wallapop con Chromium...")
    print(f"Token configurado: {BOT_TOKEN[:10]}...{BOT_TOKEN[-5:]}")
    print(f"Modo headless sin interfaz gráfica activado.")
    print("Esperando interacciones de usuarios en Telegram...")
    print("==================================================")

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("cancel", cancel_handler))
    application.add_handler(CallbackQueryHandler(button_callback_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
