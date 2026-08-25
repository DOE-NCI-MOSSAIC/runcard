"""Shared test fixtures."""

import pytest
import structlog

from ornlkit._logging import configure_structlog


@pytest.fixture(autouse=True)
def _reset_structlog():
    """Reset structlog before each test so capture_logs works correctly."""
    structlog.reset_defaults()
    configure_structlog(cache_logger_on_first_use=False)
