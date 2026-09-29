from unittest.mock import patch

from typer.testing import CliRunner

runner = CliRunner()


def invoke(arguments):
    from locallens.cli import app

    return runner.invoke(app, arguments)


def test_index_search_duplicates_largest_and_ignored_database(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    database = root / "index.sqlite3"
    (root / "notes.txt").write_text("green orchard notes", encoding="utf-8")
    (root / "copy-a.bin").write_bytes(b"same content")
    (root / "copy-b.bin").write_bytes(b"same content")
    (root / "large.bin").write_bytes(b"x" * 20)

    indexed = invoke(["index", str(root), "--database", str(database)])

    assert indexed.exit_code == 0
    assert "Indexed" in indexed.stdout
    assert "Scanned" in indexed.stdout

    search = invoke(["search", str(root), "orchard", "--database", str(database)])
    assert search.exit_code == 0
    assert "notes.txt" in search.stdout
    assert "orchard" in search.stdout.lower()

    duplicates = invoke(["duplicates", str(root), "--database", str(database)])
    assert duplicates.exit_code == 0
    assert "copy-a.bin" in duplicates.stdout
    assert "copy-b.bin" in duplicates.stdout

    largest = invoke(["largest", str(root), "--limit", "1", "--database", str(database)])
    assert largest.exit_code == 0
    assert "large.bin" in largest.stdout
    assert "index.sqlite3" not in largest.stdout


def test_index_scans_once_and_reports_index_content_summary(tmp_path):
    from locallens.inventory import Inventory

    root = tmp_path / "root"
    root.mkdir()
    database = tmp_path / "index.sqlite3"
    (root / "notes.txt").write_text("green orchard notes", encoding="utf-8")

    with patch.object(Inventory, "scan", autospec=True, side_effect=Inventory.scan) as scan:
        indexed = invoke(["index", str(root), "--database", str(database)])

    assert indexed.exit_code == 0
    assert scan.call_count == 1
    assert "Scanned 1 files" in indexed.stdout


def test_search_no_results_and_invalid_root_are_useful(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    database = tmp_path / "index.sqlite3"
    (root / "notes.txt").write_text("green orchard notes", encoding="utf-8")
    assert invoke(["index", str(root), "--database", str(database)]).exit_code == 0

    missing = invoke(["search", str(root), "absent", "--database", str(database)])
    assert missing.exit_code == 0
    assert "No results" in missing.stdout

    invalid = invoke(["index", str(root / "missing"), "--database", str(database)])
    assert invalid.exit_code != 0
    assert "existing directory" in invalid.stderr
