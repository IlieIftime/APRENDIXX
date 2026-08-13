"""Validated metadata and original learning copy derived from official docs.

The JSON snapshot is built by ``scripts/build_official_source_catalog.py`` from
official sitemaps and exact page titles/headings.  This module never downloads
content and never stores documentation body text.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class OfficialSourceSpec:
    id: str
    family: str
    area_id: str
    title: str
    author: str
    url: str
    sitemap_url: str
    headings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OfficialConceptSpec:
    slug: str
    term: str
    technology: str
    area_id: str
    source_id: str
    source_title: str
    concept: str
    definition: str
    signature: str
    example: str
    related: tuple[str, ...]
    card_bucket: str
    glossary_bucket: str


class FactFactory(Protocol):
    def __call__(
        self, *, slug: str, area_id: str, fact: str, explanation: str,
        formula_or_code: str = "", complexity: str = "intermediate",
        source_ids: tuple[str, ...] = (), card_format: str = "concept",
        visual_hint: str = "",
        formula_latex: str = "", formula_spoken: str = "",
        formula_variables: tuple[tuple[str, str], ...] = (),
        formula_worked_example: str = "",
    ): ...


_FAMILY = {
    "python": ("Python", "python"),
    "pytest": ("pytest", "software-engineering"),
    "pypa": ("Python Packaging", "software-engineering"),
    "nist-dads": ("NIST Algorithms", "classic-algorithms"),
    "linux": ("Linux kernel", "systems"),
    "docker": ("Docker", "systems"),
    "postgresql": ("PostgreSQL", "databases"),
    "pandas": ("pandas", "data-practice"),
    "mongodb": ("MongoDB", "databases"),
    "spark": ("Apache Spark", "data-practice"),
    "pytorch": ("PyTorch", "deep-learning"),
    "sklearn": ("scikit-learn", "classical-ml"),
    "tensorflow": ("TensorFlow", "deep-learning"),
    "opencv": ("OpenCV", "computer-vision"),
    "spacy": ("spaCy", "natural-language"),
    "mlflow": ("MLflow", "software-engineering"),
    "owasp": ("OWASP", "cybersecurity-app"),
    "mitre-attack": ("MITRE ATT&CK", "cybersecurity-app"),
    "fastapi": ("FastAPI", "web"),
    "kubernetes": ("Kubernetes", "systems"),
    "w3c-wcag": ("WCAG", "responsible-ai"),
    "nist-airc": ("NIST AI RMF", "responsible-ai"),
}
_EXPECTED_QUOTAS = {
    "python": 35, "pytest": 25, "pypa": 20,
    "nist-dads": 25, "linux": 25, "docker": 20,
    "postgresql": 30, "pandas": 25, "mongodb": 25, "spark": 20,
    "pytorch": 30, "sklearn": 30, "tensorflow": 20, "opencv": 15,
    "spacy": 10, "mlflow": 15, "owasp": 45, "mitre-attack": 25,
    "fastapi": 10, "kubernetes": 25, "w3c-wcag": 15, "nist-airc": 10,
}
OFFICIAL_SOURCE_QUOTAS = dict(_EXPECTED_QUOTAS)
OFFICIAL_CARD_BUCKET_QUOTAS = {
    "python": 220, "software-backend-testing": 120,
    "databases-data-engineering": 140, "mathematics-analytics": 150,
    "ai-ml": 220, "cybersecurity": 100,
    "systems-ethics-professional": 50,
}
OFFICIAL_GLOSSARY_BUCKET_QUOTAS = {
    "advanced-python": 100, "algorithms-discrete-math": 140,
    "databases-data-engineering": 160, "statistics-ai": 180,
    "cybersecurity-networks-systems": 160, "web-architecture-devops": 100,
    "analytics-visualization": 80, "quality-accessibility-ethics-performance": 80,
}
_CARD_BUCKET_FAMILIES = {
    "python": ("python", "pypa"),
    "software-backend-testing": ("pytest", "fastapi", "mlflow"),
    "databases-data-engineering": ("postgresql", "pandas", "mongodb", "spark"),
    "mathematics-analytics": ("nist-dads", "sklearn", "pandas", "pytorch"),
    "ai-ml": ("pytorch", "sklearn", "tensorflow", "opencv", "spacy", "mlflow", "nist-airc"),
    "cybersecurity": ("owasp", "mitre-attack"),
    "systems-ethics-professional": ("linux", "docker", "kubernetes", "w3c-wcag", "nist-airc"),
}
_GLOSSARY_BUCKET_FAMILIES = {
    "cybersecurity-networks-systems": ("owasp", "mitre-attack", "linux", "docker", "kubernetes", "pytest"),
    "quality-accessibility-ethics-performance": ("w3c-wcag", "nist-airc", "pytest", "mlflow", "linux"),
    "web-architecture-devops": ("fastapi", "kubernetes", "docker", "pypa", "pytest", "mlflow"),
    "advanced-python": ("python", "pypa", "pytest"),
    "analytics-visualization": ("pandas", "opencv", "spark", "sklearn", "tensorflow"),
    "databases-data-engineering": ("postgresql", "pandas", "mongodb", "spark", "mlflow"),
    "algorithms-discrete-math": ("nist-dads", "python", "sklearn", "pandas", "linux"),
    "statistics-ai": ("sklearn", "pytorch", "tensorflow", "opencv", "spacy", "nist-airc", "mlflow"),
}
_BASE_SOURCE_IDS = {
    "docker": "src-docker", "fastapi": "src-fastapi",
    "postgresql": "src-postgresql", "pytorch": "src-pytorch-autograd",
    "pytest": "src-pytest", "numpy": "src-numpy", "pandas": "src-pandas",
    "sklearn": "src-sklearn",
    "python": "src-python-docs", "pypa": "src-python-packaging",
    "nist-dads": "src-clrs", "linux": "src-git", "mongodb": "src-mongodb",
    "spark": "src-pandas", "tensorflow": "src-dlbook", "opencv": "src-resnet",
    "spacy": "src-rag", "mlflow": "src-sklearn", "fastapi": "src-fastapi",
    "kubernetes": "src-docker", "w3c-wcag": "src-ai-index",
    "nist-airc": "src-ai-index",
    "owasp": "src-nist-cybersecurity-framework",
    "mitre-attack": "src-nist-cybersecurity-framework",
}
_GENERIC_HEADINGS = frozenset({
    "sponsors", "opinions", "overview", "contents", "table of contents",
    "submit correction", "see also", "examples", "reference", "references",
    "how can we help?", "what's new", "next", "previous", "on this page",
    "docker docs", "fastapi", "pytorch documentation", "documentation",
    "navigation", "footer", "main content", "search", "summary", "introduction",
})


def _fold(value: str) -> str:
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold()


def _identifier(family: str, url: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
    return f"src-official-{family}-{digest}"


def _load_sources() -> tuple[OfficialSourceSpec, ...]:
    path = Path(__file__).with_name("official_source_catalog.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("policy") != "official-sitemap-and-html-title-metadata-only":
        raise ValueError("official source snapshot has an unknown provenance policy")
    sources: list[OfficialSourceSpec] = []
    for raw in payload.get("sources", ()):
        family = str(raw["family"])
        if family not in _FAMILY:
            raise ValueError(f"unknown official documentation family: {family}")
        sources.append(OfficialSourceSpec(
            id=_identifier(family, str(raw["url"])), family=family,
            area_id=str(raw["area"]), title=str(raw["title"]),
            author=str(raw["author"]), url=str(raw["url"]),
            sitemap_url=str(raw["sitemap_url"]),
            headings=tuple(str(item) for item in raw.get("headings", ())),
        ))
    counts = {family: sum(item.family == family for item in sources) for family in _FAMILY}
    if counts != _EXPECTED_QUOTAS:
        raise ValueError(f"official source snapshot quotas changed: {counts}")
    if len({item.url for item in sources}) != len(sources):
        raise ValueError("official source snapshot contains duplicate URLs")
    return tuple(sources)


OFFICIAL_SOURCES = _load_sources()
_SOURCE_FAMILY_BY_ID = {item.id: item.family for item in OFFICIAL_SOURCES}
_FAMILY_SOURCE_IDS = {
    family: tuple(item.id for item in OFFICIAL_SOURCES if item.family == family)
    for family in _FAMILY
}


def _supporting_source_ids(item: OfficialConceptSpec) -> tuple[str, str]:
    family = _SOURCE_FAMILY_BY_ID[item.source_id]
    secondary = _BASE_SOURCE_IDS.get(family)
    if secondary is None:
        family_ids = _FAMILY_SOURCE_IDS[family]
        position = family_ids.index(item.source_id)
        secondary = family_ids[(position + 1) % len(family_ids)]
    return item.source_id, secondary


def _page_topic(source: OfficialSourceSpec) -> str:
    title = re.sub(
        r"\s*(?:—|-|\|)\s*(?:Docker Docs|FastAPI|PyTorch[^|—]*documentation).*$",
        "", source.title, flags=re.IGNORECASE,
    ).strip()
    title = re.sub(r"^PostgreSQL:\s*Documentation:\s*\d+:\s*", "", title)
    return title or source.title


def _learning_copy(family: str, topic: str) -> tuple[str, str, str, tuple[str, ...]]:
    technology, area = _FAMILY[family]
    if family in {"python", "pypa"}:
        return (
            f"Em {technology}, {topic} deve ser lido como um contrato entre entradas, estado e resultado observável.",
            "Confirma a assinatura, os tipos, as exceções e um caso-limite com um exemplo local mínimo.",
            "entrada + contrato -> resultado verificável",
            ("Python", "contract", "edge case"),
        )
    if family == "docker":
        return (
            f"Em Docker, {topic} deve tornar explícita a fronteira entre imagem, configuração e processo em execução.",
            "Confirma inputs de build, permissões, persistência e estado observável do contentor.",
            "imagem + configuração -> processo isolado",
            ("container", "image", "least privilege"),
        )
    if family == "fastapi":
        return (
            f"Em FastAPI, {topic} integra o contrato HTTP com tipos, validação e uma resposta observável.",
            "Testa pedido válido, erro de validação e código de estado sem depender de rede externa.",
            "pedido tipado -> validação -> resposta",
            ("HTTP", "type annotation", "validation"),
        )
    if family == "postgresql":
        return (
            f"Em PostgreSQL, {topic} deve ser analisado pelo efeito no modelo, na transação e no plano de execução.",
            "Verifica integridade, concorrência e custo com um exemplo pequeno antes de escalar.",
            "consulta + esquema + estado transacional -> resultado",
            ("SQL", "transaction", "query plan"),
        )
    if family == "pytorch":
        return (
            f"Em PyTorch, {topic} participa num cálculo tensorial cujo dispositivo, dtype, forma e gradiente devem ser explícitos.",
            "Confirma shapes, dtype, device e fluxo de gradiente com um tensor mínimo.",
            "tensor + operação -> tensor e grafo de gradiente",
            ("tensor", "autograd", "shape"),
        )
    if family == "pytest":
        return (
            f"Em pytest, {topic} deve produzir evidência reproduzível sobre um contrato observável.",
            "Mantém cada teste determinístico, isola o estado e inclui um caso normal e uma fronteira.",
            "preparação -> ação -> verificação",
            ("fixture", "assertion", "regression"),
        )
    if family == "pandas":
        return (
            f"Em pandas, {topic} transforma dados rotulados; índice, schema e valores ausentes fazem parte do contrato.",
            "Confirma colunas, tipos, cardinalidade e tratamento de nulos antes e depois da transformação.",
            "tabela + índice + regra -> tabela validada",
            ("DataFrame", "index", "missing data"),
        )
    if family in {"sklearn", "tensorflow", "mlflow"}:
        return (
            f"Em {technology}, {topic} deve ser integrado sem fuga de dados entre treino, validação e teste.",
            "Usa uma pipeline, fixa a divisão de avaliação e mede uma baseline antes de aumentar a complexidade.",
            "dados -> pipeline fit/transform -> métrica fora da amostra",
            ("estimator", "pipeline", "cross-validation"),
        )
    if family in {"owasp", "mitre-attack"}:
        return (
            f"Na engenharia segura, {topic} deve ser tratado como uma relação entre ativo, ameaça, controlo e evidência.",
            "Testa o controlo num ambiente isolado, incluindo abuso previsível, sem executar payloads contra terceiros.",
            "ativo + ameaça -> controlo preventivo + verificação",
            ("threat model", "input validation", "least privilege"),
        )
    if family in {"nist-airc", "w3c-wcag"}:
        return (
            f"Na gestão responsável de IA, {topic} exige contexto, risco, responsável e evidência mensurável.",
            "Regista pressupostos, impacto, limites e uma medida verificável antes da decisão de utilização.",
            "contexto + risco + controlo -> evidência e decisão",
            ("AI risk", "measurement", "governance"),
        )
    if area == "classic-algorithms":
        return (
            f"Em algoritmos, {topic} exige invariantes e custos de tempo e memória explícitos.",
            "Percorre um exemplo pequeno à mão e testa vazio, repetição e fronteiras do domínio.",
            "entrada + invariante -> passos -> resultado",
            ("algorithm", "invariant", "complexity"),
        )
    if area == "systems":
        return (
            f"Em sistemas, {topic} relaciona recursos, isolamento, estado e observabilidade.",
            "Confirma permissões mínimas, falhas previsíveis e recuperação sem depender de serviços externos.",
            "recurso + política -> estado observável",
            ("system", "isolation", "observability"),
        )
    if area == "databases":
        return (
            f"Em {technology}, {topic} deve respeitar o modelo, a integridade e a estratégia de acesso.",
            "Testa consistência, cardinalidade e comportamento transacional com um conjunto pequeno.",
            "dados + esquema + operação -> estado consistente",
            ("database", "integrity", "query"),
        )
    if area == "data-practice":
        return (
            f"Em {technology}, {topic} transforma dados cujo schema, escala e valores ausentes devem ser explícitos.",
            "Mede linhas, colunas, tipos e nulos antes e depois da transformação.",
            "dados validados -> transformação -> dados auditáveis",
            ("data pipeline", "schema", "validation"),
        )
    if area in {"computer-vision", "natural-language"}:
        return (
            f"Em {technology}, {topic} liga uma representação de entrada a uma transformação e uma medida de qualidade.",
            "Verifica forma ou tokenização, pressupostos do modelo e uma amostra adversa simples.",
            "representação -> modelo -> métrica e erro",
            ("representation", "model", "evaluation"),
        )
    return (
        f"Em {technology}, {topic} deve explicitar entradas, contrato, riscos e resultado observável.",
        "Compara um caso normal e um caso-limite com a documentação oficial antes de generalizar.",
        "entrada + contrato -> resultado + evidência",
        ("contract", "boundary", "evidence"),
    )


def _concepts() -> tuple[OfficialConceptSpec, ...]:
    candidates: dict[str, list[tuple[OfficialSourceSpec, str]]] = {
        family: [] for family in _FAMILY
    }
    for source in OFFICIAL_SOURCES:
        topics = [_page_topic(source)]
        topics.extend(
            heading for heading in source.headings
            if _fold(heading).strip() not in _GENERIC_HEADINGS
            and len(heading.split()) <= 16
        )
        for topic in dict.fromkeys(topics):
            if _fold(topic).strip() in _GENERIC_HEADINGS:
                continue
            candidates[source.family].append((source, topic))
    result: list[OfficialConceptSpec] = []
    seen_terms: set[str] = set()
    positions = {family: 0 for family in _FAMILY}
    for card_bucket, quota in OFFICIAL_CARD_BUCKET_QUOTAS.items():
        families = _CARD_BUCKET_FAMILIES[card_bucket]
        bucket_start = len(result)
        while len(result) - bucket_start < quota:
            progressed = False
            for family in families:
                if len(result) - bucket_start == quota:
                    break
                family_candidates = candidates[family]
                while positions[family] < len(family_candidates):
                    source, topic = family_candidates[positions[family]]
                    positions[family] += 1
                    technology, area_id = _FAMILY[source.family]
                    base_term = f"{technology} · {topic}"
                    term = base_term
                    normalized = _fold(term)
                    if normalized in seen_terms:
                        qualifier = _page_topic(source)
                        term = f"{base_term} ({qualifier})"
                        normalized = _fold(term)
                    if normalized in seen_terms:
                        continue
                    seen_terms.add(normalized)
                    mechanism, check, signature, related = _learning_copy(family, topic)
                    digest = hashlib.sha256(f"{source.id}:{topic}".encode()).hexdigest()[:20]
                    result.append(OfficialConceptSpec(
                        slug=f"official-{source.family}-{digest}", term=term,
                        technology=technology.casefold(), area_id=area_id,
                        source_id=source.id, source_title=source.title, concept=topic,
                        definition=f"{mechanism} {check}", signature=signature,
                        example=(
                            f"Antes de aplicar {topic}, escreve um caso normal e um caso-limite "
                            "e compara o resultado com o contrato oficial."
                        ),
                        related=related, card_bucket=card_bucket,
                        glossary_bucket="",
                    ))
                    progressed = True
                    break
            if not progressed:
                raise ValueError(
                    f"insufficient unique concepts for card bucket {card_bucket}: "
                    f"{len(result) - bucket_start}/{quota}"
                )
    if len(result) != 1_000:
        raise ValueError(f"expected 1000 official concepts, got {len(result)}")
    slots = tuple(
        bucket
        for bucket, quota in OFFICIAL_GLOSSARY_BUCKET_QUOTAS.items()
        for _ in range(quota)
    )
    family_slots = {
        family: tuple(
            slot_index for slot_index, bucket in enumerate(slots)
            if family in _GLOSSARY_BUCKET_FAMILIES[bucket]
        )
        for family in _FAMILY
    }
    slot_owner: dict[int, int] = {}

    def assign(index: int, visited: set[int]) -> bool:
        family = _SOURCE_FAMILY_BY_ID[result[index].source_id]
        for slot_index in family_slots[family]:
            if slot_index in visited:
                continue
            visited.add(slot_index)
            current = slot_owner.get(slot_index)
            if current is None or assign(current, visited):
                slot_owner[slot_index] = index
                return True
        return False

    assignment_order = sorted(
        range(len(result)),
        key=lambda index: (
            len(family_slots[_SOURCE_FAMILY_BY_ID[result[index].source_id]]),
            result[index].slug,
        ),
    )
    if not all(assign(index, set()) for index in assignment_order):
        raise ValueError("official glossary bucket quotas have no complete semantic assignment")
    bucket_by_item = {item_index: slots[slot_index] for slot_index, item_index in slot_owner.items()}
    for index, item in enumerate(result):
        result[index] = OfficialConceptSpec(
            slug=item.slug, term=item.term, technology=item.technology,
            area_id=item.area_id, source_id=item.source_id,
            source_title=item.source_title, concept=item.concept,
            definition=item.definition, signature=item.signature,
            example=item.example, related=item.related,
            card_bucket=item.card_bucket, glossary_bucket=bucket_by_item[index],
        )
    return tuple(result)


OFFICIAL_CONCEPTS = _concepts()
OFFICIAL_GLOSSARY = tuple(
    (
        item.term, item.technology, item.definition, item.signature,
        item.example, item.related,
    )
    for item in OFFICIAL_CONCEPTS
)
OFFICIAL_GLOSSARY_SOURCE_IDS = {
    item.term: _supporting_source_ids(item)
    for item in OFFICIAL_CONCEPTS
}
OFFICIAL_GLOSSARY_ALIASES = tuple(
    (
        item.term,
        tuple(dict.fromkeys((
            item.concept,
            f"{item.technology} {item.concept}",
            *item.related,
        ))),
    )
    for item in OFFICIAL_CONCEPTS
)

_FORMULA_SPECS = {
    "mathematics-analytics": (
        (r"\mu=\frac{1}{n}\sum_{i=1}^{n}x_i", "A média soma as observações e divide pelo seu número.", (("x_i", "observação i"), ("n", "número de observações")), "Para 2, 4 e 6: μ = 12/3 = 4.", "src-probml"),
        (r"\sigma^2=\frac{1}{n}\sum_{i=1}^{n}(x_i-\mu)^2", "A variância média mede os desvios quadráticos em relação à média.", (("x_i", "observação i"), ("μ", "média"), ("n", "número de observações")), "Para 2 e 4, μ=3 e σ²=((−1)²+1²)/2=1.", "src-probml"),
        (r"z=\frac{x-\mu}{\sigma}", "O valor padronizado mede quantos desvios-padrão x dista da média.", (("x", "observação"), ("μ", "média"), ("σ", "desvio-padrão")), "Se x=14, μ=10 e σ=2, então z=2.", "src-esl"),
        (r"p=\frac{k}{n}", "A frequência relativa divide ocorrências favoráveis pelo total observado.", (("k", "ocorrências favoráveis"), ("n", "total de observações")), "Com 3 sucessos em 5 ensaios, p=3/5=0,6.", "src-probml"),
        (r"L=\frac{1}{n}\sum_{i=1}^{n}(y_i-\hat{y}_i)^2", "O erro quadrático médio agrega o quadrado de cada resíduo.", (("y_i", "valor observado"), ("ŷ_i", "previsão"), ("n", "número de casos")), "Resíduos 1 e −1 produzem L=(1+1)/2=1.", "src-esl"),
    ),
    "ai-ml": (
        (r"a=\phi(Wx+b)", "Um neurónio aplica uma ativação à transformação linear da entrada.", (("x", "vetor de entrada"), ("W", "pesos"), ("b", "viés")), "Com x=2, W=3, b=1 e ativação identidade, a=7.", "src-dlbook"),
        (r"\sigma(z)=\frac{1}{1+\exp(-z)}", "A sigmoide converte um valor real num valor entre zero e um.", (("z", "entrada linear"), ("σ", "saída sigmoide")), "Para z=0, σ(0)=1/2.", "src-dlbook"),
        (r"p_i=\frac{\exp(z_i)}{\sum_j\exp(z_j)}", "Softmax normaliza logits numa distribuição de probabilidades.", (("z_i", "logit da classe i"), ("p_i", "probabilidade da classe i")), "Dois logits iguais produzem probabilidades iguais a 0,5.", "src-dlbook"),
        (r"L=-\sum_i y_i\log(p_i)", "A entropia cruzada penaliza probabilidade baixa atribuída à classe correta.", (("y_i", "indicador da classe"), ("p_i", "probabilidade prevista")), "Se a classe correta recebe p=0,5, a contribuição é −log(0,5).", "src-dlbook"),
        (r"\theta_{t+1}=\theta_t-\alpha\nabla L(\theta_t)", "A descida do gradiente atualiza parâmetros na direção oposta ao gradiente.", (("θ", "parâmetros"), ("α", "taxa de aprendizagem"), ("∇L", "gradiente da perda")), "Com θ=3, α=0,1 e gradiente 2, o novo θ é 2,8.", "src-dlbook"),
    ),
}


def build_official_facts(factory: FactFactory) -> tuple[object, ...]:
    formats = (
        "concept", "pitfall", "microexample", "comparison",
        "application", "visual",
    )
    facts = []
    bucket_positions: dict[str, int] = {}
    formula_positions: dict[str, int] = {}
    for index, item in enumerate(OFFICIAL_CONCEPTS):
        bucket_position = bucket_positions.get(item.card_bucket, 0)
        bucket_positions[item.card_bucket] = bucket_position + 1
        formula_specs = _FORMULA_SPECS.get(item.card_bucket, ())
        interval = max(1, OFFICIAL_CARD_BUCKET_QUOTAS[item.card_bucket] // max(1, len(formula_specs)))
        formula_position = formula_positions.get(item.card_bucket, 0)
        use_formula = bool(
            formula_position < len(formula_specs) and bucket_position % interval == 0
        )
        if use_formula:
            formula_latex, formula_spoken, formula_variables, worked_example, formula_source = formula_specs[formula_position]
            formula_positions[item.card_bucket] = formula_position + 1
        else:
            formula_latex = formula_spoken = worked_example = formula_source = ""
            formula_variables = ()
        source_ids = tuple(dict.fromkeys((
            *_supporting_source_ids(item),
            *((formula_source,) if use_formula else ()),
        )))
        if use_formula and len(source_ids) < 3:
            source_ids = (*source_ids, "src-probml")
        facts.append(factory(
            slug=item.slug, area_id=item.area_id,
            fact=f"Sabias que? {item.definition}",
            explanation=(
                f"Ponto de verificação: {item.example} A referência associada é "
                f"a página oficial «{item.source_title}». O conceito canónico desta "
                f"entrada é «{item.term}»; o texto deste card é original Aprendix."
            ),
            formula_or_code=formula_latex if use_formula else item.signature,
            complexity="intermediate",
            source_ids=source_ids,
            card_format="formula" if use_formula else formats[index % len(formats)],
            visual_hint=f"{item.technology}: entrada, contrato, transformação, limite e evidência",
            formula_latex=formula_latex if use_formula else "",
            formula_spoken=formula_spoken if use_formula else "",
            formula_variables=formula_variables if use_formula else (),
            formula_worked_example=worked_example if use_formula else "",
        ))
    return tuple(facts)
