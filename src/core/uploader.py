"""Upload para TikTok com múltiplas contas e navegadores (cookies por conta).

Anti-detecção: undetected-chromedriver no Chrome/Brave, patches JS, delays humanos, nunca headless.
"""
from __future__ import annotations

import json
import logging
import os
import random
import re
import time
from datetime import datetime
from pathlib import Path

# Standard Selenium (used for Firefox / Edge)
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from webdriver_manager.firefox import GeckoDriverManager
from webdriver_manager.microsoft import EdgeChromiumDriverManager

# undetected-chromedriver — used for Chrome & Brave
try:
    import undetected_chromedriver as uc
    _UC_AVAILABLE = True
except ImportError:
    _UC_AVAILABLE = False
    # Fallback to plain selenium Chrome if uc is missing
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.chrome.service import Service as ChromeService
    from webdriver_manager.chrome import ChromeDriverManager

# Always import selenium webdriver for Firefox/Edge
from selenium import webdriver

logger = logging.getLogger("DarkAgent.Uploader")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cookies_dir() -> Path:
    """Retorna (e cria) o diretório dos cookies por conta."""
    from config.paths import ACCOUNTS_DIR
    ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)
    return ACCOUNTS_DIR


def _cookies_path(account_name: str) -> Path:
    safe = re.sub(r"[^\w\-]", "_", account_name)
    return _cookies_dir() / f"cookies_{safe}.txt"


def _accounts_index() -> Path:
    return _cookies_dir() / "accounts.json"


# ---------------------------------------------------------------------------
# Account registry
# ---------------------------------------------------------------------------

def list_accounts() -> list[dict]:
    """Lista as contas: [{'name': str, 'cookies_path': str}, ...]."""
    idx = _accounts_index()
    if not idx.exists():
        return []
    try:
        data = json.loads(idx.read_text(encoding="utf-8"))
        # Only return accounts whose cookie file actually exists
        return [a for a in data if Path(a["cookies_path"]).exists()]
    except Exception:
        return []


def _save_accounts(accounts: list[dict]) -> None:
    _accounts_index().write_text(
        json.dumps(accounts, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def add_account(name: str, cookies_path: str) -> None:
    accounts = list_accounts()
    accounts = [a for a in accounts if a["name"] != name]  # replace if exists
    accounts.append({"name": name, "cookies_path": str(cookies_path)})
    _save_accounts(accounts)


def remove_account(name: str) -> None:
    cp = _cookies_path(name)
    if cp.exists():
        cp.unlink(missing_ok=True)
    accounts = [a for a in list_accounts() if a["name"] != name]
    _save_accounts(accounts)


# ---------------------------------------------------------------------------
# Anti-detection helpers
# ---------------------------------------------------------------------------

# JS injected into every page to mask Selenium/WebDriver fingerprints
_STEALTH_JS = """
// 1. Remove navigator.webdriver flag
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

// 2. Spoof plugins — a real browser always has some
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const arr = [1, 2, 3, 4, 5];
        arr.__proto__ = PluginArray.prototype;
        return arr;
    }
});

// 3. Spoof languages
Object.defineProperty(navigator, 'languages', {get: () => ['pt-BR', 'pt', 'en-US', 'en']});

// 4. Spoof hardware concurrency (real CPUs)
Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});

// 5. Spoof device memory
Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});

// 6. Mock chrome runtime so the page thinks it's a real Chrome
window.chrome = {runtime: {}};

// 7. Remove automation-specific permission overrides
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) =>
    parameters.name === 'notifications'
        ? Promise.resolve({state: Notification.permission})
        : originalQuery(parameters);

// 8. Auto-remove TikTok 'Joyride' tutorial overlays that intercept clicks
setInterval(() => {
    const blockers = document.querySelectorAll('.react-joyride__overlay, .react-joyride__spotlight, .react-joyride__tooltip');
    blockers.forEach(el => {
        el.style.display = 'none';
        el.style.pointerEvents = 'none';
    });
}, 500);
"""


def _apply_stealth_js(driver) -> None:
    """Executa o JS anti-fingerprint na página atual."""
    try:
        driver.execute_script(_STEALTH_JS)
    except Exception as exc:
        logger.debug(f"stealth JS injection skipped: {exc}")


def _apply_stealth_cdp(driver) -> None:
    """Aplica patches via Chrome DevTools Protocol (só com uc/Chrome)."""
    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": _STEALTH_JS},
        )
        logger.debug("CDP stealth script registered.")
    except Exception as exc:
        logger.debug(f"CDP stealth patch skipped: {exc}")


def _human_delay(min_s: float = 0.8, max_s: float = 2.2) -> None:
    """Espera um tempo aleatório, imitando um humano."""
    time.sleep(random.uniform(min_s, max_s))


# ---------------------------------------------------------------------------
# Driver factory
# ---------------------------------------------------------------------------

_BROWSER_APP_DIRS = {
    "chrome": (os.path.join("Google", "Chrome", "Application"), "chrome.exe"),
    "brave": (os.path.join("BraveSoftware", "Brave-Browser", "Application"), "brave.exe"),
}


def _find_browser_path(browser_name: str) -> str | None:
    """Localiza o executável do Chrome/Brave no Windows."""
    app_dir, exe = _BROWSER_APP_DIRS[browser_name]
    candidates = []
    for env_key in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        val = os.environ.get(env_key, "")
        if val:
            candidates.append(os.path.join(val, app_dir, exe))
    return next((p for p in candidates if os.path.exists(p)), None)


def _browser_major_version(exe_path: str) -> int | None:
    """Versão major do Chromium lida das pastas de versão ao lado do .exe.

    Não roda `exe --version`: no Windows isso abre uma janela extra do navegador.
    """
    versions = [
        int(m.group(1))
        for d in Path(exe_path).parent.iterdir()
        if d.is_dir() and (m := re.match(r"(\d+)\.\d+\.\d+\.\d+$", d.name))
    ]
    return max(versions) if versions else None


def _uc_options(binary_location: str | None):
    """Monta ChromeOptions novas (o uc não aceita reaproveitar o mesmo objeto)."""
    options = uc.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    # Extra args that help bypass bot-score checks
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-notifications")
    options.add_argument("--lang=pt-BR")
    # Evita abas de boas-vindas/onboarding num perfil novo
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    if binary_location:
        options.binary_location = binary_location
    return options


def _close_extra_tabs(driver) -> None:
    """Fecha abas além da primeira (welcome do Brave, restore etc.)."""
    try:
        handles = driver.window_handles
        for h in handles[1:]:
            driver.switch_to.window(h)
            driver.close()
        driver.switch_to.window(handles[0])
    except Exception as exc:
        logger.debug(f"close extra tabs skipped: {exc}")


def _start_with_selenium_manager(start, service_cls, manager_cls):
    """Inicia o driver via Selenium Manager (embutido no selenium); webdriver_manager é reserva.

    O webdriver_manager 4.x baixa o msedgedriver de msedgedriver.azureedge.net, que saiu do ar.
    """
    try:
        return start(service_cls())  # Service sem path → Selenium Manager resolve o driver
    except Exception as exc:
        logger.warning(f"Selenium Manager falhou ({exc}); tentando webdriver_manager…")
    return start(service_cls(manager_cls().install()))


def _make_driver(browser_name: str, headless: bool = False):
    """Cria o WebDriver do navegador pedido.

    Chrome/Brave usam undetected-chromedriver quando disponível; Firefox/Edge usam Selenium padrão.
    """
    browser_name = browser_name.lower()

    # ── Firefox ─────────────────────────────────────────────────────────
    if browser_name == "firefox":
        options = FirefoxOptions()
        options.set_preference("dom.webdriver.enabled", False)
        options.set_preference("useAutomationExtension", False)
        if headless:
            options.add_argument("--headless")
        driver = _start_with_selenium_manager(
            lambda svc: webdriver.Firefox(service=svc, options=options),
            FirefoxService, GeckoDriverManager,
        )
        _apply_stealth_js(driver)
        return driver

    # ── Edge ────────────────────────────────────────────────────────────
    if browser_name == "edge":
        options = EdgeOptions()
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--start-maximized")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        if headless:
            options.add_argument("--headless=new")
        driver = _start_with_selenium_manager(
            lambda svc: webdriver.Edge(service=svc, options=options),
            EdgeService, EdgeChromiumDriverManager,
        )
        _apply_stealth_cdp(driver)
        return driver

    # ── Chrome / Brave — undetected-chromedriver ────────────────────────
    if _UC_AVAILABLE:
        brave_path = None
        if browser_name == "brave":
            brave_path = _find_browser_path("brave")
            if brave_path:
                logger.info(f"Brave found at: {brave_path}")
            else:
                logger.warning("Brave binary not found — falling back to Chrome.")

        # Versão certa já na 1ª tentativa: um retry por mismatch deixa a janela
        # da tentativa falha aberta (= dois navegadores).
        exe_path = brave_path or _find_browser_path("chrome")
        version_main = _browser_major_version(exe_path) if exe_path else None
        logger.info(f"Browser major version: {version_main}")

        try:
            driver = uc.Chrome(
                options=_uc_options(brave_path),
                headless=headless,          # uc handles headless safely
                version_main=version_main,  # None → auto-detect from installed Chrome
                use_subprocess=True,        # avoids process zombie issues on Windows
            )
        except Exception as e:
            m = re.search(r"Current browser version is (\d+)", str(e))
            if not m:
                raise
            actual_version = int(m.group(1))
            logger.info(f"Version mismatch detected! Retrying undetected_chromedriver with version_main={actual_version}")
            driver = uc.Chrome(
                options=_uc_options(brave_path),
                headless=headless,
                version_main=actual_version,
                use_subprocess=True,
            )

        _close_extra_tabs(driver)
        # Register stealth JS to run on every new page (CDP-level)
        _apply_stealth_cdp(driver)
        logger.info(f"[uc] {'Brave' if brave_path else 'Chrome'} driver started (headless={headless}).")
        return driver

    # ── Fallback: plain Selenium Chrome (uc not installed) ──────────────
    logger.warning("undetected-chromedriver not available — using plain Selenium Chrome.")
    from selenium.webdriver.chrome.options import Options as ChromeOptions  # noqa: PLC0415
    from selenium.webdriver.chrome.service import Service as ChromeService  # noqa: PLC0415
    from webdriver_manager.chrome import ChromeDriverManager  # noqa: PLC0415

    options = ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    if headless:
        options.add_argument("--headless=new")

    if browser_name == "brave":
        brave_path = _find_browser_path("brave")
        if brave_path:
            options.binary_location = brave_path

    driver = _start_with_selenium_manager(
        lambda svc: webdriver.Chrome(service=svc, options=options),
        ChromeService, ChromeDriverManager,
    )
    _apply_stealth_cdp(driver)
    return driver


# ---------------------------------------------------------------------------
# tiktok-uploader 1.1.5 patches
# ---------------------------------------------------------------------------

def _safe_remove_cookies_window(driver) -> None:
    """Fecha/remove o banner de cookies do TikTok sem nunca levantar.

    A 1.1.5 quebra o upload inteiro quando o TikTok muda o DOM do banner.
    """
    from selenium.webdriver.common.by import By

    try:
        banners = driver.find_elements(By.TAG_NAME, "tiktok-cookie-banner")
        if not banners:
            return
        try:
            root = banners[0].shadow_root
            buttons = [b for b in root.find_elements(By.CSS_SELECTOR, "button") if b.is_displayed()]
            if buttons:
                buttons[0].click()  # 1º botão = "Recusar" (mesmo critério da lib)
                return
        except Exception as exc:
            logger.debug(f"cookie banner click failed, removing it: {exc}")
        driver.execute_script(
            "document.querySelectorAll('tiktok-cookie-banner').forEach(e => e.remove());"
        )
    except Exception as exc:
        logger.debug(f"cookie banner handling skipped: {exc}")


# ── Etapas do TikTok Studio (DOM de 10/2026, UI em PT ou EN) ──────────────

_SCHEDULE_BOX = "[data-e2e='schedule_container']"
_POST_BUTTON = "button[data-e2e='post_video_button']"
# Popup "Continuar publicando?" → botão primário ("Publicar agora" / "Post now" / "Programar")
_MODAL_PRIMARY = ".common-modal-footer button.TUXButton--primary"
_POSTED_TEXTS = (
    "your video has been uploaded", "video published", "your video has been scheduled",
    "vídeo foi publicado", "vídeo publicado", "publicação foi programada",
    "vídeo foi programado", "foi agendad",
)


def _wait_until(fn, timeout: float, interval: float = 0.5):
    """Repete fn() até retornar algo truthy ou estourar o timeout. Retorna o valor ou None."""
    end = time.time() + timeout
    while time.time() < end:
        try:
            v = fn()
            if v:
                return v
        except Exception:
            pass
        time.sleep(interval)
    return None


_HASHTAG_ITEMS = ".mention-list-popover .hashtag-suggestion-item"
_HASHTAG_TOPIC = ".hash-tag-topic"


def _real_click(driver, el) -> None:
    """Clique de mouse de verdade (o React do TikTok ignora alguns .click() via JS)."""
    from selenium.webdriver.common.action_chains import ActionChains

    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
    time.sleep(0.2)
    try:
        el.click()
    except Exception:
        try:
            ActionChains(driver).move_to_element(el).click().perform()
        except Exception:
            driver.execute_script("arguments[0].click();", el)


def _type_hashtag(driver, editor, word: str) -> None:
    """Digita #tag e escolhe a sugestão idêntica do TikTok (vira hashtag de verdade).

    Sem sugestão exata em ~6 s a tag fica como texto, pra não trocar por outra.
    """
    from selenium.webdriver.common.by import By

    editor.send_keys(word)
    wanted = word.lower()

    def exact_item():
        for item in driver.find_elements(By.CSS_SELECTOR, _HASHTAG_ITEMS):
            topic = item.find_elements(By.CSS_SELECTOR, _HASHTAG_TOPIC)
            if topic and topic[0].get_attribute("textContent").strip().lower() == wanted:
                return item
        return None

    item = _wait_until(exact_item, 6, interval=0.4)
    if item is None:
        logger.info(f"Hashtag {word}: sem sugestão exata, fica como texto")
        editor.send_keys(" ")
        return
    _real_click(driver, item)
    _wait_until(lambda: not driver.find_elements(By.CSS_SELECTOR, _HASHTAG_ITEMS), 3)
    # O TikTok costuma inserir espaço após escolher a hashtag; garante 1 só
    if not editor.text.endswith((" ", "\u00a0")):
        editor.send_keys(" ")


def _type_description(driver, editor, description: str) -> None:
    """Limpa o editor e digita a descrição; cada #tag separada para escolher a sugestão."""
    from selenium.webdriver.common.keys import Keys

    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", editor)
    try:
        editor.click()
    except Exception:
        driver.execute_script("arguments[0].focus();", editor)
    editor.send_keys(Keys.CONTROL, "a")
    editor.send_keys(Keys.BACKSPACE)
    _wait_until(lambda: editor.text.strip() == "", 5)

    text_buf = []
    for token in re.split(r"(\s+)", description.strip()):
        if token.startswith("#") and len(token) > 1:
            if text_buf:
                editor.send_keys("".join(text_buf))
                text_buf = []
            _type_hashtag(driver, editor, token)
        elif token.isspace():
            if text_buf or not editor.text.endswith((" ", "\u00a0")):
                text_buf.append(" " if "\n" not in token else token)
        else:
            text_buf.append(token)
    if text_buf:
        editor.send_keys("".join(text_buf).rstrip())


def _studio_set_description(driver, description: str, video_name: str = "") -> None:
    """Digita a descrição e confere; repete até 3x se o TikTok sobrescrever o texto.

    O TikTok preenche o nome do arquivo no editor com atraso e apaga o que já foi digitado.
    """
    from selenium.webdriver.common.by import By

    if not description:
        return
    logger.info("Setting description")

    def find_editor():
        return driver.find_element(By.CSS_SELECTOR, "div[contenteditable='true']")

    editor = _wait_until(find_editor, 30)
    if editor is None:
        raise RuntimeError("Editor de descrição não encontrado")
    # Espera o prefill (nome do arquivo) aparecer e assentar antes de mexer
    if video_name:
        _wait_until(lambda: video_name[:20] in find_editor().text, 20)
    time.sleep(1.5)

    first_word = description.split()[0][:15]
    for attempt in range(1, 4):
        editor = find_editor()
        _type_description(driver, editor, description)
        time.sleep(2)  # dá tempo de um prefill atrasado sobrescrever, se for acontecer
        current = find_editor().text
        if first_word in current:
            return
        logger.warning(f"Descrição sobrescrita (tentativa {attempt}/3): {current[:60]!r}")
        time.sleep(3)
    raise RuntimeError(f"Descrição não foi preenchida (editor: {find_editor().text[:80]!r})")


def _schedule_fields_text(driver) -> str:
    """Texto visível + values dos inputs do bloco 'Quando publicar'."""
    return driver.execute_script(
        "const b = document.querySelector(arguments[0]); if (!b) return '';"
        "return b.innerText + ' ' + [...b.querySelectorAll('input')].map(i => i.value).join(' ');",
        _SCHEDULE_BOX,
    ) or ""


def _schedule_matches(driver, local_dt: datetime) -> bool:
    """True só se 'Programar' está marcado e os campos têm exatamente a data e a hora pedidas."""
    from selenium.webdriver.common.by import By

    try:
        box = driver.find_element(By.CSS_SELECTOR, _SCHEDULE_BOX)
        if not box.find_element(By.CSS_SELECTOR, "input[name='postSchedule'][value='schedule']").is_selected():
            return False
        values = {i.get_attribute("value") for i in box.find_elements(By.CSS_SELECTOR, _PICKER_INPUTS)}
    except Exception:
        return False
    return {local_dt.strftime("%Y-%m-%d"), local_dt.strftime("%H:%M")} <= values


_PICKER_INPUTS = "input.TUXTextInputCore-input"
_TIME_POPUP = ".tiktok-timepicker-time-picker-container"
# O onClick fica no <span> (não no div do item): clique no div não chega nele
_TIME_SPANS = ("span.tiktok-timepicker-left", "span.tiktok-timepicker-right")  # horas, minutos

# Rola só a lista do relógio (rolar a página fecha o popup)
_JS_SCROLL_IN_LIST = """
const el = arguments[0], box = el.closest('.tiktok-timepicker-time-scroll-container');
if (box) box.scrollTop = el.offsetTop - box.clientHeight / 2 + el.offsetHeight / 2;
"""
_CAL_POPUP = "div[class*='calendar-wrapper']"
_CAL_DAYS = "span[class*='day'][class*='valid']"
_CAL_ARROWS = "span[class*='arrow']"  # 1ª = mês anterior, última = próximo


def _js_click(driver, el) -> None:
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();", el)


def _studio_pick_date(driver, date_input, local_dt: datetime) -> None:
    """Abre o calendário e clica no dia (avança 1 mês se preciso; agenda máx. 10 dias)."""
    from selenium.webdriver.common.by import By

    target = local_dt.strftime("%Y-%m-%d")
    if date_input.get_attribute("value") == target:
        return
    current_month = int(date_input.get_attribute("value").split("-")[1])
    _js_click(driver, date_input)
    cal = _wait_until(
        lambda: (driver.find_elements(By.CSS_SELECTOR, _CAL_POPUP) or [None])[-1],
        10,
    )
    if cal is None:
        raise RuntimeError("Calendário não abriu")
    if local_dt.month != current_month:
        arrows = cal.find_elements(By.CSS_SELECTOR, _CAL_ARROWS)
        _js_click(driver, arrows[-1])  # sempre para frente (agendamento ≤ 10 dias)
        time.sleep(0.8)
    day = next(
        (d for d in cal.find_elements(By.CSS_SELECTOR, _CAL_DAYS)
         if d.get_attribute("textContent").strip() == str(local_dt.day)),
        None,
    )
    if day is None:
        raise RuntimeError(f"Dia {local_dt.day} não disponível no calendário")
    _js_click(driver, day)
    if not _wait_until(lambda: date_input.get_attribute("value") == target, 5):
        raise RuntimeError(f"Data ficou {date_input.get_attribute('value')!r}, esperado {target}")


def _close_time_popup(driver) -> None:
    """Fecha o relógio clicando fora dele (título 'Quando publicar'); ESC como reserva."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys

    if not driver.find_elements(By.CSS_SELECTOR, _TIME_POPUP):
        return
    try:
        _real_click(driver, driver.find_element(By.CSS_SELECTOR, f"{_SCHEDULE_BOX} .scheduled-title-container"))
    except Exception:
        pass
    if not _wait_until(lambda: not driver.find_elements(By.CSS_SELECTOR, _TIME_POPUP), 3):
        try:
            driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        except Exception:
            pass
    time.sleep(0.5)


def _studio_pick_time(driver, time_input, local_dt: datetime) -> None:
    """Abre o relógio e clica na hora e no minuto (colunas 00–23 e 00–55 de 5 em 5)."""
    from selenium.webdriver.common.by import By

    target = local_dt.strftime("%H:%M")
    if time_input.get_attribute("value") == target:
        return

    def open_popup():
        popups = driver.find_elements(By.CSS_SELECTOR, _TIME_POPUP)
        if popups and popups[-1].is_displayed():
            return popups[-1]
        _real_click(driver, time_input)
        return _wait_until(lambda: (driver.find_elements(By.CSS_SELECTOR, _TIME_POPUP) or [None])[-1], 5)

    for span_sel, wanted in zip(_TIME_SPANS, (f"{local_dt.hour:02d}", f"{local_dt.minute:02d}")):
        # Re-busca a cada coluna: o popup pode re-renderizar/fechar após o 1º clique
        popup = open_popup()
        if popup is None:
            raise RuntimeError("Seletor de hora não abriu")
        span = next(
            (s for s in popup.find_elements(By.CSS_SELECTOR, span_sel)
             if s.get_attribute("textContent").strip() == wanted),
            None,
        )
        if span is None:
            raise RuntimeError(f"Opção {wanted} não existe no seletor de hora")
        driver.execute_script(_JS_SCROLL_IN_LIST, span)
        time.sleep(0.3)
        try:
            span.click()
        except Exception as exc:
            # click() via JS no próprio span também dispara o onClick do React
            logger.debug(f"native click on time option failed ({exc}); using JS click")
            driver.execute_script("arguments[0].click();", span)
        time.sleep(0.6)

    # O campo só recebe o valor quando o relógio fecha: clica no título do bloco
    _close_time_popup(driver)
    if not _wait_until(lambda: time_input.get_attribute("value") == target, 5):
        raise RuntimeError(f"Hora ficou {time_input.get_attribute('value')!r}, esperado {target}")


# DOM de 28/10/2026: combobox com o valor em span.Picker__value ("28 de out de 2026", "14:10")
_NEW_PICKER_TRIGGERS = "div.schedule-picker [role='combobox']"
_NEW_PICKER_PANEL = ".Picker__panel"
_NEW_CAL_TITLE = ".DatePicker__titleMonth"
_NEW_CAL_DAYS = "button.DatePicker__day[data-outside='false'][data-disabled='false']"
_NEW_TIME_COLUMNS = ".TimePicker__panel [role='listbox']"  # horas, minutos
# 3 primeiras letras do mês em PT e EN → número
_MONTHS = {
    **{m: i for i, m in enumerate(
        ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"), 1)},
    **{m: i for i, m in enumerate(
        ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)},
}


def _month_number(text: str) -> int | None:
    """Número do 1º nome de mês (PT/EN) no texto, ou None."""
    for word in re.findall(r"[a-zç]+", text.lower()):
        if word[:3] in _MONTHS:
            return _MONTHS[word[:3]]
    return None


def _new_picker_values(box) -> tuple[str, str]:
    """Textos exibidos nos combobox de data e hora ("29 de out de 2026", "13:10")."""
    from selenium.webdriver.common.by import By

    spans = box.find_elements(By.CSS_SELECTOR, f"{_NEW_PICKER_TRIGGERS} .Picker__value")
    texts = [s.get_attribute("textContent").strip() for s in spans]
    return (texts + ["", ""])[0], (texts + ["", ""])[1]


def _new_date_matches(text: str, local_dt: datetime) -> bool:
    """Confere dia, mês e ano no texto localizado do combobox de data."""
    day = re.search(r"\b(\d{1,2})\b", text)
    year = re.search(r"\b(\d{4})\b", text)
    return (bool(day and year) and int(day.group(1)) == local_dt.day
            and int(year.group(1)) == local_dt.year and _month_number(text) == local_dt.month)


def _close_new_picker(driver, box) -> None:
    """Fecha o popup aberto clicando no título 'Quando publicar'; ESC como reserva."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys

    if not driver.find_elements(By.CSS_SELECTOR, _NEW_PICKER_PANEL):
        return
    try:
        _real_click(driver, box.find_element(By.CSS_SELECTOR, ".scheduled-title-container"))
    except Exception:
        pass
    if not _wait_until(lambda: not driver.find_elements(By.CSS_SELECTOR, _NEW_PICKER_PANEL), 3):
        try:
            driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        except Exception:
            pass
    time.sleep(0.5)


def _open_new_picker(driver, box, index: int, content_sel: str):
    """Abre o combobox `index` (0 = data, 1 = hora) e espera o conteúdo do popup."""
    from selenium.webdriver.common.by import By

    _close_new_picker(driver, box)
    _real_click(driver, box.find_elements(By.CSS_SELECTOR, _NEW_PICKER_TRIGGERS)[index])
    if not _wait_until(lambda: driver.find_elements(By.CSS_SELECTOR, content_sel), 5):
        raise RuntimeError("Seletor de " + ("data" if index == 0 else "hora") + " não abriu")


def _new_pick_date(driver, box, local_dt: datetime) -> None:
    """Navega o calendário até o mês certo e clica no dia."""
    from selenium.webdriver.common.by import By

    if _new_date_matches(_new_picker_values(box)[0], local_dt):
        return
    _open_new_picker(driver, box, 0, _NEW_CAL_TITLE)
    for _ in range(3):
        shown = _month_number(driver.find_element(By.CSS_SELECTOR, _NEW_CAL_TITLE).text)
        if shown is None:
            raise RuntimeError("Mês do calendário ilegível")
        diff = (local_dt.month - shown) % 12
        if diff == 0:
            break
        label = "Next month" if diff <= 6 else "Previous month"
        _js_click(driver, driver.find_element(By.CSS_SELECTOR, f"button[aria-label='{label}']"))
        time.sleep(0.6)
    day = next(
        (d for d in driver.find_elements(By.CSS_SELECTOR, _NEW_CAL_DAYS)
         if d.get_attribute("textContent").strip() == str(local_dt.day)),
        None,
    )
    if day is None:
        raise RuntimeError(f"Dia {local_dt.day} não disponível no calendário")
    _js_click(driver, day)
    if not _wait_until(lambda: _new_date_matches(_new_picker_values(box)[0], local_dt), 5):
        raise RuntimeError(f"Data ficou {_new_picker_values(box)[0]!r}")


def _new_pick_time(driver, box, local_dt: datetime) -> None:
    """Clica na hora e no minuto nas colunas do relógio (minutos de 5 em 5)."""
    from selenium.webdriver.common.by import By

    target = local_dt.strftime("%H:%M")
    if _new_picker_values(box)[1] == target:
        return
    for col, wanted in enumerate((f"{local_dt.hour:02d}", f"{local_dt.minute:02d}")):
        # Re-busca a cada coluna: o popup pode re-renderizar/fechar após o 1º clique
        if not driver.find_elements(By.CSS_SELECTOR, _NEW_TIME_COLUMNS):
            _open_new_picker(driver, box, 1, _NEW_TIME_COLUMNS)
        column = driver.find_elements(By.CSS_SELECTOR, _NEW_TIME_COLUMNS)[col]
        item = next(
            (b for b in column.find_elements(By.CSS_SELECTOR, "button[role='option']")
             if b.get_attribute("textContent").strip() == wanted
             and b.get_attribute("data-disabled") != "true"),
            None,
        )
        if item is None:
            raise RuntimeError(f"Opção {wanted} não existe/está bloqueada no seletor de hora")
        # Rola só a coluna (rolar a página fecha o popup)
        driver.execute_script(
            "const c = arguments[0], el = arguments[1];"
            "c.scrollTop = el.offsetTop - c.clientHeight / 2 + el.offsetHeight / 2;",
            column, item,
        )
        time.sleep(0.4)
        driver.execute_script("arguments[0].click();", item)
        time.sleep(0.6)
    _close_new_picker(driver, box)
    if not _wait_until(lambda: _new_picker_values(box)[1] == target, 5):
        raise RuntimeError(f"Hora ficou {_new_picker_values(box)[1]!r}, esperado {target}")


def _studio_set_schedule_new(driver, box, local_dt: datetime) -> None:
    """Preenche data/hora no seletor Picker (DOM de 28/10/2026); levanta se não confirmar."""
    for attempt in range(1, 3):
        try:
            # Data antes da hora: no dia de hoje o TikTok limita as horas disponíveis
            _new_pick_date(driver, box, local_dt)
            _new_pick_time(driver, box, local_dt)
        except Exception as exc:
            logger.warning(f"schedule picker step failed (tentativa {attempt}/2): {exc}")
        _close_new_picker(driver, box)
        date_text, time_text = _new_picker_values(box)
        if _new_date_matches(date_text, local_dt) and time_text == local_dt.strftime("%H:%M"):
            logger.info("Schedule set and verified.")
            return
    raise RuntimeError(
        f"Não consegui definir o horário {local_dt:%d/%m %H:%M} "
        f"(campos atuais: {_new_picker_values(box)!r})"
    )


def _studio_set_schedule(driver, schedule: datetime) -> None:
    """Marca 'Programar' e preenche data/hora; levanta se não confirmar (nunca publica errado).

    Na falha deixa o seletor de data aberto para o dump mostrar o DOM dele.
    """
    from selenium.webdriver.common.by import By

    local_dt = schedule.astimezone().replace(tzinfo=None)  # lib manda em UTC
    logger.info(f"Setting schedule → {local_dt:%Y-%m-%d %H:%M}")

    radio = driver.find_element(By.CSS_SELECTOR, "input[name='postSchedule'][value='schedule']")
    driver.execute_script("arguments[0].click();", radio)
    if not _wait_until(lambda: radio.is_selected(), 10):
        raise RuntimeError("Não consegui marcar 'Programar'")

    box = driver.find_element(By.CSS_SELECTOR, _SCHEDULE_BOX)
    if not _wait_until(
        lambda: len(box.find_elements(By.CSS_SELECTOR, _PICKER_INPUTS)) >= 2
        or len(box.find_elements(By.CSS_SELECTOR, _NEW_PICKER_TRIGGERS)) >= 2,
        10,
    ):
        raise RuntimeError("Campos de data/hora não apareceram após marcar 'Programar'")
    if box.find_elements(By.CSS_SELECTOR, _NEW_PICKER_TRIGGERS):
        _studio_set_schedule_new(driver, box, local_dt)
        return

    def field(pattern: str):
        for inp in box.find_elements(By.CSS_SELECTOR, _PICKER_INPUTS):
            if re.fullmatch(pattern, inp.get_attribute("value") or ""):
                return inp
        raise RuntimeError(f"Campo {pattern} não encontrado")

    date_input = field(r"\d{4}-\d{2}-\d{2}")
    for attempt in range(1, 3):
        try:
            # Data antes da hora: no dia de hoje o TikTok limita as horas disponíveis
            _studio_pick_date(driver, date_input, local_dt)
            _studio_pick_time(driver, field(r"\d{1,2}:\d{2}"), local_dt)
        except Exception as exc:
            logger.warning(f"schedule picker step failed (tentativa {attempt}/2): {exc}")
        _close_time_popup(driver)
        if _wait_until(lambda: _schedule_matches(driver, local_dt), 3):
            logger.info("Schedule set and verified.")
            return

    # Falhou: deixa o calendário aberto para o dump mostrar o DOM dele
    try:
        driver.execute_script("arguments[0].click();", date_input)
        time.sleep(1.5)
    except Exception:
        pass
    raise RuntimeError(
        f"Não consegui definir o horário {local_dt:%d/%m %H:%M} "
        f"(campos atuais: {_schedule_fields_text(driver)[:120]!r})"
    )


def _studio_post(driver) -> None:
    """Clica em Publicar/Programar, confirma o popup e espera a confirmação do TikTok."""
    from selenium.webdriver.common.by import By
    import tiktok_uploader

    logger.info("Clicking the post button")
    post = _wait_until(
        lambda: (b := driver.find_element(By.CSS_SELECTOR, _POST_BUTTON))
        and b.get_attribute("data-disabled") == "false" and b,
        tiktok_uploader.config.uploading_wait,
        interval=1,
    )
    if post is None:
        raise RuntimeError("Botão Publicar não habilitou (upload do vídeo não terminou?)")
    start_url = driver.current_url
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();", post)

    def _done() -> bool:
        # Popup "Continuar publicando?" pode aparecer a qualquer momento
        for b in driver.find_elements(By.CSS_SELECTOR, _MODAL_PRIMARY):
            if b.is_displayed():
                logger.info(f"Confirming modal: {b.text!r}")
                driver.execute_script("arguments[0].click();", b)
                return False
        if driver.current_url != start_url and "upload" not in driver.current_url:
            return True
        body = (driver.execute_script("return document.body.innerText") or "").lower()
        return any(t in body for t in _POSTED_TEXTS)

    if not _wait_until(_done, tiktok_uploader.config.explicit_wait * 2, interval=1):
        raise RuntimeError("TikTok não confirmou a publicação")
    logger.info("Video posted/scheduled successfully.")


_UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload?from=upload"
_SESSION_SIZE = 8  # vídeos por navegador (sessões longas deixam o Studio lento)
_UPLOAD_MAX_WAIT = 600  # s para o arquivo subir e o TikTok liberar o botão Publicar


def _studio_go_to_upload(driver) -> None:
    """Abre uma página de upload limpa, sem o diálogo 'Sair do site?' de um form anterior."""
    from selenium.webdriver.common.by import By

    logger.info("Navigating to upload page")
    try:
        driver.execute_script(
            "window.onbeforeunload = null;"
            "window.addEventListener('beforeunload', e => e.stopImmediatePropagation(), true);"
        )
    except Exception:
        pass
    driver.get(_UPLOAD_URL)
    try:
        driver.switch_to.alert.accept()
    except Exception:
        pass
    if not _wait_until(lambda: driver.find_elements(By.CSS_SELECTOR, "input[type='file']"), 60):
        raise RuntimeError("Página de upload não carregou (input de arquivo não apareceu)")


def _studio_set_video(driver, path: str) -> None:
    """Envia o arquivo e espera o TikTok terminar de subir (botão Publicar habilitado)."""
    from selenium.webdriver.common.by import By

    logger.info(f"Uploading video file: {Path(path).name}")
    driver.find_element(By.CSS_SELECTOR, "input[type='file']").send_keys(path)

    def uploaded() -> bool:
        btns = driver.find_elements(By.CSS_SELECTOR, _POST_BUTTON)
        return bool(btns) and btns[0].get_attribute("data-disabled") == "false"

    started = time.time()
    if not _wait_until(uploaded, _UPLOAD_MAX_WAIT, interval=2):
        raise RuntimeError(f"Upload do arquivo não terminou em {_UPLOAD_MAX_WAIT}s")
    logger.info(f"Video file uploaded ({time.time() - started:.0f}s)")


def _studio_complete_upload_form(
    driver, path, description, schedule, skip_split_window, cover_path=None,
    product_id=None, visibility="everyone", num_retries=1, headless=False, *args, **kwargs,
) -> None:
    """Fluxo de um vídeo, sequencial e com timeout em toda espera.

    Substitui o da 1.1.5, que trava para sempre se o envio do arquivo der erro (thread + Event).
    """
    import tiktok_uploader.upload as tt_upload

    _studio_go_to_upload(driver)
    _safe_remove_cookies_window(driver)
    _studio_set_video(driver, path)
    if cover_path:
        tt_upload._set_cover(driver, cover_path)
    if not skip_split_window:
        tt_upload._remove_split_window(driver)
    tt_upload._set_interactivity(driver, **kwargs)
    _studio_set_description(driver, description, Path(path).stem)
    if visibility != "everyone":
        tt_upload._set_visibility(driver, visibility)
    if schedule:
        _studio_set_schedule(driver, schedule)
    if product_id:
        tt_upload._add_product_link(driver, product_id)
    _studio_post(driver)


def _dump_page(driver, video_path: str) -> None:
    """Salva HTML + screenshot da página em LOGS_DIR/tiktok_debug para diagnosticar seletores."""
    try:
        from config.paths import LOGS_DIR
        out = LOGS_DIR / "tiktok_debug"
        out.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^\w\-]", "_", Path(video_path).stem)[:40]
        stem = f"{time.strftime('%Y%m%d_%H%M%S')}_{safe_name}"
        (out / f"{stem}.html").write_text(driver.page_source, encoding="utf-8")
        driver.save_screenshot(str(out / f"{stem}.png"))
        logger.error(f"Página do TikTok salva para diagnóstico em: {out / stem}.html/.png")
    except Exception as exc:
        logger.debug(f"page dump skipped: {exc}")


_TIKTOK_PATCHED = False


class _BrowserStartError(RuntimeError):
    """O navegador/driver não iniciou (ex.: driver não baixou)."""


def _patch_tiktok_uploader() -> None:
    """Aplica (uma vez) os ajustes na tiktok-uploader 1.1.5 antes do upload."""
    global _TIKTOK_PATCHED
    if _TIKTOK_PATCHED:
        return
    import tiktok_uploader.upload as tt_upload

    # Fluxo por vídeo é todo nosso (seletores da 1.1.5 morreram e o dela pode travar);
    # da lib fica só o loop de upload_videos, que isola a falha de cada vídeo.
    def _form_with_dump(driver, path, *args, **kwargs):
        try:
            return _studio_complete_upload_form(driver, path, *args, **kwargs)
        except Exception as exc:
            logger.error(f"Falha em {Path(path).name}: {exc}")
            _dump_page(driver, path)
            raise

    tt_upload.complete_upload_form = _form_with_dump

    from tiktok_uploader.auth import AuthBackend
    original_auth = AuthBackend.authenticate_agent

    def _light_authenticate(self, driver):
        # A lib abria o feed (pesado, autoplay) e esperava o título: dava timeout/crash do renderer
        if not self.cookies:
            return original_auth(self, driver)
        _open_tiktok_domain(driver)
        failed = 0
        for cookie in self.cookies:
            try:
                driver.add_cookie(cookie)
            except Exception:
                failed += 1
        if failed:
            logger.warning(f"{failed} de {len(self.cookies)} cookie(s) não foram aceitos")
        return driver

    AuthBackend.authenticate_agent = _light_authenticate
    _TIKTOK_PATCHED = True


_TIKTOK_LIGHT_URL = "https://www.tiktok.com/robots.txt"


def _open_tiktok_domain(driver, attempts: int = 3) -> None:
    """Abre uma página leve do www.tiktok.com (necessário para add_cookie), com retry."""
    try:
        previous_timeout = driver.timeouts.page_load
    except Exception:
        previous_timeout = 300
    driver.set_page_load_timeout(45)
    last_exc: Exception | None = None
    try:
        for attempt in range(1, attempts + 1):
            try:
                driver.get(_TIKTOK_LIGHT_URL)
                if "tiktok.com" in (driver.current_url or ""):
                    return
            except Exception as exc:
                last_exc = exc
                logger.warning(f"tiktok.com não abriu (tentativa {attempt}/{attempts}): {str(exc)[:120]}")
            time.sleep(3)
        raise RuntimeError(f"Não consegui abrir tiktok.com para aplicar os cookies: {last_exc}")
    finally:
        driver.set_page_load_timeout(previous_timeout)


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class TikTokUploader:
    """Uploader do TikTok por conta; account_name=None usa o cookies.txt legado."""

    def __init__(self, account_name: str | None = None):
        if account_name:
            self.account_name = account_name
            self.cookies_path = str(_cookies_path(account_name))
        else:
            # Legacy fallback
            self.account_name = "default"
            from config.paths import COOKIES_FILE
            self.cookies_path = str(COOKIES_FILE)
        self.logger = logging.getLogger("DarkAgent.Uploader")

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    def login(self, browser_name: str = "chrome") -> bool:
        """Abre o navegador para o usuário logar no TikTok.

        Os cookies são salvos em self.cookies_path quando o sessionid aparece.
        """
        self.logger.info(f"Opening {browser_name} for login (account: {self.account_name})…")
        driver = None
        try:
            driver = _make_driver(browser_name, headless=False)
            driver.get("https://www.tiktok.com/login")
            self.logger.info("Waiting for user to log in…")

            deadline = time.time() + 300  # 5 minutes
            logged_in = False

            while time.time() < deadline:
                try:
                    if not driver.window_handles:
                        break
                    cookies = {c["name"]: c["value"] for c in driver.get_cookies()}
                    if "sessionid" in cookies:
                        self.logger.info("sessionid found — saving cookies…")
                        self._save_cookies_netscape(driver.get_cookies())
                        add_account(self.account_name, self.cookies_path)
                        logged_in = True
                        break
                    time.sleep(1)
                except Exception:
                    break

            if logged_in:
                time.sleep(2)
                try:
                    driver.quit()
                except Exception:
                    pass
                return True

            self.logger.warning("Login timed out or browser was closed.")
        except Exception as exc:
            self.logger.error(f"Login error: {exc}")
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
        return False

    # ------------------------------------------------------------------
    # Cookie persistence
    # ------------------------------------------------------------------

    def _save_cookies_netscape(self, cookies_list: list[dict]) -> None:
        """Save Selenium cookies in Netscape format."""
        with open(self.cookies_path, "w", encoding="utf-8") as f:
            f.write("# Netscape HTTP Cookie File\n")
            f.write("# This is a generated file!  Do not edit.\n\n")
            for c in cookies_list:
                domain = c.get("domain", "")
                flag = "TRUE" if domain.startswith(".") else "FALSE"
                path = c.get("path", "/")
                secure = "TRUE" if c.get("secure") else "FALSE"
                expiry = int(c.get("expiry", time.time() + 3600 * 24 * 365))
                name = c.get("name", "")
                value = c.get("value", "")
                f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expiry}\t{name}\t{value}\n")

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------

    def upload(
        self,
        video_path: str,
        title: str,
        hashtags: list[str] | None = None,
        headless: bool = False,
        browser_name: str = "chrome",
        schedule_time: datetime | None = None,
    ) -> bool:
        """Envia um único vídeo; atalho para upload_batch. Retorna True se deu certo."""
        task = {"path": video_path, "title": title, "hashtags": hashtags or [],
                "schedule_time": schedule_time}
        return not self.upload_batch([task], headless=headless, browser_name=browser_name)

    @staticmethod
    def _build_description(title: str, hashtags: list[str] | None) -> str:
        tag_str = " ".join(f"#{t.lstrip('#')}" for t in (hashtags or []) if t.strip())
        return f"{title or ''} {tag_str}".strip()

    def upload_batch(
        self,
        tasks: list[dict],
        headless: bool = False,
        browser_name: str = "chrome",
    ) -> list[str]:
        """Envia vários vídeos (navegador novo a cada _SESSION_SIZE). Retorna os paths que falharam.

        Cada task: {path, title, hashtags?, schedule_time? (datetime naive local)}.
        """
        if headless:
            self.logger.warning("TikTok blocks headless sessions — forcing headless=False.")

        all_paths = [t.get("path") or "" for t in tasks]
        if not os.path.exists(self.cookies_path):
            self.logger.error(
                f"Cookies not found for account '{self.account_name}' at {self.cookies_path}. "
                "Please log in first."
            )
            return all_paths

        failed_paths: list[str] = []
        videos_to_upload = []
        for task in tasks:
            video_path = task.get("path")
            if not video_path or not os.path.exists(video_path):
                self.logger.warning(f"Video file not found, skipping: {video_path}")
                failed_paths.append(video_path or "")
                continue

            video_dict = {
                "path": video_path,
                "description": self._build_description(task.get("title", ""), task.get("hashtags")),
            }
            # tiktok-uploader 1.1.5 espera datetime (string quebra em .tzinfo)
            if task.get("schedule_time"):
                video_dict["schedule"] = task["schedule_time"]
            videos_to_upload.append(video_dict)

        if not videos_to_upload:
            self.logger.error("No valid videos to upload.")
            return failed_paths

        self.logger.info(
            f"Starting batch upload of {len(videos_to_upload)} video(s) | "
            f"account='{self.account_name}' | browser='{browser_name}'"
        )

        # Sessão longa deixa o Studio lento (prefill atrasado sobrescreve a descrição):
        # navegador novo a cada _SESSION_SIZE vídeos.
        for start in range(0, len(videos_to_upload), _SESSION_SIZE):
            chunk = videos_to_upload[start:start + _SESSION_SIZE]
            self.logger.info(
                f"Sessão {start // _SESSION_SIZE + 1}: vídeos {start + 1}–{start + len(chunk)} "
                f"de {len(videos_to_upload)}"
            )
            try:
                failed_paths += self._upload_session(chunk, browser_name)
            except _BrowserStartError as exc:
                # Sem navegador não adianta tentar as próximas sessões
                self.logger.error(f"Navegador '{browser_name}' não abriu: {exc}")
                failed_paths += [v["path"] for v in videos_to_upload[start:]]
                break

        if failed_paths:
            self.logger.error(f"Batch upload had {len(failed_paths)} failure(s): {failed_paths}")
        else:
            self.logger.info("Batch upload completed successfully.")
        return failed_paths

    def _upload_session(self, videos: list[dict], browser_name: str) -> list[str]:
        """Sobe os vídeos num navegador novo. Retorna os paths que falharam."""
        driver = None
        try:
            from tiktok_uploader.upload import upload_videos
            from tiktok_uploader.auth import AuthBackend

            _patch_tiktok_uploader()

            # Build our own undetected driver — the library's factory rejects 'brave'
            # and uses plain Selenium which gets flagged immediately.
            try:
                driver = _make_driver(browser_name, headless=False)
            except Exception as exc:
                raise _BrowserStartError(str(exc)) from exc
            _human_delay(1.5, 3.0)

            auth = AuthBackend(cookies=self.cookies_path)
            _human_delay(0.5, 1.5)

            failed = upload_videos(videos=videos, auth=auth, browser_agent=driver)
            return [v.get("path", "") for v in failed]

        except _BrowserStartError:
            raise
        except Exception as exc:
            self.logger.error(f"Error during upload session: {exc}", exc_info=True)
            return [v.get("path", "") for v in videos]
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
