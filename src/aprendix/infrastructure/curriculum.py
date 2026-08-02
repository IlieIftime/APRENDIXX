"""Encrypted curriculum, assessments, glossary and bibliography graph."""

from __future__ import annotations

import json
import re
import unicodedata
from difflib import SequenceMatcher
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from aprendix.application.learning_catalog import EXTRA_GLOSSARY


def _id(kind: str, slug: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"aprendix:curriculum:{kind}:{slug}"))


TRACKS = (
    ("python-foundations", "Python: bases", "Prática progressiva de valores, decisões e funções.", 0),
    ("python-oop", "Python: POO", "Objetos pequenos, estado explícito e comportamento testável.", 1),
    ("python-algorithms", "Python: algoritmos", "Resolução determinística, casos-limite e análise de passos.", 2),
    ("python-data-structures", "Python: estruturas de dados", "Escolha consciente de listas, mapas e conjuntos.", 3),
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
        with self._database.transaction() as connection:
            for slug, title, description, position in TRACKS:
                connection.execute(
                    "INSERT OR IGNORE INTO learning_tracks VALUES(?,?,?,?,?,?)",
                    (_id("track", slug), slug, title, description, "python", position),
                )
            last_hybrid: dict[str, str] = {}
            for chapter_position, data in enumerate(CHAPTERS):
                (slug, track_slug, node_slug, title, objective, exercise_slug,
                 theory, example, question, options, answer, explanation,
                 hybrid_prompt, hybrid_answer, hybrid_explanation) = data
                track_id, chapter_id = _id("track", track_slug), _id("chapter", slug)
                node = connection.execute("SELECT id FROM graph_nodes WHERE slug=?", (node_slug,)).fetchone()
                exercise = connection.execute("SELECT id FROM exercises WHERE slug=? ORDER BY version DESC", (exercise_slug,)).fetchone()
                if node is None or exercise is None:
                    continue
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
                    if slug in last_hybrid:
                        connection.execute(
                            "INSERT OR IGNORE INTO learning_unit_dependencies VALUES(?,?)",
                            (unit_id, last_hybrid[slug]),
                        )
            # Stable prerequisite spine for an ARPG-like skill tree.  Dynamic
            # co-occurrence later strengthens these edges without replacing it.
            ordered_nodes = []
            for data in CHAPTERS:
                node = connection.execute("SELECT id FROM graph_nodes WHERE slug=?", (data[2],)).fetchone()
                if node and node["id"] not in ordered_nodes:
                    ordered_nodes.append(node["id"])
            now = datetime.now(UTC).isoformat()
            for source, target in zip(ordered_nodes, ordered_nodes[1:]):
                connection.execute(
                    """INSERT OR IGNORE INTO graph_edges(source_node_id,target_node_id,
                       weight,co_occurrence_count,updated_at) VALUES(?,?,0.35,0,?)""",
                    (source, target, now),
                )
            for term, technology, definition, signature, example, related in (*GLOSSARY, *EXTRA_GLOSSARY):
                identity = _id("glossary", _normalize(term))
                connection.execute(
                    "INSERT OR IGNORE INTO glossary_entries VALUES(?,?,?,?,?,?,?,?)",
                    (identity, term, _normalize(term), technology,
                     self._encrypt("glossary_entries.definition", identity, definition),
                     self._encrypt("glossary_entries.signature", identity, signature),
                     self._encrypt("glossary_entries.example", identity, example),
                     json.dumps(related, ensure_ascii=False, separators=(",", ":"))),
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

    def units(self, track_slug: str, user_id: UUID) -> tuple[dict[str, object], ...]:
        with self._database.read_connection() as connection:
            rows = connection.execute("""
                SELECT u.*, c.title chapter_title, c.graph_node_id,
                       (SELECT id FROM assessment_items a WHERE a.unit_id=u.id LIMIT 1) assessment_id,
                       EXISTS(SELECT 1 FROM learning_unit_progress p
                              WHERE p.user_id=? AND p.unit_id=u.id) completed
                FROM learning_units u JOIN learning_chapters c ON c.id=u.chapter_id
                JOIN learning_tracks t ON t.id=c.track_id WHERE t.slug=?
                ORDER BY c.position,u.position
            """, (str(user_id), track_slug)).fetchall()
            completed_ids = {
                row[0] for row in connection.execute(
                    "SELECT unit_id FROM learning_unit_progress WHERE user_id=?", (str(user_id),)
                ).fetchall()
            }
            dependencies = {}
            for row in connection.execute("SELECT unit_id,prerequisite_unit_id FROM learning_unit_dependencies"):
                dependencies.setdefault(row["unit_id"], set()).add(row["prerequisite_unit_id"])
        result = []
        for row in rows:
            item = dict(row); identity = item["id"]
            item["body"] = self._decrypt("learning_units.body", identity, item.pop("body_encrypted"))
            item["example"] = self._decrypt("learning_units.example", identity, item.pop("example_encrypted"))
            item["unlocked"] = dependencies.get(identity, set()).issubset(completed_ids)
            result.append(item)
        return tuple(result)

    def complete_unit(self, user_id: UUID, unit_id: str) -> None:
        now = datetime.now(UTC).isoformat()
        with self._database.transaction() as connection:
            row = connection.execute("SELECT kind FROM learning_units WHERE id=?", (unit_id,)).fetchone()
            if row is None: raise KeyError(unit_id)
            if row["kind"] == "practice":
                raise ValueError("practice units are completed only by a passed IDE attempt")
            prerequisites = {
                item[0] for item in connection.execute(
                    "SELECT prerequisite_unit_id FROM learning_unit_dependencies WHERE unit_id=?", (unit_id,)
                ).fetchall()
            }
            completed = {
                item[0] for item in connection.execute(
                    "SELECT unit_id FROM learning_unit_progress WHERE user_id=?", (str(user_id),)
                ).fetchall()
            }
            if not prerequisites.issubset(completed):
                raise ValueError("unit prerequisites are not complete")
            connection.execute(
                "INSERT OR IGNORE INTO learning_unit_progress VALUES(?,?,?)",
                (str(user_id), unit_id, now),
            )

    def glossary(self, term: str, *, limit: int = 8) -> tuple[dict[str, object], ...]:
        normalized = _normalize(term)
        with self._database.read_connection() as connection:
            rows = connection.execute("SELECT * FROM glossary_entries ORDER BY normalized_term").fetchall()
        query_tokens = set(normalized.split())
        def rank(row):
            candidate = row["normalized_term"]
            related = " ".join(json.loads(row["related_terms_json"])).casefold()
            exact = candidate == normalized
            prefix = candidate.startswith(normalized) or normalized.startswith(candidate)
            substring = normalized in candidate or candidate in normalized
            overlap = len(query_tokens & set((candidate + " " + related).split()))
            similarity = SequenceMatcher(None, normalized, candidate).ratio() if normalized else 0.0
            return (int(exact), int(prefix), int(substring), overlap, similarity, -len(candidate))
        rows = sorted(rows, key=rank, reverse=True)
        if normalized:
            rows = [row for row in rows if rank(row)[:4] != (0, 0, 0, 0) or rank(row)[4] >= .36]
        rows = rows[:max(1, min(limit, 30))]
        result = []
        for row in rows:
            item, identity = dict(row), row["id"]
            for name in ("definition", "signature", "example"):
                item[name] = self._decrypt(f"glossary_entries.{name}", identity, item.pop(f"{name}_encrypted"))
            item["related_terms"] = tuple(json.loads(item.pop("related_terms_json")))
            reference_map = {
                "python": (("Documentação Python", "https://docs.python.org/3/"),),
                "sql": (("PostgreSQL Documentation", "https://www.postgresql.org/docs/current/"),),
                "javascript": (("MDN Web Docs", "https://developer.mozilla.org/docs/Web/JavaScript"),),
                "django": (("Django Documentation", "https://docs.djangoproject.com/"),),
                "numpy": (("NumPy Documentation", "https://numpy.org/doc/stable/"),),
                "pandas": (("pandas Documentation", "https://pandas.pydata.org/docs/"),),
                "pytorch": (("PyTorch Documentation", "https://pytorch.org/docs/stable/"),),
            }
            item["references"] = reference_map.get(item["technology"], (
                ("Python Glossary", "https://docs.python.org/3/glossary.html"),
                ("Aprendix · conhecimento local", "aprendix://dictionary"),
            ))
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
            prerequisites = {
                item[0] for item in connection.execute(
                    "SELECT prerequisite_unit_id FROM learning_unit_dependencies WHERE unit_id=?",
                    (row["unit_id"],),
                ).fetchall()
            }
            completed = {
                item[0] for item in connection.execute(
                    "SELECT unit_id FROM learning_unit_progress WHERE user_id=?",
                    (str(user_id),),
                ).fetchall()
            }
            if not prerequisites.issubset(completed):
                raise ValueError("assessment prerequisites are not complete")
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
            if passed:
                connection.execute(
                    "INSERT OR IGNORE INTO learning_unit_progress VALUES(?,?,?)",
                    (str(user_id), row["unit_id"], now),
                )
        return {"attempt_id": attempt_id, "passed": passed, "score": 1.0 if passed else 0.0,
                "explanation": explanation}

    def graph_node_for_assessment(self, item_id: str) -> str:
        with self._database.read_connection() as connection:
            row = connection.execute("""
                SELECT c.graph_node_id FROM assessment_items a
                JOIN learning_units u ON u.id=a.unit_id
                JOIN learning_chapters c ON c.id=u.chapter_id WHERE a.id=?
            """, (item_id,)).fetchone()
        if row is None: raise KeyError(item_id)
        return str(row["graph_node_id"])
