# 在当前 macOS 用户下原生运行 CowAgent

本部署放弃 Docker、Kubernetes 和独立 macOS 用户，直接把由本 fork 源码安装的 CowAgent 运行在 `steven` 账户下，以便保留浏览器、Node/MCP、终端和对本机文件的完整访问能力。使用者明确接受该安全边界：Agent 的 `full-access` 权限覆盖此账户的全部文件与网络资源，提示注入、恶意 Skill 或不可信 MCP 可能读取、修改或外传这些数据。备选的容器与独立用户方案被放弃，因为它们会限制完整本机能力并增加安装与运维复杂度。
