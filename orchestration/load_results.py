"""把 run_job.py 產生的 JSONL 灌進 PostgreSQL。

用法（從專案根目錄）：
    python orchestration/load_results.py data/results.jsonl --batch-id 1
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
from orchestration.db import insert_job_result  # noqa: E402


def load_jsonl(path: str, batch_id: int | None = None) -> int:
    n = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            insert_job_result(json.loads(line), batch_id=batch_id)
            n += 1
    return n


def main():
    parser = argparse.ArgumentParser(description="Load run_job JSONL results into PostgreSQL.")
    parser.add_argument("path", help="JSONL 檔路徑")
    parser.add_argument("--batch-id", type=int, default=None)
    args = parser.parse_args()

    n = load_jsonl(args.path, args.batch_id)
    print(f"已寫入 {n} 筆 job（batch_id={args.batch_id}）")


if __name__ == "__main__":
    main()
