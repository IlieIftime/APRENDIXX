"""Run the Phase 5 golden-query gate and persist its aggregate, never query text."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from aprendix.application.search_quality import ALGORITHM_VERSION, evaluate_search
from aprendix.bootstrap import build_runtime, default_data_directory


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=default_data_directory())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    runtime = build_runtime(args.data_dir)
    metrics = evaluate_search(runtime.search_service)
    with runtime.database.transaction() as connection:
        connection.execute(
            """INSERT INTO search_quality_runs(
                id,algorithm_version,query_count,recall_at_10,mrr,ndcg_at_10,
                p95_ms,passed,measured_at) VALUES(?,?,?,?,?,?,?,?,?)""",
            (str(uuid4()), ALGORITHM_VERSION, metrics["query_count"],
             metrics["recall_at_10"], metrics["mrr"], metrics["ndcg_at_10"],
             metrics["p95_ms"], int(metrics["passed"]), datetime.now(UTC).isoformat()),
        )
    payload = json.dumps(metrics, ensure_ascii=False, indent=2)
    print(payload)
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")
    return 0 if metrics["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
