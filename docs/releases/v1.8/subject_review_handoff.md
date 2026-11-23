# v1.8 诊断题学科审校交接包

工程已实现受控导入和验收门禁，但学科内容不能由工程人员或模型冒充审校完成。本包供小学数学学科审核人完成正式发布前的最后一步。

## 审校输入

- 题目模板：`backend/scripts/v18_diagnostic_question_template.json`
- 当前目标版本：active `v142`（二年级下册数学）
- 每题必须绑定该版本中的知识点与教材来源块；不得使用 `provenance_gap=true` 的知识点。

## 逐题检查

- 题干、选项、答案/评分规则与目标知识点一致。
- 难度标记符合“基础 / 进阶 / 拔高”。
- 客观题有明确 `answer_key.value`；主观题有可执行的 `rubric`。
- 不含诱导性、歧义性或超出当前教材范围的表述。
- 填写真实的 `reviewed_by` 与具体 `review_note`；不得填写“AI 审校”或虚构姓名。

## 导入与验收

```powershell
cd backend
python scripts/import_v18_diagnostic_questions.py <审校后的题目.json> --version-id 142
python scripts/run_v18_engineering_acceptance.py
```

第二个命令会生成 `docs/releases/v1.8/engineering-sample-output.json`。该 JSON 只能证明工程闭环可复现，不能替代题目学科质量结论或真实学习效果评估。
