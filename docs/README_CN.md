# TeamRun

本地多 Agent 协同工作框架。

## 功能特性

- **多 Agent 编排**：协调多个 AI Agent（Claude Code、Codex）作为团队协同工作
- **角色配置**：定义项目经理、架构师、开发工程师、测试工程师等角色，配置专属提示词
- **动态 TODO 工作流**：根据任务自动生成并执行结构化的 TODO 工作流
- **文件即状态**：所有状态和上下文以文件形式存储，透明可追溯
- **Git 分支隔离**：并行任务在独立分支中执行，自动合并
- **人工审核节点**：内置人工审批和反馈机制
- **输出验证**：可配置的验证器（文件存在、测试通过、Schema 校验、LLM 语义检查）
- **受控重规划**：步骤失败时自动进行局部重规划，可追溯历史

## 安装

```bash
pip install trun
```

或从源码安装：

```bash
git clone https://github.com/teamrun/teamrun.git
cd teamrun
pip install .
```

## 快速开始

### 1. 初始化项目

在你的项目目录中：

```bash
trun init
```

这将创建 `.team_run/` 目录及配置文件。

### 2. 配置环境变量

在项目根目录创建 `.env` 文件（或设置系统环境变量）：

```bash
# Service LLM 配置
TRUN_LLM_PROVIDER=openai      # 或 anthropic
TRUN_LLM_MODEL=gpt-4          # 或 claude-3-opus 等

# API Keys
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key
TAVILY_API_KEY=your_tavily_key
```

### 3. 添加团队角色

```bash
# 交互式添加
trun role add

# 或快速模式
trun role add pm --agent claude-code --quick
trun role add architect --agent claude-code --quick
trun role add backend --agent codex --quick
```

### 4. 启动任务

```bash
trun start "开发一个博客系统"
```

### 5. 查看状态

```bash
trun status
```

### 6. 恢复中断的任务

```bash
trun resume
```

## CLI 命令

| 命令 | 说明 |
|------|------|
| `trun init` | 初始化 TeamRun 配置 |
| `trun role add` | 添加角色（交互式） |
| `trun role list` | 列出所有角色 |
| `trun role remove <id>` | 删除角色 |
| `trun start "<任务>"` | 启动新任务 |
| `trun resume` | 恢复中断的任务 |
| `trun status` | 查看当前任务状态 |
| `trun logs` | 查看执行日志 |

## 配置文件

### 团队配置 (`.team_run/team.config.json`)

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

### 重规划策略

| 策略 | 说明 |
|------|------|
| `disabled` | 禁用重规划，失败后立即中止 |
| `auto` | 自动重规划失败的步骤（局部范围） |
| `confirm` | 重规划前询问用户确认 |

> 注意：Service LLM 配置通过环境变量管理（`TRUN_LLM_PROVIDER`、`TRUN_LLM_MODEL`），不在此配置文件中。

## TODO 工作流语法

### 步骤类型

| 类型 | 语法 | 说明 |
|------|------|------|
| 任务 | `@task(role)` | 指定角色执行任务 |
| 讨论 | `@discuss(role1, role2)` | 多角色讨论 |
| 并行 | `@parallel` | 并行执行子任务 |
| 条件 | `@gate(condition)` | 条件分支 |
| 人工 | `@human` | 人工审核节点 |
| 跳转 | `@goto(step_id)` | 跳转到指定步骤 |

### TODO 文件示例

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

### 验证器

| 类型 | 语法 | 说明 |
|------|------|------|
| 文件检查 | `file_exists:path` | 验证输出文件存在 |
| 测试 | `test_pass:test_path` | 运行测试并验证通过 |
| Schema | `schema:schema.json` | 验证符合 JSON Schema |
| LLM | `llm:requirement` | LLM 语义验证 |

### 状态标记

| 状态 | 标记 | 说明 |
|------|------|------|
| 待执行 | `- [ ]` | 等待执行 |
| 执行中 | `- [~]` | 正在执行 |
| 已完成 | `- [x]` | 执行成功 |
| 失败 | `- [!]` | 执行失败 |
| 跳过 | `- [-]` | 已跳过 |

## 开发指南

面向 TeamRun 项目贡献者：

```bash
# 克隆仓库
git clone https://github.com/teamrun/teamrun.git
cd teamrun

# 安装 uv（如未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 同步依赖
uv sync

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入你的 API Keys

# 调试运行 trun 命令
uv run trun --help
uv run trun init
uv run trun role add
uv run trun start "测试任务"

# 运行测试
uv run pytest

# 运行测试（带覆盖率）
uv run pytest --cov=trun

# 类型检查
uv run mypy trun

# 代码检查
uv run ruff check trun

# 代码格式化
uv run ruff format trun
```

## 项目结构

```
TeamRun/
├── trun/                       # 主包
│   ├── cli.py                  # CLI 入口
│   ├── config.py               # 配置管理
│   ├── todo/                   # TODO 文件处理
│   │   ├── models.py           # 数据模型
│   │   ├── parser.py           # 解析器和写入器
│   │   └── generator.py        # LLM 生成器
│   ├── scheduler/              # 工作流执行
│   │   ├── scheduler.py        # 调度器
│   │   ├── state_manager.py    # 状态管理
│   │   └── replan.py           # 重规划引擎
│   ├── validators/             # 输出验证
│   │   ├── base.py             # 验证器基类
│   │   ├── factory.py          # 验证器工厂
│   │   ├── file_validator.py   # 文件存在验证器
│   │   ├── test_validator.py   # 测试通过验证器
│   │   ├── schema_validator.py # JSON Schema 验证器
│   │   └── llm_validator.py    # LLM 语义验证器
│   ├── adapters/               # Agent 适配器
│   │   ├── base.py             # 适配器基类
│   │   ├── claude_code.py      # Claude Code 适配器
│   │   ├── codex.py            # Codex 适配器
│   │   └── factory.py          # 适配器工厂
│   ├── tools/                  # 内置工具
│   │   ├── file_ops.py         # 文件操作
│   │   ├── git_ops.py          # Git 操作
│   │   ├── shell.py            # Shell 命令
│   │   └── web_search.py       # 网络搜索（Tavily）
│   ├── llm/                    # LLM 服务
│   │   └── service_llm.py      # Service LLM
│   └── utils/                  # 工具类
│       ├── env.py              # 环境变量管理
│       └── logger.py           # 日志
├── tests/                      # 测试
├── docs/                       # 文档
├── pyproject.toml              # 项目配置
├── DESIGN.md                   # 设计文档
└── README.md                   # 英文文档
```

## 许可证

MIT
