from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from zenclaude import __version__
from zenclaude.config import load_config
from zenclaude.docker_manager import DockerManager
from zenclaude.engine import Engine
from zenclaude.models import ResourceLimits
from zenclaude.paths import ensure_dirs
from zenclaude.skills import discover_skills, expand_skill
from zenclaude.snapshot import restore_snapshot

console = Console()


def _build_engine() -> tuple[Engine, dict]:
    config = load_config()
    docker = DockerManager()
    return Engine(docker, config), config


@click.group()
@click.version_option(__version__, prog_name="zenclaude")
def main() -> None:
    """Run Claude Code autonomously inside Docker containers."""
    pass


@main.command()
@click.argument("workspace", default=".", type=click.Path(exists=True, path_type=Path))
@click.option("--task", "-t", default=None, help="Task description for Claude")
@click.option("--skill", "-s", default=None, help="Skill to invoke (e.g., technomancer)")
@click.option("--no-snapshot", is_flag=True, help="Skip workspace snapshot")
@click.option("--memory", "-m", default=None, help="Memory limit (e.g., 8g)")
@click.option("--cpus", default=None, help="CPU limit (e.g., 4)")
def run(
    workspace: Path,
    task: str | None,
    skill: str | None,
    no_snapshot: bool,
    memory: str | None,
    cpus: str | None,
) -> None:
    """Run a task in a Docker container.

    Use --skill to invoke a Claude Code skill (e.g., --skill technomancer).
    Use --task to pass arguments to the skill or a plain task without a skill.
    At least one of --skill or --task is required.
    """
    if not task and not skill:
        console.print(
            "[bold red]Error:[/bold red] Provide --task, --skill, or both."
        )
        sys.exit(1)

    resolved_workspace = workspace.resolve()
    skill_name = None

    if skill:
        available = discover_skills(resolved_workspace)
        if skill not in available:
            console.print(f"[bold red]Error:[/bold red] Unknown skill: {skill}")
            if available:
                console.print("\nAvailable skills:")
                for name in sorted(available):
                    console.print(f"  [bold]{name}[/bold]  {available[name].description}")
            else:
                console.print("[dim]No skills found.[/dim]")
            sys.exit(1)

        skill_info = available[skill]
        skill_name = skill
        final_task = expand_skill(skill_info, task or "")
        console.print(
            f"[bold]Skill:[/bold] {skill_info.name}\n"
        )
    else:
        final_task = task

    engine, config = _build_engine()
    defaults = config.get("defaults", {})

    limits = ResourceLimits(
        memory=memory or defaults.get("memory", "8g"),
        cpus=cpus or defaults.get("cpus", "4"),
        pids=defaults.get("pids", 256),
    )

    snapshot_enabled = not no_snapshot and defaults.get("snapshot", True)

    try:
        meta = engine.run_task(
            workspace=resolved_workspace,
            task=final_task,
            limits=limits,
            snapshot=snapshot_enabled,
            skill=skill_name,
        )
    except Exception as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        sys.exit(1)

    if meta.exit_code == 0:
        console.print(f"\n[bold green]Completed[/bold green] session {meta.id}")
    else:
        console.print(
            f"\n[bold red]Failed[/bold red] session {meta.id} "
            f"(exit code {meta.exit_code})"
        )
        sys.exit(meta.exit_code or 1)


@main.command()
@click.argument("session_id")
def stop(session_id: str) -> None:
    """Stop a running session."""
    engine, _ = _build_engine()
    try:
        meta = engine.stop_session(session_id)
        console.print(f"[bold yellow]Stopped[/bold yellow] session {meta.id}")
    except (FileNotFoundError, RuntimeError) as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        sys.exit(1)


@main.command()
@click.argument("session_id", required=False)
def status(session_id: str | None) -> None:
    """Show session status. Without ID, lists all sessions."""
    engine, _ = _build_engine()

    if session_id:
        try:
            meta = engine.get_session(session_id)
        except FileNotFoundError as exc:
            console.print(f"[bold red]Error:[/bold red] {exc}")
            sys.exit(1)
        _print_session_detail(meta)
    else:
        sessions = engine.list_sessions()
        if not sessions:
            console.print("[dim]No sessions found.[/dim]")
            return
        _print_session_table(sessions)


@main.command()
@click.argument("session_id")
@click.option("--follow", "-f", is_flag=True, help="Stream logs in real-time")
def logs(session_id: str, follow: bool) -> None:
    """Show logs for a session."""
    engine, _ = _build_engine()
    try:
        for line in engine.stream_session_logs(session_id, follow=follow):
            console.print(line, highlight=False, end="" if line.endswith("\n") else "\n")
    except FileNotFoundError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        sys.exit(1)
    except KeyboardInterrupt:
        pass


@main.command("list")
def list_sessions() -> None:
    """List all sessions."""
    engine, _ = _build_engine()
    sessions = engine.list_sessions()
    if not sessions:
        console.print("[dim]No sessions found.[/dim]")
        return
    _print_session_table(sessions)


@main.command()
@click.argument("session_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def rollback(session_id: str, yes: bool) -> None:
    """Restore workspace from a session's snapshot."""
    engine, _ = _build_engine()
    try:
        meta = engine.get_session(session_id)
    except FileNotFoundError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        sys.exit(1)

    if not meta.snapshot_path:
        console.print(
            f"[bold red]Error:[/bold red] Session {session_id} has no snapshot."
        )
        sys.exit(1)

    target = Path(meta.workspace)
    if not yes:
        console.print(
            f"This will overwrite [bold]{target}[/bold] with the snapshot "
            f"from session [bold]{session_id}[/bold]."
        )
        if not click.confirm("Continue?"):
            console.print("[dim]Cancelled.[/dim]")
            return

    try:
        restore_snapshot(session_id, target)
    except FileNotFoundError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        sys.exit(1)


@main.command()
@click.argument("workspace", default=".", type=click.Path(exists=True, path_type=Path))
def skills(workspace: Path) -> None:
    """List available skills."""
    available = discover_skills(workspace.resolve())
    if not available:
        console.print("[dim]No skills found.[/dim]")
        console.print(
            "[dim]Skills are loaded from ~/.claude/skills/ "
            "and <workspace>/.claude/skills/[/dim]"
        )
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Skill", style="bold")
    table.add_column("Description", max_width=60)
    table.add_column("Arguments")

    for name in sorted(available):
        info = available[name]
        table.add_row(name, info.description, info.argument_hint or "-")

    console.print(table)


@main.command()
@click.option("--port", "-p", default=None, type=int, help="Port (default: 7777)")
@click.option("--host", default=None, help="Host (default: 127.0.0.1)")
def dashboard(port: int | None, host: str | None) -> None:
    """Start the web dashboard."""
    config = load_config()
    dash_config = config.get("dashboard", {})

    actual_port = port or dash_config.get("port", 7777)
    actual_host = host or dash_config.get("host", "127.0.0.1")

    ensure_dirs()

    try:
        import uvicorn
        from zenclaude.web.app import create_app
        app = create_app()
        console.print(
            f"[bold]Dashboard[/bold] running at "
            f"http://{actual_host}:{actual_port}"
        )
        uvicorn.run(app, host=actual_host, port=actual_port, log_level="warning")
    except ImportError as exc:
        console.print(
            f"[bold red]Error:[/bold red] Missing dependency: {exc}\n"
            "Install with: pip install 'zenclaude[web]'"
        )
        sys.exit(1)
    except KeyboardInterrupt:
        pass


def _status_style(status_str: str) -> str:
    styles = {
        "running": "[bold cyan]running[/bold cyan]",
        "completed": "[bold green]completed[/bold green]",
        "failed": "[bold red]failed[/bold red]",
        "stopped": "[bold yellow]stopped[/bold yellow]",
        "starting": "[dim]starting[/dim]",
    }
    return styles.get(status_str, status_str)


def _print_session_table(sessions: list) -> None:
    table = Table(show_header=True, header_style="bold")
    table.add_column("Session ID", style="bold")
    table.add_column("Task", max_width=50)
    table.add_column("Status")
    table.add_column("Duration", justify="right")

    for meta in sessions:
        task_display = meta.task[:47] + "..." if len(meta.task) > 50 else meta.task
        duration = _compute_duration(meta.started_at, meta.finished_at)
        table.add_row(
            meta.id,
            task_display,
            _status_style(meta.status),
            duration,
        )

    console.print(table)


def _print_session_detail(meta) -> None:
    console.print(f"[bold]Session:[/bold]      {meta.id}")
    if meta.skill:
        console.print(f"[bold]Skill:[/bold]        {meta.skill}")
    console.print(f"[bold]Task:[/bold]         {meta.task}")
    console.print(f"[bold]Status:[/bold]       {_status_style(meta.status)}")
    console.print(f"[bold]Workspace:[/bold]    {meta.workspace}")
    if meta.container_id:
        console.print(f"[bold]Container:[/bold]    {meta.container_id[:12]}")
    if meta.image:
        console.print(f"[bold]Image:[/bold]        {meta.image}")
    if meta.started_at:
        console.print(f"[bold]Started:[/bold]      {meta.started_at}")
    if meta.finished_at:
        console.print(f"[bold]Finished:[/bold]     {meta.finished_at}")
    if meta.exit_code is not None:
        console.print(f"[bold]Exit code:[/bold]    {meta.exit_code}")
    if meta.snapshot_path:
        console.print(f"[bold]Snapshot:[/bold]     {meta.snapshot_path}")
    console.print(
        f"[bold]Limits:[/bold]       "
        f"memory={meta.limits.memory}, cpus={meta.limits.cpus}, pids={meta.limits.pids}"
    )


def _compute_duration(started_at: str | None, finished_at: str | None) -> str:
    if not started_at:
        return "-"

    try:
        start = datetime.fromisoformat(started_at)
    except (ValueError, TypeError):
        return "-"

    if finished_at:
        try:
            end = datetime.fromisoformat(finished_at)
        except (ValueError, TypeError):
            return "-"
    else:
        end = datetime.now(timezone.utc)

    delta = end - start
    total_seconds = int(delta.total_seconds())
    if total_seconds < 60:
        return f"{total_seconds}s"
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    if minutes < 60:
        return f"{minutes}m {seconds}s"
    hours = minutes // 60
    minutes = minutes % 60
    return f"{hours}h {minutes}m"
