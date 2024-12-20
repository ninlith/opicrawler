"""Post-installation logic."""

import logging
import re
import subprocess
import zipfile
from pathlib import Path
from urllib.request import urlretrieve
from playwright._impl._driver import compute_driver_executable, get_driver_env
from playwright.sync_api import sync_playwright, Error

logger = logging.getLogger(__name__)

UBOL_URL = "https://github.com/uBlockOrigin/uBOL-home/releases/download/uBOLite_2024.11.20.858/uBOLite_2024.11.20.858.chromium.mv3.zip"  # pylint: disable=line-too-long


def ensure_chromium():
    """Ensure that Chromium is installed."""
    with sync_playwright() as p:
        browser_type = p.chromium
        expected_browser_path = Path(browser_type.executable_path)
        logger.debug(f"{expected_browser_path = }")
        if not expected_browser_path.exists():
            browser_name = browser_type.name.capitalize()
            logger.info(f"Installing {browser_name}...")
            playwright_install(browser_type)


# https://github.com/eggplants/install-playwright-python/blob/master/install_playwright/__init__.py
def playwright_install(browser_type, *, with_deps=False):
    """Run the `playwright install` command."""
    driver_executable, driver_cli = compute_driver_executable()
    args = [driver_executable, driver_cli, "install", browser_type.name]
    if with_deps:
        args.append("--with-deps")
    proc = subprocess.run(args,
                          env=get_driver_env(),
                          capture_output=True,
                          text=True,
                          check=False)
    return proc.returncode == 0


def ensure_ublock_origin_lite(path: Path):
    """Ensure that uBlock Origin Lite is installed."""
    expected_ubol_path = path/re.search(r".*/(.*)\.zip", UBOL_URL).group(1)
    logger.debug(f"{expected_ubol_path = }")
    if not expected_ubol_path.exists():
        logger.info("Installing uBlock Origin Lite...")
        temp_file, _headers = urlretrieve(UBOL_URL)
        temp_file_path = Path(temp_file)
        with zipfile.ZipFile(temp_file_path, "r") as zip_ref:
            zip_ref.extractall(expected_ubol_path)
        temp_file_path.unlink(missing_ok=True)  # delete
    return expected_ubol_path


def launch_browser_window(path_to_extension, user_data_dir):
    """Launch the browser in a non-headless mode"""
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir,
            headless=False,
            args=[
                f"--disable-extensions-except={path_to_extension}",
                f"--load-extension={path_to_extension}",
            ],
        )
        page = context.new_page()
        page.goto("chrome://extensions/")
        page.wait_for_event("close", timeout=0)
        page.close()
        context.close()


def configure_ublock_origin_lite(path_to_extension, user_data_dir):
    """Ensure that uBlock Origin Lite blocks Cookie Notices."""
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir,
            headless=False,
            args=[
                "--headless=new",
                f"--disable-extensions-except={path_to_extension}",
                f"--load-extension={path_to_extension}",
            ],
        )

        # Find out the extension id (which might be derived from the installed directory path).
        background = context.service_workers[0]
        if not background:
            background = context.wait_for_event("serviceworker")
        extension_id = background.url.split("/")[2]
        logger.debug(f"{extension_id = }")

        # Enable Cookie Notices filter list if disabled.
        page = context.new_page()
        page.goto(f"chrome-extension://{extension_id}/dashboard.html")
        page.locator('button[data-pane="rulesets"]').click(timeout=3000)
        checkbox = page.locator('div[data-rulesetid="annoyances-cookies"] input[type="checkbox"]')
        if not checkbox.is_checked():
            logger.debug("Enabling Cookie Notices filter list...")
            checkbox.check(timeout=3000)
            page.wait_for_timeout(5000)  # 2000 seemed to be sufficient for the setting to stick
        page.close()
        context.close()


def ensure_installation(cache_path):
    """Ensure that Chromium and uBlock Origin Lite are installed."""
    ensure_chromium()
    ubol_path = ensure_ublock_origin_lite(cache_path)
    return ubol_path


def ensure_configuration(ubol_path, playwright_user_data_path, manual, *, callback):
    """Ensure that uBlock Origin Lite is configured."""
    try:
        if manual:
            launch_browser_window(ubol_path, playwright_user_data_path)
        else:
            # Ensure uBlock Origin Lite is configured to bypass Cookie Notices.
            configure_ublock_origin_lite(ubol_path, playwright_user_data_path)
            logger.info("Internal browser configuration done.")
    except Error as error:
        logger.error(error)
    callback()
