# EduTutor v1.4 验收报告

验收日期：2026-10-12  
版本主题：核心正确性与真实性基线  
结论：通过

## 交付范围

- 修复未复习记忆的衰减起点，并实现可循环的复习计划状态机。
- 将记忆冲突改为事实槽位规则：多薄弱点共存，单值事实覆盖，同知识点“薄弱点/已掌握”互斥。
- 让 `extract_min_confidence` 进入实际写入流程。
- 对记忆新增、编辑、归档、删除和冲突淘汰执行 MySQL/Chroma 同步及失败补偿。
- 增加默认只读、仅 `--apply` 修改数据的一致性审计脚本。
- 知识图谱重编译后重新关联本次受影响的记忆。
- 学生、会话、记忆、复习计划、错题和报告统一执行账号归属校验。
- 修复报告页，接入学习路径入口，并把 `vue-tsc --noEmit` 加入生产构建前置步骤。

## 自动化验证

### 后端

执行命令：

```powershell
python -m pytest tests -q -p no:cacheprovider -k "not test_chat_flow and not test_extractor_returns_json"
```

结果：36 项离线测试全部通过。覆盖内容包括：

- 连续三次成功复习后仍有下一条 `pending` 计划，间隔增长至 8 天。
- 未复习记忆从 `created_at` 开始衰减。
- 多薄弱点共存；单值冲突写入 `memory_conflicts` 并删除旧向量。
- 编辑记忆后向量文档同步，归档后向量删除。
- 向量写入失败时 MySQL 不保留半成品。
- 匿名访问返回 401，跨账号访问学生域资源返回 404。

两个真实 LLM 用例未纳入离线门禁：`test_chat_flow`、`test_extractor_returns_json`。本次版本没有改动 LLM 提示词或供应商调用，它们继续由显式的在线测试执行。

### 前端

```powershell
npm run typecheck
npm run build
```

结果：类型检查通过，Vite 生产构建通过。构建包含报告页、学习路径入口和练习页 API 类型修复。

### 静态检查

```powershell
python -m compileall -q app scripts tests
git diff --check
```

结果：通过。`git diff --check` 只有 Git 的 LF/CRLF 转换提示，没有空白错误。

## MySQL/Chroma 一致性

修复前 dry-run：

- 缺失向量：22
- 孤儿向量：9
- metadata 错误：0
- 失效知识点关联：0

执行 `python scripts/audit_vector_consistency.py --apply` 后，脚本内置复审四项均为 0。完成全部测试后再次执行只读审计，四项仍为 0。详细记录见 `vector-audit.json`。

修复前 Chroma 备份：`backend/data/chroma_db.backup-v1.4-20261012`。原库与备份均为 10 个文件、11,592,886 字节。备份属于本地数据，不提交 Git。

## 已知非阻塞提示

- LangGraph 依赖发出 `allowed_objects` 默认值未来变化提示。
- JWT 代码仍使用 `datetime.utcnow()`，Python 3.13 发出弃用提示；当前 token 测试通过，后续安全维护版本再迁移时区感知时间。
- Vite 对 `@vueuse/core` 的 PURE 注释位置和大于 500 kB 的 chunk 给出提示；不影响本次构建，包体拆分放到性能优化版本。
- `npm install` 报告 8 个依赖漏洞（3 moderate、5 high）；本次未运行可能产生破坏性升级的 `npm audit fix --force`。

## 验收结论

v1.4 路线图中的功能、测试、双库修复、前端门禁和账号隔离均已交付。历史评测数字未修改，也未把离线测试结果外推为真实学习效果。
