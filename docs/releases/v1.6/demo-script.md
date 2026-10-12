# EduTutor v1.6 端到端演示与录屏清单

## 启动前检查

```powershell
cd E:\python\Graduation\EduTutor\backend
python -m alembic upgrade head
uvicorn app.main:app --reload --port 8000

cd E:\python\Graduation\EduTutor\frontend
npm run dev
```

确认 `/health` 的 `mysql` 为 `ok`，浏览器 Network 面板保留日志。

## 演示路径

1. 登录并选择已有学生，记录学生姓名和当前记忆总数。
2. 在对话页提问一个与已有薄弱点相关的问题。
3. 展示回答逐片段出现；侧栏依次出现本轮命中、新增或更新，不口述尚未出现的数据。
4. 若出现待确认任务，点击确认加入复习计划或错题本。
5. 刷新页面，确认原会话和数据库消息恢复。
6. 进入智能出题页，选数据库返回的科目，生成练习；点击“我错了”确认入错题本。
7. 进入记忆库，展示当前 λ、真实时间起算的曲线并完成一次复习。
8. 进入知识图谱，打开一个知识点的个性路径，展示掌握度、推荐原因和预计复习时间。
9. 进入学习报告，展示新增错题、掌握度变化和复习完成率；鼠标悬停显示组成数据点的 `learning_events` ID。

## 录屏后核对

- 登录信息、API Key 和本机密码未出现在画面中。
- Network 中 `/api/chat/stream` 的事件顺序与契约一致。
- 刷新后消息内容与刷新前一致。
- 页面数字与本次实际操作一致，没有使用预填演示数字。
- 录屏文件名记录日期、Git 提交和使用的学生 ID。

