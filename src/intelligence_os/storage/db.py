"""SQLite connection management and transaction helpers."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator
from intelligence_os.core.exceptions import StorageError
from intelligence_os.core.logger import logger


class Database:
    """Manages SQLite database connections with WAL mode and foreign keys enabled."""

    def __init__(self, db_path: str | Path = "data/intelligence_os.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        """Create a configured SQLite connection with row factories and WAL pragma."""
        try:
            conn = sqlite3.connect(
                self.db_path,
                timeout=30.0,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            # Enable WAL mode for high concurrency & avoid lock contention
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            return conn
        except sqlite3.Error as e:
            logger.error(f"Failed to connect to SQLite at {self.db_path}: {e}")
            raise StorageError(f"Database connection failure: {e}") from e

    @contextmanager
    def session(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for transactional database operations."""
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Transaction failed and rolled back: {e}")
            raise StorageError(f"Database transaction error: {e}") from e
        finally:
            conn.close()
