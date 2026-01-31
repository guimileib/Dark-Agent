import os
import time
import logging
from tiktok_uploader.upload import upload_video
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.edge.service import Service as EdgeService
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager
from webdriver_manager.microsoft import EdgeChromiumDriverManager

class TikTokUploader:
    def __init__(self, cookies_path="cookies.txt"):
        self.cookies_path = cookies_path
        self.logger = logging.getLogger("DarkAgent.Uploader")

    def _get_driver(self, browser_name):
        """Helper to get the appropriate driver"""
        browser_name = browser_name.lower()
        
        if browser_name == "firefox":
            options = FirefoxOptions()
            options.set_preference("dom.webdriver.enabled", False)
            options.set_preference('useAutomationExtension', False)
            service = FirefoxService(GeckoDriverManager().install())
            driver = webdriver.Firefox(service=service, options=options)
            
        elif browser_name == "edge":
            options = EdgeOptions()
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--start-maximized")
            service = EdgeService(EdgeChromiumDriverManager().install())
            driver = webdriver.Edge(service=service, options=options)
            
        else: # Default or chrome
            options = ChromeOptions()
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--start-maximized")
            service = ChromeService(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            
        return driver

    def login(self, browser_name="chrome"):
        """
        Opens a browser for the user to login and saves cookies.
        """
        self.logger.info(f"Opening {browser_name} browser for login...")
        
        driver = None
        try:
            driver = self._get_driver(browser_name)
            driver.get("https://www.tiktok.com/login")
            
            self.logger.info("Waiting for user to login...")
            
            max_retries = 300 # 5 minutes
            logged_in = False
            
            while max_retries > 0:
                try:
                    # Check if window is still open
                    if not driver.window_handles:
                        break
                        
                    cookies = {c['name']: c['value'] for c in driver.get_cookies()}
                    if 'sessionid' in cookies:
                        self.logger.info("Session ID found! Saving cookies...")
                        self._save_cookies_netscape(driver.get_cookies())
                        logged_in = True
                        break
                        
                    time.sleep(1)
                    max_retries -= 1
                except Exception:
                    # Browser likely closed
                    break
            
            if logged_in:
                self.logger.info("Login successful.")
                time.sleep(2) 
                try:
                    driver.quit()
                except:
                    pass
                return True
            else:
                self.logger.warning("Browser closed or timeout without login.")
                try:
                    driver.quit()
                except:
                    pass
                return False

        except Exception as e:
            self.logger.error(f"Error during login: {e}")
            if driver:
                try:
                    driver.quit()
                except:
                    pass
            return False

    def _save_cookies_netscape(self, cookies_list):
        """Saves cookies in Netscape format for compatibility"""
        with open(self.cookies_path, 'w') as f:
            f.write("# Netscape HTTP Cookie File\n")
            f.write("# This is a generated file!  Do not edit.\n\n")
            
            for cookie in cookies_list:
                domain = cookie.get('domain', '')
                flag = "TRUE" if domain.startswith('.') else "FALSE"
                path = cookie.get('path', '/')
                secure = "TRUE" if cookie.get('secure') else "FALSE"
                expiration = int(cookie.get('expiry', time.time() + 3600*24*365))
                name = cookie.get('name', '')
                value = cookie.get('value', '')
                
                f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expiration}\t{name}\t{value}\n")

    def upload(self, video_path, title, hashtags=None, headless=True, browser_name="chrome"):
        """
        Uploads a video to TikTok.
        """
        if not os.path.exists(video_path):
            self.logger.error(f"Video file not found: {video_path}")
            return False

        description = title
        if hashtags:
            tags_str = " ".join([f"#{tag}" for tag in hashtags])
            description = f"{title} {tags_str}"

        try:
            self.logger.info(f"Starting upload for {video_path} using {browser_name}...")
            
            if not os.path.exists(self.cookies_path):
                 self.logger.warning(f"Cookies file not found at {self.cookies_path}. Login required.")
                 return False

            # tiktok-uploader supports 'browser' argument
            result = upload_video(
                filename=video_path,
                description=description,
                cookies=self.cookies_path,
                headless=headless,
                browser=browser_name 
            )
            
            if result:
                self.logger.info("Upload completed successfully.")
                return True
            else:
                self.logger.error("Upload failed.")
                return False

        except Exception as e:
            self.logger.error(f"Error during upload: {str(e)}")
            return False
