# EduTutor v1.8 验收记录

验收日期：2026-11-23
版本主题：诊断测评、学习目标与个性化计划

## 已验证闭环

后端集成测试 `backend/tests/test_v18_goals.py` 以独立、随机 MySQL 夹具验证：

1. 创建目标时固定 active 知识版本和目标知识点来源。
2. 修改、暂停、恢复都追加目标版本，不覆盖历史。
3. 诊断只选择同一知识版本内已发布题目。
4. 客观题使用确定性规则判分。
5. 提交后产生按知识点聚合的掌握结论。
6. 未覆盖的目标知识点被显式标记为 `no_evidence`，不会被写成“不懂”。
7. 已提交诊断可生成带原因、证据引用、容量状态的周计划。
8. 目标修改生成新版本；旧计划在查询计划历史时被标记为 `stale`。
9. 刷新页面可恢复最近诊断；报告返回知识点教材来源页范围。
10. 其他账号读取学生目标时被拒绝。

这证明工程流程与数据边界，不代表真实学生学习效果，也不把工程夹具题目表述为教师审定测评题。

## 迁移验证

```powershell
cd backend
python scripts/check_v18_migration_roundtrip.py
```

随机临时库成功升级至 `e8b4a907c512`，降级至 `7efb3126a01c` 后诊断表消失，再升级后所有 v1.8 诊断/计划表恢复。

## 已执行命令

```powershell
cd backend
python -m pytest tests/test_v18_goals.py -q
python -m pytest tests/test_v18_diagnostics.py -q
python scripts/check_v18_migration_roundtrip.py

cd ..\frontend
npm run typecheck
npm test
npm run build
```

已通过：完整后端回归（15 项）、v1.8 端到端集成测试、诊断模型测试、迁移往返、前端类型检查、Vitest 12 项和生产构建。

## 完整后端回归

既有 PDF 提取测试曾指向已更名的知识库目录。已修正为当前仍在本机知识库中的同一教材文件：

`知识库\初中\初中数学\2024 人教版数学 七年级上册电子课本（高清正式版）.pdf`。

2026-11-23 已运行 `python -m pytest -q`，15 项均通过。该测试依旧是本机教材资产集成测试，而不是仓库内置二进制夹具。

## 已知范围

- 主观题保存答案并保持未确认状态；没有实际可用评分模型建议时，不会伪造分数或把它写成掌握证据。
- 当前 real `v142` 内容包尚未导入教师审校的正式诊断题；路由只会使用已发布且绑定来源块的题目。工程集成测试使用独立受控夹具。

## v142 人工审校题目导入

仓库提供 `backend/scripts/v18_diagnostic_question_template.json` 模板和受控导入器。只有包含 `reviewed_by` 与 `review_note` 的人工审校题目才能发布：

```powershell
cd backend
python scripts/import_v18_diagnostic_questions.py scripts/v18_diagnostic_question_template.json --version-id 142
```

模板中的占位符不能直接导入；它是人工审校题目的结构说明，避免把生成内容冒充正式测评资产。

仓库另附 `backend/scripts/v18_v142_engineering_samples.json`：它是明确标注为“非学科人工审校”的工程验证样例，只用于验证已激活的 v142 内容包能被受控题库读取。正式发布前必须由学科审核人以同一导入格式替换或复审。

2026-11-23 已对本机 active `v142` 运行该工程样例导入，结果为 `created: 1, skipped: 0`。
