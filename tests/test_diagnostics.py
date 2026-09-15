"""Tests for the diagnostics module."""

from structlog.testing import capture_logs

from runcard.diagnostics import (
    DiagnosticsReport,
    _get_package_version,
    collect_diagnostics,
    log_diagnostics,
)


class TestCollectDiagnostics:
    def test_hostname_populated(self) -> None:
        report = collect_diagnostics()
        assert report.hostname

    def test_python_version_format(self) -> None:
        report = collect_diagnostics()
        assert "." in report.python_version

    def test_core_packages_present(self) -> None:
        report = collect_diagnostics()
        assert "polars" in report.packages
        assert "pydantic" in report.packages
        assert report.packages["polars"] != "NOT FOUND"

    def test_slurm_inactive_outside_job(self) -> None:
        report = collect_diagnostics()
        assert report.slurm.job_id is None

    def test_slurm_active_when_env_set(self, monkeypatch: object) -> None:
        monkeypatch.setenv("SLURM_JOB_ID", "12345")
        monkeypatch.setenv("SLURM_NODELIST", "node[001-004]")
        monkeypatch.setenv("SLURM_NNODES", "4")
        monkeypatch.setenv("SLURM_NTASKS", "16")
        monkeypatch.setenv("SLURM_CLUSTER_NAME", "frontier")
        report = collect_diagnostics()
        assert report.slurm.job_id == "12345"
        assert report.slurm.nodelist == "node[001-004]"
        assert report.slurm.nnodes == "4"
        assert report.slurm.ntasks == "16"
        assert report.slurm.cluster_name == "frontier"

    def test_elapsed_seconds_non_negative(self) -> None:
        report = collect_diagnostics()
        assert report.elapsed_seconds >= 0.0


class TestLogDiagnostics:
    def test_emits_three_flat_events(self) -> None:
        with capture_logs() as cap:
            log_diagnostics()
        assert [e["event"] for e in cap] == ["environment", "slurm", "packages"]
        env, _, packages = cap
        assert "hostname" in env
        assert "python_version" in env
        assert "polars" in packages
        # No nested dicts: every value fits on one console line.
        for ev in cap:
            assert not any(isinstance(v, dict) for v in ev.values())

    def test_slurm_inactive_outside_job(self) -> None:
        with capture_logs() as cap:
            log_diagnostics()
        slurm = cap[1]
        assert slurm["active"] is False
        assert "job_id" not in slurm

    def test_slurm_active_when_env_set(self, monkeypatch) -> None:
        monkeypatch.setenv("SLURM_JOB_ID", "99999")
        with capture_logs() as cap:
            log_diagnostics()
        slurm = cap[1]
        assert slurm["active"] is True
        assert slurm["job_id"] == "99999"

    def test_returns_report(self) -> None:
        with capture_logs():
            report = log_diagnostics()
        assert isinstance(report, DiagnosticsReport)


class TestCustomCorePackages:
    def test_custom_core_packages_collect(self) -> None:
        report = collect_diagnostics(core_packages=("pydantic", "orjson"))
        assert set(report.packages.keys()) == {"pydantic", "orjson"}

    def test_custom_core_packages_log(self) -> None:
        with capture_logs() as cap:
            report = log_diagnostics(core_packages=("pydantic",))
        assert set(report.packages.keys()) == {"pydantic"}
        packages = cap[2]
        assert packages["event"] == "packages"
        assert packages["pydantic"] == report.packages["pydantic"]

    def test_empty_core_packages(self) -> None:
        report = collect_diagnostics(core_packages=())
        assert report.packages == {}


class TestGetPackageVersion:
    def test_known_package(self) -> None:
        version = _get_package_version("polars")
        assert version != "NOT FOUND"
        assert "." in version

    def test_unknown_package(self) -> None:
        assert _get_package_version("no-such-package-xyz-999") == "NOT FOUND"
