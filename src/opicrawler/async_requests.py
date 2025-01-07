"""Asynchronous requests."""

import asyncio
import logging
import socket
import urllib.parse
import aiohttp
import stamina
from opicrawler.async_memoize import CoalescingCache

logger = logging.getLogger(__name__)


async def resolve_ip_addresses(url_or_domain: str) -> list[str]:
    """Query DNS for both IPv4 and IPv6 addresses."""
    if "://" in url_or_domain:
        domain = urllib.parse.urlparse(url_or_domain).netloc
    else:
        domain = url_or_domain
    loop = asyncio.get_running_loop()
    answer = await loop.getaddrinfo(host=domain,
                                    port=None,
                                    proto=socket.IPPROTO_TCP)
    ip_addresses = [
        sockaddr[0]
        for (family, socktype, proto, canonname, sockaddr)
        in answer
    ]
    return ip_addresses


def _error_to_retry(exc: Exception) -> bool:
    """Return True if Exception is of specified type."""
    # If the error is an HTTP status error, only retry on 5xx errors.
    if isinstance(exc, aiohttp.ClientResponseError):
        return exc.status >= 500

    # Do not retry on SSL certificate verification errors.
    if isinstance(exc, aiohttp.ClientConnectorCertificateError):
        return False

    # Otherwise retry on all of the following errors.
    return isinstance(exc, (aiohttp.ClientError, asyncio.TimeoutError))


@stamina.retry(
    on=_error_to_retry,
    attempts=4,
    timeout=10,
    wait_initial=1,
    wait_max=5,
    wait_jitter=2,
)
@CoalescingCache(key_argument=1)  # the decorator order matters
async def _fetch_html(session, url):
    async with session.get(url) as response:
        logger.debug(f"GET {url}")
        return await response.text()


@stamina.retry(
    on=_error_to_retry,
    attempts=4,
    timeout=10,
    wait_initial=1,
    wait_max=5,
    wait_jitter=2,
)
@CoalescingCache(key_argument=1)  # the decorator order matters
async def _resolve_redirects(session, start_url):
    """Return the final URL or raise an exception."""
    try:
        # HEAD request
        async with session.head(start_url, allow_redirects=True) as response:
            return str(response.url)
    except aiohttp.ClientResponseError as exc:
        if exc.status == 405:  # Method Not Allowed
            # Fall back to a GET request with a Range header.
            logger.debug(f"HEAD request not allowed for {start_url}")
            headers = {"Range": "bytes=0-0"}
            async with session.get(start_url, headers=headers, allow_redirects=True) as response:
                return str(response.url)
        else:
            raise  # re-raise


async def _resolve_url(session, domain):
    """Find the URL associated with a given domain, attempting HTTPS first."""
    results = {}
    url_resolution_errors = []
    for scheme in ("https", "http"):
        start_url = f"{scheme}://{domain}"
        try:
            results["final_url"] = await _resolve_redirects(session, start_url)
            results["start_url"] = start_url
            break
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            url_resolution_errors.append({
                "start_url": start_url,
                "error": str(exc),
            })
    if url_resolution_errors:
        results["url_resolution_errors"] = url_resolution_errors
    return results


async def _request(session, semaphore, id_domain_pair, counter, callback,
                   opiferum_ip_addresses):
    """Send HEAD, GET and DNS requests."""
    async with semaphore:
        callback(advance_secondary=1)
        data = {}
        data["identifier"], domain = id_domain_pair
        data |= await _resolve_url(session, domain)  # HEAD (+ GET w/ Range)
        if "final_url" in data:
            ip_addresses = await resolve_ip_addresses(data["final_url"])  # DNS
            data["ip_addresses"] = ip_addresses
            if not set(ip_addresses).intersection(opiferum_ip_addresses):
                data["external_to_opiferum"] = True
                return data
            data["external_to_opiferum"] = False
            try:
                data["html"] = await _fetch_html(session, data["final_url"])  # GET
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                data["html_fetch_error"] = str(exc)
        callback(advance=1)
        return data


async def gather_responses(
        id_domain_pairs,
        *,
        concurrency_limit,
        tasks_per_second,
        opiferum_ip_addresses,
        callback,
) -> list[dict]:
    """Send concurrent requests and collect results."""
    semaphore = asyncio.Semaphore(concurrency_limit)
    connector = aiohttp.TCPConnector(limit=concurrency_limit)  # default: 100
    async with aiohttp.ClientSession(connector=connector) as session:
        async with asyncio.TaskGroup() as tg:
            tasks = []
            n = len(id_domain_pairs)
            callback(total=n)
            for i, id_domain_pair in enumerate(id_domain_pairs, 1):
                task = tg.create_task(
                    _request(session, semaphore, id_domain_pair, (i, n), callback,
                             opiferum_ip_addresses)
                )
                tasks.append(task)
                await asyncio.sleep(1/tasks_per_second)
        responses = [task.result() for task in tasks]
        _resolve_redirects.close()
        _fetch_html.close()
        return responses
