# selenium_worker.py - Automatización de Simyo con Microsoft Edge y Selenium
import os
import time
import secrets
import string
import logging
from typing import Callable, Optional

from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

from config import EDGE_BINARY_PATHS, SIMYO_URL, DEFAULT_ADDRESS

logger = logging.getLogger(__name__)

MAX_INTENTOS_TARJETA = 8
ESPERA_RESULTADO_PAGO = 15

MARCADORES_EXITO = (
    "solo te queda",
    "quedan 2 pasos",
    "quedan 1 paso",
    "quedan 3 pasos",
)
MARCADORES_INVALIDO = (
    "no es válida",
    "no es valida",
    "no ha ido bien",
    "ooops",
)


def generate_secure_password(length: int = 12) -> str:
    """Genera una contraseña segura que cumpla con los requisitos típicos (mayúscula, minúscula, número, especial)."""
    alphabet = string.ascii_letters + string.digits + "!@*#$"
    while True:
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.islower() for c in password)
                and any(c.isupper() for c in password)
                and any(c.isdigit() for c in password)
                and any(c in "!@*#$" for c in password)):
            return password


def get_edge_driver(headless: bool = False) -> webdriver.Edge:
    """Inicializa y devuelve una instancia de Microsoft Edge WebDriver."""
    opts = Options()

    # Buscar binario de Edge
    for path in EDGE_BINARY_PATHS:
        if os.path.exists(path):
            opts.binary_location = path
            break

    if headless:
        opts.add_argument("--headless=new")

    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--disable-notifications")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Edge(options=opts)
    driver.set_page_load_timeout(60)
    return driver


# ---------------------------------------------------------------------------
# HELPERS DE INTERACCIÓN
# ---------------------------------------------------------------------------

def _set_native_value(driver, element, value: str):
    """
    Escribe un valor en un input disparando los eventos que esperan los
    frameworks (React / Vue / jQuery) para que el formulario lo registre.
    """
    driver.execute_script("""
        const el = arguments[0];
        const val = arguments[1];
        const proto = el.tagName === 'TEXTAREA'
            ? window.HTMLTextAreaElement.prototype
            : window.HTMLInputElement.prototype;
        const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
        el.focus();
        setter.call(el, val);
        el.dispatchEvent(new Event('input', {bubbles: true}));
        el.dispatchEvent(new Event('change', {bubbles: true}));
        el.dispatchEvent(new KeyboardEvent('keyup', {bubbles: true}));
        el.dispatchEvent(new Event('blur', {bubbles: true}));
    """, element, value)


def _select_custom_option(driver, wait, select_id: str, value: str, label: Optional[str] = None):
    """
    Selecciona una opción de un <select> personalizado (myaddr-custom-select):
    abre el desplegable, intenta pulsar la opción visible equivalente y,
    como garantía, fija el value disparando 'change'.
    """
    el = wait.until(EC.presence_of_element_located((By.ID, select_id)))
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
    time.sleep(0.3)

    # 1) Intento "humano": clic en el desplegable y en su opción
    try:
        driver.execute_script("arguments[0].click();", el)
        time.sleep(0.4)
        texto = label if label else value
        opciones = driver.find_elements(
            By.XPATH,
            f"//select[@id='{select_id}']/following-sibling::*//li[normalize-space()='{texto}']"
            f" | //select[@id='{select_id}']/following-sibling::*//div[normalize-space()='{texto}']"
            f" | //select[@id='{select_id}']/following-sibling::*//span[normalize-space()='{texto}']"
        )
        visibles = [o for o in opciones if o.is_displayed()]
        if visibles:
            driver.execute_script("arguments[0].click();", visibles[0])
            time.sleep(0.3)
    except Exception as e:
        logger.debug(f"No se pudo clicar visualmente la opción {value} de {select_id}: {e}")

    # 2) Garantía: fijar el value y notificar el cambio
    driver.execute_script("""
        const sel = arguments[0];
        sel.value = arguments[1];
        sel.dispatchEvent(new Event('input', {bubbles: true}));
        sel.dispatchEvent(new Event('change', {bubbles: true}));
    """, el, value)
    time.sleep(0.4)

    valor_final = el.get_attribute("value")
    if valor_final != value:
        logger.warning(f"{select_id}: se esperaba '{value}' y quedó '{valor_final}'")
    else:
        logger.info(f"{select_id}: opción '{value}' seleccionada.")


def _find_element_by_candidates(driver, ids=(), names=(), autocompletes=()):
    """Busca un elemento por ids, luego por name y luego por autocomplete."""
    for i in ids:
        try:
            els = driver.find_elements(By.ID, i)
            if els:
                return els[0]
        except Exception:
            pass
    for n in names:
        try:
            els = driver.find_elements(By.CSS_SELECTOR, f"[name='{n}']")
            if els:
                return els[0]
        except Exception:
            pass
    for ac in autocompletes:
        try:
            els = driver.find_elements(By.CSS_SELECTOR, f"[autocomplete='{ac}']")
            if els:
                return els[0]
        except Exception:
            pass
    return None


def _set_value_any(driver, element, value: str):
    """Fija un valor tanto si el campo es un <select> como si es un input de texto."""
    tag = (element.tag_name or "").lower()
    if tag == "select":
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        time.sleep(0.1)
        val_str = str(value).strip()
        val_int = int(val_str) if val_str.isdigit() else None

        variantes = [val_str]
        if val_int is not None:
            variantes.append(str(val_int))
            variantes.append(val_str.zfill(2))
            if len(val_str) == 2 and val_int < 100:
                variantes.append(f"20{val_str}")
            elif len(val_str) == 4 and val_str.startswith("20"):
                variantes.append(val_str[2:])

        sel_obj = Select(element)
        for v in variantes:
            try:
                sel_obj.select_by_value(v)
                return
            except Exception:
                pass
            try:
                sel_obj.select_by_visible_text(v)
                return
            except Exception:
                pass

        # Intento JavaScript nativo recorriendo opciones
        for v in variantes:
            driver.execute_script("""
                const sel = arguments[0];
                const target = arguments[1];
                for (let i = 0; i < sel.options.length; i++) {
                    if (sel.options[i].value === target || sel.options[i].text.trim() === target) {
                        sel.selectedIndex = i;
                        sel.dispatchEvent(new Event('input', {bubbles: true}));
                        sel.dispatchEvent(new Event('change', {bubbles: true}));
                        return true;
                    }
                }
                return false;
            """, element, v)
    else:
        _set_native_value(driver, element, value)


def _is_card_input_present(driver) -> bool:
    """Verifica si en el contexto actual del driver están los inputs de tarjeta."""
    selectors = [
        (By.ID, "numero1"),
        (By.CSS_SELECTOR, "input[name='numero1']"),
        (By.CSS_SELECTOR, ".card-payment__card-number-input"),
        (By.XPATH, "//input[@autocomplete='cc-number' or contains(@class, 'card-number')]"),
    ]
    for by, sel in selectors:
        try:
            els = driver.find_elements(by, sel)
            if els and any(e.is_displayed() for e in els):
                return True
        except Exception:
            pass
    return False


def _ensure_card_context(driver) -> bool:
    """
    Busca el bloque de tarjeta en el contexto actual, en el documento principal
    y en todos los iframes (y sub-iframes). Si lo encuentra dentro de un iframe,
    deja el driver situado en dicho iframe. Devuelve True si lo encuentra.
    """
    # 1. Comprobar contexto actual
    try:
        if _is_card_input_present(driver):
            return True
    except Exception:
        pass

    # 2. Comprobar documento principal
    try:
        driver.switch_to.default_content()
        if _is_card_input_present(driver):
            return True
    except Exception:
        pass

    # 3. Buscar en iframes
    try:
        driver.switch_to.default_content()
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for iframe in iframes:
            try:
                driver.switch_to.frame(iframe)
                if _is_card_input_present(driver):
                    return True
                # Sub-iframes
                sub_iframes = driver.find_elements(By.TAG_NAME, "iframe")
                for sub in sub_iframes:
                    try:
                        driver.switch_to.frame(sub)
                        if _is_card_input_present(driver):
                            return True
                        driver.switch_to.parent_frame()
                    except Exception:
                        pass
                driver.switch_to.default_content()
            except Exception:
                driver.switch_to.default_content()
    except Exception:
        try:
            driver.switch_to.default_content()
        except Exception:
            pass

    return False


def _find_cvv_element(driver):
    """
    Localiza de forma exhaustiva el campo de CVV / CVC en la pasarela de pago.
    Empieza por el id exacto de Simyo (#cvvNumber) y sigue con múltiples estrategias:
    IDs comunes, nombres, autocompletes, proximidad al texto 'CVV' o
    'DÍGITOS DE SEGURIDAD', proximidad al checkbox 'Mostrar CVV',
    tipo password sin id password, y longitud máxima 3/4.
    """
    # 0. Ruta directa: ids exactos usados por la pasarela
    for exact_id in ("cvvNumber", "cvv", "cvv2"):
        try:
            els = driver.find_elements(By.ID, exact_id)
            vis = [e for e in els if e.is_displayed()]
            if vis:
                return vis[0]
        except Exception:
            pass

    # 1. Búsqueda por IDs y nombres comunes
    candidate_ids = [
        "cvv", "cvv2", "cv2", "cvc", "cvc2", "cvn",
        "securityCode", "security_code", "codigoSeguridad", "codigo_seguridad",
        "codSeguridad", "card_cvv", "cardCvv", "inputCvv", "txtCvv", "numCvv"
    ]
    for cid in candidate_ids:
        try:
            els = driver.find_elements(By.ID, cid)
            vis = [e for e in els if e.is_displayed()]
            if vis:
                return vis[0]
            if els:
                return els[0]
        except Exception:
            pass

    candidate_names = [
        "cvv", "cvv2", "cv2", "cvc", "cvc2", "cvn",
        "securityCode", "security_code", "codigoSeguridad", "codigo_seguridad",
        "codSeguridad", "card_cvv", "cardCvv"
    ]
    for cname in candidate_names:
        try:
            els = driver.find_elements(By.NAME, cname)
            vis = [e for e in els if e.is_displayed()]
            if vis:
                return vis[0]
            if els:
                return els[0]
        except Exception:
            pass

    # 2. Autocomplete de estándares web para tarjeta
    try:
        els = driver.find_elements(By.CSS_SELECTOR, "input[autocomplete='cc-csc'], input[autocomplete='csc']")
        vis = [e for e in els if e.is_displayed()]
        if vis:
            return vis[0]
        if els:
            return els[0]
    except Exception:
        pass

    # 3. Elemento inmediatamente anterior al checkbox o texto 'Mostrar CVV'
    xpath_mostrar = [
        "//label[contains(translate(., 'MOSTRAR', 'mostrar'), 'mostrar') and contains(translate(., 'CV', 'cv'), 'cv')]/preceding::input[not(@type='checkbox') and not(@type='hidden')][1]",
        "//*[contains(translate(text(), 'MOSTRAR', 'mostrar'), 'mostrar') and contains(translate(text(), 'CV', 'cv'), 'cv')]/preceding::input[not(@type='checkbox') and not(@type='hidden')][1]",
        "//input[@type='checkbox']/preceding::input[not(@type='checkbox') and not(@type='hidden')][1]",
    ]
    for xp in xpath_mostrar:
        try:
            els = driver.find_elements(By.XPATH, xp)
            vis = [e for e in els if e.is_displayed()]
            if vis:
                return vis[0]
            if els:
                return els[0]
        except Exception:
            pass

    # 4. Elemento inmediatamente posterior a la etiqueta de CVV / Dígitos de seguridad
    xpath_labels = [
        "//*[contains(translate(text(), 'cv', 'CV'), 'CVV') or contains(translate(text(), 'dígitos de seguridad', 'DÍGITOS DE SEGURIDAD'), 'DÍGITOS DE SEGURIDAD') or contains(translate(text(), 'seguridad', 'SEGURIDAD'), 'SEGURIDAD')]/following::input[not(@type='checkbox') and not(@type='hidden')][1]",
        "//*[contains(translate(., 'cv', 'CV'), 'CVV')]/ancestor::div[contains(@class, 'form') or contains(@class, 'group') or contains(@class, 'row') or contains(@class, 'field') or contains(@class, 'col')]//input[not(@type='checkbox') and not(@type='hidden')]",
    ]
    for xp in xpath_labels:
        try:
            els = driver.find_elements(By.XPATH, xp)
            vis = [e for e in els if e.is_displayed()]
            if vis:
                return vis[0]
            if els:
                return els[0]
        except Exception:
            pass

    # 5. Elemento input siguiente al select de año de caducidad
    try:
        els = driver.find_elements(By.XPATH, "//select[contains(@id, 'ano') or contains(@name, 'ano') or contains(@id, 'anio') or contains(@name, 'anio')]/following::input[not(@type='checkbox') and not(@type='hidden')][1]")
        vis = [e for e in els if e.is_displayed()]
        if vis:
            return vis[0]
        if els:
            return els[0]
    except Exception:
        pass

    # 6. Inputs con maxlength 3 o 4 (típicos de CVV) que no sean numero1..numero4
    try:
        els = driver.find_elements(By.XPATH, "//input[(@maxlength='3' or @maxlength='4') and not(contains(@id, 'numero')) and not(contains(@name, 'numero')) and not(@type='checkbox') and not(@type='hidden')]")
        vis = [e for e in els if e.is_displayed()]
        if vis:
            return vis[0]
        if els:
            return els[0]
    except Exception:
        pass

    # 7. Input tipo password en el bloque de tarjeta (que no sea contraseña de usuario)
    try:
        els = driver.find_elements(By.XPATH, "//input[@type='password' and not(contains(@id, 'password')) and not(contains(@id, 'clave')) and not(contains(@name, 'password')) and not(contains(@name, 'clave'))]")
        vis = [e for e in els if e.is_displayed()]
        if vis:
            return vis[0]
        if els:
            return els[0]
    except Exception:
        pass

    return None


def _write_cvv_robust(driver, cvv_el, cvv: str) -> bool:
    """
    Escribe el CVV de forma 100% fiable en el campo:
    1. Asegura visibilidad y foco
    2. Limpia completamente cualquier valor previo
    3. Escribe dígito a dígito simulando tecleo humano
    4. Si el valor no se refleja, usa setter nativo de JavaScript con todos los eventos de teclado
    5. Usa ActionChains como refuerzo adicional
    6. Verifica que el valor final en el DOM coincide exactamente con el CVV
    """
    digits_cvv = "".join(c for c in cvv if c.isdigit())
    if not digits_cvv:
        return False

    driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", cvv_el)
    time.sleep(0.2)

    # Quitar cualquier restricción readonly/disabled que pudiera tener
    try:
        driver.execute_script("arguments[0].removeAttribute('disabled'); arguments[0].removeAttribute('readonly');", cvv_el)
    except Exception:
        pass

    # Intentar hacer foco y clic
    try:
        cvv_el.click()
    except Exception:
        try:
            ActionChains(driver).move_to_element(cvv_el).click().perform()
        except Exception:
            driver.execute_script("arguments[0].focus(); arguments[0].click();", cvv_el)
    time.sleep(0.15)

    # Limpiar campo a conciencia
    try:
        cvv_el.clear()
    except Exception:
        pass
    try:
        cvv_el.send_keys(Keys.CONTROL + "a")
        cvv_el.send_keys(Keys.BACKSPACE)
    except Exception:
        pass
    try:
        driver.execute_script("arguments[0].value = '';", cvv_el)
    except Exception:
        pass
    time.sleep(0.1)

    # Método 1: send_keys con pequeñas pausas (tecleo humano)
    for ch in digits_cvv:
        try:
            cvv_el.send_keys(ch)
            time.sleep(0.06)
        except Exception:
            break

    # Comprobar si se ha escrito
    val = cvv_el.get_attribute("value") or ""
    if val != digits_cvv:
        logger.info(f"CVV tras send_keys es '{val}', aplicando inyección JavaScript robusta...")
        driver.execute_script("""
            const el = arguments[0];
            const val = arguments[1];
            el.focus();
            const proto = window.HTMLInputElement.prototype;
            const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
            if (setter) {
                setter.call(el, val);
            } else {
                el.value = val;
            }
            el.dispatchEvent(new Event('input', {bubbles: true, cancelable: true}));
            el.dispatchEvent(new Event('change', {bubbles: true, cancelable: true}));
            el.dispatchEvent(new KeyboardEvent('keydown', {key: val.slice(-1), bubbles: true}));
            el.dispatchEvent(new KeyboardEvent('keypress', {key: val.slice(-1), bubbles: true}));
            el.dispatchEvent(new KeyboardEvent('keyup', {key: val.slice(-1), bubbles: true}));
            el.dispatchEvent(new Event('blur', {bubbles: true}));
        """, cvv_el, digits_cvv)
        time.sleep(0.2)

    val = cvv_el.get_attribute("value") or ""
    if val != digits_cvv:
        logger.info(f"CVV tras JS es '{val}', reintentando con ActionChains...")
        try:
            ActionChains(driver).click(cvv_el).key_down(Keys.CONTROL).send_keys("a").key_up(Keys.CONTROL).send_keys(Keys.BACKSPACE).send_keys(digits_cvv).perform()
            time.sleep(0.2)
        except Exception as e_ac:
            logger.debug(f"ActionChains CVV fallback error: {e_ac}")

    final_val = cvv_el.get_attribute("value") or ""
    logger.info(f"Valor en campo CVV: '{final_val}' (esperado: '{digits_cvv}')")
    return final_val == digits_cvv


def _fill_card_form(driver, card_data: dict, wait=None, log_func=None) -> bool:
    """
    Rellena el formulario de tarjeta:
    - Escribe el número de tarjeta en numero1..numero4 (o en el input de tarjeta).
    - Si se incluyeron mes, año y CVV, los rellena también asegurando verificación del 100%.
    Devuelve True si todo lo requerido se completó con éxito.
    """
    _ensure_card_context(driver)

    numero = card_data["numero"]
    digits = "".join(c for c in numero if c.isdigit())
    grupos = [digits[i:i + 4] for i in range(0, len(digits), 4)]

    # 1. Escribir número de tarjeta en numero1..numero4
    n1_check = driver.find_elements(By.ID, "numero1") or driver.find_elements(By.CSS_SELECTOR, "input[name='numero1']")
    if n1_check:
        for idx, grupo in enumerate(grupos, start=1):
            campo = None
            try:
                campo = driver.find_element(By.ID, f"numero{idx}")
            except Exception:
                try:
                    campo = driver.find_element(By.CSS_SELECTOR, f"input[name='numero{idx}']")
                except Exception:
                    pass

            if campo:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", campo)
                time.sleep(0.1)
                try:
                    campo.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", campo)
                try:
                    campo.clear()
                except Exception:
                    pass
                for ch in grupo:
                    campo.send_keys(ch)
                    time.sleep(0.04)
                _set_native_value(driver, campo, grupo)
                time.sleep(0.15)
    else:
        # Campo único de tarjeta
        inputs_card = driver.find_elements(By.CSS_SELECTOR, "input[autocomplete='cc-number'], .card-payment__card-number-input, input[id*='card']")
        if inputs_card:
            campo = inputs_card[0]
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", campo)
            time.sleep(0.1)
            try:
                campo.click()
            except Exception:
                driver.execute_script("arguments[0].click();", campo)
            try:
                campo.clear()
            except Exception:
                pass
            for ch in digits:
                campo.send_keys(ch)
                time.sleep(0.04)
            _set_native_value(driver, campo, digits)

    logger.info("Número de tarjeta escrito en el input correspondiente.")

    # 2. Mes, año y CVV si están presentes
    mes = card_data.get("mes")
    ano = card_data.get("ano")
    cvv = card_data.get("cvv")

    if mes:
        mes_el = _find_element_by_candidates(
            driver,
            ids=["mes", "caducidadMes", "expiryMonth", "fechaCaducidadMes", "caducidad_mes", "month"],
            names=["mes", "caducidadMes", "expiryMonth", "month"],
            autocompletes=["cc-exp-month"],
        )
        if not mes_el:
            sels = driver.find_elements(By.XPATH, "//select[contains(@id, 'mes') or contains(@name, 'mes') or contains(@id, 'Mes')]")
            if sels:
                mes_el = sels[0]
        if mes_el:
            _set_value_any(driver, mes_el, mes)
            time.sleep(0.2)

    if ano:
        ano_el = _find_element_by_candidates(
            driver,
            ids=["ano", "anio", "caducidadAno", "caducidadAnio", "expiryYear", "fechaCaducidadAno", "year"],
            names=["ano", "anio", "caducidadAno", "expiryYear", "year"],
            autocompletes=["cc-exp-year"],
        )
        if not ano_el:
            sels = driver.find_elements(By.XPATH, "//select[contains(@id, 'ano') or contains(@name, 'ano') or contains(@id, 'anio') or contains(@name, 'anio')]")
            if sels:
                ano_el = sels[0]
        if ano_el:
            _set_value_any(driver, ano_el, ano)
            time.sleep(0.2)

    cvv_verified = True
    if cvv:
        # Ruta prioritaria: el id exacto del campo de seguridad
        cvv_el = None
        try:
            directos = driver.find_elements(By.ID, "cvvNumber")
            vis = [e for e in directos if e.is_displayed()]
            if vis:
                cvv_el = vis[0]
                logger.info("Campo CVV localizado por id exacto #cvvNumber.")
        except Exception:
            pass

        if not cvv_el:
            logger.info("Localizando campo de CVV en el formulario...")
            cvv_el = _find_cvv_element(driver)

        if cvv_el:
            cvv_ok = _write_cvv_robust(driver, cvv_el, cvv)
            if cvv_ok:
                logger.info("✅ CVV escrito y verificado al 100%.")
                if log_func:
                    log_func("🔒 CVV escrito y verificado al 100% en el campo de seguridad.")
            else:
                cvv_verified = False
                logger.warning(f"⚠️ El valor del CVV no coincide al 100%: actual='{cvv_el.get_attribute('value')}', esperado='{cvv}'")
                if log_func:
                    log_func("⚠️ Atención: Revisa el CVV en la pantalla de Edge.")
        else:
            cvv_verified = False
            logger.error("❌ No se encontró el campo input del CVV en el DOM.")
            if log_func:
                log_func("❌ Campo CVV no localizado en el DOM.")

    driver.execute_script("document.body.click();")
    time.sleep(0.5)
    return cvv_verified


def _click_selector(driver, wait, css_selector: str, timeout: int = 30):
    """Espera a que un elemento por selector sea clicable, lo centra y lo pulsa."""
    local_wait = WebDriverWait(driver, timeout)
    btn = local_wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, css_selector)))
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
    time.sleep(0.4)
    try:
        driver.execute_script("arguments[0].click();", btn)
    except Exception:
        ActionChains(driver).move_to_element(btn).click().perform()
    return btn


def _pulsar_pagar(driver, wait, log):
    """Pulsa el botón Pagar de la pasarela, con varios selectores de respaldo."""
    for sel in ("input#pay", "button#pay", "input[type='submit'][value='Pagar']", ".payment__btn"):
        try:
            btns = [b for b in driver.find_elements(By.CSS_SELECTOR, sel) if b.is_displayed()]
            if btns:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btns[0])
                time.sleep(0.3)
                try:
                    driver.execute_script("arguments[0].click();", btns[0])
                except Exception:
                    ActionChains(driver).move_to_element(btns[0]).click().perform()
                return True
        except Exception:
            pass
    try:
        _click_selector(driver, wait, "input#pay", timeout=15)
        return True
    except Exception as e_p:
        log(f"⚠️ No se pudo pulsar el botón Pagar: {e_p}")
        return False


def _cerrar_pasarela(driver, log) -> bool:
    """
    Cierra la ventana de pago seguro pulsando la 'x'
    (#button-close-secure-payment) para poder reintentar el proceso.
    """
    try:
        candidatos = driver.find_elements(By.ID, "button-close-secure-payment")
        if not candidatos:
            candidatos = driver.find_elements(By.CSS_SELECTOR, "a.js-close-secure-payment-button")
        visibles = [c for c in candidatos if c.is_displayed()]
        if visibles:
            objetivo = visibles[0]
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", objetivo)
            time.sleep(0.2)
            try:
                objetivo.click()
            except Exception:
                driver.execute_script("arguments[0].click();", objetivo)
            log("✖️ Pasarela de pago cerrada con la 'x'.")
            return True
        log("ℹ️ No se encontró el botón de cerrar la pasarela.")
    except Exception as e:
        logger.debug(f"Error cerrando la pasarela: {e}")
    return False


def _volver_al_formulario_tarjeta(driver, wait, log) -> bool:
    """
    Tras un rechazo o un cierre, vuelve al formulario de tarjeta:
    pulsa Pagar en el resumen, luego 'No guardar' y espera al bloque de tarjeta.
    """
    log("↩️ Volviendo al formulario de tarjeta (Pagar → No guardar)...")

    # 1. Pagar del resumen del pedido
    try:
        _click_selector(driver, wait, "button#nextButton[name='_eventId_purchase']", timeout=30)
    except Exception:
        try:
            alt = driver.find_elements(By.XPATH, "//button[@id='nextButton' or contains(normalize-space(), 'Pagar')]")
            vis = [b for b in alt if b.is_displayed()]
            if vis:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", vis[0])
                time.sleep(0.3)
                driver.execute_script("arguments[0].click();", vis[0])
        except Exception as e:
            logger.debug(f"Sin botón Pagar en el reintento: {e}")
    time.sleep(2)

    # 2. No guardar
    t_ng = time.time()
    while time.time() - t_ng < 30:
        try:
            ng = [b for b in driver.find_elements(By.ID, "no-guardar-tarjeta") if b.is_displayed()]
            if ng:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", ng[0])
                time.sleep(0.3)
                driver.execute_script("arguments[0].click();", ng[0])
                break
        except Exception:
            pass
        time.sleep(0.5)

    # 3. Esperar bloque de tarjeta
    t_card = time.time()
    while time.time() - t_card < 45:
        if _ensure_card_context(driver):
            return True
        time.sleep(1)
    return False


def _wait_payment_outcome(driver, baseline: str, timeout: int = ESPERA_RESULTADO_PAGO) -> str:
    """
    Espera el resultado del pago durante un máximo de `timeout` segundos.
    Devuelve 'success' si aparece el aviso de pasos restantes,
    'invalid' si Simyo rechaza la tarjeta, o 'timeout'.
    """
    fin = time.time() + timeout
    while time.time() < fin:
        try:
            src = (driver.page_source or "").lower()
            for marca in MARCADORES_EXITO:
                if marca in src and marca not in baseline:
                    return "success"
            for marca in MARCADORES_INVALIDO:
                if marca in src and marca not in baseline:
                    return "invalid"
        except Exception:
            pass
        time.sleep(0.4)
    return "timeout"


# ---------------------------------------------------------------------------
# FLUJO PRINCIPAL
# ---------------------------------------------------------------------------

def run_simyo_order(
    dni: str,
    firstname: str,
    lastname1: str,
    lastname2: str,
    email: str,
    phone: str,
    day: int,
    month: int,
    year: int,
    num_esims: int,
    status_callback: Optional[Callable[[str], None]] = None,
    screenshot_callback: Optional[Callable[[str], None]] = None,
    request_card_callback: Optional[Callable[[], Optional[dict]]] = None,
    card_invalid_callback: Optional[Callable[[int, dict], None]] = None,
    driver_callback: Optional[Callable[[webdriver.Edge], None]] = None,
    initial_card: Optional[dict] = None,
    keep_browser_open: bool = True,
    headless: bool = False
) -> dict:
    """
    Ejecuta el flujo completo de contratación de eSIMs en Simyo.
    """
    def log(msg: str):
        logger.info(msg)
        if status_callback:
            try:
                status_callback(msg)
            except Exception as e:
                logger.warning(f"Error en callback de estado: {e}")

    result = {
        "success": False,
        "message": "",
        "screenshot_path": None,
        "generated_password": None,
        "valid_card": None
    }

    driver = None
    try:
        log("🚀 Iniciando Microsoft Edge...")
        driver = get_edge_driver(headless=headless)
        if driver_callback:
            try:
                driver_callback(driver)
            except Exception as e_cb:
                logger.warning(f"Error en driver_callback: {e_cb}")
        wait = WebDriverWait(driver, 20)

        # 1. Cargar la página de tarifas móvil
        log(f"🌐 Entrando a {SIMYO_URL}...")
        driver.get(SIMYO_URL)
        time.sleep(3)

        # Gestionar banner de cookies si aparece
        try:
            cookie_btns = driver.find_elements(By.ID, "accept-all")
            if not cookie_btns:
                cookie_btns = driver.find_elements(By.CSS_SELECTOR, "button.js__cookies-all, #didomi-notice-agree-button")
            if cookie_btns:
                log("🍪 Aceptando cookies...")
                driver.execute_script("arguments[0].click();", cookie_btns[0])
                time.sleep(1.5)
        except Exception as e:
            logger.debug(f"Aviso de cookies no interactuable o ya cerrado: {e}")

        # 2. Localizar y clicar 'Comprar ya'
        log("🛒 Seleccionando tarifa y clicando en 'Comprar ya'...")
        wait.until(lambda d: d.find_elements(By.CSS_SELECTOR, "a.js-buyNow[href*='/simyo/cart']") or d.find_elements(By.CSS_SELECTOR, "a.js-buyNow"))

        buy_btns = driver.find_elements(By.CSS_SELECTOR, "a.js-buyNow[data-combined-tariff='tarifa-barata-hablar']")
        if not buy_btns:
            buy_btns = driver.find_elements(By.CSS_SELECTOR, "a.js-buyNow[href*='/simyo/cart']")

        target_buy = None
        for b in buy_btns:
            if b.is_displayed():
                target_buy = b
                break
        if not target_buy and buy_btns:
            target_buy = buy_btns[0]

        if not target_buy:
            raise Exception("No se encontró el botón 'Comprar ya' para la tarifa.")

        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target_buy)
        time.sleep(1)
        driver.execute_script("arguments[0].click();", target_buy)

        # 3. Esperar al modal de login/cliente y clicar 'No'
        log("⏳ Esperando ventana de confirmación '¿Eres cliente?' y clicando en 'No'...")
        wait.until(lambda d: d.find_elements(By.XPATH, "//button[contains(@onclick, 'notUserFixedSubmit') or (contains(@class, 'c-button') and normalize-space()='No')]"))
        time.sleep(1.5)

        no_btns = driver.find_elements(By.XPATH, "//button[contains(@onclick, 'notUserFixedSubmit') or (contains(@class, 'c-button') and normalize-space()='No')]")
        if no_btns:
            driver.execute_script("arguments[0].click();", no_btns[0])
            time.sleep(3)

        # 4. Ajustar cantidad de líneas (eSIMs)
        clicks_needed = max(0, min(3, num_esims) - 1)
        if clicks_needed > 0:
            log(f"➕ Ajustando cantidad de líneas: se requieren {clicks_needed} línea(s) adicional(es) para un total de {num_esims} eSIM(s)...")
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "button.js-counter-add")))
            time.sleep(1)

            for click_idx in range(clicks_needed):
                target_count = click_idx + 2
                log(f"➕ [Línea {target_count}/{num_esims}] Clicando en 'Añade una línea'...")

                counter_btns = [b for b in driver.find_elements(By.CSS_SELECTOR, "button.js-counter-add") if b.is_displayed()]
                if not counter_btns:
                    counter_btns = driver.find_elements(By.CSS_SELECTOR, "button.js-counter-add")

                if not counter_btns:
                    raise Exception("No se encontró el botón para añadir líneas adicionales.")

                add_btn = counter_btns[0]
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", add_btn)
                time.sleep(0.5)
                driver.execute_script("arguments[0].click();", add_btn)

                log(f"⏳ Esperando a que cargue la actualización a {target_count} eSIM(s)...")
                t_count = time.time()
                while time.time() - t_count < 10:
                    try:
                        counters = driver.find_elements(By.CSS_SELECTOR, ".cart__lines-controller.js-counter, .js-counter")
                        for c in counters:
                            if c.is_displayed():
                                num_el = c.find_element(By.CSS_SELECTOR, ".js-counter-number")
                                if num_el.text.strip() == str(target_count):
                                    break
                    except Exception:
                        pass
                    time.sleep(0.5)

                time.sleep(3.5)
                log(f"✅ Línea {target_count} añadida y cargada con éxito.")
        else:
            log("ℹ️ Configuración con 1 eSIM (no se requieren líneas adicionales).")

        # 5. Clicar en 'Tramitar pedido'
        log("📋 Clicando en 'Tramitar pedido'...")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "button.js-order-cart")))
        order_btns = driver.find_elements(By.CSS_SELECTOR, "button.js-order-cart")
        if not order_btns:
            raise Exception("No se encontró el botón 'Tramitar pedido'.")
        driver.execute_script("arguments[0].click();", order_btns[0])

        # 6. Configuración de líneas: Prepago, Número nuevo, eSIM
        log("⚙️ Seleccionando opciones: Prepago, Número nuevo y eSIM...")
        wait.until(lambda d: "newOrder" in d.current_url or d.find_elements(By.XPATH, "//label[contains(@for, 'consumo_prepago') or contains(., 'Prepago')]"))
        time.sleep(2)

        prepago_labels = driver.find_elements(By.XPATH, "//label[contains(@for, 'consumo_prepago') or contains(., 'Prepago')]")
        for p in prepago_labels:
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", p)
                driver.execute_script("arguments[0].click();", p)
                time.sleep(0.5)
            except Exception:
                pass

        nuevo_labels = driver.find_elements(By.XPATH, "//label[contains(@for, 'nuevo_numero_radio') or contains(., 'Número nuevo')]")
        for n in nuevo_labels:
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", n)
                driver.execute_script("arguments[0].click();", n)
                time.sleep(0.5)
            except Exception:
                pass

        esim_labels = driver.find_elements(By.XPATH, "//label[contains(@for, 'esim') or .//span[contains(text(), 'eSIM')]]")
        for e in esim_labels:
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", e)
                driver.execute_script("arguments[0].click();", e)
                time.sleep(0.5)
            except Exception:
                pass

        # Clicar Continuar
        log("➡️ Clicando en 'Continuar'...")
        next_btn = wait.until(EC.element_to_be_clickable((By.ID, "nextButton")))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_btn)
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", next_btn)
        time.sleep(3)

        # 7. Popup de aviso eSIM
        log("🔍 Comprobando aviso de seguridad eSIM...")
        try:
            popup_btns = driver.find_elements(By.XPATH, "//div[contains(@class, 'popup-content')]//a[contains(., 'Continuar') or contains(@onclick, 'popupEsimDeterrentMessage')]")
            if popup_btns:
                log("📌 Cerrando ventana de aviso eSIM...")
                driver.execute_script("arguments[0].click();", popup_btns[0])
                time.sleep(2)
            else:
                driver.execute_script("if (typeof $('#popupEsimDeterrentMessage') !== 'undefined') { $('#popupEsimDeterrentMessage').hide(); }")
        except Exception as e:
            logger.debug(f"Aviso de seguridad eSIM no presente o ya cerrado: {e}")

        # 8. Rellenar formulario de datos personales
        log("✍️ Rellenando formulario de datos personales...")
        wait.until(EC.presence_of_element_located((By.ID, "identification_type_select")))
        time.sleep(1)

        doc_select_elem = driver.find_element(By.ID, "identification_type_select")
        Select(doc_select_elem).select_by_value("02")
        time.sleep(0.5)

        doc_num_input = driver.find_element(By.ID, "document_number")
        doc_num_input.clear()
        doc_num_input.send_keys(dni.strip().upper())

        log("⏳ Esperando 3 segundos tras ingresar DNI...")
        time.sleep(3)

        fname_input = driver.find_element(By.ID, "firstname")
        fname_input.clear()
        fname_input.send_keys(firstname.strip())

        lname1_input = driver.find_element(By.ID, "lastname1")
        lname1_input.clear()
        lname1_input.send_keys(lastname1.strip())

        if lastname2:
            lname2_input = driver.find_element(By.ID, "lastname2")
            lname2_input.clear()
            lname2_input.send_keys(lastname2.strip())

        email_clean = email.strip()
        email_input = driver.find_element(By.ID, "email_address")
        email_input.clear()
        email_input.send_keys(email_clean)

        email_confirm_input = driver.find_element(By.ID, "email_address_confirm")
        email_confirm_input.clear()
        email_confirm_input.send_keys(email_clean)

        clean_phone = "".join(ch for ch in phone if ch.isdigit())
        if clean_phone.startswith("34") and len(clean_phone) == 11:
            clean_phone = clean_phone[2:]
        phone_input = driver.find_element(By.ID, "contact_phone1")
        phone_input.clear()
        phone_input.send_keys(clean_phone)

        Select(driver.find_element(By.ID, "birthdate_day")).select_by_value(str(int(day)))
        Select(driver.find_element(By.ID, "birthdate_month")).select_by_value(str(int(month) - 1))
        Select(driver.find_element(By.ID, "birthdate_year")).select_by_value(str(int(year)))

        # Dirección con Google Autocomplete
        log(f"📍 Introduciendo dirección: '{DEFAULT_ADDRESS}'...")
        addr_input = wait.until(EC.presence_of_element_located((By.ID, "gAddress")))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", addr_input)
        time.sleep(0.5)

        addr_input.click()
        addr_input.clear()
        time.sleep(0.3)
        for ch in DEFAULT_ADDRESS:
            addr_input.send_keys(ch)
            time.sleep(0.015)

        log("🔍 Esperando sugerencias de dirección en el autocompletado de Google...")
        t_pac = time.time()
        while time.time() - t_pac < 10:
            try:
                items = driver.find_elements(By.CSS_SELECTOR, ".pac-container .pac-item")
                if items and items[0].is_displayed():
                    break
            except Exception:
                pass
            time.sleep(0.3)

        time.sleep(1)

        pac_selected = False
        for attempt in range(3):
            try:
                fresh_items = driver.find_elements(By.CSS_SELECTOR, ".pac-container .pac-item")
                if fresh_items and fresh_items[0].is_displayed():
                    first_pac = fresh_items[0]
                    log(f"👉 Seleccionando la primera opción de la lista: '{first_pac.text}'...")
                    ActionChains(driver).move_to_element(first_pac).click().perform()
                    time.sleep(1)

                    still_open = any(p.is_displayed() for p in driver.find_elements(By.CSS_SELECTOR, ".pac-container .pac-item"))
                    if not still_open:
                        pac_selected = True
                        log("✅ Dirección seleccionada correctamente del desplegable.")
                        break
            except Exception as e_pac:
                logger.debug(f"Intento {attempt + 1} de selección de dirección: {e_pac}")
                time.sleep(0.5)

        if not pac_selected:
            log("⚠️ Intentando selección de respaldo mediante eventos de ratón en JS...")
            try:
                driver.execute_script("""
                    var items = document.querySelectorAll('.pac-container .pac-item');
                    if (items && items.length > 0) {
                        var item = items[0];
                        var rect = item.getBoundingClientRect();
                        var opts = {bubbles: true, cancelable: true, view: window, clientX: rect.x + 15, clientY: rect.y + 15};
                        item.dispatchEvent(new MouseEvent('mousedown', opts));
                        item.dispatchEvent(new MouseEvent('mouseup', opts));
                        item.dispatchEvent(new MouseEvent('click', opts));
                    }
                """)
                time.sleep(1)
            except Exception as e_js:
                logger.debug(f"Fallback JS pac item: {e_js}")
                addr_input.send_keys(Keys.ARROW_DOWN)
                time.sleep(0.5)
                addr_input.send_keys(Keys.ENTER)

        time.sleep(1)

        # ------------------------------------------------------------------
        # 8.b Número, planta y puerta de la dirección predeterminada
        # ------------------------------------------------------------------
        log("🏠 Completando número, planta y puerta de la dirección...")
        wait.until(EC.presence_of_element_located((By.ID, "numeroSelected")))
        time.sleep(0.8)

        _select_custom_option(driver, wait, "numeroSelected", "1", "1")
        _select_custom_option(driver, wait, "filterPlanta", "001", "1")
        _select_custom_option(driver, wait, "filterMano2", "A", "A")
        time.sleep(1)

        num_final = (driver.find_element(By.ID, "numeroSelected").get_attribute("value") or "").strip()
        planta_final = (driver.find_element(By.ID, "filterPlanta").get_attribute("value") or "").strip()
        mano_final = (driver.find_element(By.ID, "filterMano2").get_attribute("value") or "").strip()
        log(f"🏠 Dirección fijada -> número: '{num_final}', planta: '{planta_final}', puerta: '{mano_final}'")

        # Checkbox 'sinNumero'
        try:
            sin_num_list = driver.find_elements(By.ID, "sinNumero")
            if sin_num_list and sin_num_list[0].is_displayed():
                sin_num_cb = sin_num_list[0]
                if not sin_num_cb.is_selected():
                    driver.execute_script("arguments[0].click();", sin_num_cb)
                    time.sleep(0.5)
        except Exception as e:
            logger.debug(f"Checkbox sinNumero: {e}")

        # Clave y repite clave
        password = generate_secure_password(12)
        result["generated_password"] = password
        log("🔐 Asignando contraseña segura para la cuenta...")
        pwd_input = driver.find_element(By.ID, "password")
        pwd_input.clear()
        pwd_input.send_keys(password)

        pwd_conf_input = driver.find_element(By.ID, "password_confirm")
        pwd_conf_input.clear()
        pwd_conf_input.send_keys(password)

        # 9. Toggles de consentimiento y condiciones
        log("🔘 Activando switches de consentimiento y condiciones...")
        overlays = driver.find_elements(By.CSS_SELECTOR, "div.switch div.overlay")
        for idx in range(min(2, len(overlays))):
            o = overlays[idx]
            parent = o.find_element(By.XPATH, "..")
            span = parent.find_element(By.CSS_SELECTOR, "span.switched")
            for _ in range(5):
                driver.execute_script("arguments[0].click();", o)
                time.sleep(0.5)
                style = span.get_attribute("style") or ""
                cls = span.get_attribute("class") or ""
                if "left: 0px" in style or "off" not in cls:
                    break

        # 10. Clicar en botón final Continuar
        log("🚀 Clicando botón final 'Continuar'...")
        final_btn = wait.until(EC.element_to_be_clickable((By.ID, "nextButton")))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", final_btn)
        time.sleep(1)
        driver.execute_script("arguments[0].click();", final_btn)

        # ------------------------------------------------------------------
        # 11. Página de pago: Pagar -> No guardar -> tarjeta -> Pagar (bucle)
        # ------------------------------------------------------------------
        log("⏳ Esperando la página de pago y confirmación...")
        time.sleep(2)

        log("➡️ Pulsando 'Pagar' en el resumen del pedido...")
        try:
            _click_selector(driver, wait, "button#nextButton[name='_eventId_purchase']", timeout=40)
        except Exception:
            pay_btns = driver.find_elements(By.XPATH, "//button[@id='nextButton' or contains(normalize-space(), 'Pagar')]")
            if pay_btns:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", pay_btns[0])
                time.sleep(0.3)
                driver.execute_script("arguments[0].click();", pay_btns[0])
            else:
                raise

        log("🔍 Esperando botón 'No guardar'...")
        no_guardar_btn = None
        t_ng = time.time()
        while time.time() - t_ng < 40:
            try:
                ng_list = driver.find_elements(By.ID, "no-guardar-tarjeta") or \
                          driver.find_elements(By.XPATH, "//button[contains(normalize-space(), 'No guardar') or contains(@id, 'no-guardar')]") or \
                          driver.find_elements(By.CSS_SELECTOR, "button[name='_eventId_purchase'].btn.orangeButton")
                visibles = [b for b in ng_list if b.is_displayed()]
                if visibles:
                    no_guardar_btn = visibles[-1]
                    break
            except Exception:
                pass
            time.sleep(0.5)

        if no_guardar_btn:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", no_guardar_btn)
            time.sleep(0.3)
            try:
                driver.execute_script("arguments[0].click();", no_guardar_btn)
            except Exception:
                ActionChains(driver).move_to_element(no_guardar_btn).click().perform()
            log("💳 Botón 'No guardar' pulsado.")
        else:
            log("ℹ️ No se detectó botón 'No guardar' (o ya avanzó automáticamente).")

        log("⏳ Esperando a que aparezca el bloque de tarjeta en pantalla...")
        card_ready = False
        t_card = time.time()
        while time.time() - t_card < 45:
            if _ensure_card_context(driver):
                card_ready = True
                break
            time.sleep(1)

        if not card_ready:
            raise Exception("No apareció el bloque de tarjeta tras pulsar 'No guardar'.")

        log("💳 ¡Bloque de tarjeta detectado y listo en pantalla!")
        time.sleep(1)

        tarjeta_valida = None

        for intento in range(1, MAX_INTENTOS_TARJETA + 1):
            if intento > 1:
                if not _volver_al_formulario_tarjeta(driver, wait, log):
                    raise Exception("No se pudo volver al formulario de tarjeta tras el rechazo.")
                time.sleep(1)

            # 1. Obtener datos de la tarjeta
            card_data = None
            if intento == 1 and initial_card and initial_card.get("cvv"):
                card_data = initial_card
                log(f"💳 Usando la tarjeta guardada terminada en {card_data['numero'][-4:]}.")
            else:
                log("📨 Solicitando en Telegram los datos de la tarjeta...")
                try:
                    card_data = request_card_callback() if request_card_callback else None
                except Exception as e_card:
                    logger.error(f"Error obteniendo datos de tarjeta: {e_card}")
                    card_data = None

                while card_data and not card_data.get("cvv") and request_card_callback:
                    log("⚠️ La tarjeta no trae CVV, se solicita de nuevo...")
                    try:
                        card_data = request_card_callback()
                    except Exception:
                        card_data = None

            if not card_data:
                raise Exception("No se recibieron los datos de la tarjeta a tiempo.")

            # 2. Escribir la tarjeta (el CVV va forzado en #cvvNumber)
            log(f"✍️ Escribiendo tarjeta terminada en {card_data['numero'][-4:]} y datos de pago...")
            cvv_ok = _fill_card_form(driver, card_data, wait=wait, log_func=log)

            if not cvv_ok:
                log("⚠️ El CVV no quedó confirmado. Reintentando escritura directa en #cvvNumber...")
                try:
                    directo = [e for e in driver.find_elements(By.ID, "cvvNumber") if e.is_displayed()]
                    if directo:
                        _write_cvv_robust(driver, directo[0], card_data["cvv"])
                except Exception as e_cvv:
                    logger.debug(f"Reintento directo de CVV: {e_cvv}")

            log("✅ Datos de tarjeta introducidos en el formulario.")
            time.sleep(0.5)

            # 3. Pulsar Pagar y esperar el resultado
            baseline = (driver.page_source or "").lower()
            log("🚀 Pulsando 'Pagar'...")
            if not _pulsar_pagar(driver, wait, log):
                raise Exception("No se pudo pulsar el botón Pagar.")

            outcome = _wait_payment_outcome(driver, baseline, timeout=ESPERA_RESULTADO_PAGO)

            if outcome == "success":
                tarjeta_valida = card_data
                log("🎉 Pago aceptado: la tarjeta es válida (¡Solo te quedan 2 pasos!).")
                break

            if outcome == "invalid":
                log(f"❌ Tarjeta rechazada por Simyo (intento {intento}/{MAX_INTENTOS_TARJETA}).")
                if card_invalid_callback:
                    try:
                        card_invalid_callback(intento, card_data)
                    except Exception as e_inv:
                        logger.warning(f"Error en card_invalid_callback: {e_inv}")
                time.sleep(2)
                continue

            # outcome == "timeout"
            log(f"⏱️ Sin respuesta en {ESPERA_RESULTADO_PAGO} s. Cerrando la pasarela con la 'x' y reintentando...")
            if card_invalid_callback:
                try:
                    card_invalid_callback(intento, card_data)
                except Exception as e_inv:
                    logger.warning(f"Error en card_invalid_callback: {e_inv}")
            _cerrar_pasarela(driver, log)
            time.sleep(2)
            continue

        if not tarjeta_valida:
            raise Exception("Ninguna tarjeta fue aceptada por la pasarela de pago de Simyo.")

        result["valid_card"] = {
            "numero": tarjeta_valida["numero"],
            "mes": tarjeta_valida["mes"],
            "ano": tarjeta_valida["ano"],
            "cvv": tarjeta_valida["cvv"],
        }

        log("⏳ Esperando la confirmación final de Simyo...")
        time.sleep(8)

        screenshot_filename = f"simyo_result_{int(time.time())}.png"
        screenshot_path = os.path.abspath(screenshot_filename)
        driver.save_screenshot(screenshot_path)
        result["screenshot_path"] = screenshot_path
        if screenshot_callback:
            try:
                screenshot_callback(screenshot_path)
            except Exception as e:
                logger.warning(f"Error en callback de captura: {e}")

        result["success"] = True
        result["message"] = "¡Proceso de solicitud completado correctamente en la web de Simyo!"
        log("✅ " + result["message"])

    except Exception as e:
        logger.exception("Error durante la automatización de Simyo")
        result["success"] = False
        result["message"] = f"Error en la automatización: {str(e)}"
        log(f"❌ {result['message']}")
        if driver:
            try:
                err_screenshot = f"simyo_error_{int(time.time())}.png"
                err_path = os.path.abspath(err_screenshot)
                driver.save_screenshot(err_path)
                result["screenshot_path"] = err_path
                if screenshot_callback:
                    screenshot_callback(err_path)
            except Exception:
                pass
    finally:
        if driver and not keep_browser_open:
            try:
                driver.quit()
            except Exception:
                pass
        elif driver and keep_browser_open:
            logger.info("Navegador Edge mantenido abierto por solicitud (esperando comando /cancel en Telegram).")

    return result