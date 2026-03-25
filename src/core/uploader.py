"""
TikTokUploader — multi-account, multi-browser upload core.

Cookies are stored per account as:
    <cookies_dir>/cookies_<account_name>.txt

Anti-detection strategy:
  - Chrome/Brave: undetected-chromedriver (uc) patches the binary-level
    Selenium fingerprints that TikTok's bot-detection reads.
  - All browsers: JS patches for navigator.webdriver, plugins, etc.
  - Human-like random delays between actions.
  - Uploads always run non-headless (TikTok aggressively blocks headless).
"""
from __future__ import annotations

import json
import logging
import os
import random
import re
import subprocess
import time
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
    """Return (and create) the directory where per-account cookies live."""
    d = Path(__file__).parent.parent / "accounts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cookies_path(account_name: str) -> Path:
    safe = re.sub(r"[^\w\-]", "_", account_name)
    return _cookies_dir() / f"cookies_{safe}.txt"


def _accounts_index() -> Path:
    return _cookies_dir() / "accounts.json"


# ---------------------------------------------------------------------------
# Account registry
# ---------------------------------------------------------------------------

def list_accounts() -> list[dict]:
    """Return [{'name': str, 'cookies_path': str}, ...]"""
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
"""


def _apply_stealth_js(driver) -> None:
    """Execute anti-fingerprint JS on the current page."""
    try:
        driver.execute_script(_STEALTH_JS)
    except Exception as exc:
        logger.debug(f"stealth JS injection skipped: {exc}")


def _apply_stealth_cdp(driver) -> None:
    """Apply Chrome DevTools Protocol patches (only works with uc / Chrome)."""
    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": _STEALTH_JS},
        )
        logger.debug("CDP stealth script registered.")
    except Exception as exc:
        logger.debug(f"CDP stealth patch skipped: {exc}")


def _human_delay(min_s: float = 0.8, max_s: float = 2.2) -> None:
    """Sleep for a random human-like duration."""
    time.sleep(random.uniform(min_s, max_s))


# ---------------------------------------------------------------------------
# Driver factory
# ---------------------------------------------------------------------------

def _find_brave_path() -> str | None:
    """Locate the Brave executable on Windows."""
    candidates = []
    for env_key in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        val = os.environ.get(env_key, "")
        if val:
            candidates.append(
                os.path.join(val, "BraveSoftware", "Brave-Browser", "Application", "brave.exe")
            )
    return next((p for p in candidates if os.path.exists(p)), None)


def _brave_major_version(brave_path: str) -> str | None:
    """Return the major version number string of the Brave binary."""
    try:
        out = subprocess.check_output(
            [brave_path, "--version"], stderr=subprocess.DEVNULL
        ).decode().strip()
        m = re.search(r"(\d+)\.\d+\.\d+\.\d+", out)
        if m:
            logger.info(f"Brave version major: {m.group(1)}")
            return m.group(1)
    except Exception as exc:
        logger.warning(f"Could not detect Brave version: {exc}")
    return None


def _make_driver(browser_name: str, headless: bool = False):
    """
    Build and return a WebDriver for the requested browser.

    Chrome & Brave always use undetected-chromedriver (uc) when available,
    which patches the driver binary to remove all Selenium fingerprints.
    Firefox and Edge fall back to standard Selenium.

    NOTE: TikTok aggressively detects headless Chrome — uploads should
    always use headless=False (enforced in TikTokUploader.upload()).
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
        options = uc.ChromeOptions()
        options.add_argument("--start-maximized")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        # Extra args that help bypass bot-score checks
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--disable-notifications")
        options.add_argument("--lang=pt-BR")

        brave_path = None
        version_main = None

        if browser_name == "brave":
            brave_path = _find_brave_path()
            if brave_path:
                options.binary_location = brave_path
                logger.info(f"Brave found at: {brave_path}")
                version_main_str = _brave_major_version(brave_path)
                if version_main_str:
                    version_main = int(version_main_str)
            else:
                logger.warning("Brave binary not found — falling back to Chrome.")

        driver = uc.Chrome(
            options=options,
            headless=headless,          # uc handles headless safely
            version_main=version_main,  # None → auto-detect from installed Chrome
            use_subprocess=True,        # avoids process zombie issues on Windows
        )

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
        brave_path = _find_brave_path()
        if brave_path:
            options.binary_location = brave_path

    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    _apply_stealth_cdp(driver)
    return driver


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class TikTokUploader:
    """
    Multi-account TikTok uploader.

    Parameters
    ----------
    account_name : str
        Human-readable name for this account (used to locate its cookies file).
        Pass None to fall back to the legacy 'cookies.txt' path (single-account
        backwards compat).
    """

    def __init__(self, account_name: str | None = None):
        if account_name:
            self.account_name = account_name
            self.cookies_path = str(_cookies_path(account_name))
        else:
            # Legacy fallback
            self.account_name = "default"
            self.cookies_path = str(Path(__file__).parent.parent / "cookies.txt")
        self.logger = logging.getLogger("DarkAgent.Uploader")

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    def login(self, browser_name: str = "chrome") -> bool:
        """
        Open a browser window so the user can log into TikTok.
        Cookies are saved to self.cookies_path when sessionid is detected.
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
        schedule_time: str | None = None,
    ) -> bool:
        """
        Upload *video_path* to TikTok using the account's saved cookies.
        Works for all supported browsers (chrome, brave, firefox, edge).

        Parameters
        ----------
        headless : bool
            Kept for API compatibility — ALWAYS forced to False for uploads.
            TikTok aggressively blocks headless sessions regardless of spoofing.
        schedule_time : str | None
            If given, tells TikTok Studio to schedule the post.
            Format expected by tiktok_uploader: 'YYYY-MM-DD HH:MM:SS'
        """
        # Force non-headless: TikTok detects headless Chrome even with UC
        if headless:
            self.logger.warning(
                "headless=True was requested but TikTok blocks headless sessions. "
                "Forcing headless=False."
            )
        headless = False  # always

        if not os.path.exists(video_path):
            self.logger.error(f"Video file not found: {video_path}")
            return False

        if not os.path.exists(self.cookies_path):
            self.logger.error(
                f"Cookies not found for account '{self.account_name}' at {self.cookies_path}. "
                "Please log in first."
            )
            return False

        description = title or ""
        if hashtags:
            tag_str = " ".join(f"#{t.lstrip('#')}" for t in hashtags if t.strip())
            description = f"{description} {tag_str}".strip() if description else tag_str

        self.logger.info(
            f"Uploading '{video_path}' | account='{self.account_name}' | browser='{browser_name}'"
            + (f" | scheduled={schedule_time}" if schedule_time else "")
        )

        driver = None
        try:
            from tiktok_uploader.upload import upload_videos
            from tiktok_uploader.auth import AuthBackend

            # Build our own undetected driver — the library's factory rejects 'brave'
            # and uses plain Selenium which gets flagged immediately.
            driver = _make_driver(browser_name, headless=False)

            # Warm-up: give the browser a moment to settle before automation begins
            _human_delay(1.5, 3.0)

            auth = AuthBackend(cookies=self.cookies_path)

            video_dict = {"path": video_path, "description": description}
            if schedule_time:
                video_dict["schedule"] = schedule_time

            # Small delay before starting the upload sequence
            _human_delay(0.5, 1.5)

            failed = upload_videos(
                videos=[video_dict],
                auth=auth,
                browser_agent=driver,  # inject our pre-built undetected driver
            )

            if not failed:
                self.logger.info("Upload completed successfully.")
                # Brief pause so the page can finalize before the driver closes
                _human_delay(1.0, 2.0)
                return True
            else:
                self.logger.error(f"Upload failed: {failed}")
                return False

        except Exception as exc:
            self.logger.error(f"Error during upload: {exc}", exc_info=True)
            return False
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

    def upload_batch(
        self,
        tasks: list[dict],
        headless: bool = False,
        browser_name: str = "chrome",
    ) -> bool:
        """
        Upload multiple videos to TikTok in a single browser session.
        Each task is a dict containing:
          - path: str
          - title: str
          - hashtags: list[str] (optional)
          - schedule_time: str (optional)
        """
        headless = False  # always

        if not os.path.exists(self.cookies_path):
            self.logger.error(f"Cookies not found. Please log in first.")
            return False

        videos_to_upload = []
        for task in tasks:
            video_path = task.get("path")
            if not video_path or not os.path.exists(video_path):
                self.logger.warning(f"Video file not found, skipping: {video_path}")
                continue

            description = task.get("title", "")
            hashtags = task.get("hashtags", [])
            
            if hashtags:
                tag_str = " ".join(f"#{t.lstrip('#')}" for t in hashtags if t.strip())
                description = f"{description} {tag_str}".strip() if description else tag_str

            video_dict = {"path": video_path, "description": description}
            if task.get("schedule_time"):
                video_dict["schedule"] = task.get("schedule_time")
            
            videos_to_upload.append(video_dict)

        if not videos_to_upload:
            self.logger.error("No valid videos to upload.")
            return False

        self.logger.info(f"Starting batch upload for {len(videos_to_upload)} videos...")

        driver = None
        try:
            from tiktok_uploader.upload import upload_videos
            from tiktok_uploader.auth import AuthBackend

            driver = _make_driver(browser_name, headless=False)
            _human_delay(1.5, 3.0)

            auth = AuthBackend(cookies=self.cookies_path)

            _human_delay(0.5, 1.5)

            # upload_videos handles iterating over the videos list in a single browser session
            failed = upload_videos(
                videos=videos_to_upload,
                auth=auth,
                browser_agent=driver,
            )

            if not failed:
                self.logger.info("Batch upload completed successfully.")
                _human_delay(1.0, 2.0)
                return True
            else:
                self.logger.error(f"Batch upload had failures: {failed}")
                return False

        except Exception as exc:
            self.logger.error(f"Error during batch upload: {exc}", exc_info=True)
            return False
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass


