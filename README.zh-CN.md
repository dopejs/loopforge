<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="brand/svg/loopforge-horizontal-dark.svg">
    <img alt="Loopforge" src="brand/svg/loopforge-horizontal-light.svg" width="340">
  </picture>
</p>

# Loopforge

[English](README.md) | [简体中文](README.zh-CN.md)

Loopforge 是一个独立运行在本地的游戏开发 Agent。它在普通游戏仓库中工作，将想法
推进为可玩实验，收集技术证据与真人反馈，并帮助团队明确做出保留、放弃或重构决策。

Loopforge Agent 是产品控制面，桌面 Workbench 是主要用户界面。CLI 和版本化 Skills
保留为 Agent 内部执行、自动化和调试能力；用户不需要手动启动 Agent，也不需要自行
编排这些内部能力。

## 产品形态

Workbench 通过原生目录选择器把一个游戏仓库添加为项目。选择项目后，它会自动启动
或重新连接该项目的 Loopforge Agent，并加载经过约束的项目上下文，不暴露 provider
credential、环境变量或 access token。

界面围绕项目和开发工作组织，而不是围绕 Agent 进程组织：

- 左侧项目主菜单用于切换仓库和项目级视图；
- 项目 Header 展示项目身份和必要操作；
- 主工作区承载各模式下的游戏开发工具；
- 浮动模式工具栏在探索、设计、构建和测试上下文之间切换；
- Agent Chat 常驻在工作区一侧，但不会代替实际工作区。

项目状态和证据保存在游戏仓库中，聊天记录不是工作过程的唯一记录。

## 架构与权责

```text
用户
  |
  v
Workbench（Tauri + React）
  |-- 打开项目，呈现工具、证据和 Chat
  |-- 只负责 Loopforge Agent sidecar 的生命周期
  v
Loopforge Agent
  |-- 负责项目上下文、规划、会话和工具选择
  |-- 调用内部 Skills 与确定性操作
  v
Loopforge core + CLI adapter ----> 游戏仓库 + .loopforge 状态
  |
  `----> Kura 通用模型、会话和运行时能力
```

各层边界是明确的：

- `apps/agent` 包含 Loopforge 领域 Agent 和用户可见行为。
- `apps/workbench` 包含桌面产品界面及其收敛的原生边界。
- `cli` 包含确定性项目操作，以及无头兼容和诊断 adapter；它不是产品控制面。
- `skills` 包含需要上下文判断的版本化 Agent 工作流能力；它们不是主要用户界面。
- `contracts` 包含 Loopforge 自己拥有的版本化通信与项目 Schema。
- Kura 只提供通用模型、会话和运行时能力，不包含 Loopforge route、类型、文件或领域状态。
- Deckle 和 Doper 是负责可视化 artifact 与原生渲染的公共库；Loopforge 专属行为应放在
  应用侧 adapter 中，而不是写入这些公共库。

发布应用会内嵌 Loopforge Agent 和固定版本的 Kura sidecar。Workbench 只调用
Loopforge Agent 契约，不会直接调用 Kura 或启动工作流命令。

## 仓库结构

```text
loopforge/
├── apps/
│   ├── agent/                 # 独立 Loopforge Agent
│   └── workbench/             # Tauri + React 桌面应用
│       └── vendor/kura/       # 固定版本的通用运行时 submodule
├── cli/                       # 确定性 core 与无头 adapter
├── contracts/                 # Loopforge 自有版本化 Schema
├── skills/                    # Agent 内部工作流能力
├── tests/                     # Agent、CLI 和 Skill 测试
├── docs/                      # 产品、架构和决策文档
└── dev.sh                     # 根目录开发启动脚本
```

## 开发 Workbench

前置条件：

- Git；
- Node.js 22 和 pnpm；
- Rust 和 Cargo；
- Python 3.11+ 和 [uv](https://docs.astral.sh/uv/)；
- 仅在开发或测试 Godot 工作流时需要 Godot 4。

在仓库根目录启动完整的原生开发环境：

```bash
git clone https://github.com/dopejs/loopforge.git
cd loopforge
./dev.sh
```

首次运行时，启动脚本会初始化固定版本的 Kura submodule、安装 Workbench 依赖，并
构建缺失的 Agent 与 Kura sidecar。后续运行会复用 sidecar，通过 Vite 热更新启动
原生 Tauri 应用。

React 和 CSS 修改无需重新生成发布包即可更新。Rust 或原生配置修改会重启 Tauri
开发进程。只有对应 sidecar 代码变化时才需要重建：

```bash
./dev.sh --rebuild-agent
./dev.sh --rebuild-kura
./dev.sh --rebuild-sidecars
```

只进行浏览器前端开发时：

```bash
cd apps/workbench
pnpm dev
```

构建发布版桌面应用及其内嵌 sidecar：

```bash
git submodule update --init --recursive
cd apps/workbench
pnpm install --frozen-lockfile
pnpm build:desktop
```

## 内部 CLI 与 Skills

Python package 用于开发确定性操作、运行无头自动化和诊断项目状态。使用已打包的
Workbench 发布版不需要单独安装它。

```bash
uv sync --locked
uv run loopforge --help
uv run loopforge inspect --format json
uv run loopforge doctor --format json
uv run python -m unittest discover -s tests -v
```

Package 同时包含官方 Loopforge Skills。开发者测试 Skill 安装时可以使用隔离目录：

```bash
uv run loopforge setup --skills-root /tmp/loopforge-skills
```

该 package 尚未发布到 PyPI，请不要假设 `uv tool install loopforge` 指向本仓库。

## 证据驱动的工作流

Loopforge 围绕一个可重复的学习循环组织游戏开发：

```text
游戏想法 -> 可证伪假设 -> 最小可玩实验
         -> 技术检查 -> 真人试玩 -> 保留 / 放弃 / 重构
         -> 有依据地投入游戏设计、美术和垂直切片
```

当前内部工作流能力覆盖任务路由、玩法原型、Godot 4 实现、游戏设计和美术指导。
确定性 core 在 `.loopforge` 中记录哈希链事件、阶段推进、构建与测试证据、试玩记录
以及恢复状态。

技术正确性、视觉质量、试玩观察和玩法乐趣证据始终是不同的质量声明。创意、试玩、
范围和发布相关决策仍由人类审查者负责。

## 当前范围

Loopforge 目前处于 alpha 阶段。独立 Agent、Workbench shell、确定性 core、CLI
adapter、工作流契约和仓库 Skills 已经实现并经过测试。当前引擎工作流聚焦于
Godot 4。Workbench 各模式的完整工具、更广泛的引擎 adapter、托管式协作和发布
生产自动化仍在开发中。

## 产品原则

- 以独立 Agent 作为产品控制面，以 Workbench 作为主要用户体验。
- 将 CLI 和 Skills 保留在 Agent 边界之后，而不是要求用户自行编排。
- 优先验证游戏想法是否成立，而不是只追求完成功能清单。
- 让状态推进、证据、验证和恢复保持确定性且可检查。
- 不把 Loopforge 领域行为写入通用公共库。
- 让每次有意义的迭代都可玩或可检查。
- 保留人类对创意方向、试玩解释、范围和发布决策的最终权责。

## 文档

- [产品设计](docs/product.md)
- [系统架构](docs/architecture.md)
- [开发工作流](docs/workflow.md)
- [阶段与阶段门契约](docs/gates.md)
- [CLI 设计](docs/cli.md)
- [Skill 系统](docs/skills.md)
- [仓库 Skills](skills/README.md)
- [路线图](docs/planning/roadmap.md)
- [MVP 计划](docs/planning/mvp.md)
- [开放问题](docs/planning/open-questions.md)
- [架构决策](docs/decisions/)

## 许可证

Copyright 2026 Loopforge contributors。本项目采用
[Apache License 2.0](LICENSE) 许可证。
