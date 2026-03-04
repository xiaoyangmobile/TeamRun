"""
Tests for scheduler workflow behavior.
"""

import pytest

from trun.adapters.base import AgentResult
from trun.config import RoleConfig, TeamConfig
from trun.scheduler.scheduler import Scheduler
from trun.todo.models import Step, StepStatus, StepType, TodoFile, TodoMeta


class _FakeAdapter:
    def __init__(self, output: str = "ok"):
        self.output = output
        self.last_working_dir: str | None = None

    async def execute(self, context_file: str, working_dir: str | None = None) -> AgentResult:
        self.last_working_dir = working_dir
        return AgentResult(success=True, output=self.output)

    async def stop(self) -> None:
        return None


def _make_scheduler(tmp_path) -> Scheduler:
    config = TeamConfig(
        roles={
            "backend": RoleConfig(
                name="Backend",
                description="Backend role",
                agent="codex",
                prompt="You are backend.",
            )
        }
    )
    return Scheduler(config=config, team_run_dir=tmp_path / ".team_run", auto_approve=True)


@pytest.mark.asyncio
async def test_execute_task_requires_output_marker(tmp_path, monkeypatch):
    """TASK with output should fail when completion marker is missing."""
    scheduler = _make_scheduler(tmp_path)
    monkeypatch.setattr("trun.scheduler.scheduler.AdapterFactory.create", lambda *_: _FakeAdapter(output=""))

    step = Step(
        id="step1",
        type=StepType.TASK,
        role="backend",
        description="write output",
        output="result.md",
    )

    success, _ = await scheduler._execute_task_with_validation(step)
    assert success is False


@pytest.mark.asyncio
async def test_execute_task_accepts_output_with_marker(tmp_path, monkeypatch):
    """TASK with output should pass when output file contains completion marker."""
    scheduler = _make_scheduler(tmp_path)
    monkeypatch.setattr("trun.scheduler.scheduler.AdapterFactory.create", lambda *_: _FakeAdapter())

    output_path = scheduler.state_manager.get_output_path("result.md")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("done\n<!-- TASK_COMPLETED -->\n", encoding="utf-8")

    step = Step(
        id="step1",
        type=StepType.TASK,
        role="backend",
        description="write output",
        output="result.md",
    )

    success, _ = await scheduler._execute_task_with_validation(step)
    assert success is True


@pytest.mark.asyncio
async def test_execute_task_passes_working_dir_to_adapter(tmp_path, monkeypatch):
    """TASK execution should pass outputs working directory to adapter."""
    scheduler = _make_scheduler(tmp_path)
    fake_adapter = _FakeAdapter(output="content\n<!-- TASK_COMPLETED -->\n")
    monkeypatch.setattr("trun.scheduler.scheduler.AdapterFactory.create", lambda *_: fake_adapter)

    step = Step(
        id="step1",
        type=StepType.TASK,
        role="backend",
        description="write output",
        output="result.md",
    )

    success, _ = await scheduler._execute_task_with_validation(step)
    assert success is True
    assert fake_adapter.last_working_dir == str(scheduler.state_manager.outputs_dir)


@pytest.mark.asyncio
async def test_execute_task_materializes_output_from_agent_text(tmp_path, monkeypatch):
    """If agent returns text but no file, scheduler should materialize output file."""
    scheduler = _make_scheduler(tmp_path)
    monkeypatch.setattr(
        "trun.scheduler.scheduler.AdapterFactory.create",
        lambda *_: _FakeAdapter(output="PRD content")
    )

    step = Step(
        id="step1",
        type=StepType.TASK,
        role="backend",
        description="write output",
        output="result.md",
    )

    success, _ = await scheduler._execute_task_with_validation(step)
    assert success is True

    output_path = scheduler.state_manager.get_output_path("result.md")
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "PRD content" in content
    assert "<!-- TASK_COMPLETED -->" in content


@pytest.mark.asyncio
async def test_gate_pass_step_triggers_jump_and_reset(tmp_path, monkeypatch):
    """GATE pass should jump to pass_step and reset it for re-execution."""
    scheduler = _make_scheduler(tmp_path)

    async def _pass_gate(todo, step):
        return True

    monkeypatch.setattr(scheduler, "_execute_gate", _pass_gate)

    gate = Step(
        id="step1",
        type=StepType.GATE,
        description="gate",
        pass_step="step3",
        reject_step="step2",
    )
    target = Step(
        id="step3",
        type=StepType.TASK,
        role="backend",
        description="target",
        status=StepStatus.DONE,
    )

    todo = TodoFile(
        file_path=str(tmp_path / ".team_run" / "todos" / "main.todo.md"),
        meta=TodoMeta(title="t"),
        steps=[gate, target],
    )
    scheduler.state_manager.save_todo(todo)

    should_continue, jump_to = await scheduler._execute_step(todo, gate)

    assert should_continue is True
    assert jump_to == "step3"
    assert gate.status == StepStatus.DONE
    assert target.status == StepStatus.PENDING


@pytest.mark.asyncio
async def test_human_pass_step_triggers_jump_and_reset(tmp_path, monkeypatch):
    """HUMAN pass should jump to pass_step and reset it for re-execution."""
    scheduler = _make_scheduler(tmp_path)

    async def _human_pass(todo, step):
        return "pass"

    monkeypatch.setattr(scheduler, "_execute_human", _human_pass)

    human = Step(
        id="step1",
        type=StepType.HUMAN,
        description="human review",
        pass_step="step3",
        reject_step="step2",
    )
    target = Step(
        id="step3",
        type=StepType.TASK,
        role="backend",
        description="target",
        status=StepStatus.DONE,
    )

    todo = TodoFile(
        file_path=str(tmp_path / ".team_run" / "todos" / "main.todo.md"),
        meta=TodoMeta(title="t"),
        steps=[human, target],
    )
    scheduler.state_manager.save_todo(todo)

    should_continue, jump_to = await scheduler._execute_step(todo, human)

    assert should_continue is True
    assert jump_to == "step3"
    assert human.status == StepStatus.DONE
    assert target.status == StepStatus.PENDING


@pytest.mark.asyncio
async def test_parallel_runs_each_subtask_on_its_branch(tmp_path, monkeypatch):
    """PARALLEL execution should run each subtask in its own branch context."""
    scheduler = _make_scheduler(tmp_path)

    class _FakeGit:
        def __init__(self):
            self.current = "main"

        def current_branch(self):
            return self.current

        def create_branch(self, branch_name, from_branch=None, checkout=True):
            if checkout:
                self.current = branch_name
            return {"success": True}

        def switch_branch(self, branch_name):
            self.current = branch_name
            return {"success": True}

        def merge_branch(self, branch_name):
            return {"success": True}

        def check_conflicts(self):
            return {"has_conflicts": False, "conflicted_files": []}

        def delete_branch(self, branch_name):
            return {"success": True}

    fake_git = _FakeGit()
    monkeypatch.setattr(scheduler, "git", fake_git)

    executed_on: list[str] = []

    async def _fake_execute_task_with_validation(step):
        executed_on.append(fake_git.current)
        return (True, "")

    monkeypatch.setattr(scheduler, "_execute_task_with_validation", _fake_execute_task_with_validation)

    sub1 = Step(id="step1.1", type=StepType.TASK, role="backend", description="a")
    sub2 = Step(id="step1.2", type=StepType.TASK, role="backend", description="b")
    parallel = Step(id="step1", type=StepType.PARALLEL, description="p", subtasks=[sub1, sub2])

    todo = TodoFile(
        file_path=str(tmp_path / ".team_run" / "todos" / "main.todo.md"),
        meta=TodoMeta(title="t"),
        steps=[parallel],
    )

    success = await scheduler._execute_parallel(todo, parallel)

    assert success is True
    assert executed_on == [
        "trun/step1/step1.1",
        "trun/step1/step1.2",
    ]
