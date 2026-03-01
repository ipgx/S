#!/usr/bin/env python3
"""Run CMS pipeline for all 7 datasets sequentially."""

import os
import sys
import time
import json

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from cms_pipeline import run_pipeline

DATASETS = ["Apopka", "Hillsborough", "Osceola", "PalmBeach", "Polk", "Seminole", "StLucie"]

def main():
    start = time.time()
    results = {}

    # Process one at a time or a specific one
    target = sys.argv[1] if len(sys.argv) > 1 else None

    for name in DATASETS:
        if target and name.lower() != target.lower():
            continue

        json_path = os.path.join(BASE, f"{name}_segments.json")
        if not os.path.exists(json_path):
            print(f"SKIP {name}: {json_path} not found")
            continue

        t0 = time.time()
        try:
            qa = run_pipeline(json_path)
            results[name] = qa
            elapsed = time.time() - t0
            print(f"  Time: {elapsed/60:.1f} minutes\n")
        except Exception as e:
            print(f"  ERROR: {e}\n")
            results[name] = {"error": str(e)}

    # Summary
    total_time = (time.time() - start) / 60
    print(f"\n{'='*60}")
    print(f"  ALL DATASETS COMPLETE — {total_time:.1f} minutes total")
    print(f"{'='*60}")
    for name, qa in results.items():
        if "error" in qa:
            print(f"  {name:15s}: ERROR — {qa['error']}")
        else:
            print(f"  {name:15s}: {qa.get('geocoded',0):>4} geocoded, {qa.get('routed',0):>4} routed, {qa.get('oob_pct',0):.3f}% OOB")

    with open(os.path.join(BASE, "pipeline_summary.json"), "w") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()
