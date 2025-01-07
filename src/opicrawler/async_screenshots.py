"""Asynchronous screenshots."""

import asyncio
import logging
import stamina
from playwright.async_api import async_playwright, Error
from opicrawler.filepath_utils import ensure_path, sanitize_url_to_filename

logger = logging.getLogger(__name__)


@stamina.retry(
    on=Error,
    attempts=4,
    timeout=30,
    wait_initial=2,
    wait_max=10,
    wait_jitter=2,
)
async def _capture_page(page_data, context, screenshot_path, render_wait,
        full_page, resolutions, filetype, callback):
    """Open a webpage and capture screenshots of it."""
    callback(advance_secondary=1)
    identifier, url = page_data["site_id"], page_data["url"]
    page = await context.new_page()
    for resolution in resolutions:
        width, height = map(int, resolution.split("x"))
        await page.set_viewport_size({"width": width, "height": height})
        # "A lot of websites don't expect phones to change size, so you should
        # set the viewport size before navigating to the page."
        await page.goto(url)
        await page.wait_for_timeout(render_wait)
        filename = sanitize_url_to_filename(
            url,
            limit_length=True,
            prefix=f"{identifier}_{width}x{height}_",
            postfix=f".{filetype}",
        )
        await page.screenshot(path=screenshot_path/f"{width}x{height}"/filename,
                              full_page=full_page)
    await page.close()
    callback(advance=1)
    return page_data


async def _capture_page_with_semaphore(semaphore, page_data, **kwargs):
    """Limit concurrency with semaphore and handle specific exceptions."""
    async with semaphore:
        try:
            return await _capture_page(page_data, **kwargs)
        except Error as error:
            logger.error(error)
            page_data["screenshot_error"] = error
            return page_data


async def capture_screenshots(
        *,  # PEP 3102
        pages,
        path_to_extension,
        user_data_dir,
        callback,
        options,
):
    """Take multiple screenshots in headless mode with an extension."""
    screenshot_path = ensure_path(options["output_path"]/"screenshots")
    semaphore = asyncio.Semaphore(options["concurrency_limit"])
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir,
            headless=False,  # needs to be False apparently
            args=[
                "--headless=new",
                "--hide-scrollbars",
                f"--disable-extensions-except={path_to_extension}",
                f"--load-extension={path_to_extension}",
            ],
        )
        tasks = []
        async with asyncio.TaskGroup() as tg:
            n = len(pages)
            callback(total=n)
            for page in pages:
                task = tg.create_task(
                    _capture_page_with_semaphore(
                        semaphore,
                        page,
                        context=context,
                        screenshot_path=screenshot_path,
                        render_wait=options["render_wait"],
                        full_page=options["full_page"],
                        resolutions=options["resolutions"],
                        filetype=options["filetype"],
                        callback=callback,
                    )
                )
                tasks.append(task)
                await asyncio.sleep(1/options["tasks_per_second"])
        results = [task.result() for task in tasks]
        await context.close()
        return results
