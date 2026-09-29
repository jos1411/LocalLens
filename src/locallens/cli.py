"""Command-line interface for LocalLens's local inventory."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated

import typer

from .inventory import Inventory

app = typer.Typer(help="Search and inspect a local-only file inventory.", no_args_is_help=True)


def _default_database() -> Path:
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return data_home / "locallens" / "index.sqlite3"


def _validate_root(root: Path) -> Path:
    if not root.is_dir() or root.is_symlink():
        typer.echo("Error: root must be an existing directory, not a symlink", err=True)
        raise typer.Exit(code=1)
    return root.absolute()


@contextmanager
def _inventory(database: Path | None) -> Iterator[Inventory]:
    inventory = Inventory(database or _default_database())
    try:
        yield inventory
    finally:
        inventory.close()


def _run(action: Callable[[], None]) -> None:
    try:
        action()
    except (RuntimeError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=1) from error


@app.command()
def index(
    root: Annotated[Path, typer.Argument(..., help="Directory to index.")],
    database: Annotated[Path | None, typer.Option("--database", help="SQLite database path.")] = None,
) -> None:
    """Index supported content below ROOT."""
    root = _validate_root(root)

    def action() -> None:
        with _inventory(database) as inventory:
            result = inventory.index_content(root)
        typer.echo(
            f"Scanned {result.scan.scanned} files; Indexed {result.indexed} files; "
            f"unchanged {result.scan.unchanged}, skipped {result.scan.skipped}, "
            f"removed {result.scan.removed}; "
            f"attempted {result.attempted}, no text {result.no_text}, failed {result.failed}."
        )

    _run(action)


@app.command()
def search(
    root: Annotated[Path, typer.Argument(..., help="Indexed directory to search.")],
    query: Annotated[str, typer.Argument(..., help="Words to search for.")],
    database: Annotated[Path | None, typer.Option("--database", help="SQLite database path.")] = None,
    limit: Annotated[int, typer.Option("--limit", min=0, help="Maximum results.")] = 20,
) -> None:
    """Search already-indexed content below ROOT."""
    root = _validate_root(root)

    def action() -> None:
        with _inventory(database) as inventory:
            results = inventory.search(root, query, limit)
        if not results:
            typer.echo("No results.")
            return
        for result in results:
            typer.echo(f"{result.path}\n  {result.snippet}")

    _run(action)


@app.command()
def duplicates(
    root: Annotated[Path, typer.Argument(..., help="Indexed directory to inspect.")],
    database: Annotated[Path | None, typer.Option("--database", help="SQLite database path.")] = None,
) -> None:
    """Show exact duplicate groups below ROOT."""
    root = _validate_root(root)

    def action() -> None:
        with _inventory(database) as inventory:
            groups = inventory.duplicates(root)
        if not groups:
            typer.echo("No duplicate groups.")
            return
        for group in groups:
            typer.echo(f"{group[0].size} bytes:")
            for record in group:
                typer.echo(f"  {record.path}")

    _run(action)


@app.command()
def largest(
    root: Annotated[Path, typer.Argument(..., help="Indexed directory to inspect.")],
    database: Annotated[Path | None, typer.Option("--database", help="SQLite database path.")] = None,
    limit: Annotated[int, typer.Option("--limit", min=0, help="Maximum files.")] = 20,
) -> None:
    """Show the largest indexed files below ROOT."""
    root = _validate_root(root)

    def action() -> None:
        with _inventory(database) as inventory:
            records = inventory.largest(root, limit)
        if not records:
            typer.echo("No indexed files.")
            return
        for record in records:
            typer.echo(f"{record.size}\t{record.path}")

    _run(action)
