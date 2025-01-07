"""Console output test. Run with `pdm consoletest`."""

import asyncio
import contextlib
import io
import logging
import random
import string
import tempfile
import time
from unittest.mock import AsyncMock, patch
import pytest
from aioresponses import aioresponses, CallbackResult

logger = logging.getLogger(__name__)


async def mock_getaddrinfo(host, *args, **kwargs):
    """Return a fake IP with a delay."""
    await asyncio.sleep(0.01)
    return [(2, 1, 6, '', ('123.45.67.89', 0))]


def mock_ensure_configuration(*args, **kwargs):
    """Simulate ensure_configuration."""
    time.sleep(2)
    kwargs["callback"]()
    logger.info("Internal browser configuration done.")


async def aioresponse_callback(url, **kwargs):
    """Response with a delay."""
    await asyncio.sleep(1)
    html = "<!doctype html><title>.</title>content"
    return CallbackResult(body=html, status=200)


async def mock_capture_screenshots(*args, **kwargs):
    """Simulate capture_screenshots."""

    async def mock_capture_page(semaphore, callback, counter):
        """Simulate capture_page."""
        async with semaphore:
            filename = "".join(random.sample(string.ascii_letters + string.digits + "-_=", 40))
            logger.debug(f"({counter[0]}/{counter[1]}), {counter[0]}, "
                         f"https://label.test/ -> '{filename}.png'")
            await asyncio.sleep(2)
            callback(advance=1)

    callback = kwargs["callback"]
    pages = kwargs["pages"]
    tasks_per_second = kwargs["options"]["tasks_per_second"]
    concurrency_limit = kwargs["options"]["concurrency_limit"]
    semaphore = asyncio.Semaphore(concurrency_limit)
    async with asyncio.TaskGroup() as tg:
        n = len(pages)
        callback(total=n)
        for i, _ in enumerate(pages):
            task = tg.create_task(
                mock_capture_page(semaphore, callback, (i, n))
            )
            callback(advance_secondary=1)
            await asyncio.sleep(1/tasks_per_second)


async def mock_extract_data(*args, **kwargs):
    """Simulate data extraction."""
    callback = kwargs["callback"]
    page = kwargs["page"]
    callback(advance_secondary=1)
    await asyncio.sleep(1)
    callback(advance=1)
    page["ai_extracts"] = "..."
    return page


@pytest.mark.integration
@pytest.mark.asyncio
@patch("opicrawler.post_install.ensure_installation", side_effect=lambda *args, **kwargs: None)
@patch("opicrawler.post_install.ensure_configuration", side_effect=mock_ensure_configuration)
@patch("opicrawler.async_ai_extraction._extract_data", side_effect=mock_extract_data)
@patch("opicrawler.async_screenshots.capture_screenshots", side_effect=mock_capture_screenshots)
@patch("opicrawler.report.write_report", side_effect=lambda *args, **kwargs: None)
@patch("asyncio.get_running_loop", autospec=True)  # used with mock_getaddrinfo
async def test_program_main(mock_loop, mwr, mcs, mai, mec, mei, extra):
    """Run async_main with mocking."""
    from opicrawler.main import async_main
    mock_loop.return_value.getaddrinfo = AsyncMock(side_effect=mock_getaddrinfo)
    domains = ["valid.test"]*9 + ["invalid.test"]
    input_data = "\n".join(f"{i} {domains[i%len(domains)]}" for i in range(100))
    with tempfile.TemporaryDirectory() as temp_dir_name:
        options = ["opicrawler", "--domains", "-", "--output", temp_dir_name]
        if extra and "debug" in extra:
            options += ["--debug"]
        if extra and "fetchonly" in extra:
            options += ["--no-screenshots", "--no-extraction"]
        with (
            aioresponses() as m,
            patch("sys.stdin", new=io.StringIO(input_data)),
            patch("sys.argv", new=options),
            contextlib.suppress(SystemExit, asyncio.CancelledError),
        ):
            m.get(f"https://{domains[0]}", repeat=True, callback=aioresponse_callback)
            m.head(f"https://{domains[0]}", repeat=True)
            await async_main()
