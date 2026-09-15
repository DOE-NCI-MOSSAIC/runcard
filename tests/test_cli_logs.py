"""Tests for the runcard logs CLI subcommand."""

import json

import pytest
from typer.testing import CliRunner

from runcard.cli.app import app
from runcard.cli.logs import (
    _event_candidates,
    _find_run_dirs,
    _fmt_duration,
    _format_event,
    _format_human,
    _progress,
    _read_jsonl_events,
    _read_tail_events,
    _run_candidates,
    _run_context,
    _status,
    _summarize,
)

runner = CliRunner()


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
        result = runner.invoke(app, ["logs", "show", str(log_file)])
        assert result.exit_code == 0, result.output
        out = result.output.splitlines()
        assert out[0] == "# slurm_job_id=123"
        assert out[1].startswith("00:40:41 [info     ] greeting")
        assert "slurm_job_id" not in out[1]

    def test_json_flag(self, tmp_path, capsys) -> None:
        log_file = self._write_log(tmp_path)
        result = runner.invoke(app, ["logs", "show", "--json", str(log_file)])
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["event"] == "greeting"

    def test_json_and_compact_conflict(self, tmp_path) -> None:
        log_file = self._write_log(tmp_path)
        result = runner.invoke(app, ["logs", "show", "--json", "-c", str(log_file)])
        assert result.exit_code != 0

    def test_missing_run_exits_1(self, tmp_path) -> None:
        result = runner.invoke(app, ["logs", "show", str(tmp_path / "nope")])
        assert result.exit_code == 1

    def test_tail_human_default(self, tmp_path, capsys) -> None:
        log_file = self._write_log(tmp_path)
        result = runner.invoke(app, ["logs", "tail", str(log_file)])
        assert result.exit_code == 0, result.output
        assert result.output.splitlines()[-1].startswith("00:40:41 [info     ] greeting")


def _make_run(root, name, overrides="", events=(), records=None):
    """Create a run dir; *events* are bare names, *records* full event dicts."""
    run = root / name
    (run / ".hydra").mkdir(parents=True)
    if overrides:
        (run / ".hydra" / "overrides.yaml").write_text(overrides)
    with open(run / "train.log", "w") as f:
        for ev in events:
            f.write(json.dumps({"level": "info", "event": ev}) + "\n")
        for rec in records or ():
            f.write(json.dumps(rec) + "\n")
    return run


def _ts(i):
    return f"2026-09-15T10:00:{i:02d}.000000-04:00"


_FINISHED = [
    {
        "timestamp": _ts(0),
        "level": "info",
        "event": "environment",
        "hostname": "n1",
        "python_version": "3.12.13",
        "slurm_job_id": "777",
        "slurm_nnodes": "2",
    },
    {"timestamp": _ts(0), "level": "info", "event": "start", "lr": 0.1},
    {"timestamp": _ts(1), "level": "info", "event": "epoch_done", "epoch": 0, "loss": 1.5},
    {"timestamp": _ts(2), "level": "warning", "event": "loss_increased", "epoch": 1},
    {"timestamp": _ts(3), "level": "info", "event": "epoch_done", "epoch": 1, "loss": 0.25},
    {"timestamp": _ts(3), "level": "info", "event": "done", "final_loss": 0.25, "note": "ok"},
    {"timestamp": _ts(4), "level": "info", "event": "run_finished", "elapsed_s": 3.5},
]
_FAILED = _FINISHED[:3] + [
    {
        "timestamp": _ts(2),
        "level": "error",
        "event": "run_failed",
        "elapsed_s": 1.2,
        "exception": "Traceback (most recent call last):\n  ...\nRuntimeError: boom",
    },
]


class TestListCommand:
    def test_plain_output_when_piped(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("runcard.cli.logs.shutil.which", lambda _: None)
        _make_run(tmp_path / "outputs", "a", overrides="- model.lr=0.1\n", records=_FINISHED)
        _make_run(tmp_path / "outputs", "b", records=_FAILED)
        _make_run(tmp_path / "outputs", "c", events=["start"])  # no end marker, fresh file
        result = runner.invoke(app, ["logs", "list"])
        assert result.exit_code == 0, result.output
        lines = [ln.split("\t") for ln in result.output.strip().splitlines()]
        assert lines[0] == ["outputs/a", "finished", "3.5s", "model.lr=0.1"]
        assert lines[1] == ["outputs/b", "failed", "1.2s", ""]
        assert lines[2][:3] == ["outputs/c", "running?", "--"]

    def test_no_runs(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["logs", "list"])
        assert "No run directories found." in result.output


class TestCompletion:
    def test_run_candidates_cover_multirun(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        _make_run(tmp_path / "outputs", "2026-09-13/20-00-00")
        _make_run(tmp_path / "multirun", "2026-09-13/20-00-01/0")
        assert _run_candidates("") == [
            "multirun/2026-09-13/20-00-01/0",
            "outputs/2026-09-13/20-00-00",
        ]
        assert _run_candidates("out") == ["outputs/2026-09-13/20-00-00"]

    def test_event_candidates_from_run(self, tmp_path) -> None:
        run = _make_run(tmp_path, "r", events=["start", "epoch_done", "epoch_done", "done"])
        assert _event_candidates(str(run), "") == ["start", "epoch_done", "done"]
        assert _event_candidates(str(run), "ep") == ["epoch_done"]
        assert _event_candidates(None, "") == []

    @pytest.mark.parametrize("shell", ["bash", "zsh", "fish"])
    def test_completion_script_generates(self, shell) -> None:
        result = runner.invoke(app, ["--show-completion", shell])
        assert result.exit_code == 0, result.output
        assert "runcard" in result.output.lower()


class TestRootCommands:
    def test_version(self) -> None:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert result.output.startswith("runcard ")

    def test_no_args_shows_help(self) -> None:
        result = runner.invoke(app, [])
        assert "check" in result.output and "logs" in result.output

    def test_check_passes_overrides_to_hydra(self, tmp_path) -> None:
        result = runner.invoke(app, ["check", f"hydra.run.dir={tmp_path}", "app.greeting=Howdy"])
        assert result.exit_code == 0, result.output
        assert "Howdy" in result.output
        assert "packages" in result.output
        assert (tmp_path / ".hydra" / "config.yaml").exists()


class TestOverrides:
    def test_list_markers_stripped(self, tmp_path) -> None:
        from runcard.cli.logs import _overrides

        run = _make_run(tmp_path, "r", overrides="- model.lr=0.1\n- +model.dropout=0.2\n")
        assert _overrides(run) == "model.lr=0.1 +model.dropout=0.2"
        run2 = _make_run(tmp_path, "r2", overrides="[]\n")
        assert _overrides(run2) == ""


class TestStatus:
    def test_end_markers(self) -> None:
        assert _status(None, _FINISHED, None) == "finished"
        assert _status(None, _FAILED, None) == "failed"
        with_errors = _FINISHED[:-1] + [{"level": "error", "event": "failed_step"}] + _FINISHED[-1:]
        assert _status(None, with_errors, None) == "finished, 1 error"

    def test_no_marker_uses_slurm_then_mtime(self, tmp_path) -> None:
        log = tmp_path / "x.log"
        log.write_text("{}\n")
        events = [{"event": "start", "slurm_job_id": "777"}]
        assert _status(events[0], events, log, {"777": "RUNNING"}) == "running"
        assert _status(events[0], events, log, {"777": "TIMEOUT"}) == "incomplete"
        assert _status(events[0], events, log, {}) == "running?"  # just written
        import os

        os.utime(log, (0, 0))
        assert _status(events[0], events, log, {}) == "incomplete"


class TestSummary:
    def test_summarize_finished(self, tmp_path) -> None:
        run = _make_run(tmp_path, "r", overrides="- model.lr=0.1\n", records=_FINISHED)
        s = _summarize(run)
        assert s["status"] == "finished"
        assert s["duration_s"] == 3.5
        assert s["hostname"] == "n1"
        assert s["slurm"] == {"job_id": "777", "nnodes": "2"}
        assert s["events"] == {"total": 7, "warnings": 1, "errors": 0}
        assert s["progress"] == {
            "event": "epoch_done",
            "count": 2,
            "fields": {"epoch": [0, 1], "loss": [1.5, 0.25]},
        }
        assert s["last"]["event"] == "done"
        assert s["last"]["fields"] == {"final_loss": 0.25, "note": "ok"}
        assert s["failure"] is None

    def test_last_event_hides_traceback_and_truncates(self, tmp_path) -> None:
        records = _FINISHED[:2] + [
            {
                "timestamp": _ts(2),
                "level": "error",
                "event": "failed_step",
                "step": 1,
                "exception": "Traceback...\nValueError: x",
                "msg": "y" * 100,
            },
            _FINISHED[-1],
        ]
        run = _make_run(tmp_path, "r", records=records)
        fields = _summarize(run)["last"]["fields"]
        assert "exception" not in fields
        assert fields["step"] == 1 and fields["msg"].endswith("...") and len(fields["msg"]) == 60

    def test_summarize_failed_reports_exception(self, tmp_path) -> None:
        run = _make_run(tmp_path, "r", records=_FAILED)
        s = _summarize(run)
        assert s["status"] == "failed"
        assert s["failure"] == "RuntimeError: boom"

    def test_progress_event_override(self, tmp_path) -> None:
        assert _progress(_FINISHED, "start") == {
            "event": "start",
            "count": 1,
            "fields": {"lr": [0.1, 0.1]},
        }
        assert _progress(_FINISHED, "nope") is None

    def test_command_plain_and_json(self, tmp_path) -> None:
        run = _make_run(tmp_path, "r", overrides="- model.lr=0.1\n", records=_FINISHED)
        result = runner.invoke(app, ["logs", "summary", str(run)])
        assert result.exit_code == 0, result.output
        out = result.output
        assert out.splitlines()[0].endswith("finished")
        assert "Progress: epoch_done ×2 · epoch 0 → 1 · loss 1.5 → 0.25" in out
        assert "Where: n1 · python 3.12.13 · job 777 on 2 nodes" in out
        result = runner.invoke(app, ["logs", "summary", "--json", str(run)])
        assert json.loads(result.output)["status"] == "finished"

    def test_missing_run(self, tmp_path) -> None:
        assert runner.invoke(app, ["logs", "summary", str(tmp_path / "nope")]).exit_code == 1


class TestHelpers:
    def test_tail_reader_skips_partial_first_line(self, tmp_path) -> None:
        log = tmp_path / "big.log"
        with open(log, "w") as f:
            for i in range(5000):
                f.write(json.dumps({"event": "e", "i": i, "pad": "x" * 50}) + "\n")
        events = _read_tail_events(log, nbytes=4096)
        assert events and events[-1]["i"] == 4999
        assert all(isinstance(ev, dict) for ev in events)
        assert len(events) < 100

    @pytest.mark.parametrize(
        ("seconds", "text"),
        [(None, "--"), (3.14, "3.1s"), (61, "1m 01s"), (3725, "1h 02m")],
    )
    def test_fmt_duration(self, seconds, text) -> None:
        assert _fmt_duration(seconds) == text
