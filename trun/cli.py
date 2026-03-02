"""
CLI entry point for TeamRun.
"""

import asyncio
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, Confirm

from . import __version__
from .config import ConfigManager, RoleConfig, TeamConfig
from .scheduler.scheduler import Scheduler
from .utils.env import load_env
from .utils.logger import get_logger

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="trun")
def main():
    """TeamRun - Multi-Agent collaboration framework."""
    load_env()


# ============== Init Command ==============

@main.command()
@click.option("--global", "is_global", is_flag=True, help="Initialize global config instead of project")
def init(is_global: bool):
    """Initialize TeamRun configuration."""
    config_manager = ConfigManager()

    if is_global:
        base_dir = config_manager.ensure_directories(project_level=False)
        config_path = config_manager.global_config_path
    else:
        base_dir = config_manager.init_project()
        config_path = config_manager.project_config_path

    console.print(f"[green]✅ TeamRun initialized at: {base_dir}[/green]")
    console.print(f"[dim]Configuration file: {config_path}[/dim]")
    console.print()
    console.print("Next steps:")
    console.print("  1. Edit [cyan].env[/cyan] to add your API keys")
    console.print("  2. Run [cyan]trun role add[/cyan] to add team roles")
    console.print("  3. Run [cyan]trun start \"your task\"[/cyan] to begin")


# ============== Role Commands ==============

@main.group()
def role():
    """Manage team roles."""
    pass


@role.command("add")
@click.argument("role_id", required=False)
@click.option("--agent", type=click.Choice(["claude-code", "codex"]), help="Agent type")
@click.option("--quick", is_flag=True, help="Quick create with minimal info")
def role_add(role_id: str | None, agent: str | None, quick: bool):
    """Add a new role (interactive)."""
    config_manager = ConfigManager()
    config = config_manager.load_config()

    if quick and role_id and agent:
        # Quick create
        role = RoleConfig(
            name=role_id,
            description=f"Role: {role_id}",
            agent=agent,
            prompt=None
        )
        config.add_role(role_id, role)
        config_manager.save_config(config)
        console.print(f"[green]✅ Role '{role_id}' created[/green]")
        console.print(f"[dim]Edit {config_manager.active_config_path} to add details[/dim]")
        return

    # Interactive mode
    console.print("[bold]Add New Role[/bold]")
    console.print()

    if not role_id:
        role_id = Prompt.ask("Role ID (e.g., pm, architect, backend)")

    if role_id in config.roles:
        if not Confirm.ask(f"Role '{role_id}' already exists. Overwrite?"):
            return

    name = Prompt.ask("Display name", default=role_id)
    description = Prompt.ask("Description")

    if not agent:
        agent = Prompt.ask(
            "Agent type",
            choices=["claude-code", "codex"],
            default="claude-code"
        )

    prompt_file = Prompt.ask(
        "Prompt file path (optional, leave empty to skip)",
        default=""
    )

    prompt = None
    if not prompt_file:
        if Confirm.ask("Enter prompt inline?", default=False):
            console.print("Enter prompt (Ctrl+D or empty line to finish):")
            lines = []
            try:
                while True:
                    line = input()
                    if not line:
                        break
                    lines.append(line)
            except EOFError:
                pass
            prompt = "\n".join(lines)

    role = RoleConfig(
        name=name,
        description=description,
        agent=agent,
        prompt=prompt or None,
        prompt_file=prompt_file or None
    )

    config.add_role(role_id, role)
    config_manager.save_config(config)

    console.print()
    console.print(f"[green]✅ Role '{role_id}' added successfully[/green]")


@role.command("list")
def role_list():
    """List all configured roles."""
    config_manager = ConfigManager()
    config = config_manager.load_config()

    if not config.roles:
        console.print("[yellow]No roles configured.[/yellow]")
        console.print("Run [cyan]trun role add[/cyan] to add a role.")
        return

    table = Table(title="Team Roles")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Agent", style="green")
    table.add_column("Description")

    for role_id, role in config.roles.items():
        table.add_row(
            role_id,
            role.name,
            role.agent,
            role.description[:50] + "..." if len(role.description) > 50 else role.description
        )

    console.print(table)


@role.command("remove")
@click.argument("role_id")
def role_remove(role_id: str):
    """Remove a role."""
    config_manager = ConfigManager()
    config = config_manager.load_config()

    if role_id not in config.roles:
        console.print(f"[red]Role '{role_id}' not found[/red]")
        return

    if Confirm.ask(f"Remove role '{role_id}'?"):
        config.remove_role(role_id)
        config_manager.save_config(config)
        console.print(f"[green]✅ Role '{role_id}' removed[/green]")


@role.command("edit")
@click.argument("role_id")
def role_edit(role_id: str):
    """Edit a role (opens config file location)."""
    config_manager = ConfigManager()
    config = config_manager.load_config()

    if role_id not in config.roles:
        console.print(f"[red]Role '{role_id}' not found[/red]")
        return

    console.print(f"Edit role '{role_id}' in:")
    console.print(f"  [cyan]{config_manager.active_config_path}[/cyan]")


# ============== Task Commands ==============

@main.command()
@click.argument("task_description")
@click.option("--auto-approve", is_flag=True, help="Auto-approve human review steps")
@click.option("--config", "config_path", type=click.Path(exists=True), help="Custom config file")
def start(task_description: str, auto_approve: bool, config_path: str | None):
    """Start a new task."""
    config_manager = ConfigManager()

    if config_path:
        config = TeamConfig.load(config_path)
    else:
        config = config_manager.load_config()

    if not config.roles:
        console.print("[red]No roles configured.[/red]")
        console.print("Run [cyan]trun role add[/cyan] to add roles first.")
        return

    console.print(f"[bold]Starting task:[/bold] {task_description}")
    console.print()

    scheduler = Scheduler(
        config=config,
        team_run_dir=config_manager.team_run_dir,
        auto_approve=auto_approve
    )

    try:
        asyncio.run(scheduler.start(task_description))
        console.print()
        console.print("[green]✅ Task completed[/green]")
    except KeyboardInterrupt:
        console.print()
        console.print("[yellow]Task interrupted[/yellow]")
    except Exception as e:
        console.print()
        console.print(f"[red]Task failed: {str(e)}[/red]")
        sys.exit(1)


@main.command()
@click.option("--auto-approve", is_flag=True, help="Auto-approve human review steps")
def resume(auto_approve: bool):
    """Resume an interrupted task."""
    config_manager = ConfigManager()
    config = config_manager.load_config()

    scheduler = Scheduler(
        config=config,
        team_run_dir=config_manager.team_run_dir,
        auto_approve=auto_approve
    )

    try:
        asyncio.run(scheduler.resume())
        console.print()
        console.print("[green]✅ Task completed[/green]")
    except ValueError as e:
        console.print(f"[red]{str(e)}[/red]")
    except KeyboardInterrupt:
        console.print()
        console.print("[yellow]Task interrupted[/yellow]")
    except Exception as e:
        console.print()
        console.print(f"[red]Task failed: {str(e)}[/red]")
        sys.exit(1)


@main.command()
def status():
    """Show current task status."""
    from .scheduler.state_manager import StateManager

    config_manager = ConfigManager()
    state_manager = StateManager(config_manager.team_run_dir)

    state = state_manager.get_current_state()

    if state["status"] == "no_task":
        console.print("[yellow]No active task[/yellow]")
        return

    console.print(f"[bold]Task:[/bold] {state['title']}")
    console.print()

    status_color = {
        "running": "blue",
        "completed": "green",
        "blocked": "yellow",
    }.get(state["status"], "white")

    console.print(f"Status: [{status_color}]{state['status']}[/{status_color}]")
    console.print(f"Progress: {state['completed_steps']}/{state['total_steps']} steps completed")

    if state["failed_steps"] > 0:
        console.print(f"[red]Failed steps: {state['failed_steps']}[/red]")

    if state["next_step"]:
        console.print(f"Next step: [cyan]{state['next_step']}[/cyan]")


# ============== Logs Command ==============

@main.command()
@click.option("--date", help="Show logs for specific date (YYYY-MM-DD)")
@click.option("--tail", "-n", default=50, help="Number of lines to show")
def logs(date: str | None, tail: int):
    """View execution logs."""
    from datetime import datetime

    config_manager = ConfigManager()
    logs_dir = config_manager.team_run_dir / "logs"

    if date:
        log_file = logs_dir / f"{date.replace('-', '_')}.log"
    else:
        # Today's log
        today = datetime.now().strftime("%Y_%m_%d")
        log_file = logs_dir / f"{today}.log"

    if not log_file.exists():
        console.print(f"[yellow]No logs found: {log_file}[/yellow]")
        return

    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Show last N lines
    for line in lines[-tail:]:
        console.print(line.rstrip())


if __name__ == "__main__":
    main()
