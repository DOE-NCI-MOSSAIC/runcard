"""Tests for the runcard logs CLI subcommand."""

import json

from runcard.cli.logs import (
    _find_run_dirs,
    _format_event,
    _format_human,
    _read_jsonl_events,
    _run_context,
    logs_main,
)


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
            '{"event": "start", "level": "info"}\n{"event": "end", "level": "info"}\n'
        )
        events = _read_jsonl_events(log_file)
        assert len(events) == 2
        assert events[0]["event"] == "start"
        assert events[1]["event"] == "end"

    def test_wraps_non_json_lines(self, tmp_path) -> None:
        log_file = tmp_path / "test.log"
        log_file.write_text('plain text line\n{"event": "structured"}\n')
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


class TestFormatHuman:
    def test_hides_run_context_keys(self) -> None:
        event = {
            "timestamp": "2026-09-14T00:40:41.540391Z",
            "level": "info",
            "logger": "root",
            "event": "greeting",
            "message": "hi",
            "slurm_job_id": "123",
            "hostname": "node1",
        }
        line = _format_human(event, colors=False)
        assert line.startswith("00:40:41 [info     ] greeting")
        assert "message=hi" in line
        assert "slurm_job_id" not in line
        assert "hostname" not in line

    def test_raw_line_passthrough(self) -> None:
        assert _format_human({"raw": "plain text"}, colors=False) == "plain text"


class TestRunContext:
    def test_from_first_event_with_context(self) -> None:
        events = [{"event": "a"}, {"event": "b", "slurm_job_id": "1", "hostname": "n"}]
        assert _run_context(events) == {"hostname": "n", "slurm_job_id": "1"}

    def test_empty(self) -> None:
        assert _run_context([{"event": "a"}]) == {}


class TestShowCommand:
    def _write_log(self, tmp_path):
        log_file = tmp_path / "run.log"
        log_file.write_text(
            json.dumps(
                {
                    "timestamp": "2026-09-14T00:40:41.540391Z",
                    "level": "info",
                    "logger": "root",
                    "event": "greeting",
                    "message": "hi",
                    "slurm_job_id": "123",
                }
            )
            + "\n"
        )
        return log_file

    def test_human_default_prints_context_header(self, tmp_path, capsys) -> None:
        log_file = self._write_log(tmp_path)
        logs_main(["show", str(log_file)])
        out = capsys.readouterr().out.splitlines()
        assert out[0] == "# slurm_job_id=123"
        assert out[1].startswith("00:40:41 [info     ] greeting")
        assert "slurm_job_id" not in out[1]

    def test_json_flag(self, tmp_path, capsys) -> None:
        log_file = self._write_log(tmp_path)
        logs_main(["show", "--json", str(log_file)])
        out = capsys.readouterr().out
        assert json.loads(out)["event"] == "greeting"

    def test_tail_human_default(self, tmp_path, capsys) -> None:
        log_file = self._write_log(tmp_path)
        logs_main(["tail", str(log_file)])
        out = capsys.readouterr().out.splitlines()
        assert out[-1].startswith("00:40:41 [info     ] greeting")
