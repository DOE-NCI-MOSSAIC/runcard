"""Tests for the _logging module."""

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars
from structlog.testing import capture_logs

from ornlkit._logging import (
    add_local_timestamp,
    get_logger,
    merge_run_context,
    render_console_line,
)


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


class TestMergeRunContext:
    def test_marks_keys_merged_from_context(self) -> None:
        clear_contextvars()
        bind_contextvars(slurm_job_id="1", hostname="node1")
        try:
            ev = merge_run_context(None, "info", {"event": "x", "hostname": "explicit"})
        finally:
            clear_contextvars()
        assert ev["slurm_job_id"] == "1"
        # Explicit kwargs win and are not marked as context.
        assert ev["hostname"] == "explicit"
        assert ev["_run_context"] == ["slurm_job_id"]


class TestAddLocalTimestamp:
    def test_iso_local_with_offset(self) -> None:
        from datetime import datetime

        ts = add_local_timestamp(None, "info", {})["timestamp"]
        parsed = datetime.fromisoformat(ts)
        assert parsed.tzinfo is not None
        assert parsed.utcoffset() == datetime.now().astimezone().utcoffset()
        # Console slicing relies on this layout.
        assert ts[10] == "T" and ts[19] == "."


class TestRenderConsoleLine:
    def _event(self, **extra) -> dict:
        return {
            "timestamp": "2026-09-14T00:40:41.540391Z",
            "level": "info",
            "logger": "root",
            "event": "greeting",
            "message": "hi",
            **extra,
        }

    def test_compact_prefix(self) -> None:
        line = render_console_line(self._event(), colors=False)
        assert line.startswith("00:40:41 [info     ] greeting")
        assert "[root]" not in line
        assert "message=hi" in line

    def test_hides_context_keys_but_keeps_explicit_ones(self) -> None:
        ev = self._event(slurm_job_id="1", hostname="node1", _run_context=["slurm_job_id"])
        line = render_console_line(ev, colors=False)
        assert "slurm_job_id" not in line
        assert "hostname=node1" in line

    def test_named_logger_is_shown(self) -> None:
        line = render_console_line(self._event(logger="mymodule"), colors=False)
        assert "[mymodule]" in line

    def test_does_not_mutate_input(self) -> None:
        ev = self._event()
        render_console_line(ev, colors=False)
        assert ev["timestamp"] == "2026-09-14T00:40:41.540391Z"
