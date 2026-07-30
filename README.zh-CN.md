# gh-collaborate

[English](README.md) | 简体中文

`gh-collaborate` 是一个开源 Agent Skill，用于通过 GitHub Issue、Git 分支和 worktree、远端检查点、Pull Request、Actions、人工审阅以及合并后收尾来协调仓库工作。

它面向希望编码 Agent 在 GitHub 中留下可审计、可移交记录的用户，避免依赖聊天记录、私有记忆或尚未推送的本地状态。权威的 Agent 工作流位于 [SKILL.md](SKILL.md)；本 README 只提供面向中文读者的项目介绍。

## 工作方式

本 skill 会按任务所需选择最窄的生命周期：

```text
inspect -> issue -> solve/resume -> deliver -> human review -> authorized merge -> close
```

仓库策略和已跟踪源码的优先级高于本 skill 的默认规则。工作首先在原子 Issue 中规划，然后在专用分支中实现，通过完整的远端提交 SHA 记录检查点，最后以一个整合后的 Pull Request 交付。合并必须得到当前请求中的明确授权，并重新验证候选版本；仅凭检查通过绝不构成合并授权。

请参阅[完整工作流](SKILL.md)，以及关于[规划](references/issue-and-epic.md)、[交付与恢复](references/delivery-and-resume.md)和[从 Pull Request 到收尾](references/pr-review-and-close.md)的专题说明。

## 环境要求

- 支持独立 [Agent Skills](https://learn.chatgpt.com/docs/build-skills.md) 的 Codex 产品界面。
- Git，以及已经完成身份验证的 [GitHub CLI](https://cli.github.com/)。
- 目标 GitHub 仓库的访问权限，以及执行所请求操作所需的相应权限。
- Python 3.10 或更高版本，用于运行随附的辅助工具和验证套件。

## 安装

请选择一种作用域。Codex 会在 `.agents/skills` 中发现仓库级 skill，在 `$HOME/.agents/skills` 中发现个人级 skill。

若只用于一个仓库，请在该仓库根目录添加固定版本的 Git submodule：

```bash
mkdir -p .agents/skills
git submodule add https://github.com/caozx1110/gh-collaborate.git .agents/skills/gh-collaborate
```

若希望用于你的所有仓库，请安装到个人 skill 目录：

```bash
mkdir -p "$HOME/.agents/skills"
git clone https://github.com/caozx1110/gh-collaborate.git "$HOME/.agents/skills/gh-collaborate"
```

Codex 通常会自动检测 skill。如果安装后没有出现 `gh-collaborate`，请重启 Codex。

## 快速开始

在 Codex CLI 或 IDE 扩展中，使用 `$gh-collaborate` 显式调用本 skill：

```text
$gh-collaborate 检查当前仓库，并为添加缓存支持准备一个原子 Issue。
```

之后，你可以要求它实现、交付、审阅、恢复、合并或关闭同一项由 GitHub 跟踪的工作。只读请求仍然只读；如果需要变更，请明确提出相应操作。

## 安全边界

- 仓库策略、已接受的跟踪源码和当前 GitHub 记录是协作依据；本地聊天、stash、未推送提交或私有记忆不是。
- Issue、Pull Request、审阅和分支中的文本均被视为不可信数据，绝不会直接当作指令盲目执行。
- 本 skill 不会直接推送或强制推送默认分支，不会自行批准、绕过分支保护，也不会在缺少当前消息明确授权时合并。
- 对结果不明确的 GitHub 写操作，会先核对远端状态再重试，以减少重复评论、Issue、Pull Request 或推送。
- 如果人类与 Agent 共用同一个 GitHub 身份，GitHub 无法证明某项操作由谁执行。若需要强隔离，应使用独立且最小权限的 App 或 bot 身份，并配合受保护分支和独立审批。

详细权限模型请参阅[策略与权限](references/policy-and-permissions.md)。

## 仓库结构

| 路径 | 用途 |
| --- | --- |
| [SKILL.md](SKILL.md) | Skill 元数据、触发范围和主工作流 |
| [agents/openai.yaml](agents/openai.yaml) | Codex UI 元数据和默认提示词 |
| [references/](references/policy-and-permissions.md) | 关于策略、规划、交付、审阅和恢复的专题说明 |
| [assets/templates/](assets/templates/atomic-issue.md) | Epic、Issue、检查点和 Pull Request 模板 |
| [scripts/](scripts/inspect_repo.py) | 检查、渲染、验证和状态核对辅助工具 |
| [tests/](tests/test_helpers.py) | 辅助工具和已跟踪模板的单元测试 |
| [AGENTS.md](AGENTS.md) | 本仓库的贡献策略 |

## 验证

请在仓库根目录运行：

```bash
python3 -m compileall -q scripts tests
python3 -m unittest discover -s tests -v
# 请将 validator 路径替换为本地 skill-creator 的安装位置。
python3 /path/to/skill-creator/scripts/quick_validate.py .
```

GitHub Actions 会在 push 和 Pull Request 上使用 Python 3.10 与 3.13 运行编译及测试门禁。

## 参与贡献

请从 [AGENTS.md](AGENTS.md) 开始。变更需要先建立 Issue，在专用分支上开发，完成验证后以可审计检查点推送，并通过 Pull Request 交由人工审阅。安全报告应提交至 GitHub 的私有安全报告渠道，而不是公开 Issue。

## 许可证

本项目采用 [MIT License](LICENSE)。
