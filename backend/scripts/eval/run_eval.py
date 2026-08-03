"""统一入口：跑全部评测"""
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).parent


def main() -> None:
    scripts = [
        "eval_forgetting.py",   # 快，纯数学
        "eval_extraction.py",   # LLM 提取
        "eval_retrieval.py",    # BGE 检索
        "eval_ablation.py",     # LLM 消融（最慢）
    ]
    for s in scripts:
        print(f"\n{'=' * 50}\n>>> 运行 {s}\n{'=' * 50}")
        r = subprocess.run([sys.executable, str(BASE / s)], cwd=BASE)
        if r.returncode != 0:
            print(f"!!! {s} 失败 (exit {r.returncode})")


if __name__ == "__main__":
    main()