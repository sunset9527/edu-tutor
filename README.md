# EduTutor — 个性化教育智能体（毕设）

基于 LangChain/LangGraph 的智能体记忆增强系统——以个性化教育辅导为例。

> 毕设 + 产品双定位。系统设计见 `E:\个人发展\002职业\项目4：个性化教育\个性化教育-系统设计.md`，
> 版本规划见同目录 `个性化教育-产品迭代路线图.md`。

## 已实现



### v0.5 — 评测实验（2026-08-03）
- 🧪 **记忆提取质量**：P=0.567 / R=0.850 / F1=0.680（15 轮标注对话，召回率高、存在过度提取，调优方向：置信度阈值）
- 🎯 **记忆检索效果**：Hit@3 = 1.000 / MRR = 0.730（12 条查询，全命中 top-3）
- 🔬 **消融实验（核心）**：有记忆 vs 无记忆（6 场景 × LLM-as-judge 1-5 分）
  - 个性化：**4.33 vs 1.50**（+2.83）
  - 连贯性：**5.00 vs 4.00**（+1.00）
  - 正确性：**4.83 vs 4.67**（+0.17）
- 📉 **遗忘机制验证**：30 天后保留率，间隔复习 0.0498 vs 不复习 0.0299；复习后记忆强度 0.6→1.0
- 📊 图表产出：scripts/eval/results/（eval_ablation.png + eval_forgetting.png + 4 个 JSON）
- 🔧 数据诚信：所有结果可复现（`python scripts/eval/run_eval.py`），标注集/查询集/评分记录全部入库
### v0.4 — Vue3 前端（2026-08-02）
- 🏗️ 前端骨架：Vite6 + Vue3 + TS + Pinia + Element Plus + ECharts（axios 封装 / router / 学生 store）
- 💬 辅导对话页：ChatView + **记忆面板侧边栏**（对话后实时刷新记忆，可视化记忆提取过程）
- 👤 学生管理页：学生列表 + 新建 + 画像卡片（薄弱点/已掌握标签 + ECharts 雷达图）
- 🧠 记忆库页：记忆卡片流（按类型筛选）+ **遗忘曲线 ECharts 图** + 复习打卡（成功/遗忘）
- 🕸️ 知识图谱页：ECharts 力导向图（113 节点，难度着色，前置/相关线型区分）+ 点击节点看详情
- 📊 学习报告页：待复习计划（遗忘曲线调度）+ 错题本 + 薄弱点摘要
- 🔌 前后端联通：Vite proxy `/api` → FastAPI 8000（已验证：图谱统计/学生列表/记忆/复习计划）
### v0.3 — 遗忘曲线 + 知识引擎（2026-08-02）
- 🧠 遗忘曲线（SM-2 简化）：保留率 `R = strength × e^(-λt)`，复习成功强度↑间隔×2 / 失败强度×0.5 间隔重置
- 📅 复习调度：`review_plans` 表，记忆写入自动建计划，到期可查（`ReviewScheduler`），API：复习打卡 / 计划查询
- 🔍 检索遗忘加权：向量召回按保留率重排（`retriever._vector_search`）
- 📚 知识引擎（LLM Wiki 模式）：PDF 课本 → 知识点互链图谱 → `knowledge_points` + `knowledge_point_links` + `knowledge_vectors`
- 📊 知识库（人教版数学七年级上册，已编译+去重）：**113 个知识点 / 223 条边 / 连接率 92.9%**
- 🔗 双引擎桥：记忆写入自动关联知识点（`knowledge_point_id`）

### v0.2 — 记忆引擎 MVP（2026-08-02）
- 🧠 记忆提取：LLM 从对话抽取结构化记忆（`extractor.py`）
- 🧠 记忆存储：MySQL + ChromaDB 双写，冲突消解，画像快照（`storage.py`）
- 🧠 记忆检索：多路召回（画像 + 向量 + 最近事件）注入 Prompt（`retriever.py`）
- ✅ 跨会话记忆验证：新会话能记得学生上次的薄弱点和学习内容

### v0.1 — 基建（2026-08-02）
- FastAPI 骨架 + MySQL 8（本机 `edu_tutor` 库，10 张表，Alembic 迁移）
- LangGraph 对话流：`load_history → generate → save_messages`（短期记忆）
- 学生 CRUD + 对话 API

## 快速启动

```bash
cd backend
# 1. 配置 .env（MySQL 已默认 root/123456；填 DEEPSEEK_API_KEY）
# 2. 建库 + 迁移
python scripts/create_db.py
alembic upgrade head
# 3. 编译知识库（可选，知识引擎）
python scripts/build_knowledge.py "<教材PDF路径>" --subject 数学 --grade 初一
# 4. 启动前端（终端2）
uvicorn app.main:app --reload --port 8000
cd ../frontend && npm run dev   # 前端 http://localhost:3000
# 5. 测试
pytest
```

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/students | 创建学生 |
| GET | /api/students | 学生列表 |
| POST | /api/chat | 辅导对话（自动建会话/续会话） |
| GET | /health | 健康检查 |
