# LocalLens

LocalLens indexes a folder on your Linux machine so you can search text, find exact duplicates, and list large files. It runs locally: no API, cloud service, OCR, semantic model, daemon, or Docker is involved.

## Quick start

Python 3.12 or newer is required. Create a virtual environment and install the CLI with PDF support:

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[pdf,dev]'
.venv/bin/locallens index /path/to/folder
.venv/bin/locallens search /path/to/folder "quarterly notes"
.venv/bin/locallens duplicates /path/to/folder
.venv/bin/locallens largest /path/to/folder --limit 10
```

Use `--database PATH` to choose the SQLite index location. By default it is `$XDG_DATA_HOME/locallens/index.sqlite3`, or `~/.local/share/locallens/index.sqlite3` when `XDG_DATA_HOME` is unset.

## What is indexed

LocalLens reads supported text, Markdown, source, configuration, data, and markup files, plus text-bearing PDFs when the optional `pdf` extra is installed. It does not perform OCR, so scanned PDFs have no searchable text. Text files are capped at 1 MB. PDFs are capped at 25 MiB, 100 pages, and 1,000,000 extracted characters.

The indexer safely traverses only the selected root on Linux and excludes symbolic links. Windows is currently unsupported. It uses size and modification time as an incremental heuristic, so a file changed while retaining both its size and mtime can be missed until its metadata changes. Duplicate groups are exact full-content BLAKE2b hashes.

## Privacy and licensing

Your files stay local. LocalLens only writes its SQLite database and never sends file contents to an external service. Keep the database outside roots you do not want indexed; a database inside the selected root is excluded automatically.

PDF support uses PyMuPDF. PyMuPDF is AGPL-licensed unless you obtain a commercial license; verify that this licensing fits your use before distributing LocalLens with PDF support.

## Checks

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests
```
