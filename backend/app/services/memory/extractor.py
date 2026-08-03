"""记忆提取器：LLM 从辅导对话中抽取值得长期记住的结构化信息

输出 JSON 数组：
[{"type": "semantic|episodic|procedural", "predicate": "...", "object": "...", "confidence": 0.9, "conflict": false}]
"""
import json
import logging
import re

from app.core.llm import create_llm

logger = logging.getLogger(__name__)

EXTRACT_SYSTEM_PROMPT = """你是一名学生记忆提取器。从辅导对话中提取「值得长期记住」的信息，用于构建学生的长期记忆。

已有学生画像（避免重复提取，只提取画像中还没有的新信息）：
{profile_summary}

对话记录：
学生：{user_message}
老师：{ai_response}

只输出一个 JSON 数组，不要输出任何其他文字。格式：
[{{"type": "semantic|episodic|procedural", "predicate": "薄弱点|已掌握|学习偏好|学习事件|错题|有效策略", "object": "具体内容", "confidence": 0.9, "conflict": false}}]

规则：
1. 只提取跨会话有用的信息（画像、学习事件、错题、有效策略），日常寒暄、客套、语气词不提取
2. 对话中没有依据的信息不要提取
3. 提取的信息与已有画像冲突时，conflict 设为 true
4. 一条对话可能提取 0~5 条；没有值得提取的信息时输出 []
5. predicate 只用：薄弱点 / 已掌握 / 学习偏好 / 学习事件 / 错题 / 有效策略
6. object 要具体、可读（如"解方程中的移项"而不是"数学问题"）"""


class MemoryExtractor:
    def __init__(self):
        self.llm = create_llm(temperature=0.0)

    def extract(
        self,
        user_message: str,
        ai_response: str,
        profile_summary: str = "",
    ) -> list[dict]:
        """从一轮对话中提取记忆项"""
        prompt = EXTRACT_SYSTEM_PROMPT.format(
            profile_summary=profile_summary or "（无）",
            user_message=user_message,
            ai_response=ai_response,
        )
        try:
            resp = self.llm.invoke(prompt)
            return self._parse(resp.content)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"记忆提取失败: {e}")
            return []

    def _parse(self, content: str) -> list[dict]:
        """解析 LLM 输出为 JSON 列表（容错处理）"""
        if not content:
            return []
        text = content.strip()
        # 去掉可能的 ```json 包裹
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text).strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # 尝试截取第一个 [ 到最后一个 ]
            start, end = text.find("["), text.rfind("]")
            if start == -1 or end == -1 or end <= start:
                logger.warning(f"无法解析提取结果: {content[:200]}")
                return []
            try:
                data = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                logger.warning(f"JSON 解析失败: {content[:200]}")
                return []
        if not isinstance(data, list):
            return []
        # 清洗字段
        cleaned = []
        for item in data:
            if not isinstance(item, dict):
                continue
            mtype = item.get("type", "episodic")
            if mtype not in {"semantic", "episodic", "procedural"}:
                mtype = "episodic"
            predicate = str(item.get("predicate", "信息")).strip()
            obj = str(item.get("object", "")).strip()
            if not obj:
                continue
            cleaned.append(
                {
                    "type": mtype,
                    "predicate": predicate,
                    "object": obj,
                    "confidence": float(item.get("confidence", 0.7)),
                    "conflict": bool(item.get("conflict", False)),
                }
            )
        return cleaned
