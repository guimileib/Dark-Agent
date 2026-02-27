"""
TikTokUploader — multi-account, multi-browser upload core.

Cookies are stored per account as:
    <cookies_dir>/cookies_<account_name>.txt
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager
from webdriver_manager.microsoft import EdgeChromiumDriverManager

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
# Driver factory
# ---------------------------------------------------------------------------

def _make_driver(browser_name: str, headless: bool = False) -> webdriver.Remote:
    """Build and return a Selenium WebDriver for the requested browser."""
    browser_name = browser_name.lower()

    if browser_name == "firefox":
        options = FirefoxOptions()
        options.set_preference("dom.webdriver.enabled", False)
        options.set_preference("useAutomationExtension", False)
        if headless:
            options.add_argument("--headless")
        service = FirefoxService(GeckoDriverManager().install())
        return webdriver.Firefox(service=service, options=options)

    if browser_name == "edge":
        options = EdgeOptions()
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--start-maximized")
        if headless:
            options.add_argument("--headless=new")
        service = EdgeService(EdgeChromiumDriverManager().install())
        return webdriver.Edge(service=service, options=options)

    # Chrome or Brave — both use the ChromeDriver
    options = ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    if headless:
        options.add_argument("--headless=new")

    if browser_name == "brave":
        brave_candidates = []
        for env_key in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            val = os.environ.get(env_key, "")
            if val:
                brave_candidates.append(
                    os.path.join(val, "BraveSoftware", "Brave-Browser", "Application", "brave.exe")
                )

        brave_path = next((p for p in brave_candidates if os.path.exists(p)), None)
        if brave_path:
            options.binary_location = brave_path
            logger.info(f"Brave found at: {brave_path}")
        else:
            logger.warning("Brave binary not found — falling back to Chrome.")

        # Detect Brave version → fetch matching ChromeDriver
        driver_version = None
        if brave_path:
            try:
                out = subprocess.check_output(
                    [brave_path, "--version"], stderr=subprocess.DEVNULL
                ).decode().strip()
                m = re.search(r"(\d+\.\d+\.\d+\.\d+)", out)
                if m:
                    driver_version = m.group(1).split(".")[0]
                    logger.info(f"Brave version: {m.group(1)}")
            except Exception as exc:
                logger.warning(f"Could not detect Brave version: {exc}")

        try:
            mgr = ChromeDriverManager(driver_version=driver_version) if driver_version else ChromeDriverManager()
            service = ChromeService(mgr.install())
        except Exception:
            service = ChromeService(ChromeDriverManager().install())
    else:
        service = ChromeService(ChromeDriverManager().install())

    return webdriver.Chrome(service=service, options=options)


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
        headless: bool = True,
        browser_name: str = "chrome",
    ) -> bool:
        """
        Upload *video_path* to TikTok using the account's saved cookies.
        Works for all supported browsers (chrome, brave, firefox, edge).
        """
        if not os.path.exists(video_path):
            self.logger.error(f"Video file not found: {video_path}")
            return False

        if not os.path.exists(self.cookies_path):
            self.logger.error(
                f"Cookies not found for account '{self.account_name}' at {self.cookies_path}. "
                "Please log in first."
            )
            return False

        description = title
        if hashtags:
            description = f"{title} " + " ".join(
                f"#{t.lstrip('#')}" for t in hashtags if t.strip()
            )

        self.logger.info(
            f"Uploading '{video_path}' | account='{self.account_name}' | browser='{browser_name}'"
        )

        driver = None
        try:
            from tiktok_uploader.upload import upload_videos
            from tiktok_uploader.auth import AuthBackend

            # Always build our own driver so every browser (including Brave)
            # works — the library's built-in browser factory rejects 'brave'.
            driver = _make_driver(browser_name, headless=headless)
            auth = AuthBackend(cookies=self.cookies_path)

            video_dict = {"path": video_path, "description": description}

            failed = upload_videos(
                videos=[video_dict],
                auth=auth,
                browser_agent=driver,  # inject our pre-built driver
            )

            if not failed:
                self.logger.info("Upload completed successfully.")
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
