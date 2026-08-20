<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="brand/svg/loopforge-horizontal-dark.svg">
    <img alt="Loopforge" src="brand/svg/loopforge-horizontal-light.svg" width="340">
  </picture>
</p>

# Loopforge

[English](README.md) | [简体中文](README.zh-CN.md)

Loopforge 是一个独立的本地游戏开发 Agent。它使用内部 Skills 和确定性工作流工具，
把游戏想法推进为经过测试、由证据支撑的可玩版本，同时避免将项目状态困在聊天记录中。

Loopforge Agent 是产品控制面。CLI 保留为无头自动化与调试入口，Skills 是随 Agent
版本发布的内部能力，而不是要求用户自行编排的主要产品界面。

## 本地 Agent 工作台

Loopforge 提供一个由 Kura 驱动的本地游戏开发工作台：

- 独立 Loopforge Agent 负责项目上下文、规划、内部 Skills 和确定性工具；
- Kura 只提供通用模型、会话和运行时能力，不包含 Loopforge 领域逻辑；
- Tauri + React 客户端只调用 Loopforge Agent 契约；
- Deckle（`@dopejs/deckle-*`）负责可视化 artifact、画布和 revision；
- Doper（`@dopejs/doper`）负责高性能原生渲染、滚动、编辑和输入；
- `contracts/` 中的版本化 JSON Schema 归 Loopforge 所有，由应用侧 adapter 转换为 Deckle、Doper 和 Kura 的公共契约；公共库不依赖 Loopforge 领域类型。daemon 是运行状态事实源，Loopforge 是游戏项目与证据事实源。

在已初始化的游戏项目中，可以这样启动第一版本地工作台链路：

```bash
loopforge agent start --format json
loopforge agent status --format json
loopforge agent context --format json
```

`agent context` 只返回项目路径、阶段、revision 和能力列表等经过约束的上下文，不会返回环境变量、provider credential 或 access token。

从源码构建桌面客户端时，先初始化固定版本的 Kura submodule。Tauri 只管理 Loopforge Agent sidecar，Agent 在内部管理 Kura：

```bash
git submodule update --init --recursive
cd apps/workbench
pnpm install
pnpm build:desktop
```

发布构建会把独立 Loopforge Agent 和 Kura submodule 中编译出的 `dope-cli` 一起放进 Tauri 应用资源。`dope-cli` 是 Kura 当前上游包名。

在仓库根目录直接启动开发环境：

```bash
./dev.sh
```

首次运行会安装 Workbench 依赖、初始化 Kura submodule，并构建缺失的 Agent 与
Kura sidecar。后续运行会复用 sidecar，启动原生 Tauri 开发壳和 Vite 热更新，
不会生成发布安装包。修改 Agent 或 Kura 后，可分别使用 `--rebuild-agent` 或
`--rebuild-kura`；使用 `--rebuild-sidecars` 可重建两者。只需要浏览器前端时，
仍可在 `apps/workbench` 中使用 `pnpm dev`。

Workbench 中使用原生目录选择器添加游戏项目。选中项目后，Workbench 会自动启动
或重新连接该项目的 Loopforge Agent，不需要手动管理 Agent 的启动。

## Loopforge 提供什么

### 由证据驱动的游戏开发流程

Loopforge 围绕可重复的学习循环组织工作，而不是简单地完成一份功能清单：

```text
游戏想法 -> 可证伪假设 -> 最小可玩实验
         -> 技术检查 -> 真人试玩 -> 保留 / 放弃 / 重构
         -> 有依据地投入游戏设计、美术和垂直切片
```

每个阶段都有明确的交付物和阶段门。原型可以被放弃或重构，而不必把停止一个不成立的方向视为失败。

### 五个生产级 Skills

- `loopforge-router`：读取项目状态，并选择下一项适用的工作流。
- `prototype-gameplay`：将想法转化为有边界的原型、试玩和明确决策。
- `build-godot-game`：实现并验证一个小型 Godot 4 核心玩法循环。
- `design-game`：为保留的原型交付完整的用户可读游戏策划文档（GDD）、同步的范围契约和基于证据的审查结果。
- `direct-game-art`：定义美术方向、代表性目标、资产清单、来源记录和运行时视觉审查。

### 确定性的项目 CLI

`loopforge` CLI 将项目状态保存在 `.loopforge` 中，并提供：

- 哈希链事件、文件锁、状态快照和恢复检查；
- 假设记录、阶段门以及原子化的保留、放弃和重构决策；
- 带结构化运行证据的 Godot 构建和测试命令；
- 带校验和与源码身份追踪的证据登记；
- 适合智能体自动化的 `status`、`doctor`、`validate` 和 JSON 输出。

### 面向生产工作的保护机制

Loopforge 将技术正确性、视觉质量、试玩观察和玩法乐趣的证据分开处理。
它会拒绝不安全的状态推进、检测过期产物、在更新时保护本地 Skill 修改，
并将创意判断和发布相关决策保留给人类审查者。

### 当前范围

项目目前处于 alpha 阶段。独立 Agent、CLI、工作流契约和仓库 Skills 已经实现并经过测试，
当前引擎工作流聚焦于 Godot 4。完整的真实引擎验证、更广泛的引擎适配、
托管式协作以及发布生产自动化尚未包含在 MVP 中。

## 安装

### 前置条件

- Python 3.11 或更高版本；
- [uv](https://docs.astral.sh/uv/getting-started/installation/)；
- Git；
- 仅在使用 Godot 构建工作流时需要 Godot 4。

### 安装 Loopforge

```bash
uv tool install git+https://github.com/dopejs/loopforge.git
loopforge setup --host codex
```

安装包包含所有官方 Loopforge Skills。`loopforge setup` 会将它们复制到共享的
Agent Skills 目录 `~/.agents/skills`。该命令可以安全地重复执行：未变化的 Skill
会被跳过，更新只会应用到由 Loopforge 管理的安装。

在游戏仓库根目录运行以下命令完成初始化：

```bash
loopforge inspect --format json
loopforge init --format json
loopforge doctor --format json
loopforge status --format json
```

然后在 Codex 中调用 `$loopforge-router`。它会读取持久化的项目状态，
并将下一步工作路由到玩法原型、Godot 实现、游戏设计或美术制作。

### 更新

```bash
uv tool install --force git+https://github.com/dopejs/loopforge.git
loopforge setup --host codex
```

在修改文件之前，可以先查看更新计划：

```bash
loopforge setup --host codex --dry-run
```

Loopforge 不会覆盖包含本地修改的 Skill，也不会覆盖同名但未由 Loopforge 管理的
Skill。审查冲突后，可以使用 `--force`；安装器会先把现有目录保存为带时间戳的
备份，再安装随包发布的版本。

如需可复现的环境，请在 Git URL 后附加经过审查的 tag 或 commit，例如：
`git+https://github.com/dopejs/loopforge.git@<commit>`。

### 卸载

先移除由 Loopforge 管理的 Skills，再卸载 CLI：

```bash
loopforge setup --host codex --uninstall
uv tool uninstall loopforge
```

卸载同样不会删除包含本地修改的 Skill。使用 `--force` 时，修改过的 Skill
会被移动到带时间戳的备份，而不是直接删除。卸载 CLI 和 Skills 不会移除项目自身的
`.loopforge` 历史或证据。

### 从源码开发

只有在开发 Loopforge 或修改其 Skills 时才需要克隆仓库：

```bash
git clone https://github.com/dopejs/loopforge.git
cd loopforge
uv sync --locked
uv run loopforge --help
uv run python -m unittest discover -s tests -v
```

如需在不替换个人安装的情况下测试仓库 Skills，可以指定临时目录：

```bash
uv run loopforge setup --skills-root /tmp/loopforge-skills
```

该包尚未发布到 PyPI，因此不要假设 `uv tool install loopforge` 指向本项目。

## 产品原则

- 优先验证游戏想法是否成立，而不是只追求完成功能清单。
- 将创意判断保留在 Skills 和人类审查中。
- 将状态推进、验证、证据和恢复交给 CLI。
- 使用现有编码智能体，而不是构建专有智能体运行时。
- 让每次有意义的迭代都可玩或可检查。
- 明确区分技术正确性、视觉质量、真人试玩和玩法乐趣证据。

## 文档

- [产品设计](docs/product.md)
- [系统架构](docs/architecture.md)
- [开发工作流](docs/workflow.md)
- [阶段与阶段门契约](docs/gates.md)
- [CLI 设计](docs/cli.md)
- [Skill 系统](docs/skills.md)
- [仓库 Skills](skills/README.md)
- [参考研究](docs/research.md)
- [路线图](docs/planning/roadmap.md)
- [MVP 计划](docs/planning/mvp.md)
- [开放问题](docs/planning/open-questions.md)
- [ADR 0001：产品形态](docs/decisions/0001-product-shape.md)
- [ADR 0002：质量声明](docs/decisions/0002-quality-claims.md)
- [ADR 0003：状态事务与恢复](docs/decisions/0003-state-transactions-and-recovery.md)
- [ADR 0004：证据与声明](docs/decisions/0004-evidence-identity-and-claims.md)
- [ADR 0005：CLI 语言](docs/decisions/0005-cli-language.md)

## 工作定义

> Loopforge 帮助现有编码智能体持续地将游戏想法转化为可玩的实验，收集证据，
> 并明确做出保留、放弃或重构决策。
