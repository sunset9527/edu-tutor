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
6. 已提交诊断可生成带原因和容量状态的周计划。
7. 其他账号读取学生目标时被拒绝。

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

已通过：v1.8 端到端集成测试、诊断模型测试、迁移往返、前端类型检查、Vitest 11 项和生产构建。

## 全量后端回归边界

`python -m pytest -q` 当前在既有 `tests/test_knowledge.py::test_pdf_extract_text` 停止：测试依赖的三年级上册 PDF 固定路径在本机不存在。失败发生在 v1.8 测试之前，与本版迁移和诊断/计划逻辑无关；补回教材文件或改为显式夹具前，不能声称后端完整回归全绿。

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
