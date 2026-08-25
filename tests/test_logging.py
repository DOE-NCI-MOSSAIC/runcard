"""Tests for the _logging module."""

import structlog
from structlog.testing import capture_logs

from ornlkit._logging import get_logger


class TestGetLogger:
    def test_returns_bound_logger(self) -> None:
        log = get_logger()
        assert isinstance(log, structlog._config.BoundLoggerLazyProxy)

    def test_capture_logs_captures_events(self) -> None:
        log = get_logger()
        with capture_logs() as cap:
            log.info("test_event", key="value")
        assert len(cap) == 1
        assert cap[0]["event"] == "test_event"
        assert cap[0]["key"] == "value"
        assert cap[0]["log_level"] == "info"

    def test_bound_initial_values(self) -> None:
        log = get_logger(component="test")
        with capture_logs() as cap:
            log.info("hello")
        assert cap[0]["component"] == "test"
