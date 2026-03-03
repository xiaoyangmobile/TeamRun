# TeamRun 设计文档

## 核心理念

**文件即状态，TODO 即流程**

- 根据用户角色和任务，**动态生成** TODO 文件
- TODO 文件本身就是流程控制
- 每个步骤产生新的 TODO 文件（子任务、讨论记录等）
- 执行引擎只需要：**解析 TODO → 执行 → 更新状态 → 继续**

## 系统架构

```
┌─────────────────────────────────────────────┐
│                 TeamRun CLI                  │
├─────────────────────────────────────────────┤
│  1. TODO 生成器（根据角色+任务生成初始TODO）    │
│  2. TODO 解析器（解析 markdown 语法）          │
│  3. 流程调度器（执行、并行、条件判断）          │
│  4. Agent 适配器（调用各类 Agent CLI）         │
│  5. 状态管理器（更新 TODO 文件状态）           │
│  6. 服务 LLM（处理项目外任务，如生成TODO）      │
└─────────────────────────────────────────────┘
                      ↓↑
         .team_run/todos/*.todo.md（文件系统）
```

## 配置设计

### 全局配置路径
- 全局：`~/.team_run/`
- 项目级：`./.team_run/`（优先级更高）

### 团队配置文件：team.config.json

```json
{
  "roles": {
    "pm": {
      "name": "项目经理",
      "description": "项目管理者，规划项目功能和架构",
      "agent": "claude-code",
      "prompt": "你是项目经理，负责..."
    },
    "architect": {
      "name": "开发架构师",
      "description": "开发主负责人，负责代码架构设计和代码review",
      "agent": "claude-code",
      "prompt": "你是架构师，负责..."
    },
    "backend": {
      "name": "后端工程师",
      "description": "后端开发人员，负责后端代码编写",
      "agent": "codex",
      "prompt": "你是后端工程师，负责..."
    },
    "frontend": {
      "name": "前端工程师",
      "description": "前端开发人员，负责前端代码编写",
      "agent": "codex",
      "prompt": "你是前端工程师，负责..."
    },
    "tester": {
      "name": "测试工程师",
      "description": "测试人员，负责做最后的代码测试",
      "agent": "claude-code",
      "prompt": "你是测试工程师，负责..."
    }
  },
  "service_llm": {
    "provider": "openai",
    "model": "gpt-4",
    "api_key_env": "OPENAI_API_KEY"
  }
}
```

## TODO 文件语法设计

### 步骤类型枚举

| 类型 | 语法 | 描述 |
|------|------|------|
| `TASK` | `@task(role)` | 单角色执行任务 |
| `DISCUSS` | `@discuss(role1, role2, ...)` | 多角色讨论 |
| `PARALLEL` | `@parallel` | 并行执行（子项为并行任务） |
| `GATE` | `@gate(condition)` | 条件判断 |
| `HUMAN` | `@human` | 人工审核节点 |
| `GOTO` | `@goto(step_id)` | 跳转到指定步骤 |

### 状态枚举

| 状态 | Markdown 表示 | 描述 |
|------|---------------|------|
| `PENDING` | `- [ ]` | 待执行 |
| `RUNNING` | `- [~]` | 执行中 |
| `DONE` | `- [x]` | 已完成 |
| `FAILED` | `- [!]` | 失败 |
| `SKIPPED` | `- [-]` | 跳过 |

### 示例：主 TODO 文件

`.team_run/todos/main.todo.md`

```markdown
# 任务：开发一个博客系统

## 元信息
- 创建时间：2024-01-15 10:00:00
- 状态：RUNNING

## 流程

- [ ] #step1 @task(pm) 规划项目功能
  - output: requirements.md
  - instruction: 分析用户需求，输出详细的功能需求文档

- [ ] #step2 @human 审核需求文档
  - depends: #step1
  - pass: #step3
  - reject: #step1

- [ ] #step3 @task(architect) 编写技术方案
  - depends: #step2
  - output: design.md
  - instruction: 根据需求文档设计技术架构

- [ ] #step4 @discuss(architect, backend, frontend) 讨论技术方案
  - depends: #step3
  - rounds: 2
  - output: discussion_001.md

- [ ] #step5 @task(architect) 更新技术方案
  - depends: #step4
  - input: discussion_001.md
  - output: design.md

- [ ] #step6 @parallel 并行开发
  - depends: #step5
  - subtasks:
    - [ ] #step6.1 @task(backend) 开发后端 API
    - [ ] #step6.2 @task(frontend) 开发前端页面

- [ ] #step7 @task(architect) 代码 Review
  - depends: #step6
  - output: review.md

- [ ] #step8 @gate(review.md:passed)
  - depends: #step7
  - pass: #step9
  - reject: #step6

- [ ] #step9 @task(tester) 执行测试
  - depends: #step8
```

### 示例：讨论 TODO 文件

`.team_run/todos/discussion_001.todo.md`

```markdown
# 讨论：技术方案

## 元信息
- 创建时间：2024-01-15 14:00:00
- 状态：RUNNING
- 参与者：architect, backend, frontend
- 总轮次：2

## Round 1

- [ ] @task(architect) 阐述方案要点
  - output: round1_architect.md

- [ ] @task(backend) 从后端角度提出意见
  - input: round1_architect.md
  - output: round1_backend.md

- [ ] @task(frontend) 从前端角度提出意见
  - input: round1_architect.md
  - output: round1_frontend.md

## Round 2

- [ ] @task(architect) 回应意见并总结
  - input: round1_backend.md, round1_frontend.md
  - output: round2_summary.md

## 结论

（执行完毕后由系统提取填入）
```

## 模块设计

### 1. TODO 生成器 (todo_generator.py)
- 输入：用户任务描述 + 角色配置
- 输出：初始 TODO 文件
- 使用服务 LLM 生成

### 2. TODO 解析器 (todo_parser.py)
- 解析 Markdown TODO 语法
- 提取步骤类型、角色、依赖关系等
- 返回结构化的任务列表

### 3. 流程调度器 (scheduler.py)
- 读取 TODO 文件
- 按依赖顺序执行任务
- 处理并行、条件判断、循环
- 更新任务状态

### 4. Agent 适配器 (adapters/)
- `claude_code_adapter.py`
- `codex_adapter.py`
- `opencode_adapter.py`
- 统一接口：`execute(instruction, context) -> result`

### 5. 状态管理器 (state_manager.py)
- 更新 TODO 文件中的状态标记
- 记录执行日志
- 支持中断恢复

### 6. 服务 LLM (service_llm.py)
- 用于项目外处理（生成 TODO、提取结论等）
- 独立的上下文管理

## 执行流程

```
用户输入任务
     ↓
服务 LLM 生成初始 TODO
     ↓
┌─→ 解析 TODO 文件
│        ↓
│   找到下一个待执行步骤
│        ↓
│   根据步骤类型执行
│   - TASK: 调用对应 Agent
│   - DISCUSS: 生成讨论子 TODO
│   - PARALLEL: 并发执行子任务
│   - GATE: 判断条件
│   - HUMAN: 等待用户输入
│        ↓
│   更新 TODO 状态
│        ↓
│   检查是否完成
│        ↓
└─── 未完成则继续 ←─┘
```

## 已确定的设计决策

### MVP 范围

| 功能 | MVP | 后续 |
|------|-----|------|
| 角色配置 | ✅ | |
| TODO 生成 | ✅ | |
| TODO 解析执行 | ✅ | |
| @task 单任务 | ✅ | |
| @human 人工审核 | ✅ | |
| @discuss 讨论 | ✅ | |
| @parallel 并行 | ✅ | |
| @gate 条件判断 | ✅ | |
| Claude Code 适配器 | ✅ | |
| Codex 适配器 | ✅ | |
| Web UI | | ✅ |

### 日志存储

- 路径：`.team_run/logs/YYYY_MM_DD.log`
- 按天分文件
- 存储在当前工作目录下

### 并发控制

- 使用 Git 分支隔离
- `@parallel` 执行时，每个子任务在独立分支工作
- 所有子任务完成后，自动合并到主分支
- 合并冲突时中止并提醒用户

### 上下文传递

**原则：所有操作基于文件**

- 每个任务执行前，生成任务上下文文件
- 文件包含：任务说明、相关输入文件路径、角色 prompt
- Agent 自行读取文件获取上下文
- 示例：`.team_run/context/step1_context.md`

```markdown
# 任务上下文

## 角色
你是项目经理，负责...

## 任务
规划项目功能，输出详细的功能需求文档

## 输入文件
- 用户原始需求：.team_run/inputs/user_request.md

## 输出要求
- 输出文件：.team_run/outputs/requirements.md
- 完成后在文件末尾添加标记：<!-- TASK_COMPLETED -->
```

### 错误处理

- 任务失败后**立即中止**整个流程
- 更新 TODO 状态为 `FAILED`
- 在日志中记录错误详情
- 提醒用户处理
- 用户修复后可手动恢复执行

### 服务 LLM

- 使用 LiteLLM + 自定义上下文管理
- 保持轻量，按需扩展

### 人工介入点

`@human` 节点交互设计：

```
[TeamRun] 等待人工审核...
[TeamRun] 请查看文件：.team_run/outputs/requirements.md

选项：
  [p] 通过 (pass)
  [r] 驳回 (reject)
  [m] 添加修改意见
  [q] 退出

> m
请输入修改意见（输入空行结束）：
> 需要补充用户权限管理功能
> 登录需要支持第三方OAuth
>

[TeamRun] 意见已保存到 .team_run/feedback/step2_feedback.md
[TeamRun] 返回步骤 #step1 重新执行...
```

- 支持添加修改意见
- 意见保存到 feedback 文件
- 重新执行时，Agent 可以读取 feedback 作为补充输入

## Agent 适配器设计

### 概述

使用官方 SDK 封装，统一接口：

```python
class AgentAdapter(ABC):
    @abstractmethod
    async def execute(self, context_file: str) -> AgentResult:
        """
        执行任务
        :param context_file: 任务上下文文件路径
        :return: AgentResult 包含 success, output_files, error 等
        """
        pass

    @abstractmethod
    async def stop(self):
        """停止当前任务"""
        pass
```

### Claude Code 适配器

使用官方 **Claude Agent SDK** (`pip install claude-agent-sdk`)

**特性：**
- 内置工具：Read、Write、Edit、Bash、Glob、Grep 等
- 双向通信：通过 async generator 实时获取消息
- Hook 注入：PreToolUse、PostToolUse 等生命周期钩子
- 权限控制：allowed_tools、permission_mode
- 会话管理：支持 resume 继续上下文

**实现示例：**

```python
from claude_agent_sdk import query, ClaudeAgentOptions

class ClaudeCodeAdapter(AgentAdapter):
    async def execute(self, context_file: str) -> AgentResult:
        # 读取上下文文件内容
        with open(context_file, 'r') as f:
            context = f.read()

        result_text = ""
        session_id = None

        async for message in query(
            prompt=f"请阅读以下任务上下文并执行任务：\n\n{context}",
            options=ClaudeAgentOptions(
                allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
                permission_mode="acceptEdits",
                hooks={
                    "PostToolUse": [
                        HookMatcher(matcher="Edit|Write", hooks=[self._log_file_change])
                    ]
                }
            ),
        ):
            if hasattr(message, "subtype") and message.subtype == "init":
                session_id = message.session_id
            if hasattr(message, "result"):
                result_text = message.result

        return AgentResult(
            success=True,
            output=result_text,
            session_id=session_id
        )

    async def _log_file_change(self, input_data, tool_use_id, context):
        """Hook：记录文件变更"""
        file_path = input_data.get("tool_input", {}).get("file_path", "unknown")
        self.logger.info(f"File modified: {file_path}")
        return {}
```

**参考文档：** https://platform.claude.com/docs/en/agent-sdk/overview

### Codex 适配器

使用社区 SDK **codex-local-sdk-python** (`pip install codex-local-sdk-python`)

**特性：**
- 同步/异步接口：run、run_async、run_live_async
- 流式事件：实时 JSONL 事件处理
- 会话管理：start_thread、resume
- 重试策略：RetryPolicy 配置
- Schema 约束：支持 JSON Schema 输出

**实现示例：**

```python
from codex_local_sdk import CodexLocalClient, CodexExecRequest, SandboxMode

class CodexAdapter(AgentAdapter):
    def __init__(self):
        self.client = CodexLocalClient(
            retry_policy=RetryPolicy(max_retries=3),
            event_hook=self._on_event
        )

    async def execute(self, context_file: str) -> AgentResult:
        # 读取上下文文件内容
        with open(context_file, 'r') as f:
            context = f.read()

        request = CodexExecRequest(
            prompt=f"请阅读以下任务上下文并执行任务：\n\n{context}",
            model="codex",
            sandbox=SandboxMode.FULL_AUTO
        )

        result = await self.client.run_async(request, timeout_seconds=300)

        return AgentResult(
            success=result.success,
            output=result.final_message,
            session_id=result.session_id
        )

    def _on_event(self, event: CodexClientEvent):
        """事件回调：用于日志和监控"""
        self.logger.info(f"Codex event: {event.type}")
```

**参考项目：** https://github.com/maestromaximo/codex-local-sdk-python

### 适配器工厂

```python
class AdapterFactory:
    _adapters = {
        "claude-code": ClaudeCodeAdapter,
        "codex": CodexAdapter,
    }

    @classmethod
    def create(cls, agent_type: str) -> AgentAdapter:
        if agent_type not in cls._adapters:
            raise ValueError(f"Unknown agent type: {agent_type}")
        return cls._adapters[agent_type]()

    @classmethod
    def register(cls, name: str, adapter_class: type):
        """注册自定义适配器"""
        cls._adapters[name] = adapter_class
```

## CLI 设计

### 命令名称

`trun`

### 命令列表

```bash
# 初始化项目配置
trun init

# 角色管理（交互式）
trun role add              # 交互式添加角色
trun role add pm --agent claude-code --quick  # 快速创建骨架
trun role list             # 列出所有角色
trun role edit pm          # 编辑角色
trun role remove pm        # 删除角色

# 任务执行
trun start "开发一个博客系统"    # 启动新任务
trun resume                      # 从中断处恢复
trun status                      # 查看当前状态

# 日志
trun logs                        # 查看今日日志
trun logs --date 2024-01-15      # 查看指定日期日志
```

### 非交互模式

```bash
# 自动跳过所有人工审核节点
trun start "任务描述" --auto-approve

# 指定配置文件
trun start "任务描述" --config ./custom.config.json
```

### 角色添加交互流程

```
$ trun role add

角色ID: pm
显示名称: 项目经理
角色描述: 项目管理者，规划项目功能和架构
Agent类型 [claude-code/codex]: claude-code
Prompt文件路径 (可选，留空则手动输入): .team_run/prompts/pm.md

✅ 角色 pm 添加成功
```

## 内置工具设计

### 工具使用场景

| 场景 | Agent 类型 | 工具来源 |
|------|-----------|---------|
| 用户配置的角色（PM、架构师等） | Claude Code / Codex | **Agent 自带工具** |
| TeamRun 系统创建的子 Agent | 服务 LLM 驱动 | **TeamRun 内置工具** |

### 子 Agent 使用场景

- 生成初始 TODO
- 提取讨论结论
- 判断 Gate 条件
- 解析 Agent 输出
- 其他系统级任务

子 Agent 与服务 LLM 共用配置。

### 工具清单

```python
tools = {
    # 文件操作
    "read_file": "读取文件内容",
    "write_file": "写入文件",
    "append_file": "追加内容到文件",
    "file_exists": "检查文件是否存在",
    "list_files": "列出目录下的文件",

    # TODO 操作
    "parse_todo": "解析 TODO 文件",
    "update_todo_status": "更新步骤状态",
    "get_next_step": "获取下一个待执行步骤",
    "create_sub_todo": "创建子 TODO 文件",

    # Git 操作
    "git_create_branch": "创建分支",
    "git_switch_branch": "切换分支",
    "git_merge_branch": "合并分支",
    "git_check_conflicts": "检查合并冲突",
    "git_status": "查看 Git 状态",

    # Shell 命令
    "run_command": "执行 Shell 命令",
    "run_tests": "运行测试",
    "run_build": "运行构建",

    # 网络搜索
    "web_search": "网络搜索（Tavily）",

    # 日志
    "log": "记录日志",
}
```

### 环境变量配置

工具所需的 API Key 从项目 `.env` 文件读取：

```bash
# .env
TAVILY_API_KEY=your_tavily_api_key
OPENAI_API_KEY=your_openai_api_key
ANTHROPIC_API_KEY=your_anthropic_api_key
```

### 工具实现示例

#### 网络搜索（Tavily）

```python
# tools/web_search.py
import os
from tavily import TavilyClient

class WebSearchTool:
    def __init__(self):
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            raise ValueError("TAVILY_API_KEY not found in environment")
        self.client = TavilyClient(api_key=api_key)

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        """
        执行网络搜索
        :param query: 搜索关键词
        :param max_results: 最大结果数
        :return: 搜索结果列表
        """
        response = self.client.search(query, max_results=max_results)
        return response.get("results", [])
```

#### Shell 命令

```python
# tools/shell.py
import subprocess

class ShellTool:
    def run_command(
        self,
        command: str,
        cwd: str = None,
        timeout: int = 300
    ) -> dict:
        """
        执行 Shell 命令
        :param command: 命令字符串
        :param cwd: 工作目录
        :param timeout: 超时秒数
        :return: {"success": bool, "stdout": str, "stderr": str, "code": int}
        """
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "code": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "stdout": "",
                "stderr": "Command timed out",
                "code": -1
            }
```

#### 文件操作

```python
# tools/file_ops.py
import os

class FileOpsTool:
    def read_file(self, path: str) -> dict:
        """读取文件内容"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return {"success": True, "content": f.read()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def write_file(self, path: str, content: str) -> dict:
        """写入文件"""
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def append_file(self, path: str, content: str) -> dict:
        """追加内容到文件"""
        try:
            with open(path, 'a', encoding='utf-8') as f:
                f.write(content)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def file_exists(self, path: str) -> bool:
        """检查文件是否存在"""
        return os.path.exists(path)

    def list_files(self, directory: str, pattern: str = "*") -> list[str]:
        """列出目录下的文件"""
        import glob
        return glob.glob(os.path.join(directory, pattern))
```

#### Git 操作

```python
# tools/git_ops.py
import subprocess

class GitOpsTool:
    def __init__(self, repo_path: str = "."):
        self.repo_path = repo_path

    def _run_git(self, args: list[str]) -> dict:
        """执行 git 命令"""
        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=self.repo_path,
                capture_output=True,
                text=True
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def create_branch(self, branch_name: str) -> dict:
        """创建新分支"""
        return self._run_git(["checkout", "-b", branch_name])

    def switch_branch(self, branch_name: str) -> dict:
        """切换分支"""
        return self._run_git(["checkout", branch_name])

    def merge_branch(self, branch_name: str) -> dict:
        """合并分支"""
        return self._run_git(["merge", branch_name])

    def check_conflicts(self) -> dict:
        """检查是否有合并冲突"""
        result = self._run_git(["diff", "--check"])
        has_conflicts = result["returncode"] != 0
        return {"has_conflicts": has_conflicts, "details": result["stdout"]}

    def status(self) -> dict:
        """查看 Git 状态"""
        return self._run_git(["status", "--short"])
```

## 项目目录结构

```
TeamRun/
├── trun/                       # 主包
│   ├── __init__.py
│   ├── cli.py                  # CLI 入口
│   ├── config.py               # 配置管理
│   ├── todo/
│   │   ├── generator.py        # TODO 生成器
│   │   ├── parser.py           # TODO 解析器
│   │   └── models.py           # TODO 数据模型
│   ├── scheduler/
│   │   ├── scheduler.py        # 流程调度器
│   │   └── state_manager.py    # 状态管理
│   ├── adapters/
│   │   ├── base.py             # 适配器基类
│   │   ├── claude_code.py      # Claude Code 适配器
│   │   ├── codex.py            # Codex 适配器
│   │   └── factory.py          # 适配器工厂
│   ├── tools/
│   │   ├── file_ops.py         # 文件操作工具
│   │   ├── git_ops.py          # Git 操作工具
│   │   ├── shell.py            # Shell 命令工具
│   │   └── web_search.py       # 网络搜索工具
│   ├── llm/
│   │   ├── service_llm.py      # 服务 LLM
│   │   └── sub_agent.py        # 子 Agent
│   └── utils/
│       ├── logger.py           # 日志工具
│       └── env.py              # 环境变量管理
├── tests/                      # 测试
├── pyproject.toml              # 项目配置
├── README.md
└── DESIGN.md                   # 设计文档
```

## 待讨论问题

（暂无）

## 架构增强：验证器与受控重规划

### 设计目标

**主模式**：LLM 规划 + 确定性调度
**增强点**：受控动态重规划（局部） + 强验证器（产物/测试/状态）

### 架构流程图

```
┌─────────────────────────────────────────────────────────────────┐
│                         用户任务                                 │
└─────────────────────────────┬───────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    TodoGenerator (LLM)                          │
│              初始规划 + 验证器配置                               │
└─────────────────────────────┬───────────────────────────────────┘
                              ▼
                    ┌─────────────────┐
                    │   main.todo.md  │  ← 可审计的执行计划
                    └────────┬────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Scheduler                                │
│  ┌────────────────────────────────────────────────────────┐    │
│  │                    执行循环                              │    │
│  │   get_next_step() → execute() → validate() → update()  │    │
│  └───────────────────────────┬────────────────────────────┘    │
│                              │                                  │
│              ┌───────────────┼───────────────┐                 │
│              ▼               ▼               ▼                 │
│      ┌─────────────┐ ┌─────────────┐ ┌─────────────┐          │
│      │  成功 ✓     │ │  失败 ✗     │ │  需审核     │          │
│      │  → 验证     │ │  → 重规划?  │ │  → @human   │          │
│      └──────┬──────┘ └──────┬──────┘ └─────────────┘          │
│             │               │                                   │
│      ┌──────▼──────┐ ┌──────▼────────┐                         │
│      │ StepValidator│ │ ReplanEngine  │                         │
│      │ - file_exists│ │ - 局部重规划  │                         │
│      │ - test_pass  │ │ - 可追溯     │                         │
│      │ - schema     │ │ - 有限次     │                         │
│      │ - llm        │ │ - 可确认     │                         │
│      └──────┬──────┘ └──────┬────────┘                         │
│             │               │                                   │
│             └───────┬───────┘                                   │
│                     ▼                                           │
│            ┌────────────────┐                                   │
│            │  更新 TODO.md  │ ← 记录 [REPLANNED]               │
│            └────────────────┘                                   │
└─────────────────────────────────────────────────────────────────┘
```

### 验证器框架

#### 验证器类型

| 类型 | 说明 | 使用场景 |
|------|------|----------|
| `file_exists` | 验证输出文件存在且非空 | 所有产出文件 |
| `test_pass` | 运行测试命令验证通过 | 代码开发步骤 |
| `schema` | 验证输出符合 JSON Schema | API 设计、配置文件 |
| `llm` | LLM 语义验证 | 文档质量、需求满足度 |
| `custom` | 自定义命令验证 | 特殊场景 |

#### 配置示例

```json
{
  "validators": {
    "auto_file_check": true,
    "auto_completion_marker": true,
    "test_command": "pytest",
    "test_timeout": 300
  }
}
```

#### TODO 文件语法

```markdown
- [ ] #step3 @task(backend) 实现用户认证 API
  - output: auth_api.py
  - validators:
    - file_exists:auth_api.py
    - test_pass:tests/test_auth.py
    - schema:openapi/auth.yaml
```

### 重规划引擎

#### 设计原则

| 原则 | 说明 |
|------|------|
| **局部性** | 只改写失败步骤及其直接后续，不推翻已完成步骤 |
| **可追溯** | 所有重规划记录在 TODO 文件历史中 |
| **有限次** | 同一步骤最多重规划 N 次，防止死循环 |
| **可确认** | 支持人工确认模式，重规划前询问用户 |

#### 重规划策略

```python
class ReplanPolicy(Enum):
    DISABLED = "disabled"   # 禁用重规划
    AUTO = "auto"           # 自动重规划（默认）
    CONFIRM = "confirm"     # 需要人工确认
```

#### 配置示例

```json
{
  "replan": {
    "policy": "auto",
    "max_attempts": 3,
    "scope": "local"
  }
}
```

#### 重规划流程

```
步骤执行失败
     ↓
检查是否可重规划
  - policy != disabled?
  - replan_count < max_attempts?
  - step_type in [TASK, DISCUSS, PARALLEL]?
     ↓
[policy == CONFIRM] → 询问用户确认
     ↓
调用 LLM 生成替代步骤
     ↓
替换失败步骤及其依赖
     ↓
记录重规划历史
     ↓
继续执行
```

#### TODO 文件重规划历史

```markdown
## 重规划历史
- [2024-01-15 10:30:00] step2: 执行失败，缺少数据库配置
  - 新步骤: step2.1, step2.2

## 流程

- [x] #step1 @task(backend) 设计数据模型
- [!] #step2 @task(backend) 实现 API  <!-- FAILED -->
- [ ] #step2.1 @task(backend) 配置数据库连接
  <!-- [REPLANNED] from step2 -->
- [ ] #step2.2 @task(backend) 实现 API
  - depends: step1, step2.1
  <!-- [REPLANNED] from step2 -->
```

### 模块结构

```
trun/
├── validators/                 # 验证器框架
│   ├── __init__.py
│   ├── base.py                 # Validator 基类
│   ├── factory.py              # ValidatorFactory, StepValidator
│   ├── file_validator.py       # FileExistsValidator
│   ├── test_validator.py       # TestPassValidator
│   ├── schema_validator.py     # SchemaValidator
│   └── llm_validator.py        # LLMValidator
├── scheduler/
│   ├── scheduler.py            # 集成验证和重规划
│   ├── replan.py               # ReplanEngine
│   └── state_manager.py
├── todo/
│   ├── models.py               # ValidatorConfig, ReplanRecord
│   ├── parser.py               # 解析 validators 和重规划历史
│   └── generator.py            # 支持重规划生成
└── config.py                   # ReplanConfig, DefaultValidatorConfig
```

### 优势总结

| 考虑因素 | 当前设计 | 完全自主 Agent |
|----------|----------|----------------|
| **可预测性** | ⭐⭐⭐⭐⭐ 高 | ⭐⭐ 低 |
| **可审计性** | ⭐⭐⭐⭐⭐ TODO.md 可读 | ⭐⭐ 依赖日志 |
| **成本控制** | ⭐⭐⭐⭐ LLM 只用于规划 | ⭐⭐ 每步都调用 |
| **断点续做** | ⭐⭐⭐⭐⭐ 原生支持 | ⭐⭐⭐ 需要额外实现 |
| **动态适应** | ⭐⭐⭐⭐ 受控重规划 | ⭐⭐⭐⭐⭐ 灵活 |
| **调试难度** | ⭐⭐⭐⭐ 易调试 | ⭐⭐ 难调试 |
