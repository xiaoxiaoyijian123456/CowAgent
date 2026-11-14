# CowAgent 原生 macOS 架构文档

> 文档版本：1.0
>
> 范围：本 fork 在单台 macOS 上原生运行的产品架构、组件关系、数据流、持久化、安全与故障域
>
> 产品范围与验收标准见 `docs/product-document.md`；操作步骤见用户手册和开发运维手册。

## 1. 架构目标与原则

### 1.1 目标

- 在一台 macOS 上提供单用户、长期运行的完整 AI Agent。
- Web 控制台与个人微信共享同一个 Agent 运行时和用户数据。
- 保留本机文件、终端、浏览器、Node/MCP 和网络访问能力。
- 配置、会话、记忆、知识和产物跨重启持久化。
- 通过用户级 `launchd`、备份和脚本化升级降低长期运维成本。

### 1.2 设计原则

1. **本地优先**：不依赖云端控制平面、容器编排或公网入口。
2. **单用户可信环境**：按当前 macOS 用户权限运行，不用多租户隔离假设设计。
3. **控制面与数据面分离**：源码在仓库，运行数据在 `~/.cow`，工作区在 `~/cow`。
4. **通道解耦**：Web 与微信通过统一消息协议进入 Agent，不各自复制业务逻辑。
5. **工具受权限约束**：Agent 能力由权限模式和工具实现共同限制。
6. **失败可恢复**：服务自动拉起，升级可回退，数据每日备份。
7. **可观测且可诊断**：健康接口、结构化日志和本机状态命令优先。
8. **生成物不进 Git**：浏览器缓存、虚拟环境和运行时数据永不提交。

## 2. 系统上下文

```text
                         ┌─────────────────────────────┐
                         │        macOS 用户会话        │
                         │                             │
  Browser ──HTTP/SSE────▶│ WebChannel                  │
                         │        │                    │
  WeChat ──iLink API────▶│ WeixinChannel               │
                         │        │                    │
                         │        ▼                    │
                         │ ChannelManager              │
                         │        │                    │
                         │        ▼                    │
                         │ Agent runtime / Bridge      │──────▶ Model providers
                         │   │       │       │         │
                         │   │       │       └──────────────▶ Network / web
                         │   │       └──────────────────────▶ Tools / Skills / MCP
                         │   └──────────────────────────────▶ Filesystem / shell / browser
                         │        │                    │
                         │        ▼                    │
                         │ ~/.cow + ~/cow + logs       │
                         └─────────────────────────────┘
                                      ▲
                                      │
                              launchd / backup / update
```

外部依赖包括：

- 用户配置的模型厂商 API。
- 微信官方 iLink 服务。
- 可选 MCP 服务、联网搜索、网页抓取和第三方 Skill 依赖。
- Homebrew 提供的 ffmpeg、Git、curl 等本机工具。
- fnm 提供的 Node 24 及 `npx`/`uvx` 类运行时。

## 3. 组件视图

| 层 | 组件/代码位置 | 职责 |
| --- | --- | --- |
| 进程入口 | `app.py`, `scripts/cowagent-service.sh` | 加载配置、启动 Web、启动通道、注册信号、常驻进程 |
| 通道编排 | `app.py::ChannelManager` | 启动、停止、重启、动态添加和移除通道 |
| Web 通道 | `channel/web/` | HTTP 服务、密码认证、SSE 对话、文件/工作区/配置/日志 API |
| 微信通道 | `channel/weixin/weixin_channel.py` | 二维码登录、凭证持久化、iLink 收发、消息转换 |
| Agent 运行时 | `agent/`, `bridge/` | Agent 循环、上下文、工具调用、会话生命周期 |
| 模型层 | `models/`, `bridge/bridge.py` | 厂商适配、模型选择、文本/视觉/语音/向量能力 |
| 工具层 | `agent/tools/` | 文件、终端、浏览器、搜索、发送、MCP、定时、记忆等 |
| 权限层 | `agent/permission/` | `read-only`、`workspace-write`、`full-access` 边界 |
| 记忆与知识 | `agent/memory/`, `agent/knowledge/` | 会话存储、长期记忆、摘要、检索、知识页 |
| Skills | `agent/skills/`, `skills/` | 内置与用户技能加载、快照、安装和提示注入 |
| 多 Agent | `agent/registry.py`, `agent/routing.py`, `agent/subagent/` | Agent 注册、会话路由、委派和临时子 Agent |
| 自我进化 | `agent/evolution/` | 空闲复盘、记忆/知识沉淀和受控改进 |
| 配置与状态 | `config.py`, `common/state_dir.py` | `config.json`、数据根、工作区、通道配置 |
| 运维脚本 | `scripts/native-macos-common.sh` 等 | 安装、更新、维护、launchd 渲染、健康检查 |
| 持久化 | SQLite + JSON + Markdown | 会话、配置、记忆、知识、产物和备份 |

## 4. 运行时部署拓扑

### 4.1 进程与生命周期

```text
LaunchAgent com.steven.cowagent
  └─ /bin/bash scripts/cowagent-service.sh
      └─ .venv/bin/python app.py
          ├─ Web HTTP server (127.0.0.1:9899)
          ├─ WeixinChannel thread
          ├─ Agent runtime / scheduler
          ├─ MCP warmup / subprocesses
          └─ Tool execution subprocesses
```

- LaunchAgent 是用户级 `Aqua` 任务，macOS 用户登录后启动。
- `RunAtLoad` 和 `KeepAlive` 提供自动启动与异常恢复。
- `ThrottleInterval=10` 限制服务连续失败时的重启频率。
- 服务环境固定 `COW_DATA_DIR=~/.cow`、`COW_DEPLOYMENT=managed`、`COW_NO_OPEN_BROWSER=1`。
- 两个 LaunchAgent：主服务和每日备份维护任务。

### 4.2 网络边界

| 入口 | 监听/连接方式 | 边界 |
| --- | --- | --- |
| Web | `127.0.0.1:9899` | 仅本机回环，密码认证 |
| 微信 | 出站 iLink API + 轮询/长连接 | 无公网入站端口 |
| 模型 | 出站 HTTPS | 用户配置的厂商 |
| MCP/搜索/网页 | 出站网络或本地子进程 | `full-access` 下无网络级隔离 |

不部署反向代理、TLS 终止或局域网监听；远程访问不属于当前架构范围。

## 5. 消息与 Agent 执行流

### 5.1 标准请求路径

1. **接入**：Web 请求或微信消息进入对应通道。
2. **标准化**：通道转换为统一消息上下文，附带渠道、会话、用户和附件信息。
3. **路由**：`AgentRouter` 根据通道实例或会话选择默认/指定 Agent。
4. **会话恢复**：从 SQLite 会话库加载上下文；必要时应用项目工作空间、模型和权限设置。
5. **模型规划**：模型结合系统提示、记忆、知识、技能和工具描述生成下一步动作。
6. **工具执行**：按权限检查结果执行文件、命令、浏览器、搜索、MCP、定时等工具。
7. **循环**：将工具结果回送模型，直到任务完成、步数/上下文达到上限或被用户停止。
8. **输出**：Web 通过 SSE 流式返回；微信转换为文本、图片、文件等消息。
9. **持久化**：消息、运行记录、产物和必要记忆写入工作区。
10. **后台任务**：会话标题、记忆摘要、知识整理和自主进化在受控后台路径执行。

### 5.2 权限检查

权限模式在工具执行前生效：

| 模式 | 文件写入 | 命令/浏览器 | 边界 |
| --- | --- | --- | --- |
| `read-only` | 拒绝 | 只读/分析类操作 | 不修改文件 |
| `workspace-write` | 仅当前工作空间 | 受工作空间约束 | 越界写入拒绝 |
| `full-access` | 允许当前用户可写位置 | 允许 | 依赖 macOS 账户权限 |

权限模式不是操作系统级沙箱。`full-access` 的实际边界等同于当前 macOS 用户。

## 6. Web 通道架构

### 6.1 服务组成

- 嵌入式 `web.py` HTTP 服务，绑定 `127.0.0.1:9899`。
- 认证入口 `/auth/login`、`/auth/check`、`/auth/logout`。
- 对话 API 转发到 `WebChannel`，后者维护请求队列和 SSE 状态。
- 文件、工作空间、配置、通道、技能、记忆、知识、定时任务、日志和产物 API。
- 可选 OpenAI 兼容接口 `/v1/chat/completions`，默认关闭。

### 6.2 认证

- 密码来自 `~/.cow/config.json` 的 `web_password`。
- 登录成功后签发 HMAC 签名的无状态 token，并写入 HttpOnly Cookie。
- token 以密码为签名密钥，默认会话有效期 30 天。
- 连续错误密码由登录限流器限制，降低本机或误暴露场景下的暴力尝试风险。

### 6.3 流式输出

Web 对话使用 SSE：

- `post_message` 提交请求。
- `stream_response` 按事件序号返回文本、思考、工具调用和完成状态。
- `cancel_request` 支持停止当前运行。
- SSE 状态保存在进程内，长连接断开后可由客户端按序号恢复。

### 6.4 动态通道管理

Web 控制台通过 `ChannelManager` 可动态启动、停止和重启通道。保存通道配置后会清理对应单例缓存并重启通道线程，不需要重启整个进程。

## 7. 个人微信通道架构

### 7.1 登录与凭证

1. 无有效 token 时调用 iLink 获取二维码。
2. 用户扫码并在手机确认。
3. 凭证原子写入 `~/.cow/weixin_credentials.json`，权限 `600`。
4. 下次启动优先复用凭证。
5. session 过期时清除旧凭证并重新发起扫码。

### 7.2 消息处理

- 支持私聊文本、图片、文件、视频接收和发送。
- 语音接收依赖语音识别模型；iLink 不提供对应的语音发送项，因此语音回复按文件发送。
- 微信平台限制主动推送窗口为用户最近一条消息后的 24 小时。
- 微信通道在独立线程中运行，由 `ChannelManager` 管理生命周期。

## 8. Agent 运行时与后台任务

### 8.1 会话与上下文

- `SessionService` 管理会话列表、删除、重命名、清空上下文和自动标题。
- 会话历史存于 `<workspace>/memory/long-term/index.db`（SQLite）。
- `sessions` 表保存会话元数据；`messages` 表保存消息 JSON 和序号。
- 每个会话可单独指定模型、项目工作空间和权限。
- `projects.json` 保存会话到项目目录的映射和最近项目列表。

### 8.2 模型与能力

模型层按能力分派：

- 主对话模型。
- 视觉理解。
- 图像生成。
- 语音识别/合成。
- 向量嵌入。
- 联网搜索。

不同能力可以来自不同厂商，保存配置后不需要修改 Agent 工具调用协议。

### 8.3 工具、Skills 与 MCP

- 工具通过统一注册表暴露给模型，包含描述、参数模式和权限要求。
- 自定义 Skills 以 Markdown/目录形式加载，内容进入系统提示或按需发现。
- MCP 服务在启动后台预热，使用 Node/`npx` 或 Python/`uvx` 子进程。
- MCP 失败是非致命的：单个 server 加载失败不应阻止主服务启动。

### 8.4 多 Agent 与子 Agent

- `AgentRegistry` 维护 Agent profile、工作区和启用状态。
- `AgentRouter` 把通道实例或会话路由到指定 Agent。
- 团队成员拥有独立人格、记忆和工作区。
- 子 Agent 是临时执行单元，共享父 Agent 工作区，不拥有独立持久记忆。

### 8.5 后台组件

- 定时调度器：执行一次性、固定间隔和 Cron 任务。
- 记忆摘要/刷新：在上下文和会话生命周期中维护长期记忆。
- 自主进化：会话空闲后复盘并沉淀记忆、知识和技能改进。
- MCP 预热：缩短首轮消息等待第三方工具初始化的时间。

## 9. 数据架构

### 9.1 数据位置

| 数据 | 位置 | 格式/权限 |
| --- | --- | --- |
| 主配置、模型 Key、Web 密码 | `~/.cow/config.json` | JSON，`600` |
| Skill/工具密钥 | `~/.cow/.env` | 环境文件，`600` |
| 微信凭证 | `~/.cow/weixin_credentials.json` | JSON，`600` |
| Playwright 浏览器 | `~/.cow/ms-playwright` | 平台二进制缓存 |
| 浏览器 profile | `~/.cow/browser_profile` | 站点登录状态 |
| 会话数据库 | `~/cow/memory/long-term/index.db` | SQLite |
| 长期/每日记忆 | `~/cow/MEMORY.md`, `~/cow/memory/` | Markdown |
| 知识库 | `~/cow/knowledge/` | Markdown + 索引 |
| 技能 | `~/cow/skills/`, 仓库 `skills/` | 目录 + `SKILL.md` |
| 项目映射 | `~/cow/projects.json` | JSON |
| 多 Agent 配置 | `~/cow/agents/team.json` | JSON |
| 备份 | `~/Backups/CowAgent/` | ZIP，`600`；不含 `~/.cow/.env` 和微信凭证 |
| 日志 | `~/Library/Logs/CowAgent/` | 文本，`600` |

### 9.2 数据生命周期

- 配置变更通过临时文件替换，避免半写入。
- 会话历史追加写入 SQLite，按年龄和配置进行清理。
- 记忆、知识和技能是用户可见、可编辑的持久文件。
- 备份包含 `config.json` 和全部 Agent 工作区，不包含 `~/.cow/.env`、微信凭证、浏览器缓存、临时文件、Git 元数据或符号链接。模型 Key 若存放在 `config.json` 中会随备份保存。
- 备份不加密，需按敏感数据管理。
- 恢复覆盖同名文件，不删除目标目录中的其他文件，并先生成回滚备份。

### 9.3 数据一致性

- 单进程内由锁和原子写控制配置/项目映射。
- SQLite 提供会话级持久性。
- 记忆、知识和技能是文件级最终一致性，不提供跨文件事务。
- 手工编辑用户数据前应停止服务或先做备份。

## 10. 安全架构

### 10.1 信任边界

```text
受信任：当前 macOS 用户、已审核源码/技能、用户明确授权的工具调用
不受信任：外部网页、第三方消息附件、未知 Skill/MCP、提示注入内容
```

当前没有容器或独立用户隔离，因此不受信任内容一旦诱导 Agent 执行工具，实际能力边界就是当前 macOS 用户。

模型厂商、搜索/抓取服务、MCP 服务和微信 iLink 属于外部数据处理方；发送给它们的对话、附件与工具参数受各自服务条款和用户配置约束。本机落盘优先不等于所有内容只在本地流转。

### 10.2 控制措施

- Web 只监听回环地址并使用密码。
- 配置、凭证、日志、备份使用 `600/700` 权限。
- 密钥不写入源码、plist、日志或 Git。
- Git hooks 与 CI 阻止运行时缓存和大文件进入历史。
- 会话级权限可在高风险任务中降为只读或工作区可写。
- 恢复、升级和提交前要求备份或历史检查。

### 10.3 未提供的控制

- 文件系统级沙箱。
- 多用户身份与角色权限。
- 网络出站白名单。
- 审计级不可篡改日志。
- 静态数据加密和加密备份。
- 对恶意 Skill/MCP 的自动供应链验证。

## 11. 可靠性、故障域与恢复

| 故障域 | 行为 | 恢复 |
| --- | --- | --- |
| Python 进程崩溃 | `KeepAlive` 拉起，`ThrottleInterval` 限制频率 | 查看日志，修复启动错误 |
| Mac 睡眠 | Web、微信和定时任务离线 | 唤醒后进程恢复；错过的任务不承诺补跑 |
| `launchd` 重载时序错误 | `bootstrap` I/O error | 脚本等待重试；手工等待后重试 |
| 模型 API 故障 | 当前对话失败或降级 | 切换模型/厂商，检查网络和余额 |
| MCP server 故障 | 对应工具不可用 | 非致命；查看日志并修复配置 |
| Web 连接中断 | SSE 断开 | 客户端按事件序号恢复 |
| 微信 session 过期 | 通道停止收发 | 清除旧凭证并重新扫码 |
| 磁盘空间不足 | 写入/备份/数据库可能失败 | 清理备份、日志、产物或缓存 |
| 更新失败 | 新代码无法启动 | 更新脚本回退旧 commit 并恢复服务 |
| 数据损坏 | 配置或工作区不可用 | 停服务，从最近备份恢复 |

### 11.1 恢复目标

- 正常每日备份下，数据恢复点最多约 24 小时。
- 重要变更前执行手动备份可降低数据损失。
- 恢复时间取决于归档大小和人工操作，未定义硬性 SLA。

## 12. 可观测性

### 12.1 当前能力

- `/api/health` 健康检查。
- Web 控制台运行日志。
- `service.out.log`、`service.err.log`、`maintenance.*.log`。
- Web 控制台中的会话、任务执行记录、记忆、知识和产物视图。
- `launchctl print`、`lsof` 和本机文件权限检查。

### 12.2 当前缺口

- 没有内置 Prometheus/OpenTelemetry 指标。
- 没有外部遥测或集中告警。
- 没有自动资源水位、磁盘增长趋势和模型调用成本看板。
- 日志轮转按每日维护执行，不是实时日志平台。

## 13. 扩展点

| 扩展 | 入口 |
| --- | --- |
| 新消息通道 | `channel/` + `ChannelManager` 注册 |
| 新模型厂商 | `models/` + 模型配置 |
| 新工具 | `agent/tools/` + 工具注册表 |
| 新 Skill | `skills/` 或用户工作区 `skills/` |
| MCP 服务 | `~/cow/mcp.json` |
| 多 Agent 团队 | `~/cow/agents/team.json` + Web 智能体页面 |
| 运维自动化 | `scripts/` + LaunchAgent |
| 备份策略 | `cli/commands/backup.py` + 维护脚本 |

扩展时应维持：

- 通道到 Agent 的统一消息协议。
- 工具权限检查先于执行。
- 配置、数据和生成缓存不进入 Git。
- 新增后台进程必须可停止、可观测且不阻塞健康启动。

## 14. 关键架构决策

| 决策 | 理由 | 影响 |
| --- | --- | --- |
| 原生 macOS 而非 Docker | 保留终端、浏览器、Node/MCP 和本机文件能力 | 无容器隔离，依赖当前用户权限 |
| 当前用户而非独立用户 | 降低安装和完整本机能力门槛 | Agent 可访问该账户全部资源 |
| `launchd` 管理服务 | 用户登录后自启、异常恢复 | 不使用 `cow start/stop` 管理 |
| Web 仅监听回环地址 | 避免无公网防护的控制台暴露 | 其他设备不能直接访问 |
| 数据与源码分离 | 更新/重装不触碰用户数据 | 备份需覆盖 `~/.cow` 与 `~/cow` |
| Playwright 放在数据根 | 避免缓存进入源码和 Git | 安装/升级需设置固定浏览器路径 |
| 每日备份 + 7 份保留 | 低成本灾难恢复 | 无加密，RPO 约一天 |
| Git hooks + CI | 防止大文件历史再次污染远端 | 每个克隆需启用本地 hooks |

## 15. 已知架构限制

- 单进程、单机，无高可用、多副本或水平扩展。
- 仅支持当前 macOS 用户环境，不覆盖多用户组织场景。
- Mac 睡眠期间没有持续在线保证。
- Web 无 TLS/反向代理，默认仅本机访问。
- SQLite 为单进程共享会话库，不适合多实例并发写入。
- `full-access` 仅受 macOS 用户权限限制，无容器级隔离。
- 讯飞星火语音因依赖版本冲突未启用。
- 备份和日志未加密，依赖本机文件权限。

## 16. 验证矩阵

| 架构属性 | 验证方法 |
| --- | --- |
| 服务生命周期 | `launchctl print`、`kickstart` 后健康接口 |
| Web 边界 | `lsof` 确认仅 `127.0.0.1:9899` |
| 认证 | 正确/错误密码、Cookie 后续请求 |
| Agent 工具 | 文件读写、受控命令、Playwright 页面加载 |
| 通道 | Web 与微信登录状态及真实消息 |
| 持久化 | 重启后配置、会话和工作区仍在 |
| 备份 | 手动维护、ZIP 权限、保留数量、恢复演练 |
| 日志 | 超阈值轮转、当前日志可写、权限正确 |
| Git 约束 | 超限文件、缓存路径、已删除的历史 blob 均被拦截 |
| Node/MCP | `node`/`npx` 版本、MCP 预热和单 server 故障隔离 |

## 17. 相关文档

- 产品定义与验收：`docs/product-document.md`
- 用户操作：`docs/native-macos-user-manual.md`
- 开发运维：`docs/native-macos-devops-manual.md`
- 安装说明：`docs/native-macos-install.md`
- 原生 full-access 决策：`docs/adr/0001-native-full-access-cowagent.md`
- 通用 Agent 架构：`docs/zh/intro/architecture.mdx`
- 质量要求：`QUALITY.md`
- Agent 提交约束：`AGENTS.md`
