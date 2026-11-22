# EduTutor v1.7 验收报告

验收日期：2026-11-22  
版本主题：教材、知识库治理与回答证据

## 1. 真实教材闭环

在用户明确授权后，使用本地文件 `E:\个人发展\002职业\项目4：个性化教育\知识库\小学\人教版小学数学【电子课本】\2026人教版数学二年级下册电子课本.pdf` 做真实构建验收。该文件仅按本项目已配置的 DeepSeek API 用于知识编译，不对外发布教材内容。

| 项目 | 结果 |
|---|---|
| 文件页数 / SHA-256 | 106 页 / `5dd2894ca4d2e1fcbdf7b58c217189e74ebf211bc3d0712317d7749c4caa659b` |
| 教材 / 构建任务 | `textbook_id=155` / `task_id=70` |
| 构建结果 | 成功，115/115 单元完成，`failed_units=0` |
| 初始版本 | `v141`，五类结构性抽检记录 `review_id=13`，发布门禁无问题后激活 |
| 证据与纠错 | 生成证据账本 `ledger_id=34`，1 条已采用教材证据；纠错工单 `#36` 已应用 |
| 修订版本 | `v142`，五类结构性抽检记录 `review_id=14`，发布门禁通过 |
| 回滚验证 | `v142 → v141 → v142` 成功；验收结束时 `active_version_id=142` |

五类抽检项为正文、公式、知识点、难度和先修关系。它们验证的是受控发布所要求的完整性与可追溯记录；本报告不把自动化结构检查表述为人工教学内容审校。

## 2. 可复现命令与结果

```powershell
cd backend
python scripts/create_v17_real_sample.py "E:\个人发展\002职业\项目4：个性化教育\知识库\小学\人教版小学数学【电子课本】\2026人教版数学二年级下册电子课本.pdf"
python scripts/knowledge_worker.py --once
python scripts/run_v17_real_acceptance.py
python scripts/check_v17_migration_roundtrip.py
python -m pytest -q
python scripts/audit_vector_consistency.py

cd ..\frontend
npm run typecheck
npm test
npm run build
```

| 门禁 | 结果 |
|---|---|
| 数据库迁移 | 新建随机 MySQL 临时库完整升级、降至 `39c8a7d1e2f4`、再升至 `31b933ce603d` 均成功；治理表全部恢复。临时库 `edu_tutor_v17_migration_check_9b19f129569d` 为避免删除风险被保留。 |
| 后端完整回归 | `python -m pytest -q` 退出码 0。 |
| 前端 | `npm run typecheck` 通过；Vitest 5 个文件、11 项通过；`npm run build` 通过。 |
| 双库一致性 | 只读审计中 memory / knowledge 的缺失向量、孤儿向量、metadata 错误和无效知识链接均为 0。 |
| 发布门禁 | v141 与 v142 的 `audit_version_consistency` 均无 issues。 |

## 3. 交付内容

- 教材文件哈希去重、安全上传、任务租约、进度事件、断点续跑与失败重试。
- staged / active / archived 知识版本，来源页、块、知识点、向量与图谱关系的门禁校验。
- 管理端教材、任务、审核和纠错队列；普通用户不可访问该区域。
- 回答证据账本与 SSE 证据事件；教材证据不足时返回明确缺口。
- 纠错工单保留原值、提议值、原因、操作者和处理状态；知识纠错创建不可变子版本而不覆盖历史版本。

## 4. 已知边界

- 真实教材构建验证了工程链路、来源追踪与版本治理，不等同于逐页、逐公式的人工教研审校；教材内容进入正式教学发布前仍应安排具备学科资质的审核人逐项复核。
- 前端覆盖管理权限、聊天证据和纠错交互的组件测试；未执行跨浏览器和长时间断网恢复压测。
- Vite 生产构建存在既有的大包警告（最大 chunk 约 1.1 MB），不影响本版正确性，性能拆包留给后续版本。

## 5. 结论

v1.7 的教材治理、知识库发布、回答证据、纠错与回滚工程闭环已通过真实教材验收。所有数值均来自本次命令输出；本报告不声称教材内容已完成专家级教学正确性认证。
