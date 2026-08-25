"""Tests for the ornlkit logs CLI subcommand."""

import json

from ornlkit.cli.logs import _find_run_dirs, _format_event, _read_jsonl_events


class TestFindRunDirs:
    def test_finds_hydra_dirs(self, tmp_path) -> None:
        run1 = tmp_path / "outputs" / "2024-01-01" / "run1"
        (run1 / ".hydra").mkdir(parents=True)
        run2 = tmp_path / "outputs" / "2024-01-02" / "run2"
        (run2 / ".hydra").mkdir(parents=True)
        # Not a run dir — no .hydra
        (tmp_path / "outputs" / "other").mkdir(parents=True)

        dirs = _find_run_dirs([str(tmp_path / "outputs")])
        assert len(dirs) == 2
        assert run1 in dirs
        assert run2 in dirs

    def test_empty_when_no_runs(self, tmp_path) -> None:
        (tmp_path / "outputs").mkdir()
        dirs = _find_run_dirs([str(tmp_path / "outputs")])
        assert dirs == []


class TestReadJsonlEvents:
    def test_reads_valid_jsonl(self, tmp_path) -> None:
        log_file = tmp_path / "test.log"
        log_file.write_text(
            '{"event": "start", "level": "info"}\n'
            '{"event": "end", "level": "info"}\n'
        )
        events = _read_jsonl_events(log_file)
        assert len(events) == 2
        assert events[0]["event"] == "start"
        assert events[1]["event"] == "end"

    def test_wraps_non_json_lines(self, tmp_path) -> None:
        log_file = tmp_path / "test.log"
        log_file.write_text(
            "plain text line\n"
            '{"event": "structured"}\n'
        )
        events = _read_jsonl_events(log_file)
        assert len(events) == 2
        assert events[0] == {"raw": "plain text line"}
        assert events[1]["event"] == "structured"

    def test_skips_empty_lines(self, tmp_path) -> None:
        log_file = tmp_path / "test.log"
        log_file.write_text('{"event": "a"}\n\n{"event": "b"}\n')
        events = _read_jsonl_events(log_file)
        assert len(events) == 2


class TestFormatEvent:
    def test_compact_format(self) -> None:
        event = {"event": "test", "key": "value"}
        result = _format_event(event, compact=True)
        assert json.loads(result) == event
        assert "\n" not in result

    def test_pretty_format(self) -> None:
        event = {"event": "test", "key": "value"}
        result = _format_event(event, compact=False)
        assert json.loads(result) == event
        assert "\n" in result
