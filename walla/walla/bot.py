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
    """Garantiza que sólo una instancia del bot se ejecute en local (Windows)."""
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
# CONFIGURACIÓN ROBUSTA DE SELENIUM
# ==========================================
def get_browser_driver():
    """Crea una instancia de navegador compatible tanto con Windows local (Edge visible) como con Render/Linux (Chrome/Edge headless con sandbox deshabilitado)."""
    is_headless = IS_CLOUD or os.environ.get("HEADLESS", "false").lower() == "true"

    # Argumentos comunes anti-detección
    common_args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
    ]

    # Argumentos indispensables para contenedores Linux (Render / Docker)
    cloud_args = [
        "--headless=new",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-software-rasterizer",
        "--remote-debugging-port=9222",
        "--window-size=1920,1080",
    ]

    # --- 1. En Windows, intentar Edge primero (visible) ---
    if not IS_CLOUD:
        try:
            logger.info("Iniciando Edge en Windows...")
            edge_opts = webdriver.EdgeOptions()
            for arg in common_args:
                edge_opts.add_argument(arg)
            edge_opts.add_argument("--start-maximized")
            edge_opts.add_experimental_option("excludeSwitches", ["enable-automation"])
            edge_opts.add_experimental_option("useAutomationExtension", False)
            return webdriver.Edge(options=edge_opts)
        except Exception as e:
            logger.warning(f"Edge falló en Windows ({e}), probando Chrome...")

    # --- 2. En Render / Linux o fallback en Windows: Chrome ---
    try:
        logger.info("Iniciando Chrome...")
        chrome_opts = webdriver.ChromeOptions()
        for arg in common_args:
            chrome_opts.add_argument(arg)
        chrome_opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_opts.add_experimental_option("useAutomationExtension", False)

        if is_headless:
            for arg in cloud_args:
                chrome_opts.add_argument(arg)

            # Buscar posibles rutas de binarios de Chrome en Render / Linux
            possible_chrome_paths = [
                os.environ.get("CHROME_BIN", ""),
                "/opt/render/project/.render/chrome/opt/google/chrome/google-chrome",
                "/usr/bin/google-chrome",
                "/usr/bin/google-chrome-stable",
                "/usr/bin/chromium",
                "/usr/bin/chromium-browser",
            ]
            for path in possible_chrome_paths:
                if path and os.path.exists(path):
                    chrome_opts.binary_location = path
                    logger.info(f"Binario de Chrome encontrado en: {path}")
                    break
        else:
            chrome_opts.add_argument("--start-maximized")

        return webdriver.Chrome(options=chrome_opts)
    except Exception as e_chrome:
        logger.warning(f"Chrome falló ({e_chrome}), intentando Edge como fallback...")

    # --- 3. Edge en Linux (si está instalado) ---
    try:
        logger.info("Intentando Edge en Linux...")
        edge_opts = webdriver.EdgeOptions()
        for arg in common_args:
            edge_opts.add_argument(arg)
        edge_opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        edge_opts.add_experimental_option("useAutomationExtension", False)
        if is_headless:
            for arg in cloud_args:
                edge_opts.add_argument(arg)
        else:
            edge_opts.add_argument("--start-maximized")
        return webdriver.Edge(options=edge_opts)
    except Exception as e_edge:
        logger.error(f"Error fatal: no se pudo iniciar ni Chrome ni Edge. Detalles: Chrome ({e_chrome}), Edge ({e_edge})")
        raise RuntimeError(f"No se pudo iniciar el navegador. Si estás en Render, asegúrate de que Chrome está instalado. Error: {e_chrome}")


def open_and_navigate_to_onboarding(url: str):
    """Inicia el navegador y clica en Regístrate."""
    driver = get_browser_driver()
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

    # Enfocar y hacer clic
    try:
        otp_input.click()
    except Exception:
        driver.execute_script("arguments[0].click();", otp_input)
    driver.execute_script("arguments[0].focus();", otp_input)
    time.sleep(0.2)

    # Limpiar y escribir cada dígito
    otp_input.clear()
    for char in code:
        otp_input.send_keys(char)
        time.sleep(0.05)

    # Disparar eventos Input y Change por JS para asegurar la actualización de estado en React
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

    # Clicar botón Verificar
    click_verificar_button(driver)
    time.sleep(3)


def click_verificar_button(driver):
    """Localiza y pulsa el botón 'Verificar'."""
    wait = WebDriverWait(driver, 15)
    # 1. Intentar por walla-button con texto Verificar
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
        logger.info("Botón Verificar clicado exitosamente (walla-button).")
        return
    except Exception as e:
        logger.warning(f"No se localizó walla-button Verificar directamente: {e}")

    # 2. Fallback por selector XPath general o submit
    try:
        btn = driver.find_element(
            By.XPATH,
            "//button[contains(., 'Verificar')] | //*[@part='button'][contains(., 'Verificar')] | //button[@type='submit']"
        )
        driver.execute_script("arguments[0].click();", btn)
        logger.info("Botón Verificar clicado exitosamente (fallback XPath).")
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
    # 1. Intentar por walla-button con texto Enviar código
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

    # 2. Fallback XPath
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
    """Cierra el driver de Edge/Chrome si existe para este usuario."""
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
        "🤖 **¡Bienvenido al Bot de Registro Completo de Wallapop!**\n\n"
        "Este bot automatiza la creación y verificación de cuentas en Wallapop mediante "
        "Selenium y completando los datos en tiempo real.\n\n"
        "⚡ **Flujo completo del proceso:**\n"
        "1️⃣ Pulsa el botón **New Account**.\n"
        "2️⃣ Se iniciará el navegador y accederá al portal de Wallapop.\n"
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
    """Comando /cancel: cancela la operación y cierra el navegador si está abierto."""
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
        "🚀 **Iniciando navegador...**\n"
        "Accediendo a Wallapop Onboarding y pulsando en **Regístrate**, por favor espera unos segundos...",
        parse_mode=ParseMode.MARKDOWN,
    )

    try:
        driver = await asyncio.to_thread(open_and_navigate_to_onboarding, WALLAPOP_ONBOARDING_URL)
        user_sessions[chat_id]["driver"] = driver
        user_sessions[chat_id]["state"] = "WAITING_EMAIL"

        await status_msg.edit_text(
            "🌐 **¡Página de registro lista!**\n\n"
            "📧 Por favor, **escribe el correo electrónico** que deseas usar para esta cuenta:",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        logger.error(f"Error al iniciar navegador: {e}", exc_info=True)
        cleanup_session_driver(chat_id)
        user_sessions[chat_id] = {"state": "IDLE"}
        await status_msg.edit_text(
            f"❌ *Error al iniciar el navegador o cargar la página:*\n`{str(e)}`\n\n"
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
                "✨ Todo el proceso ha finalizado correctamente.\n"
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
    print("Iniciando Bot de Telegram para Wallapop...")
    print(f"Token configurado: {BOT_TOKEN[:10]}...{BOT_TOKEN[-5:]}")
    print(f"Modo entorno: {'Cloud / Render (Linux)' if IS_CLOUD else 'Local (Windows Edge)'}")
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
