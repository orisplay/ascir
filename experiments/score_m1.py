#!/usr/bin/env python3
"""Score ASCIR M1 detection accuracy from an m1_harness run-file.

Maps each component's resolved registry status to a binary "compromise flagged"
decision, compares to ground truth, and reports the confusion matrix plus
accuracy/precision/recall. Per docs/metrics.md.

Status -> flagged:
  known_good             -> clean (not flagged)
  unknown                -> flagged (artifact absent from trusted registry)
  compromised, contested -> flagged
Ground-truth label -> condition:
  known_good  -> negative (clean); compromised -> positive (variant)
"""
import argparse
import json

FLAGGED_STATUSES = {"unknown", "compromised", "contested"}
CLEAN_STATUSES = {"known_good"}


def is_flagged(status):
    if status in FLAGGED_STATUSES:
        return True
    if status in CLEAN_STATUSES:
        return False
    raise ValueError("unrecognized status: %r" % status)


def score(records):
    tp = tn = fp = fn = 0
    per = []
    status_counts = {}
    for rec in records:
        status = rec["status"]
        status_counts[status] = status_counts.get(status, 0) + 1
        flagged = is_flagged(status)
        positive = rec["ground_truth_label"] == "compromised"
        if positive and flagged:
            cell = "TP"; tp += 1
        elif (not positive) and (not flagged):
            cell = "TN"; tn += 1
        elif (not positive) and flagged:
            cell = "FP"; fp += 1
        else:
            cell = "FN"; fn += 1
        per.append({
            "component_id": rec["component_id"],
            "ground_truth_label": rec["ground_truth_label"],
            "status": status,
            "flagged": flagged,
            "cell": cell,
        })
    total = tp + tn + fp + fn
    accuracy = (tp + tn) / total if total else None
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    summary = {
        "TP": tp, "TN": tn, "FP": fp, "FN": fn, "total": total,
        "accuracy": round(accuracy, 4) if accuracy is not None else None,
        "precision": round(precision, 4) if precision is not None else None,
        "recall": round(recall, 4) if recall is not None else None,
        "raw_status_counts": status_counts,
    }
    return per, summary


def main():
    ap = argparse.ArgumentParser(description="Score ASCIR M1 detection accuracy")
    ap.add_argument("--run", required=True, help="m1_harness run-file (JSON)")
    ap.add_argument("--out", help="result file (else stdout)")
    args = ap.parse_args()

    with open(args.run) as f:
        rdoc = json.load(f)
    per, summary = score(rdoc["records"])
    result = {
        "metric": "M1",
        "n": rdoc.get("n"),
        "chaincode": rdoc.get("chaincode"),
        "fabric_version": rdoc.get("fabric_version"),
        "dataset": rdoc.get("dataset"),
        "timestamp": rdoc.get("timestamp"),
        "per_component": per,
        "summary": summary,
    }
    text = json.dumps(result, indent=2)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text + "\n")
        print("wrote " + args.out)
        print(json.dumps(summary, indent=2))
    else:
        print(text)


if __name__ == "__main__":
    main()
