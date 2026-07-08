# Ponytail 与 Notification Adapter 使用边界

> 日期：2026-06-30

## 1. Ponytail

Ponytail 仓库：

```text
git@github.com:DietrichGebert/ponytail.git
```

本项目使用方式：

- 作为开发前检查：是否必要、是否已有、是否能用标准库/平台能力、是否最小实现。
- 作为 review 检查：是否过度抽象、是否改了无关文件、是否引入不必要依赖。
- 已按官方 Codex 插件方式安装；本机缓存路径为 `C:\Users\86173\.codex\plugins\cache\ponytail\ponytail\4.8.4`。
- hooks 用于开发会话约束，不参与业务系统运行。
- 不加入后端 `requirements.txt`。
- 不加入前端 `package.json`。
- 不进入 Docker Compose 运行时。

## 2. Notification Adapter

Notification Adapter 在本项目中只做独立消息通道适配器：

- 钉钉测试消息。
- 消息发送验证。
- 运维健康检查。
- 第一版正式消息发送：企业内部应用通知入口。2026-07-04 已按用户要求验证互动卡片模板投放，后续新品待办卡片接入见 `docs/19-钉钉新品待办卡片接入说明.md`；工作通知 `link` / `action_card` 保留为兜底。

边界：

- 不直接访问生产数据库。
- 不挂载 Docker socket。
- 不持有 ERP 或钉钉生产密钥，密钥由服务器环境注入。
- 不参与核心业务状态流转，业务状态以 FastAPI + PostgreSQL 为准。
- 不在第一版承担钉钉待办、互动卡片模板管理、机器人群会话运营或在线表写回。

## 3. 当前落地

- `deploy/notification-adapter/` 已提供独立容器骨架。
- `POST /dingtalk/test` 在未配置 webhook 时只返回 `skipped`。
- 2026-07-03 已验证企业内部应用 access token、部门通讯录遍历、个人工作通知发送和发送结果回查。
- 直接按姓名搜索 userId 仍缺 `qyapi_addresslist_search` 权限；当前可用部门遍历兜底。
- 已封装“接收人 -> 新品待办卡片变量 -> 钉钉互动卡片投放 -> 任务页”的最小发送函数；工作通知 link/action_card 保留为 fallback。
