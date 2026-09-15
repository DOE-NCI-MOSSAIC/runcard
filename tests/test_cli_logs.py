"""Tests for the runcard logs CLI subcommand."""

import json

import pytest
from typer.testing import CliRunner

from runcard.cli.app import app
from runcard.cli.logs import (
    _event_candidates,
    _find_run_dirs,
    _format_event,
    _format_human,
    _read_jsonl_events,
    _run_candidates,
    _run_context,
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


def _make_run(root, name, overrides="", events=()):
    run = root / name
    (run / ".hydra").mkdir(parents=True)
    if overrides:
        (run / ".hydra" / "overrides.yaml").write_text(overrides)
    with open(run / "train.log", "w") as f:
        for ev in events:
            f.write(json.dumps({"level": "info", "event": ev}) + "\n")
    return run


class TestListCommand:
    def test_plain_output_when_piped(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        _make_run(tmp_path / "outputs", "a", overrides="- model.lr=0.1\n", events=["start"])
        result = runner.invoke(app, ["logs", "list"])
        assert result.exit_code == 0, result.output
        assert result.output.strip() == "outputs/a  (1 log file(s)) - model.lr=0.1"

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
