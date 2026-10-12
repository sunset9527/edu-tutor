# EduTutor v1.6 验收报告

验收日期：2026-10-12  
版本主题：前端学习闭环与可解释过程

## 1. 交付范围

- 新增 `POST /api/chat/stream`，按固定契约发送检索、原生回答片段、消息保存、记忆提取、画像更新、完成和失败事件；保留原 `/api/chat`。
- 新增归属校验后的会话消息查询。浏览器按账号和学生保存会话 ID，刷新时从 MySQL 恢复消息。
- 记忆列表支持服务端类型筛选与分页，科目列表读取数据库。
- 学习路径返回逐步理由、掌握度、到期状态、预计复习时间和证据 ID。
- 新增 `learning_events`，掌握变化、错题新增/掌握、复习成功/失败在业务事务内记录。报告按日聚合真实事件并保留事件 ID。
- 对话页显示本轮命中、新增和更新，并让用户确认错题或复习建议；复习计划确认接口幂等。
- 记忆曲线使用当前 `decay_lambda`、真实强度及最近复习/创建时间。报告页展示真实事件时间序列。

## 2. 数据库迁移

迁移：`7c1e6a9d4b20_add_learning_events.py`

`learning_events.student_id` 在学生删除时级联清理；知识点删除时事件保留并把 `knowledge_point_id` 置空。迁移已执行 `upgrade head`，并实际验证一次 downgrade/upgrade。历史记录不回填，因此 v1.6 上线前的报告时间线为空是预期行为。

## 3. 自动化验收

### 后端

```powershell
cd backend
python -m pytest -k "not test_chat_flow and not test_extractor_returns_json" -q
```

结果：**64 项通过**。两个排除项会调用真实 DeepSeek，未把外部网络与计费调用纳入离线门禁。

v1.6 专项测试为 **9 项通过**，覆盖 SSE 编码与顺序、失败事件、会话归属与恢复、记忆分页筛选、数据库科目、复习建议幂等确认、报告聚合和事件 ID 回查。

### 前端

```powershell
cd frontend
npm run typecheck
npm test
npm run build
```

结果：TypeScript 检查通过；Vitest **3 个文件、5 项测试通过**；Vite 生产构建通过。构建仍提示 ECharts 相关主包超过 500 kB，功能不受影响，代码拆包留给性能版本。

### 双库一致性

```powershell
cd backend
python scripts/audit_vector_consistency.py
```

最终只读审计：缺失记忆向量、孤儿记忆向量、元数据错误、无效知识点关联四项均为 **0**。首次完整回归因旧测试清理被新外键阻挡，留下一个 `user_id=null`、随机 `v15-*` 名称的测试学生和一条记忆；核验来源后仅删除该测试残留，再次审计为零，没有修改业务记录或补造数据。

## 4. 可追溯性

- SSE 契约：`docs/releases/v1.6/sse-contract.md`
- 确定性测试事件样例：`docs/releases/v1.6/event-sample.json`
- 演示与录屏清单：`docs/releases/v1.6/demo-script.md`
- 时间序列的每个数据点返回组成它的 `learning_events.id`。
- 路径步骤返回 `memory_ids`、`wrong_question_ids` 和 `review_plan_ids`。

## 5. 边界

- 本次未执行真实 LLM 质量验收和浏览器网络断线重连压力测试。
- 录屏清单已完成，实际录屏文件需要在启动前后端并准备演示学生后由人工执行。
- v1.6 不增加前端知识编译入口，知识构建继续使用 CLI。
- 本次测试证明工程流程和数据可追溯，没有产生或声称新的学习效果指标。

## 6. 结论

v1.6 路线图中的流式对话、会话恢复、过程可视化、真实报告时间线、动态记忆曲线、数据库科目和可确认任务均已交付。离线自动化门禁全部通过，适合进入 v1.7 的评测协议与统一质量门禁迭代。

