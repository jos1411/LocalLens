"""Safe, local SQLite-backed file inventory."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import stat
from dataclasses import dataclass
from pathlib import Path

_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class FileRecord:
    path: str
    size: int
    content_hash: str


@dataclass(frozen=True)
class ScanResult:
    scanned: int
    indexed: int
    unchanged: int
    skipped: int
    removed: int


class Inventory:
    """Index regular files below explicitly selected roots in one SQLite database."""

    def __init__(self, database: str | Path) -> None:
        self.database = Path(database).absolute()
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.database)
        self._connection.row_factory = sqlite3.Row
        self._connection.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE IF NOT EXISTS roots (
                id INTEGER PRIMARY KEY,
                path TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS files (
                root_id INTEGER NOT NULL REFERENCES roots(id) ON DELETE CASCADE,
                path TEXT NOT NULL,
                mtime_ns INTEGER NOT NULL,
                size INTEGER NOT NULL,
                content_hash TEXT NOT NULL,
                content_status TEXT NOT NULL DEFAULT 'pending',
                indexed_text TEXT,
                PRIMARY KEY (root_id, path)
            );
            CREATE INDEX IF NOT EXISTS files_root_size ON files(root_id, size DESC);
            CREATE INDEX IF NOT EXISTS files_root_hash ON files(root_id, size, content_hash);
            """
        )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def scan(self, root: str | Path) -> ScanResult:
        root_path = Path(root).absolute()
        if not root_path.is_dir() or root_path.is_symlink():
            raise ValueError(f"root must be an existing directory, not a symlink: {root_path}")

        root_key = str(root_path)
        root_id = self._root_id(root_key)
        known = {
            row["path"]: (row["mtime_ns"], row["size"])
            for row in self._connection.execute(
                "SELECT path, mtime_ns, size FROM files WHERE root_id = ?", (root_id,)
            )
        }
        seen: set[str] = set()
        protected: set[str] = set()
        scanned = indexed = unchanged = skipped = 0
        complete = True

        def onerror(_: OSError) -> None:
            nonlocal complete
            complete = False

        excluded = {
            str(self.database),
            f"{self.database}-journal",
            f"{self.database}-wal",
            f"{self.database}-shm",
        }
        for directory, directories, filenames in os.walk(root_path, topdown=True, followlinks=False, onerror=onerror):
            directory_path = Path(directory)
            directories[:] = [
                name for name in directories
                if name not in {".git", ".venv"} and not (directory_path / name).is_symlink()
            ]
            for filename in filenames:
                path = directory_path / filename
                key = str(path.absolute())
                if key in excluded:
                    skipped += 1
                    continue
                try:
                    file_stat = path.lstat()
                except OSError:
                    protected.add(key)
                    skipped += 1
                    continue
                if not stat.S_ISREG(file_stat.st_mode):
                    if not stat.S_ISLNK(file_stat.st_mode):
                        protected.add(key)
                    skipped += 1
                    continue
                seen.add(key)
                scanned += 1
                if known.get(key) == (file_stat.st_mtime_ns, file_stat.st_size):
                    unchanged += 1
                    continue
                try:
                    digest, size, mtime_ns = self._hash_file(path)
                except OSError:
                    protected.add(key)
                    skipped += 1
                    continue
                self._connection.execute(
                    """
                    INSERT INTO files(root_id, path, mtime_ns, size, content_hash)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(root_id, path) DO UPDATE SET
                        mtime_ns = excluded.mtime_ns,
                        size = excluded.size,
                        content_hash = excluded.content_hash,
                        content_status = 'pending',
                        indexed_text = NULL
                    """,
                    (root_id, key, mtime_ns, size, digest),
                )
                indexed += 1

        removed = 0
        if complete:
            missing = set(known) - seen - protected
            if missing:
                self._connection.executemany(
                    "DELETE FROM files WHERE root_id = ? AND path = ?",
                    ((root_id, key) for key in missing),
                )
                removed = len(missing)
        self._connection.commit()
        return ScanResult(scanned, indexed, unchanged, skipped, removed)

    def duplicates(self, root: str | Path) -> list[tuple[FileRecord, ...]]:
        root_id = self._existing_root_id(root)
        rows = self._connection.execute(
            """
            SELECT path, size, content_hash FROM files
            WHERE root_id = ?
            ORDER BY size, content_hash, path
            """,
            (root_id,),
        ).fetchall()
        groups: list[tuple[FileRecord, ...]] = []
        current: list[FileRecord] = []
        current_key: tuple[int, str] | None = None
        for row in rows:
            key = (row["size"], row["content_hash"])
            record = FileRecord(row["path"], row["size"], row["content_hash"])
            if current_key is not None and key != current_key:
                if len(current) > 1:
                    groups.append(tuple(current))
                current = []
            current_key = key
            current.append(record)
        if len(current) > 1:
            groups.append(tuple(current))
        return groups

    def largest(self, root: str | Path, limit: int = 20) -> list[FileRecord]:
        if limit < 0:
            raise ValueError("limit must not be negative")
        root_id = self._existing_root_id(root)
        rows = self._connection.execute(
            """
            SELECT path, size, content_hash FROM files
            WHERE root_id = ?
            ORDER BY size DESC, path ASC
            LIMIT ?
            """,
            (root_id, limit),
        ).fetchall()
        return [FileRecord(row["path"], row["size"], row["content_hash"]) for row in rows]

    def _root_id(self, root: str) -> int:
        self._connection.execute("INSERT OR IGNORE INTO roots(path) VALUES (?)", (root,))
        return self._connection.execute("SELECT id FROM roots WHERE path = ?", (root,)).fetchone()[0]

    def _existing_root_id(self, root: str | Path) -> int:
        root_key = str(Path(root).absolute())
        row = self._connection.execute("SELECT id FROM roots WHERE path = ?", (root_key,)).fetchone()
        if row is None:
            return -1
        return row[0]

    @staticmethod
    def _hash_file(path: Path) -> tuple[str, int, int]:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode):
                raise OSError("not a regular file")
            digest = hashlib.blake2b()
            while chunk := os.read(descriptor, _CHUNK_SIZE):
                digest.update(chunk)
            after = os.fstat(descriptor)
            if (
                not stat.S_ISREG(after.st_mode)
                or (after.st_size, after.st_mtime_ns) != (info.st_size, info.st_mtime_ns)
            ):
                raise OSError("file changed during hashing")
            return digest.hexdigest(), info.st_size, info.st_mtime_ns
        finally:
            os.close(descriptor)
