# 生产代码基线（2026-08-25）

## 结论

本分支保存了 2026-08-25 线上可部署源码的脱敏副本。允许范围内的 148 个文件与生产主机逐文件 SHA-256 一致；生产主机的 76 个后端 Python 文件又与正在运行的 API 容器逐文件一致。

这是“源码一致基线”，不是一次新发布。线上没有 Git 工作区，`RELEASE_COMMIT` 仍为过期标记 `c2fe6f8`，不能用它判断线上版本。

## 来源与校验

- 生产别名：`hz-new-product-preprod`
- 只读来源：`/opt/hengzhe-new-product/app`
- 抓取时间：2026-08-25 11:14–11:15（Asia/Shanghai）
- 本地基底提交：`917d382467f2d1372f0b7d5d33cad9e429d51e59`
- 文件数：148
- 总字节数：1,986,529
- 清单：[production-baseline-20260825.sha256](production-baseline-20260825.sha256)
- 清单文件 SHA-256：`9f8993ed933bd7c89430ca319c09e2264f9b6118f5f547b73f3f02f1441c94ec`
- 抓取前后生产清单差异：0
- 本地与生产清单差异：0；线上独有：0；本地独有：0
- 后端主机与运行中 API 容器：76/76 一致；差异：0

纳入范围仅为后端应用/迁移源码、前端源码和锁文件、Dockerfile、Compose、Nginx、Caddy 等非敏感部署配置。未复制 `.env`、密码、令牌、Cookie、钉钉凭据、数据库、上传文件、业务表格、日志、缓存、输出和备份。

## 前端运行产物

线上运行产物：

- JS：`index-BJBf5msH.js`，508,683 字节，SHA-256 `555cee9063cfde02f38e7a74324a99998ff465ac7de8da50f77bf51756a68260`
- CSS：`index-C-wntkuO.css`，82,054 字节，SHA-256 `fb6eb4227e4541fbc60e9704a9fe480adcc52f46a576fa7291f3a250218d508e`

本地不注入凭据的构建成功，CSS 与线上逐字节一致。JS 为 508,620 字节，指纹不同。生产 Compose 在构建时注入了非空、36 字符的 `VITE_DINGTALK_CORP_ID`；用同长度的非敏感占位符重建后，JS 恢复为线上相同的 508,683 字节。因此差异来自被刻意排除的构建期配置，不是源码清单漂移。真实 Corp ID 未读取到 Git、未写入本文档。

## 验证结果

- Alembic：单一 head `a7b8c9d0e123`
- 前端 TypeScript/Vite 构建：通过
- 前端测试：245 通过、6 失败（共 251）
- 后端测试：683 通过、18 失败（共 701）

测试失败没有被改源码掩盖。证据表明测试基准落后于运行源码：本地基线与生产主机的 103 个测试文件中有 16 个内容不同；失败断言还在要求旧迁移 head、旧钉钉跳转 URL、旧 PLM 筛选语义、旧前端函数签名或固定 16 列。生产主机自身也保存着部分相同的陈旧断言。测试债务需要单独校准，不能据此否定已完成的运行源码哈希一致性，也不能把本基线表述为“全测试通过”。

## 本地保护与操作边界

- 任务前完整 Git bundle：`E:\Project\Hengzhe-New-Product-Workflow-backups\20260825-production-baseline\repository.bundle`
- bundle SHA-256：`7ba227ed79ab1963355fe3d44140a91dce6fa84c5af516ff52831e5a08cdd711`
- 任务前 13 个现存工作树的补丁、未跟踪文件清单和远端 heads 清单保存在同一备份目录。
- 本任务未删除分支、工作树或 stash，未 push、merge、deploy、restart，也未修改生产文件、容器、数据库、配置、任务调度或流量。

本地基线分支为 `lxc/production-baseline-20260825`，本地标签为 `prod-2026-08-25-baseline`。后续清理旧分支前，应先以此基线和 bundle 为恢复锚点；清理仍须另行确认。
