import inspect
import logging

import pytest

from cody.core.log import log_elapsed


@pytest.mark.asyncio
async def test_log_elapsed_preserves_async_generator_semantics(caplog):
    @log_elapsed("live-generator", level=logging.INFO)
    async def values():
        yield 1
        yield 2

    assert inspect.isasyncgenfunction(values)
    with caplog.at_level(logging.INFO):
        assert [value async for value in values()] == [1, 2]
    assert "live-generator took" in caplog.text
