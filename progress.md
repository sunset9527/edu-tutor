# EduTutor v1.8 实施进度

## 2026-11-22

- 已完成 v1.8 设计并提交 `7ac18f0`。
- 用户批准设计并授权开始实施。
- 已读取现有数据库模型、路径服务、访问控制、路由和测试模式。
- 下一步：为学习目标不可变版本写最小失败测试，确认失败后实现模型和服务。
- 已确认第一批实现只包含目标身份、目标版本、目标知识点三个表；诊断和计划表将在各自的失败测试出现后再增加。
- RED：`python -m pytest tests/test_v18_goals.py -q` 因缺少 `app.services.learning_goals` 失败，符合预期。
- 当前：实现目标模型、服务和可回滚迁移，随后将同一测试跑至通过。
- GREEN：本机开发库已升级到 `7efb3126a01c`；同一测试通过（1 passed）。
- 发现并修复：首版测试在服务内部提交后不能依靠 `rollback()` 清理夹具，需显式按依赖顺序删除测试数据。
- 清理第一次未提交：`learning_goals.current_version_id` 仍指向版本，先清空该指针再删除目标版本。
- 修正后已清除首轮遗留夹具，并复跑 `python -m pytest tests/test_v18_goals.py -q`：1 passed。
- 当前：检查第一批改动并提交；下一条 RED 测试覆盖目标版本追加（修改/暂停/恢复/结束）。
- RED：新增追加版本测试因缺少 `append_learning_goal_version` 导入失败，符合预期；当前实现最小追加版本服务。
- GREEN：`python -m pytest tests/test_v18_goals.py -q` 通过（1 passed），确认目标修改追加新版本且原版本不变。
- 下一步：补齐学习目标 API 归属校验，再进入诊断题与诊断会话模型。
- RED：学习目标读取接口不存在，本人请求得到 404。
- GREEN：新增 `GET /api/learning/goals/{student_id}`，复用 `get_owned_student`；本人读取为 200，其他账号为 404，目标集成测试通过。
- 下一步：为目标创建与版本更新补齐写入 API，然后开始诊断领域模型。
