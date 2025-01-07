"""Asynchronous screenshots."""

import asyncio
import logging
import stamina
from playwright.async_api import async_playwright, Error
from opicrawler.filepath_utils import ensure_path, filename_safe_encode

logger = logging.getLogger(__name__)


@stamina.retry(
    on=Error,
    attempts=4,
    timeout=30,
    wait_initial=2,
    wait_max=10,
    wait_jitter=2,
)
async def _capture_page(*, context, pagedict, screenshot_path,
        render_wait, full_page, counter, callback):
    """Open a webpage and capture a screenshot of it."""
    callback(advance_secondary=1)
    identifier, url = pagedict["site_id"], pagedict["url"]
    page = await context.new_page()
    await page.goto(url)
    await page.wait_for_timeout(render_wait)
    filename = filename_safe_encode(
        url,
        limit_length=True,
        prefix=f"{identifier}_{counter[0]}=",  # to avoid collisions
        postfix=".png",
    )
    logger.debug(
        f"({counter[0]}/{counter[1]}), {identifier}, {url} -> '{filename}'"
    )
    await page.screenshot(path=screenshot_path/filename,
                          full_page=full_page)
    await page.close()
    callback(advance=1)
    return pagedict


async def _capture_page_with_semaphore(semaphore, **kwargs):
    """Limit concurrency with semaphore and handle specific exceptions."""
    async with semaphore:
        try:
            return await _capture_page(**kwargs)
        except Error as error:
            logger.error(error)
            pagedict = kwargs["pagedict"]
            pagedict["screenshot_error"] = error
            return pagedict


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
            viewport={"width": options["width"], "height": options["height"]},
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
            for i, page in enumerate(pages, 1):
                task = tg.create_task(
                    _capture_page_with_semaphore(
                        semaphore,
                        context=context,
                        pagedict=page,
                        screenshot_path=screenshot_path,
                        render_wait=options["render_wait"],
                        full_page=options["full_page"],
                        counter=(i, n),
                        callback=callback,
                    )
                )
                tasks.append(task)
                await asyncio.sleep(1/options["tasks_per_second"])
        results = [task.result() for task in tasks]
        await context.close()
        return results
