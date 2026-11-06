# bot.py - Bot de Telegram para automatización de eSIMs en Simyo
import os
import re
import html
import json
import time
import asyncio
import logging
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

from config import BOT_TOKEN
from storage import get_user_data, save_user_data
from name_parser import parse_full_name
from selenium_worker import run_simyo_order

# Configuración de logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Estados de la conversación
(
    STATE_START,
    STATE_ASK_CARD_REUSE,
    STATE_EMAIL,
    STATE_PHONE,
    STATE_ASK_SAVE,
    STATE_DNI,
    STATE_NAME,
    STATE_BIRTHDATE,
    STATE_ESIM_COUNT,
) = range(9)

# Tiempo máximo (segundos) que el navegador esperará los datos de la tarjeta
CARD_TIMEOUT = 600

# Fichero donde se guardan las tarjetas validadas
CARDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saved_cards.json")


# --- ALMACÉN DE TARJETAS ---

def _load_cards() -> dict:
    try:
        with open(CARDS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_card(user_id: int, card: dict):
    try:
        cards = _load_cards()
        cards[str(user_id)] = {
            "numero": card["numero"],
            "mes": card["mes"],
            "ano": card["ano"],
            "cvv": card.get("cvv", ""),
            "guardada": datetime.now().isoformat(timespec="seconds"),
        }
        with open(CARDS_FILE, "w", encoding="utf-8") as f:
            json.dump(cards, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"No se pudo guardar la tarjeta: {e}")


def _get_saved_card(user_id: int) -> dict | None:
    card = _load_cards().get(str(user_id))
    if card and card.get("numero") and card.get("cvv"):
        return card
    return None


def _mask_card(numero: str) -> str:
    return f"{numero[:4]} **** **** {numero[-4:]}"


def validate_email(email: str) -> bool:
    """Valida formato básico de correo electrónico."""
    pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    return bool(re.match(pattern, email.strip()))


def clean_spanish_phone(phone_str: str) -> str | None:
    """Limpia y valida un número de teléfono español de 9 dígitos."""
    digits = "".join(ch for ch in phone_str if ch.isdigit())
    if digits.startswith("34") and len(digits) == 11:
        digits = digits[2:]
    if len(digits) == 9 and digits[0] in ("6", "7"):
        return digits
    return None


def parse_birthdate_str(date_str: str) -> tuple[int, int, int] | None:
    """Parsea una fecha en formato DD/MM/AAAA o similar."""
    clean = re.sub(r"[^\d]", "/", date_str.strip())
    parts = [p for p in clean.split("/") if p]
    if len(parts) != 3:
        return None
    try:
        d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
        if not (1 <= d <= 31):
            return None
        if not (1 <= m <= 12):
            return None
        if not (1926 <= y <= 2008):
            return None
        datetime(year=y, month=m, day=d)
        return d, m, y
    except Exception:
        return None


def parse_card_data(raw: str) -> dict | None:
    """
    Parsea los datos de tarjeta enviados por el usuario.
    Formatos aceptados:
    1. NUMERO|MM|AA|CVV  (ej: 4766635218246360|09|30|078)
    2. NUMERO MM/AA CVV  (separado por espacios, barras o guiones)
    3. Cadena continua de 23 o 25 dígitos
    4. Solo número de tarjeta (sin CVV)
    """
    if not raw:
        return None

    raw_clean = raw.strip()

    if "|" in raw_clean:
        partes = [p.strip() for p in raw_clean.split("|") if p.strip()]
        if len(partes) == 4:
            p_num = "".join(c for c in partes[0] if c.isdigit())
            p_mes = "".join(c for c in partes[1] if c.isdigit()).zfill(2)
            p_ano = "".join(c for c in partes[2] if c.isdigit())
            p_cvv = "".join(c for c in partes[3] if c.isdigit())
            if len(p_ano) == 4:
                p_ano = p_ano[2:]
            if (13 <= len(p_num) <= 19) and (1 <= int(p_mes) <= 12) and (len(p_ano) == 2) and (3 <= len(p_cvv) <= 4):
                return {"numero": p_num, "mes": p_mes, "ano": p_ano, "cvv": p_cvv}
        elif len(partes) == 3:
            p_num = "".join(c for c in partes[0] if c.isdigit())
            exp_sub = [s.strip() for s in re.split(r"[^\d]+", partes[1]) if s.strip()]
            p_cvv = "".join(c for c in partes[2] if c.isdigit())
            if len(exp_sub) == 2 and (13 <= len(p_num) <= 19) and (3 <= len(p_cvv) <= 4):
                p_mes = exp_sub[0].zfill(2)
                p_ano = exp_sub[1]
                if len(p_ano) == 4:
                    p_ano = p_ano[2:]
                if (1 <= int(p_mes) <= 12) and (len(p_ano) == 2):
                    return {"numero": p_num, "mes": p_mes, "ano": p_ano, "cvv": p_cvv}

    m = re.search(r"(\b(?:\d[ -]?){13,19}\b)", raw_clean)
    if m:
        card_digits = "".join(c for c in m.group(1) if c.isdigit())
        remainder = raw_clean[m.end():].strip()
        tokens = [t for t in re.split(r"[^\d]+", remainder) if t]
        if len(tokens) == 3:
            t_mes = tokens[0].zfill(2)
            t_ano = tokens[1]
            t_cvv = tokens[2]
            if len(t_ano) == 4:
                t_ano = t_ano[2:]
            if (1 <= int(t_mes) <= 12) and (len(t_ano) == 2) and (3 <= len(t_cvv) <= 4):
                return {"numero": card_digits, "mes": t_mes, "ano": t_ano, "cvv": t_cvv}
        elif len(tokens) == 2:
            if len(tokens[0]) == 4 and (3 <= len(tokens[1]) <= 4):
                t_mes = tokens[0][:2]
                t_ano = tokens[0][2:]
                t_cvv = tokens[1]
                if 1 <= int(t_mes) <= 12:
                    return {"numero": card_digits, "mes": t_mes, "ano": t_ano, "cvv": t_cvv}

    digits_only = "".join(c for c in raw_clean if c.isdigit())
    if len(digits_only) == 23:
        p_num = digits_only[:16]
        p_mes = digits_only[16:18]
        p_ano = digits_only[18:20]
        p_cvv = digits_only[20:23]
        if 1 <= int(p_mes) <= 12:
            return {"numero": p_num, "mes": p_mes, "ano": p_ano, "cvv": p_cvv}
    elif len(digits_only) == 25:
        p_num = digits_only[:16]
        p_mes = digits_only[16:18]
        p_ano = digits_only[20:22]
        p_cvv = digits_only[22:25]
        if 1 <= int(p_mes) <= 12:
            return {"numero": p_num, "mes": p_mes, "ano": p_ano, "cvv": p_cvv}

    if 13 <= len(digits_only) <= 19:
        return {"numero": digits_only, "mes": None, "ano": None, "cvv": None}

    return None


# --- MANEJADORES DE TELEGRAM ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Maneja el comando /start mostrando el resumen y un único botón 'Empezar'."""
    old_drv = context.user_data.get("active_driver")
    if old_drv:
        try:
            old_drv.quit()
        except Exception:
            pass
        context.user_data["active_driver"] = None

    old_fut = context.user_data.get("card_future")
    if old_fut and not old_fut.done():
        old_fut.cancel()
        context.user_data.pop("card_future", None)

    context.user_data["initial_card"] = None
    context.user_data["pending_saved_card"] = None

    text = (
        "┌── [ ⚡ SIMYO AUTOMATION CORE // v2.0 ] ──┐\n"
        "│ Tramitación 100% automatizada con Edge\n"
        "│ para líneas eSIM Prepago con número nuevo.\n"
        "└──────────────────────────────────────────┘\n\n"
        "<code>[STATUS] : SYSTEM READY & IDLE</code>\n"
        "<code>[TARGET] : simyo.es/cart (15GB + Ilimitadas)</code>\n\n"
        "⚡ Presiona el botón para inicializar la secuencia:"
    )
    keyboard = [
        [InlineKeyboardButton("🚀 Iniciar Tramitación", callback_data="start_flow")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")
    elif update.callback_query:
        await update.callback_query.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")
    return STATE_START


async def _prompt_email_or_saved(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Pregunta por email: reutilizar los guardados o pedir unos nuevos."""
    user_id = query.from_user.id
    saved = get_user_data(user_id)

    if saved and "email" in saved and "phone" in saved:
        text = (
            "┌── [ 💾 DATOS GUARDADOS ENCONTRADOS ] ──┐\n"
            f"│ • <b>EMAIL   :</b> <code>{html.escape(saved['email'])}</code>\n"
            f"│ • <b>TELÉFONO:</b> <code>{html.escape(saved['phone'])}</code>\n"
            "└───────────────────────────────────────┘\n\n"
            "¿Deseas reutilizar estos datos o ingresar unos nuevos?"
        )
        keyboard = [
            [
                InlineKeyboardButton("✓ Usar Guardados", callback_data="use_saved"),
                InlineKeyboardButton("↺ Ingresar Nuevos", callback_data="enter_new")
            ]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        return STATE_ASK_SAVE

    await query.edit_message_text(
        "┌── [ 📧 INPUT // CORREO ELECTRÓNICO ] ──┐\n"
        "│ Introduce tu correo de contacto para Simyo:\n"
        "└─────────────────────────────────────────┘",
        parse_mode="HTML"
    )
    return STATE_EMAIL


async def start_flow_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Se ejecuta al pulsar el botón 'Empezar'. Pregunta primero por la tarjeta guardada."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    saved_card = _get_saved_card(user_id)

    if saved_card:
        context.user_data["pending_saved_card"] = saved_card
        text = (
            "┌── [ 💳 TARJETA GUARDADA DISPONIBLE ] ──┐\n"
            f"│ • <b>TARJETA:</b> <code>{_mask_card(saved_card['numero'])}</code>\n"
            f"│ • <b>CADUCA :</b> <code>{saved_card['mes']}/{saved_card['ano']}</code>\n"
            "└─────────────────────────────────────────┘\n\n"
            "¿Quieres usar la misma tarjeta que la última vez?"
        )
        keyboard = [
            [
                InlineKeyboardButton("✓ Sí, la misma", callback_data="card_reuse_yes"),
                InlineKeyboardButton("✕ No, otra tarjeta", callback_data="card_reuse_no"),
            ]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        return STATE_ASK_CARD_REUSE

    context.user_data["initial_card"] = None
    return await _prompt_email_or_saved(query, context)


async def handle_card_reuse_yes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    card = context.user_data.get("pending_saved_card") or {}
    context.user_data["initial_card"] = card if card else None
    context.user_data["pending_saved_card"] = None

    if card:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"💳 <code>[CARD_LOADED]</code> Se usará la tarjeta <code>{_mask_card(card['numero'])}</code>.",
            parse_mode="HTML"
        )
    return await _prompt_email_or_saved(query, context)


async def handle_card_reuse_no(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    context.user_data["initial_card"] = None
    context.user_data["pending_saved_card"] = None

    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="💳 <code>[CARD_NEW]</code> Se solicitará una tarjeta nueva en el paso de pago.",
        parse_mode="HTML"
    )
    return await _prompt_email_or_saved(query, context)


async def handle_use_saved_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Usuario decide usar los datos guardados."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    saved = get_user_data(user_id)

    context.user_data["email"] = saved["email"]
    context.user_data["phone"] = saved["phone"]

    await query.edit_message_text(
        "┌── [ ✓ CACHE CARGADA EN MEMORIA ] ──┐\n"
        f"│ • <b>EMAIL   :</b> <code>{html.escape(saved['email'])}</code>\n"
        f"│ • <b>TELÉFONO:</b> <code>{html.escape(saved['phone'])}</code>\n"
        "└────────────────────────────────────┘\n\n"
        "┌── [ 🆔 INPUT // DOCUMENTO DE IDENTIDAD ] ──┐\n"
        "│ Introduce tu número de DNI o NIE (ej: 12345678Z):\n"
        "└────────────────────────────────────────────┘",
        parse_mode="HTML"
    )
    return STATE_DNI


async def handle_enter_new_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Usuario decide introducir datos nuevos."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "┌── [ 📧 INPUT // CORREO ELECTRÓNICO ] ──┐\n"
        "│ Introduce tu correo de contacto para Simyo:\n"
        "└─────────────────────────────────────────┘",
        parse_mode="HTML"
    )
    return STATE_EMAIL


async def receive_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe y valida el correo electrónico."""
    email_text = update.message.text.strip()
    if not validate_email(email_text):
        await update.message.reply_text(
            "⚠️ <code>[ERROR // INVALID_EMAIL]</code>\n"
            "El formato de email no parece válido. Por favor, revísalo:",
            parse_mode="HTML"
        )
        return STATE_EMAIL

    context.user_data["email"] = email_text
    await update.message.reply_text(
        "┌── [ 📱 INPUT // TELÉFONO ESPAÑOL ] ──┐\n"
        "│ Introduce tu número móvil español (9 dígitos, ej: 612345678):\n"
        "└───────────────────────────────────────┘",
        parse_mode="HTML"
    )
    return STATE_PHONE


async def receive_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el teléfono español y pregunta si desea guardarlo."""
    phone_text = update.message.text.strip()
    clean_phone = clean_spanish_phone(phone_text)
    if not clean_phone:
        await update.message.reply_text(
            "⚠️ <code>[ERROR // INVALID_PHONE]</code>\n"
            "Introduce un móvil español válido de 9 dígitos (que empiece por 6 o 7):",
            parse_mode="HTML"
        )
        return STATE_PHONE

    context.user_data["phone"] = clean_phone

    text = (
        "┌── [ 💾 SYSTEM CACHE // GUARDAR DATOS ] ──┐\n"
        f"│ • <b>EMAIL   :</b> <code>{html.escape(context.user_data['email'])}</code>\n"
        f"│ • <b>TELÉFONO:</b> <code>{html.escape(clean_phone)}</code>\n"
        "└──────────────────────────────────────────┘\n\n"
        "¿Deseas guardar estos datos para las próximas veces?"
    )
    keyboard = [
        [
            InlineKeyboardButton("✓ Sí, Guardar", callback_data="save_yes"),
            InlineKeyboardButton("✕ No Guardar", callback_data="save_no")
        ]
    ]
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
    return STATE_ASK_SAVE


async def handle_save_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Maneja la elección de guardar datos (Sí o No)."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    if query.data == "save_yes":
        save_user_data(user_id, context.user_data["email"], context.user_data["phone"])
        save_msg = "💾 <code>[CACHE_SAVED]</code> Datos guardados en disco."
    else:
        save_msg = "👌 <code>[CACHE_SKIPPED]</code> No se guardarán estos datos."

    await query.edit_message_text(
        f"{save_msg}\n\n"
        "┌── [ 🆔 INPUT // DOCUMENTO DE IDENTIDAD ] ──┐\n"
        "│ Introduce tu número de DNI o NIE (ej: 12345678Z):\n"
        "└────────────────────────────────────────────┘",
        parse_mode="HTML"
    )
    return STATE_DNI


async def receive_dni(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el número de DNI o NIE."""
    dni_text = update.message.text.strip().upper()
    if len(dni_text) < 6 or len(dni_text) > 12:
        await update.message.reply_text(
            "⚠️ <code>[ERROR // INVALID_DNI]</code>\n"
            "Introduce un número de documento DNI o NIE válido:",
            parse_mode="HTML"
        )
        return STATE_DNI

    context.user_data["dni"] = dni_text
    await update.message.reply_text(
        "┌── [ 👤 INPUT // NOMBRE COMPLETO TITULAR ] ──┐\n"
        "│ Introduce el nombre completo del titular:\n"
        "└─────────────────────────────────────────────┘\n\n"
        "💡 <i>Ejemplos de asignación:</i>\n"
        "• <code>Ana Maria Ramos Castillon</code> (Nombre: <code>Ana Maria</code>)\n"
        "• <code>Ana Romero Mendoza</code> (Nombre: <code>Ana</code>)",
        parse_mode="HTML"
    )
    return STATE_NAME


async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el nombre completo y lo separa según la regla solicitada."""
    full_name = update.message.text.strip()
    fn, ln1, ln2 = parse_full_name(full_name)

    if not fn or not ln1:
        await update.message.reply_text(
            "⚠️ <code>[ERROR // INCOMPLETE_NAME]</code>\n"
            "Por favor, introduce tu nombre y al menos el primer apellido:",
            parse_mode="HTML"
        )
        return STATE_NAME

    context.user_data["firstname"] = fn
    context.user_data["lastname1"] = ln1
    context.user_data["lastname2"] = ln2

    ln2_str = ln2 if ln2 else "(vacío)"
    await update.message.reply_text(
        "┌── [ ✓ TITULAR INTERPRETADO ] ──┐\n"
        f"│ • <b>NOMBRE     :</b> <code>{html.escape(fn)}</code>\n"
        f"│ • <b>1º APELLIDO:</b> <code>{html.escape(ln1)}</code>\n"
        f"│ • <b>2º APELLIDO:</b> <code>{html.escape(ln2_str)}</code>\n"
        "└────────────────────────────────┘\n\n"
        "┌── [ 📅 INPUT // FECHA DE NACIMIENTO ] ──┐\n"
        "│ Formato: DD/MM/AAAA (ej: 15/04/1990)\n"
        "└─────────────────────────────────────────┘",
        parse_mode="HTML"
    )
    return STATE_BIRTHDATE


async def receive_birthdate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe y valida la fecha de nacimiento."""
    date_text = update.message.text.strip()
    parsed_date = parse_birthdate_str(date_text)
    if not parsed_date:
        await update.message.reply_text(
            "⚠️ <code>[ERROR // INVALID_BIRTHDATE]</code>\n"
            "Fecha no válida. Debe ser en formato <code>DD/MM/AAAA</code> (año entre 1926 y 2008):",
            parse_mode="HTML"
        )
        return STATE_BIRTHDATE

    day, month, year = parsed_date
    context.user_data["birthdate_day"] = day
    context.user_data["birthdate_month"] = month
    context.user_data["birthdate_year"] = year

    keyboard = [
        [
            InlineKeyboardButton("⚡ 1 eSIM", callback_data="esim_1"),
            InlineKeyboardButton("⚡ 2 eSIMs", callback_data="esim_2"),
            InlineKeyboardButton("⚡ 3 eSIMs", callback_data="esim_3"),
        ]
    ]
    await update.message.reply_text(
        "┌── [ 📲 CONFIG // CANTIDAD DE ESIMS ] ──┐\n"
        "│ Selecciona cuántas líneas deseas tramitar (máx 3):\n"
        "└─────────────────────────────────────────┘",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
    return STATE_ESIM_COUNT


async def handle_esim_count(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe la cantidad de eSIMs e inicia la consola interactiva de Selenium Edge."""
    num_esims = 1
    chat_id = None

    if update.callback_query:
        query = update.callback_query
        await query.answer()
        chat_id = query.message.chat_id
        if query.data == "esim_1":
            num_esims = 1
        elif query.data == "esim_2":
            num_esims = 2
        elif query.data == "esim_3":
            num_esims = 3
        await query.edit_message_reply_markup(reply_markup=None)
    elif update.message:
        chat_id = update.message.chat_id
        text = update.message.text.strip()
        if text in ("1", "2", "3"):
            num_esims = int(text)
        else:
            await update.message.reply_text("⚠️ Por favor selecciona 1, 2 o 3 eSIMs con los botones:")
            return STATE_ESIM_COUNT

    context.user_data["num_esims"] = num_esims
    context.user_data["user_id"] = update.effective_user.id
    data = context.user_data
    titular_name = f"{data['firstname']} {data['lastname1']}".strip()

    tarjeta_info = "nueva (se pedirá en el pago)"
    if data.get("initial_card"):
        tarjeta_info = f"guardada {_mask_card(data['initial_card']['numero'])}"

    initial_panel_html = (
        "┌── [ ⚡ SIMYO AUTOMATION CONSOLE ] ──┐\n"
        f"│ <b>TITULAR:</b> <code>{html.escape(titular_name)}</code>\n"
        f"│ <b>DNI/NIE:</b> <code>{html.escape(data['dni'])}</code>\n"
        f"│ <b>ORDEN  :</b> <code>{num_esims}x eSIM Prepago (Nuevo)</code>\n"
        f"│ <b>TARJETA:</b> <code>{html.escape(tarjeta_info)}</code>\n"
        "└────────────────────────────────────┘\n\n"
        "<pre>[>] Inicializando Chrome WebDriver (headless)...\n"
        "[>] Conectando con los servidores de Simyo...</pre>\n\n"
        "🛰️ <b>PASO ACTUAL:</b>\n"
        "<code>Iniciando navegador y cargando la página...</code>"
    )

    msg = await context.bot.send_message(chat_id=chat_id, text=initial_panel_html, parse_mode="HTML")

    asyncio.create_task(run_automation_task(context, chat_id, msg.message_id))

    return ConversationHandler.END


class LiveTerminal:
    def __init__(self, bot, chat_id: int, message_id: int, dni: str, name: str, lines_count: int):
        self.bot = bot
        self.chat_id = chat_id
        self.message_id = message_id
        self.dni = dni
        self.name = name
        self.lines_count = lines_count
        self.logs: list[str] = [
            "[✓] Chrome WebDriver inicializado (headless)",
            "[~] Conectando con simyo.es..."
        ]
        self.current_status: str = "Conectando con simyo.es..."
        self.last_edit = 0.0
        self._lock = asyncio.Lock()
        self._pending = False

    def add_log(self, raw_msg: str):
        clean = raw_msg.strip()
        text_clean = re.sub(r"^[^\w\d\[\(]+", "", clean).strip()
        if not text_clean:
            text_clean = clean

        low = clean.lower()
        if any(w in low for w in ["éxito", "correctamente", "aceptando", "fijada", "asignando", "activando", "escrito", "detectado", "pulsado", "completado", "aceptado"]):
            prefix = "[✓]"
        elif any(w in low for w in ["error", "fallo", "incorrecto", "rechazada"]) or "❌" in clean:
            prefix = "[!]"
        elif any(w in low for w in ["esperando", "solicitando", "comprobando", "buscando"]):
            prefix = "[~]"
        else:
            prefix = "[►]"

        formatted_line = f"{prefix} {text_clean}"
        if not self.logs or self.logs[-1] != formatted_line:
            self.logs.append(formatted_line)
        self.current_status = clean

    def render_html(self) -> str:
        visible = self.logs[-8:] if len(self.logs) > 8 else self.logs
        log_content = "\n".join(visible) if visible else "[>] Ejecutando secuencia..."

        return (
            "┌── [ ⚡ SIMYO AUTOMATION CONSOLE ] ──┐\n"
            f"│ <b>TITULAR:</b> <code>{html.escape(self.name)}</code>\n"
            f"│ <b>DNI/NIE:</b> <code>{html.escape(self.dni)}</code>\n"
            f"│ <b>ORDEN  :</b> <code>{self.lines_count}x eSIM Prepago (Nuevo)</code>\n"
            "└────────────────────────────────────┘\n\n"
            f"<pre>{html.escape(log_content)}</pre>\n\n"
            f"🛰️ <b>PASO ACTUAL:</b>\n"
            f"<code>{html.escape(self.current_status)}</code>"
        )

    async def update(self):
        async with self._lock:
            now = time.time()
            if now - self.last_edit < 0.8:
                if not self._pending:
                    self._pending = True
                    delay = max(0.1, 0.85 - (now - self.last_edit))
                    asyncio.create_task(self._delayed_update(delay))
                return
            await self._send_edit()

    async def _delayed_update(self, delay: float):
        await asyncio.sleep(delay)
        async with self._lock:
            self._pending = False
            await self._send_edit()

    async def _send_edit(self):
        try:
            await self.bot.edit_message_text(
                chat_id=self.chat_id,
                message_id=self.message_id,
                text=self.render_html(),
                parse_mode="HTML"
            )
            self.last_edit = time.time()
        except Exception as e:
            err_msg = str(e)
            if "Message is not modified" not in err_msg:
                logger.debug(f"Terminal live edit note: {e}")


async def run_automation_task(context: ContextTypes.DEFAULT_TYPE, chat_id: int, status_message_id: int):
    """Tarea asíncrona que ejecuta Selenium en un hilo y edita en vivo el mensaje de consola."""
    loop = asyncio.get_running_loop()
    data = context.user_data
    titular_name = f"{data['firstname']} {data['lastname1']}".strip()
    user_id = data.get("user_id")

    terminal = LiveTerminal(
        bot=context.bot,
        chat_id=chat_id,
        message_id=status_message_id,
        dni=data["dni"],
        name=titular_name,
        lines_count=data["num_esims"]
    )

    def sync_status_callback(text_msg: str):
        try:
            terminal.add_log(text_msg)
            asyncio.run_coroutine_threadsafe(terminal.update(), loop)
        except Exception as e:
            logger.error(f"Error en sync_status_callback: {e}")

    def sync_screenshot_callback(screenshot_path: str):
        try:
            if os.path.exists(screenshot_path):
                with open(screenshot_path, "rb") as f:
                    asyncio.run_coroutine_threadsafe(
                        context.bot.send_photo(
                            chat_id=chat_id,
                            photo=f,
                            caption="📸 <code>[SNAPSHOT // EDGE WEBDRIVER EVIDENCE]</code>",
                            parse_mode="HTML"
                        ),
                        loop
                    )
        except Exception as e:
            logger.error(f"Error enviando captura de pantalla: {e}")

    def sync_request_card_callback() -> dict | None:
        """Pide los datos de la tarjeta por Telegram y bloquea el hilo de Selenium hasta recibirlos."""
        async def _request():
            fut = loop.create_future()
            context.user_data["card_future"] = fut
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "┌── [ 💳 GATEWAY PAYMENT // REQUERIDO ] ──┐\n"
                    "│ El formulario de pago de Simyo ya está en pantalla.\n"
                    "└─────────────────────────────────────────┘\n\n"
                    "Introduce la tarjeta en formato:\n"
                    "<code>NUMERO|MM|AA|CVV</code>\n\n"
                    "Ejemplo:\n"
                    "<code>4766635218246360|09|30|078</code>\n\n"
                    "⚠️ El <b>CVV es obligatorio</b> para poder continuar.\n\n"
                    "⏳ <i>Esperando credencial... (10 minutos máximo)</i>"
                ),
                parse_mode="HTML"
            )
            try:
                return await asyncio.wait_for(fut, timeout=CARD_TIMEOUT)
            finally:
                context.user_data.pop("card_future", None)

        try:
            return asyncio.run_coroutine_threadsafe(_request(), loop).result(timeout=CARD_TIMEOUT + 30)
        except Exception as e:
            logger.error(f"Error pidiendo datos de tarjeta: {e}")
            return None

    def sync_card_invalid_callback(intento: int, card: dict):
        """Avisa por Telegram de que la tarjeta ha sido rechazada y que se repite el proceso."""
        numero = card.get("numero", "")
        masked = _mask_card(numero) if numero else "desconocida"

        async def _send():
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "┌── [ ❌ TARJETA RECHAZADA ] ──┐\n"
                    f"│ • <b>TARJETA :</b> <code>{masked}</code>\n"
                    f"│ • <b>INTENTO :</b> <code>{intento}</code>\n"
                    "└──────────────────────────────┘\n\n"
                    "Simyo no ha aceptado la tarjeta.\n"
                    "🔁 Cerrando la pasarela, repitiendo el pago y pidiendo una tarjeta nueva..."
                ),
                parse_mode="HTML"
            )

        try:
            asyncio.run_coroutine_threadsafe(_send(), loop)
        except Exception as e:
            logger.error(f"Error avisando de tarjeta inválida: {e}")

    def sync_driver_callback(drv):
        context.user_data["active_driver"] = drv

    res = await asyncio.to_thread(
        run_simyo_order,
        dni=data["dni"],
        firstname=data["firstname"],
        lastname1=data["lastname1"],
        lastname2=data.get("lastname2", ""),
        email=data["email"],
        phone=data["phone"],
        day=data["birthdate_day"],
        month=data["birthdate_month"],
        year=data["birthdate_year"],
        num_esims=data["num_esims"],
        status_callback=sync_status_callback,
        screenshot_callback=sync_screenshot_callback,
        request_card_callback=sync_request_card_callback,
        card_invalid_callback=sync_card_invalid_callback,
        driver_callback=sync_driver_callback,
        initial_card=data.get("initial_card"),
        keep_browser_open=True,
        headless=False
    )

    # Guardar la tarjeta si Simyo la ha aceptado
    tarjeta_guardada = False
    if res.get("success") and res.get("valid_card") and user_id:
        _save_card(user_id, res["valid_card"])
        tarjeta_guardada = True
        context.user_data["initial_card"] = None

    if res.get("success"):
        terminal.add_log("PROCESO TRAMITADO CORRECTAMENTE")
        await terminal._send_edit()

        tarjeta_txt = ""
        if tarjeta_guardada:
            tarjeta_txt = (
                "💳 <b>TARJETA VALIDADA Y GUARDADA:</b>\n"
                f"<code>{_mask_card(res['valid_card']['numero'])}</code>\n"
                "La próxima vez te preguntaré si quieres usarla de nuevo.\n\n"
            )

        final_text = (
            "┌── [ 🎉 TRAMITACIÓN COMPLETADA // ÉXITO ] ──┐\n"
            f"│ • <b>LÍNEAS ESIM :</b> <code>{data['num_esims']}</code>\n"
            f"│ • <b>DNI TITULAR :</b> <code>{data['dni']}</code>\n"
            f"│ • <b>EMAIL SIMYO :</b> <code>{data['email']}</code>\n"
            f"│ • <b>PASSWORD    :</b> <code>{res.get('generated_password')}</code>\n"
            "└──────────────────────────────────────────┘\n\n"
            f"{tarjeta_txt}"
            "ℹ️ <i>Simyo te enviará un enlace por email/SMS para completar la validación final de identidad.</i>\n\n"
            "🌐 <b>EDGE WEBDRIVER ACTIVO:</b>\n"
            "<code>El navegador se mantiene abierto en pantalla.</code>\n"
            "👉 Envía <b>/cancel</b> en Telegram cuando desees cerrar el navegador."
        )
    else:
        terminal.add_log(f"ERROR: {res.get('message', '')}")
        await terminal._send_edit()

        final_text = (
            "┌── [ ❌ ERROR // PROCESO INTERRUMPIDO ] ──┐\n"
            f"│ <b>Detalle:</b> <code>{html.escape(res.get('message', ''))}</code>\n"
            "└─────────────────────────────────────────┘\n\n"
            "🌐 <b>EDGE WEBDRIVER ACTIVO:</b>\n"
            "<code>El navegador se mantiene abierto para tu inspección.</code>\n"
            "👉 Envía <b>/cancel</b> para cerrar Edge o <b>/start</b> para reiniciar."
        )

    await context.bot.send_message(chat_id=chat_id, text=final_text, parse_mode="HTML")


async def receive_card_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe los datos de la tarjeta mientras el navegador está esperando en el formulario de pago."""
    fut = context.user_data.get("card_future")
    if not fut or fut.done():
        return

    raw = (update.message.text or "").strip()
    parsed = parse_card_data(raw)

    if not parsed:
        await update.message.reply_text(
            "⚠️ <code>[ERROR // INVALID_CARD_FORMAT]</code>\n\n"
            "Formato obligatorio: <code>NUMERO|MM|AA|CVV</code>\n"
            "Ejemplo: <code>4766635218246360|09|30|078</code>",
            parse_mode="HTML"
        )
        return

    if not parsed.get("cvv"):
        await update.message.reply_text(
            "⚠️ <code>[ERROR // MISSING_CVV]</code>\n\n"
            "Falta el CVV. Envíalo así:\n"
            "<code>NUMERO|MM|AA|CVV</code>\n"
            "Ejemplo: <code>4766635218246360|09|30|078</code>",
            parse_mode="HTML"
        )
        return

    fut.set_result(parsed)

    masked = _mask_card(parsed["numero"])
    await update.message.reply_text(
        "┌── [ 🔒 CREDENCIAL DE PAGO RECIBIDA ] ──┐\n"
        f"│ • <b>TARJETA :</b> <code>{masked}</code>\n"
        f"│ • <b>CADUCA  :</b> <code>{parsed['mes']}/{parsed['ano']}</code>\n"
        f"│ • <b>CVV     :</b> <code>{parsed['cvv']}</code>\n"
        "└───────────────────────────────────────┘\n\n"
        "✍️ <i>Escribiendo datos en el formulario y pulsando Pagar...</i>",
        parse_mode="HTML"
    )


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela la conversación y cierra el navegador Edge si está abierto."""
    drv = context.user_data.get("active_driver")
    driver_closed = False
    if drv:
        try:
            drv.quit()
            driver_closed = True
            logger.info("Navegador Edge cerrado por comando /cancel del usuario.")
        except Exception as e:
            logger.warning(f"Error cerrando Edge en /cancel: {e}")
        finally:
            context.user_data["active_driver"] = None

    card_fut = context.user_data.get("card_future")
    if card_fut and not card_fut.done():
        card_fut.cancel()
        context.user_data.pop("card_future", None)

    if driver_closed:
        msg = (
            "┌── [ 🛑 SESIÓN FINALIZADA // CANCEL ] ──┐\n"
            "│ • <b>ESTADO :</b> <code>PROCESO TERMINADO</code>\n"
            "│ • <b>EDGE   :</b> <code>NAVEGADOR CERRADO</code>\n"
            "└────────────────────────────────────────┘\n\n"
            "Se ha cerrado la ventana de Microsoft Edge con éxito.\n"
            "Para comenzar una nueva tramitación, envía <b>/start</b>."
        )
    else:
        msg = (
            "┌── [ 🛑 OPERACIÓN CANCELADA ] ──┐\n"
            "└────────────────────────────────┘\n\n"
            "Operación cancelada. Puedes escribir <b>/start</b> para comenzar de nuevo."
        )

    await update.message.reply_text(msg, parse_mode="HTML")
    return ConversationHandler.END


def main():
    """Función principal para arrancar el bot de Telegram."""
    logger.info("Iniciando Bot de Telegram Simyo...")
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start_command),
            CallbackQueryHandler(start_flow_callback, pattern="^start_flow$"),
        ],
        states={
            STATE_START: [
                CallbackQueryHandler(start_flow_callback, pattern="^start_flow$"),
            ],
            STATE_ASK_CARD_REUSE: [
                CallbackQueryHandler(handle_card_reuse_yes, pattern="^card_reuse_yes$"),
                CallbackQueryHandler(handle_card_reuse_no, pattern="^card_reuse_no$"),
            ],
            STATE_ASK_SAVE: [
                CallbackQueryHandler(handle_use_saved_callback, pattern="^use_saved$"),
                CallbackQueryHandler(handle_enter_new_callback, pattern="^enter_new$"),
                CallbackQueryHandler(handle_save_choice, pattern="^save_(yes|no)$"),
            ],
            STATE_EMAIL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_email)
            ],
            STATE_PHONE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_phone)
            ],
            STATE_DNI: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_dni)
            ],
            STATE_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name)
            ],
            STATE_BIRTHDATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_birthdate)
            ],
            STATE_ESIM_COUNT: [
                CallbackQueryHandler(handle_esim_count, pattern="^esim_[123]$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_esim_count),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_command),
            CommandHandler("start", start_command)
        ],
        allow_reentry=True
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, receive_card_data)
    )

    logger.info("Bot listo y escuchando mensajes en Telegram...")
    application.run_polling()


if __name__ == "__main__":
    main()