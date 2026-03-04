# TeamRun

[中文文档](docs/README_CN.md)

Multi-Agent collaboration framework for local development.

## Features

- **Multi-Agent Orchestration**: Coordinate multiple AI agents (Claude Code, Codex) working as a team
- **Role-Based Configuration**: Define roles like PM, Architect, Developer, Tester with specific prompts
- **Dynamic TODO Workflow**: Generate and execute structured TODO workflows based on tasks
- **File-Based State Management**: All state and context stored as files for transparency
- **Git Branch Isolation**: Parallel tasks run in isolated branches with automatic merge
- **Human Review Points**: Built-in support for human approval and feedback
- **Output Validation**: Configurable validators (file existence, tests, schema, LLM semantic check)
- **Controlled Replan**: Automatic local replan on step failure with traceable history

## Installation

```bash
pip install trun
```

Or install from source:

```bash
git clone https://github.com/teamrun/teamrun.git
cd teamrun
pip install .
```

## Quick Start

### 1. Initialize Project

```bash
# Initialize project in current directory (auto-generate project name)
trun init

# Initialize in current directory with specific name
trun init my-project

# Initialize in a specific directory
trun init my-project -w ~/projects/my-app

# Initialize with description
trun init my-project -w ~/projects/my-app -d "My awesome project"

# Initialize global config only (no project)
trun init --global
```

This will:
- Register the project in `~/.team_run/projects.json`
- Create `.team_run/` directory in the project path
- Save project name in `.team_run/project.json`

### 2. Configure Environment Variables

Create a `.env` file in your project root (or set environment variables):

```bash
# Service LLM Configuration
TRUN_LLM_PROVIDER=openai      # or anthropic
TRUN_LLM_MODEL=gpt-4          # or claude-3-opus, etc.

# API Keys
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key
TAVILY_API_KEY=your_tavily_key
```

### 3. Add Team Roles

```bash
# In project directory, auto-detect current project
cd ~/my-project
trun role add

# Or quick mode
trun role add pm --agent claude-code --quick
trun role add architect --agent claude-code --quick
trun role add backend --agent codex --quick

# Or operate on specific project from anywhere
trun role add -p my-project
```

### 4. Start a Task

```bash
# In project directory, auto-detect current project
cd ~/my-project
trun start "Build a blog system"

# Or operate on specific project from anywhere
trun start -p my-project "Build a blog system"
```

### 5. Check Status

```bash
# In project directory
trun status

# Or specify project
trun status -p my-project
```

### 6. Resume Interrupted Task

```bash
# In project directory
trun resume

# Or specify project
trun resume -p my-project
```

> **Note**:
> - When running commands inside a project directory, the project name is auto-detected from `.team_run/project.json`
> - Use `-p <project_name>` to operate on any registered project from any directory

## CLI Commands

### Project Management

| Command | Description |
|---------|-------------|
| `trun init` | Initialize project in current directory (auto-generate name) |
| `trun init <name>` | Initialize project with specific name |
| `trun init <name> -w <path>` | Initialize project in specific directory |
| `trun init --global` | Initialize global config only |
| `trun project list` | List all registered projects |
| `trun project show <name>` | Show project details |
| `trun project remove <name>` | Remove project from registry |

### Role Management

| Command | Description |
|---------|-------------|
| `trun role add [-p <project>]` | Add a new role (interactive) |
| `trun role list [-p <project>]` | List all configured roles |
| `trun role remove <id> [-p <project>]` | Remove a role |

### Task Execution

| Command | Description |
|---------|-------------|
| `trun start "<task>" [-p <project>]` | Start a new task |
| `trun resume [-p <project>]` | Resume interrupted task |
| `trun status [-p <project>]` | Show current task status |
| `trun logs [-p <project>]` | View execution logs |

> **Note**:
> - When inside a project directory, project name is auto-detected from `.team_run/project.json`
> - Project information is stored in:
>   - `~/.team_run/projects.json` - Global project registry
>   - `<project-dir>/.team_run/project.json` - Project name identifier

## Configuration

### Team Config (`.team_run/team.config.json`)

```json
{
  "roles": {
    "pm": {
      "name": "项目经理",
      "description": "负责项目规划和管理",
      "agent": "claude-code"
    }
  },
  "replan": {
    "policy": "auto",
    "max_attempts": 3,
    "scope": "local"
  },
  "validators": {
    "auto_file_check": true,
    "auto_completion_marker": true,
    "test_command": "pytest",
    "test_timeout": 300
  }
}
```

### Replan Policy

| Policy | Description |
|--------|-------------|
| `disabled` | No replan, fail immediately on error |
| `auto` | Automatically replan failed steps (local scope) |
| `confirm` | Ask for user confirmation before replan |

> Note: Service LLM configuration is managed via environment variables (`TRUN_LLM_PROVIDER`, `TRUN_LLM_MODEL`), not in this config file.

## TODO Workflow Syntax

### Step Types

| Type | Syntax | Description |
|------|--------|-------------|
| TASK | `@task(role)` | Single role executes task |
| DISCUSS | `@discuss(role1, role2)` | Multi-role discussion |
| PARALLEL | `@parallel` | Parallel execution |
| GATE | `@gate(condition)` | Conditional branch |
| HUMAN | `@human` | Human review point |
| GOTO | `@goto(step_id)` | Jump to step |

### Example TODO File

```markdown
# 任务：开发博客系统

## 流程

- [ ] #step1 @task(pm) 规划项目功能
  - output: requirements.md

- [ ] #step2 @human 审核需求
  - depends: step1
  - pass: step3
  - reject: step1

- [ ] #step3 @task(architect) 设计架构
  - depends: step2
  - output: design.md
  - validators:
    - file_exists:design.md
    - llm:架构设计需要包含数据模型和API设计
```

### Validators

| Type | Syntax | Description |
|------|--------|-------------|
| File Check | `file_exists:path` | Verify output file exists |
| Test | `test_pass:test_path` | Run tests and verify pass |
| Schema | `schema:schema.json` | Validate against JSON schema |
| LLM | `llm:requirement` | LLM semantic validation |

## Development

For contributors developing TeamRun itself:

```bash
# Clone the repository
git clone https://github.com/teamrun/teamrun.git
cd teamrun

# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Sync dependencies
uv sync

# Configure environment variables
cp .env.example .env
# Edit .env and fill in your API keys

# Run trun commands (for debugging)
uv run trun --help
uv run trun init
uv run trun role add
uv run trun start "测试任务"

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=trun

# Type check
uv run mypy trun

# Lint
uv run ruff check trun

# Format
uv run ruff format trun
```

## Project Structure

```
TeamRun/
├── trun/                       # Main package
│   ├── cli.py                  # CLI entry point
│   ├── config.py               # Configuration management
│   ├── todo/                   # TODO file handling
│   │   ├── models.py           # Data models
│   │   ├── parser.py           # Parser and writer
│   │   └── generator.py        # LLM-based generator
│   ├── scheduler/              # Workflow execution
│   │   ├── scheduler.py        # Main scheduler
│   │   ├── state_manager.py    # State management
│   │   └── replan.py           # Replan engine
│   ├── validators/             # Output validation
│   │   ├── base.py             # Base validator class
│   │   ├── factory.py          # Validator factory
│   │   ├── file_validator.py   # File existence validator
│   │   ├── test_validator.py   # Test pass validator
│   │   ├── schema_validator.py # JSON schema validator
│   │   └── llm_validator.py    # LLM semantic validator
│   ├── adapters/               # Agent adapters
│   │   ├── base.py             # Base adapter class
│   │   ├── claude_code.py      # Claude Code adapter
│   │   ├── codex.py            # Codex adapter
│   │   └── factory.py          # Adapter factory
│   ├── tools/                  # Built-in tools
│   │   ├── file_ops.py         # File operations
│   │   ├── git_ops.py          # Git operations
│   │   ├── shell.py            # Shell commands
│   │   └── web_search.py       # Web search (Tavily)
│   ├── llm/                    # LLM services
│   │   └── service_llm.py      # Service LLM
│   └── utils/                  # Utilities
│       ├── env.py              # Environment management
│       └── logger.py           # Logging
├── tests/                      # Tests
├── pyproject.toml              # Project configuration
├── DESIGN.md                   # Design documentation
└── README.md
```

## License

MIT
