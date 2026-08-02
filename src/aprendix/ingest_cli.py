"""Explicit desktop command for local content ingestion."""

from __future__ import annotations

import argparse
from pathlib import Path

from aprendix.bootstrap import build_runtime
from aprendix.infrastructure.ingestion import ContentIngestionPipeline, DEFAULT_SOURCE_PATHS


def main() -> int:
    parser = argparse.ArgumentParser(description="Indexar conteúdo local no Aprendix")
    parser.add_argument("paths", nargs="*", type=Path, help="Ficheiros ou diretórios adicionais")
    parser.add_argument("--max-files", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--shard-index", type=int, default=0)
    args = parser.parse_args()
    runtime = build_runtime()
    pipeline = ContentIngestionPipeline(runtime.knowledge)
    sources = tuple(args.paths) if args.paths else DEFAULT_SOURCE_PATHS

    def progress(current: int, total: int, path: Path) -> None:
        print(f"[{current}/{total}] {path}", flush=True)

    summary = pipeline.ingest(
        sources, max_files=args.max_files, dry_run=args.dry_run,
        shard_count=args.shard_count, shard_index=args.shard_index,
        progress=progress
    )
    print(summary.model_dump_json(indent=2))
    return 0 if summary.failed_documents == 0 else 2


def cluster_main() -> int:
    """Explicitly rebuild topic clusters after local ingestion."""

    parser = argparse.ArgumentParser(description="Reconstruir clusters locais do Aprendix")
    parser.add_argument("--min-cluster-size", type=int, default=5)
    args = parser.parse_args()
    runtime = build_runtime()
    from aprendix.application.clustering import HdbscanClusterService

    assignments = HdbscanClusterService(
        runtime.knowledge, min_cluster_size=args.min_cluster_size
    ).rebuild()
    cluster_count = len({item.cluster_id for item in assignments if item.cluster_id != "noise"})
    print(f"Clustering concluído: {len(assignments)} chunks, {cluster_count} clusters.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
