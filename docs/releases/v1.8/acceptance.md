# EduTutor v1.8 验收记录

验收日期：2026-11-24
阶段状态：完成（AI 初审演示题库口径）
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
11. 已发布诊断题保存审计信息且受数据库不可变保护；教材 active 版本切换后不能用旧目标新开诊断。

这证明工程流程与数据边界，不代表真实学生学习效果，也不把工程夹具题目表述为教师审定测评题。

## 迁移验证

```powershell
cd backend
python scripts/check_v18_migration_roundtrip.py
```

随机临时库成功升级至 `b6e2c8f4a913`，降级至 `7efb3126a01c` 后诊断表消失，再升级后所有 v1.8 表、评分理由、审核审计字段和已发布题不可变触发器恢复。

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

已通过：完整后端回归（17 项）、v1.8 端到端集成测试、诊断模型与多来源证据冲突测试、迁移往返、前端类型检查、Vitest 13 项和生产构建。

本次补缺后，学习目标支持修改目标水平并追加版本；诊断页面按题导航，报告展示来源页、累计用时与平均自信度；计划历史可切换查看旧版本明细。诊断先修范围限制为两层，学习计划同时以结构化 `evidence_gap` 返回当前知识版本中无法解析的先修缺口。

## 完整后端回归

既有 PDF 提取测试曾指向已更名的知识库目录。已修正为当前仍在本机知识库中的同一教材文件：

`知识库\初中\初中数学\2024 人教版数学 七年级上册电子课本（高清正式版）.pdf`。

2026-11-23 已运行 `python -m pytest -q`，17 项均通过。该测试依旧是本机教材资产集成测试，而不是仓库内置二进制夹具。

PDF 提取测试现为可选本机集成测试：默认使用开发机教材路径；其他环境若没有该文件会显示 `skipped`，不会被误判为回归失败。可通过 `EDUTUTOR_PDF_FIXTURE` 指定自己的可用 PDF 后启用该项验证。

## 阶段边界

- 主观题保存答案并保持未确认状态；没有实际可用评分模型建议时，不会伪造分数或把它写成掌握证据。
- 当前 v142 使用 AI 初审演示题库；路由只会使用已发布且绑定来源块的题目。AI 初审不构成教师审校、官方教材认证或真实学习效果结论。

## v142 可审计题目导入

仓库提供 `backend/scripts/v18_diagnostic_question_template.json` 模板和受控导入器。导入器接受真实人工审校的 `human_review`，或结论为 `pass` 的 `ai_pre_review`；二者会分别持久化审计信息：

```powershell
cd backend
python scripts/import_v18_diagnostic_questions.py scripts/v18_diagnostic_question_template.json --version-id 142
python scripts/run_v18_engineering_acceptance.py
```

模板中的占位符不能直接导入；它是受控题目导入结构说明，避免把生成内容冒充人工审校资产。

仓库另附 `backend/scripts/v18_v142_engineering_samples.json`：它是明确标注为“非学科人工审校”的工程验证样例，只用于验证已激活的 v142 内容包能被受控题库读取。

2026-11-23 已对本机 active `v142` 运行该工程样例导入，结果为 `created: 1, skipped: 0`。

## 可复现工程样例输出

已执行 `python scripts/run_v18_engineering_acceptance.py`，输出保存在：

`docs/releases/v1.8/engineering-sample-output.json`

该次实际运行使用 v142 的已发布工程题，生成 1 条已确认诊断结论和 3 个周计划项。脚本会创建名称带随机标识的工程学生、目标、诊断和计划记录，保留它们以便本机复核；这些记录不是用户数据。

## 学科审校交接

题库支持两种可审计口径：`human_review` 代表真实人工审校，`ai_pre_review` 代表 AI 初审演示题。两者不会混写；AI 初审不等同于人工或官方教材认证。审核清单、导入命令与质量边界见 [subject_review_handoff.md](subject_review_handoff.md)。

## AI 初审演示题

2026-11-24 已使用 `deepseek-v4-flash` 对 `scripts/v18_v142_ai_review_candidate.json` 运行 AI 初审，输出为 `scripts/v18_v142_ai_reviewed.json`。结论为 `pass`、问题清单为空；随后已导入 active v142（`created: 1, skipped: 0`）。该题及其数据库记录明确标注 `review_mode: ai_pre_review`，仅用作演示题库。
