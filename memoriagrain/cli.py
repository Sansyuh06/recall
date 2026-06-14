"""memoriagrain CLI -- six active verbs, all backed by rich terminal output.

Commands:
    memoriagrain seed --from PATH      Populate memory from existing content
    memoriagrain stats [--json]        Heatmap of what's actually used
    memoriagrain heal [--dry-run]      Actively resolve contradictions
    memoriagrain replay [--since 30d]  Git-log-style timeline of memory growth
    memoriagrain diff [--against ...]  Flag memories invalidated by changes
    memoriagrain forget --pattern STR  Manual eviction

Admin:
    memoriagrain config get/set KEY VALUE
    memoriagrain version
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from memoriagrain.store.sqlite import SQLiteStore

app = typer.Typer(
    name="memoriagrain",
    help="Memory the AI agent can call as a tool.",
    no_args_is_help=True,
    rich_markup_mode="markdown",
)
console = Console()


def _get_store(backend: str = ".memoriagrain/memoriagrain.db") -> SQLiteStore:
    """Get the default SQLite store."""
    return SQLiteStore(backend)


@app.command()
def seed(
    from_path: str = typer.Option(..., "--from", help="Path to seed from (file or directory)"),
    backend: str = typer.Option(".memoriagrain/memoriagrain.db", "--backend", help="Storage backend path"),
    agent_id: str = typer.Option("seed", "--agent-id", help="Agent ID for attribution"),
) -> None:
    """Populate memory from existing content.

    Walks markdown, text, PDF, and OpenAPI files to extract Q->A pairs
    and writes them as atoms. Runs one promotion pass afterward.
    """
    from memoriagrain.seed import from_path as seed_from_path

    store = _get_store(backend)
    path = Path(from_path)

    if not path.exists():
        console.print(f"[red]Path not found:[/red] {path}")
        raise typer.Exit(1)

    with console.status("[bold green]Seeding memory..."):
        count = seed_from_path(path, store, agent_id=agent_id)

    stats = store.stats()
    console.print(
        Panel(
            f"[green]Seeded {count} atoms[/green]\n"
            f"Patterns: {stats.total_patterns}\n"
            f"Principles: {stats.total_principles}",
            title="memoriagrain seed",
            border_style="green",
        )
    )
    store.close()


@app.command()
def stats(
    backend: str = typer.Option(".memoriagrain/memoriagrain.db", "--backend", help="Storage backend path"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show memory statistics -- what's stored, what's used, what's decayed."""
    store = _get_store(backend)
    st = store.stats()

    if as_json:
        data = {
            "total_atoms": st.total_atoms,
            "total_patterns": st.total_patterns,
            "total_principles": st.total_principles,
            "decayed_atoms": st.decayed_atoms,
            "fresh_atoms": st.fresh_atoms,
            "agents": st.agents,
            "oldest_memory": st.oldest_memory,
            "newest_memory": st.newest_memory,
        }
        console.print_json(json.dumps(data))
        store.close()
        return

    table = Table(title="memoriagrain stats", show_header=True, header_style="bold cyan")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Atoms (active)", str(st.fresh_atoms))
    table.add_row("Atoms (decayed)", str(st.decayed_atoms))
    table.add_row("Patterns", str(st.total_patterns))
    table.add_row("Principles", str(st.total_principles))
    table.add_row("Agents", ", ".join(st.agents) if st.agents else "none")
    table.add_row("Oldest", st.oldest_memory or "n/a")
    table.add_row("Newest", st.newest_memory or "n/a")

    console.print(table)

    # Memory grain distribution bar
    total = st.total_atoms + st.total_patterns + st.total_principles
    if total > 0:
        a_pct = st.total_atoms / total * 100
        p_pct = st.total_patterns / total * 100
        pr_pct = st.total_principles / total * 100
        bar_width = 40
        a_bar = int(a_pct / 100 * bar_width)
        p_bar = int(p_pct / 100 * bar_width)
        pr_bar = bar_width - a_bar - p_bar

        bar = (
            f"[cyan]{'=' * a_bar}[/cyan]"
            f"[yellow]{'=' * p_bar}[/yellow]"
            f"[green]{'=' * max(0, pr_bar)}[/green]"
        )
        console.print(f"\nGrain distribution: [{bar}]")
        console.print(
            f"  [cyan]atoms {a_pct:.0f}%[/cyan]  "
            f"[yellow]patterns {p_pct:.0f}%[/yellow]  "
            f"[green]principles {pr_pct:.0f}%[/green]"
        )

    store.close()


@app.command()
def heal(
    backend: str = typer.Option(".memoriagrain/memoriagrain.db", "--backend", help="Storage backend path"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Detect but don't apply resolutions"),
) -> None:
    """Actively resolve contradictions in memory.

    Runs a promotion pass, then scans for contradicting atom clusters
    and resolves them by picking winners based on confidence and recency.
    """
    from memoriagrain.heal import HealWorker

    store = _get_store(backend)
    worker = HealWorker(store)

    with console.status("[bold yellow]Healing memory..."):
        resolutions = worker.run(dry_run=dry_run)

    if not resolutions:
        console.print("[green]No contradictions found.[/green]")
    else:
        mode = "[yellow]DRY RUN[/yellow] " if dry_run else ""
        table = Table(
            title=f"{mode}Heal Results",
            show_header=True,
            header_style="bold yellow",
        )
        table.add_column("Winner", style="green")
        table.add_column("Superseded", style="red")
        table.add_column("Disagreement", justify="right")
        table.add_column("Reason")

        for res in resolutions:
            table.add_row(
                res.winner_id[:8],
                ", ".join(lid[:8] for lid in res.loser_ids),
                f"{res.disagreement:.2f}",
                res.reason[:60],
            )

        console.print(table)
        console.print("\n[dim]Full log: .memoriagrain/heal.log[/dim]")

    store.close()


@app.command()
def replay(
    backend: str = typer.Option(".memoriagrain/memoriagrain.db", "--backend", help="Storage backend path"),
    since: str = typer.Option("30d", "--since", help="Time window (e.g., 7d, 30d, 90d)"),
) -> None:
    """Git-log-style timeline of memory growth.

    Shows atoms, patterns, and principles created over time with
    a visual timeline.
    """
    store = _get_store(backend)

    # Parse the since value — supports '7d', '30d', etc.
    # Falls back to 30 days on unrecognized formats like '1h', '1w'.
    try:
        days = int(since.replace("d", ""))
    except ValueError:
        console.print(f"[yellow]Warning: could not parse --since '{since}', defaulting to 30 days.[/yellow]")
        days = 30
    cutoff = datetime.now(UTC) - timedelta(days=days)

    atoms = list(store.all_atoms(since=cutoff))
    patterns = list(store.all_patterns(since=cutoff))

    if not atoms and not patterns:
        console.print(f"[dim]No memories in the last {days} days.[/dim]")
        store.close()
        return

    tree = Tree(f"[bold]Memory timeline[/bold] (last {days} days)")

    # Group by date
    by_date: dict[str, list[tuple[str, str, str]]] = {}
    for atom in atoms:
        date_str = atom.written_at.strftime("%Y-%m-%d")
        by_date.setdefault(date_str, []).append(("atom", atom.id[:8], atom.prompt[:60]))
    for pattern in patterns:
        date_str = pattern.written_at.strftime("%Y-%m-%d")
        by_date.setdefault(date_str, []).append(("pattern", pattern.id[:8], pattern.text[:60]))

    for date_str in sorted(by_date.keys()):
        date_branch = tree.add(f"[bold cyan]{date_str}[/bold cyan]")
        for grain, mid, text in by_date[date_str]:
            icon = {
                "atom": "[dim]o[/dim]",
                "pattern": "[yellow]*[/yellow]",
                "principle": "[green]#[/green]",
            }.get(grain, "?")
            date_branch.add(f"{icon} {mid} {grain}: {text}")

    console.print(tree)
    store.close()


@app.command(name="diff")
def diff_cmd(
    backend: str = typer.Option(".memoriagrain/memoriagrain.db", "--backend", help="Storage backend path"),
    against: str = typer.Option("last-deploy", "--against", help="What to diff against"),
    save: bool = typer.Option(False, "--save", help="Save current config as deploy snapshot"),
) -> None:
    """Flag memories invalidated by prompt/tool changes.

    Compares stored memories against the last deploy snapshot and
    reports which ones may need review.
    """
    from memoriagrain.diff import diff_against_last_deploy, save_deploy_snapshot

    store = _get_store(backend)

    if save:
        save_deploy_snapshot()
        console.print("[green]Deploy snapshot saved.[/green]")
        store.close()
        return

    results = diff_against_last_deploy(store)

    if not results:
        console.print("[green]No invalidated memories detected.[/green]")
    else:
        table = Table(
            title="Potentially Invalidated Memories",
            show_header=True,
            header_style="bold red",
        )
        table.add_column("ID", style="dim")
        table.add_column("Grain")
        table.add_column("Action", style="yellow")
        table.add_column("Reason")

        for r in results:
            table.add_row(
                r.memory_id[:8],
                r.grain,
                r.suggested_action,
                r.reason[:80],
            )

        console.print(table)

    store.close()


@app.command()
def forget(
    pattern: str | None = typer.Option(None, "--pattern", help="Pattern to match and forget"),
    memory_id: str | None = typer.Option(None, "--id", help="Specific memory ID to forget"),
    backend: str = typer.Option(".memoriagrain/memoriagrain.db", "--backend", help="Storage backend path"),
) -> None:
    """Manually evict memories from the store.

    Use --pattern to match by prompt/answer text, or --id for exact removal.
    """
    if not pattern and not memory_id:
        console.print("[red]Specify --pattern or --id[/red]")
        raise typer.Exit(1)

    store = _get_store(backend)
    deleted = 0

    if memory_id:
        store.delete(memory_id)
        deleted = 1
        console.print(f"[yellow]Deleted memory {memory_id}[/yellow]")
    elif pattern:
        for atom in store.all_atoms():
            if pattern.lower() in atom.prompt.lower() or pattern.lower() in atom.answer.lower():
                store.delete(atom.id)
                deleted += 1

    console.print(f"[green]Forgot {deleted} memories matching the criteria.[/green]")
    store.close()


@app.command()
def config(
    action: str = typer.Argument(..., help="'get' or 'set'"),
    key: str = typer.Argument(..., help="Config key (e.g., promotion.strictness)"),
    value: str | None = typer.Argument(None, help="Value to set"),
    backend: str = typer.Option(".memoriagrain/memoriagrain.db", "--backend", help="Storage backend path"),
) -> None:
    """Get or set memoriagrain configuration values."""
    store = _get_store(backend)

    if action == "get":
        val = store.get_config(key)
        console.print(f"[bold]{key}[/bold] = {val or '[dim]not set[/dim]'}")
    elif action == "set":
        if value is None:
            console.print("[red]Provide a value to set[/red]")
            raise typer.Exit(1)
        store.set_config(key, value)
        console.print(f"[green]Set {key} = {value}[/green]")
    else:
        console.print(f"[red]Unknown action: {action}. Use 'get' or 'set'.[/red]")

    store.close()


@app.command()
def version() -> None:
    """Print the memoriagrain version."""
    from memoriagrain import __version__

    console.print(f"memoriagrain [bold]{__version__}[/bold]")


if __name__ == "__main__":
    app()
