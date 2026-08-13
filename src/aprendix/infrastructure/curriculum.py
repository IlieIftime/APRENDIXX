"""Encrypted curriculum, assessments, glossary and bibliography graph."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import unicodedata
from difflib import SequenceMatcher
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from aprendix.application.academy_catalog import (
    ACADEMY_MODULES,
    ACADEMY_TRACKS,
    VERTICAL_CORE_MODULES,
)
from aprendix.application.learning_catalog import EXTRA_GLOSSARY, GLOSSARY_ALIASES
from aprendix.application.official_catalog import (
    OFFICIAL_GLOSSARY,
    OFFICIAL_GLOSSARY_ALIASES,
    OFFICIAL_GLOSSARY_SOURCE_IDS,
)
from aprendix.application.stdlib_glossary import STDLIB_GLOSSARY
from aprendix.application.vertical_practice import CORE_PRACTICE_VARIANTS, TRACK_SOURCE_IDS
from aprendix.infrastructure.db.access_policy import (
    access_from_state,
    unit_access,
    valid_completed_ids,
)


def _id(kind: str, slug: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"aprendix:curriculum:{kind}:{slug}"))


LEGACY_TRACKS = (
    ("python-foundations", "Python: bases", "Prática progressiva de valores, decisões e funções.", 0),
    ("python-oop", "Python: POO", "Objetos pequenos, estado explícito e comportamento testável.", 1),
    ("python-algorithms", "Python: algoritmos", "Resolução determinística, casos-limite e análise de passos.", 2),
    ("python-data-structures", "Python: estruturas de dados", "Escolha consciente de listas, mapas e conjuntos.", 3),
)


TRACKS = tuple(
    (slug, title, description, position)
    for slug, title, description, _technology, position in ACADEMY_TRACKS
)


CHAPTERS = (
    ("visible-output", "python-foundations", "output", "Resultados observáveis",
     "Produzir e verificar output antes de abstrair.", "hello-python",
     "O output é a evidência mais curta de que uma transformação ocorreu. Começa por um valor conhecido e compara exatamente espaços, acentos e linhas.",
     "print('resultado:', 2 + 3)",
     "Qual função envia texto para o output padrão?", ("input", "print", "open"), "b",
     "print recebe valores e produz uma representação textual observável.",
     "Que output produz print('A', 'B', sep='-')?", "A-B",
     "O separador substitui o espaço usado por omissão."),
    ("values-and-names", "python-foundations", "variables-arithmetic", "Valores e nomes",
     "Ligar nomes claros a valores e transformar sem efeitos ocultos.", "sum-two-values",
     "Uma variável é uma ligação local entre um nome e um valor. Nomes descritivos tornam a transformação verificável e reduzem ambiguidades.",
     "preco = 12\nquantidade = 3\ntotal = preco * quantidade",
     "O que acontece em total = preco * quantidade?", ("Os nomes são apagados", "É calculado e ligado um novo valor", "É aberta uma rede"), "b",
     "A expressão é avaliada e o resultado fica associado ao nome total.",
     "Com preco=12 e quantidade=3, qual é total?", "36",
     "A multiplicação é executada antes da atribuição."),
    ("safe-decisions", "python-foundations", "conditionals", "Decisões explícitas",
     "Cobrir ramos e fronteiras de uma condição.", "even-or-odd",
     "Uma condição deve tornar visíveis todos os caminhos relevantes. Testa um caso de cada ramo e pelo menos um valor na fronteira.",
     "estado = 'adulto' if idade >= 18 else 'menor'",
     "Qual palavra introduz o ramo alternativo?", ("for", "else", "class"), "b",
     "else descreve o caminho seguido quando a condição é falsa.",
     "Se idade=18, qual ramo de idade >= 18 é usado?", "adulto",
     "O operador >= inclui o próprio valor de fronteira."),
    ("objects-and-state", "python-oop", "object-oriented-python", "Objetos e estado",
     "Construir uma classe com invariantes simples.", "oop-account",
     "Uma classe define a forma de objetos relacionados; cada instância conserva o seu próprio estado. Métodos devem proteger as regras desse estado.",
     "class Contador:\n    def __init__(self):\n        self.valor = 0",
     "O que representa self num método de instância?", ("A classe inteira", "A instância atual", "Um módulo"), "b",
     "self referencia o objeto que recebeu a chamada.",
     "Duas instâncias de Contador partilham automaticamente valor?", "não",
     "Cada instância possui o seu dicionário de estado independente."),
    ("methods-and-invariants", "python-oop", "object-oriented-python", "Métodos e invariantes",
     "Alterar estado sem quebrar regras do domínio.", "oop-vault",
     "Um invariante é uma condição que deve continuar verdadeira depois de cada operação pública. Valida antes de alterar e deixa o objeto consistente quando a operação falha.",
     "def levantar(self, valor):\n    if valor > self.saldo:\n        return False",
     "Quando deve um método validar um invariante?", ("Depois de corromper o estado", "Antes de confirmar a alteração", "Apenas ao fechar a app"), "b",
     "Validar primeiro permite rejeitar a operação sem estado intermédio inválido.",
     "Se o saldo é 6 e se tenta levantar 9, o saldo deve mudar?", "não",
     "A operação inválida é rejeitada sem efeitos parciais."),
    ("iteration-and-search", "python-algorithms", "python-algorithms", "Iteração e pesquisa",
     "Percorrer uma sequência com critério de paragem claro.", "algo-linear-search",
     "Um algoritmo de pesquisa linear examina elementos por ordem e termina quando encontra o alvo ou esgota a sequência. O caso ausente faz parte do contrato.",
     "for indice, valor in enumerate(valores):\n    if valor == alvo:\n        return indice",
     "Qual é o pior número de comparações numa lista com n itens?", ("1", "n", "n²"), "b",
     "Se o alvo não existir, todos os n elementos são comparados.",
     "Que sentinela usa o exercício quando o alvo não existe?", "-1",
     "A sentinela está fora dos índices válidos da lista."),
    ("algorithm-boundaries", "python-algorithms", "python-algorithms", "Casos-limite",
     "Testar vazio, mínimo e valores repetidos.", "algo-count",
     "Casos-limite não são exceções ao problema: fazem parte dele. Uma coleção vazia, um único item e repetições revelam suposições escondidas.",
     "contador = 0\nfor valor in valores:\n    if valor == alvo:\n        contador += 1",
     "Qual deve ser a contagem numa coleção vazia?", ("-1", "0", "1"), "b",
     "Sem elementos não existe qualquer ocorrência.",
     "Em [1,1,2], quantas ocorrências tem 1?", "2",
     "A contagem considera cada posição que satisfaz a igualdade."),
    ("maps-and-frequency", "python-data-structures", "python-data-structures", "Mapas e frequências",
     "Associar chaves únicas a contagens.", "ds-frequency",
     "Um dicionário é adequado quando a pergunta parte de uma chave. Para frequências, cada valor observado é a chave e a contagem é atualizada incrementalmente.",
     "contagens[valor] = contagens.get(valor, 0) + 1",
     "Qual estrutura associa chaves a valores?", ("set", "dict", "tuple"), "b",
     "dict mantém uma associação por chave única.",
     "Qual é a frequência de 'a' em ['a','b','a']?", "2",
     "A chave 'a' é observada em duas posições."),
    ("sets-and-order", "python-data-structures", "python-data-structures", "Pertença e ordem",
     "Combinar set para pertença com list para ordem.", "ds-unique",
     "Um conjunto responde rapidamente se um valor já foi visto, mas não deve substituir a lista quando a ordem de primeira ocorrência faz parte do resultado.",
     "vistos = set()\nresultado = []",
     "Que estrutura é adequada para testar pertença?", ("set", "float", "str apenas"), "a",
     "set representa elementos únicos e suporta testes de pertença.",
     "Em [2,1,2], quais são os únicos pela primeira ordem?", "2,1",
     "A segunda ocorrência de 2 é ignorada sem reordenar 1."),
)


def _chapter_specs():
    """Return legacy authored chapters plus the expanded academy modules."""
    generated = []
    for slug, track_slug, title, objective, theory, starter, _test in ACADEMY_MODULES:
        generated.append((
            slug, track_slug, slug, title, objective, f"academy-{slug}",
            theory, starter,
            f"Qual prática torna '{title}' verificável?",
            ("Ignorar o contrato e observar apenas o resultado final",
             "Declarar o contrato e testar um caso normal e um caso-limite",
             "Usar rede ou ficheiros externos sem necessidade"),
            "b",
            "Um contrato observável e casos representativos distinguem uma solução correta de uma coincidência.",
            "Antes de executar, qual ação permite comparar a previsão com o resultado?",
            "validar",
            "Validar é definir a expectativa primeiro e compará-la com a evidência da execução.",
        ))
    return (*CHAPTERS, *generated)


GLOSSARY = (
    ("print", "python", "Mostra uma representação textual dos valores recebidos no output padrão.", "print(*valores, sep=' ', end='\\n')", "print('total', 3)", ("output", "str")),
    ("len", "python", "Devolve a quantidade de elementos de uma coleção finita.", "len(objeto)", "len([4, 8])  # 2", ("list", "tuple")),
    ("range", "python", "Produz uma progressão inteira usada frequentemente em iterações limitadas.", "range(inicio, fim, passo)", "list(range(1, 4))", ("for", "iteration")),
    ("enumerate", "python", "Combina cada elemento iterado com o respetivo índice.", "enumerate(iteravel, start=0)", "for i, valor in enumerate(valores): ...", ("for", "index")),
    ("zip", "python", "Agrupa elementos de iteráveis pela mesma posição até um deles terminar.", "zip(*iteraveis)", "list(zip(nomes, notas))", ("tuple", "iteration")),
    ("sum", "python", "Acumula valores numéricos a partir de um valor inicial opcional.", "sum(iteravel, start=0)", "sum([2, 3, 4])", ("algorithm",)),
    ("sorted", "python", "Cria uma nova lista ordenada sem alterar o iterável original.", "sorted(iteravel, key=None, reverse=False)", "sorted([3, 1, 2])", ("sort", "list")),
    ("list", "python", "Coleção mutável e ordenada que admite valores repetidos.", "list(iteravel=())", "valores = [1, 2]", ("set", "tuple")),
    ("dict", "python", "Coleção mutável que associa cada chave única a um valor.", "dict(...) ", "pessoa = {'nome': 'Ana'}", ("mapping", "key")),
    ("set", "python", "Coleção de elementos únicos, útil para pertença e eliminação de duplicados.", "set(iteravel=())", "vistos = set(valores)", ("list", "membership")),
    ("tuple", "python", "Sequência imutável e ordenada, adequada para um registo curto estável.", "tuple(iteravel=())", "ponto = (3, 5)", ("list",)),
    ("def", "python", "Inicia a definição de uma função com parâmetros e um bloco próprio.", "def nome(parametros):", "def dobro(x):\n    return x * 2", ("return", "function")),
    ("return", "python", "Termina a função atual e entrega um valor ao chamador.", "return valor", "return total", ("def",)),
    ("class", "python", "Inicia uma definição que agrupa construção de instâncias e métodos relacionados.", "class Nome:", "class Conta:\n    pass", ("object", "method")),
    ("self", "python", "Nome convencional do parâmetro que referencia a instância atual.", "def metodo(self, ...):", "self.saldo = 0", ("class", "instance")),
    ("if", "python", "Executa um bloco apenas quando a condição é verdadeira.", "if condicao:", "if saldo >= valor:\n    ...", ("else", "boolean")),
    ("for", "python", "Percorre os elementos de um iterável, atribuindo cada um ao nome indicado.", "for item in iteravel:", "for item in valores:\n    print(item)", ("range", "while")),
    ("while", "python", "Repete um bloco enquanto a condição continuar verdadeira.", "while condicao:", "while tentativas > 0:\n    tentativas -= 1", ("for", "loop")),
    ("method", "python", "Função definida numa classe e ligada a uma instância ou à própria classe.", "objeto.metodo(argumentos)", "conta.depositar(5)", ("class", "self")),
    ("invariant", "python", "Regra de estado que todas as operações públicas devem preservar.", "condição sempre verdadeira", "saldo >= 0", ("validation", "class")),
    ("exception", "python", "Objeto que representa uma falha ou condição não local no fluxo normal.", "raise TipoErro(mensagem)", "raise ValueError('valor inválido')", ("try", "error")),
    ("SELECT", "sql", "Operação SQL que escolhe colunas e linhas de uma relação sem alterar os dados.", "SELECT colunas FROM tabela WHERE condição", "SELECT nome FROM alunos", ("WHERE", "JOIN")),
    ("JOIN", "sql", "Combina linhas de relações através de uma condição entre chaves compatíveis.", "... JOIN tabela ON condição", "SELECT * FROM a JOIN b ON b.a_id=a.id", ("SELECT", "foreign key")),
    ("index", "sql", "Estrutura auxiliar que acelera certas pesquisas em troca de espaço e custo de escrita.", "CREATE INDEX nome ON tabela(coluna)", "CREATE INDEX alunos_nome ON alunos(nome)", ("query", "database")),
    ("transaction", "sql", "Unidade atómica de alterações que confirma tudo ou reverte tudo.", "BEGIN; ... COMMIT;", "BEGIN IMMEDIATE", ("ACID", "rollback")),
    ("NoSQL", "nosql", "Família de modelos de dados não relacionais, escolhidos segundo padrões de acesso específicos.", "documento, chave-valor, coluna ou grafo", "{'id': 1, 'tags': ['local']}", ("database", "document")),
    ("Django", "django", "Framework Python para aplicações web com routing, templates, ORM e convenções integradas.", "django-admin startproject nome", "class Artigo(models.Model): ...", ("python", "ORM")),
    ("FastAPI", "fastapi", "Framework Python orientado a APIs tipadas e validação de contratos.", "@app.get('/rota')", "def estado(): return {'ok': True}", ("python", "HTTP")),
    ("Flask", "flask", "Microframework Python que fornece um núcleo web pequeno e extensível.", "@app.route('/')", "return 'local'", ("python", "HTTP")),
    ("NumPy", "numpy", "Biblioteca Python para arrays multidimensionais e operações numéricas vetorizadas.", "numpy.array(valores)", "np.array([1, 2]) * 2", ("python", "array")),
    ("pandas", "pandas", "Biblioteca Python para dados tabulares rotulados e transformações por coluna.", "pandas.DataFrame(dados)", "df['total'] = df['qtd'] * df['preco']", ("python", "dataframe")),
    ("HTML", "html", "Linguagem de marcação que descreve a estrutura semântica de um documento web.", "<elemento>conteúdo</elemento>", "<button>Praticar</button>", ("CSS", "JavaScript")),
    ("CSS", "css", "Linguagem que define apresentação e layout de documentos estruturados.", "seletor { propriedade: valor; }", ".card { padding: 1rem; }", ("HTML", "Bootstrap")),
    ("JavaScript", "javascript", "Linguagem de programação usada para comportamento interativo em ambientes web e outros runtimes.", "function nome(args) { ... }", "const dobro = x => x * 2", ("HTML", "React")),
    ("React", "react", "Biblioteca de interface baseada em componentes e atualização declarativa de estado.", "function Componente() { return <UI/> }", "function Card({title}) { return <h2>{title}</h2> }", ("JavaScript", "JSX")),
    ("Bootstrap", "bootstrap", "Sistema CSS de componentes e utilitários responsivos reutilizáveis.", "class='container'", "<div class='row'>...</div>", ("CSS", "HTML")),
    ("Java", "java", "Linguagem tipada compilada para bytecode da JVM, com gestão automática de memória.", "class Nome { ... }", "System.out.println(42);", ("JVM", "class")),
    ("Go", "go", "Linguagem compilada com tipos estáticos, concorrência por goroutines e ferramenta integrada.", "func nome(args) retorno", "fmt.Println(42)", ("goroutine", "module")),
)


_CORE_RELATED = {
    "python-foundations": ("python", "função", "teste"),
    "python-oop": ("class", "object", "invariant"),
    "python-algorithms": ("algorithm", "complexidade temporal", "invariant"),
    "python-data-structures": ("data structure", "algorithm", "complexidade espacial"),
}

CORE_GLOSSARY = tuple(
    (
        title, "python", f"{objective} {explanation}",
        starter.strip().splitlines()[0], starter.strip(), _CORE_RELATED[track],
    )
    for _slug, track, title, objective, explanation, starter, _test
    in VERTICAL_CORE_MODULES
)

STDLIB_GLOSSARY_ENTRIES = tuple(
    (
        str(item["term"]), str(item["technology"]), str(item["definition"]),
        str(item["signature"]), str(item["example"]), tuple(item["related"]),
    )
    for item in STDLIB_GLOSSARY
)

GENERATED_GLOSSARY_ALIASES = tuple(
    (str(item["term"]), tuple(str(alias) for alias in item["aliases"]))
    for item in STDLIB_GLOSSARY
) + tuple(
    (title, (slug, title.casefold(), title.replace(" e ", " & ")))
    for slug, _track, title, _objective, _explanation, _starter, _test
    in VERTICAL_CORE_MODULES
)

GLOSSARY_SOURCE_IDS = {
    **{str(item["term"]): tuple(item["source_ids"]) for item in STDLIB_GLOSSARY},
    **{
        title: TRACK_SOURCE_IDS[track]
        for _slug, track, title, _objective, _explanation, _starter, _test
        in VERTICAL_CORE_MODULES
    },
}

_GLOSSARY_TECHNOLOGY_SOURCES = {
    "python": ("src-python-docs", "src-fluent-python"),
    "algorithms": ("src-clrs", "src-python-docs"),
    "mathematics": ("src-numpy", "src-probml"),
    "statistics": ("src-probml", "src-numpy"),
    "machine-learning": ("src-sklearn", "src-esl", "src-probml"),
    "deep-learning": ("src-dlbook", "src-pytorch-autograd"),
    "artificial-intelligence": ("src-aima", "src-ai-index"),
    "computer-vision": ("src-resnet", "src-vit", "src-unet"),
    "sql": ("src-postgresql", "src-sqlalchemy"),
    "sqlalchemy": ("src-sqlalchemy", "src-postgresql"),
    "django": ("src-django", "src-python-docs"),
    "fastapi": ("src-fastapi", "src-python-docs"),
    "flask": ("src-flask", "src-python-docs"),
    "javascript": ("src-mdn", "src-python-docs"),
    "html": ("src-mdn", "src-python-docs"),
    "css": ("src-mdn", "src-python-docs"),
    "numpy": ("src-numpy", "src-python-docs"),
    "pandas": ("src-pandas", "src-python-docs"),
    "pytorch": ("src-pytorch-autograd", "src-dlbook"),
    "pytest": ("src-pytest", "src-python-docs"),
    "mongodb": ("src-mongodb", "src-postgresql"),
    "git": ("src-git", "src-python-docs"),
    "docker": ("src-docker", "src-python-packaging"),
    "python-packaging": ("src-python-packaging", "src-python-docs"),
    "asyncio": ("src-python-asyncio", "src-python-docs"),
}


def _glossary_examples(
    term: str,
    definition: str,
    signature: str,
    example: str,
) -> tuple[tuple[str, str, str, str], ...]:
    """Return two original learning views without reproducing source prose."""

    principal = example.strip() or signature.strip() or term
    boundary = (
        f"# Verificação de fronteira para {term}\n"
        f"# Compare uma entrada mínima, uma entrada vazia e uma entrada inválida.\n"
        f"{signature.strip() or term}"
    )
    return (
        (
            principal,
            f"Exemplo principal: relaciona `{term}` com o contrato descrito na definição local.",
            "beginner",
            "utilização principal",
        ),
        (
            boundary,
            (
                f"Exemplo de fronteira: usa o comportamento de `{term}` para testar limites e "
                f"falhas previsíveis. Ideia central: {definition.strip()}"
            ),
            "intermediate",
            "casos-limite e diagnóstico",
        ),
    )

TRACK_BIBLIOGRAPHY_SOURCE_IDS = {
    "computer-literacy": ("src-python-docs", "src-fluent-python", "src-pytest"),
    "logic-pseudocode": ("src-python-docs", "src-clrs", "src-pytest"),
    "python-foundations": ("src-python-docs", "src-fluent-python", "src-pytest"),
    "python-oop": ("src-python-docs", "src-fluent-python", "src-pytest"),
    "python-algorithms": ("src-clrs", "src-python-docs", "src-numpy"),
    "python-data-structures": ("src-clrs", "src-python-docs", "src-fluent-python"),
    "math-programming": ("src-numpy", "src-probml", "src-clrs"),
    "testing-debugging": ("src-pytest", "src-python-docs", "src-fluent-python"),
    "python-advanced": ("src-python-docs", "src-fluent-python", "src-pytest"),
    "sql-databases": ("src-postgresql", "src-sqlalchemy", "src-django"),
    "web-apis": ("src-mdn", "src-django", "src-fastapi"),
    "data-ai": ("src-numpy", "src-sklearn", "src-pandas"),
}


def _normalize(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold()
    return re.sub(r"\s+", " ", folded).strip()


class CurriculumRepository:
    def __init__(self, database, cipher) -> None:
        self._database, self._cipher = database, cipher

    def _encrypt(self, table_field: str, identity: str, value: str) -> bytes:
        return self._cipher.encrypt(value.encode("utf-8"), associated_data=f"{table_field}:{identity}".encode())

    def _decrypt(self, table_field: str, identity: str, value: bytes | None) -> str:
        if value is None:
            return ""
        return self._cipher.decrypt(value, associated_data=f"{table_field}:{identity}".encode()).decode("utf-8")

    def seed(self) -> None:
        chapters = _chapter_specs()
        with self._database.transaction() as connection:
            technology_by_track = {item[0]: item[3] for item in ACADEMY_TRACKS}
            for slug, title, description, position in TRACKS:
                connection.execute(
                    """INSERT INTO learning_tracks VALUES(?,?,?,?,?,?)
                       ON CONFLICT(id) DO UPDATE SET title=excluded.title,
                       description=excluded.description,technology=excluded.technology,
                       position=excluded.position""",
                    (_id("track", slug), slug, title, description,
                     technology_by_track[slug], position),
                )
            now = datetime.now(UTC).isoformat()
            track_position = {item[0]: item[4] for item in ACADEMY_TRACKS}
            for slug, track_slug, title, objective, _theory, starter, test in ACADEMY_MODULES:
                node_id = _id("graph-node", slug)
                difficulty = min(2.5, -1.25 + track_position[track_slug] * 0.3)
                connection.execute(
                    """INSERT OR IGNORE INTO graph_nodes(
                       id,slug,title,description,difficulty,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?)""",
                    (node_id, slug, title, objective, difficulty, now, now),
                )
                exercise_id = _id("exercise", f"academy-{slug}")
                connection.execute(
                    """INSERT OR IGNORE INTO exercises(
                       id,graph_node_id,slug,title,prompt,starter_code,tests_json,
                       difficulty,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,1,?,?)""",
                    (exercise_id, node_id, f"academy-{slug}", f"Prática · {title}",
                     f"{objective}\n\nCompleta o contrato iniciado. A solução deve passar todos os casos normais e limites sem rede nem ficheiros externos.",
                     starter, json.dumps((test,), ensure_ascii=False), difficulty, now, now),
                )
                for source_id in TRACK_BIBLIOGRAPHY_SOURCE_IDS[track_slug]:
                    connection.execute(
                        """INSERT INTO exercise_source_links(exercise_id,source_id,rationale)
                           SELECT ?,id,? FROM curated_sources WHERE id=?
                           ON CONFLICT(exercise_id,source_id) DO UPDATE SET
                           rationale=excluded.rationale""",
                        (exercise_id,
                         "Referência técnica do percurso; o enunciado e os testes são originais Aprendix.",
                         source_id),
                    )
            for variant in CORE_PRACTICE_VARIANTS:
                node_id = _id("graph-node", variant.module_slug)
                exercise_id = _id("exercise", variant.slug)
                connection.execute(
                    """INSERT INTO exercises(
                       id,graph_node_id,slug,title,prompt,starter_code,tests_json,
                       difficulty,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,1,?,?)
                       ON CONFLICT(id) DO UPDATE SET graph_node_id=excluded.graph_node_id,
                       title=excluded.title,prompt=excluded.prompt,
                       starter_code=excluded.starter_code,tests_json=excluded.tests_json,
                       difficulty=excluded.difficulty,updated_at=excluded.updated_at""",
                    (exercise_id, node_id, variant.slug, variant.title, variant.prompt,
                     variant.starter_code,
                     json.dumps((variant.test_code,), ensure_ascii=False),
                     variant.difficulty, now, now),
                )
                for source_id in variant.source_ids:
                    connection.execute(
                        """INSERT INTO exercise_source_links(exercise_id,source_id,rationale)
                           SELECT ?,id,? FROM curated_sources WHERE id=?
                           ON CONFLICT(exercise_id,source_id) DO UPDATE SET
                           rationale=excluded.rationale""",
                        (exercise_id,
                         "Referência de orientação temática; enunciado e testes são originais Aprendix.",
                         source_id),
                    )
            last_hybrid: dict[str, str] = {}
            for chapter_position, data in enumerate(chapters):
                (slug, track_slug, node_slug, title, objective, exercise_slug,
                 theory, example, question, options, answer, explanation,
                 hybrid_prompt, hybrid_answer, hybrid_explanation) = data
                track_id, chapter_id = _id("track", track_slug), _id("chapter", slug)
                node = connection.execute("SELECT id FROM graph_nodes WHERE slug=?", (node_slug,)).fetchone()
                exercise = connection.execute("SELECT id FROM exercises WHERE slug=? ORDER BY version DESC", (exercise_slug,)).fetchone()
                if node is None or exercise is None:
                    continue
                for source_id in TRACK_BIBLIOGRAPHY_SOURCE_IDS[track_slug]:
                    connection.execute(
                        """INSERT INTO exercise_source_links(exercise_id,source_id,rationale)
                           SELECT ?,id,? FROM curated_sources WHERE id=?
                           ON CONFLICT(exercise_id,source_id) DO UPDATE SET
                           rationale=excluded.rationale""",
                        (exercise["id"],
                         "Referência técnica do capítulo; teoria e prática são originais Aprendix.",
                         source_id),
                    )
                connection.execute(
                    "INSERT OR IGNORE INTO learning_chapters VALUES(?,?,?,?,?,?,?)",
                    (chapter_id, track_id, node["id"], slug, title, objective, chapter_position),
                )
                unit_ids = {kind: _id("unit", f"{slug}-{kind}") for kind in ("practice", "theory", "quiz", "hybrid")}
                unit_values = (
                    ("practice", "Experimenta antes de ler", "Resolve o exercício no IDE e regista uma tentativa verificável.", "", exercise["id"], 0, 0),
                    ("theory", title, theory, example, None, 1, 1),
                    ("quiz", "Verificação conceptual", "Escolhe uma resposta e explica por que as restantes não servem.", "", None, 2, 1),
                    ("hybrid", "Liga previsão e código", "Prevê o resultado antes de executar; depois compara as duas evidências.", example, None, 3, 1),
                )
                for kind, unit_title, body, code, exercise_id, position, gate in unit_values:
                    identity = unit_ids[kind]
                    connection.execute(
                        "INSERT OR IGNORE INTO learning_units VALUES(?,?,?,?,?,?,?,?,?)",
                        (identity, chapter_id, exercise_id, kind, unit_title,
                         self._encrypt("learning_units.body", identity, body),
                         self._encrypt("learning_units.example", identity, code) if code else None,
                         position, gate),
                    )
                for child, parent in (("theory", "practice"), ("quiz", "theory"), ("hybrid", "quiz")):
                    connection.execute(
                        "INSERT OR IGNORE INTO learning_unit_dependencies VALUES(?,?)",
                        (unit_ids[child], unit_ids[parent]),
                    )
                objective_id = _id("objective", slug)
                connection.execute(
                    "INSERT OR IGNORE INTO curriculum_objectives VALUES(?,?,?,'apply')",
                    (objective_id, f"OBJ-{slug.upper()}", objective),
                )
                connection.executemany(
                    "INSERT OR IGNORE INTO unit_objectives VALUES(?,?,1)",
                    ((unit_id, objective_id) for unit_id in unit_ids.values()),
                )
                assessments = (
                    ("practical", unit_ids["practice"], "Conclui e valida o exercício no IDE.", "passed", "O corretor AST e os testes isolados decidem o resultado.", 0.0, ()),
                    ("theory", unit_ids["quiz"], question, answer, explanation, 0.0,
                     tuple((chr(97 + i), value) for i, value in enumerate(options))),
                    ("hybrid", unit_ids["hybrid"], hybrid_prompt, hybrid_answer, hybrid_explanation, 0.25, ()),
                )
                for kind, unit_id, prompt, expected, why, difficulty, choices in assessments:
                    item_id = _id("assessment", f"{slug}-{kind}")
                    connection.execute(
                        "INSERT OR IGNORE INTO assessment_items VALUES(?,?,?,?,?,?,?)",
                        (item_id, unit_id, kind,
                         self._encrypt("assessment_items.prompt", item_id, prompt),
                         self._encrypt("assessment_items.answer", item_id, expected),
                         self._encrypt("assessment_items.explanation", item_id, why), difficulty),
                    )
                    for position, (option_id, text) in enumerate(choices):
                        connection.execute(
                            "INSERT OR IGNORE INTO assessment_options VALUES(?,?,?,?)",
                            (item_id, option_id,
                             self._encrypt("assessment_options.text", f"{item_id}:{option_id}", text), position),
                        )
                last_hybrid[track_slug] = unit_ids["hybrid"]
            # Within a course, each new chapter starts only after the previous
            # chapter's hybrid check. Content remains viewable at all times;
            # this spine controls credit only.
            for slug, _title, _description, _position in TRACKS:
                ordered = connection.execute(
                    """SELECT c.id chapter_id,
                              (SELECT id FROM learning_units p
                               WHERE p.chapter_id=c.id AND p.kind='practice'
                               ORDER BY p.position,p.id LIMIT 1) practice_id,
                              (SELECT id FROM learning_units h
                               WHERE h.chapter_id=c.id AND h.kind='hybrid'
                               ORDER BY h.position,h.id LIMIT 1) hybrid_id
                       FROM learning_chapters c
                       JOIN learning_tracks t ON t.id=c.track_id
                       WHERE t.slug=? ORDER BY c.position,c.id""",
                    (slug,),
                ).fetchall()
                previous_hybrid = None
                for stage in ordered:
                    if previous_hybrid and stage["practice_id"]:
                        connection.execute(
                            """INSERT OR IGNORE INTO learning_unit_dependencies
                               VALUES(?,?)""",
                            (stage["practice_id"], previous_hybrid),
                        )
                    if stage["hybrid_id"]:
                        previous_hybrid = stage["hybrid_id"]
            for slug, title, description, position in TRACKS:
                unit_id = _id("unit", f"{slug}-project")
                first_chapter = connection.execute(
                    "SELECT id FROM learning_chapters WHERE track_id=? ORDER BY position LIMIT 1",
                    (_id("track", slug),),
                ).fetchone()
                if first_chapter:
                    body = f"Constrói um projeto local curto para {title}; define contrato, três testes, implementação e reflexão sobre um caso-limite."
                    connection.execute(
                        "INSERT OR IGNORE INTO learning_units VALUES(?,?,?,?,?,?,?,?,?)",
                        (unit_id, first_chapter["id"], None, "project", f"Projeto · {title}",
                         self._encrypt("learning_units.body", unit_id, body), None, 99, 1),
                    )
                    project_objective_id = _id("objective", f"{slug}-project")
                    connection.execute(
                        "INSERT OR IGNORE INTO curriculum_objectives VALUES(?,?,?,'create')",
                        (project_objective_id, f"OBJ-{slug.upper()}-PROJECT",
                         f"Criar e justificar um artefacto local verificável para {title}."),
                    )
                    connection.execute(
                        "INSERT OR IGNORE INTO unit_objectives VALUES(?,?,1)",
                        (unit_id, project_objective_id),
                    )
                    if slug in last_hybrid:
                        connection.execute(
                            "INSERT OR IGNORE INTO learning_unit_dependencies VALUES(?,?)",
                            (unit_id, last_hybrid[slug]),
                        )
            # Stable prerequisite spine for an ARPG-like skill tree.  Dynamic
            # co-occurrence later strengthens these edges without replacing it.
            ordered_nodes = []
            for data in chapters:
                node = connection.execute("SELECT id FROM graph_nodes WHERE slug=?", (data[2],)).fetchone()
                if node and node["id"] not in ordered_nodes:
                    ordered_nodes.append(node["id"])
            for source, target in zip(ordered_nodes, ordered_nodes[1:]):
                connection.execute(
                    """INSERT OR IGNORE INTO graph_edges(source_node_id,target_node_id,
                       weight,co_occurrence_count,updated_at) VALUES(?,?,0.35,0,?)""",
                    (source, target, now),
                )
            # Public hierarchy: each principal pathway currently contains one
            # independently versionable course; the schema supports adding more.
            for slug, title, description, position in TRACKS:
                path_id = _id("path", slug)
                track_id = _id("track", slug)
                connection.execute(
                    "INSERT OR IGNORE INTO learning_paths VALUES(?,?,?,?,?,1)",
                    (path_id, slug, f"Percurso · {title}", description, position),
                )
                connection.execute(
                    "INSERT OR IGNORE INTO learning_path_courses VALUES(?,?,0,1)",
                    (path_id, track_id),
                )
            for previous, current in zip(TRACKS, TRACKS[1:]):
                previous_track, current_track = _id("track", previous[0]), _id("track", current[0])
                connection.execute(
                    "INSERT OR IGNORE INTO course_prerequisites VALUES(?,?,0.70)",
                    (current_track, previous_track),
                )
                first_practice = connection.execute(
                    """SELECT u.id FROM learning_units u JOIN learning_chapters c ON c.id=u.chapter_id
                       WHERE c.track_id=? AND u.kind='practice' ORDER BY c.position,u.position LIMIT 1""",
                    (current_track,),
                ).fetchone()
                previous_project = _id("unit", f"{previous[0]}-project")
                project_exists = connection.execute(
                    "SELECT 1 FROM learning_units WHERE id=?", (previous_project,)
                ).fetchone()
                if first_practice is not None and project_exists is not None:
                    connection.execute(
                        "INSERT OR IGNORE INTO learning_unit_dependencies VALUES(?,?)",
                        (first_practice["id"], previous_project),
                    )
            checksum_payload = json.dumps(
                {"tracks": ACADEMY_TRACKS, "modules": ACADEMY_MODULES},
                ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            ).encode("utf-8")
            unit_count = int(connection.execute("SELECT count(*) FROM learning_units").fetchone()[0])
            connection.execute(
                """INSERT INTO curriculum_releases VALUES(?,?,?,?,?,?)
                   ON CONFLICT(version) DO UPDATE SET status=excluded.status,
                   catalog_checksum=excluded.catalog_checksum,track_count=excluded.track_count,
                   unit_count=excluded.unit_count,activated_at=excluded.activated_at""",
                ("academy-1", "active", hashlib.sha256(checksum_payload).hexdigest(),
                 len(TRACKS), unit_count, now),
            )
            glossary_nodes: dict[str, str] = {}
            glossary_relations: list[tuple[str, tuple[str, ...]]] = []
            glossary_specs = (
                *GLOSSARY, *EXTRA_GLOSSARY, *CORE_GLOSSARY, *STDLIB_GLOSSARY_ENTRIES,
                *OFFICIAL_GLOSSARY,
            )
            current_official_entry_ids = {
                _id("glossary", _normalize(spec[0])) for spec in OFFICIAL_GLOSSARY
            }
            # Official headings can change between curated releases.  Remove
            # only superseded generated dictionary rows; local/user content and
            # graph mastery remain untouched.  Without this upgrade path an
            # installed profile accumulated every previous release and falsely
            # exceeded the exact editorial delta.
            stale_official_entry_ids = {
                row["id"] for row in connection.execute(
                    """SELECT DISTINCT e.id FROM glossary_entries e
                       JOIN glossary_source_links l ON l.entry_id=e.id
                       WHERE l.source_id LIKE 'src-official-%'"""
                )
                if row["id"] not in current_official_entry_ids
            }
            if stale_official_entry_ids:
                connection.executemany(
                    "DELETE FROM glossary_entries WHERE id=?",
                    ((entry_id,) for entry_id in sorted(stale_official_entry_ids)),
                )
            glossary_example_counts = {
                row["entry_id"]: int(row["total"])
                for row in connection.execute(
                    """SELECT entry_id,count(*) total FROM glossary_examples
                       GROUP BY entry_id"""
                )
            }
            source_catalog = {
                row["id"]: row["title"]
                for row in connection.execute("SELECT id,title FROM curated_sources")
            }
            detailed_python_source = {}
            for source_id, source_title in source_catalog.items():
                suffix = " — Python 3 Documentation"
                if source_id.startswith("src-pydoc-") and suffix in source_title:
                    detailed_python_source[_normalize(source_title.split(suffix, 1)[0])] = source_id
            for term, technology, definition, signature, example, related in glossary_specs:
                identity = _id("glossary", _normalize(term))
                normalized_term = _normalize(term)
                connection.execute(
                    "INSERT OR IGNORE INTO glossary_entries VALUES(?,?,?,?,?,?,?,?)",
                    (identity, term, normalized_term, technology,
                     self._encrypt("glossary_entries.definition", identity, definition),
                     self._encrypt("glossary_entries.signature", identity, signature),
                     self._encrypt("glossary_entries.example", identity, example),
                     json.dumps(related, ensure_ascii=False, separators=(",", ":"))),
                )
                node_id = _id("graph-node", f"concept:{normalized_term}")
                node_slug = "concept-" + re.sub(r"[^a-z0-9]+", "-", normalized_term).strip("-")
                if node_slug == "concept-":
                    node_slug += hashlib.sha256(term.encode("utf-8")).hexdigest()[:12]
                elif len(node_slug) > 80:
                    suffix = hashlib.sha256(node_slug.encode("utf-8")).hexdigest()[:12]
                    node_slug = f"{node_slug[:67].rstrip('-')}-{suffix}"
                collision = connection.execute(
                    "SELECT id FROM graph_nodes WHERE slug=? AND id<>?",
                    (node_slug, node_id),
                ).fetchone()
                if collision is not None:
                    suffix = hashlib.sha256(normalized_term.encode("utf-8")).hexdigest()[:12]
                    node_slug = f"{node_slug[:67].rstrip('-')}-{suffix}"
                connection.execute(
                    """INSERT INTO graph_nodes(
                       id,slug,title,description,difficulty,created_at,updated_at)
                       VALUES(?,?,?,?,0.0,?,?) ON CONFLICT(id) DO UPDATE SET
                       slug=excluded.slug,title=excluded.title,
                       description=excluded.description,updated_at=excluded.updated_at""",
                    (node_id, node_slug, term,
                     f"Conceito local de {technology}; abre o dicionário para definição, exemplo e fontes.",
                     now, now),
                )
                glossary_nodes[normalized_term] = node_id
                glossary_relations.append((normalized_term, related))
                linked_source_ids = tuple(dict.fromkeys((
                    *OFFICIAL_GLOSSARY_SOURCE_IDS.get(term, ()),
                    *GLOSSARY_SOURCE_IDS.get(term, ()),
                    *((detailed_python_source.get(normalized_term),)
                      if detailed_python_source.get(normalized_term) else ()),
                    *_GLOSSARY_TECHNOLOGY_SOURCES.get(
                        technology,
                        ("src-python-docs", "src-fluent-python"),
                    ),
                )))
                linked_source_ids = tuple(
                    source_id for source_id in linked_source_ids if source_id in source_catalog
                )[:4]
                for position, source_id in enumerate(linked_source_ids):
                    connection.execute(
                        """INSERT INTO glossary_source_links(
                            entry_id,source_id,position,rationale
                           ) VALUES(?,?,?,?)
                           ON CONFLICT(entry_id,source_id) DO UPDATE SET
                           position=excluded.position,rationale=excluded.rationale""",
                        (
                            identity, source_id, position,
                            "Referência técnica aprovada; definição e exemplos são originais Aprendix.",
                        ),
                    )
                example_source_id = linked_source_ids[0] if linked_source_ids else None
                generated_examples = (
                    () if glossary_example_counts.get(identity, 0) >= 2 else
                    _glossary_examples(term, definition, signature, example)
                )
                for ordinal, (example_text, explanation, difficulty, context) in enumerate(
                    generated_examples
                ):
                    example_id = _id("glossary-example", f"{normalized_term}:{ordinal}")
                    connection.execute(
                        """INSERT INTO glossary_examples(
                            id,entry_id,ordinal,example_encrypted,explanation_encrypted,
                            difficulty,context,source_id
                           ) VALUES(?,?,?,?,?,?,?,?)
                           ON CONFLICT(id) DO UPDATE SET
                           example_encrypted=excluded.example_encrypted,
                           explanation_encrypted=excluded.explanation_encrypted,
                           difficulty=excluded.difficulty,context=excluded.context,
                           source_id=excluded.source_id""",
                        (
                            example_id, identity, ordinal,
                            self._encrypt("glossary_examples.example", example_id, example_text),
                            self._encrypt("glossary_examples.explanation", example_id, explanation),
                            difficulty, context, example_source_id,
                        ),
                    )
            for canonical, aliases in (
                *GLOSSARY_ALIASES,
                *GENERATED_GLOSSARY_ALIASES,
                *OFFICIAL_GLOSSARY_ALIASES,
            ):
                entry = connection.execute(
                    "SELECT id FROM glossary_entries WHERE normalized_term=?",
                    (_normalize(canonical),),
                ).fetchone()
                if entry is None:
                    continue
                for alias in aliases:
                    normalized_alias = _normalize(alias)
                    if not normalized_alias or normalized_alias == _normalize(canonical):
                        continue
                    connection.execute(
                        "INSERT OR IGNORE INTO glossary_aliases VALUES(?,?,?,'und')",
                        (entry["id"], alias, normalized_alias),
                    )
            for term, source_ids in GLOSSARY_SOURCE_IDS.items():
                entry = connection.execute(
                    "SELECT id FROM glossary_entries WHERE normalized_term=?",
                    (_normalize(term),),
                ).fetchone()
                if entry is None:
                    continue
                for position, source_id in enumerate(source_ids):
                    connection.execute(
                        """INSERT INTO glossary_source_links(entry_id,source_id,position,rationale)
                           SELECT ?,id,?,? FROM curated_sources WHERE id=?
                           ON CONFLICT(entry_id,source_id) DO UPDATE SET
                           position=excluded.position,rationale=excluded.rationale""",
                        (entry["id"], position,
                         "Referência para aprofundar; definição e exemplo são originais Aprendix.",
                         source_id),
                    )
            for source_term, related_terms in glossary_relations:
                source_node = glossary_nodes[source_term]
                for related_term in related_terms:
                    target_node = glossary_nodes.get(_normalize(related_term))
                    if target_node is None or target_node == source_node:
                        continue
                    connection.execute(
                        """INSERT OR IGNORE INTO graph_edges(source_node_id,target_node_id,
                           weight,co_occurrence_count,updated_at) VALUES(?,?,0.20,0,?)""",
                        (source_node, target_node, now),
                    )

    def rebuild_bibliography_links(self) -> int:
        with self._database.transaction() as connection:
            connection.execute("DELETE FROM bibliography_links")
            connection.execute("""
                WITH ordered AS (
                    SELECT chunk_id, cluster_id, probability,
                           lag(chunk_id) OVER(PARTITION BY cluster_id ORDER BY probability DESC, chunk_id) previous
                    FROM knowledge_cluster_members
                    WHERE cluster_id <> 'noise'
                )
                INSERT OR IGNORE INTO bibliography_links(source_chunk_id,target_chunk_id,relation,weight)
                SELECT previous, chunk_id, 'same-cluster',
                       min(1.0, max(0.05, probability))
                FROM ordered WHERE previous IS NOT NULL AND previous <> chunk_id
            """)
            connection.execute("""
                WITH ordered AS (
                    SELECT id, graph_node_id,
                           lag(id) OVER(PARTITION BY graph_node_id ORDER BY ordinal, id) previous
                    FROM document_chunks WHERE graph_node_id IS NOT NULL
                )
                INSERT OR IGNORE INTO bibliography_links(source_chunk_id,target_chunk_id,relation,weight)
                SELECT previous, id, 'same-concept', 0.9 FROM ordered
                WHERE previous IS NOT NULL AND previous <> id
            """)
            connection.execute("""
                WITH ranked AS (
                    SELECT kac.area_id, kac.chunk_id, kac.relevance,
                           lag(kac.chunk_id) OVER(
                               PARTITION BY kac.area_id
                               ORDER BY kac.relevance DESC, kac.chunk_id
                           ) previous
                    FROM knowledge_area_chunks kac
                    JOIN document_chunks c ON c.id=kac.chunk_id
                    JOIN documents d ON d.id=c.document_id
                    LEFT JOIN chunk_quality q ON q.chunk_id=c.id
                    WHERE d.lifecycle='active'
                      AND COALESCE(q.status,'accepted')='accepted'
                )
                INSERT OR IGNORE INTO bibliography_links(
                    source_chunk_id,target_chunk_id,relation,weight
                )
                SELECT previous,chunk_id,'related',min(0.88,max(0.35,relevance))
                FROM ranked
                WHERE previous IS NOT NULL AND previous <> chunk_id
            """)
            return int(connection.execute("SELECT count(*) FROM bibliography_links").fetchone()[0])

    def tracks(self) -> tuple[dict[str, object], ...]:
        with self._database.read_connection() as connection:
            rows = connection.execute("""
                SELECT t.*, count(distinct c.id) chapters, count(distinct u.id) units
                FROM learning_tracks t LEFT JOIN learning_chapters c ON c.track_id=t.id
                LEFT JOIN learning_units u ON u.chapter_id=c.id
                GROUP BY t.id ORDER BY t.position
            """).fetchall()
        return tuple(dict(row) for row in rows)

    def paths(self, user_id: UUID) -> tuple[dict[str, object], ...]:
        with self._database.read_connection() as connection:
            rows = connection.execute(
                """SELECT p.id,p.slug,p.title,p.description,p.position,t.id track_id,
                          t.slug track_slug,t.title course_title,
                          count(DISTINCT u.id) total_units
                   FROM learning_paths p JOIN learning_path_courses pc ON pc.path_id=p.id
                   JOIN learning_tracks t ON t.id=pc.track_id
                   LEFT JOIN learning_chapters c ON c.track_id=t.id
                   LEFT JOIN learning_units u ON u.chapter_id=c.id
                   WHERE p.active=1 GROUP BY p.id,t.id ORDER BY p.position,pc.position""",
            ).fetchall()
            valid_ids = valid_completed_ids(connection, user_id)
            unit_rows = connection.execute(
                """SELECT u.id,u.kind,c.track_id FROM learning_units u
                   JOIN learning_chapters c ON c.id=u.chapter_id"""
            ).fetchall()
            unit_tracks = {
                str(row["id"]): (str(row["track_id"]), str(row["kind"]))
                for row in unit_rows
            }
            completed_counts: dict[str, int] = {}
            completed_projects = set()
            for unit_id in valid_ids:
                context = unit_tracks.get(unit_id)
                if context is None:
                    continue
                track_id, kind = context
                completed_counts[track_id] = completed_counts.get(track_id, 0) + 1
                if kind == "project":
                    completed_projects.add(track_id)
            prerequisites = {}
            for row in connection.execute("SELECT * FROM course_prerequisites"):
                prerequisites.setdefault(row["track_id"], set()).add(row["prerequisite_track_id"])
        result = []
        for row in rows:
            item = dict(row)
            item["completed_units"] = completed_counts.get(item["track_id"], 0)
            completed = bool(item["total_units"]) and (
                item["completed_units"] >= item["total_units"]
            )
            eligible = not completed and prerequisites.get(
                item["track_id"], set()
            ).issubset(completed_projects)
            item["viewable"] = True
            item["credit_eligible"] = eligible
            item["completed"] = completed
            item["reason_code"] = (
                "completed" if completed else
                "eligible" if eligible else "prerequisites_incomplete"
            )
            item["unlocked"] = eligible or completed
            item["progress"] = (
                item["completed_units"] / item["total_units"] if item["total_units"] else 0.0
            )
            result.append(item)
        return tuple(result)

    def validate_catalog(self) -> dict[str, object]:
        """Return a deterministic structural audit used as the CURR-1 gate."""
        with self._database.read_connection() as connection:
            counts = {
                "paths": connection.execute("SELECT count(*) FROM learning_paths WHERE active=1").fetchone()[0],
                "tracks": connection.execute("SELECT count(*) FROM learning_tracks").fetchone()[0],
                "chapters": connection.execute("SELECT count(*) FROM learning_chapters").fetchone()[0],
                "units": connection.execute("SELECT count(*) FROM learning_units").fetchone()[0],
                "objectives": connection.execute("SELECT count(*) FROM curriculum_objectives").fetchone()[0],
                "exercises": connection.execute("SELECT count(*) FROM exercises").fetchone()[0],
            }
            defects = {
                "orphan_units": connection.execute(
                    """SELECT count(*) FROM learning_units u LEFT JOIN learning_chapters c
                       ON c.id=u.chapter_id WHERE c.id IS NULL"""
                ).fetchone()[0],
                "units_without_objective": connection.execute(
                    """SELECT count(*) FROM learning_units u LEFT JOIN unit_objectives o
                       ON o.unit_id=u.id WHERE o.unit_id IS NULL"""
                ).fetchone()[0],
                "practice_without_exercise": connection.execute(
                    "SELECT count(*) FROM learning_units WHERE kind='practice' AND exercise_id IS NULL"
                ).fetchone()[0],
                "tracks_without_project": connection.execute(
                    """SELECT count(*) FROM learning_tracks t WHERE NOT EXISTS(
                       SELECT 1 FROM learning_chapters c JOIN learning_units u ON u.chapter_id=c.id
                       WHERE c.track_id=t.id AND u.kind='project')"""
                ).fetchone()[0],
                "assessments_without_objective": connection.execute(
                    """SELECT count(*) FROM assessment_items a JOIN learning_units u ON u.id=a.unit_id
                       LEFT JOIN unit_objectives o ON o.unit_id=u.id WHERE o.objective_id IS NULL"""
                ).fetchone()[0],
            }
            edges = connection.execute(
                "SELECT unit_id,prerequisite_unit_id FROM learning_unit_dependencies"
            ).fetchall()
            executable_sources = connection.execute(
                "SELECT starter_code,tests_json FROM exercises"
            ).fetchall()
        invalid_syntax = 0
        for source in executable_sources:
            try:
                ast.parse(source["starter_code"])
                for test in json.loads(source["tests_json"]):
                    if test.lower().startswith("stdout equals"):
                        continue
                    ast.parse(test)
            except (SyntaxError, TypeError, json.JSONDecodeError):
                invalid_syntax += 1
        defects["invalid_executable_syntax"] = invalid_syntax
        graph = {}
        for edge in edges:
            graph.setdefault(edge["unit_id"], set()).add(edge["prerequisite_unit_id"])
        visiting, visited = set(), set()
        def has_cycle(node):
            if node in visiting: return True
            if node in visited: return False
            visiting.add(node)
            cycle = any(has_cycle(parent) for parent in graph.get(node, ()))
            visiting.remove(node); visited.add(node)
            return cycle
        defects["dependency_cycles"] = int(any(has_cycle(node) for node in tuple(graph)))
        return {"valid": not any(defects.values()), "counts": counts, "defects": defects}

    def units(self, track_slug: str, user_id: UUID, *,
              include_quarantined: bool = False) -> tuple[dict[str, object], ...]:
        quality_filter = "" if include_quarantined else "AND COALESCE(pq.status, 'accepted') = 'accepted'"
        with self._database.read_connection() as connection:
            rows = connection.execute(f"""
                SELECT u.*, c.title chapter_title, c.graph_node_id,
                       (SELECT id FROM assessment_items a WHERE a.unit_id=u.id LIMIT 1) assessment_id,
                       EXISTS(SELECT 1 FROM learning_unit_progress p
                              WHERE p.user_id=? AND p.unit_id=u.id) completed
                FROM learning_units u JOIN learning_chapters c ON c.id=u.chapter_id
                JOIN learning_tracks t ON t.id=c.track_id
                LEFT JOIN pedagogical_quality pq
                  ON pq.item_type='unit' AND pq.item_id=u.id
                WHERE t.slug=? {quality_filter}
                ORDER BY c.position,u.position
            """, (str(user_id), track_slug)).fetchall()
            completed_ids = valid_completed_ids(connection, user_id)
            dependencies = {}
            for row in connection.execute("SELECT unit_id,prerequisite_unit_id FROM learning_unit_dependencies"):
                dependencies.setdefault(row["unit_id"], set()).add(row["prerequisite_unit_id"])
            course_dependencies = {
                str(row["id"]) for row in connection.execute(
                    """SELECT parent.id FROM learning_tracks child
                       JOIN course_prerequisites cp ON cp.track_id=child.id
                       JOIN learning_chapters parent_chapter
                         ON parent_chapter.track_id=cp.prerequisite_track_id
                       JOIN learning_units parent
                         ON parent.chapter_id=parent_chapter.id
                        AND parent.kind='project'
                       WHERE child.slug=?""",
                    (track_slug,),
                ).fetchall()
            }
        result = []
        for row in rows:
            item = dict(row); identity = item["id"]
            item["body"] = self._decrypt("learning_units.body", identity, item.pop("body_encrypted"))
            item["example"] = self._decrypt("learning_units.example", identity, item.pop("example_encrypted"))
            access = access_from_state(
                resource_id=identity,
                resource_kind=str(item["kind"]),
                track_slug=track_slug,
                completed=identity in completed_ids,
                prerequisite_ids=(
                    set(dependencies.get(identity, set())) | course_dependencies
                ),
                completed_ids=completed_ids,
            )
            item["viewable"] = access.viewable
            item["credit_eligible"] = access.credit_eligible
            item["completed"] = access.completed
            item["reason_code"] = access.reason_code.value
            item["missing_prerequisite_ids"] = access.missing_prerequisite_ids
            item["unlocked"] = access.credit_eligible or access.completed
            result.append(item)
        return tuple(result)

    def diagnostic(self, user_id: UUID, *, limit: int = 5) -> tuple[dict[str, object], ...]:
        """Choose an auditable cold-start sequence without jumping prerequisites."""
        with self._database.read_connection() as connection:
            ability = float(connection.execute(
                "SELECT COALESCE(avg(irt_ability),-1.0) FROM mastery_states WHERE user_id=?",
                (str(user_id),),
            ).fetchone()[0])
            rows = connection.execute(
                """SELECT DISTINCT e.id,e.slug,e.title,e.difficulty,u.id unit_id,
                          c.title chapter_title,
                          t.slug track_slug,
                          EXISTS(SELECT 1 FROM attempts a WHERE a.user_id=? AND a.exercise_id=e.id) attempted
                   FROM exercises e JOIN learning_units u ON u.exercise_id=e.id
                   JOIN learning_chapters c ON c.id=u.chapter_id
                   JOIN learning_tracks t ON t.id=c.track_id
                   WHERE u.kind='practice' AND (EXISTS(
                     SELECT 1 FROM learning_unit_progress started
                     JOIN learning_units su ON su.id=started.unit_id
                     JOIN learning_chapters sc ON sc.id=su.chapter_id
                     WHERE started.user_id=? AND sc.track_id=t.id
                   ) OR NOT EXISTS(
                     SELECT 1 FROM course_prerequisites cp WHERE cp.track_id=t.id
                     AND NOT EXISTS(
                       SELECT 1 FROM learning_unit_progress up
                       JOIN learning_units pu ON pu.id=up.unit_id
                       JOIN learning_chapters pc ON pc.id=pu.chapter_id
                       WHERE up.user_id=? AND pu.kind='project'
                       AND pc.track_id=cp.prerequisite_track_id)))
                   ORDER BY attempted,abs(e.difficulty-?),e.difficulty,e.slug LIMIT 200""",
                (str(user_id), str(user_id), str(user_id), ability),
            ).fetchall()
            valid_ids = valid_completed_ids(connection, user_id)
            candidate_ids = {str(row["unit_id"]) for row in rows}
            dependencies: dict[str, set[str]] = {}
            if candidate_ids:
                placeholders = ",".join("?" for _ in candidate_ids)
                for dependency in connection.execute(
                    f"""SELECT unit_id,prerequisite_unit_id
                        FROM learning_unit_dependencies
                        WHERE unit_id IN ({placeholders})""",
                    tuple(sorted(candidate_ids)),
                ).fetchall():
                    dependencies.setdefault(
                        str(dependency["unit_id"]), set()
                    ).add(str(dependency["prerequisite_unit_id"]))
            eligible = tuple(
                row for row in rows
                if str(row["unit_id"]) not in valid_ids
                and dependencies.get(str(row["unit_id"]), set()).issubset(valid_ids)
            )[:max(1, min(10, limit))]
        return tuple({
            **dict(row), "target_ability": ability,
            "reason_code": "maximum_information_near_ability",
        } for row in eligible)

    def complete_unit(self, user_id: UUID, unit_id: str):
        now = datetime.now(UTC).isoformat()
        with self._database.transaction() as connection:
            row = connection.execute("SELECT kind FROM learning_units WHERE id=?", (unit_id,)).fetchone()
            if row is None: raise KeyError(unit_id)
            if row["kind"] == "practice":
                raise ValueError("practice units are completed only by a passed IDE attempt")
            if row["kind"] in {"quiz", "hybrid"}:
                raise ValueError(
                    "assessment units are completed only by a passed assessment attempt"
                )
            if row["kind"] == "project":
                raise ValueError(
                    "project units are completed only by an approved matching capstone evaluation"
                )
            access = unit_access(connection, user_id, unit_id)
            if access.completed:
                return access
            if not access.credit_eligible:
                raise ValueError("unit prerequisites are not complete")
            connection.execute(
                "INSERT OR IGNORE INTO learning_unit_progress VALUES(?,?,?)",
                (str(user_id), unit_id, now),
            )
            return unit_access(connection, user_id, unit_id)

    def progress_integrity_audit(self, user_id: UUID) -> dict[str, object]:
        """Aggregate legacy progress that cannot safely unlock the curriculum."""

        with self._database.read_connection() as connection:
            rows = connection.execute(
                """SELECT p.unit_id,u.kind FROM learning_unit_progress p
                   JOIN learning_units u ON u.id=p.unit_id
                   WHERE p.user_id=?""",
                (str(user_id),),
            ).fetchall()
            valid = valid_completed_ids(connection, user_id)
        by_kind: dict[str, int] = {}
        suspicious = 0
        for row in rows:
            if str(row["unit_id"]) in valid:
                continue
            suspicious += 1
            kind = str(row["kind"])
            by_kind[kind] = by_kind.get(kind, 0) + 1
        return {
            "recorded": len(rows),
            "valid": len(valid),
            "suspicious": suspicious,
            "suspicious_by_kind": dict(sorted(by_kind.items())),
            "history_preserved": True,
            "used_for_unlocking": False,
        }

    def _materialize_glossary_entries(
        self, entry_ids: tuple[str, ...],
    ) -> tuple[dict[str, object], ...]:
        """Decrypt only the already ranked glossary entries and their evidence."""

        if not entry_ids:
            return ()
        placeholders = ",".join("?" for _ in entry_ids)
        with self._database.read_connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM glossary_entries WHERE id IN ({placeholders})",
                entry_ids,
            ).fetchall()
            alias_rows = connection.execute(
                f"""SELECT entry_id,alias FROM glossary_aliases
                    WHERE entry_id IN ({placeholders}) ORDER BY normalized_alias""",
                entry_ids,
            ).fetchall()
            source_rows = connection.execute(
                f"""SELECT l.entry_id,s.title,s.canonical_url
                   FROM glossary_source_links l
                   JOIN curated_sources s ON s.id=l.source_id
                   WHERE l.entry_id IN ({placeholders})
                   ORDER BY l.entry_id,l.position,s.title""",
                entry_ids,
            ).fetchall()
            example_rows = connection.execute(
                f"""SELECT id,entry_id,ordinal,example_encrypted,explanation_encrypted,
                           difficulty,context,source_id
                    FROM glossary_examples WHERE entry_id IN ({placeholders})
                    ORDER BY entry_id,ordinal""",
                entry_ids,
            ).fetchall()
        rows_by_id = {str(row["id"]): row for row in rows}
        aliases: dict[str, list[str]] = {}
        for row in alias_rows:
            aliases.setdefault(str(row["entry_id"]), []).append(str(row["alias"]))
        sources: dict[str, list[tuple[str, str]]] = {}
        for row in source_rows:
            sources.setdefault(str(row["entry_id"]), []).append(
                (str(row["title"]), str(row["canonical_url"]))
            )
        examples: dict[str, list[dict[str, object]]] = {}
        for row in example_rows:
            example_id = str(row["id"])
            examples.setdefault(str(row["entry_id"]), []).append({
                "id": example_id,
                "example": self._decrypt(
                    "glossary_examples.example", example_id, row["example_encrypted"]
                ),
                "explanation": self._decrypt(
                    "glossary_examples.explanation", example_id,
                    row["explanation_encrypted"],
                ),
                "difficulty": row["difficulty"], "context": row["context"],
                "source_id": row["source_id"],
            })
        reference_map = {
            "python": (("Documentação Python", "https://docs.python.org/3/"),),
            "sql": (("PostgreSQL Documentation", "https://www.postgresql.org/docs/current/"),),
            "javascript": (("MDN Web Docs", "https://developer.mozilla.org/docs/Web/JavaScript"),),
            "django": (("Django Documentation", "https://docs.djangoproject.com/"),),
            "numpy": (("NumPy Documentation", "https://numpy.org/doc/stable/"),),
            "pandas": (("pandas Documentation", "https://pandas.pydata.org/docs/"),),
            "pytorch": (("PyTorch Documentation", "https://pytorch.org/docs/stable/"),),
        }
        materialized = []
        for identity in entry_ids:
            row = rows_by_id.get(identity)
            if row is None:
                continue
            item = dict(row)
            for name in ("definition", "signature", "example"):
                item[name] = self._decrypt(
                    f"glossary_entries.{name}", identity,
                    item.pop(f"{name}_encrypted"),
                )
            item["related_terms"] = tuple(json.loads(item.pop("related_terms_json")))
            item["aliases"] = tuple(aliases.get(identity, ()))
            item["examples"] = tuple(examples.get(identity, ()))
            item["references"] = tuple(sources.get(identity, ())) or reference_map.get(
                item["technology"], (
                    ("Python Glossary", "https://docs.python.org/3/glossary.html"),
                    ("Aprendix · conhecimento local", "aprendix://dictionary"),
                ),
            )
            materialized.append(item)
        return tuple(materialized)

    def glossary(self, term: str, *, limit: int = 8) -> tuple[dict[str, object], ...]:
        normalized = _normalize(term)
        result_limit = max(1, min(limit, 30))
        if normalized:
            with self._database.read_connection() as connection:
                exact_rows = connection.execute(
                    """SELECT id,0 priority FROM glossary_entries
                       WHERE normalized_term=?
                       UNION ALL
                       SELECT entry_id id,1 priority FROM glossary_aliases
                       WHERE normalized_alias=?
                       ORDER BY priority,id LIMIT ?""",
                    (normalized, normalized, result_limit),
                ).fetchall()
            exact_ids = tuple(dict.fromkeys(str(row["id"]) for row in exact_rows))
            if exact_ids:
                return self._materialize_glossary_entries(exact_ids)
        with self._database.read_connection() as connection:
            if normalized:
                candidate_rows = connection.execute(
                    """SELECT e.id FROM glossary_entries e
                       WHERE e.normalized_term=?
                       UNION
                       SELECT a.entry_id FROM glossary_aliases a
                       WHERE a.normalized_alias=?
                       LIMIT 30""",
                    (normalized, normalized),
                ).fetchall()
                if not candidate_rows:
                    escaped = normalized.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                    candidate_rows = connection.execute(
                    """SELECT DISTINCT e.id FROM glossary_entries e
                       LEFT JOIN glossary_aliases a ON a.entry_id=e.id
                       WHERE e.normalized_term LIKE ? ESCAPE '\\'
                           OR a.normalized_alias LIKE ? ESCAPE '\\'
                           OR e.normalized_term LIKE ? ESCAPE '\\'
                           OR a.normalized_alias LIKE ? ESCAPE '\\'
                       LIMIT 320""",
                        (escaped + "%", escaped + "%",
                         "%" + escaped + "%", "%" + escaped + "%"),
                    ).fetchall()
                if not candidate_rows and len(normalized) >= 2:
                    prefix = normalized[:2].replace("%", "\\%").replace("_", "\\_") + "%"
                    candidate_rows = connection.execute(
                        """SELECT DISTINCT e.id FROM glossary_entries e
                           LEFT JOIN glossary_aliases a ON a.entry_id=e.id
                           WHERE e.normalized_term LIKE ? ESCAPE '\\'
                              OR a.normalized_alias LIKE ? ESCAPE '\\' LIMIT 320""",
                        (prefix, prefix),
                    ).fetchall()
            else:
                candidate_rows = connection.execute(
                    "SELECT id FROM glossary_entries ORDER BY normalized_term LIMIT 30"
                ).fetchall()
            candidate_ids = tuple(row["id"] for row in candidate_rows)
            if not candidate_ids:
                candidate_ids = tuple(row["id"] for row in connection.execute(
                    "SELECT id FROM glossary_entries ORDER BY normalized_term"
                ).fetchall())
            placeholders = ",".join("?" for _ in candidate_ids)
            rows = connection.execute(
                f"SELECT * FROM glossary_entries WHERE id IN ({placeholders}) ORDER BY normalized_term",
                candidate_ids,
            ).fetchall()
            alias_rows = connection.execute(
                f"""SELECT entry_id,alias,normalized_alias FROM glossary_aliases
                    WHERE entry_id IN ({placeholders}) ORDER BY normalized_alias""",
                candidate_ids,
            ).fetchall()
            source_rows = connection.execute(
                f"""SELECT l.entry_id,s.title,s.canonical_url FROM glossary_source_links l
                   JOIN curated_sources s ON s.id=l.source_id
                   WHERE l.entry_id IN ({placeholders})
                   ORDER BY l.entry_id,l.position,s.title""",
                candidate_ids,
            ).fetchall()
            example_rows = connection.execute(
                f"""SELECT id,entry_id,ordinal,example_encrypted,explanation_encrypted,
                           difficulty,context,source_id
                    FROM glossary_examples WHERE entry_id IN ({placeholders})
                    ORDER BY entry_id,ordinal""",
                candidate_ids,
            ).fetchall()
        aliases_by_entry: dict[str, list[tuple[str, str]]] = {}
        for alias in alias_rows:
            aliases_by_entry.setdefault(alias["entry_id"], []).append(
                (alias["alias"], alias["normalized_alias"])
            )
        sources_by_entry: dict[str, list[tuple[str, str]]] = {}
        for source in source_rows:
            sources_by_entry.setdefault(source["entry_id"], []).append(
                (source["title"], source["canonical_url"])
            )
        examples_by_entry: dict[str, list[dict[str, object]]] = {}
        for example in example_rows:
            example_id = example["id"]
            examples_by_entry.setdefault(example["entry_id"], []).append({
                "id": example_id,
                "example": self._decrypt(
                    "glossary_examples.example", example_id, example["example_encrypted"]
                ),
                "explanation": self._decrypt(
                    "glossary_examples.explanation", example_id,
                    example["explanation_encrypted"],
                ),
                "difficulty": example["difficulty"],
                "context": example["context"],
                "source_id": example["source_id"],
            })
        query_tokens = set(normalized.split())
        def rank(row):
            candidate = row["normalized_term"]
            aliases = aliases_by_entry.get(row["id"], ())
            alias_values = tuple(value for _label, value in aliases)
            related = " ".join(json.loads(row["related_terms_json"])).casefold()
            exact = candidate == normalized
            exact_alias = normalized in alias_values
            prefix = (candidate.startswith(normalized) or normalized.startswith(candidate) or
                      any(value.startswith(normalized) or normalized.startswith(value) for value in alias_values))
            substring = (normalized in candidate or candidate in normalized or
                         any(normalized in value or value in normalized for value in alias_values))
            overlap = len(query_tokens & set((candidate + " " + related + " " + " ".join(alias_values)).split()))
            similarity = max(
                (SequenceMatcher(None, normalized, value).ratio()
                 for value in (candidate, *alias_values)), default=0.0,
            ) if normalized else 0.0
            return (int(exact), int(exact_alias), int(prefix), int(substring), overlap, similarity, -len(candidate))
        rows = sorted(rows, key=rank, reverse=True)
        if normalized:
            rows = [row for row in rows if rank(row)[:5] != (0, 0, 0, 0, 0) or rank(row)[5] >= .36]
        rows = rows[:max(1, min(limit, 30))]
        result = []
        for row in rows:
            item, identity = dict(row), row["id"]
            for name in ("definition", "signature", "example"):
                item[name] = self._decrypt(f"glossary_entries.{name}", identity, item.pop(f"{name}_encrypted"))
            item["related_terms"] = tuple(json.loads(item.pop("related_terms_json")))
            item["aliases"] = tuple(label for label, _normalized in aliases_by_entry.get(identity, ()))
            item["examples"] = tuple(examples_by_entry.get(identity, ()))
            reference_map = {
                "python": (("Documentação Python", "https://docs.python.org/3/"),),
                "sql": (("PostgreSQL Documentation", "https://www.postgresql.org/docs/current/"),),
                "javascript": (("MDN Web Docs", "https://developer.mozilla.org/docs/Web/JavaScript"),),
                "django": (("Django Documentation", "https://docs.djangoproject.com/"),),
                "numpy": (("NumPy Documentation", "https://numpy.org/doc/stable/"),),
                "pandas": (("pandas Documentation", "https://pandas.pydata.org/docs/"),),
                "pytorch": (("PyTorch Documentation", "https://pytorch.org/docs/stable/"),),
            }
            item["references"] = tuple(sources_by_entry.get(identity, ())) or reference_map.get(
                item["technology"], (
                    ("Python Glossary", "https://docs.python.org/3/glossary.html"),
                    ("Aprendix · conhecimento local", "aprendix://dictionary"),
                )
            )
            result.append(item)
        return tuple(result)

    def assessment(self, item_id: str) -> dict[str, object]:
        with self._database.read_connection() as connection:
            row = connection.execute("""
                SELECT ai.*, lc.graph_node_id FROM assessment_items ai
                JOIN learning_units lu ON lu.id=ai.unit_id
                JOIN learning_chapters lc ON lc.id=lu.chapter_id WHERE ai.id=?
            """, (item_id,)).fetchone()
            if row is None: raise KeyError(item_id)
            options = connection.execute(
                "SELECT * FROM assessment_options WHERE item_id=? ORDER BY position", (item_id,)
            ).fetchall()
        result = dict(row)
        result["prompt"] = self._decrypt("assessment_items.prompt", item_id, result.pop("prompt_encrypted"))
        result.pop("answer_encrypted"); result.pop("explanation_encrypted")
        result["options"] = tuple({
            "id": option["option_id"],
            "text": self._decrypt("assessment_options.text", f"{item_id}:{option['option_id']}", option["text_encrypted"]),
        } for option in options)
        return result

    def grade(self, user_id: UUID, item_id: str, answer: str, *,
              duration_seconds: int | None = None, mode: str = "training") -> dict[str, object]:
        if mode not in {"training", "evaluation"}:
            raise ValueError("Modo de avaliação inválido.")
        with self._database.transaction() as connection:
            row = connection.execute("SELECT * FROM assessment_items WHERE id=?", (item_id,)).fetchone()
            if row is None: raise KeyError(item_id)
            if row["kind"] == "practical":
                raise ValueError("practical assessments are graded only by the IDE")
            access = unit_access(connection, user_id, str(row["unit_id"]))
            expected = self._decrypt("assessment_items.answer", item_id, row["answer_encrypted"])
            explanation = self._decrypt("assessment_items.explanation", item_id, row["explanation_encrypted"])
            passed = _normalize(answer) == _normalize(expected)
            attempt_id, now = str(uuid4()), datetime.now(UTC).isoformat()
            encrypted = self._encrypt("assessment_attempts.answer", attempt_id, answer)
            connection.execute(
                """INSERT INTO assessment_attempts(
                   id,user_id,item_id,answer_encrypted,passed,score,created_at,duration_seconds,mode)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (attempt_id, str(user_id), item_id, encrypted, int(passed),
                 1.0 if passed else 0.0, now, duration_seconds, mode),
            )
            credit_awarded = False
            if passed and access.credit_eligible:
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO learning_unit_progress VALUES(?,?,?)",
                    (str(user_id), row["unit_id"], now),
                )
                credit_awarded = cursor.rowcount == 1
                access = unit_access(connection, user_id, str(row["unit_id"]))
        return {
            "attempt_id": attempt_id,
            "passed": passed,
            "score": 1.0 if passed else 0.0,
            "kind": row["kind"],
            "mode": mode,
            "viewable": access.viewable,
            "credit_eligible": access.credit_eligible,
            "completed": access.completed,
            "reason_code": access.reason_code.value,
            "missing_prerequisite_ids": access.missing_prerequisite_ids,
            "credit_awarded": credit_awarded,
            "explanation": explanation if mode == "training" else "",
            "feedback": (
                "Resposta registada em avaliação sem revelar a solução; a explicação fica disponível no modo de treino."
                if mode == "evaluation" else explanation
            ),
        }

    def graph_node_for_assessment(self, item_id: str) -> str:
        with self._database.read_connection() as connection:
            row = connection.execute("""
                SELECT c.graph_node_id FROM assessment_items a
                JOIN learning_units u ON u.id=a.unit_id
                JOIN learning_chapters c ON c.id=u.chapter_id WHERE a.id=?
            """, (item_id,)).fetchone()
        if row is None: raise KeyError(item_id)
        return str(row["graph_node_id"])
