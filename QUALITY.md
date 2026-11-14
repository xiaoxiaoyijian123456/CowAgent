# 代码质量要求

本项目的安装与运行门槛适用于当前 macOS 用户下的源码安装，不修改系统级 Python。

## 运行时与依赖

- 使用 `uv` 提供的 Python 3.13，并在仓库内创建独立 `.venv`。
- CowAgent、Python 依赖、Playwright/Chromium 与 `cow` CLI 均安装在该 venv 中。
- ffmpeg 由 Homebrew 安装，供语音格式转换等音频能力使用；Playwright 浏览器缓存放于 `~/.cow/ms-playwright`。
- 不使用 Homebrew Python 3.15、系统级 pip 或 `--break-system-packages`。
- 核心依赖和除讯飞星火固定项外的全部可选依赖均安装；不得降级 `websocket-client` 到 1.2.0。
- 不在源码、launchd plist 或其他交付文件中写入模型 API Key；模型凭据只由 Web 控制台写入 `~/.cow/config.json`。
- 使用 `fnm` 提供的 Node 24 LTS 作为 CowAgent 专用运行时；不修改 Homebrew Node 26 的全局默认版本。
- 每日通过 `launchd` 执行 `cow backup`，归档写入 `~/Backups/CowAgent/`，仅当前用户可访问，并保留最近 7 份。
- 新增 `COW_NO_OPEN_BROWSER=1` 开关并在服务环境启用，避免 `launchd` 启动或重启时自动弹出浏览器。

## 交付与验证

- 安装、更新、维护脚本必须可重复执行；重复运行时不得覆盖已有配置、凭证或用户数据。
- Git 提交必须通过大文件钩子和 CI 检查；不得提交 Playwright、虚拟环境、`node_modules`、浏览器配置或其他运行时缓存。
- 脚本不得把 API Key、Web 密码或微信凭证写入终端日志、仓库或 launchd plist。
- 更新失败时必须回到升级前 commit 并恢复旧版本服务，用户数据目录保持不变。
- 每日维护任务在备份前轮转日志：单文件超过 20 MB 时压缩归档，保留最近 5 份。
- 交付前检查 shell 语法、Python 导入、`launchd` 加载状态、`/api/health`、密码登录和一次服务重启。
- 交付前完成浏览器无头页面加载、Node 24 `node`/`npx`、备份归档权限与保留策略检查。
- 微信扫码登录和真实对话、模型真实对话由使用者在安装完成后完成；若未完成，必须明确列为待验收项。

## 服务与数据

- 使用当前用户的 `launchd` LaunchAgent 运行 `app.py`，启用 `RunAtLoad` 与 `KeepAlive`。
- 服务环境固定使用 `COW_DATA_DIR=~/.cow`、`agent_workspace=~/cow` 和 `COW_DEPLOYMENT=managed`。
- `~/.cow/config.json` 与微信凭证必须仅允许当前用户读写。
- Web 控制台必须显式绑定 `127.0.0.1:9899` 并设置 `web_password`。
- 升级只通过项目内更新脚本执行；不使用控制台的 Web 一键更新。
