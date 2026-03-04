"""
CLI entry point for TeamRun.
"""

import asyncio
import secrets
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, Confirm

from . import __version__
from .config import ConfigManager, ProjectRegistry, RoleConfig, TeamConfig
from .scheduler.scheduler import Scheduler
from .utils.env import load_env
from .utils.logger import get_logger

console = Console()


def get_project_dir(project_name: str | None) -> Path | None:
    """
    Get the working directory for a project.

    :param project_name: Project name (if None, tries to load from .team_run/project.json in current directory)
    :return: Path to project directory or None
    """
    # If no project name provided, try to load from current directory's project.json
    if not project_name:
        config_manager = ConfigManager()  # Uses current directory
        project_name = config_manager.load_project_name()

        if not project_name:
            # No project.json in current directory, use current directory as-is
            return None

        console.print(f"[dim]Using project: {project_name}[/dim]")

    # Look up project in global registry
    registry = ProjectRegistry()
    work_path = registry.get_work_path(project_name)

    if work_path is None:
        console.print(f"[red]Error: Project '{project_name}' not found in registry[/red]")
        console.print("Run [cyan]trun project list[/cyan] to see registered projects.")
        return None

    if not work_path.exists():
        console.print(f"[yellow]Warning: Project directory does not exist: {work_path}[/yellow]")

    return work_path


@click.group()
@click.version_option(version=__version__, prog_name="trun")
def main():
    """TeamRun - Multi-Agent collaboration framework."""
    load_env()


# ============== Init Command ==============

@main.command()
@click.argument("project_name", required=False)
@click.option("--work-path", "-w", type=click.Path(), help="Working directory for the project (default: current directory)")
@click.option("--global", "is_global", is_flag=True, help="Initialize global config only (no project)")
@click.option("--description", "-d", default="", help="Project description")
def init(project_name: str | None, work_path: str | None, is_global: bool, description: str):
    """Initialize TeamRun configuration.

    Examples:
        trun init                         # Initialize in current directory with random name
        trun init my-project              # Initialize in current directory
        trun init my-project -w ~/work    # Initialize in specified directory
        trun init --global                # Initialize global config only
    """
    registry = ProjectRegistry()

    if is_global:
        # Global init only
        config_manager = ConfigManager()
        base_dir = config_manager.ensure_directories(project_level=False)
        config_path = config_manager.global_config_path

        console.print(f"[green]✅ Global TeamRun initialized at: {base_dir}[/green]")
        console.print(f"[dim]Configuration file: {config_path}[/dim]")
        return

    # Generate random project name if not provided
    if not project_name:
        # Generate a random 8-character hex string
        project_name = f"project-{secrets.token_hex(4)}"
        console.print(f"[dim]No project name provided, using: {project_name}[/dim]")

    # Check if project already exists in global registry
    if registry.project_exists(project_name):
        existing = registry.get_project(project_name)
        console.print(f"[yellow]Warning: Project '{project_name}' already exists at: {existing.work_path}[/yellow]")
        if not Confirm.ask("Overwrite existing project registration?"):
            return

    # Determine work path
    if work_path:
        resolved_path = Path(work_path).resolve()
    else:
        resolved_path = Path.cwd()

    # Ensure the work path exists
    resolved_path.mkdir(parents=True, exist_ok=True)

    # Register project in global projects.json
    project_info = registry.register_project(
        name=project_name,
        work_path=resolved_path,
        description=description
    )

    # Initialize project directory structure
    config_manager = ConfigManager(project_dir=resolved_path)
    base_dir = config_manager.init_project()
    config_path = config_manager.project_config_path

    # Save project name to .team_run/project.json
    config_manager.save_project_name(project_name)

    console.print(f"[green]✅ Project '{project_name}' initialized[/green]")
    console.print(f"[dim]Working directory: {resolved_path}[/dim]")
    console.print(f"[dim]Configuration: {config_path}[/dim]")
    console.print(f"[dim]Project file: {config_manager.project_file_path}[/dim]")
    console.print(f"[dim]Registered in: {registry.projects_file_path}[/dim]")
    console.print()
    console.print("Next steps:")
    console.print("  1. Edit [cyan].env[/cyan] to add your API keys")
    console.print("  2. Run [cyan]trun role add[/cyan] to add team roles")
    console.print(f"  3. Run [cyan]trun start \"your task\"[/cyan] to begin")


# ============== Role Commands ==============

@main.group()
def role():
    """Manage team roles."""
    pass


@role.command("add")
@click.argument("role_id", required=False)
@click.option("--project", "-p", help="Project name to operate on")
@click.option("--agent", type=click.Choice(["claude-code", "codex", "mock"]), help="Agent type")
@click.option("--quick", is_flag=True, help="Quick create with minimal info")
def role_add(role_id: str | None, project: str | None, agent: str | None, quick: bool):
    """Add a new role (interactive)."""
    project_dir = get_project_dir(project)
    if project and project_dir is None:
        return

    config_manager = ConfigManager(project_dir=project_dir)
    config = config_manager.load_config()

    if quick and role_id and agent:
        # Quick create
        role = RoleConfig(
            name=role_id,
            description=f"Role: {role_id}",
            agent=agent
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
            choices=["claude-code", "codex", "mock"],
            default="claude-code"
        )

    role = RoleConfig(
        name=name,
        description=description,
        agent=agent
    )

    config.add_role(role_id, role)
    config_manager.save_config(config)

    console.print()
    console.print(f"[green]✅ Role '{role_id}' added successfully[/green]")


@role.command("list")
@click.option("--project", "-p", help="Project name to operate on")
def role_list(project: str | None):
    """List all configured roles."""
    project_dir = get_project_dir(project)
    if project and project_dir is None:
        return

    config_manager = ConfigManager(project_dir=project_dir)
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
@click.option("--project", "-p", help="Project name to operate on")
def role_remove(role_id: str, project: str | None):
    """Remove a role."""
    project_dir = get_project_dir(project)
    if project and project_dir is None:
        return

    config_manager = ConfigManager(project_dir=project_dir)
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
@click.option("--project", "-p", help="Project name to operate on")
def role_edit(role_id: str, project: str | None):
    """Edit a role (opens config file location)."""
    project_dir = get_project_dir(project)
    if project and project_dir is None:
        return

    config_manager = ConfigManager(project_dir=project_dir)
    config = config_manager.load_config()

    if role_id not in config.roles:
        console.print(f"[red]Role '{role_id}' not found[/red]")
        return

    console.print(f"Edit role '{role_id}' in:")
    console.print(f"  [cyan]{config_manager.active_config_path}[/cyan]")


# ============== Task Commands ==============

@main.command()
@click.argument("task_description")
@click.option("--project", "-p", help="Project name to operate on")
@click.option("--auto-approve", is_flag=True, help="Auto-approve human review steps")
@click.option("--config", "config_path", type=click.Path(exists=True), help="Custom config file")
def start(task_description: str, project: str | None, auto_approve: bool, config_path: str | None):
    """Start a new task."""
    project_dir = get_project_dir(project)
    if project and project_dir is None:
        return

    config_manager = ConfigManager(project_dir=project_dir)

    if config_path:
        config = TeamConfig.load(config_path)
    else:
        config = config_manager.load_config()

    if not config.roles:
        console.print("[red]No roles configured.[/red]")
        console.print("Run [cyan]trun role add[/cyan] to add roles first.")
        return

    if project:
        console.print(f"[dim]Project: {project} ({project_dir})[/dim]")
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
@click.option("--project", "-p", help="Project name to operate on")
@click.option("--auto-approve", is_flag=True, help="Auto-approve human review steps")
def resume(project: str | None, auto_approve: bool):
    """Resume an interrupted task."""
    project_dir = get_project_dir(project)
    if project and project_dir is None:
        return

    config_manager = ConfigManager(project_dir=project_dir)
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
@click.option("--project", "-p", help="Project name to operate on")
def status(project: str | None):
    """Show current task status."""
    from .scheduler.state_manager import StateManager

    project_dir = get_project_dir(project)
    if project and project_dir is None:
        return

    config_manager = ConfigManager(project_dir=project_dir)
    state_manager = StateManager(config_manager.team_run_dir)

    state = state_manager.get_current_state()

    if state["status"] == "no_task":
        console.print("[yellow]No active task[/yellow]")
        return

    if project:
        console.print(f"[dim]Project: {project}[/dim]")
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
@click.option("--project", "-p", help="Project name to operate on")
@click.option("--date", help="Show logs for specific date (YYYY-MM-DD)")
@click.option("--tail", "-n", default=50, help="Number of lines to show")
def logs(project: str | None, date: str | None, tail: int):
    """View execution logs."""
    from datetime import datetime

    project_dir = get_project_dir(project)
    if project and project_dir is None:
        return

    config_manager = ConfigManager(project_dir=project_dir)
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


# ============== Project Commands ==============

@main.group()
def project():
    """Manage registered projects."""
    pass


@project.command("list")
def project_list():
    """List all registered projects."""
    registry = ProjectRegistry()
    projects = registry.list_projects()

    if not projects:
        console.print("[yellow]No projects registered.[/yellow]")
        console.print("Run [cyan]trun init <project_name>[/cyan] to register a project.")
        return

    table = Table(title="Registered Projects")
    table.add_column("Name", style="cyan")
    table.add_column("Working Directory")
    table.add_column("Description")
    table.add_column("Created", style="dim")

    for name, info in projects.items():
        # Check if directory exists
        path_exists = Path(info.work_path).exists()
        path_display = info.work_path if path_exists else f"[red]{info.work_path} (missing)[/red]"

        table.add_row(
            name,
            path_display,
            info.description[:40] + "..." if len(info.description) > 40 else info.description,
            info.created_at[:10] if info.created_at else ""
        )

    console.print(table)


@project.command("remove")
@click.argument("project_name")
@click.option("--delete-files", is_flag=True, help="Also delete .team_run directory in project")
def project_remove(project_name: str, delete_files: bool):
    """Remove a project from the registry."""
    registry = ProjectRegistry()

    if not registry.project_exists(project_name):
        console.print(f"[red]Project '{project_name}' not found[/red]")
        return

    project_info = registry.get_project(project_name)

    if Confirm.ask(f"Remove project '{project_name}' from registry?"):
        if delete_files:
            team_run_dir = Path(project_info.work_path) / ".team_run"
            if team_run_dir.exists():
                import shutil
                shutil.rmtree(team_run_dir)
                console.print(f"[dim]Deleted: {team_run_dir}[/dim]")

        registry.remove_project(project_name)
        console.print(f"[green]✅ Project '{project_name}' removed from registry[/green]")


@project.command("show")
@click.argument("project_name")
def project_show(project_name: str):
    """Show details of a project."""
    registry = ProjectRegistry()

    project_info = registry.get_project(project_name)
    if not project_info:
        console.print(f"[red]Project '{project_name}' not found[/red]")
        return

    work_path = Path(project_info.work_path)
    team_run_dir = work_path / ".team_run"

    console.print(f"[bold]Project:[/bold] {project_name}")
    console.print(f"[bold]Working Directory:[/bold] {project_info.work_path}")
    console.print(f"[bold]Description:[/bold] {project_info.description or '(none)'}")
    console.print(f"[bold]Created:[/bold] {project_info.created_at}")
    console.print()

    # Check status
    if not work_path.exists():
        console.print("[red]⚠ Working directory does not exist[/red]")
    elif not team_run_dir.exists():
        console.print("[yellow]⚠ .team_run directory not found[/yellow]")
    else:
        console.print("[green]✓ Project directory OK[/green]")
        # List subdirectories
        subdirs = [d.name for d in team_run_dir.iterdir() if d.is_dir()]
        console.print(f"[dim]Subdirectories: {', '.join(subdirs)}[/dim]")


if __name__ == "__main__":
    main()
