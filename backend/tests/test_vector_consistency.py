"""v1.4 MySQL/Chroma 一致性规则测试。"""

import importlib

from app.models.memory import Memory
from app.services.knowledge import graph_service
from app.services.memory import storage


class FakeCollection:
    def __init__(self):
        self.upserts = []
        self.deletes = []

    def upsert(self, **kwargs):
        self.upserts.append(kwargs)

    def delete(self, **kwargs):
        self.deletes.append(kwargs)


def test_upsert_memory_vector_uses_current_content_and_metadata():
    memory = Memory(
        id=31,
        student_id=4,
        memory_type="semantic",
        content="薄弱点：函数图像",
        structured_data={"predicate": "薄弱点", "object": "函数图像"},
    )
    collection = FakeCollection()

    storage.upsert_memory_vector(
        memory,
        collection=collection,
        embedder=lambda texts: [[0.1, 0.2]],
    )

    payload = collection.upserts[0]
    assert payload["ids"] == ["31"]
    assert payload["documents"] == ["薄弱点：函数图像"]
    assert payload["metadatas"][0] == {
        "student_id": 4,
        "memory_type": "semantic",
        "predicate": "薄弱点",
    }


def test_delete_memory_vector_uses_memory_id():
    collection = FakeCollection()

    storage.delete_memory_vector(31, collection=collection)

    assert collection.deletes == [{"ids": ["31"]}]


def test_audit_detects_all_consistency_problem_types():
    audit = importlib.import_module("scripts.audit_vector_consistency")
    mysql_memories = [
        {
            "id": 1,
            "student_id": 7,
            "status": "active",
            "content": "薄弱点：函数",
            "predicate": "薄弱点",
            "knowledge_point_id": 100,
        },
        {
            "id": 2,
            "student_id": 7,
            "status": "active",
            "content": "已掌握：整数",
            "predicate": "已掌握",
            "knowledge_point_id": 999,
        },
    ]
    chroma_entries = {
        "1": {
            "document": "薄弱点：函数",
            "metadata": {
                "student_id": 999,
                "memory_type": "semantic",
                "predicate": "薄弱点",
            },
        },
        "88": {"document": "孤儿", "metadata": {}},
    }

    report = audit.build_consistency_report(
        mysql_memories,
        chroma_entries,
        valid_knowledge_point_ids={100},
    )

    assert report["missing_vector_ids"] == [2]
    assert report["orphan_vector_ids"] == [88]
    assert report["metadata_error_ids"] == [1]
    assert report["invalid_knowledge_link_ids"] == [2]


def test_recompile_relinks_only_affected_memories():
    affected = [Memory(id=41), Memory(id=42)]

    class Relinker:
        def __init__(self):
            self.ids = []

        def _link_knowledge_point(self, db, memory):
            self.ids.append(memory.id)

    relinker = Relinker()

    count = graph_service.relink_memories(object(), affected, storage=relinker)

    assert count == 2
    assert relinker.ids == [41, 42]
