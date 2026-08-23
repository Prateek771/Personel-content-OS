"""Tests for Phase 2: Project Foundation (Settings, Logging, Exceptions, Health, CLI)."""

import os
from pathlib import Path
import pytest
from typer.testing import CliRunner

from intelligence_os.config.settings import Settings, get_settings
from intelligence_os.core.exceptions import (
    ConfigurationError,
    IntelligenceOSError,
    StorageError,
)
from intelligence_os.core.logger import setup_logger
from intelligence_os.core.health import run_health_check
from intelligence_os.cli import app

runner = CliRunner()


def test_settings_default_instantiation(temp_workspace: Settings) -> None:
    """Verify settings instantiate with clean paths and default values."""
    assert temp_workspace.app_name == "AI Content Intelligence OS"
    assert temp_workspace.app_env == "testing"
    assert temp_workspace.data_dir.exists()
    assert temp_workspace.logs_dir.exists()
    assert temp_workspace.output_dir.exists()


def test_openrouter_validation_failure() -> None:
    """Verify validate_openrouter raises ConfigurationError when key is unset or empty."""
    settings = Settings(openrouter_api_key="")
    with pytest.raises(ConfigurationError) as exc_info:
        settings.validate_openrouter()
    assert "OPENROUTER_API_KEY is not configured" in str(exc_info.value)


def test_custom_exception_formatting() -> None:
    """Verify custom exception serialization and details formatting."""
    err = StorageError("Failed to open SQLite database", details={"path": "data/db.sqlite", "code": 5})
    assert "Failed to open SQLite database" in str(err)
    assert "Details: {'path': 'data/db.sqlite', 'code': 5}" in str(err)
    assert isinstance(err, IntelligenceOSError)


def test_structured_logger(temp_workspace: Settings) -> None:
    """Verify structured logger writes to log file."""
    log_dir = temp_workspace.logs_dir
    test_logger = setup_logger(name="test_logger", log_level="DEBUG", logs_dir=log_dir)
    test_logger.info("Test log message for foundation verification")

    log_file = log_dir / "intelligence_os.log"
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "Test log message for foundation verification" in content
    assert "INFO" in content


def test_health_check_execution(temp_workspace: Settings) -> None:
    """Verify health check executes and returns structured healthy status."""
    health_result = run_health_check(temp_workspace)
    assert health_result["status"] == "healthy"
    assert "directories" in health_result["checks"]
    assert "database" in health_result["checks"]
    assert "credentials" in health_result["checks"]
    assert health_result["checks"]["database"]["accessible"] is True


def test_cli_version_command() -> None:
    """Verify CLI version command output."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "AI Content Intelligence OS" in result.stdout
    assert "v0.1.0" in result.stdout


def test_cli_health_command_json() -> None:
    """Verify CLI health command with --json flag."""
    result = runner.invoke(app, ["health", "--json"])
    assert result.exit_code == 0
    assert '"status":' in result.stdout
    assert '"directories":' in result.stdout


def test_cli_check_config_command() -> None:
    """Verify CLI check-config command."""
    result = runner.invoke(app, ["check-config"])
    assert result.exit_code == 0
    assert "Configuration loaded successfully." in result.stdout
