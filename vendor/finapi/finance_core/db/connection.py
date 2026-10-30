"""SQLite connection helpers shared by the API and the Telegram bot."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def transaction(connection: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Run a block as one SQLite transaction.

    Repositories never commit on their own, so a caller can compose several
    writes and get all-or-nothing behaviour by wrapping them in this context
    manager.
    """

    try:
        yield connection
    except BaseException:
        connection.rollback()
        raise
    else:
        connection.commit()


def connect(
    database_path: str | Path,
    *,
    check_same_thread: bool = True,
) -> sqlite3.Connection:
    """Open a SQLite connection with the project-wide pragmas applied.

    ``check_same_thread`` stays enabled by default. Only the Telegram bot, which
    shares one connection across handler executions, passes ``False``.
    """

    path = str(database_path)
    connection = sqlite3.connect(path, check_same_thread=check_same_thread, timeout=5.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection