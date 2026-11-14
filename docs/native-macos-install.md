# 原生 macOS 安装与运维

本安装把 CowAgent 直接运行在当前 macOS 用户下。Agent 使用 `full-access`，可以访问该账户的全部文件和网络资源，请先阅读 `docs/adr/0001-native-full-access-cowagent.md`。

日常登录、对话、模型配置、微信、备份和故障处理见 `docs/native-macos-user-manual.md`。
开发、测试、Git 约束、升级和服务排障见 `docs/native-macos-devops-manual.md`。
产品定位、范围和验收见 `docs/product-document.md`；组件、数据流和安全边界见 `docs/architecture-document.md`。

## 安装

```bash
./scripts/install-native-macos.sh
```

脚本会创建并验证 Python 3.13 venv、Node 24 LTS、ffmpeg、Playwright/Chromium、`~/.cow/config.json`、两个用户级 `launchd` 任务，并等待 `/api/health` 通过。Playwright 浏览器缓存放于 `~/.cow/ms-playwright`。

首次安装会生成 Web 密码并输出到终端。后续重复安装会保留现有密码。需要再次查看时运行：

```bash
jq -r '.web_password' ~/.cow/config.json
```

## 路径

- Web 控制台：`http://127.0.0.1:9899/`
- 配置与微信凭证：`~/.cow`
- Agent 工作区：`~/cow`
- 备份：`~/Backups/CowAgent`
- 日志：`~/Library/Logs/CowAgent`

## 服务管理

```bash
launchctl print gui/$(id -u)/com.steven.cowagent
launchctl kickstart -k gui/$(id -u)/com.steven.cowagent
launchctl bootout gui/$(id -u)/com.steven.cowagent
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.steven.cowagent.plist
```

不要使用 `cow start`、`cow stop` 或控制台的一键更新管理此安装。

## 更新

```bash
./scripts/update-native-macos.sh
```

脚本会停止服务、执行 fast-forward 更新、更新依赖并重启。失败时回到更新前的 commit 并恢复旧版本服务。

## 备份与恢复

每日维护任务在 `03:00` 执行备份和日志轮转。也可以立即运行：

```bash
./scripts/cowagent-maintenance.sh
```

备份不包含 `~/.cow` 中的个人微信登录凭证，恢复后需要重新扫码。

恢复前先停止服务：

```bash
launchctl bootout gui/$(id -u)/com.steven.cowagent
COW_DATA_DIR=~/.cow .venv/bin/cow restore /path/to/cowagent-backup.zip
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.steven.cowagent.plist
```
