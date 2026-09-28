from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from locallens.inventory import Inventory


class InventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name) / "root"
        self.root.mkdir()
        self.inventory = Inventory(self.root / "index.sqlite3")

    def tearDown(self) -> None:
        self.inventory.close()
        self.tempdir.cleanup()

    def write(self, relative_path: str, content: bytes) -> Path:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_repeat_changed_and_deleted_files(self) -> None:
        file_path = self.write("report.txt", b"first")

        first = self.inventory.scan(self.root)
        second = self.inventory.scan(self.root)
        original_mtime = file_path.stat().st_mtime_ns
        file_path.write_bytes(b"other")
        os.utime(file_path, ns=(original_mtime + 1, original_mtime + 1))
        changed = self.inventory.scan(self.root)
        file_path.unlink()
        deleted = self.inventory.scan(self.root)

        self.assertEqual((first.indexed, first.unchanged), (1, 0))
        self.assertEqual((second.indexed, second.unchanged), (0, 1))
        self.assertEqual((changed.indexed, changed.unchanged), (1, 0))
        self.assertEqual(deleted.removed, 1)
        self.assertEqual(self.inventory.largest(self.root), [])

    def test_duplicate_groups_require_same_size_and_full_content_hash(self) -> None:
        self.write("one.bin", b"same")
        self.write("two.bin", b"same")
        self.write("different.bin", b"else")
        self.inventory.scan(self.root)

        groups = self.inventory.duplicates(self.root)

        self.assertEqual(len(groups), 1)
        self.assertEqual({entry.path for entry in groups[0]}, {
            str((self.root / "one.bin").absolute()),
            str((self.root / "two.bin").absolute()),
        })

    def test_nested_paths_and_largest_files_use_absolute_keys(self) -> None:
        small = self.write("nested/small.txt", b"a")
        large = self.write("nested/deeper/large.txt", b"abcdef")
        self.inventory.scan(self.root)

        largest = self.inventory.largest(self.root, limit=1)

        self.assertEqual(largest[0].path, str(large.absolute()))
        self.assertEqual(largest[0].size, 6)
        self.assertNotEqual(largest[0].path, str(small))

    def test_skips_outside_root_symlinks_and_database_files(self) -> None:
        outside = Path(self.tempdir.name) / "outside.txt"
        outside.write_bytes(b"private")
        self.write("inside.txt", b"public")
        link = self.root / "outside-link.txt"
        try:
            link.symlink_to(outside)
        except OSError as error:
            self.skipTest(f"symlinks unavailable: {error}")

        self.inventory.scan(self.root)
        paths = {entry.path for entry in self.inventory.largest(self.root)}

        self.assertEqual(paths, {str((self.root / "inside.txt").absolute())})
        self.assertFalse(any("index.sqlite3" in path for path in paths))

    def test_complete_scan_removes_regular_file_replaced_by_outside_symlink(self) -> None:
        path = self.write("replaced.txt", b"indexed")
        outside = Path(self.tempdir.name) / "outside.txt"
        outside.write_bytes(b"private")
        self.inventory.scan(self.root)
        path.unlink()
        try:
            path.symlink_to(outside)
        except OSError as error:
            self.skipTest(f"symlinks unavailable: {error}")

        result = self.inventory.scan(self.root)

        self.assertEqual(result.removed, 1)
        self.assertEqual(self.inventory.largest(self.root), [])

    def test_hash_file_rejects_metadata_changed_during_hashing(self) -> None:
        path = self.write("changing.txt", b"content")
        before = SimpleNamespace(
            st_mode=path.stat().st_mode,
            st_size=7,
            st_mtime_ns=100,
        )
        after = SimpleNamespace(
            st_mode=path.stat().st_mode,
            st_size=7,
            st_mtime_ns=101,
        )

        with (
            patch("locallens.inventory.os.fstat", side_effect=[before, after]),
            self.assertRaisesRegex(OSError, "changed during hashing"),
        ):
            self.inventory._hash_file(path)

    def test_roots_are_isolated_in_a_shared_database(self) -> None:
        other_root = Path(self.tempdir.name) / "other"
        other_root.mkdir()
        (other_root / "other.txt").write_bytes(b"x" * 10)
        self.write("root.txt", b"x")

        self.inventory.scan(self.root)
        self.inventory.scan(other_root)

        self.assertEqual([entry.path for entry in self.inventory.largest(self.root)],
                         [str((self.root / "root.txt").absolute())])
        self.assertEqual([entry.path for entry in self.inventory.largest(other_root)],
                         [str((other_root / "other.txt").absolute())])

    def test_invalid_root_has_a_clear_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "existing directory"):
            self.inventory.scan(self.root / "missing")


if __name__ == "__main__":
    unittest.main()
