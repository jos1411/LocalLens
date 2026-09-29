"""Bounded, local-only content extraction for supported file types."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

_MAX_TEXT_BYTES = 1_000_000
_MAX_PDF_BYTES = 25 * 1024 * 1024
_MAX_PDF_PAGES = 100
_MAX_PDF_CHARACTERS = 1_000_000
_TEXT_SUFFIXES = {
    ".txt",
    ".md",
    ".markdown",
    ".py",
    ".pyi",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".sh",
    ".bash",
    ".zsh",
    ".html",
    ".css",
    ".sql",
    ".xml",
    ".csv",
    ".rst",
}


@dataclass(frozen=True)
class ExtractionResult:
    status: str
    text: str | None = None


class _FileTooLargeError(OSError):
    """Raised when a regular file exceeds the extraction byte limit."""


def extract_file(path: Path) -> ExtractionResult:
    """Extract bounded text from one local regular file without following links."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix not in _TEXT_SUFFIXES:
        return ExtractionResult("unsupported")
    try:
        content = _read_bounded(path, _MAX_TEXT_BYTES)
    except OSError:
        return ExtractionResult("unreadable")
    if b"\x00" in content:
        return ExtractionResult("unsupported")
    text = content.decode("utf-8", errors="replace")
    return ExtractionResult("indexed", text) if text.strip() else ExtractionResult("no_text")


def _read_bounded(path: Path, limit: int) -> bytes:
    descriptor = _open_regular_file_without_links(path)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise OSError("not a regular file")
        if info.st_size > limit:
            raise _FileTooLargeError("file exceeds extraction byte limit")
        return os.read(descriptor, limit)
    finally:
        os.close(descriptor)


def _open_regular_file_without_links(path: Path) -> int:
    """Open a file descriptor while refusing symlinks in every path component."""
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise OSError("safe no-follow file access is unavailable")

    absolute_path = path.absolute()
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory = os.open(absolute_path.anchor, directory_flags)
    try:
        for component in absolute_path.parts[1:-1]:
            next_directory = os.open(component, directory_flags, dir_fd=directory)
            os.close(directory)
            directory = next_directory
        return os.open(absolute_path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
    finally:
        os.close(directory)


def _extract_pdf(path: Path) -> ExtractionResult:
    try:
        import fitz
    except ImportError:
        return ExtractionResult("pdf_dependency_missing")

    try:
        content = _read_bounded(path, _MAX_PDF_BYTES)
    except _FileTooLargeError:
        return ExtractionResult("too_large")
    except OSError:
        return ExtractionResult("unreadable")

    try:
        document = fitz.open(stream=content, filetype="pdf")
        try:
            text_parts: list[str] = []
            remaining = _MAX_PDF_CHARACTERS
            for page_number in range(min(document.page_count, _MAX_PDF_PAGES)):
                if remaining <= 0:
                    break
                page_text = document.load_page(page_number).get_text("text")
                text_parts.append(page_text[:remaining])
                remaining -= len(page_text)
        finally:
            document.close()
    except (RuntimeError, ValueError):
        return ExtractionResult("unreadable")

    text = "".join(text_parts)
    return ExtractionResult("indexed", text) if text.strip() else ExtractionResult("no_text")
