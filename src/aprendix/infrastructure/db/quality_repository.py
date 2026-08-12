"""SQLite persistence for pedagogical quality compiler decisions."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime

from aprendix.application.contracts import (
    PedagogicalQualityAuditDTO,
    PedagogicalQualityDTO,
    QualityCheckDTO,
)


class PedagogicalQualityRepository:
    def __init__(self, database) -> None:
        self._database = database

    def exercise_source_counts(self, exercise_ids: tuple[str, ...]) -> dict[str, int]:
        if not exercise_ids:
            return {}
        counts: dict[str, int] = {}
        for offset in range(0, len(exercise_ids), 500):
            batch = exercise_ids[offset:offset + 500]
            marks = ",".join("?" for _ in batch)
            with self._database.read_connection() as connection:
                rows = connection.execute(
                    f"SELECT exercise_id,count(*) amount FROM exercise_source_links WHERE exercise_id IN ({marks}) GROUP BY exercise_id",
                    batch,
                ).fetchall()
            counts.update({row["exercise_id"]: int(row["amount"]) for row in rows})
        return counts

    def replace(self, audit: PedagogicalQualityAuditDTO,
                results: tuple[PedagogicalQualityDTO, ...]) -> None:
        now = audit.generated_at.isoformat()
        with self._database.transaction() as connection:
            connection.execute("DELETE FROM pedagogical_quality")
            connection.executemany(
                """INSERT INTO pedagogical_quality(
                   item_type,item_id,quality_score,estimated_difficulty,status,
                   generator_version,fingerprint,checks_json,audited_at)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                [(
                    item.item_type, item.item_id, item.quality_score,
                    item.estimated_difficulty, item.status, item.generator_version,
                    audit.fingerprint,
                    json.dumps([check.model_dump(mode="json") for check in item.checks], ensure_ascii=False),
                    now,
                ) for item in results],
            )
            connection.execute(
                """INSERT INTO pedagogical_quality_runs(
                   fingerprint,total,accepted,quarantined,average_score,by_type_json,generated_at)
                   VALUES(?,?,?,?,?,?,?) ON CONFLICT(fingerprint) DO UPDATE SET
                   total=excluded.total,accepted=excluded.accepted,
                   quarantined=excluded.quarantined,average_score=excluded.average_score,
                   by_type_json=excluded.by_type_json,generated_at=excluded.generated_at""",
                (audit.fingerprint, audit.total, audit.accepted, audit.quarantined,
                 audit.average_score, json.dumps(audit.by_type, sort_keys=True), now),
            )

    def summary(self, *, fingerprint: str | None = None) -> PedagogicalQualityAuditDTO | None:
        with self._database.read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM pedagogical_quality_runs "
                + ("WHERE fingerprint=? " if fingerprint else "")
                + "ORDER BY generated_at DESC LIMIT 1",
                (fingerprint,) if fingerprint else (),
            ).fetchone()
        if row is None:
            return None
        return PedagogicalQualityAuditDTO(
            fingerprint=row["fingerprint"], total=row["total"],
            accepted=row["accepted"], quarantined=row["quarantined"],
            average_score=row["average_score"], by_type=json.loads(row["by_type_json"]),
            generated_at=datetime.fromisoformat(row["generated_at"]),
        )

    def results(self, *, status: str | None = None, limit: int = 100):
        if status not in {None, "accepted", "quarantined"}:
            raise ValueError("invalid quality status")
        parameters: list[object] = []
        where = ""
        if status:
            where, parameters = "WHERE status=?", [status]
        parameters.append(max(1, min(limit, 5_000)))
        with self._database.read_connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM pedagogical_quality {where} ORDER BY quality_score,item_type,item_id LIMIT ?",
                parameters,
            ).fetchall()
        return tuple(PedagogicalQualityDTO(
            item_type=row["item_type"], item_id=row["item_id"],
            quality_score=row["quality_score"],
            estimated_difficulty=row["estimated_difficulty"], status=row["status"],
            generator_version=row["generator_version"],
            checks=tuple(QualityCheckDTO(**item) for item in json.loads(row["checks_json"])),
        ) for row in rows)
