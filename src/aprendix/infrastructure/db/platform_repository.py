"""Persistence for feature rollout, privacy-safe diagnostics, and baselines."""

from __future__ import annotations

import json

from aprendix.application.contracts import (
    BaselineMetricDTO,
    DiagnosticEventDTO,
    DiagnosticSeverity,
    FeatureFlagDTO,
)
from aprendix.infrastructure.db.database import Database
from aprendix.infrastructure.security import AesGcmFieldCipher


DEFAULT_FEATURE_FLAGS: dict[str, bool] = {
    "ux.design-system-v2": True,
    "ux.command-palette": True,
    "learning.mastery-v2": True,
    "learning.personal-planner": True,
    "curriculum.academy-v2": True,
    "search.pipeline-v2": True,
    "content.signed-packs": True,
    "ide.debugger": True,
    "content.surfaces-v2": True,
    "tutor.offline-v2": True,
    "projects.portfolio-v2": True,
    "mobile.parity-v2": True,
    "assistant.multimodal": True,
    "games.pause-v2": True,
}


class PlatformRepository:
    def __init__(self, database: Database, cipher: AesGcmFieldCipher) -> None:
        self._database = database
        self._cipher = cipher

    def seed_feature_flags(self) -> None:
        with self._database.transaction() as connection:
            for name, enabled in DEFAULT_FEATURE_FLAGS.items():
                connection.execute(
                    """INSERT INTO feature_flags(name,enabled,source,updated_at)
                       VALUES(?,?, 'default', strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                       ON CONFLICT(name) DO UPDATE SET enabled=excluded.enabled,
                       updated_at=excluded.updated_at WHERE feature_flags.source='default'""",
                    (name, int(enabled)),
                )

    def feature_flags(self) -> tuple[FeatureFlagDTO, ...]:
        with self._database.read_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM feature_flags ORDER BY name"
            ).fetchall()
        return tuple(
            FeatureFlagDTO(
                name=row["name"], enabled=bool(row["enabled"]),
                source=row["source"], updated_at=row["updated_at"],
            )
            for row in rows
        )

    def feature_enabled(self, name: str, *, default: bool = False) -> bool:
        with self._database.read_connection() as connection:
            row = connection.execute(
                "SELECT enabled FROM feature_flags WHERE name=?", (name,)
            ).fetchone()
        return bool(row["enabled"]) if row else default

    def set_feature(self, name: str, enabled: bool) -> FeatureFlagDTO:
        flag = FeatureFlagDTO(name=name, enabled=enabled, source="override")
        with self._database.transaction() as connection:
            connection.execute(
                """INSERT INTO feature_flags(name,enabled,source,updated_at)
                   VALUES(?,?,?,?) ON CONFLICT(name) DO UPDATE SET
                   enabled=excluded.enabled,source=excluded.source,
                   updated_at=excluded.updated_at""",
                (flag.name, int(flag.enabled), flag.source, flag.updated_at.isoformat()),
            )
        return flag

    def record_diagnostic(self, event: DiagnosticEventDTO) -> None:
        associated = f"diagnostic_events.context:{event.id}".encode()
        encrypted = self._cipher.encrypt(
            json.dumps(event.context, sort_keys=True, separators=(",", ":")).encode(),
            associated_data=associated,
        )
        with self._database.transaction() as connection:
            connection.execute(
                """INSERT INTO diagnostic_events(
                    id,code,severity,subsystem,message,context_encrypted,occurred_at
                ) VALUES(?,?,?,?,?,?,?)""",
                (str(event.id), event.code, event.severity.value, event.subsystem,
                 event.message, encrypted, event.occurred_at.isoformat()),
            )
            connection.execute(
                """DELETE FROM diagnostic_events WHERE id IN (
                       SELECT id FROM diagnostic_events ORDER BY occurred_at DESC
                       LIMIT -1 OFFSET 2000
                   )"""
            )

    def diagnostics(self, *, limit: int = 100) -> tuple[DiagnosticEventDTO, ...]:
        if not 1 <= limit <= 1000:
            raise ValueError("diagnostic limit must be between 1 and 1000")
        with self._database.read_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM diagnostic_events ORDER BY occurred_at DESC,id LIMIT ?",
                (limit,),
            ).fetchall()
        result = []
        for row in rows:
            event_id = row["id"]
            context = json.loads(self._cipher.decrypt(
                row["context_encrypted"],
                associated_data=f"diagnostic_events.context:{event_id}".encode(),
            ))
            result.append(DiagnosticEventDTO(
                id=event_id, code=row["code"], severity=DiagnosticSeverity(row["severity"]),
                subsystem=row["subsystem"], message=row["message"], context=context,
                occurred_at=row["occurred_at"],
            ))
        return tuple(result)

    def record_metric(self, metric: BaselineMetricDTO) -> None:
        with self._database.transaction() as connection:
            connection.execute(
                """INSERT INTO baseline_metrics(
                    id,name,value,unit,context_json,measured_at
                ) VALUES(?,?,?,?,?,?)""",
                (str(metric.id), metric.name, metric.value, metric.unit,
                 json.dumps(metric.context, sort_keys=True, separators=(",", ":")),
                 metric.measured_at.isoformat()),
            )
            connection.execute(
                """DELETE FROM baseline_metrics WHERE id IN (
                       SELECT id FROM baseline_metrics WHERE name=?
                       ORDER BY measured_at DESC,id LIMIT -1 OFFSET 200
                   )""",
                (metric.name,),
            )

    def metrics(self, name: str, *, limit: int = 30) -> tuple[BaselineMetricDTO, ...]:
        if not 1 <= limit <= 200:
            raise ValueError("metric limit must be between 1 and 200")
        with self._database.read_connection() as connection:
            rows = connection.execute(
                """SELECT * FROM baseline_metrics WHERE name=?
                   ORDER BY measured_at DESC,id LIMIT ?""",
                (name, limit),
            ).fetchall()
        return tuple(BaselineMetricDTO(
            id=row["id"], name=row["name"], value=float(row["value"]), unit=row["unit"],
            context=json.loads(row["context_json"]), measured_at=row["measured_at"],
        ) for row in rows)
