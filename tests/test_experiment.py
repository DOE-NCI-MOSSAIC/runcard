"""Tests for the ornlkit_main decorator and Hydra config integration."""

import argparse
import json
import sys

import pytest
from hydra import compose, initialize_config_dir

from ornlkit.experiment import ornlkit_main

# Absolute path to ornlkit's own conf/ directory for tests
_CONF_DIR = str(
    __import__("pathlib").Path(__file__).resolve().parent.parent / "src" / "ornlkit" / "conf"
)

# Hydra 1.3 uses a LazyCompletionHelp object that doesn't implement __contains__,
# which breaks Python 3.14's stricter argparse validation.  Disable the check
# when running under affected Python versions.
_NEED_ARGPARSE_PATCH = sys.version_info >= (3, 14)


@pytest.fixture()
def _patch_argparse(monkeypatch):
    """Disable argparse help-string validation that is incompatible with Hydra on Python 3.14+."""
    if _NEED_ARGPARSE_PATCH:
        monkeypatch.setattr(argparse.ArgumentParser, "_check_help", lambda self, action: None)


class TestHydraConfig:
    def test_default_config_loads(self) -> None:
        with initialize_config_dir(version_base=None, config_dir=_CONF_DIR):
            cfg = compose(config_name="config")
            assert cfg.app.greeting == "Hello from ornlkit"

    def test_override_config_value(self) -> None:
        with initialize_config_dir(version_base=None, config_dir=_CONF_DIR):
            cfg = compose(config_name="config", overrides=["app.greeting=Hi"])
            assert cfg.app.greeting == "Hi"


class TestOrnlkitMainDecorator:
    def test_decorator_returns_callable(self) -> None:
        @ornlkit_main(config_path="conf", config_name="config")
        def dummy(cfg):
            pass

        assert callable(dummy)

    def test_decorator_preserves_function_name(self) -> None:
        @ornlkit_main(config_path="conf", config_name="config")
        def my_experiment(cfg):
            pass

        assert my_experiment.__name__ == "my_experiment"

    @pytest.mark.usefixtures("_patch_argparse")
    def test_diagnostics_logged_on_run(self, capsys, monkeypatch) -> None:
        """Verify that diagnostics are logged when the decorated function runs."""
        captured_greetings = []

        @ornlkit_main(
            config_path=_CONF_DIR,
            config_name="config",
            core_packages=("pydantic",),
        )
        def experiment(cfg):
            captured_greetings.append(cfg.app.greeting)

        # Hydra expects sys.argv for CLI parsing; override to avoid test-runner args
        monkeypatch.setattr("sys.argv", ["experiment"])
        experiment()

        # Hydra manages its own logging handlers (stdout), so check captured output
        out = capsys.readouterr().out
        assert "environment" in out
        assert "packages" in out
        # Run context (hostname, SLURM vars) is hidden from console lines.
        assert "hostname=" not in out.split("environment", 1)[1].split("\n", 1)[1]
        assert "[root]" not in out
        assert len(captured_greetings) == 1
        assert captured_greetings[0] == "Hello from ornlkit"

    @pytest.mark.usefixtures("_patch_argparse")
    def test_exception_traceback_written_to_json_log(self, tmp_path, monkeypatch) -> None:
        """log.exception() must land in the JSON file with the traceback text."""
        from ornlkit._logging import get_logger

        log = get_logger("exc_test")

        @ornlkit_main(config_path=_CONF_DIR, config_name="config", core_packages=())
        def experiment(cfg):
            try:
                raise ValueError("boom")
            except ValueError:
                log.exception("failed_step", step=1)

        monkeypatch.setattr("sys.argv", ["experiment", f"hydra.run.dir={tmp_path}"])
        experiment()

        (log_file,) = tmp_path.glob("*.log")
        [line] = [ln for ln in log_file.read_text().splitlines() if "failed_step" in ln]
        event = json.loads(line)
        assert event["step"] == 1
        assert "ValueError: boom" in event["exception"]
        assert "exc_info" not in event

    @pytest.mark.usefixtures("_patch_argparse")
    def test_cli_override(self, capsys, monkeypatch) -> None:
        """Verify that Hydra CLI overrides work through the decorator."""
        captured = []

        @ornlkit_main(
            config_path=_CONF_DIR,
            config_name="config",
            core_packages=(),
        )
        def experiment(cfg):
            captured.append(cfg.app.greeting)

        monkeypatch.setattr("sys.argv", ["experiment", "app.greeting=Howdy"])
        experiment()

        assert captured[0] == "Howdy"
