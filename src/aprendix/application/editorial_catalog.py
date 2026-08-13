"""Original deterministic practice and project specifications for Iteration 21."""

from __future__ import annotations

from dataclasses import dataclass

from aprendix.application.career_catalog import CAREER_ROLES


CATALOG_VERSION = "aaa-21.0"
CATALOG_GENERATOR = "aprendix-editorial-v1"


@dataclass(frozen=True, slots=True)
class EditorialExercise:
    slug: str
    title: str
    prompt: str
    starter_code: str
    tests: tuple[str, ...]
    solution: str
    explanation: str
    expected_trace: tuple[str, ...]
    difficulty: float
    role_slug: str
    track_slug: str
    graph_node_slug: str
    source_id: str
    reveal_mode: str
    walkthrough_after: int
    solution_after: int
    supporting_source_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EditorialProject:
    id: str
    role_slug: str
    track_slug: str
    title: str
    brief: str
    requirements: tuple[str, ...]
    milestones: tuple[str, ...]
    rubric: tuple[str, ...]
    level: str
    capstone: bool


_ROLE_CONTEXT = {
    "python-software-engineer": (
        "um serviço Python local", "python-foundations", "function-contracts", "src-python-docs",
    ),
    "data-analyst": (
        "um estudo de dados reproduzível", "data-ai", "data-pipelines", "src-pandas",
    ),
    "machine-learning-engineer": (
        "um pipeline de Machine Learning auditável", "data-ai", "classical-ml", "src-sklearn",
    ),
    "cybersecurity-automation": (
        "uma ferramenta defensiva sem rede", "testing-debugging", "contracts-and-errors", "src-python-docs",
    ),
    "data-engineer": (
        "um pipeline incremental de dados", "sql-databases", "relational-keys", "src-postgresql",
    ),
}


def _prompt(
    *, context: str, objective: str, signature: str, inputs: str,
    example: str, limits: str, variant: int,
) -> str:
    return (
        "Contextualização\n"
        f"Estás a implementar uma operação pequena e verificável para {context}. "
        f"Esta variante {variant + 1} deve produzir sempre o mesmo resultado para a mesma entrada.\n\n"
        "Objetivo\n"
        f"{objective}\n\n"
        "Especificação técnica\n"
        f"Implementa `{signature}` exatamente com os nomes indicados.\n\n"
        "Entradas e parâmetros\n"
        f"{inputs}\n\n"
        "Exemplo de comportamento\n"
        f"{example}\n\n"
        "Requisitos e casos-limite\n"
        f"{limits} Não alteres os argumentos recebidos e não uses rede, processos ou ficheiros.\n\n"
        "Critérios de avaliação\n"
        "A solução executa sem erros, respeita a assinatura, passa casos normais e de fronteira "
        "e devolve um resultado observável com o tipo pedido."
    )


def _family(
    family: int, name: str, variant: int, context: str,
) -> tuple[str, str, str, str, tuple[str, ...], str, str, str, tuple[str, ...]]:
    marker = variant + 2
    if family == 0:
        objective = "Somar apenas os valores numéricos maiores ou iguais ao limite indicado."
        signature = f"{name}(valores, minimo=0)"
        inputs = "`valores` é uma sequência numérica; `minimo` define a fronteira inclusiva."
        example = f"`{name}([{marker - 1}, {marker}, {marker + 2}], {marker})` devolve `{2 * marker + 2}`."
        starter = f"def {name}(valores, minimo=0):\n    pass\n"
        solution = f"def {name}(valores, minimo=0):\n    return sum(valor for valor in valores if valor >= minimo)\n"
        tests = (
            f"assert {name}([{marker - 1}, {marker}, {marker + 2}, {-marker}], {marker}) == {2 * marker + 2}",
            f"assert {name}([], {marker}) == 0",
        )
        limits = "Considera sequência vazia, valores negativos e igualdade exata com o limite."
        trace = ("inicializar a soma em zero", "comparar cada valor com minimo", "acumular apenas valores aceites", f"devolver {2 * marker + 2} no exemplo")
    elif family == 1:
        divisor = variant % 4 + 2
        objective = "Contar quantos inteiros são múltiplos de um divisor não nulo."
        signature = f"{name}(valores, divisor)"
        inputs = "`valores` é uma sequência de inteiros; `divisor` é um inteiro diferente de zero."
        example = f"`{name}([{divisor}, {2 * divisor}, {divisor + 1}, 0], {divisor})` devolve `3`."
        starter = f"def {name}(valores, divisor):\n    pass\n"
        solution = f"def {name}(valores, divisor):\n    if divisor == 0:\n        raise ValueError('divisor não pode ser zero')\n    return sum(1 for valor in valores if valor % divisor == 0)\n"
        tests = (
            f"assert {name}([{divisor}, {2 * divisor}, {divisor + 1}, 0], {divisor}) == 3",
            f"try:\n    {name}([1], 0)\n    assert False\nexcept ValueError:\n    pass",
        )
        limits = "Rejeita divisor zero; uma sequência vazia produz contagem zero."
        trace = ("validar divisor", "calcular o resto de cada inteiro", "incrementar nas divisões exatas", "devolver 3 no exemplo")
    elif family == 2:
        tail = marker + 20
        objective = "Remover repetições mantendo a ordem da primeira ocorrência."
        signature = f"{name}(valores)"
        inputs = "`valores` é uma sequência de valores hashable cuja ordem deve ser preservada."
        example = f"`{name}([{marker}, 1, {marker}, {tail}, 1])` devolve `[{marker}, 1, {tail}]`."
        starter = f"def {name}(valores):\n    pass\n"
        solution = (
            f"def {name}(valores):\n    vistos = set()\n    resultado = []\n"
            "    for valor in valores:\n        if valor not in vistos:\n            vistos.add(valor)\n"
            "            resultado.append(valor)\n    return resultado\n"
        )
        tests = (f"assert {name}([{marker}, 1, {marker}, {tail}, 1]) == [{marker}, 1, {tail}]", f"assert {name}([]) == []")
        limits = "Não ordenes o resultado e devolve uma lista nova, inclusive para a entrada vazia."
        trace = ("criar conjunto de vistos", "percorrer pela ordem original", "guardar apenas a primeira ocorrência", f"devolver [{marker}, 1, {tail}]")
    elif family == 3:
        token = f"item{variant}"
        objective = "Construir um mapa de frequências sem perder elementos da entrada."
        signature = f"{name}(valores)"
        inputs = "`valores` é uma sequência de chaves hashable; o resultado associa cada chave à sua contagem."
        example = f"`{name}(['{token}', 'x', '{token}'])` devolve `{{'{token}': 2, 'x': 1}}`."
        starter = f"def {name}(valores):\n    pass\n"
        solution = f"def {name}(valores):\n    resultado = {{}}\n    for valor in valores:\n        resultado[valor] = resultado.get(valor, 0) + 1\n    return resultado\n"
        tests = (f"assert {name}(['{token}', 'x', '{token}']) == {{'{token}': 2, 'x': 1}}", f"assert {name}([]) == {{}}")
        limits = "A coleção vazia produz um mapa vazio e cada ocorrência deve ser contabilizada uma vez."
        trace = ("criar mapa vazio", "obter a contagem anterior", "somar uma ocorrência", f"confirmar duas ocorrências de {token}")
    elif family == 4:
        objective = "Produzir o total acumulado depois de cada valor, sem alterar a sequência."
        signature = f"{name}(valores)"
        inputs = "`valores` é uma sequência numérica; o resultado contém um total por posição."
        example = f"`{name}([{marker}, -1, 3])` devolve `[{marker}, {marker - 1}, {marker + 2}]`."
        starter = f"def {name}(valores):\n    pass\n"
        solution = f"def {name}(valores):\n    total = 0\n    resultado = []\n    for valor in valores:\n        total += valor\n        resultado.append(total)\n    return resultado\n"
        tests = (f"assert {name}([{marker}, -1, 3]) == [{marker}, {marker - 1}, {marker + 2}]", f"assert {name}([]) == []")
        limits = "Preserva um resultado por entrada; para vazio devolve lista vazia."
        trace = ("inicializar total", f"somar {marker}", "somar -1 e depois 3", f"devolver o total final {marker + 2}")
    elif family == 5:
        window = variant % 3 + 2
        values = list(range(2, 2 * (window + 2) + 1, 2))
        expected = [sum(values[i:i + window]) / window for i in range(len(values) - window + 1)]
        objective = "Calcular médias móveis completas para uma janela positiva."
        signature = f"{name}(valores, tamanho)"
        inputs = "`valores` é uma sequência numérica; `tamanho` é a quantidade de elementos por janela."
        example = f"`{name}({values}, {window})` devolve `{expected}`."
        starter = f"def {name}(valores, tamanho):\n    pass\n"
        solution = f"def {name}(valores, tamanho):\n    if tamanho <= 0:\n        raise ValueError('tamanho deve ser positivo')\n    return [sum(valores[i:i + tamanho]) / tamanho for i in range(len(valores) - tamanho + 1)]\n"
        tests = (f"assert {name}({values}, {window}) == {expected}", f"assert {name}([1], {window}) == []", f"try:\n    {name}([1], 0)\n    assert False\nexcept ValueError:\n    pass")
        limits = "Rejeita tamanho não positivo e ignora janelas incompletas no fim."
        trace = ("validar o tamanho", "delimitar cada janela completa", "somar e dividir pelo tamanho", f"produzir {len(expected)} médias")
    elif family == 6:
        field = f"grupo{variant}"
        objective = "Agrupar registos por uma chave obrigatória, preservando a ordem em cada grupo."
        signature = f"{name}(registos, campo)"
        inputs = "`registos` é uma sequência de dicionários; `campo` identifica a chave de agrupamento."
        example = f"Dois registos com `{field}='a'` ficam juntos no grupo `a`."
        starter = f"def {name}(registos, campo):\n    pass\n"
        solution = f"def {name}(registos, campo):\n    grupos = {{}}\n    for registo in registos:\n        if campo not in registo:\n            raise KeyError(campo)\n        grupos.setdefault(registo[campo], []).append(dict(registo))\n    return grupos\n"
        rows = f"[{{'{field}':'a','v':1}},{{'{field}':'b','v':2}},{{'{field}':'a','v':3}}]"
        expected = f"{{'a':[{{'{field}':'a','v':1}},{{'{field}':'a','v':3}}],'b':[{{'{field}':'b','v':2}}]}}"
        tests = (f"assert {name}({rows}, '{field}') == {expected}", f"try:\n    {name}([{{'x': 1}}], '{field}')\n    assert False\nexcept KeyError:\n    pass")
        limits = "Rejeita registos sem a chave e devolve cópias rasas para evitar efeitos laterais."
        trace = ("criar grupos vazios", "validar a chave em cada registo", "anexar uma cópia ao grupo", "preservar a ordem 1 antes de 3")
    elif family == 7:
        target = marker * 3
        objective = "Devolver o índice da primeira ocorrência ou -1 quando o alvo não existe."
        signature = f"{name}(valores, alvo)"
        inputs = "`valores` é uma sequência; `alvo` é comparado por igualdade."
        example = f"`{name}([{marker}, {target}, {target}], {target})` devolve `1`."
        starter = f"def {name}(valores, alvo):\n    pass\n"
        solution = f"def {name}(valores, alvo):\n    for indice, valor in enumerate(valores):\n        if valor == alvo:\n            return indice\n    return -1\n"
        tests = (f"assert {name}([{marker}, {target}, {target}], {target}) == 1", f"assert {name}([{marker}], {target}) == -1", f"assert {name}([], {target}) == -1")
        limits = "Termina na primeira igualdade e usa -1 tanto para ausente como para sequência vazia."
        trace = ("enumerar valores", f"comparar {marker} com {target}", "encontrar o alvo na posição 1", "devolver 1 sem percorrer o resto")
    elif family == 8:
        upper = marker + 5
        objective = "Limitar cada valor ao intervalo fechado definido pelos extremos."
        signature = f"{name}(valores, minimo, maximo)"
        inputs = "`valores` é uma sequência numérica; `minimo` não pode exceder `maximo`."
        example = f"`{name}([-2, {marker}, {upper + 4}], 0, {upper})` devolve `[0, {marker}, {upper}]`."
        starter = f"def {name}(valores, minimo, maximo):\n    pass\n"
        solution = f"def {name}(valores, minimo, maximo):\n    if minimo > maximo:\n        raise ValueError('intervalo inválido')\n    return [min(max(valor, minimo), maximo) for valor in valores]\n"
        tests = (f"assert {name}([-2, {marker}, {upper + 4}], 0, {upper}) == [0, {marker}, {upper}]", f"try:\n    {name}([1], 2, 1)\n    assert False\nexcept ValueError:\n    pass")
        limits = "Valida a ordem dos extremos e aceita valores exatamente nas fronteiras."
        trace = ("validar extremos", "substituir abaixo pelo mínimo", "preservar o valor interior", "substituir acima pelo máximo")
    elif family == 9:
        weight = round(0.2 + variant * 0.03, 2)
        expected = round(2 * weight + 4 * (1 - weight), 8)
        objective = "Calcular um score ponderado validando a correspondência entre valores e pesos."
        signature = f"{name}(valores, pesos)"
        inputs = "`valores` e `pesos` são sequências numéricas com o mesmo comprimento."
        example = f"`{name}([2, 4], [{weight}, {round(1-weight, 2)}])` devolve `{expected}`."
        starter = f"def {name}(valores, pesos):\n    pass\n"
        solution = f"def {name}(valores, pesos):\n    if len(valores) != len(pesos):\n        raise ValueError('dimensões incompatíveis')\n    return sum(valor * peso for valor, peso in zip(valores, pesos))\n"
        tests = (f"assert abs({name}([2, 4], [{weight}, {round(1-weight, 2)}]) - {expected}) < 1e-9", f"assert {name}([], []) == 0", f"try:\n    {name}([1], [])\n    assert False\nexcept ValueError:\n    pass")
        limits = "Rejeita comprimentos diferentes; duas sequências vazias produzem score zero."
        trace = ("validar dimensões", "multiplicar valores por pesos", "somar os contributos", f"devolver {expected}")
    elif family == 10:
        objective = "Inverter a ordem das palavras depois de normalizar espaços exteriores e repetidos."
        signature = f"{name}(texto)"
        inputs = "`texto` é uma string; palavras são segmentos separados por whitespace."
        example = f"`{name}('  etapa {marker} final ')` devolve `'final {marker} etapa'`."
        starter = f"def {name}(texto):\n    pass\n"
        solution = f"def {name}(texto):\n    return ' '.join(reversed(texto.split()))\n"
        tests = (f"assert {name}('  etapa {marker} final ') == 'final {marker} etapa'", f"assert {name}('   ') == ''")
        limits = "Remove whitespace redundante, preserva os caracteres de cada palavra e trata texto vazio."
        trace = ("separar palavras", "inverter a sequência", "juntar com um espaço", f"obter final {marker} etapa")
    elif family == 11:
        objective = "Validar se parênteses estão equilibrados sem aceitar um fecho antecipado."
        signature = f"{name}(texto)"
        inputs = "`texto` é uma string onde apenas os caracteres `(` e `)` afetam o balanço."
        example = f"`{name}('({marker})()')` devolve `True`; `{name}(')(')` devolve `False`."
        starter = f"def {name}(texto):\n    pass\n"
        solution = f"def {name}(texto):\n    nivel = 0\n    for caracter in texto:\n        if caracter == '(':\n            nivel += 1\n        elif caracter == ')':\n            nivel -= 1\n            if nivel < 0:\n                return False\n    return nivel == 0\n"
        tests = (f"assert {name}('({marker})()') is True", f"assert {name}(')(') is False", f"assert {name}('(()') is False")
        limits = "Ignora outros caracteres, rejeita fechos antes da abertura e exige balanço final zero."
        trace = ("iniciar nível zero", "incrementar em cada abertura", "decrementar em cada fecho", "confirmar nível final zero")
    elif family == 12:
        objective = "Achatar exatamente um nível de sequências internas, preservando a ordem."
        signature = f"{name}(grupos)"
        inputs = "`grupos` é uma sequência de sequências; o resultado é uma lista nova."
        example = f"`{name}([[{marker}], [], [1, 2]])` devolve `[{marker}, 1, 2]`."
        starter = f"def {name}(grupos):\n    pass\n"
        solution = f"def {name}(grupos):\n    return [valor for grupo in grupos for valor in grupo]\n"
        tests = (f"assert {name}([[{marker}], [], [1, 2]]) == [{marker}, 1, 2]", f"assert {name}([]) == []")
        limits = "Não achata níveis adicionais e não altera qualquer grupo recebido."
        trace = ("percorrer grupos", "percorrer valores do grupo atual", "anexar pela ordem", f"produzir [{marker}, 1, 2]")
    elif family == 13:
        objective = "Separar valores por um predicado mantendo a ordem nas duas partições."
        signature = f"{name}(valores, predicado)"
        inputs = "`valores` é uma sequência; `predicado(valor)` devolve um valor truthy ou falsy."
        example = f"Com o predicado `x >= {marker}`, separa `[{marker - 1}, {marker}, {marker + 1}]` em duas listas."
        starter = f"def {name}(valores, predicado):\n    pass\n"
        solution = f"def {name}(valores, predicado):\n    aceites = []\n    rejeitados = []\n    for valor in valores:\n        (aceites if predicado(valor) else rejeitados).append(valor)\n    return aceites, rejeitados\n"
        tests = (f"assert {name}([{marker - 1}, {marker}, {marker + 1}], lambda x: x >= {marker}) == ([{marker}, {marker + 1}], [{marker - 1}])", f"assert {name}([], bool) == ([], [])")
        limits = "Avalia o predicado uma vez por valor e cria listas independentes."
        trace = ("criar duas partições", "avaliar cada valor uma vez", "anexar à partição correspondente", "devolver aceites e rejeitados")
    elif family == 14:
        objective = "Transpor uma matriz retangular depois de validar a largura de todas as linhas."
        signature = f"{name}(matriz)"
        inputs = "`matriz` é uma sequência de linhas; cada linha deve ter o mesmo comprimento."
        example = f"`{name}([[{marker}, 1], [{marker + 1}, 2]])` devolve `[[{marker}, {marker + 1}], [1, 2]]`."
        starter = f"def {name}(matriz):\n    pass\n"
        solution = f"def {name}(matriz):\n    if not matriz:\n        return []\n    largura = len(matriz[0])\n    if any(len(linha) != largura for linha in matriz):\n        raise ValueError('matriz irregular')\n    return [[linha[coluna] for linha in matriz] for coluna in range(largura)]\n"
        tests = (f"assert {name}([[{marker}, 1], [{marker + 1}, 2]]) == [[{marker}, {marker + 1}], [1, 2]]", f"assert {name}([]) == []", f"try:\n    {name}([[1], [2, 3]])\n    assert False\nexcept ValueError:\n    pass")
        limits = "A matriz vazia produz lista vazia; rejeita linhas de comprimentos diferentes."
        trace = ("obter largura", "validar todas as linhas", "percorrer colunas", "recolher um valor por linha")
    elif family == 15:
        objective = "Calcular o produto interno de dois vetores com dimensões iguais."
        signature = f"{name}(a, b)"
        inputs = "`a` e `b` são sequências numéricas com o mesmo comprimento."
        example = f"`{name}([{marker}, 2], [3, 4])` devolve `{marker * 3 + 8}`."
        starter = f"def {name}(a, b):\n    pass\n"
        solution = f"def {name}(a, b):\n    if len(a) != len(b):\n        raise ValueError('dimensões incompatíveis')\n    return sum(x * y for x, y in zip(a, b))\n"
        tests = (f"assert {name}([{marker}, 2], [3, 4]) == {marker * 3 + 8}", f"assert {name}([], []) == 0", f"try:\n    {name}([1], [1, 2])\n    assert False\nexcept ValueError:\n    pass")
        limits = "Rejeita dimensões diferentes; vetores vazios compatíveis produzem zero."
        trace = ("validar dimensões", "multiplicar coordenadas correspondentes", "somar produtos", f"devolver {marker * 3 + 8}")
    elif family == 16:
        objective = "Normalizar valores para zero a um e declarar o caso constante."
        signature = f"{name}(valores)"
        inputs = "`valores` é uma sequência numérica não vazia; o resultado é uma lista de floats."
        example = f"`{name}([{marker}, {marker + 2}, {marker + 4}])` devolve `[0.0, 0.5, 1.0]`."
        starter = f"def {name}(valores):\n    pass\n"
        solution = f"def {name}(valores):\n    if not valores:\n        raise ValueError('sem valores')\n    minimo = min(valores)\n    amplitude = max(valores) - minimo\n    if amplitude == 0:\n        return [0.0 for _ in valores]\n    return [(valor - minimo) / amplitude for valor in valores]\n"
        tests = (f"assert {name}([{marker}, {marker + 2}, {marker + 4}]) == [0.0, 0.5, 1.0]", f"assert {name}([7, 7]) == [0.0, 0.0]", f"try:\n    {name}([])\n    assert False\nexcept ValueError:\n    pass")
        limits = "Rejeita vazio e transforma uma sequência constante em zeros sem divisão por zero."
        trace = ("encontrar mínimo e máximo", "calcular amplitude", "tratar amplitude zero", "escalar cada valor")
    elif family == 17:
        window = variant % 3 + 2
        values = list(range(marker, marker + 5))
        expected = [max(values[i:i + window]) for i in range(len(values) - window + 1)]
        objective = "Calcular o máximo de cada janela completa de tamanho positivo."
        signature = f"{name}(valores, tamanho)"
        inputs = "`valores` é uma sequência comparável e `tamanho` é um inteiro positivo."
        example = f"`{name}({values}, {window})` devolve `{expected}`."
        starter = f"def {name}(valores, tamanho):\n    pass\n"
        solution = f"def {name}(valores, tamanho):\n    if tamanho <= 0:\n        raise ValueError('tamanho inválido')\n    return [max(valores[i:i + tamanho]) for i in range(len(valores) - tamanho + 1)]\n"
        tests = (f"assert {name}({values}, {window}) == {expected}", f"assert {name}([1], 2) == []", f"try:\n    {name}([1], 0)\n    assert False\nexcept ValueError:\n    pass")
        limits = "Rejeita tamanho não positivo e não produz janelas incompletas."
        trace = ("validar tamanho", "recortar cada janela completa", "obter o máximo", f"produzir {len(expected)} resultados")
    elif family == 18:
        objective = "Intercalar duas sequências já ordenadas numa nova lista ordenada."
        signature = f"{name}(a, b)"
        inputs = "`a` e `b` são sequências em ordem crescente."
        example = f"`{name}([1, {marker}], [2, {marker + 2}])` devolve a intercalação crescente."
        starter = f"def {name}(a, b):\n    pass\n"
        solution = f"def {name}(a, b):\n    i = j = 0\n    resultado = []\n    while i < len(a) and j < len(b):\n        if a[i] <= b[j]:\n            resultado.append(a[i]); i += 1\n        else:\n            resultado.append(b[j]); j += 1\n    return resultado + list(a[i:]) + list(b[j:])\n"
        merged = sorted([1, marker, 2, marker + 2])
        tests = (f"assert {name}([1, {marker}], [2, {marker + 2}]) == {merged}", f"assert {name}([], [1]) == [1]")
        limits = "Preserva repetidos, não altera as entradas e trata uma sequência vazia."
        trace = ("manter dois índices", "escolher o menor valor atual", "avançar apenas o índice escolhido", "anexar a cauda restante")
    elif family == 19:
        objective = "Encontrar um alvo por pesquisa binária numa sequência crescente."
        signature = f"{name}(valores, alvo)"
        inputs = "`valores` está ordenado por ordem crescente; devolve um índice válido ou -1."
        example = f"`{name}([1, {marker}, {marker + 3}], {marker})` devolve `1`."
        starter = f"def {name}(valores, alvo):\n    pass\n"
        solution = f"def {name}(valores, alvo):\n    inicio, fim = 0, len(valores) - 1\n    while inicio <= fim:\n        meio = (inicio + fim) // 2\n        if valores[meio] == alvo:\n            return meio\n        if valores[meio] < alvo:\n            inicio = meio + 1\n        else:\n            fim = meio - 1\n    return -1\n"
        tests = (f"assert {name}([1, {marker}, {marker + 3}], {marker}) == 1", f"assert {name}([1, 3], 2) == -1", f"assert {name}([], 1) == -1")
        limits = "Trata vazio, reduz o intervalo em cada passo e devolve -1 quando ausente."
        trace = ("inicializar limites", "calcular meio", "descartar metade incompatível", "devolver índice ou -1")
    elif family == 20:
        token = f"v{variant}"
        objective = "Codificar ocorrências consecutivas como pares valor-contagem."
        signature = f"{name}(valores)"
        inputs = "`valores` é uma sequência; repetições separadas originam grupos diferentes."
        example = f"`{name}(['{token}', '{token}', 'x'])` devolve `[('{token}', 2), ('x', 1)]`."
        starter = f"def {name}(valores):\n    pass\n"
        solution = f"def {name}(valores):\n    resultado = []\n    for valor in valores:\n        if resultado and resultado[-1][0] == valor:\n            anterior, contagem = resultado[-1]\n            resultado[-1] = (anterior, contagem + 1)\n        else:\n            resultado.append((valor, 1))\n    return resultado\n"
        tests = (f"assert {name}(['{token}', '{token}', 'x']) == [('{token}', 2), ('x', 1)]", f"assert {name}([]) == []", f"assert {name}(['a','b','a']) == [('a',1),('b',1),('a',1)]")
        limits = "A entrada vazia produz vazio e apenas ocorrências adjacentes são combinadas."
        trace = ("criar resultado vazio", "comparar com o último grupo", "incrementar ou abrir grupo", "preservar a ordem")
    elif family == 21:
        objective = "Selecionar nomes que são identificadores Python e não começam por underscore."
        signature = f"{name}(nomes)"
        inputs = "`nomes` é uma sequência de strings; o resultado preserva a ordem."
        example = f"`{name}(['item_{marker}', '{marker}x', '_privado'])` devolve `['item_{marker}']`."
        starter = f"def {name}(nomes):\n    pass\n"
        solution = f"def {name}(nomes):\n    return [nome for nome in nomes if nome.isidentifier() and not nome.startswith('_')]\n"
        tests = (f"assert {name}(['item_{marker}', '{marker}x', '_privado']) == ['item_{marker}']", f"assert {name}([]) == []")
        limits = "Não altera capitalização, rejeita nomes privados por convenção e trata vazio."
        trace = ("percorrer nomes", "testar isidentifier", "excluir prefixo underscore", "preservar aceites pela ordem")
    elif family == 22:
        key = f"chave{variant}"
        objective = "Interpretar linhas chave=valor, ignorando vazias e rejeitando chaves repetidas."
        signature = f"{name}(linhas)"
        inputs = "`linhas` é uma sequência de strings; cada linha não vazia contém exatamente um separador inicial `=`."
        example = f"`{name}(['{key}= {marker}', '', 'estado=ok'])` devolve um dicionário com duas chaves."
        starter = f"def {name}(linhas):\n    pass\n"
        solution = f"def {name}(linhas):\n    resultado = {{}}\n    for linha in linhas:\n        if not linha.strip():\n            continue\n        if '=' not in linha:\n            raise ValueError('linha inválida')\n        chave, valor = (parte.strip() for parte in linha.split('=', 1))\n        if not chave or chave in resultado:\n            raise ValueError('chave inválida ou repetida')\n        resultado[chave] = valor\n    return resultado\n"
        tests = (f"assert {name}(['{key}= {marker}', '', 'estado=ok']) == {{'{key}':'{marker}','estado':'ok'}}", f"try:\n    {name}(['x=1','x=2'])\n    assert False\nexcept ValueError:\n    pass")
        limits = "Remove espaços exteriores, permite `=` no valor, rejeita chave vazia e duplicados."
        trace = ("ignorar vazias", "separar apenas no primeiro igual", "validar chave", "guardar valor normalizado")
    elif family == 23:
        objective = "Calcular o grau de saída de cada nó presente numa lista de arestas dirigidas."
        signature = f"{name}(arestas)"
        inputs = "`arestas` contém pares origem-destino; nós apenas de destino também aparecem com grau zero."
        example = f"`{name}([('{marker}','b'), ('{marker}','c'), ('b','c')])` atribui grau 2 a `{marker}`."
        starter = f"def {name}(arestas):\n    pass\n"
        solution = f"def {name}(arestas):\n    graus = {{}}\n    for origem, destino in arestas:\n        graus[origem] = graus.get(origem, 0) + 1\n        graus.setdefault(destino, 0)\n    return graus\n"
        tests = (f"assert {name}([('{marker}','b'), ('{marker}','c'), ('b','c')]) == {{'{marker}':2,'b':1,'c':0}}", f"assert {name}([]) == {{}}")
        limits = "Conta arestas repetidas como observações distintas e inclui destinos sem saída."
        trace = ("criar mapa de graus", "incrementar origem", "registar destino se ausente", "devolver todos os nós observados")
    else:
        amount = variant + 1
        objective = "Selecionar os k maiores valores por ordem decrescente sem alterar a entrada."
        signature = f"{name}(valores, k)"
        inputs = "`valores` é uma sequência comparável; `k` é um inteiro entre zero e o comprimento."
        example = f"`{name}([{marker}, 1, {marker + 3}], 2)` devolve `[{marker + 3}, {marker}]`."
        starter = f"def {name}(valores, k):\n    pass\n"
        solution = f"def {name}(valores, k):\n    if k < 0 or k > len(valores):\n        raise ValueError('k fora do intervalo')\n    return sorted(valores, reverse=True)[:k]\n"
        tests = (f"assert {name}([{marker}, 1, {marker + 3}], 2) == [{marker + 3}, {marker}]", f"assert {name}([1], 0) == []", f"try:\n    {name}([1], 2)\n    assert False\nexcept ValueError:\n    pass")
        limits = "Aceita k zero, preserva repetidos e rejeita k negativo ou superior ao comprimento."
        trace = ("validar k", "ordenar uma cópia por ordem decrescente", "recortar k posições", "devolver sem alterar entrada")
    return objective, signature, inputs, example, tests, starter, solution, limits, trace


def capital_accumulation_exercise() -> EditorialExercise:
    name = "tabela_capital_acumulado"
    prompt = (
        "Contextualização\n"
        "Pretendes comparar o crescimento de um depósito ao longo de vários anos. O cálculo é local, "
        "determinístico e não inclui reforços, impostos ou arredondamentos intermédios.\n\n"
        "Objetivo\n"
        "Construir a tabela anual de capitalização composta para todas as taxas fornecidas.\n\n"
        "Especificação técnica\n"
        "Implementa `tabela_capital_acumulado(capital_inicial, ano_inicial, taxas, anos)`. "
        "Para cada ano n e taxa t aplica `capital_inicial * (1 + t / 100) ** n` e arredonda cada resultado a duas casas decimais.\n\n"
        "Entradas e parâmetros\n"
        "`capital_inicial` é um número não negativo; `ano_inicial` e `anos` são inteiros, com anos positivo; "
        "`taxas` é uma sequência não vazia de percentagens superiores a -100.\n\n"
        "Exemplo de comportamento\n"
        "Com capital inicial 1500, ano inicial 2020, taxas 2, 2.5 e 3, e três anos, a tabela contém:\n"
        "2021 -> 1530.00, 1537.50, 1545.00\n"
        "2022 -> 1560.60, 1575.94, 1591.35\n"
        "2023 -> 1591.81, 1615.34, 1639.09\n\n"
        "Requisitos e casos-limite\n"
        "Usa nomes claros para ano, taxa e capital acumulado. Rejeita capital negativo, anos não positivo, "
        "taxas vazias e taxas inferiores ou iguais a -100. Não alteres a sequência de taxas.\n\n"
        "Critérios de avaliação\n"
        "A solução respeita a fórmula composta, devolve uma linha por ano, preserva a ordem das taxas e passa os testes locais."
    )
    solution = (
        f"def {name}(capital_inicial, ano_inicial, taxas, anos):\n"
        "    if capital_inicial < 0 or anos <= 0 or not taxas:\n"
        "        raise ValueError('parâmetros inválidos')\n"
        "    if any(taxa <= -100 for taxa in taxas):\n"
        "        raise ValueError('taxa inválida')\n"
        "    tabela = []\n"
        "    for numero_ano in range(1, anos + 1):\n"
        "        capitais = tuple(round(capital_inicial * (1 + taxa / 100) ** numero_ano, 2) for taxa in taxas)\n"
        "        tabela.append((ano_inicial + numero_ano, capitais))\n"
        "    return tabela\n"
    )
    tests = (
        f"assert {name}(1500, 2020, (2, 2.5, 3), 3) == [(2021, (1530.0, 1537.5, 1545.0)), (2022, (1560.6, 1575.94, 1591.35)), (2023, (1591.81, 1615.34, 1639.09))]",
        f"try:\n    {name}(-1, 2020, (2,), 1)\n    assert False\nexcept ValueError:\n    pass",
        f"try:\n    {name}(100, 2020, (), 1)\n    assert False\nexcept ValueError:\n    pass",
    )
    return EditorialExercise(
        slug="career-capital-acumulado", title="Capital acumulado por taxa e ano",
        prompt=prompt, starter_code=f"def {name}(capital_inicial, ano_inicial, taxas, anos):\n    pass\n",
        tests=tests, solution=solution,
        explanation=(
            "Capital inicial, ano inicial e quantidade de anos são constantes do cenário. "
            "numero_ano, taxa e capitais são variáveis de iteração. O ciclo exterior cria uma linha por ano; "
            "o cálculo interior aplica a fórmula a cada taxa sem acumular arredondamento."
        ),
        expected_trace=(
            "validar capital=1500, ano inicial=2020, taxas=(2, 2.5, 3) e anos=3",
            "n=1: calcular os capitais de 2021",
            "n=2: recalcular desde o capital inicial para 2022",
            "n=3: calcular 2023 e devolver as três linhas",
        ),
        difficulty=-0.1, role_slug="data-analyst", track_slug="python-foundations",
        graph_node_slug="loops-and-accumulators",
        source_id="local-d3e11ab782d92acd919e",
        supporting_source_ids=("src-python-docs", "src-pydoc-math-pow"),
        reveal_mode="guided", walkthrough_after=2, solution_after=4,
    )


def build_editorial_exercises() -> tuple[EditorialExercise, ...]:
    """Return exactly 500 distinct, deterministic exercises including the canonical example."""

    exercises: list[EditorialExercise] = [capital_accumulation_exercise()]
    for role_index, role in enumerate(CAREER_ROLES):
        context, track_slug, graph_node_slug, source_id = _ROLE_CONTEXT[role.slug]
        for family in range(25):
            for variant in range(4):
                if role.slug == "data-analyst" and family == 0 and variant == 0:
                    continue
                name = f"pratica_{role_index + 1}_{family + 1}_{variant + 1}"
                objective, signature, inputs, example, tests, starter, solution, limits, trace = _family(
                    family, name, variant, context,
                )
                prompt = _prompt(
                    context=context, objective=objective, signature=signature,
                    inputs=inputs, example=example, limits=limits, variant=variant,
                )
                difficulty = round(
                    min(2.4, -1.4 + (family % 5) * 0.55
                        + (family // 5) * 0.12 + variant * 0.08),
                    2,
                )
                reveal_mode = "evaluation-locked" if variant == 3 else "progressive"
                exercises.append(EditorialExercise(
                    slug=f"career-{role.slug}-{family + 1:02d}-{variant + 1:02d}",
                    title=f"{role.title} · prática {family + 1}.{variant + 1}",
                    prompt=prompt, starter_code=starter, tests=tests, solution=solution,
                    explanation=(
                        f"A solução separa validação, transformação e resultado para {context}. "
                        "Compara a tua estratégia pelos casos-limite e pela complexidade, não pelo texto."
                    ),
                    expected_trace=trace, difficulty=difficulty,
                    role_slug=role.slug, track_slug=track_slug,
                    graph_node_slug=graph_node_slug, source_id=source_id,
                    reveal_mode=reveal_mode,
                    walkthrough_after=3 if variant >= 2 else 2,
                    solution_after=6 if reveal_mode == "evaluation-locked" else (5 if variant >= 2 else 4),
                ))
    if len(exercises) != 500 or len({item.slug for item in exercises}) != 500:
        raise AssertionError("the editorial exercise bank must contain 500 unique exercises")
    return tuple(exercises)


_PROJECT_DOMAINS = (
    "registo e validação", "pesquisa e indexação", "processamento incremental",
    "qualidade e observabilidade", "relatórios reproduzíveis", "persistência transacional",
    "recuperação de falhas", "avaliação de desempenho", "segurança de fronteiras",
    "entrega e documentação",
)


def build_editorial_projects() -> tuple[EditorialProject, ...]:
    projects: list[EditorialProject] = []
    for role in CAREER_ROLES:
        tracks = tuple(dict.fromkeys(
            track for stage in role.stages for track in stage.track_slugs
        ))
        for index, domain in enumerate(_PROJECT_DOMAINS):
            projects.append(EditorialProject(
                id=f"career-project-{role.slug}-{index + 1:02d}",
                role_slug=role.slug, track_slug=tracks[index % len(tracks)],
                title=f"{role.title} · {domain.capitalize()}",
                brief=(
                    f"Constrói um artefacto local de {domain} orientado ao papel de {role.title}. "
                    "Define utilizadores e entradas, torna o resultado observável, justifica as estruturas escolhidas "
                    f"e demonstra como o produto contribui para este resultado profissional: {role.outcome}"
                ),
                requirements=(
                    "Contrato de entrada, saída, erros e limites escrito antes da implementação",
                    "Arquitetura em componentes pequenos com dependências explícitas",
                    "Testes determinísticos para casos normal, fronteira, falha e recuperação",
                    "Métricas locais e registo suficiente para reproduzir uma decisão",
                    "Documento final com instruções, compromissos e trabalho futuro",
                ),
                milestones=(
                    "Problema, atores e critérios de aceitação",
                    "Primeira fatia ponta a ponta executável",
                    "Casos-limite, segurança e recuperação",
                    "Testes, medição, refactoring e entrega",
                ),
                rubric=(
                    "correção observável", "desenho e legibilidade", "testes e fronteiras",
                    "segurança e recuperação", "evidência e documentação",
                ),
                level="beginner" if index < 2 else "intermediate" if index < 7 else "advanced",
                capstone=index == len(_PROJECT_DOMAINS) - 1,
            ))
    if len(projects) != 50 or len({item.id for item in projects}) != 50:
        raise AssertionError("the editorial project bank must contain 50 unique projects")
    return tuple(projects)


EDITORIAL_EXERCISES = build_editorial_exercises()
EDITORIAL_PROJECTS = build_editorial_projects()
