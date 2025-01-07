"""Main module."""

import asyncio
import contextlib
import logging
import multiprocessing
import pickle
import signal
import sys
import time
import threading
from concurrent.futures import ProcessPoolExecutor
from functools import partial
import platformdirs
from opicrawler import PACKAGE_NAME, __version__, orm
from opicrawler.async_ai_extraction import gather_extracts
from opicrawler.async_requests import gather_responses, resolve_ip_addresses
from opicrawler.async_screenshots import capture_screenshots
from opicrawler.console_args import parse_arguments
from opicrawler.eyecandy import setup_eyecandy
from opicrawler.filepath_utils import ensure_path
from opicrawler.logging import setup_logging
from opicrawler.post_install import ensure_configuration, ensure_installation
from opicrawler.preprocess import convert_html_to_text, parse_domains_file
from opicrawler.report import write_report

logger = logging.getLogger(__name__)


async def _termination_signal_handler(signal_number, loop):
    """Graceful exit."""
    signal_name = signal.Signals(signal_number).name
    logger.warning(f"{signal_name} received. Cancelling all tasks.")
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=False)
    loop.stop()


def _setup_signal_handlers():
    """Set up termination signal handlers."""
    signals = [signal.SIGINT, signal.SIGTERM]
    if hasattr(signal, "SIGHUP"):  # only add SIGHUP if it exists (e.g., on Unix)
        signals.append(signal.SIGHUP)
    loop = asyncio.get_event_loop()
    try:
        for s in signals:
            loop.add_signal_handler(
                s, lambda s=s: asyncio.create_task(_termination_signal_handler(s, loop)))
                # To prevent late bindings, the s is bound immediately:
                # https://docs.python-guide.org/writing/gotchas/#late-binding-closures
    except NotImplementedError:
        logger.debug("Signal handler not allowed to interact with the event loop.")
        for s in signals:
            signal.signal(s, lambda sig=s, frame=None: asyncio.run_coroutine_threadsafe(
                _termination_signal_handler(sig, loop), loop
            ))


async def async_main():
    """Run the program."""
    start_time = time.perf_counter()
    multiprocessing.set_start_method("spawn", force=True)  # force for tests
    console_args = parse_arguments()

    # Define (and create) paths.
    output_path = ensure_path(console_args.output)
    cache_path = ensure_path(
        platformdirs.user_cache_path(appname=PACKAGE_NAME, appauthor=False))
    log_path = ensure_path(
        platformdirs.user_log_path(appname=PACKAGE_NAME, appauthor=False))
    playwright_user_data_path = ensure_path(cache_path/"playwright-user-data")

    # Start logging.
    setup_logging(console_args.loglevel, log_path/f"{PACKAGE_NAME}.log")
    logger.info(f"{PACKAGE_NAME} {__version__}")
    logger.info(f"{log_path = }")
    logger.info(f"{cache_path = }")
    logger.debug(console_args)

    _setup_signal_handlers()

    # Start live display.
    progress_bar, progress_status, live_display = setup_eyecandy()

    if not console_args.no_screenshots or console_args.browser_window:
        # Ensure that internal browser setup is installed.
        config_status_id = progress_status.add_task("Ensuring internal browser setup")
        ubol_path = await asyncio.to_thread(ensure_installation, cache_path)

        # Ensure that internal browser setup is configured.
        if console_args.browser_window:
            progress_status.update(
                config_status_id, description="Running internal browser"
            )
        ensure_configuration_thread = threading.Thread(
            target=ensure_configuration,
            args=(
                ubol_path,
                playwright_user_data_path,
                console_args.browser_window,
            ),
            kwargs={
                "callback": lambda: progress_status.remove_task(config_status_id),
            },
        )
        ensure_configuration_thread.start()

    orm.setup_engine(output_path/(PACKAGE_NAME + ".sqlite"))
    if not console_args.database:
        opiferum_ip_addresses = await resolve_ip_addresses("opiferum.fi")
        orm.create_db_and_tables()
        orm.create_or_replace_opiferum_ips(opiferum_ip_addresses)

    if console_args.responses:
        # Deserialize responses from a pickle file.
        logger.debug(f"Loading responses from '{console_args.responses.name}'")
        with open(console_args.responses.name, "rb") as f:
            responses = pickle.load(f)
    elif console_args.domains:
        # Read the domain list.
        id_domain_pairs = parse_domains_file(console_args.domains)

        # Send requests and collect responses.
        fetch_bar_id = progress_bar.add_task("Fetching responses")
        responses = await gather_responses(
            id_domain_pairs,
            concurrency_limit=console_args.fetching_concurrency,
            tasks_per_second=console_args.fetching_spawn_rate,
            opiferum_ip_addresses=opiferum_ip_addresses,
            callback=partial(progress_bar.update, fetch_bar_id),
        )
        logger.info("Fetching done.")
        progress_bar.remove_task(fetch_bar_id)

        # Allow asyncio to stabilize to prevent ConnectionResetError messages
        # flooding the debug log (in Windows).
        if (hasattr(asyncio, "ProactorEventLoop")
                and isinstance(asyncio.get_event_loop(), asyncio.ProactorEventLoop)):
            waiting_status_id = progress_status.add_task("Waiting for asyncio to stabilize")
            await asyncio.sleep(1)
            progress_status.remove_task(waiting_status_id)
    elif console_args.database:
        pass
    else:  # no input
        if not console_args.no_screenshots or console_args.browser_window:
            ensure_configuration_thread.join()
        if not console_args.browser_window:
            logger.warning("No input.")
        live_display.stop()
        sys.exit(0)

    processing_status_id = progress_status.add_task("Processing responses")
    if not console_args.responses and not console_args.database:
        # Serialize responses to a pickle file.
        responses_pickle_path = output_path/"responses.pkl"
        with open(responses_pickle_path, "wb") as f:
            pickle.dump(responses, f)
        logger.info(f"Responses saved to '{responses_pickle_path}'")

    if not console_args.database:
        orm.create_or_replace_structured_responses(responses)
        del responses
    pages = orm.select_pages()
    progress_status.remove_task(processing_status_id)

    if not console_args.no_extraction:
        # Convert HTML to plain-text Markdown.
        converting_status_id = progress_status.add_task("Converting HTML to plain-text Markdown")
        with ProcessPoolExecutor() as executor:
            pages = list(executor.map(convert_html_to_text, pages))
        logger.info("Preprocessing done.")
        progress_status.remove_task(converting_status_id)

        # Use the OpenAI API to extract data.
        extraction_bar_id = progress_bar.add_task("Extracting data")
        pages = await gather_extracts(
            pages,
            console_args.extraction_concurrency,
            console_args.extraction_spawn_rate,
            console_args.openai_model,
            callback=partial(progress_bar.update, extraction_bar_id),
        )
        orm.update_pages(pages)
        progress_bar.remove_task(extraction_bar_id)
        logger.info("AI data extraction done.")

    # Take screenshots.
    if not console_args.no_screenshots:
        # Wait for configuration thread to finish.
        ensure_configuration_thread.join()

        screenshot_bar_id = progress_bar.add_task("Capturing screenshots")
        pages = await capture_screenshots(
            pages=pages,
            path_to_extension=ubol_path,
            user_data_dir=playwright_user_data_path,
            callback=partial(progress_bar.update, screenshot_bar_id),
            options={
                "concurrency_limit": console_args.screenshot_concurrency,
                "tasks_per_second": console_args.screenshot_spawn_rate,
                "output_path": output_path,
                "render_wait": console_args.render_wait,
                "full_page": console_args.full_page,
                "resolutions": console_args.resolutions,
                "filetype": console_args.filetype,
            },
        )
        orm.update_pages(pages)
        progress_bar.remove_task(screenshot_bar_id)
        logger.info("Screenshots captured.")

    # Write a report.
    write_report(output_path)
    logger.info("Report written.")

    live_display.stop()
    elapsed_time = time.perf_counter() - start_time
    logger.info(f"All done. {elapsed_time = } s")


def main():
    """Start the event loop manager."""
    with contextlib.suppress(asyncio.CancelledError):
        asyncio.run(async_main())
