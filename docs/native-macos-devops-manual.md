# CowAgent 原生 macOS 开发运维手册

> 适用对象：维护当前 fork、修改代码、执行安装升级、排查服务故障的开发者与运维人员。
>
> 最终用户的日常使用说明见 `docs/native-macos-user-manual.md`；安装步骤摘要见 `docs/native-macos-install.md`。

## 1. 环境与架构

当前部署采用“源码仓库 + 用户级 `launchd` + 本机 venv”的原生模式，不使用 Docker 或 Kubernetes。

| 组件 | 路径或标识 | 说明 |
| --- | --- | --- |
| 源码仓库 | `/Users/steven/CowAgent` | Git 工作区与所有脚本 |
| Python | `.venv/bin/python` | Python 3.13，由 `uv` 管理 |
| Node | fnm 下的 Node 24 LTS | 仅供 CowAgent 和浏览器相关工具使用 |
| 数据根 | `~/.cow` | 配置、密钥、微信凭证、Playwright 缓存 |
| Agent 工作区 | `~/cow` | 记忆、知识、技能、会话产物 |
| 服务 | `com.steven.cowagent` | 主 CowAgent LaunchAgent |
| 备份任务 | `com.steven.cowagent.backup` | 每日 `03:00` 维护任务 |
| 备份目录 | `~/Backups/CowAgent` | 最近 7 份 ZIP |
| 日志目录 | `~/Library/Logs/CowAgent` | 服务、错误和维护日志 |
| Web | `127.0.0.1:9899` | 仅本机监听，使用密码登录 |

关键环境变量由 `scripts/native-macos-common.sh` 统一设置：

```text
COW_DATA_DIR=~/.cow
COW_DEPLOYMENT=managed
COW_NO_OPEN_BROWSER=1
```

Node 的 `PATH` 由 fnm 安装目录动态拼入，不修改 Homebrew Node 的全局默认版本。

## 2. 开发环境

### 2.1 前提工具

```bash
command -v git uv fnm brew curl ffmpeg
```

首次完整安装或修复运行时：

```bash
cd /Users/steven/CowAgent
bash scripts/install-native-macos.sh
```

安装脚本会校验 Python 3.13、安装依赖、安装 Node 24、确保 ffmpeg、安装 Playwright、刷新配置并重启两个 LaunchAgent。

### 2.2 使用 venv

```bash
cd /Users/steven/CowAgent
source .venv/bin/activate
python --version
python -c 'import cli; print("venv ok")'
```

当前项目已安装为 editable 包。需要新增开发依赖时，优先装进仓库内 `.venv`，不要修改系统 Python，也不要使用 `--break-system-packages`。

```bash
UV_CACHE_DIR=/tmp/cowagent-uv-cache uv pip install --python .venv/bin/python pytest ruff
```

### 2.3 检查 Node 运行时

```bash
cd /Users/steven/CowAgent
bash -c 'source scripts/native-macos-common.sh; setup_runtime_env; node --version; npx --version'
```

预期看到 `v24.x` 和对应的 `npx` 版本。不要用系统或 Homebrew 全局 Node 覆盖它。

### 2.4 配置生成

`scripts/bootstrap_native_config.py` 是幂等的：已有配置不会被覆盖，只补齐缺失字段、监听地址、Agent 默认值和 Web 密码。

```bash
COW_DATA_DIR="$HOME/.cow" .venv/bin/python scripts/bootstrap_native_config.py
```

该脚本不得写入模型 API Key。模型和微信凭证由用户在 Web 控制台录入。

## 3. Git 工作流与提交约束

### 3.1 每个克隆启用一次钩子

```bash
cd /Users/steven/CowAgent
bash scripts/install-git-hooks.sh
git config --local --get core.hooksPath
```

预期输出 `.githooks`。

### 3.2 强制限制

| 限制 | 阈值 |
| --- | --- |
| 单文件 | `20 MB` |
| 单次暂存内容 | `50 MB` |
| 单次推送新增对象 | `100 MB` |
| 禁止路径 | `ms-playwright`、`.venv`、`node_modules`、浏览器 profile、Playwright 和测试报告 |
| 禁止下载二进制目录 | `desktop/resources/bin` |

约束由三层执行：

1. `.githooks/pre-commit` 检查暂存区。
2. `.githooks/pre-push` 检查待推送范围中的全部新增对象，包括“先添加、后删除”的大文件。
3. `.github/workflows/git-hygiene.yml` 在 GitHub 上检查新增历史对象。

不要使用 `git push --no-verify` 绕过检查。即使本地绕过，CI 仍会检查；超过 GitHub 100 MB 文件限制时，推送会在服务端直接被拒绝。

### 3.3 提交前检查

```bash
git status
git diff --cached --stat
python3 scripts/check_git_file_sizes.py staged
git diff --check
```

只暂存本次任务需要的文件，禁止无检查地使用 `git add -A` 或 `git add .`。提交信息使用英文、简短、祈使句，例如：

```text
feat: add native macOS deployment and user manual
fix: retry launchd bootstrap after unload
docs: clarify backup restore steps
```

不要把 API Key、Web 密码、微信凭证、数据库、日志、构建产物或浏览器缓存提交进仓库。

### 3.4 推送前检查

```bash
git diff --stat origin/dev...HEAD
git log --oneline origin/dev..HEAD
python3 scripts/check_git_file_sizes.py range origin/dev HEAD
```

然后正常推送：

```bash
git push origin dev
```

CI 分工：`git-hygiene.yml` 对所有 push/PR 运行；`test.yml` 在 master push 和 PR 上运行完整测试。向 `dev` 推送不会自动跑完整测试，因此必须在本地先运行测试。

### 3.5 大文件已经进入历史时

只在确认以下条件后重写历史：

- 大文件只存在于尚未推送到远端的本地提交。
- 当前分支没有其他人正在基于这些提交工作。
- 已创建本地备份分支。

示例：

```bash
git branch backup/dev-large-history-$(date +%Y%m%d-%H%M%S)
git fetch origin
git log --oneline origin/dev..HEAD
git reset --soft origin/dev
git status
git add path1 path2  # only reviewed paths needed for the clean commit
git diff --cached --name-status
git commit -m "feat: add native macOS deployment and user manual"
git log --oneline origin/dev..HEAD
if git rev-list --objects origin/dev..HEAD | rg 'ms-playwright'; then
  echo "ERROR: browser cache remains in history" >&2
  exit 1
fi
remote_sha=$(git rev-parse origin/dev)
git push --force-with-lease="dev:${remote_sha}" origin dev:dev
```

要点：

- 在后续提交中删除大文件不会把 blob 从历史移除。
- 不要用 Git LFS 保存浏览器缓存或虚拟环境。
- `--force-with-lease` 用来确认远端没有出现意外更新；不要对共享的 master/main 历史做无保护强推。
- 如果不是个人分支，先创建干净分支并通过 PR 合并，而不是直接改写共享分支。
- 如果大文件已经成功推送到共享远端，不要单方面强推；应由维护者协调历史清理，涉及密钥时立即轮换。

## 4. 测试与质量门禁

### 4.1 快速定向测试

```bash
cd /Users/steven/CowAgent
.venv/bin/python -m pytest tests/test_git_file_size_guard.py -q
.venv/bin/python -m pytest tests/test_web_browser_auto_open.py -q
```

### 4.2 全量后端测试

```bash
.venv/bin/python -m pytest tests/ -q
```

完整测试可能耗时较长。改动 Python 后端、Agent 工具、通道或配置逻辑时必须运行；只改文档时可运行定向检查。

### 4.3 静态检查

```bash
bash -n scripts/*.sh .githooks/pre-commit .githooks/pre-push
.venv/bin/python -m py_compile scripts/bootstrap_native_config.py scripts/native_maintenance.py
plutil -lint scripts/launchd/*.template
git diff --check
```

CI 的 ruff 门禁只检查变更的 Python 文件中的 F 类问题：

```bash
ruff check <changed-python-files> --select F --ignore F403,F405
```

### 4.4 浏览器运行时

```bash
COW_DATA_DIR="$HOME/.cow" \
PLAYWRIGHT_BROWSERS_PATH="$HOME/.cow/ms-playwright" \
.venv/bin/python - <<'PY'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.set_content('<title>check</title><h1>ok</h1>')
    print(page.title(), page.locator('h1').inner_text())
    browser.close()
PY
```

如果在受限沙箱中运行，Chromium 可能因 Mach 端口注册被拒绝而失败。改在普通终端或实际用户会话中验证；不要因此误判为应用故障。

## 5. 安装、升级与回滚

### 5.1 安装脚本

`scripts/install-native-macos.sh` 的顺序大致为：

1. 校验用户和命令。
2. 建立目录并收紧权限。
3. 创建或校验 Python 3.13 venv。
4. 安装依赖和 editable 包。
5. 安装 Node 24。
6. 确保 ffmpeg。
7. 迁移/安装 Playwright 到 `~/.cow/ms-playwright`。
8. 刷新配置。
9. 渲染并重载 LaunchAgent。
10. 等待 `/api/health`。

脚本必须保持幂等。重复运行不得覆盖已有配置、模型 Key、Web 密码、微信凭证或用户工作区。

### 5.2 升级

```bash
cd /Users/steven/CowAgent
bash scripts/update-native-macos.sh
```

升级流程会卸载服务、执行 `git pull --ff-only`、更新依赖、Node、ffmpeg、浏览器、配置并重启服务。失败时尝试回到升级前 commit 并恢复旧服务。

升级前要求工作区没有未提交改动，否则 fast-forward 拉取会失败。先提交或暂存你的开发改动：

```bash
git status
git stash push -u -m "before native update"
```

升级脚本不会自动启用 Git hooks。新克隆或重置本地 Git 配置后，记得运行 `bash scripts/install-git-hooks.sh`。

### 5.3 禁止的更新方式

- 不要使用 `cow start`、`cow stop`、`cow restart` 管理本安装。
- 不要点击 Web 控制台的一键更新。
- 不要在有 LaunchAgent 的情况下再手动启动第二个 `app.py`。

这些路径会与 `launchd` 的进程生命周期冲突，可能导致端口占用、重复进程或更新后无法恢复。

## 6. launchd 服务运维

### 6.1 状态与健康

```bash
launchctl print gui/$(id -u)/com.steven.cowagent
curl -sS http://127.0.0.1:9899/api/health
lsof -nP -iTCP:9899 -sTCP:LISTEN
```

正常状态应同时满足：服务 `state = running`、健康接口返回 `{"status":"ok"}`、监听地址只有 `127.0.0.1:9899`。

### 6.2 重启

```bash
launchctl kickstart -k gui/$(id -u)/com.steven.cowagent
```

### 6.3 停止与重新加载

```bash
launchctl bootout gui/$(id -u)/com.steven.cowagent
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/com.steven.cowagent.plist"
launchctl enable gui/$(id -u)/com.steven.cowagent
launchctl kickstart -k gui/$(id -u)/com.steven.cowagent
```

`bootout` 后立即 `bootstrap` 偶发返回 I/O error 是 launchd 的时序问题。安装脚本已等待并重试 10 次；手工操作遇到此错误时，等待 1 到 2 秒后重试即可。

### 6.4 前台调试

需要临时前台运行时，先停止 LaunchAgent，避免端口冲突：

```bash
launchctl bootout gui/$(id -u)/com.steven.cowagent 2>/dev/null || true
cd /Users/steven/CowAgent
COW_DATA_DIR="$HOME/.cow" \
COW_DEPLOYMENT=managed \
COW_NO_OPEN_BROWSER=1 \
.venv/bin/python app.py
```

调试结束后按 `Ctrl-C`，再重新 `bootstrap` 并 `kickstart` 服务。

### 6.5 日志

```bash
tail -f ~/Library/Logs/CowAgent/service.out.log
tail -f ~/Library/Logs/CowAgent/service.err.log
tail -n 100 ~/Library/Logs/CowAgent/maintenance.err.log
```

Web 控制台的「监控 → 日志」也提供运行日志。日志文件权限应为 `600`，目录权限应为 `700`。

## 7. 配置、凭证与权限

| 文件 | 内容 | 要求 |
| --- | --- | --- |
| `~/.cow/config.json` | 主配置、模型 Key、Web 密码 | `600` |
| `~/.cow/.env` | 技能/工具使用的密钥 | `600` |
| `~/.cow/weixin_credentials.json` | 微信登录凭证 | `600` |
| `~/.cow/ms-playwright` | Chromium 缓存 | 目录权限仅当前用户 |

### 7.1 Web 密码

```bash
jq -r '.web_password' ~/.cow/config.json
```

不要在终端日志、CI 输出、issue 或截图中打印完整配置。需要检查配置结构时使用类似：

```bash
jq '{channel_type, web_host, web_port, agent_workspace, agent_permission_mode}' ~/.cow/config.json
```

### 7.2 模型与搜索 Key

模型 Key 通过 Web 控制台的「配置 → 模型配置」写入。搜索、图像、语音等能力可分别配置厂商和模型。不要把 Key 写入源码、plist、脚本默认值或 Git。

`scripts/native-macos-common.sh` 安装可选依赖时会过滤固定的讯飞 `websocket-client==1.2.0`，避免与主依赖冲突。若未来调整语音依赖，必须同时验证讯飞和其他语音厂商。

### 7.3 Agent 权限

当前全局默认权限为 `full-access`，Agent 可访问当前用户的大部分文件、终端和网络资源。开发和测试高风险操作时，使用会话级「只读」或「工作区可写」权限，或把实验放到隔离目录。

## 8. 维护、备份与恢复

### 8.1 每日维护

`com.steven.cowagent.backup` 每天 `03:00` 执行：

- 轮转超过 20 MB 的服务/维护日志，保留 5 份压缩归档。
- 调用 `cow backup` 生成 `~/Backups/CowAgent/cowagent-*.zip`。
- 备份权限设为 `600`，保留最近 7 份。

手动执行：

```bash
cd /Users/steven/CowAgent
bash scripts/cowagent-maintenance.sh
```

检查：

```bash
ls -ld ~/Backups/CowAgent ~/Library/Logs/CowAgent
find ~/Backups/CowAgent -maxdepth 1 -name 'cowagent-*.zip' -exec ls -l {} \;
find ~/Library/Logs/CowAgent -maxdepth 1 -name '*.gz' | wc -l
```

### 8.2 恢复

恢复前先停服务，避免进程继续写配置：

```bash
launchctl bootout gui/$(id -u)/com.steven.cowagent
cd /Users/steven/CowAgent
COW_DATA_DIR="$HOME/.cow" .venv/bin/cow restore \
  "$HOME/Backups/CowAgent/cowagent-YYYYMMDD-HHMMSS.zip" \
  --workspace "$HOME/cow"
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/com.steven.cowagent.plist"
launchctl kickstart -k gui/$(id -u)/com.steven.cowagent
curl -sS http://127.0.0.1:9899/api/health
```

恢复命令会先生成 `cow-pre-restore-*.zip` 回滚备份。备份不加密，可能包含 API Key、Web 密码和对话内容；个人微信凭证不在归档中，恢复后通常需要重新扫码。

## 9. Web 与个人微信运行检查

### 9.1 Web 登录

登录状态默认保持 30 天。密码登录、健康接口和端口监听应作为每次部署后的验收项。

### 9.2 微信通道

- 通道类型为 `web,weixin`。
- 扫码二维码约 2 分钟过期，控制台会自动刷新。
- 登录成功后凭证写入 `~/.cow/weixin_credentials.json`。
- session 过期时会清除旧凭证并重新发起扫码。
- 微信只允许在用户最近一次发消息后的 24 小时内主动推送，定时任务超时是平台限制。
- 微信客户端建议 8.0.69 或更高版本。

## 10. 常见故障排查

| 现象 | 优先检查 | 处理 |
| --- | --- | --- |
| Web 无法连接 | 服务状态、9899 监听、健康接口 | `launchctl print`；查看 `service.err.log`；重启服务 |
| `bootstrap` 返回 I/O error | 是否刚执行 `bootout` | 等待 1–2 秒重试；安装脚本会自动重试 |
| 端口 9899 被占用 | 是否有手动 `app.py` 或旧进程 | `lsof -nP -iTCP:9899`；停掉重复进程，不要同时跑两个实例 |
| 登录密码错误 | 是否复制了完整密码 | `jq` 读取配置后重试；避免把密码写入 shell 历史 |
| 模型调用失败 | Key、API Base、余额、厂商状态 | 在 Web 配置中重新保存；查看服务日志 |
| Chromium 启动失败 | `~/.cow/ms-playwright`、沙箱环境 | 普通终端复测；重跑安装脚本；检查架构是否为 arm64 |
| ffmpeg 警告 | `command -v ffmpeg`、日志时间 | 安装后旧日志仍保留历史警告；只检查新时间戳 |
| 讯飞语音不可用 | `websocket-client` 版本 | 当前安装有意过滤讯飞固定依赖，属于已知限制 |
| 微信二维码过期 | 页面刷新、通道状态 | 重开二维码或重启服务；必要时重新接入 |
| 更新失败 | `update-native-macos.sh` 输出 | 脚本会尝试回退 commit；修复问题后再更新，不要盲目重试 |
| 推送被 GitHub 拒绝 | 提交历史中是否有 >100 MB blob | 停止重复推送；按第 3.5 节清理未推送历史 |
| 磁盘空间不足 | 备份、日志、工作区和浏览器缓存 | 检查 `~/Backups/CowAgent`、`~/Library/Logs/CowAgent`、`~/cow`、`~/.cow/ms-playwright` |
| 恢复后微信不可用 | 凭证是否重新生成 | 重新扫码，不要从旧备份复制过期凭证 |

## 11. 发布前检查清单

### 11.1 提交前

- `git status` 中没有意外文件。
- `git diff --cached --stat` 只包含本次任务文件。
- `python3 scripts/check_git_file_sizes.py staged` 通过。
- 变更的 Python 文件通过定向 pytest 和 ruff F 类检查。
- Shell、plist、JSON 配置语法检查通过。
- 没有密钥、密码、凭证、日志或生成缓存进入暂存区。

### 11.2 推送前

- `git log --oneline origin/dev..HEAD` 符合预期。
- `python3 scripts/check_git_file_sizes.py range origin/dev HEAD` 通过。
- 如果改动了服务启动或安装脚本，已在当前机器上实际安装/重启并检查健康接口。
- 如果改动了 Web 或微信，已验证登录和通道状态。

### 11.3 推送后

```bash
GIT_TERMINAL_PROMPT=0 git ls-remote origin refs/heads/dev
git status
```

确认远端 commit、当前分支和 `origin/dev` 一致。GitHub Actions 中的 Git hygiene 检查必须为绿色；PR 合入 master 前完整测试必须为绿色。

## 12. 安全边界

- 只用当前登录用户运行服务，不以 root 运行。
- 不把 Web 监听地址改为 `0.0.0.0`，除非已经配置密码、防火墙和可信网络。
- 不把 `full-access` Agent 指向不受信任的脚本、下载内容或未知仓库。
- 备份、日志、配置和 venv 都视为本机敏感数据。
- 一旦密钥进入 Git，仅删除文件还不够；应立即轮换密钥并清理未推送历史。

## 13. 命令速查

```bash
# 服务
launchctl print gui/$(id -u)/com.steven.cowagent
launchctl kickstart -k gui/$(id -u)/com.steven.cowagent
curl -sS http://127.0.0.1:9899/api/health
lsof -nP -iTCP:9899 -sTCP:LISTEN

# 日志
tail -f ~/Library/Logs/CowAgent/service.out.log
tail -f ~/Library/Logs/CowAgent/service.err.log

# 安装/升级/维护
bash scripts/install-native-macos.sh
bash scripts/update-native-macos.sh
bash scripts/cowagent-maintenance.sh

# Git
bash scripts/install-git-hooks.sh
python3 scripts/check_git_file_sizes.py staged
python3 scripts/check_git_file_sizes.py range origin/dev HEAD

# 测试
.venv/bin/python -m pytest tests/test_git_file_size_guard.py -q
.venv/bin/python -m pytest tests/test_web_browser_auto_open.py -q
.venv/bin/python -m pytest tests/ -q

# 配置
jq -r '.web_password' ~/.cow/config.json
stat -f '%Sp %N' ~/.cow ~/.cow/config.json ~/cow ~/Backups/CowAgent
```

相关文档：`docs/product-document.md`、`docs/architecture-document.md`、`docs/native-macos-install.md`、`docs/native-macos-user-manual.md`、`QUALITY.md`、`AGENTS.md`、`CONTRIBUTING.md`。
