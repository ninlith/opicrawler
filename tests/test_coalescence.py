"""Coalescing cache test."""

import asyncio
import logging
import random
import time
import pytest
from opicrawler.async_memoize import CoalescingCache


@pytest.mark.asyncio
async def test_coalescing_cache(caplog):
    """Test coalescing cache decorator."""
    caplog.set_level(logging.DEBUG)
    random.seed(0)

    decorator = CoalescingCache(key_argument=0, max_size=2, ttl=0.5, autoclean=True)

    @decorator
    async def func(x):
        await asyncio.sleep(0.1)
        return random.random()

    # Test coalescence.
    start_time = time.perf_counter()
    task1 = asyncio.create_task(func(1))
    task2 = asyncio.create_task(func(1))
    result1, result2 = await asyncio.gather(task1, task2)
    end_time = time.perf_counter()
    assert result1 == result2
    assert end_time - start_time < 0.2

    # Test LRU removal.
    assert 1 in func.cache_access
    assert 1 in decorator.lock_map
    await func(2)
    await func(3)
    assert len(func.cache_access) == 2
    assert 1 not in func.cache_access
    assert 2 in func.cache_access
    assert 3 in func.cache_access
    assert 1 not in decorator.lock_map
    assert 2 in decorator.lock_map
    assert 3 in decorator.lock_map

    # Test TTL expiration.
    await asyncio.sleep(1)
    assert 2 not in func.cache_access
    assert 3 not in func.cache_access
    assert 2 not in decorator.lock_map
    assert 3 not in decorator.lock_map

    # Test cleanup task cancellation.
    func.close()
    assert not hasattr(func, "cleanup_task")
