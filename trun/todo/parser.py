"""
TODO file parser.

Parses markdown TODO files into structured data.
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import Step, StepStatus, StepType, TodoFile, TodoMeta


class TodoParser:
    """Parser for TODO markdown files."""

    # Regex patterns
    STEP_PATTERN = re.compile(
        r'^- \[([ x~!\-])\]\s+'      # Checkbox
        r'(?:#(\w+(?:\.\w+)?)\s+)?'  # Optional step ID
        r'@(\w+)(?:\(([^)]*)\))?\s*' # Step type with optional args
        r'(.*)$',                     # Description
        re.MULTILINE
    )

    META_PATTERN = re.compile(r'^- ([^:]+):\s*(.+)$', re.MULTILINE)
    PROPERTY_PATTERN = re.compile(r'^\s+- (\w+):\s*(.+)$', re.MULTILINE)

    def __init__(self):
        pass

    def parse_file(self, file_path: str | Path) -> TodoFile:
        """
        Parse a TODO markdown file.

        :param file_path: Path to the TODO file
        :return: Parsed TodoFile object
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"TODO file not found: {path}")

        content = path.read_text(encoding="utf-8")
        return self.parse_content(content, str(path))

    def parse_content(self, content: str, file_path: str = "") -> TodoFile:
        """
        Parse TODO content string.

        :param content: TODO file content
        :param file_path: Optional file path for reference
        :return: Parsed TodoFile object
        """
        lines = content.split('\n')

        # Parse title (first # heading)
        title = self._parse_title(lines)

        # Parse metadata section
        meta = self._parse_meta(content, title)

        # Parse steps
        steps = self._parse_steps(content)

        return TodoFile(
            file_path=file_path,
            meta=meta,
            steps=steps
        )

    def _parse_title(self, lines: list[str]) -> str:
        """Extract title from the first heading."""
        for line in lines:
            line = line.strip()
            if line.startswith('# '):
                # Remove "任务：" prefix if present
                title = line[2:].strip()
                if title.startswith('任务：'):
                    title = title[3:]
                return title
        return "Untitled"

    def _parse_meta(self, content: str, title: str) -> TodoMeta:
        """Parse metadata section."""
        meta = TodoMeta(title=title)

        # Find 元信息 section
        meta_section = re.search(
            r'## 元信息\s*\n((?:- .+\n?)+)',
            content
        )

        if meta_section:
            meta_content = meta_section.group(1)
            for match in self.META_PATTERN.finditer(meta_content):
                key, value = match.groups()
                key = key.strip()
                value = value.strip()

                if key == '创建时间':
                    try:
                        meta.created_at = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        pass
                elif key == '状态':
                    meta.status = self._parse_status_text(value)
                elif key == '参与者':
                    meta.participants = [p.strip() for p in value.split(',')]
                elif key == '总轮次':
                    meta.total_rounds = int(value)

        return meta

    def _parse_status_text(self, text: str) -> StepStatus:
        """Parse status from text."""
        mapping = {
            'PENDING': StepStatus.PENDING,
            'RUNNING': StepStatus.RUNNING,
            'DONE': StepStatus.DONE,
            'FAILED': StepStatus.FAILED,
            'SKIPPED': StepStatus.SKIPPED,
        }
        return mapping.get(text.upper(), StepStatus.PENDING)

    def _parse_steps(self, content: str) -> list[Step]:
        """Parse all steps from content."""
        steps = []
        lines = content.split('\n')

        current_step = None
        step_counter = 0

        for i, line in enumerate(lines):
            # Check for step line
            match = self.STEP_PATTERN.match(line)
            if match:
                checkbox, step_id, step_type, args, description = match.groups()

                # Generate step ID if not provided
                step_counter += 1
                if not step_id:
                    step_id = f"step{step_counter}"

                # Parse step type
                parsed_type = self._parse_step_type(step_type)

                # Create step
                step = Step(
                    id=step_id,
                    type=parsed_type,
                    status=StepStatus.from_markdown(f"[{checkbox}]"),
                    description=description.strip(),
                )

                # Parse type-specific arguments
                self._parse_step_args(step, step_type, args)

                # Parse properties from following lines
                self._parse_step_properties(step, lines, i + 1)

                steps.append(step)
                current_step = step

        return steps

    def _parse_step_type(self, type_str: str) -> StepType:
        """Parse step type from string."""
        type_str = type_str.lower()
        mapping = {
            'task': StepType.TASK,
            'discuss': StepType.DISCUSS,
            'parallel': StepType.PARALLEL,
            'gate': StepType.GATE,
            'human': StepType.HUMAN,
            'goto': StepType.GOTO,
        }
        return mapping.get(type_str, StepType.TASK)

    def _parse_step_args(self, step: Step, type_str: str, args: str | None) -> None:
        """Parse step type-specific arguments."""
        if not args:
            return

        args = args.strip()

        if step.type == StepType.TASK:
            # @task(role)
            step.role = args

        elif step.type == StepType.DISCUSS:
            # @discuss(role1, role2, ...)
            step.participants = [p.strip() for p in args.split(',')]

        elif step.type == StepType.GATE:
            # @gate(condition)
            step.condition = args

        elif step.type == StepType.GOTO:
            # @goto(step_id)
            step.target_step = args

    def _parse_step_properties(self, step: Step, lines: list[str], start_idx: int) -> None:
        """Parse step properties from indented lines."""
        for i in range(start_idx, len(lines)):
            line = lines[i]

            # Stop at non-indented line or empty line
            if not line.startswith('  ') or not line.strip():
                break

            # Parse property
            match = re.match(r'^\s+- (\w+):\s*(.+)$', line)
            if match:
                key, value = match.groups()
                key = key.lower()
                value = value.strip()

                if key == 'output':
                    step.output = value
                elif key == 'instruction':
                    step.instruction = value
                elif key == 'depends':
                    step.depends = [d.strip().lstrip('#') for d in value.split(',')]
                elif key == 'input':
                    step.inputs = [i.strip() for i in value.split(',')]
                elif key == 'rounds':
                    step.rounds = int(value)
                elif key == 'pass':
                    step.pass_step = value.lstrip('#')
                elif key == 'reject':
                    step.reject_step = value.lstrip('#')


class TodoWriter:
    """Writer for TODO markdown files."""

    def __init__(self):
        pass

    def write_file(self, todo: TodoFile, file_path: str | Path | None = None) -> str:
        """
        Write TodoFile to markdown format.

        :param todo: TodoFile object to write
        :param file_path: Optional path to write to (uses todo.file_path if not provided)
        :return: Generated markdown content
        """
        content = self.to_markdown(todo)

        path = Path(file_path) if file_path else Path(todo.file_path)
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        return content

    def to_markdown(self, todo: TodoFile) -> str:
        """Convert TodoFile to markdown string."""
        lines = []

        # Title
        lines.append(f"# 任务：{todo.meta.title}")
        lines.append("")

        # Metadata
        lines.append("## 元信息")
        lines.append(f"- 创建时间：{todo.meta.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"- 状态：{todo.meta.status.value.upper()}")
        if todo.meta.participants:
            lines.append(f"- 参与者：{', '.join(todo.meta.participants)}")
        if todo.meta.total_rounds:
            lines.append(f"- 总轮次：{todo.meta.total_rounds}")
        lines.append("")

        # Steps
        lines.append("## 流程")
        lines.append("")

        for step in todo.steps:
            lines.extend(self._step_to_lines(step))
            lines.append("")

        return '\n'.join(lines)

    def _step_to_lines(self, step: Step, indent: str = "") -> list[str]:
        """Convert a step to markdown lines."""
        lines = []

        # Main step line
        checkbox = step.status.to_markdown()
        type_str = self._step_type_to_string(step)
        line = f"{indent}- {checkbox} #{step.id} {type_str}"
        if step.description:
            line += f" {step.description}"
        lines.append(line)

        # Properties
        prop_indent = indent + "  "
        if step.depends:
            lines.append(f"{prop_indent}- depends: {', '.join('#' + d for d in step.depends)}")
        if step.inputs:
            lines.append(f"{prop_indent}- input: {', '.join(step.inputs)}")
        if step.output:
            lines.append(f"{prop_indent}- output: {step.output}")
        if step.instruction:
            lines.append(f"{prop_indent}- instruction: {step.instruction}")
        if step.rounds and step.type == StepType.DISCUSS:
            lines.append(f"{prop_indent}- rounds: {step.rounds}")
        if step.pass_step:
            lines.append(f"{prop_indent}- pass: #{step.pass_step}")
        if step.reject_step:
            lines.append(f"{prop_indent}- reject: #{step.reject_step}")

        # Subtasks for parallel
        if step.subtasks:
            lines.append(f"{prop_indent}- subtasks:")
            for subtask in step.subtasks:
                lines.extend(self._step_to_lines(subtask, prop_indent + "  "))

        return lines

    def _step_type_to_string(self, step: Step) -> str:
        """Convert step to type string with arguments."""
        if step.type == StepType.TASK:
            return f"@task({step.role})" if step.role else "@task"
        elif step.type == StepType.DISCUSS:
            if step.participants:
                return f"@discuss({', '.join(step.participants)})"
            return "@discuss"
        elif step.type == StepType.PARALLEL:
            return "@parallel"
        elif step.type == StepType.GATE:
            return f"@gate({step.condition})" if step.condition else "@gate"
        elif step.type == StepType.HUMAN:
            return "@human"
        elif step.type == StepType.GOTO:
            return f"@goto({step.target_step})" if step.target_step else "@goto"
        return "@task"

    def update_step_status(
        self,
        file_path: str | Path,
        step_id: str,
        status: StepStatus
    ) -> None:
        """
        Update a step's status in the TODO file.

        :param file_path: Path to the TODO file
        :param step_id: Step ID to update
        :param status: New status
        """
        parser = TodoParser()
        todo = parser.parse_file(file_path)

        if todo.update_step_status(step_id, status):
            self.write_file(todo, file_path)
