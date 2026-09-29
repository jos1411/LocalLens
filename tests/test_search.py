from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from locallens.extract import extract_file as real_extract_file
from locallens.inventory import Inventory


class TestContentSearch:
    def setup_method(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.base = Path(self.tempdir.name)
        self.root = self.base / "root"
        self.root.mkdir()
        self.inventory = Inventory(self.base / "index.sqlite3")

    def teardown_method(self) -> None:
        self.inventory.close()
        self.tempdir.cleanup()

    def write(self, name: str, content: bytes) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def status(self, path: Path) -> str:
        return self.inventory._connection.execute(
            "SELECT content_status FROM files WHERE path = ?", (str(path.absolute()),)
        ).fetchone()[0]

    def test_text_search_updates_and_deletes_records(self) -> None:
        path = self.write("notes.md", b"Original green orchard notes")

        self.inventory.index_content(self.root)
        self.write("notes.md", b"Updated blue ocean notes")
        self.inventory.index_content(self.root)

        assert [result.path for result in self.inventory.search(self.root, "orchard")] == []
        updated = self.inventory.search(self.root, "blue ocean")
        assert [result.path for result in updated] == [str(path.absolute())]
        assert "blue" in updated[0].snippet.lower()

        path.unlink()
        self.inventory.index_content(self.root)
        assert self.inventory.search(self.root, "notes") == []

    def test_search_isolated_to_each_root_and_punctuation_is_literal(self) -> None:
        other = self.base / "other"
        other.mkdir()
        first = self.write("first.py", b'hello, "world" from local code')
        second = other / "second.py"
        second.write_bytes(b'hello, "world" elsewhere')

        self.inventory.index_content(self.root)
        self.inventory.index_content(other)

        results = self.inventory.search(self.root, 'hello, "world"!')
        assert [result.path for result in results] == [str(first.absolute())]
        assert str(second.absolute()) not in {result.path for result in results}

    def test_binary_and_scanned_pdf_are_not_indexed_as_text(self) -> None:
        binary = self.write("blob.bin", b"visible\x00but binary")
        pdf = self.root / "scan.pdf"
        document = fitz.open()
        page = document.new_page()
        page.draw_rect(fitz.Rect(10, 10, 30, 30), fill=(0, 0, 0))
        document.save(pdf)
        document.close()

        self.inventory.index_content(self.root)

        assert self.inventory.search(self.root, "visible") == []
        assert self.status(binary) == "unsupported"
        assert self.status(pdf) == "no_text"

    def test_pdf_text_is_searchable(self) -> None:
        pdf = self.root / "report.pdf"
        document = fitz.open()
        document.new_page().insert_text((72, 72), "Portable document needle")
        document.save(pdf)
        document.close()

        self.inventory.index_content(self.root)

        assert [result.path for result in self.inventory.search(self.root, "document needle")] == [
            str(pdf.absolute())
        ]

    def test_pdf_symlink_to_outside_is_not_extracted(self) -> None:
        outside = self.base / "private.pdf"
        document = fitz.open()
        document.new_page().insert_text((72, 72), "outside secret")
        document.save(outside)
        document.close()
        link = self.root / "report.pdf"
        try:
            link.symlink_to(outside)
        except OSError as error:
            self.skipTest(f"symlinks unavailable: {error}")

        assert real_extract_file(link).status == "unreadable"

    def test_oversized_pdf_is_skipped_without_parsing(self) -> None:
        pdf = self.root / "large.pdf"
        with pdf.open("wb") as output:
            output.truncate(25 * 1024 * 1024 + 1)

        with patch.object(fitz, "open", side_effect=AssertionError("must not parse")) as open_pdf:
            assert real_extract_file(pdf).status == "too_large"

        open_pdf.assert_not_called()

    def test_failed_extraction_removes_stale_text_without_stopping_other_files(self) -> None:
        stale = self.write("stale.txt", b"old searchable content")
        self.inventory.index_content(self.root)
        self.write("stale.txt", b"changed content")
        good = self.write("good.txt", b"reliable content")

        def fail_only_stale(path: Path):
            if path.name == "stale.txt":
                raise OSError("read failed")
            return real_extract_file(path)

        with patch("locallens.inventory.extract_file", side_effect=fail_only_stale):
            self.inventory.index_content(self.root)

        assert self.inventory.search(self.root, "old searchable") == []
        assert self.status(stale) == "unreadable"
        assert [result.path for result in self.inventory.search(self.root, "reliable")] == [
            str(good.absolute())
        ]
