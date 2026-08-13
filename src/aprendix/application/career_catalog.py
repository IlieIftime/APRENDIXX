"""Deterministic professional pathways layered over the course catalogue.

The pathways are advisory DAGs: a learner may inspect every lesson, while
credit and portfolio evidence follow explicit prerequisites.  They deliberately
reuse courses in an N:N relation instead of cloning the same material per role.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CareerStageDefinition:
    slug: str
    title: str
    objective: str
    stage: int
    track_slugs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CareerRoleDefinition:
    slug: str
    title: str
    summary: str
    outcome: str
    area_ids: tuple[str, ...]
    stages: tuple[CareerStageDefinition, ...]


_COMMON_FOUNDATION = CareerStageDefinition(
    "computational-foundation", "Fundamentos computacionais",
    "Transformar problemas em contratos, pseudocódigo e programas Python testáveis.",
    0, ("computer-literacy", "logic-pseudocode", "python-foundations"),
)


CAREER_ROLES: tuple[CareerRoleDefinition, ...] = (
    CareerRoleDefinition(
        "python-software-engineer", "Engenharia de software Python",
        "Percurso para construir aplicações locais e serviços Python legíveis, testados e sustentáveis.",
        "Entregar um projeto Python modular com persistência, API, testes, observabilidade e decisões documentadas.",
        ("python", "oop", "classic-algorithms", "software-engineering", "databases", "web"),
        (
            _COMMON_FOUNDATION,
            CareerStageDefinition("python-design", "Desenho em Python", "Dominar POO, estruturas e algoritmos antes de escolher frameworks.", 1, ("python-oop", "python-algorithms", "python-data-structures")),
            CareerStageDefinition("quality", "Qualidade verificável", "Usar testes, debugging, tipos e contratos como parte do desenho.", 2, ("testing-debugging", "python-advanced")),
            CareerStageDefinition("services", "Dados e serviços", "Modelar persistência e expor contratos HTTP sem misturar camadas.", 3, ("sql-databases", "web-apis")),
            CareerStageDefinition("portfolio", "Entrega profissional", "Integrar arquitetura, testes e documentação num produto demonstrável.", 4, ("python-advanced", "web-apis")),
        ),
    ),
    CareerRoleDefinition(
        "data-analyst", "Analista de dados",
        "Percurso para formular perguntas, preparar dados, calcular métricas e comunicar conclusões reproduzíveis.",
        "Entregar uma análise auditável com SQL, Python, visualizações justificadas e limites explícitos.",
        ("python", "databases", "data-practice", "probability", "time-series-app"),
        (
            _COMMON_FOUNDATION,
            CareerStageDefinition("data-models", "Dados e consultas", "Representar tabelas, validar chaves e escrever transformações reprodutíveis.", 1, ("python-data-structures", "sql-databases")),
            CareerStageDefinition("quantitative-reasoning", "Raciocínio quantitativo", "Interpretar estatística, probabilidade e incerteza sem esconder pressupostos.", 2, ("math-programming", "data-ai")),
            CareerStageDefinition("analysis-quality", "Qualidade da análise", "Detetar leakage, valores ausentes e conclusões que os dados não suportam.", 3, ("testing-debugging", "data-ai")),
            CareerStageDefinition("portfolio", "Relatório profissional", "Produzir um estudo reproduzível que liga pergunta, dados, método e evidência.", 4, ("sql-databases", "data-ai")),
        ),
    ),
    CareerRoleDefinition(
        "machine-learning-engineer", "Engenharia de Machine Learning e IA",
        "Percurso de Python e matemática até pipelines de ML, redes neuronais e agentes avaliáveis.",
        "Entregar um sistema de ML local com baseline, validação, inferência limitada, monitorização e model card.",
        ("python", "linear-algebra", "probability", "classical-ml", "deep-learning", "agent-evaluation"),
        (
            _COMMON_FOUNDATION,
            CareerStageDefinition("algorithmic-core", "Núcleo algorítmico", "Dominar estruturas, complexidade, vetores e probabilidade antes de treinar modelos.", 1, ("python-algorithms", "python-data-structures", "math-programming")),
            CareerStageDefinition("ml-pipelines", "Pipelines de ML", "Separar dados, baseline, treino e avaliação com testes contra leakage.", 2, ("data-ai", "testing-debugging")),
            CareerStageDefinition("model-systems", "Sistemas de modelos", "Integrar inferência, APIs e limites de recursos de forma observável.", 3, ("python-advanced", "web-apis", "data-ai")),
            CareerStageDefinition("portfolio", "Sistema de IA auditável", "Demonstrar qualidade do modelo e do software num cenário aplicado.", 4, ("data-ai", "web-apis")),
        ),
    ),
    CareerRoleDefinition(
        "cybersecurity-automation", "Automação de cibersegurança",
        "Percurso para automatizar análise defensiva com parsing rigoroso, isolamento e rastreabilidade.",
        "Entregar uma ferramenta defensiva local, com modelo de ameaça, mínimo privilégio e testes de abuso.",
        ("python", "systems", "software-engineering", "cybersecurity-app", "databases"),
        (
            _COMMON_FOUNDATION,
            CareerStageDefinition("secure-code", "Código defensivo", "Validar fronteiras, erros, formatos e invariantes sem executar input não confiável.", 1, ("python-oop", "testing-debugging")),
            CareerStageDefinition("automation", "Automação local", "Processar eventos e artefactos com operações limitadas e auditáveis.", 2, ("python-advanced", "python-algorithms")),
            CareerStageDefinition("security-data", "Dados de segurança", "Persistir indicadores e consultar histórico com integridade transacional.", 3, ("sql-databases", "web-apis")),
            CareerStageDefinition("portfolio", "Ferramenta defensiva", "Validar ameaças, controlos e recuperação através de evidência reproduzível.", 4, ("testing-debugging", "python-advanced")),
        ),
    ),
    CareerRoleDefinition(
        "data-engineer", "Engenharia de dados",
        "Percurso para construir pipelines locais fiáveis, modelos de dados e serviços de processamento observáveis.",
        "Entregar um pipeline incremental com contratos, qualidade, idempotência, persistência e recuperação de falhas.",
        ("python", "databases", "data-practice", "systems", "software-engineering"),
        (
            _COMMON_FOUNDATION,
            CareerStageDefinition("data-structures", "Estruturas e modelação", "Escolher representações e chaves segundo os padrões de acesso.", 1, ("python-data-structures", "sql-databases")),
            CareerStageDefinition("pipelines", "Pipelines reprodutíveis", "Construir transformações idempotentes com validação e testes de fronteira.", 2, ("data-ai", "testing-debugging")),
            CareerStageDefinition("reliable-systems", "Sistemas fiáveis", "Controlar concorrência, lotes, transações e recuperação sem perda silenciosa.", 3, ("python-advanced", "sql-databases")),
            CareerStageDefinition("portfolio", "Plataforma de dados", "Integrar ingestão, transformação, armazenamento, métricas e documentação operacional.", 4, ("python-advanced", "sql-databases", "web-apis")),
        ),
    ),
)


def validate_career_definitions() -> dict[str, int]:
    """Fail fast on duplicate identities or non-monotonic local DAG stages."""

    role_slugs = [role.slug for role in CAREER_ROLES]
    if len(role_slugs) != len(set(role_slugs)):
        raise ValueError("career role slugs must be unique")
    for role in CAREER_ROLES:
        stage_slugs = [stage.slug for stage in role.stages]
        if len(stage_slugs) != len(set(stage_slugs)):
            raise ValueError(f"duplicate stage in role {role.slug}")
        if [stage.stage for stage in role.stages] != sorted(stage.stage for stage in role.stages):
            raise ValueError(f"career stages must be topologically ordered: {role.slug}")
        if not all(stage.track_slugs for stage in role.stages):
            raise ValueError(f"career stage without course mapping: {role.slug}")
    return {
        "roles": len(CAREER_ROLES),
        "nodes": sum(len(role.stages) for role in CAREER_ROLES),
        "track_links": sum(
            len(stage.track_slugs) for role in CAREER_ROLES for stage in role.stages
        ),
    }

