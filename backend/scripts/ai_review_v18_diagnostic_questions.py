"""使用已配置模型对候选诊断题做 AI 初审；输出仍需显式标注 AI 身份。"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.core.llm import create_llm


def run(source: Path, output: Path) -> list[dict]:
    if not settings.llm_configured:
        raise ValueError("未配置 LLM，无法进行 AI 初审")
    rows = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        raise ValueError("题目文件必须是非空 JSON 数组")
    reviewed = []
    for row in rows:
        prompt = (
            "你是小学数学诊断题 AI 初审员。只输出 JSON："
            '{"decision":"pass|needs_revision","issues":[字符串],"summary":字符串}。'
            "检查题干、选项、答案/评分规则、难度和歧义；没有问题才 pass。\n"
            f"题目：{json.dumps(row, ensure_ascii=False)}"
        )
        content = str(create_llm(temperature=0.0).invoke(prompt).content).strip()
        audit = json.loads(content.removeprefix("```json").removesuffix("```").strip())
        if audit.get("decision") not in {"pass", "needs_revision"}:
            raise ValueError("AI 返回了无效初审结论")
        reviewed.append({**row, "review_mode": "ai_pre_review", "ai_model": settings.deepseek_model, "ai_review": audit})
    output.write_text(json.dumps(reviewed, ensure_ascii=False, indent=2), encoding="utf-8")
    return reviewed


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps({"reviewed": len(run(args.source, args.output)), "output": str(args.output)}, ensure_ascii=False))
