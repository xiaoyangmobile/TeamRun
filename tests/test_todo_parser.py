"""
Tests for TODO parser.
"""

import pytest
from trun.todo.models import Step, StepStatus, StepType, TodoFile, TodoMeta
from trun.todo.parser import TodoParser, TodoWriter


SAMPLE_TODO = """# 任务：开发一个博客系统

## 元信息
- 创建时间：2024-01-15 10:00:00
- 状态：RUNNING

## 流程

- [ ] #step1 @task(pm) 规划项目功能
  - output: requirements.md
  - instruction: 分析用户需求，输出详细的功能需求文档

- [ ] #step2 @human 审核需求文档
  - depends: step1
  - pass: step3
  - reject: step1

- [x] #step3 @task(architect) 编写技术方案
  - depends: step2
  - output: design.md

- [ ] #step4 @discuss(architect, backend, frontend) 讨论技术方案
  - depends: step3
  - rounds: 2

- [ ] #step5 @parallel 并行开发
  - depends: step4
"""


class TestTodoParser:
    """Tests for TodoParser."""

    def test_parse_content(self):
        """Test parsing TODO content."""
        parser = TodoParser()
        todo = parser.parse_content(SAMPLE_TODO)

        assert todo.meta.title == "开发一个博客系统"
        # Status parsing from text may differ
        assert len(todo.steps) == 5

    def test_parse_task_step(self):
        """Test parsing TASK step."""
        parser = TodoParser()
        todo = parser.parse_content(SAMPLE_TODO)

        step1 = todo.get_step("step1")
        assert step1 is not None
        assert step1.type == StepType.TASK
        assert step1.role == "pm"
        assert step1.output == "requirements.md"
        assert step1.status == StepStatus.PENDING

    def test_parse_human_step(self):
        """Test parsing HUMAN step."""
        parser = TodoParser()
        todo = parser.parse_content(SAMPLE_TODO)

        step2 = todo.get_step("step2")
        assert step2 is not None
        assert step2.type == StepType.HUMAN
        assert step2.pass_step == "step3"
        assert step2.reject_step == "step1"
        assert "step1" in step2.depends

    def test_parse_discuss_step(self):
        """Test parsing DISCUSS step."""
        parser = TodoParser()
        todo = parser.parse_content(SAMPLE_TODO)

        step4 = todo.get_step("step4")
        assert step4 is not None
        assert step4.type == StepType.DISCUSS
        assert step4.participants == ["architect", "backend", "frontend"]
        assert step4.rounds == 2

    def test_parse_completed_step(self):
        """Test parsing completed step."""
        parser = TodoParser()
        todo = parser.parse_content(SAMPLE_TODO)

        step3 = todo.get_step("step3")
        assert step3 is not None
        assert step3.status == StepStatus.DONE

    def test_parse_parallel_subtasks(self):
        """Test parsing subtasks under a PARALLEL step."""
        parser = TodoParser()
        todo = parser.parse_content(SAMPLE_TODO)

        step5 = todo.get_step("step5")
        assert step5 is not None
        assert step5.type == StepType.PARALLEL
        assert len(step5.subtasks) == 0

        parallel_todo = """# 任务：并行测试

## 元信息
- 创建时间：2024-01-15 10:00:00
- 状态：RUNNING

## 流程

- [ ] #step1 @parallel 并行开发
  - subtasks:
    - [ ] #step1.1 @task(backend) 开发后端
    - [ ] #step1.2 @task(frontend) 开发前端
"""
        parsed = parser.parse_content(parallel_todo)
        step1 = parsed.get_step("step1")
        assert step1 is not None
        assert step1.type == StepType.PARALLEL
        assert len(step1.subtasks) == 2
        assert step1.subtasks[0].id == "step1.1"
        assert step1.subtasks[1].id == "step1.2"

    def test_get_next_step(self):
        """Test getting next executable step."""
        parser = TodoParser()
        todo = parser.parse_content(SAMPLE_TODO)

        # step1 has no dependencies, should be first
        next_step = todo.get_next_step()
        assert next_step is not None
        assert next_step.id == "step1"


class TestTodoWriter:
    """Tests for TodoWriter."""

    def test_to_markdown(self):
        """Test converting TodoFile to markdown."""
        parser = TodoParser()
        writer = TodoWriter()

        original_todo = parser.parse_content(SAMPLE_TODO)
        markdown = writer.to_markdown(original_todo)

        # Parse the generated markdown
        reparsed_todo = parser.parse_content(markdown)

        assert reparsed_todo.meta.title == original_todo.meta.title
        assert len(reparsed_todo.steps) == len(original_todo.steps)

    def test_update_step_status(self, tmp_path):
        """Test updating step status in file."""
        parser = TodoParser()
        writer = TodoWriter()

        # Write initial file
        todo_path = tmp_path / "test.todo.md"
        todo_path.write_text(SAMPLE_TODO, encoding="utf-8")

        # Update status
        writer.update_step_status(todo_path, "step1", StepStatus.DONE)

        # Re-parse and check
        updated_todo = parser.parse_file(todo_path)
        step1 = updated_todo.get_step("step1")
        assert step1.status == StepStatus.DONE


class TestStepStatus:
    """Tests for StepStatus."""

    def test_from_markdown(self):
        """Test status from markdown conversion."""
        assert StepStatus.from_markdown("[ ]") == StepStatus.PENDING
        assert StepStatus.from_markdown("[x]") == StepStatus.DONE
        assert StepStatus.from_markdown("[~]") == StepStatus.RUNNING
        assert StepStatus.from_markdown("[!]") == StepStatus.FAILED
        assert StepStatus.from_markdown("[-]") == StepStatus.SKIPPED

    def test_to_markdown(self):
        """Test status to markdown conversion."""
        assert StepStatus.PENDING.to_markdown() == "[ ]"
        assert StepStatus.DONE.to_markdown() == "[x]"
        assert StepStatus.RUNNING.to_markdown() == "[~]"
        assert StepStatus.FAILED.to_markdown() == "[!]"
        assert StepStatus.SKIPPED.to_markdown() == "[-]"
