# 本机 CowAgent 原生安装

本上下文描述如何把由本 fork 源码构建的 CowAgent 长期运行在当前 macOS 用户下。

## 术语（Language）

**个人微信通道**:
CowAgent 通过微信官方 iLink API 接入个人微信的渠道，渠道类型为 `weixin`，通过扫码登录且无需公网 IP。
_Avoid_: 微信公众号, 企业微信, 微信客服

**CowAgent 工作区**:
Agent 的持久状态根，本安装中位于 `~/cow`，保存会话、记忆、知识、技能和工作产物。
_Avoid_: 项目目录, 仓库目录

**CowAgent 数据根**:
本安装中由 `COW_DATA_DIR=~/.cow` 指定，保存 `config.json`、微信登录凭证等敏感运行数据。
_Avoid_: 工作区
