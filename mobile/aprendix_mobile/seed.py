"""Deterministic public Lite knowledge database and atomic installer."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import struct
import tempfile
from difflib import SequenceMatcher
from dataclasses import asdict, dataclass
from pathlib import Path

from aprendix.application.knowledge_structure import AREAS, PRIMARY_SOURCES, area_depths, fold
from aprendix.application.learning_catalog import ALL_FACTS, EXTRA_GLOSSARY, GLOSSARY_ALIASES
from aprendix.application.academy_catalog import ACADEMY_MODULES, ACADEMY_TRACKS

APPLICATION_ID = 0x41505258  # APRX
SCHEMA_VERSION = 5
MAX_SEED_BYTES = 200 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class SeedManifest:
    schema_version: int
    sha256: str
    size_bytes: int
    content_version: str

    @classmethod
    def load(cls, path: Path) -> "SeedManifest":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            schema_version=int(payload["schema_version"]),
            sha256=str(payload["sha256"]), size_bytes=int(payload["size_bytes"]),
            content_version=str(payload["content_version"]),
        )


ORIGINAL_CONTENT = (
    ("python-output", "Primeiros resultados", "Python", "fundamentals",
     "Produz um resultado observável e compara-o com o objetivo antes de avançar.",
     "print('Olá, mobile!')"),
    ("python-decisions", "Decisões pequenas", "Python", "algorithms",
     "Pratica uma condição com casos verdadeiro e falso; depois testa a fronteira.",
     "def classificar(valor):\n    return 'positivo' if valor > 0 else 'não positivo'"),
    ("python-objects", "Estado e comportamento", "Python", "oop",
     "Modela um objeto com estado mínimo e um método que o altera de forma verificável.",
     "class Contador:\n    def __init__(self):\n        self.valor = 0"),
    ("python-collections", "Coleções previsíveis", "Python", "data-structures",
     "Escolhe uma lista para ordem, um conjunto para pertença ou um mapa para associações.",
     "def unicos(valores):\n    return list(set(valores))"),
    ("python-finance", "Juros sem surpresas", "Python", "finance",
     "Separa capital, taxa e períodos e valida os casos de taxa zero.",
     "def montante(capital, taxa):\n    return capital * (1 + taxa)"),
    ("python-games", "Regras de jogo", "Python", "games",
     "Transforma uma regra curta numa função pura que seja fácil de testar.",
     "def ganhou(pontos):\n    return pontos >= 10"),
)

PRACTICE = {
    "python-output": ("Mostra exatamente: Olá, mobile!", "print('')", "Olá, mobile!"),
    "python-decisions": ("Para valor=3, mostra positivo se for maior que zero.", "valor = 3\n", "positivo"),
    "python-objects": ("Cria Contador, incrementa duas vezes e mostra valor.", "class Contador:\n    pass\n", "2"),
    "python-collections": ("Remove repetidos de [2,1,2] e mostra 1,2 por ordem crescente.", "valores = [2, 1, 2]\n", "[1, 2]"),
    "python-finance": ("Mostra o montante de 100 com taxa 0.05.", "capital = 100\ntaxa = 0.05\n", "105.0"),
    "python-games": ("Com pontos=10, mostra ganhou ou continua.", "pontos = 10\n", "ganhou"),
}

QUIZZES = {
    "python-output": ("Que função produz output textual?", ("input", "print", "open"), "b", "print envia a representação dos valores para o output."),
    "python-decisions": ("Que ramo corre quando uma condição é falsa?", ("else", "for", "class"), "a", "else representa o caminho alternativo."),
    "python-objects": ("self referencia o quê?", ("A rede", "A instância atual", "A base de dados"), "b", "self é a instância que recebeu a chamada."),
    "python-collections": ("Que estrutura mantém elementos únicos?", ("set", "float", "str"), "a", "set representa uma coleção sem repetidos."),
    "python-finance": ("Uma taxa de 5% em decimal é…", ("5", "0.5", "0.05"), "c", "Dividir a percentagem por 100 produz 0.05."),
    "python-games": ("O operador >= inclui o valor de fronteira?", ("Sim", "Não", "Só online"), "a", ">= é verdadeiro também quando os valores são iguais."),
}

LITE_GLOSSARY = (
    ("print", "Mostra valores no output padrão.", "print(*valores, sep=' ', end='\\n')"),
    ("len", "Devolve a quantidade de elementos de uma coleção.", "len(objeto)"),
    ("range", "Cria uma progressão inteira limitada.", "range(inicio, fim, passo)"),
    ("list", "Coleção mutável, ordenada e com repetidos.", "list(iteravel=())"),
    ("dict", "Associa chaves únicas a valores.", "dict(...)"),
    ("set", "Coleção de elementos únicos.", "set(iteravel=())"),
    ("def", "Inicia a definição de uma função.", "def nome(parametros):"),
    ("class", "Agrupa construção e métodos de objetos.", "class Nome:"),
    ("if", "Executa um bloco quando a condição é verdadeira.", "if condicao:"),
    ("for", "Percorre elementos de um iterável.", "for item in iteravel:"),
    ("algoritmo", "Sequência finita e verificável de passos para resolver uma classe de problemas.", "entrada → passos → saída"),
    ("complexidade", "Crescimento do custo temporal ou espacial quando o tamanho da entrada aumenta.", "O(f(n))"),
    ("vetor", "Sequência ordenada de valores que também pode representar direção ou características.", "x ∈ R^n"),
    ("matriz", "Tabela bidimensional usada para representar dados e transformações lineares.", "A ∈ R^(m×n)"),
    ("gradiente", "Vetor de derivadas parciais que indica a direção de maior crescimento local.", "∇f(x)"),
    ("probabilidade", "Medida entre zero e um para quantificar incerteza sob um modelo.", "P(evento)"),
    ("regressão", "Família de métodos que estima um valor contínuo condicionado às entradas.", "ŷ = f(x)"),
    ("classificação", "Atribuição de uma entrada a uma de várias categorias possíveis.", "classe = argmax score"),
    ("overfitting", "Ajuste excessivo ao treino que prejudica a generalização para dados novos.", "erro_treino baixo; erro_teste alto"),
    ("rede neuronal", "Modelo composto por transformações parametrizadas organizadas em camadas.", "y = f_L(...f_1(x))"),
    ("backpropagation", "Aplicação eficiente da regra da cadeia para calcular gradientes numa rede.", "∂L/∂θ"),
    ("convolução", "Operação local que aplica o mesmo filtro em diferentes posições dos dados.", "feature = input * kernel"),
    ("attention", "Mecanismo que pondera informação de outras posições segundo a sua relevância.", "softmax(QKᵀ/√d)V"),
    ("transformer", "Arquitetura sequencial baseada principalmente em atenção e transformações por posição.", "attention + MLP"),
    ("embedding", "Representação vetorial aprendida para preservar relações úteis entre entidades.", "item → R^d"),
    ("agente", "Sistema que observa um ambiente, escolhe ações e acompanha resultados face a um objetivo.", "observar → decidir → agir"),
    ("memória episódica", "Registo de experiências específicas usado para recuperar contexto relevante.", "evento + resultado + tempo"),
    ("reinforcement learning", "Aprendizagem de decisões através de recompensas acumuladas pela interação.", "estado, ação, recompensa"),
    ("segmentação", "Atribuição de uma classe ou identidade a cada região ou píxel de uma imagem.", "imagem → máscara"),
    ("quantização", "Representação de pesos ou ativações com menos bits para reduzir custo e tamanho.", "float32 → int8"),
)

ORIGINAL_AREAS = {
    "python-output": "prog-foundations", "python-decisions": "classic-algorithms",
    "python-objects": "oop", "python-collections": "data-structures",
    "python-finance": "finance-app", "python-games": "games-app",
}


def _embedding(text: str, dimensions: int = 64) -> bytes:
    values = [0] * dimensions
    for token in text.casefold().split():
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest()
        index = int.from_bytes(digest[:2], "little") % dimensions
        values[index] = max(-127, min(127, values[index] + (1 if digest[2] & 1 else -1)))
    return struct.pack(f"{dimensions}b", *values)


def build_seed(database_path: Path, manifest_path: Path, *, content_version: str = "2026.08") -> SeedManifest:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    if database_path.exists():
        database_path.unlink()
    connection = sqlite3.connect(database_path)
    try:
        connection.executescript(f"""
            PRAGMA application_id={APPLICATION_ID};
            PRAGMA user_version={SCHEMA_VERSION};
            CREATE TABLE cards(
                id TEXT PRIMARY KEY, title TEXT NOT NULL, technology TEXT NOT NULL,
                theme TEXT NOT NULL, body TEXT NOT NULL, code TEXT NOT NULL,
                cluster_id TEXT NOT NULL, area_id TEXT NOT NULL,
                recommended_order INTEGER NOT NULL, embedding_q8 BLOB NOT NULL
            ) STRICT;
            CREATE INDEX cards_taxonomy ON cards(technology, theme, cluster_id, area_id);
            CREATE TABLE exercises(
                id TEXT PRIMARY KEY, card_id TEXT NOT NULL UNIQUE,
                prompt TEXT NOT NULL, starter_code TEXT NOT NULL,
                expected_output TEXT NOT NULL,
                FOREIGN KEY(card_id) REFERENCES cards(id)
            ) STRICT;
            CREATE TABLE quizzes(
                id TEXT PRIMARY KEY, card_id TEXT NOT NULL UNIQUE,
                question TEXT NOT NULL, options_json TEXT NOT NULL CHECK(json_valid(options_json)),
                correct_option TEXT NOT NULL, explanation TEXT NOT NULL,
                FOREIGN KEY(card_id) REFERENCES cards(id)
            ) STRICT;
            CREATE TABLE glossary(
                term TEXT PRIMARY KEY, definition TEXT NOT NULL, signature TEXT NOT NULL,
                aliases_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(aliases_json))
            ) STRICT;
            CREATE TABLE areas(
                id TEXT PRIMARY KEY, parent_id TEXT, title TEXT NOT NULL,
                description TEXT NOT NULL, depth INTEGER NOT NULL,
                position INTEGER NOT NULL, recommended_order INTEGER NOT NULL
            ) STRICT;
            CREATE TABLE shortcuts(
                id TEXT PRIMARY KEY, area_id TEXT NOT NULL, label TEXT NOT NULL,
                query TEXT NOT NULL, position INTEGER NOT NULL,
                FOREIGN KEY(area_id) REFERENCES areas(id)
            ) STRICT;
            CREATE TABLE sources(
                id TEXT PRIMARY KEY, area_ids_json TEXT NOT NULL CHECK(json_valid(area_ids_json)),
                title TEXT NOT NULL, authors_json TEXT NOT NULL CHECK(json_valid(authors_json)),
                publication_year INTEGER NOT NULL, source_type TEXT NOT NULL,
                canonical_url TEXT NOT NULL, overview TEXT NOT NULL,
                why_it_matters TEXT NOT NULL, access_note TEXT NOT NULL
            ) STRICT;
            CREATE TABLE learning_tracks(
                slug TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL,
                technology TEXT NOT NULL, position INTEGER NOT NULL
            ) STRICT;
            CREATE TABLE learning_units(
                slug TEXT PRIMARY KEY, track_slug TEXT NOT NULL, title TEXT NOT NULL,
                objective TEXT NOT NULL, explanation TEXT NOT NULL,
                starter_code TEXT NOT NULL, test_code TEXT NOT NULL, position INTEGER NOT NULL,
                FOREIGN KEY(track_slug) REFERENCES learning_tracks(slug)
            ) STRICT;
            CREATE INDEX learning_units_track ON learning_units(track_slug,position);
        """)
        depths = area_depths()
        for order, area in enumerate(AREAS):
            connection.execute(
                "INSERT INTO areas VALUES(?,?,?,?,?,?,?)",
                (area.id, area.parent_id, area.title, area.description,
                 depths[area.id], area.position, order),
            )
            keyword = area.keywords[0] if area.keywords else area.title
            for shortcut_position, (label, query) in enumerate((
                (f"Começar: {area.title}", f"fundamentos de {keyword} com exemplo"),
                (f"Aprofundar: {area.title}", f"algoritmos e limitações de {keyword}"),
            )):
                connection.execute(
                    "INSERT INTO shortcuts VALUES(?,?,?,?,?)",
                    (f"shortcut:{area.id}:{shortcut_position}", area.id,
                     label, query, shortcut_position),
                )
        for slug, title, technology, theme, body, code in ORIGINAL_CONTENT:
            area_id = ORIGINAL_AREAS[slug]
            order = next(index for index, area in enumerate(AREAS) if area.id == area_id)
            connection.execute(
                "INSERT INTO cards VALUES(?,?,?,?,?,?,?,?,?,?)",
                (slug, title, technology, theme, body, code, f"cluster-{theme}", area_id, order,
                 _embedding(f"{title} {body} {code}")),
            )
            prompt, starter, expected = PRACTICE[slug]
            connection.execute(
                "INSERT INTO exercises VALUES(?,?,?,?,?)",
                ("exercise-" + slug, slug, prompt, starter, expected),
            )
            question, options, correct, explanation = QUIZZES[slug]
            connection.execute(
                "INSERT INTO quizzes VALUES(?,?,?,?,?,?)",
                ("quiz-" + slug, slug, question,
                 json.dumps(options, ensure_ascii=False), correct, explanation),
            )
        area_map = {area.id: (index, area) for index, area in enumerate(AREAS)}
        for fact in ALL_FACTS:
            order, area = area_map[fact.area_id]
            body = fact.fact + "\n\n" + fact.explanation
            code = fact.formula_or_code
            connection.execute(
                "INSERT INTO cards VALUES(?,?,?,?,?,?,?,?,?,?)",
                (f"fact-{fact.slug}", f"Sabias que? · {area.title}", "Python", area.parent_id or area.id,
                 body, code, f"cluster-{area.parent_id or area.id}", area.id, order,
                 _embedding(f"{area.title} {body} {code}")),
            )
        for source in PRIMARY_SOURCES:
            connection.execute(
                "INSERT INTO sources VALUES(?,?,?,?,?,?,?,?,?,?)",
                (source.id, json.dumps(source.area_ids), source.title,
                 json.dumps(source.authors, ensure_ascii=False), source.year,
                 source.source_type, source.url, source.overview, source.why,
                source.access_note),
            )
        for slug, title, description, technology, position in ACADEMY_TRACKS:
            connection.execute(
                "INSERT INTO learning_tracks VALUES(?,?,?,?,?)",
                (slug, title, description, technology, position),
            )
        unit_positions: dict[str, int] = {}
        for slug, track_slug, title, objective, explanation, starter, test in ACADEMY_MODULES:
            position = unit_positions.get(track_slug, 0); unit_positions[track_slug] = position + 1
            connection.execute(
                "INSERT INTO learning_units VALUES(?,?,?,?,?,?,?,?)",
                (slug, track_slug, title, objective, explanation, starter, test, position),
            )
        aliases = {term.casefold(): values for term, values in GLOSSARY_ALIASES}
        connection.executemany(
            "INSERT INTO glossary VALUES(?,?,?,?)",
            ((term, definition, signature,
              json.dumps(aliases.get(term.casefold(), ()), ensure_ascii=False))
             for term, definition, signature in LITE_GLOSSARY),
        )
        connection.executemany(
            "INSERT OR IGNORE INTO glossary(term,definition,signature,aliases_json) VALUES(?,?,?,?)",
            ((term, definition, signature,
              json.dumps(aliases.get(term.casefold(), ()), ensure_ascii=False))
             for term, _technology, definition, signature, _example, _related in EXTRA_GLOSSARY),
        )
        connection.commit()
        connection.execute("VACUUM")
    finally:
        connection.close()
    size = database_path.stat().st_size
    if size > MAX_SEED_BYTES:
        raise ValueError("Lite seed exceeds the 200 MB product limit")
    digest = hashlib.sha256(database_path.read_bytes()).hexdigest()
    manifest = SeedManifest(SCHEMA_VERSION, digest, size, content_version)
    manifest_path.write_text(json.dumps(asdict(manifest), indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def install_seed(asset: Path, manifest: SeedManifest, destination: Path) -> bool:
    """Install once using copy, fsync, validation and atomic replacement."""

    if destination.exists() and _valid_database(destination, manifest):
        return False
    if asset.stat().st_size != manifest.size_bytes or manifest.size_bytes > MAX_SEED_BYTES:
        raise ValueError("seed size does not match its manifest")
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".knowledge-lite-", dir=destination.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as target, asset.open("rb") as source:
            digest = hashlib.sha256()
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
                target.write(chunk)
            target.flush()
            os.fsync(target.fileno())
        if digest.hexdigest() != manifest.sha256 or not _valid_database(temporary, manifest):
            raise ValueError("seed integrity or schema validation failed")
        os.replace(temporary, destination)
        return True
    finally:
        if temporary.exists():
            temporary.unlink()


def _valid_database(path: Path, manifest: SeedManifest) -> bool:
    if path.stat().st_size != manifest.size_bytes:
        return False
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest.sha256:
        return False
    uri = path.resolve().as_uri() + "?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    try:
        app_id = connection.execute("PRAGMA application_id").fetchone()[0]
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        return app_id == APPLICATION_ID and version == manifest.schema_version and integrity == "ok"
    finally:
        connection.close()


class LiteContentStore:
    def __init__(self, path: Path) -> None:
        self._uri = path.resolve().as_uri() + "?mode=ro&immutable=1"

    def cards(self, *, technology: str | None = None, theme: str | None = None,
              area_id: str | None = None) -> tuple[dict[str, object], ...]:
        clauses, parameters = [], []
        if technology:
            clauses.append("technology=?")
            parameters.append(technology)
        if theme:
            clauses.append("theme=?")
            parameters.append(theme)
        if area_id:
            clauses.append("area_id IN (WITH RECURSIVE branch(id) AS (SELECT ? UNION ALL SELECT a.id FROM areas a JOIN branch b ON a.parent_id=b.id) SELECT id FROM branch)")
            parameters.append(area_id)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        connection = sqlite3.connect(self._uri, uri=True)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                """SELECT c.id,c.title,c.technology,c.theme,c.body,c.code,c.cluster_id,c.area_id,c.recommended_order,
                          e.id exercise_id,e.prompt,e.starter_code,e.expected_output,
                          q.id quiz_id,q.question,q.options_json,q.correct_option,q.explanation
                   FROM cards c LEFT JOIN exercises e ON e.card_id=c.id
                   LEFT JOIN quizzes q ON q.card_id=c.id""" + where.replace("technology", "c.technology").replace("theme", "c.theme").replace("area_id", "c.area_id") + " ORDER BY c.recommended_order,c.title",
                parameters,
            ).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                options = item.pop("options_json")
                item["options"] = tuple(json.loads(options)) if options else ()
                result.append(item)
            return tuple(result)
        finally:
            connection.close()

    def areas(self) -> tuple[dict[str, object], ...]:
        connection = sqlite3.connect(self._uri, uri=True); connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute("SELECT * FROM areas ORDER BY recommended_order").fetchall()
            return tuple(dict(row) for row in rows)
        finally:
            connection.close()

    def courses(self) -> tuple[dict[str, object], ...]:
        connection = sqlite3.connect(self._uri, uri=True); connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                """SELECT t.*,count(u.slug) unit_count FROM learning_tracks t
                   LEFT JOIN learning_units u ON u.track_slug=t.slug
                   GROUP BY t.slug ORDER BY t.position"""
            ).fetchall()
            return tuple(dict(row) for row in rows)
        finally:
            connection.close()

    def course_units(self, track_slug: str) -> tuple[dict[str, object], ...]:
        connection = sqlite3.connect(self._uri, uri=True); connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                "SELECT * FROM learning_units WHERE track_slug=? ORDER BY position,slug",
                (track_slug,),
            ).fetchall()
            return tuple(dict(row) for row in rows)
        finally:
            connection.close()

    def shortcuts(self, area_id: str | None = None, *, limit: int = 30) -> tuple[dict[str, object], ...]:
        connection = sqlite3.connect(self._uri, uri=True); connection.row_factory = sqlite3.Row
        try:
            if area_id:
                rows = connection.execute(
                    """SELECT * FROM shortcuts WHERE area_id IN (
                    WITH RECURSIVE branch(id) AS (SELECT ? UNION ALL SELECT a.id FROM areas a JOIN branch b ON a.parent_id=b.id)
                    SELECT id FROM branch) ORDER BY position,id LIMIT ?""",
                    (area_id, max(1, min(limit, 100))),
                ).fetchall()
            else:
                rows = connection.execute("SELECT * FROM shortcuts ORDER BY position,id LIMIT ?", (max(1, min(limit, 100)),)).fetchall()
            return tuple(dict(row) for row in rows)
        finally:
            connection.close()

    def search(self, query: str, *, area_id: str | None = None, limit: int = 20) -> tuple[dict[str, object], ...]:
        terms = tuple(dict.fromkeys(term.casefold() for term in query.split() if len(term) >= 3))
        cards = self.cards(area_id=area_id)
        results = []
        for item in cards:
            haystack = f"{item['title']} {item['body']} {item['code']}".casefold()
            score = sum(term in haystack for term in terms) / max(1, len(terms))
            if score:
                results.append({"id": item["id"], "kind": "card", "title": item["title"],
                                "excerpt": item["body"], "score": score, "source": "Aprendix offline"})
        connection = sqlite3.connect(self._uri, uri=True); connection.row_factory = sqlite3.Row
        try:
            allowed_areas: set[str] | None = None
            if area_id:
                allowed_areas = {area_id}
                area_rows = connection.execute("SELECT id,parent_id FROM areas").fetchall()
                changed = True
                while changed:
                    changed = False
                    for area_row in area_rows:
                        if area_row["parent_id"] in allowed_areas and area_row["id"] not in allowed_areas:
                            allowed_areas.add(str(area_row["id"])); changed = True
            rows = connection.execute("SELECT * FROM sources ORDER BY publication_year DESC,title").fetchall()
            for row in rows:
                item = dict(row); source_areas = tuple(json.loads(item["area_ids_json"]))
                if allowed_areas is not None and not allowed_areas.intersection(source_areas):
                    continue
                haystack = f"{item['title']} {item['authors_json']} {item['overview']} {item['why_it_matters']}".casefold()
                score = sum(term in haystack for term in terms) / max(1, len(terms))
                if score:
                    results.append({"id": "reference:" + item["id"], "kind": "source",
                                    "title": item["title"], "excerpt": item["overview"],
                                    "score": score, "source": item["canonical_url"]})
        finally:
            connection.close()
        return tuple(sorted(results, key=lambda item: (-item["score"], item["title"]))[:max(1, min(limit, 50))])

    def reading_item(self, item_id: str) -> dict[str, object]:
        connection = sqlite3.connect(self._uri, uri=True); connection.row_factory = sqlite3.Row
        try:
            if item_id.startswith("reference:"):
                row = connection.execute("SELECT * FROM sources WHERE id=?", (item_id.removeprefix("reference:"),)).fetchone()
                if row is None: raise KeyError(item_id)
                item = dict(row)
                return {"id": item_id, "title": item["title"],
                        "body": item["overview"] + "\n\nPorque importa: " + item["why_it_matters"],
                        "source": item["canonical_url"], "canonical_url": item["canonical_url"]}
            row = connection.execute("SELECT * FROM cards WHERE id=?", (item_id,)).fetchone()
            if row is None: raise KeyError(item_id)
            item = dict(row)
            return {"id": item_id, "title": item["title"], "body": item["body"] + "\n\n" + item["code"],
                    "source": "Aprendix offline", "canonical_url": None}
        finally:
            connection.close()

    def sources(self, area_id: str, *, limit: int = 5) -> tuple[dict[str, object], ...]:
        connection = sqlite3.connect(self._uri, uri=True); connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute("SELECT * FROM sources ORDER BY publication_year DESC,title").fetchall()
            return tuple(dict(row) for row in rows if area_id in json.loads(row["area_ids_json"]))[:limit]
        finally:
            connection.close()

    def glossary(self, prefix: str, *, limit: int = 12) -> tuple[dict[str, str], ...]:
        connection = sqlite3.connect(self._uri, uri=True)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute("SELECT * FROM glossary ORDER BY term").fetchall()
            query = fold(prefix.strip())
            def rank(row):
                candidate = fold(row["term"])
                aliases = tuple(fold(value) for value in json.loads(row["aliases_json"]))
                values = (candidate, *aliases)
                return (
                    candidate == query,
                    query in aliases,
                    any(value.startswith(query) for value in values),
                    any(query in value for value in values),
                    max((SequenceMatcher(None, query, value).ratio() for value in values), default=0)
                    if query else 0,
                )
            ordered = sorted(rows, key=rank, reverse=True)
            if query:
                ordered = [row for row in ordered if any(rank(row)[:4]) or rank(row)[4] >= .36]
            result = []
            for row in ordered[:max(1, min(limit, 30))]:
                item = dict(row); item["aliases"] = tuple(json.loads(item.pop("aliases_json")))
                result.append(item)
            return tuple(result)
        finally:
            connection.close()
