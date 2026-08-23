"""Pytest fixtures for Intelligence OS testing."""

import shutil
import tempfile
from pathlib import Path
import pytest

from intelligence_os.config.settings import Settings


@pytest.fixture
def temp_workspace(monkeypatch):
    """Create an isolated temporary workspace with data, logs, and output directories."""
    temp_dir = Path(tempfile.mkdtemp(prefix="intel_os_test_"))
    data_dir = temp_dir / "data"
    logs_dir = temp_dir / "logs"
    output_dir = temp_dir / "output"
    db_path = data_dir / "test_intelligence.db"

    settings = Settings(
        base_dir=temp_dir,
        data_dir=data_dir,
        logs_dir=logs_dir,
        output_dir=output_dir,
        database_path=db_path,
        app_env="testing",
    )
    settings.ensure_directories()

    yield settings

    # Teardown
    shutil.rmtree(temp_dir, ignore_errors=True)
