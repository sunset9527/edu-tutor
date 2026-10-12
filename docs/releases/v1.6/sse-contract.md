# EduTutor v1.6 SSE 事件契约

接口：`POST /api/chat/stream`

请求体与原非流式接口一致：

```json
{"student_id": 1, "session_id": 12, "message": "移项怎么做？"}
```

`session_id` 可省略。后端创建会话后通过响应头 `X-Session-Id` 返回编号。认证继续使用 `Authorization: Bearer <token>`。

每个 SSE 帧包含命名事件和 JSON 数据：

```text
event: response_chunk
data: {"sequence":3,"session_id":12,"timestamp":"2026-10-12T15:30:00","text":"先画图"}

```

## 正常事件顺序

1. `generation_started`
2. `memory_retrieved`：画像摘要、相关记忆、近期事件、被采用候选和完整检索追踪
3. `response_chunk`：LLM 原生流式片段，可出现多次
4. `messages_saved`：本轮用户和助手消息 ID
5. `memory_extracted`：候选、新增、更新、待确认错题/复习建议和非致命提取错误
6. `profile_updated`：最新薄弱点与优势
7. `completed`：完整回答及消息 ID

所有事件包含从 1 递增的 `sequence`、`session_id` 和服务端时间。任一步抛出异常时发送 `failed`，其中包含错误文本。记忆提取内部失败会写进 `memory_extracted.error`，回答和消息仍可完成。

## 兼容策略

- `POST /api/chat` 保留非流式响应，现有调用方无需迁移。
- 会话历史的唯一来源仍是 MySQL `messages` 表。
- 页面刷新通过 `GET /api/sessions/{id}/messages` 恢复，不从浏览器缓存重建内容。
- 事件解析测试覆盖跨网络分片、CRLF、多事件、事件顺序、真实回答片段和失败事件。

