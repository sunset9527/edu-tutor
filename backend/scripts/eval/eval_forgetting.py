"""评测4：遗忘曲线机制验证（纯数学模拟）
- SM-2 复习序列模拟（成功/失败路径）
- 不同 λ 衰减对比
"""
import json
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.services.memory.forgetting import (  # noqa: E402
    calculate_retention,
    review_failure,
    review_success,
)


def simulate_review_sequence() -> dict:
    """模拟一条记忆（strength=0.6）按 SM-2 复习：第1/3/7/15天复习"""
    strength = 0.6
    interval = 1
    schedule = [1, 3, 7, 15]  # 复习日
    days = list(range(0, 31))
    retention = []
    for d in days:
        retention.append(round(calculate_retention(strength, d), 4))
        if d in schedule:
            strength, interval = review_success(strength, interval)
    return {"days": days, "retention": retention, "final_strength": round(strength, 4)}


def simulate_no_review() -> dict:
    strength = 0.6
    days = list(range(0, 31))
    retention = [round(calculate_retention(strength, d), 4) for d in days]
    return {"days": days, "retention": retention}


def lambda_compare() -> dict:
    days = list(range(0, 31))
    lambdas = [0.05, 0.1, 0.2]
    series = {}
    for lam in lambdas:
        series[f"λ={lam}"] = [round(calculate_retention(0.6, d, lambda_=lam), 4) for d in days]
    return {"days": days, "series": series}


def main() -> None:
    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)

    reviewed = simulate_review_sequence()
    no_review = simulate_no_review()
    lam_series = lambda_compare()

    # 图1：复习 vs 不复习
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    ax = axes[0]
    ax.plot(reviewed["days"], reviewed["retention"], label="SM-2 间隔复习", color="#67c23a", lw=2)
    ax.plot(no_review["days"], no_review["retention"], label="不复习", color="#f56c6c", lw=2, ls="--")
    ax.set_title("遗忘曲线：复习 vs 不复习")
    ax.set_xlabel("天数")
    ax.set_ylabel("保留率 R")
    ax.legend()
    ax.grid(alpha=0.3)

    ax2 = axes[1]
    for name, vals in lam_series["series"].items():
        ax2.plot(lam_series["days"], vals, label=name, lw=1.8)
    ax2.set_title("遗忘速率 λ 对比（strength=0.6）")
    ax2.set_xlabel("天数")
    ax2.set_ylabel("保留率 R")
    ax2.legend()
    ax2.grid(alpha=0.3)

    fig.tight_layout()
    fig_path = results_dir / "eval_forgetting.png"
    fig.savefig(fig_path, dpi=120)
    plt.close(fig)

    result = {
        "reviewed_final_strength": reviewed["final_strength"],
        "reviewed_day30_retention": reviewed["retention"][-1],
        "no_review_day30_retention": no_review["retention"][-1],
        "lambda_series": lam_series["series"],
        "figure": str(fig_path),
    }
    (results_dir / "eval_forgetting.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[评测4 遗忘机制] 30天后保留率：复习={result['reviewed_day30_retention']} vs 不复习={result['no_review_day30_retention']}")
    print(f"  最终记忆强度: {result['reviewed_final_strength']}")
    print(f"  图已存: {fig_path}")


if __name__ == "__main__":
    main()