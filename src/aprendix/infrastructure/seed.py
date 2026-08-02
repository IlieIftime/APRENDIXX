"""Deterministic local catalogue used by the Sprint 2 CLI MVP."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from aprendix.application.contracts import ExerciseDTO
from aprendix.application.contracts.models import GraphNodeDTO
from aprendix.infrastructure.db.database import Database

_SEED_TIMESTAMP = datetime(2026, 1, 1, tzinfo=UTC)


def _seed_id(kind: str, slug: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"aprendix:seed:{kind}:{slug}")


DEFAULT_NODES: tuple[GraphNodeDTO, ...] = (
    GraphNodeDTO(
        id=_seed_id("node", "output"),
        slug="output",
        title="Output",
        description="Producing visible output with print.",
        difficulty=-1.5,
        created_at=_SEED_TIMESTAMP,
        updated_at=_SEED_TIMESTAMP,
    ),
    GraphNodeDTO(
        id=_seed_id("node", "variables-arithmetic"),
        slug="variables-arithmetic",
        title="Variables and arithmetic",
        description="Storing numeric values and combining them.",
        difficulty=-0.5,
        created_at=_SEED_TIMESTAMP,
        updated_at=_SEED_TIMESTAMP,
    ),
    GraphNodeDTO(
        id=_seed_id("node", "conditionals"),
        slug="conditionals",
        title="Conditionals",
        description="Choosing behavior from a boolean condition.",
        difficulty=0.25,
        created_at=_SEED_TIMESTAMP,
        updated_at=_SEED_TIMESTAMP,
    ),
)

DEFAULT_EXERCISES: tuple[ExerciseDTO, ...] = (
    ExerciseDTO(
        id=_seed_id("exercise", "hello-python"),
        graph_node_id=DEFAULT_NODES[0].id,
        slug="hello-python",
        title="Olá, Python!",
        prompt='Escreve um programa que mostre exatamente: Olá, Python!',
        starter_code='print("Olá, Python!")',
        tests=("stdout equals 'Olá, Python!'",),
        difficulty=-1.5,
        created_at=_SEED_TIMESTAMP,
        updated_at=_SEED_TIMESTAMP,
    ),
    ExerciseDTO(
        id=_seed_id("exercise", "sum-two-values"),
        graph_node_id=DEFAULT_NODES[1].id,
        slug="sum-two-values",
        title="Somar dois valores",
        prompt="Define a=7 e b=5, calcula a soma e mostra o resultado.",
        starter_code="a = 7\nb = 5\n",
        tests=("stdout equals '12'",),
        difficulty=-0.5,
        created_at=_SEED_TIMESTAMP,
        updated_at=_SEED_TIMESTAMP,
    ),
    ExerciseDTO(
        id=_seed_id("exercise", "even-or-odd"),
        graph_node_id=DEFAULT_NODES[2].id,
        slug="even-or-odd",
        title="Par ou ímpar",
        prompt="Para numero=9, mostra 'par' se for par ou 'ímpar' caso contrário.",
        starter_code="numero = 9\n",
        tests=("stdout equals 'ímpar'",),
        difficulty=0.25,
        created_at=_SEED_TIMESTAMP,
        updated_at=_SEED_TIMESTAMP,
    ),
)


ADVANCED_NODES: tuple[GraphNodeDTO, ...] = tuple(
    GraphNodeDTO(
        id=_seed_id("node", slug), slug=slug, title=title,
        description=description, difficulty=difficulty,
        created_at=_SEED_TIMESTAMP, updated_at=_SEED_TIMESTAMP,
    )
    for slug, title, description, difficulty in (
        ("object-oriented-python", "Python orientado a objetos",
         "Classes pequenas com estado e comportamento explícitos.", 0.75),
        ("python-algorithms", "Algoritmos em Python",
         "Funções determinísticas, iteração e casos-limite.", 1.0),
        ("python-data-structures", "Estruturas de dados em Python",
         "Listas, filas, pilhas, conjuntos e dicionários.", 1.25),
    )
)


def _advanced_exercise(
    node_index: int, slug: str, title: str, prompt: str,
    starter_code: str, test_code: str, difficulty: float,
) -> ExerciseDTO:
    return ExerciseDTO(
        id=_seed_id("exercise", slug),
        graph_node_id=ADVANCED_NODES[node_index].id,
        slug=slug, title=title, prompt=prompt, starter_code=starter_code,
        tests=(test_code,), difficulty=difficulty,
        created_at=_SEED_TIMESTAMP, updated_at=_SEED_TIMESTAMP,
    )


# Original, deterministic exercises.  The milestone counts are deliberately
# satisfiable without downloading content or repeating one exercise.
ADVANCED_EXERCISES: tuple[ExerciseDTO, ...] = (
    _advanced_exercise(0, "oop-account", "Conta com depósitos",
        "Cria uma class Conta (POO) com saldo e método depositar(valor).",
        "class Conta:\n    pass\n",
        "assert Conta(10).saldo == 10\nc = Conta(10)\nc.depositar(5)\nassert c.saldo == 15", 0.7),
    _advanced_exercise(0, "oop-product", "Produto em promoção",
        "Cria uma class Produto com preco e método aplicar_desconto(percentagem).",
        "class Produto:\n    pass\n",
        "p = Produto(100)\np.aplicar_desconto(20)\nassert p.preco == 80", 0.7),
    _advanced_exercise(0, "oop-rectangle", "Área do retângulo",
        "Cria uma class Retangulo com largura, altura e método area().",
        "class Retangulo:\n    pass\n",
        "assert Retangulo(4, 3).area() == 12", 0.75),
    _advanced_exercise(0, "oop-player", "Pontuação do jogador",
        "Cria uma class Jogador com pontos e método adicionar_pontos(valor).",
        "class Jogador:\n    pass\n",
        "j = Jogador()\nj.adicionar_pontos(7)\nassert j.pontos == 7", 0.75),
    _advanced_exercise(0, "oop-book", "Empréstimo de livro",
        "Cria uma class Livro com titulo, disponivel e método emprestar().",
        "class Livro:\n    pass\n",
        "l = Livro('Local')\nassert l.disponivel is True\nl.emprestar()\nassert l.disponivel is False", 0.8),
    _advanced_exercise(0, "oop-thermometer", "Conversão de temperatura",
        "Cria uma class Termometro com celsius e método fahrenheit().",
        "class Termometro:\n    pass\n",
        "assert Termometro(0).fahrenheit() == 32\nassert Termometro(100).fahrenheit() == 212", 0.8),
    _advanced_exercise(0, "oop-cart", "Carrinho local",
        "Cria uma class Carrinho com itens, adicionar(preco) e total().",
        "class Carrinho:\n    pass\n",
        "c = Carrinho()\nc.adicionar(3)\nc.adicionar(4)\nassert c.total() == 7", 0.85),
    _advanced_exercise(0, "oop-task", "Estado de uma tarefa",
        "Cria uma class Tarefa com descricao, concluida e método concluir().",
        "class Tarefa:\n    pass\n",
        "t = Tarefa('praticar')\nassert not t.concluida\nt.concluir()\nassert t.concluida", 0.85),
    _advanced_exercise(0, "oop-sensor", "Média do sensor",
        "Cria uma class Sensor com leituras, registar(valor) e media().",
        "class Sensor:\n    pass\n",
        "s = Sensor()\ns.registar(2)\ns.registar(4)\nassert s.media() == 3", 0.9),
    _advanced_exercise(0, "oop-vault", "Cofre com levantamento",
        "Cria uma class Cofre com saldo e levantar(valor), sem permitir saldo negativo.",
        "class Cofre:\n    pass\n",
        "c = Cofre(10)\nassert c.levantar(4) is True\nassert c.saldo == 6\nassert c.levantar(9) is False\nassert c.saldo == 6", 0.95),
    _advanced_exercise(1, "algo-even-sum", "Somar pares",
        "Implementa o algoritmo somar_pares(valores), devolvendo apenas a soma dos pares.",
        "def somar_pares(valores):\n    pass\n",
        "assert somar_pares([1, 2, 3, 4]) == 6\nassert somar_pares([]) == 0", 0.8),
    _advanced_exercise(1, "algo-linear-search", "Pesquisa linear",
        "Implementa o algoritmo indice_linear(valores, alvo); devolve -1 se não existir.",
        "def indice_linear(valores, alvo):\n    pass\n",
        "assert indice_linear([5, 7, 9], 7) == 1\nassert indice_linear([5], 2) == -1", 0.9),
    _advanced_exercise(1, "algo-factorial", "Fatorial iterativo",
        "Implementa o algoritmo fatorial(n), incluindo o caso zero.",
        "def fatorial(n):\n    pass\n",
        "assert fatorial(0) == 1\nassert fatorial(5) == 120", 0.9),
    _advanced_exercise(1, "algo-sort", "Ordenação crescente",
        "Implementa o algoritmo ordenar(valores) sem alterar a lista recebida.",
        "def ordenar(valores):\n    pass\n",
        "a = [3, 1, 2]\nr = ordenar(a)\nassert r == [1, 2, 3]\nassert a == [3, 1, 2]", 1.0),
    _advanced_exercise(1, "algo-count", "Contar ocorrências",
        "Implementa o algoritmo contar_ocorrencias(valores, alvo).",
        "def contar_ocorrencias(valores, alvo):\n    pass\n",
        "assert contar_ocorrencias([1, 2, 1, 1], 1) == 3\nassert contar_ocorrencias([], 4) == 0", 1.0),
    _advanced_exercise(2, "ds-stack", "Pilha de operações",
        "Usa uma estrutura de dados list em pilha_operacoes(valores), devolvendo a ordem de remoção.",
        "def pilha_operacoes(valores):\n    pass\n",
        "assert pilha_operacoes([1, 2, 3]) == [3, 2, 1]\nassert pilha_operacoes([]) == []", 1.0),
    _advanced_exercise(2, "ds-queue", "Fila de atendimento",
        "Usa uma estrutura de dados queue/list em processar_fila(nomes), preservando a ordem.",
        "def processar_fila(nomes):\n    pass\n",
        "assert processar_fila(['Ana', 'Ivo']) == ['Ana', 'Ivo']", 1.0),
    _advanced_exercise(2, "ds-frequency", "Mapa de frequências",
        "Usa uma estrutura de dados dict em frequencias(valores).",
        "def frequencias(valores):\n    pass\n",
        "assert frequencias(['a', 'b', 'a']) == {'a': 2, 'b': 1}\nassert frequencias([]) == {}", 1.1),
    _advanced_exercise(2, "ds-unique", "Únicos por ordem",
        "Usa estruturas de dados set/list em unicos_ordem(valores), mantendo a primeira ocorrência.",
        "def unicos_ordem(valores):\n    pass\n",
        "assert unicos_ordem([2, 1, 2, 3, 1]) == [2, 1, 3]", 1.1),
    _advanced_exercise(2, "ds-invert-map", "Inverter um mapa",
        "Usa uma estrutura de dados dict em inverter_mapa(mapa), assumindo valores únicos.",
        "def inverter_mapa(mapa):\n    pass\n",
        "assert inverter_mapa({'x': 1, 'y': 2}) == {1: 'x', 2: 'y'}", 1.2),
)


def seed_default_catalog(database: Database) -> None:
    """Insert the deterministic three-exercise catalogue without duplication."""

    with database.transaction() as connection:
        for node in DEFAULT_NODES:
            connection.execute(
                """
                INSERT OR IGNORE INTO graph_nodes(
                    id, slug, title, description, difficulty, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(node.id),
                    node.slug,
                    node.title,
                    node.description,
                    node.difficulty,
                    node.created_at.isoformat(),
                    node.updated_at.isoformat(),
                ),
            )
        for exercise in DEFAULT_EXERCISES:
            connection.execute(
                """INSERT OR IGNORE INTO exercises(
                    id, graph_node_id, slug, title, prompt, starter_code,
                    tests_json, difficulty, version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (str(exercise.id), str(exercise.graph_node_id), exercise.slug,
                 exercise.title, exercise.prompt, exercise.starter_code,
                 json.dumps(exercise.tests, ensure_ascii=False, separators=(",", ":")),
                 exercise.difficulty, exercise.version,
                 exercise.created_at.isoformat(), exercise.updated_at.isoformat()),
            )


def seed_advanced_catalog(database: Database) -> None:
    """Add the original milestone catalogue without changing the Sprint-2 seed."""

    with database.transaction() as connection:
        for node in ADVANCED_NODES:
            connection.execute(
                """INSERT OR IGNORE INTO graph_nodes(
                    id, slug, title, description, difficulty, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (str(node.id), node.slug, node.title, node.description,
                 node.difficulty, node.created_at.isoformat(), node.updated_at.isoformat()),
            )
        for exercise in ADVANCED_EXERCISES:
            connection.execute(
                """INSERT OR IGNORE INTO exercises(
                    id, graph_node_id, slug, title, prompt, starter_code,
                    tests_json, difficulty, version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (str(exercise.id), str(exercise.graph_node_id), exercise.slug,
                 exercise.title, exercise.prompt, exercise.starter_code,
                 json.dumps(exercise.tests, ensure_ascii=False, separators=(",", ":")),
                 exercise.difficulty, exercise.version,
                 exercise.created_at.isoformat(), exercise.updated_at.isoformat()),
            )
