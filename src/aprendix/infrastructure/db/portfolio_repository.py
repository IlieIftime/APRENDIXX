"""Transactional storage for guided projects and portfolio evidence."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from uuid import UUID, uuid4

from aprendix.application.contracts import PortfolioEntryDTO, ProjectTemplateDTO


class PortfolioRepository:
    def __init__(self, database, cipher) -> None:
        self._database, self._cipher = database, cipher

    def seed(self) -> None:
        with self._database.transaction() as connection:
            tracks = connection.execute(
                "SELECT slug,title,position FROM learning_tracks ORDER BY position,slug"
            ).fetchall()
            for track in tracks:
                slug = re.sub(r"[^a-z0-9-]", "-", track["slug"].casefold()).strip("-")
                identity = "capstone-" + slug
                title = f"Projeto final · {track['title']}"
                brief = (
                    f"Constrói uma aplicação local verificável que demonstre as competências de "
                    f"{track['title']}. Começa por clarificar entradas, saídas e restrições; entrega "
                    "código legível, testes e uma nota curta sobre decisões e limites."
                )
                requirements = (
                    "Definir um contrato observável de entrada e saída",
                    "Implementar pelo menos três casos de uso e respetivos limites",
                    "Incluir testes determinísticos e tratamento explícito de erros",
                    "Documentar decisões, compromissos e instruções de execução",
                )
                milestones = (
                    "Briefing e critérios de aceitação",
                    "Modelo e primeira execução ponta a ponta",
                    "Testes, refactoring e casos-limite",
                    "Revisão final e relatório de competências",
                )
                rubric = ("correção", "estrutura", "testes", "qualidade", "documentação")
                connection.execute(
                    """INSERT OR IGNORE INTO guided_project_templates(
                       id,track_slug,title,brief,requirements_json,milestones_json,
                       rubric_json,level,capstone,professional_briefing,created_at)
                       VALUES(?,?,?,?,?,?,?,?,1,?,?)""",
                    (identity, track["slug"], title, brief,
                     json.dumps(requirements, ensure_ascii=False),
                     json.dumps(milestones, ensure_ascii=False),
                     json.dumps(rubric, ensure_ascii=False),
                      ("beginner" if track["position"] < 4 else
                      "intermediate" if track["position"] < 8 else "advanced"),
                     int(track["position"] >= 8),
                     datetime.now(UTC).isoformat()),
                )

    def templates(self) -> tuple[ProjectTemplateDTO, ...]:
        with self._database.read_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM guided_project_templates ORDER BY track_slug,id"
            ).fetchall()
        return tuple(ProjectTemplateDTO(
            id=row["id"], track_slug=row["track_slug"], title=row["title"],
            brief=row["brief"], requirements=tuple(json.loads(row["requirements_json"])),
            milestones=tuple(json.loads(row["milestones_json"])),
            rubric=tuple(json.loads(row["rubric_json"])), level=row["level"],
            capstone=bool(row["capstone"]),
            professional_briefing=bool(row["professional_briefing"]),
        ) for row in rows)

    def start(self, user_id: UUID, project_id: UUID, template_id: str, work_mode: str) -> None:
        if work_mode not in {"guided", "autonomous"}:
            raise ValueError("Modo de projeto inválido.")
        now = datetime.now(UTC).isoformat()
        with self._database.transaction() as connection:
            connection.execute(
                """INSERT INTO portfolio_projects(
                   project_id,user_id,template_id,work_mode,status,created_at,updated_at)
                   VALUES(?,?,?,?, 'active',?,?)
                   ON CONFLICT(project_id) DO UPDATE SET updated_at=excluded.updated_at""",
                (str(project_id), str(user_id), template_id, work_mode, now, now),
            )
            count = len(json.loads(connection.execute(
                "SELECT milestones_json FROM guided_project_templates WHERE id=?",
                (template_id,),
            ).fetchone()[0]))
            connection.executemany(
                "INSERT OR IGNORE INTO project_milestone_state VALUES(?,?,0,NULL)",
                ((str(project_id), ordinal) for ordinal in range(count)),
            )

    def set_milestone(self, user_id: UUID, project_id: UUID, ordinal: int, completed: bool) -> None:
        now = datetime.now(UTC).isoformat()
        with self._database.transaction() as connection:
            owner = connection.execute(
                "SELECT 1 FROM portfolio_projects WHERE project_id=? AND user_id=?",
                (str(project_id), str(user_id)),
            ).fetchone()
            if owner is None:
                raise KeyError("Projeto de portefólio desconhecido.")
            cursor = connection.execute(
                """UPDATE project_milestone_state SET completed=?,completed_at=?
                   WHERE project_id=? AND ordinal=?""",
                (int(completed), now if completed else None, str(project_id), ordinal),
            )
            if cursor.rowcount != 1:
                raise IndexError("Milestone de projeto desconhecido.")

    def record_evaluation(self, user_id: UUID, evaluation) -> None:
        identity, now = uuid4(), evaluation.evaluated_at.isoformat()
        payload = self._cipher.encrypt(
            json.dumps({
                "findings": evaluation.findings,
                "skills": evaluation.demonstrated_skills,
                "rubric": evaluation.rubric_scores,
            }, ensure_ascii=False).encode(),
            associated_data=f"project_evaluations.result:{identity}".encode(),
        )
        status = "passed" if evaluation.passed else "revision"
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO project_evaluations VALUES(?,?,?,?,?,?)",
                (str(identity), str(evaluation.project_id), evaluation.score,
                 int(evaluation.passed), payload, now),
            )
            connection.execute(
                "UPDATE portfolio_projects SET status=?,updated_at=? WHERE project_id=? AND user_id=?",
                (status, now, str(evaluation.project_id), str(user_id)),
            )

    def entries(self, user_id: UUID) -> tuple[PortfolioEntryDTO, ...]:
        with self._database.read_connection() as connection:
            rows = connection.execute(
                """SELECT pp.*,g.title,pe.score,pe.result_encrypted,pe.id evaluation_id
                   FROM portfolio_projects pp
                   JOIN guided_project_templates g ON g.id=pp.template_id
                   LEFT JOIN project_evaluations pe ON pe.id=(
                     SELECT id FROM project_evaluations WHERE project_id=pp.project_id
                     ORDER BY evaluated_at DESC LIMIT 1)
                   WHERE pp.user_id=? ORDER BY pp.updated_at DESC""", (str(user_id),)
            ).fetchall()
        result = []
        for row in rows:
            skills = ()
            if row["result_encrypted"] is not None:
                payload = json.loads(self._cipher.decrypt(
                    row["result_encrypted"],
                    associated_data=f"project_evaluations.result:{row['evaluation_id']}".encode(),
                ))
                skills = tuple(payload.get("skills", ()))
            result.append(PortfolioEntryDTO(
                project_id=UUID(row["project_id"]), template_id=row["template_id"],
                title=row["title"], work_mode=row["work_mode"], status=row["status"],
                score=row["score"], demonstrated_skills=skills,
                updated_at=datetime.fromisoformat(row["updated_at"]),
            ))
        return tuple(result)
