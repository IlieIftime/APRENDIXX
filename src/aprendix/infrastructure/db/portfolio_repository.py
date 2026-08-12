"""Transactional storage for guided projects and portfolio evidence."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from uuid import UUID, uuid4

from aprendix.application.contracts import (
    LearningAccessDTO,
    LearningAccessReason,
    PortfolioEntryDTO,
    ProjectTemplateDTO,
)
from aprendix.infrastructure.db.access_policy import override_access, unit_access


# id, track, title, brief, requirements, milestones, level, capstone
CORE_PROJECTS = (
    ("guided-foundations-study-log", "python-foundations", "Diário de estudo no terminal",
     "Cria uma aplicação local que regista sessões, valida entradas e produz um resumo semanal reproduzível.",
     ("Menu textual sem recursão acidental", "Registos representados por estruturas Python explícitas",
      "Validação de datas, durações e campos vazios", "Resumo por dia e por tema com testes"),
     ("Contratos e exemplos de entrada/saída", "Registo e listagem ponta a ponta",
      "Agregações e casos-limite", "Testes, ajuda e revisão final"), "beginner", 0),
    ("capstone-foundations-data-cleaner", "python-foundations", "Laboratório de limpeza de registos",
     "Constrói um pipeline puro que interpreta linhas, normaliza campos, separa erros e gera métricas sem alterar a entrada.",
     ("Formato de entrada e política para valores ausentes", "Pipeline composto por funções pequenas",
      "Relatório de erros por linha", "Testes para vazio, duplicados, Unicode e fronteiras"),
     ("Amostras e critérios de aceitação", "Parser e normalização", "Relatório e métricas",
      "Suite de regressão e documentação"), "intermediate", 1),
    ("guided-oop-library", "python-oop", "Biblioteca orientada a objetos",
     "Modela livros, membros e empréstimos com invariantes, composição e histórico observável.",
     ("Entidades com identidade e valores validados", "Empréstimo sem estados impossíveis",
      "Composição em vez de hierarquia artificial", "Testes que provam isolamento entre instâncias"),
     ("Modelo e invariantes", "Casos de uso principais", "Falhas e histórico",
      "Refactoring e testes"), "intermediate", 0),
    ("capstone-oop-workflow", "python-oop", "Motor de workflows extensível",
     "Implementa estados, comandos e políticas substituíveis para processar pedidos sem condicionais centrais crescentes.",
     ("Protocolos para comandos e políticas", "Transições válidas e inválidas auditáveis",
      "Injeção de dependências e doubles de teste", "Serialização explícita sem executar código"),
     ("Contrato de domínio", "Primeiro workflow", "Extensibilidade e recuperação",
      "Testes de arquitetura e relatório"), "advanced", 1),
    ("guided-algorithms-route", "python-algorithms", "Planeador de rotas auditável",
     "Compara BFS, Dijkstra e uma heurística simples em grafos locais, mostrando caminho, custo e nós visitados.",
     ("Grafo validado e casos sem caminho", "Algoritmos independentes da interface",
      "Reconstrução determinística do caminho", "Medição de operações em grafos distintos"),
     ("Representação e baselines", "BFS e reconstrução", "Dijkstra e comparação",
      "Experiências, testes e conclusões"), "intermediate", 0),
    ("capstone-algorithms-scheduler", "python-algorithms", "Escalonador de tarefas com restrições",
     "Ordena tarefas com dependências, deteta ciclos e produz um plano explicando cada decisão e limite.",
     ("Ordenação topológica estável", "Deteção e descrição de ciclos",
      "Prioridades sem violar pré-requisitos", "Análise de complexidade e testes gerados"),
     ("Contrato e exemplos", "Grafo e ciclos", "Prioridades e explicações",
      "Benchmark, propriedade e documentação"), "advanced", 1),
    ("guided-structures-index", "python-data-structures", "Índice de pesquisa offline",
     "Cria um índice invertido de pequenas notas e compara lista, conjunto, mapa e heap nas operações relevantes.",
     ("Tokenização determinística", "Mapa termo→documentos e frequência",
      "Ranking estável com empates", "Atualização e remoção sem reconstrução total"),
     ("Modelo e corpus de teste", "Indexação e consulta", "Ranking e atualizações",
      "Medições e revisão"), "intermediate", 0),
    ("capstone-structures-cache", "python-data-structures", "Cache LRU com expiração lógica",
     "Implementa uma cache limitada com acesso O(1) médio, ordem LRU e relógio injetado para testes determinísticos.",
     ("Mapa e lista ligada coerentes", "Evicção LRU e atualização de existentes",
      "TTL baseado em relógio colaborador", "Invariantes e testes aleatórios reproduzíveis"),
     ("Contrato e invariantes", "Get/put e evicção", "TTL e recuperação",
      "Testes de propriedade, perfil e relatório"), "advanced", 1),
)


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
            now = datetime.now(UTC).isoformat()
            for (identity, track_slug, title, brief, requirements, milestones,
                 level, capstone) in CORE_PROJECTS:
                rubric = (
                    "correção observável", "arquitetura e invariantes",
                    "testes normais/limite/falha", "complexidade e desempenho",
                    "documentação e decisões",
                )
                connection.execute(
                    """INSERT INTO guided_project_templates(
                       id,track_slug,title,brief,requirements_json,milestones_json,
                       rubric_json,level,capstone,professional_briefing,created_at)
                       VALUES(?,?,?,?,?,?,?,?,?,1,?)
                       ON CONFLICT(id) DO UPDATE SET title=excluded.title,
                       brief=excluded.brief,requirements_json=excluded.requirements_json,
                       milestones_json=excluded.milestones_json,rubric_json=excluded.rubric_json,
                       level=excluded.level,capstone=excluded.capstone,
                       professional_briefing=excluded.professional_briefing""",
                    (identity, track_slug, title, brief,
                     json.dumps(requirements, ensure_ascii=False),
                     json.dumps(milestones, ensure_ascii=False),
                     json.dumps(rubric, ensure_ascii=False), level, capstone, now),
                )

    def templates(self, *, include_quarantined: bool = False) -> tuple[ProjectTemplateDTO, ...]:
        quality_filter = "" if include_quarantined else "WHERE COALESCE(pq.status, 'accepted') = 'accepted'"
        with self._database.read_connection() as connection:
            rows = connection.execute(
                f"""SELECT p.* FROM guided_project_templates p
                    LEFT JOIN pedagogical_quality pq
                      ON pq.item_type='project' AND pq.item_id=p.id
                    {quality_filter}
                    ORDER BY p.track_slug,p.id"""
            ).fetchall()
        return tuple(ProjectTemplateDTO(
            id=row["id"], track_slug=row["track_slug"], title=row["title"],
            brief=row["brief"], requirements=tuple(json.loads(row["requirements_json"])),
            milestones=tuple(json.loads(row["milestones_json"])),
            rubric=tuple(json.loads(row["rubric_json"])), level=row["level"],
            capstone=bool(row["capstone"]),
            professional_briefing=bool(row["professional_briefing"]),
        ) for row in rows)

    def project_context(self, user_id: UUID, project_id: UUID) -> dict[str, object]:
        """Return the immutable template/track context for one owned project."""

        with self._database.read_connection() as connection:
            row = connection.execute(
                """SELECT pp.template_id,pp.work_mode,pp.status,
                          g.track_slug,g.title,g.brief,g.requirements_json,
                          g.milestones_json,g.rubric_json,g.level,g.capstone,
                          g.professional_briefing
                   FROM portfolio_projects pp
                   JOIN guided_project_templates g ON g.id=pp.template_id
                   WHERE pp.project_id=? AND pp.user_id=?""",
                (str(project_id), str(user_id)),
            ).fetchone()
        if row is None:
            raise KeyError("Projeto de portefólio desconhecido.")
        return {
            "template": ProjectTemplateDTO(
                id=row["template_id"], track_slug=row["track_slug"],
                title=row["title"], brief=row["brief"],
                requirements=tuple(json.loads(row["requirements_json"])),
                milestones=tuple(json.loads(row["milestones_json"])),
                rubric=tuple(json.loads(row["rubric_json"])),
                level=row["level"], capstone=bool(row["capstone"]),
                professional_briefing=bool(row["professional_briefing"]),
            ),
            "work_mode": str(row["work_mode"]),
            "status": str(row["status"]),
        }

    def start(self, user_id: UUID, project_id: UUID, template_id: str, work_mode: str) -> None:
        if work_mode not in {"guided", "autonomous"}:
            raise ValueError("Modo de projeto inválido.")
        now = datetime.now(UTC).isoformat()
        with self._database.transaction() as connection:
            template = connection.execute(
                "SELECT milestones_json FROM guided_project_templates WHERE id=?",
                (template_id,),
            ).fetchone()
            owner = connection.execute(
                "SELECT 1 FROM local_projects WHERE id=? AND user_id=?",
                (str(project_id), str(user_id)),
            ).fetchone()
            if template is None:
                raise KeyError("Template de projeto desconhecido.")
            if owner is None:
                raise KeyError("Projeto local desconhecido ou sem autorização.")
            connection.execute(
                """INSERT INTO portfolio_projects(
                   project_id,user_id,template_id,work_mode,status,created_at,updated_at)
                   VALUES(?,?,?,?, 'active',?,?)
                   ON CONFLICT(project_id) DO UPDATE SET updated_at=excluded.updated_at""",
                (str(project_id), str(user_id), template_id, work_mode, now, now),
            )
            count = len(json.loads(template["milestones_json"]))
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

    def record_evaluation(
        self, user_id: UUID, evaluation,
    ) -> tuple[LearningAccessDTO, bool]:
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
            context = connection.execute(
                """SELECT pp.template_id,pp.work_mode,g.track_slug,g.capstone
                   FROM portfolio_projects pp
                   JOIN guided_project_templates g ON g.id=pp.template_id
                   WHERE pp.project_id=? AND pp.user_id=?""",
                (str(evaluation.project_id), str(user_id)),
            ).fetchone()
            if context is None:
                raise KeyError("Projeto de portefólio desconhecido.")
            if (
                evaluation.template_id != context["template_id"]
                or evaluation.track_slug != context["track_slug"]
                or evaluation.work_mode != context["work_mode"]
            ):
                raise ValueError("A avaliação não corresponde ao template e modo do projeto.")
            connection.execute(
                "INSERT INTO project_evaluations VALUES(?,?,?,?,?,?)",
                (str(identity), str(evaluation.project_id), evaluation.score,
                 int(evaluation.passed), payload, now),
            )
            connection.execute(
                "UPDATE portfolio_projects SET status=?,updated_at=? WHERE project_id=? AND user_id=?",
                (status, now, str(evaluation.project_id), str(user_id)),
            )
            project_unit = connection.execute(
                """SELECT u.id FROM learning_units u
                   JOIN learning_chapters c ON c.id=u.chapter_id
                   JOIN learning_tracks t ON t.id=c.track_id
                   WHERE t.slug=? AND u.kind='project'
                   ORDER BY c.position,u.position,u.id LIMIT 1""",
                (context["track_slug"],),
            ).fetchone()
            if project_unit is None:
                return LearningAccessDTO(
                    resource_id=str(evaluation.project_id),
                    resource_kind="project", track_slug=context["track_slug"],
                    reason_code=LearningAccessReason.PROJECT_TEMPLATE_MISMATCH,
                ), False
            access = unit_access(connection, user_id, str(project_unit["id"]))
            if not evaluation.passed:
                return override_access(
                    access, LearningAccessReason.PROJECT_DOMAIN_CONTRACT_FAILED,
                ), False
            if not bool(context["capstone"]):
                return override_access(
                    access, LearningAccessReason.PROJECT_NOT_CAPSTONE,
                ), False
            incomplete_milestones = int(connection.execute(
                """SELECT count(*) FROM project_milestone_state
                   WHERE project_id=? AND completed=0""",
                (str(evaluation.project_id),),
            ).fetchone()[0])
            if incomplete_milestones:
                return override_access(
                    access, LearningAccessReason.PROJECT_MILESTONES_INCOMPLETE,
                ), False
            if not access.credit_eligible:
                return access, False
            cursor = connection.execute(
                """INSERT OR IGNORE INTO learning_unit_progress(
                       user_id,unit_id,completed_at) VALUES(?,?,?)""",
                (str(user_id), access.resource_id, now),
            )
            awarded = cursor.rowcount == 1
            return unit_access(connection, user_id, access.resource_id), awarded

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
