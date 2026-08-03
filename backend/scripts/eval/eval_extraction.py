"""评测1：记忆提取质量（精确率/召回率/F1，多次运行取均值）"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.services.memory.extractor import MemoryExtractor  # noqa: E402

from data.extraction_samples import SAMPLES  # noqa: E402


def hit(gold_obj: str, pred_obj: str) -> bool:
    """命中判断：gold 与提取的 object 存在包含关系（子串匹配）"""
    a, b = gold_obj.strip(), pred_obj.strip()
    return a in b or b in a or (len(a) >= 2 and a[:2] in b) or (len(b) >= 2 and b[:2] in a)


def run_once(use_filter: bool = False) -> dict:
    """单次提取评测（LLM 有随机性）"""
    extractor = MemoryExtractor()
    tp = fp = fn = 0
    per_sample = []

    for s in SAMPLES:
        preds = extractor.extract(s["user"], s["assistant"], enable_filter=use_filter)
        golds = s["gold"]
        matched_gold = set()
        matched_pred = set()
        for gi, g in enumerate(golds):
            for pi, p in enumerate(preds):
                if p.get("predicate") == g["predicate"] and hit(g["object"], p.get("object", "")):
                    matched_gold.add(gi)
                    matched_pred.add(pi)
        s_tp = len(matched_gold)
        s_fp = len(preds) - len(matched_pred)
        s_fn = len(golds) - len(matched_gold)
        tp += s_tp
        fp += s_fp
        fn += s_fn
        per_sample.append({"id": s["id"], "gold": len(golds), "predicted": len(preds), "tp": s_tp, "fp": s_fp, "fn": s_fn})

    return {
        "tp": tp, "fp": fp, "fn": fn,
        "precision": tp / (tp + fp) if tp + fp else 0,
        "recall": tp / (tp + fn) if tp + fn else 0,
        "per_sample": per_sample,
    }


def main(runs: int = 3, use_filter: bool = False) -> None:
    """多次运行取均值（稳健指标）"""
    results = [run_once(use_filter) for _ in range(runs)]
    avg_tp = sum(r["tp"] for r in results) / runs
    avg_fp = sum(r["fp"] for r in results) / runs
    avg_fn = sum(r["fn"] for r in results) / runs
    precision = avg_tp / (avg_tp + avg_fp) if avg_tp + avg_fp else 0
    recall = avg_tp / (avg_tp + avg_fn) if avg_tp + avg_fn else 0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0

    result = {
        "runs": runs, "use_filter": use_filter,
        "per_run": results,
        "avg_tp": round(avg_tp, 2), "avg_fp": round(avg_fp, 2), "avg_fn": round(avg_fn, 2),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }
    out = Path(__file__).parent / "results" / "eval_extraction.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    f1s = []
    for r in results:
        p, rc = r["precision"], r["recall"]
        f1s.append(round(2 * p * rc / (p + rc) if p + rc else 0, 4))
    mode = "带filter" if use_filter else "原版"
    print(f"[评测1 提取质量 {mode} {runs} 次均值] TP={avg_tp:.1f} FP={avg_fp:.1f} FN={avg_fn:.1f}")
    print(f"  精确率 P={precision:.4f}  召回率 R={recall:.4f}  F1={f1:.4f}")
    print(f"  单次 F1: {f1s}")
    print(f"  结果已存: {out}")


if __name__ == "__main__":
    import sys as _sys
    use_filter = "--filter" in _sys.argv
    main(runs=3, use_filter=use_filter)
