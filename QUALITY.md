# 代码质量要求

本项目的安装与运行门槛适用于当前 macOS 用户下的源码安装，不修改系统级 Python。

## 运行时与依赖

- 使用 `uv` 提供的 Python 3.13，并在仓库内创建独立 `.venv`。
- CowAgent、Python 依赖、Playwright/Chromium 与 `cow` CLI 均安装在该 venv 中。
- 不使用 Homebrew Python 3.15、系统级 pip 或 `--break-system-packages`。
