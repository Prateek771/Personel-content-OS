"""System health check and diagnostic module."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from intelligence_os.core.logger import logger

if TYPE_CHECKING:
    from intelligence_os.config.settings import Settings


def run_health_check(settings: Settings | None = None) -> dict[str, Any]:
    """Execute a comprehensive local health check on environment, directories, storage, and keys."""
    if settings is None:
        from intelligence_os.config.settings import get_settings
        settings = get_settings()

    status: dict[str, Any] = {
        "status": "healthy",
        "app_name": settings.app_name,
        "version": settings.app_version,
        "python_version": sys.version.split()[0],
        "checks": {},
    }

    # 1. Directory Checks
    dir_checks = {}
    for d in [settings.data_dir, settings.logs_dir, settings.output_dir]:
        p = Path(d)
        is_writable = False
        try:
            p.mkdir(parents=True, exist_ok=True)
            test_file = p / ".health_test"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink()
            is_writable = True
        except Exception as e:
            logger.error(f"Directory check failed for {p}: {e}")

        dir_checks[str(d)] = {
            "exists": p.exists(),
            "writable": is_writable,
        }
    status["checks"]["directories"] = dir_checks

    # 2. Database/Storage Accessibility Check
    db_check = {"accessible": False, "path": str(settings.database_path)}
    try:
        settings.database_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(settings.database_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("SELECT 1;")
        res = cursor.fetchone()
        conn.close()
        db_check["accessible"] = res == (1,)
    except Exception as e:
        logger.error(f"Database check failed for {settings.database_path}: {e}")
        db_check["error"] = str(e)
    status["checks"]["database"] = db_check

    # 3. Environment & Key Checks
    x_is_configured = bool(
        (settings.x_consumer_key or settings.x_api_key)
        and (settings.x_consumer_secret or settings.x_api_secret)
        and settings.x_access_token
        and settings.x_access_token_secret
    )
    linkedin_is_configured = bool(
        settings.linkedin_access_token or (settings.linkedin_client_id and settings.linkedin_client_secret)
    )

    keys_check = {
        "openrouter_configured": bool(settings.openrouter_api_key and settings.openrouter_api_key.strip()),
        "github_configured": bool(settings.github_token and settings.github_token.strip()),
        "firecrawl_configured": bool(settings.firecrawl_base_url),
        "linkedin_configured": linkedin_is_configured,
        "x_configured": x_is_configured,
    }
    status["checks"]["credentials"] = keys_check

    # Determine overall status
    if not all(d["writable"] for d in dir_checks.values()) or not db_check["accessible"]:
        status["status"] = "degraded"

    return status
