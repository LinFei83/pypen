<!--
Sync Impact Report
- Version change: (unfilled template) → 1.0.0
- Modified principles: N/A (initial ratification from template placeholders)
- Added principles:
  I. 技术栈与目录结构保留
  II. 需求驱动的最小变更
  III. 命名与编码规范一致性
  IV. 公共 API 向后兼容
  V. 新增功能必须可测
  VI. 使用既有工具链
  VII. 密钥与配置外置
  VIII. 实现前先阅读相似模块
- Added sections: 技术基线, 开发工作流, Governance
- Removed sections: N/A
- Templates requiring updates:
  ✅ .specify/templates/plan-template.md
  ✅ .specify/templates/spec-template.md
  ✅ .specify/templates/tasks-template.md
  ✅ .specify/templates/constitution-template.md (unchanged source; memory filled)
- Spec Kit skills: reviewed; generic constitution references remain valid
- Follow-up TODOs: 仓库尚无 pytest/格式化配置；引入测试工具时须更新本文件「技术基线」与 plan 模板 Testing 字段
-->

# Pypen Constitution

## Core Principles

### I. 技术栈与目录结构保留

本仓库已投入开发。所有变更 MUST 保留并延续当前技术栈与顶层目录职责，除非需求明确要求迁移且经 Constitution 修订批准。

当前不可随意替换的基线包括：Python 3.11+、Quart + Uvicorn + python-socket.io、s6-overlay 进程监督、Docker 单容器部署、`project.toml` 配置模型，以及顶层包布局 `app/`（仪表盘与 API）、`worker/`（项目克隆/venv/s6）、`ping/`（保活）、根入口脚本（`start.py`、`run.py`、`update.py`）。

**理由**：随意换栈或重划目录会破坏已有部署与运维约定，放大回归面。

### II. 需求驱动的最小变更

实现 MUST 仅覆盖当前规格/任务所需范围。禁止与需求无关的大范围重构、批量重命名、风格“净化”式改写，或顺手重写无关模块。

若发现技术债，MUST 单独立规格或任务处理，不得混入功能交付。

**理由**：最小变更降低审查与回滚成本，保证功能交付可验证。

### III. 命名与编码规范一致性

新代码 MUST 遵循仓库既有约定，并与相邻模块风格对齐：

- 模块/函数/变量：`snake_case`；私有辅助以 `_` 前缀
- 常量：`UPPER_SNAKE_CASE`（见 `worker/constants.py`）
- 包内相对导入与 `from __future__ import annotations`（新模块优先采用）
- 异步边界清晰：I/O 密集路径使用 `async`/`await`，阻塞调用经 executor 隔离
- 日志统一经 `app.utils.logging_config` 的 loguru `logger`，禁止另起互不兼容的日志体系

**理由**：一致风格降低认知负担，便于在 `app`/`worker`/`ping` 之间复用模式。

### IV. 公共 API 向后兼容

修改以下对外契约时 MUST 保持向后兼容，或提供明确的迁移路径与版本说明后再做破坏性变更：

- HTTP 路由与响应形状（`app/routes/routes.py` 中 `/service/*`、`/login` 等）
- Socket.IO 事件名与载荷
- `project.toml` 字段语义与 `[defaults]` / `[[project]]` 结构
- 可被其他模块导入的公共函数签名（如 `worker.config_loader`、`worker.s6_svc`）

破坏性变更 MUST 在规格中标注，并优先采用加字段、保留别名、默认值兼容等策略。

**理由**：仪表盘、外部脚本与已有 `project.toml` 部署依赖稳定契约。

### V. 新增功能必须可测

每个新增功能或可观察行为变更 MUST 附带对应自动化测试（单元、集成或契约测试，按风险选型）。测试 MUST 能独立失败以证明覆盖目标行为。

当前仓库测试基线尚薄；引入测试时 MUST 优先覆盖公共 API、配置解析与进程控制边界。禁止以“暂无测试基建”为由跳过本原则——必要时先补最小可运行的测试脚手架再交付功能。

**理由**：回归保护对多进程监督与配置驱动系统尤为关键。

### VI. 使用既有工具链

验证、依赖安装与构建 MUST 使用仓库已有命令与文件，不得另起平行工具链：

- 依赖：`requirements.txt` + 镜像内 `uv pip install`（见 `Dockerfile`）
- 运行：`python3 start.py`（或文档/脚本已记载的等价入口）
- 镜像：基于现有 `Dockerfile` / `heroku.yml`
- 测试/格式化：一旦仓库加入正式命令（如 `pytest`、`ruff`），后续工作 MUST 使用那些命令；在未加入前，新增测试 MUST 采用可被后续统一命令发现的布局（建议 `tests/`）

禁止为单次任务引入未经规格批准的替代构建或质量门禁体系。

**理由**：统一工具链保证 CI、本地与容器行为一致。

### VII. 密钥与配置外置

代码中 MUST NOT 硬编码密钥、口令、访问令牌或部署专用环境值。敏感与环境相关配置 MUST 来自：

- `project.toml`（及 `project.toml.example` 中的占位说明）
- 进程环境变量（如 `PORT`、`APP_URL`、`PING_INTERVAL` 等既有变量）

示例与文档可用占位符（如 `change-me`、`ghp_xxx`）；可执行路径 MUST 从配置或环境读取。发现内嵌凭据 MUST 在触及该区域时改为外置，不得扩大硬编码面。

**理由**：硬编码凭据会造成泄露与环境不可移植。

### VIII. 实现前先阅读相似模块

在编写或修改功能前，实现者 MUST 先阅读仓库中职责最接近的现有模块，并复用其模式（错误处理、s6 封装、配置合并、日志、异步边界），而不是平行发明第二套抽象。

优先对照示例：`worker/config_loader.py`、`worker/s6_svc.py`、`worker/project_manager.py`、`app/routes/routes.py`、`ping/services/pinger.py`。

**理由**：先读后写可减少重复实现与行为漂移。

## 技术基线

| 层级 | 约定 |
|------|------|
| 语言 | Python 3.11+（`from __future__ import annotations`、现代类型标注） |
| Web | Quart 异步应用 + Uvicorn ASGI；Socket.IO 经 `socketio.ASGIApp` |
| 进程 | s6-overlay；业务封装在 `worker/s6_svc.py` 与路由层辅助函数 |
| 配置 | 根目录 `project.toml`；加载逻辑在 `worker/config_loader.py` |
| 日志 | loguru，经 `setup_logging` 统一初始化 |
| 部署 | Docker 单容器；入口 `start.py` 拉起 update / uvicorn / s6 / worker / ping |
| 目录 | `app/`、`worker/`、`ping/`、根脚本；静态资源在 `app/static`、`app/templates` |

偏离上表 MUST 在实现计划的 Constitution Check 中显式记录并说明理由。

## 开发工作流

1. 变更前阅读 Constitution 与最接近的现有模块（原则 VIII）。
2. 规格与计划 MUST 通过 Constitution Check；违规项要么消除，要么记入 Complexity Tracking 并论证。
3. 实现保持最小 diff（原则 II），对齐命名与结构（原则 I、III）。
4. 涉及公共契约时验证兼容性（原则 IV）。
5. 交付前补齐测试并用既有工具链验证（原则 V、VI）。
6. 审查配置与密钥是否外置（原则 VII）。

## Governance

本 Constitution 对规格、计划、任务与实现具有最高约束力；与之冲突的惯例或临时约定无效，除非按下列程序修订本文。

- **修订**：任何原则增删或 MUST 语义变更 MUST 更新本文、递增版本，并同步
  `.specify/templates/` 中受影响的模板（至少 `plan-template.md`、`tasks-template.md`、
  `spec-template.md`）。
- **版本**：遵循语义化版本——MAJOR（原则删除/不兼容重定义）、MINOR（新增原则或实质性扩展）、
  PATCH（澄清、措辞、笔误）。
- **合规**：`/speckit-plan`、`/speckit-tasks`、`/speckit-implement`、`/speckit-analyze`、
  `/speckit-converge` 执行时 MUST 加载本文；违反 MUST 的项视为 CRITICAL，不得静默忽略。
- **运行时指引**：业务上下文见根目录 `README.md`；功能语义图见 `.codesee/features.json`（若存在）。

**Version**: 1.0.0 | **Ratified**: 2026-07-27 | **Last Amended**: 2026-07-27
