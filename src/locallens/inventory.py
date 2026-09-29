"""Safe, local SQLite-backed file inventory."""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import stat
import sys
from dataclasses import dataclass
from pathlib import Path

from .extract import ExtractionResult, extract_file

_CHUNK_SIZE = 1024 * 1024


def _require_safe_fd_traversal() -> None:
    """Reject platforms that cannot anchor a scan to no-follow descriptors."""
    if (
        not sys.platform.startswith("linux")
        or not hasattr(os, "O_DIRECTORY")
        or not hasattr(os, "O_NOFOLLOW")
        or not os.supports_dir_fd
    ):
        raise RuntimeError("safe descriptor-relative traversal is unavailable on this platform")


def _open_root_directory(root_path: Path) -> int:
    """Open every root component without following links and return its directory fd."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(root_path.anchor, flags)
    try:
        for component in root_path.parts[1:]:
            child_descriptor = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child_descriptor
        return descriptor
    except OSError:
        os.close(descriptor)
        raise


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


@dataclass(frozen=True)
class ContentIndexResult:
    attempted: int
    indexed: int
    no_text: int
    failed: int


@dataclass(frozen=True)
class SearchResult:
    path: str
    snippet: str


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
            CREATE VIRTUAL TABLE IF NOT EXISTS file_search USING fts5(
                root_id UNINDEXED,
                path UNINDEXED,
                text
            );
            """
        )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def scan(self, root: str | Path) -> ScanResult:
        _require_safe_fd_traversal()
        root_path = Path(root).absolute()
        try:
            root_descriptor = _open_root_directory(root_path)
        except OSError as error:
            raise ValueError(
                f"root must be an existing directory, not a symlink: {root_path}"
            ) from error

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
        excluded = {
            str(self.database),
            f"{self.database}-journal",
            f"{self.database}-wal",
            f"{self.database}-shm",
        }

        def walk(directory_descriptor: int, directory_path: Path) -> None:
            nonlocal complete, scanned, indexed, unchanged, skipped
            try:
                with os.scandir(os.dup(directory_descriptor)) as entries:
                    for entry in entries:
                        path = directory_path / entry.name
                        key = str(path)
                        try:
                            entry_stat = entry.stat(follow_symlinks=False)
                        except OSError:
                            protected.add(key)
                            skipped += 1
                            complete = False
                            continue
                        if stat.S_ISDIR(entry_stat.st_mode):
                            if entry.name in {".git", ".venv"}:
                                continue
                            try:
                                child_descriptor = os.open(
                                    entry.name,
                                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                    dir_fd=directory_descriptor,
                                )
                            except OSError:
                                skipped += 1
                                complete = False
                                continue
                            try:
                                walk(child_descriptor, path)
                            finally:
                                os.close(child_descriptor)
                            continue
                        if not stat.S_ISREG(entry_stat.st_mode):
                            if not stat.S_ISLNK(entry_stat.st_mode):
                                protected.add(key)
                            skipped += 1
                            continue
                        if key in excluded:
                            skipped += 1
                            continue
                        seen.add(key)
                        scanned += 1
                        if known.get(key) == (entry_stat.st_mtime_ns, entry_stat.st_size):
                            unchanged += 1
                            continue
                        try:
                            descriptor = os.open(
                                entry.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_descriptor
                            )
                            digest, size, mtime_ns = self._hash_file(descriptor)
                        except OSError:
                            protected.add(key)
                            skipped += 1
                            continue
                        self._delete_search(root_id, key)
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
            except OSError:
                complete = False
                skipped += 1

        try:
            walk(root_descriptor, root_path)
        finally:
            os.close(root_descriptor)

        removed = 0
        if complete:
            missing = set(known) - seen - protected
            if missing:
                self._connection.executemany(
                    "DELETE FROM file_search WHERE root_id = ? AND path = ?",
                    ((root_id, key) for key in missing),
                )
                self._connection.executemany(
                    "DELETE FROM files WHERE root_id = ? AND path = ?",
                    ((root_id, key) for key in missing),
                )
                removed = len(missing)
        self._connection.commit()
        return ScanResult(scanned, indexed, unchanged, skipped, removed)

    def index_content(self, root: str | Path) -> ContentIndexResult:
        """Scan a root and index its pending local text without query-time extraction."""
        self.scan(root)
        root_id = self._existing_root_id(root)
        pending = self._connection.execute(
            "SELECT path FROM files WHERE root_id = ? AND content_status = 'pending'",
            (root_id,),
        ).fetchall()
        indexed = no_text = failed = 0
        for row in pending:
            path = row["path"]
            try:
                result = extract_file(Path(path))
            except OSError:
                # A race while opening a file is isolated to this record.
                result = ExtractionResult("unreadable")
            with self._connection:
                self._delete_search(root_id, path)
                self._connection.execute(
                    "UPDATE files SET content_status = ?, indexed_text = ? WHERE root_id = ? AND path = ?",
                    (result.status, result.text, root_id, path),
                )
                if result.status == "indexed" and result.text:
                    self._connection.execute(
                        "INSERT INTO file_search(root_id, path, text) VALUES (?, ?, ?)",
                        (root_id, path, result.text),
                    )
            if result.status == "indexed":
                indexed += 1
            elif result.status == "no_text":
                no_text += 1
            else:
                failed += 1
        return ContentIndexResult(len(pending), indexed, no_text, failed)

    def search(self, root: str | Path, query: str, limit: int = 20) -> list[SearchResult]:
        """Search a root's already-indexed content using literal, safe FTS terms."""
        if limit < 0:
            raise ValueError("limit must not be negative")
        terms = re.findall(r"[^\W_]+", query, flags=re.UNICODE)
        if not terms or limit == 0:
            return []
        match = " AND ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms)
        root_id = self._existing_root_id(root)
        rows = self._connection.execute(
            """
            SELECT path, snippet(file_search, 2, '[', ']', '…', 12) AS snippet
            FROM file_search
            WHERE root_id = ? AND file_search MATCH ?
            ORDER BY bm25(file_search), path
            LIMIT ?
            """,
            (root_id, match, limit),
        ).fetchall()
        return [SearchResult(row["path"], row["snippet"]) for row in rows]

    def _delete_search(self, root_id: int, path: str) -> None:
        self._connection.execute(
            "DELETE FROM file_search WHERE root_id = ? AND path = ?", (root_id, path)
        )

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
    def _hash_file(descriptor: int) -> tuple[str, int, int]:
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
