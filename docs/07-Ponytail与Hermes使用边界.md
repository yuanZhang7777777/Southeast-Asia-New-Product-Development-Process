# Ponytail 与 Hermes 使用边界

> 日期：2026-06-29

## 1. Ponytail

Ponytail 仓库：

```text
git@github.com:DietrichGebert/ponytail.git
```

本项目使用方式：

- 作为开发前检查：是否必要、是否已有、是否能用标准库/平台能力、是否最小实现。
- 作为 review 检查：是否过度抽象、是否改了无关文件、是否引入不必要依赖。
- 不加入后端 `requirements.txt`。
- 不加入前端 `package.json`。
- 不进入 Docker Compose 运行时。

## 2. Hermes

Hermes 在本项目中只做独立 Agent/适配器：

- 钉钉测试消息。
- 自动化任务验证。
- 运维健康检查。

边界：

- 不直接访问生产数据库。
- 不挂载 Docker socket。
- 不持有 ERP 或钉钉生产密钥，密钥由服务器环境注入。
- 不参与核心业务状态流转，业务状态以 FastAPI + PostgreSQL 为准。

## 3. 当前落地

- `deploy/hermes/` 已提供独立容器骨架。
- `POST /dingtalk/test` 在未配置 webhook 时只返回 `skipped`。
- 后续接真实钉钉前，先在测试群验证消息能力。
