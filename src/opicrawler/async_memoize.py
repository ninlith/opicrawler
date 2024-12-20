"""Coalescing LRU and TTL function cache."""

import asyncio
import atexit
import logging
import time
from collections import defaultdict, OrderedDict
from functools import wraps

logger = logging.getLogger(__name__)


class CoalescingCache:
    """Decorator to cache function results and coalesce concurrent requests."""

    def __init__(self, key_argument=None, max_size=None, ttl=None, autoclean=True):
        self.key_argument = key_argument
        self.max_size = max_size
        self.ttl = ttl
        self.autoclean = ttl and autoclean
        self.cache = OrderedDict()
        self.lock_map = defaultdict(asyncio.Lock)
        self.stale_lock_keys = set()
        self.func_name = None
        self.cleanup_task = None

    def __call__(self, func):
        """Replace the original function with a wrapped function."""

        @wraps(func)  # preserve metadata of the original function
        async def wrapper(*args, **kwargs):
            """Wrap the original function with additional behavior."""
            if self.key_argument is not None:
                if isinstance(self.key_argument, int):
                    key = args[self.key_argument]
                if isinstance(self.key_argument, str):
                    key = kwargs[self.key_argument]
            else:
                # Use all arguments as a cache key by default.
                key = (args, frozenset(kwargs.items()))

            # Acquire the mutex lock to ensure mutually exclusive access.
            async with self.lock_map[key]:
                # Check if the result is cached (and still valid).
                if key in self.cache:
                    value, timestamp = self.cache[key]
                    if self.ttl is None or time.time() <= timestamp + self.ttl:
                        self.cache.move_to_end(key)  # mark as recently used
                        return value

                # Possibly purge the least recently used item.
                if self.max_size is not None:
                    if len(self.cache) >= self.max_size:
                        lru_key, _lru_value = self.cache.popitem(last=False)
                        self.lock_map.pop(lru_key, None)

                # Call the original function and cache the result.
                result = await func(*args, **kwargs)
                self.cache[key] = (result, time.time())
                return result

        # Attach methods to the wrapper function.
        wrapper.cache_access = self.cache_access
        wrapper.close = self.close

        self.func_name = func.__name__
        if self.autoclean:
            self.cleanup_task = asyncio.create_task(self._cleanup_periodically())
            atexit.register(self._at_exit)
        return wrapper

    async def _cleanup_periodically(self):
        """Periodically remove expired cache items."""
        try:
            while self.autoclean:
                await asyncio.sleep(self.ttl)
                current_time = time.time()
                expired_keys = [
                    key
                    for key, (value, timestamp) in self.cache.items()
                    if current_time > timestamp + self.ttl
                ]
                if expired_keys:
                    logger.debug(f"Time to die. {expired_keys = }")
                for key in expired_keys:
                    del self.cache[key]
                    self.lock_map.pop(key, None)
        except asyncio.CancelledError:
            logger.debug(f"Cleanup task for {self.func_name} cancelled.")

    def _at_exit(self):
        """Exit handler."""
        if self.cleanup_task and not self.cleanup_task.done():
            logger.warning(f"Cleanup task for {self.func_name} still running.")

    @property
    def cache_access(self):
        """Expose cache via a property."""
        return self.cache

    def close(self):
        """Clear cache (and cancel the cleanup task)."""
        if self.autoclean:
            self.cleanup_task.cancel()
        del self.cache
        del self.lock_map
