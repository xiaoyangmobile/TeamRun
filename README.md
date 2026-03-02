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

In your project directory:

```bash
trun init
```

This creates `.team_run/` directory with configuration files.

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
# Interactive mode
trun role add

# Or quick mode
trun role add pm --agent claude-code --quick
trun role add architect --agent claude-code --quick
trun role add backend --agent codex --quick
```

### 4. Start a Task

```bash
trun start "开发一个博客系统"
```

### 5. Check Status

```bash
trun status
```

### 6. Resume Interrupted Task

```bash
trun resume
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `trun init` | Initialize TeamRun configuration |
| `trun role add` | Add a new role (interactive) |
| `trun role list` | List all configured roles |
| `trun role remove <id>` | Remove a role |
| `trun start "<task>"` | Start a new task |
| `trun resume` | Resume interrupted task |
| `trun status` | Show current task status |
| `trun logs` | View execution logs |

## Configuration

### Team Config (`.team_run/team.config.json`)

```json
{
  "roles": {
    "pm": {
      "name": "项目经理",
      "description": "负责项目规划和管理",
      "agent": "claude-code",
      "prompt": "你是项目经理，负责..."
    }
  }
}
```

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
```

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
│   │   └── state_manager.py    # State management
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
