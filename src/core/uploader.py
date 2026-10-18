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
        service = FirefoxService(GeckoDriverManager().install())
        driver = webdriver.Firefox(service=service, options=options)
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
        service = EdgeService(EdgeChromiumDriverManager().install())
        driver = webdriver.Edge(service=service, options=options)
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

    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
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


def _studio_set_description(driver, description: str) -> None:
    """Limpa o editor (vem com o nome do arquivo) e digita a descrição, selecionando as hashtags."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys

    if not description:
        return
    logger.info("Setting description")
    editor = _wait_until(
        lambda: driver.find_element(By.CSS_SELECTOR, "div[contenteditable='true']"), 30
    )
    if editor is None:
        raise RuntimeError("Editor de descrição não encontrado")
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", editor)
    try:
        editor.click()
    except Exception:
        driver.execute_script("arguments[0].focus();", editor)
    editor.send_keys(Keys.CONTROL, "a")
    editor.send_keys(Keys.BACKSPACE)
    _wait_until(lambda: editor.text.strip() == "", 5)

    # Texto corrido de uma vez; cada #tag separada para escolher a sugestão
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
    _human_delay(0.5, 1.0)
    if description.split()[0][:15] not in editor.text:
        raise RuntimeError(f"Descrição não foi preenchida (editor: {editor.text[:80]!r})")


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
_TIME_COLUMNS = ".tiktok-timepicker-option-list"
_TIME_ITEMS = ".tiktok-timepicker-option-item"
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

    for col_idx, wanted in ((0, f"{local_dt.hour:02d}"), (1, f"{local_dt.minute:02d}")):
        # Re-busca a cada coluna: o popup pode re-renderizar/fechar após o 1º clique
        popup = open_popup()
        if popup is None:
            raise RuntimeError("Seletor de hora não abriu")
        cols = popup.find_elements(By.CSS_SELECTOR, _TIME_COLUMNS)
        if len(cols) < 2:
            raise RuntimeError(f"Seletor de hora com {len(cols)} coluna(s), esperado 2")
        item = next(
            (i for i in cols[col_idx].find_elements(By.CSS_SELECTOR, _TIME_ITEMS)
             if i.get_attribute("textContent").strip() == wanted),
            None,
        )
        if item is None:
            raise RuntimeError(f"Opção {wanted} não existe no seletor de hora")
        _real_click(driver, item)
        time.sleep(0.6)

    popups = driver.find_elements(By.CSS_SELECTOR, _TIME_POPUP)
    if popups and popups[-1].is_displayed():
        _real_click(driver, time_input)  # fecha o popup
    if not _wait_until(lambda: time_input.get_attribute("value") == target, 5):
        raise RuntimeError(f"Hora ficou {time_input.get_attribute('value')!r}, esperado {target}")


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
    if not _wait_until(lambda: len(box.find_elements(By.CSS_SELECTOR, _PICKER_INPUTS)) >= 2, 10):
        raise RuntimeError("Campos de data/hora não apareceram após marcar 'Programar'")

    def field(pattern: str):
        for inp in box.find_elements(By.CSS_SELECTOR, _PICKER_INPUTS):
            if re.fullmatch(pattern, inp.get_attribute("value") or ""):
                return inp
        raise RuntimeError(f"Campo {pattern} não encontrado")

    date_input = field(r"\d{4}-\d{2}-\d{2}")
    try:
        # Data antes da hora: no dia de hoje o TikTok limita as horas disponíveis
        _studio_pick_date(driver, date_input, local_dt)
        _studio_pick_time(driver, field(r"\d{1,2}:\d{2}"), local_dt)
    except Exception as exc:
        logger.warning(f"schedule picker step failed: {exc}")

    if _schedule_matches(driver, local_dt):
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


def _patch_tiktok_uploader() -> None:
    """Aplica (uma vez) os ajustes na tiktok-uploader 1.1.5 antes do upload."""
    global _TIKTOK_PATCHED
    if _TIKTOK_PATCHED:
        return
    import tiktok_uploader
    import tiktok_uploader.upload as tt_upload

    tt_upload._remove_cookies_window = _safe_remove_cookies_window
    # Seletores da 1.1.5 (#tux-1, "Post now" em inglês, mention box) não existem mais
    tt_upload._set_description = _studio_set_description
    tt_upload._set_schedule_video = _studio_set_schedule
    tt_upload._post_video = _studio_post

    original_form = tt_upload.complete_upload_form

    def _form_with_dump(driver, path, *args, **kwargs):
        try:
            return original_form(driver, path, *args, **kwargs)
        except Exception:
            _dump_page(driver, path)
            raise

    tt_upload.complete_upload_form = _form_with_dump
    # 5 s (default da 1.1.5) é curto para o TikTok Studio carregar; a 1.2.0 usa 30.
    tiktok_uploader.config.implicit_wait = max(tiktok_uploader.config.implicit_wait, 20)
    _TIKTOK_PATCHED = True


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
        """Envia vários vídeos numa só sessão (um navegador). Retorna os paths que falharam.

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

        driver = None
        try:
            from tiktok_uploader.upload import upload_videos
            from tiktok_uploader.auth import AuthBackend

            _patch_tiktok_uploader()

            # Build our own undetected driver — the library's factory rejects 'brave'
            # and uses plain Selenium which gets flagged immediately.
            driver = _make_driver(browser_name, headless=False)
            _human_delay(1.5, 3.0)

            auth = AuthBackend(cookies=self.cookies_path)
            _human_delay(0.5, 1.5)

            # upload_videos itera a lista inteira na mesma sessão do navegador
            failed = upload_videos(
                videos=videos_to_upload,
                auth=auth,
                browser_agent=driver,
            )
            failed_paths += [v.get("path", "") for v in failed]

            if failed:
                self.logger.error(f"Batch upload had failures: {failed}")
            else:
                self.logger.info("Batch upload completed successfully.")
                _human_delay(1.0, 2.0)
            return failed_paths

        except Exception as exc:
            self.logger.error(f"Error during batch upload: {exc}", exc_info=True)
            return all_paths
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
