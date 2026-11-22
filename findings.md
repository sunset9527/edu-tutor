# EduTutor v1.8 实施发现

## 现有架构

- 后端入口为 `backend/app/main.py`；所有 API 路由由此注册。
- 数据库为 SQLAlchemy 2 + Alembic；当前最新迁移为 `31b933ce603d_add_v17_knowledge_governance.py`。
- `get_owned_student(db, student_id, user_id)` 是学生归属校验标准入口。
- `Textbook.active_version_id` 表示受控知识的当前发布版本。
- `KnowledgePoint` 已拥有 `version_id`、`source_chunk_id` 与 `provenance_gap`，足以限制可发布诊断题。
- `KnowledgePointLink(link_type="prerequisite")` 存储先修关系。
- 既有个性化路径服务读取掌握记忆、未掌握错题和到期复习，v1.8 计划服务可只读复用这些事实。
- 前端为 Vue 3、Element Plus 与 Vitest；`eduApi` 是前端 API 类型和调用的集中入口。

## 风险与约束

- 现有测试既有直接数据库夹具，也有 FastAPI `TestClient` 集成测试；新测试应清理自己创建的所有记录。
- 教材源文件和真实 `v142` 数据不可作为自动化测试隐式前置；样例导入脚本必须显式校验 active 版本。
- 主观评分模型可能不可用，必须先实现不伪造分数的待确认/重试状态。

## 第二轮实现准备

- v1.7 的 Alembic 迁移采用显式手写 SQLAlchemy DDL；v1.8 将延续此风格，并按目标、诊断、计划三个能力阶段拆分迁移，降低回滚和定位风险。
- 现有 MySQL 集成测试以随机 token 创建数据、在 `finally` 中按外键反向清理。
- v1.8 第一条测试应验证“创建目标时固定 active 知识版本并生成不可变首个版本”，先以缺少服务模块失败，再补齐最小目标模型、服务和迁移。

## RED 结果

- `python -m pytest tests/test_v18_goals.py -q` 已观察到预期失败：`ModuleNotFoundError: No module named 'app.services.learning_goals'`。
- `Student.user_id` 可为空，但 v1.8 API 会通过既有 `get_owned_student` 强制账号归属；服务层只处理已授权学生的领域创建。
- Alembic 导入 `app.models` 注册元数据，因此新增模型必须补充 `app/models/__init__.py` 的导入和 `__all__`。

## 第一轮 GREEN 结果

- 开发库迁移 `31b933ce603d -> 7efb3126a01c` 已成功执行。
- `python -m pytest tests/test_v18_goals.py -q` 通过（1 passed）。
- 沙箱不能连接本机 MySQL；涉及数据库迁移或集成测试时需要受控提升权限执行。
- 领域服务会提交事务，因此集成测试不能仅对同一 session 调用 `rollback()`；必须显式删除已提交夹具。
- `learning_goals.current_version_id` 与 `learning_goal_versions` 是循环引用，数据清理顺序为：先清空 current 指针，再删 targets、versions、goals。
- 目标版本追加可安全复制上一版本的 `knowledge_version_id`、学科、目标水平和目标知识点；目标日期、每周时间、状态与调整原因是本次变更字段。
- `GET /api/learning/goals/{student_id}` 已由既有学生归属校验保护；所有后续学习 API 应在任何资源查询前调用同一校验。
