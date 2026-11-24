# v1.8 诊断题学科审校交接包

工程已实现受控导入和验收门禁。题库可采用真实人工审校，或采用明确标注的 AI 初审演示口径；两者不得混同。

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

## AI 初审演示口径

```powershell
cd backend
python scripts/ai_review_v18_diagnostic_questions.py <候选题目.json> <AI初审输出.json>
python scripts/import_v18_diagnostic_questions.py <AI初审输出.json> --version-id 142
```

只有模型结论为 `pass` 的题目才会导入。导入记录会保存 `review_mode=ai_pre_review`、模型名、审查结论、问题清单与审查时间；它不是人工签署，也不能描述为教师审定题库。
