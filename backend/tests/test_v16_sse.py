"""v1.6 SSE 契约与流式编排单元测试。"""

import json
from types import SimpleNamespace

from app.services.chat_stream import encode_sse, stream_chat_events


class FakeRetriever:
    def retrieve(self, _student_id, _query):
        return {
            "profile_summary": "学习偏好：图示",
            "relevant_memories": ["薄弱点：移项"],
            "recent_events": [],
            "trace": {
                "candidates": [
                    {
                        "memory_id": 9,
                        "content": "薄弱点：移项",
                        "selected": True,
                        "reason": "selected",
                    }
                ]
            },
        }

    def build_injection_text(self, _result):
        return "【学生画像】\n学习偏好：图示"


class FakeStreamingLLM:
    def stream(self, _messages):
        yield SimpleNamespace(content="先画图")
        yield SimpleNamespace(content="，再移项。")


class FakeKnowledgeRetriever:
    def retrieve(self, _student_id, _query):
        return {
            "active_version_ids": [21],
            "candidates": [
                {
                    "knowledge_point_id": 31,
                    "title": "移项",
                    "content": "移项要改变符号。",
                    "version_id": 21,
                    "version_no": 2,
                    "source_chunk_id": 41,
                    "page_range": [12, 13],
                    "similarity": 0.91,
                    "adopted": True,
                    "legacy": False,
                    "textbook": {"id": 11},
                }
            ],
            "retrieval_config": {"similarity_threshold": 0.55},
        }


def test_encode_sse_uses_named_event_and_json_data():
    frame = encode_sse("response_chunk", {"sequence": 3, "text": "第一步"})
    assert frame.startswith("event: response_chunk\n")
    assert frame.endswith("\n\n")
    payload = json.loads(frame.split("data: ", 1)[1])
    assert payload == {"sequence": 3, "text": "第一步"}


def test_stream_chat_events_has_stable_order_and_real_chunks():
    saved = []

    def save_messages(_session_id, user_text, answer):
        saved.append((user_text, answer))
        return [31, 32]

    events = list(
        stream_chat_events(
            student_id=4,
            session_id=7,
            user_message="移项怎么做？",
            retriever=FakeRetriever(),
            knowledge_retriever=FakeKnowledgeRetriever(),
            llm=FakeStreamingLLM(),
            history_loader=lambda _session_id: [],
            message_saver=save_messages,
            memory_processor=lambda **_kwargs: {
                "candidates": [{"predicate": "薄弱点", "object": "移项"}],
                "written_count": 1,
                "new_memories": [{"id": 41, "content": "薄弱点：移项"}],
                "updated_memories": [],
                "suggestions": [],
            },
            profile_loader=lambda _student_id: {
                "weaknesses": ["移项"],
                "strengths": [],
            },
            evidence_recorder=lambda **_kwargs: {
                "id": 51,
                "assistant_message_id": 32,
            },
        )
    )

    assert [event["event"] for event in events] == [
        "generation_started",
        "memory_retrieved",
        "knowledge_retrieved",
        "response_chunk",
        "response_chunk",
        "messages_saved",
        "evidence_recorded",
        "memory_extracted",
        "profile_updated",
        "completed",
    ]
    assert [event["data"]["sequence"] for event in events] == list(range(1, 11))
    assert "".join(
        event["data"]["text"]
        for event in events
        if event["event"] == "response_chunk"
    ) == "先画图，再移项。"
    assert saved == [("移项怎么做？", "先画图，再移项。")]
    assert events[2]["data"]["candidates"][0]["knowledge_point_id"] == 31
    assert events[6]["data"]["evidence_ledger_id"] == 51
    assert events[-1]["data"]["response"] == "先画图，再移项。"


def test_stream_chat_events_finishes_with_failed_event():
    class BrokenRetriever:
        def retrieve(self, *_args):
            raise RuntimeError("vector unavailable")

    events = list(
        stream_chat_events(
            student_id=4,
            session_id=7,
            user_message="测试",
            retriever=BrokenRetriever(),
            llm=FakeStreamingLLM(),
        )
    )

    assert [event["event"] for event in events] == [
        "generation_started",
        "failed",
    ]
    assert events[-1]["data"]["error"] == "vector unavailable"


def test_stream_chat_events_degrades_when_only_knowledge_retrieval_fails():
    class BrokenKnowledgeRetriever:
        def retrieve(self, *_args):
            raise RuntimeError("knowledge unavailable")

    events = list(
        stream_chat_events(
            student_id=4,
            session_id=7,
            user_message="测试",
            retriever=FakeRetriever(),
            knowledge_retriever=BrokenKnowledgeRetriever(),
            llm=FakeStreamingLLM(),
            history_loader=lambda _session_id: [],
            message_saver=lambda *_args: [31, 32],
            evidence_recorder=lambda **_kwargs: {
                "id": 51,
                "memory_evidence": [],
            },
            memory_processor=lambda **_kwargs: {
                "candidates": [],
                "written_count": 0,
                "new_memories": [],
                "updated_memories": [],
                "suggestions": [],
            },
            profile_loader=lambda _student_id: {
                "weaknesses": [],
                "strengths": [],
            },
        )
    )

    assert events[-1]["event"] == "completed"
    knowledge = next(row for row in events if row["event"] == "knowledge_retrieved")
    assert knowledge["data"]["error"] == "knowledge unavailable"
    assert knowledge["data"]["evidence_gap"]["reasons"] == [
        "knowledge_retrieval_failed"
    ]
