"""LLM Wiki 编译器：教材文本 → 互链知识点（仿 Karpathy LLM Wiki 模式）

输出 JSON 数组：
[{"title", "difficulty", "content_md", "prerequisites": [标题], "related": [标题]}]
"""
import json
import logging
import re

from app.core.llm import create_llm

logger = logging.getLogger(__name__)

COMPILE_PROMPT = """你是{subject}{grade}教材的知识点编译员。下面是《{chapter}》的教材文本。

请抽取「可独立教学的知识点」，只输出一个 JSON 数组，不要输出任何其他文字：
[{{"title": "知识点标题", "difficulty": "基础|进阶|拔高", "content_md": "正文", "prerequisites": ["前置知识点标题"], "related": ["相关知识点标题"]}}]

规则：
1. 粒度：一个知识点 = 一个可独立教学的概念/技能/定理（如"一元一次方程""移项"）
2. title 用教材标准术语，简洁（不超过 12 字）
3. prerequisites/related 只填本批知识点中真实存在的标题，没有则填 []
4. content_md 用中文 markdown：概念解释 + 要点 + 关键公式（公式用 $...$），150~300 字
5. 抽取 5~10 个知识点，按教材顺序排列

教材文本：
{text}"""


class WikiCompiler:
    def __init__(self):
        # 编译任务生成长 JSON，超时放宽到 180 秒
        self.llm = create_llm(temperature=0.0, request_timeout=180)

    def compile_chapter(
        self, subject: str, grade: str, chapter: str, text: str
    ) -> list[dict]:
        """编译一章文本 → 知识点列表"""
        # 截断保护（DeepSeek 上下文足够，但避免意外超长）
        text = text[:20000]
        prompt = COMPILE_PROMPT.format(
            subject=subject, grade=grade, chapter=chapter, text=text
        )
        try:
            resp = self.llm.invoke(prompt)
            points = self._parse(resp.content)
            logger.info(f"编译「{chapter}」: {len(points)} 个知识点")
            return points
        except Exception as e:  # noqa: BLE001
            logger.error(f"编译「{chapter}」失败: {e}")
            return []

    def _parse(self, content: str) -> list[dict]:
        if not content:
            return []
        text = content.strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text).strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            start, end = text.find("["), text.rfind("]")
            if start == -1 or end == -1 or end <= start:
                logger.warning(f"编译结果无法解析: {content[:200]}")
                return []
            try:
                data = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                logger.warning(f"编译结果 JSON 解析失败: {content[:200]}")
                return []
        if not isinstance(data, list):
            return []
        cleaned = []
        for item in data:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            content_md = str(item.get("content_md", "")).strip()
            if not title or not content_md:
                continue
            cleaned.append(
                {
                    "title": title,
                    "difficulty": item.get("difficulty", "基础"),
                    "content_md": content_md,
                    "prerequisites": [
                        str(x).strip() for x in item.get("prerequisites", []) or []
                    ],
                    "related": [str(x).strip() for x in item.get("related", []) or []],
                }
            )
        return cleaned
