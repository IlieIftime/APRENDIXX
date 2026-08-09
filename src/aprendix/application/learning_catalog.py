"""Original, source-linked learning facts and glossary expansion.

The text in this module is authored for Aprendix.  References are identifiers
for bibliographic metadata; no protected source text is reproduced.
"""

from __future__ import annotations

from dataclasses import dataclass

from aprendix.application.academy_catalog import (
    ACADEMY_MODULES,
    ACADEMY_TRACKS,
    VERTICAL_CORE_MODULES,
)


@dataclass(frozen=True, slots=True)
class FactDefinition:
    slug: str
    area_id: str
    fact: str
    explanation: str
    formula_or_code: str = ""
    complexity: str = "beginner"
    source_ids: tuple[str, ...] = ()


FACTS: tuple[FactDefinition, ...] = (
    FactDefinition("modulo-paridade", "prog-foundations", "O resto da divisão por 2 permite testar a paridade de um inteiro.", "`n % 2` vale zero quando `n` é par e um quando é ímpar. O operador `%` calcula o resto; não realiza uma divisão por zero.", "par = (n % 2 == 0)", source_ids=("src-python-docs",)),
    FactDefinition("truthiness", "prog-foundations", "Python permite testar coleções vazias diretamente numa condição.", "Listas, dicionários, conjuntos e strings vazios são falsos; coleções não vazias são verdadeiras. Isto evita comparações redundantes com zero.", "if resultados:\n    print('há dados')", source_ids=("src-python-docs", "src-fluent-python")),
    FactDefinition("generator-lazy", "python", "Um generator pode representar uma sequência maior do que a memória disponível.", "Os valores são produzidos sob pedido e não guardados todos de uma vez. A vantagem desaparece se o generator for imediatamente convertido numa lista.", "quadrados = (n * n for n in range(1_000_000))", source_ids=("src-python-docs", "src-fluent-python")),
    FactDefinition("mutable-default", "python", "Um argumento predefinido mutável é criado uma única vez, não em cada chamada.", "Usa `None` como sentinela e cria a lista dentro da função para impedir que chamadas independentes partilhem estado acidentalmente.", "def adicionar(x, itens=None):\n    itens = [] if itens is None else itens", "intermediate", ("src-python-docs", "src-fluent-python")),
    FactDefinition("composition", "oop", "Composição costuma preservar melhor o encapsulamento do que uma hierarquia profunda.", "Um objeto recebe colaboradores com contratos pequenos. Assim, cada parte pode ser substituída ou testada sem herdar estado e comportamento que não usa.", "class Relatorio:\n    def __init__(self, repositorio):\n        self.repositorio = repositorio", "intermediate", ("src-python-docs",)),
    FactDefinition("dataclass", "oop", "Uma dataclass gera operações de dados sem esconder as regras do domínio.", "É adequada para valores e registos. Invariantes continuam a pertencer a métodos explícitos ou a `__post_init__`.", "@dataclass(frozen=True)\nclass Ponto:\n    x: float\n    y: float", "intermediate", ("src-python-docs",)),
    FactDefinition("set-membership", "data-structures", "Um `set` troca ordem e repetição por testes médios de pertença muito rápidos.", "A procura média é O(1), enquanto procurar numa lista é O(n). Mantém também uma lista quando a ordem de primeira ocorrência fizer parte do resultado.", "vistos = set()\nif item not in vistos: vistos.add(item)", source_ids=("src-python-docs", "src-clrs")),
    FactDefinition("hash-collisions", "data-structures", "Duas chaves podem ter o mesmo hash sem serem a mesma chave.", "A tabela de dispersão resolve colisões e confirma igualdade. Por isso, objetos mutáveis não devem ser usados como chaves se o seu hash puder mudar.", "hash(chave)", "intermediate", ("src-python-docs", "src-clrs")),
    FactDefinition("binary-search", "classic-algorithms", "Pesquisa binária elimina metade do espaço a cada passo.", "Exige uma coleção ordenada e limites atualizados sem perder o alvo. O número de comparações cresce como O(log n).", "meio = inicio + (fim - inicio) // 2", source_ids=("src-clrs",)),
    FactDefinition("big-o-constants", "classic-algorithms", "Big-O descreve crescimento, não o tempo real isolado.", "Dois algoritmos O(n) podem ter custos constantes muito diferentes. Mede entradas representativas depois de escolher uma classe de complexidade adequada.", "T(n) = 3n + 8 ∈ O(n)", "intermediate", ("src-clrs",)),
    FactDefinition("tests-boundaries", "software-engineering", "Um teste de fronteira revela pressupostos que um exemplo médio costuma esconder.", "Para cada contrato, testa vazio, mínimo, máximo razoável, repetição e falha esperada. Um teste deve produzir sempre a mesma evidência.", "assert dividir([], 2) == []", source_ids=("src-python-docs",)),
    FactDefinition("database-index", "databases", "Um índice acelera leituras específicas, mas cobra espaço e trabalho em cada escrita.", "Escolhe índices a partir das consultas reais. A ordem das colunas num índice composto altera quais filtros e ordenações podem aproveitá-lo.", "CREATE INDEX idx_evento_user_data ON eventos(user_id, data);", "intermediate", ("src-postgresql",)),
    FactDefinition("transaction-atomic", "databases", "Uma transação transforma várias escritas numa única decisão: confirmar tudo ou nada.", "Atomicidade não substitui isolamento. Em concorrência, seleciona o nível de isolamento e mantém transações curtas para reduzir bloqueios.", "BEGIN;\nUPDATE ...;\nCOMMIT;", "intermediate", ("src-postgresql",)),
    FactDefinition("semantic-html", "web", "HTML semântico melhora acessibilidade antes de qualquer CSS.", "Elementos como `nav`, `main`, `button` e títulos comunicam estrutura a leitores de ecrã e ferramentas automáticas.", "<button type=\"button\">Executar</button>", source_ids=("src-mdn",)),
    FactDefinition("async-not-parallel", "systems", "Concorrência assíncrona não significa execução paralela de CPU.", "`asyncio` é eficaz quando tarefas esperam por I/O. Trabalho intensivo de CPU exige processos, extensões nativas ou outra estratégia de paralelismo.", "resultado = await pedido()", "intermediate", ("src-python-docs",)),
    FactDefinition("dot-product", "linear-algebra", "O produto interno mede alinhamento e também calcula a entrada de um neurónio.", "Multiplica componentes correspondentes e soma. Se os vetores forem normalizados, o produto interno coincide com a similaridade do cosseno.", "x·w = Σᵢ xᵢwᵢ", "intermediate", ("src-dlbook", "src-probml")),
    FactDefinition("chain-rule", "calculus", "Backpropagation é uma aplicação organizada da regra da cadeia.", "Cada operação local fornece uma derivada; o gradiente total resulta do produto desses efeitos ao longo do grafo computacional.", "∂L/∂x = (∂L/∂y)(∂y/∂x)", "intermediate", ("src-dlbook", "src-pytorch-autograd")),
    FactDefinition("bayes", "probability", "Bayes combina conhecimento anterior com a evidência observada.", "A posterior é proporcional à verosimilhança vezes a prior. A constante de normalização garante que as probabilidades somam um.", "P(H|D) = P(D|H)P(H) / P(D)", "intermediate", ("src-probml",)),
    FactDefinition("learning-rate", "optimization", "Uma taxa de aprendizagem demasiado grande pode aumentar a perda mesmo com o gradiente correto.", "O gradiente indica direção local; a taxa define o tamanho do passo. Compara curvas de treino e validação e verifica escalas das variáveis.", "θ ← θ − η∇L(θ)", "intermediate", ("src-dlbook",)),
    FactDefinition("data-leakage", "data-practice", "Pré-processar antes de separar treino e validação pode revelar o futuro ao modelo.", "Ajusta imputação, normalização e seleção apenas nos dados de treino. Pipelines aplicam depois a transformação aprendida à validação.", "Pipeline([('scale', StandardScaler()), ('model', SVC())])", "intermediate", ("src-sklearn", "src-pandas")),
    FactDefinition("a-star", "ai-foundations", "A* encontra um caminho ótimo quando a heurística nunca sobrestima o custo restante.", "A prioridade combina custo já pago `g` e estimativa `h`. Uma heurística mais informativa reduz expansões sem perder a garantia quando é admissível.", "f(n) = g(n) + h(n)", "advanced", ("src-aima",)),
    FactDefinition("cross-validation", "classical-ml", "Cross-validation estima variação; não transforma validação em dados de treino.", "Toda a escolha de hiperparâmetros ocorre dentro dos folds. Mantém um teste final intocado para a última estimativa.", "score = cross_val_score(modelo, X, y, cv=5)", "intermediate", ("src-sklearn", "src-esl")),
    FactDefinition("uncertainty", "probabilistic-ml", "Uma probabilidade prevista não é automaticamente uma probabilidade calibrada.", "Entre casos anunciados com 80%, aproximadamente 80% deveriam ocorrer. Verifica curvas de calibração e qualidade fora da amostra.", "P(y=1|x)=0.8", "advanced", ("src-probml",)),
    FactDefinition("bagging", "ensemble-learning", "Bagging reduz variância ao combinar modelos treinados em amostras diferentes.", "A média suaviza erros não perfeitamente correlacionados. Se todos os modelos errarem da mesma forma, o benefício diminui.", "ŷ = (1/M) Σₘ fₘ(x)", "intermediate", ("src-esl", "src-sklearn")),
    FactDefinition("neuron", "neural-networks", "Um neurónio artificial aplica uma transformação linear e depois uma não linearidade.", "Os pesos selecionam e combinam sinais; o bias desloca a fronteira; a ativação permite que camadas compostas representem relações não lineares.", "z = w·x + b;  a = φ(z)", source_ids=("src-dlbook",)),
    FactDefinition("backprop", "deep-learning", "Backpropagation reutiliza derivadas intermédias em vez de recalcular cada caminho.", "O forward guarda valores necessários; o backward propaga gradientes da perda para cada parâmetro pelo grafo invertido.", "∂L/∂w = (∂L/∂a)(∂a/∂z)(∂z/∂w)", "advanced", ("src-dlbook", "src-pytorch-autograd")),
    FactDefinition("cnn-sharing", "convolutional-networks", "Uma convolução usa os mesmos pesos em várias posições da imagem.", "A partilha reduz parâmetros e permite detetar o mesmo padrão em locais diferentes. Padding, stride e tamanho do kernel determinam a geometria da saída.", "H_out = ⌊(H+2P−K)/S⌋+1", "intermediate", ("src-resnet", "src-dlbook")),
    FactDefinition("lstm-gates", "sequence-models", "Uma LSTM controla explicitamente o que esquece, escreve e expõe.", "As portas usam valores entre zero e um para modular a memória. Isso melhora o fluxo de gradiente, mas não elimina todos os problemas de sequências longas.", "cₜ = fₜ⊙cₜ₋₁ + iₜ⊙gₜ", "advanced", ("src-dlbook",)),
    FactDefinition("scaled-attention", "transformers", "A atenção divide os produtos internos por √d para evitar softmax excessivamente saturado.", "Queries comparam-se com keys; os pesos normalizados combinam values. Máscaras impedem acesso a posições proibidas.", "Attention(Q,K,V)=softmax(QKᵀ/√dₖ)V", "advanced", ("src-attention",)),
    FactDefinition("diffusion", "generative-ai", "Um modelo de difusão aprende a inverter gradualmente um processo de adição de ruído.", "O treino prevê ruído ou uma grandeza equivalente; a geração começa em ruído e executa vários passos de remoção condicionada.", "xₜ → xₜ₋₁ → … → x₀", "advanced", ("src-dlbook",)),
    FactDefinition("iou", "computer-vision", "Intersection over Union compara a sobreposição entre previsão e referência.", "A métrica divide a área de interseção pela união. Em deteção, um limiar de IoU ajuda a decidir se uma caixa corresponde ao objeto.", "IoU = |A∩B| / |A∪B|", "intermediate", ("src-resnet", "src-vit")),
    FactDefinition("tokenization", "natural-language", "Um modelo de linguagem normalmente recebe tokens, não palavras completas.", "Subpalavras equilibram vocabulário e cobertura. Uma alteração pequena no texto pode produzir uma sequência de tokens diferente.", "texto → ids de tokens → embeddings", "intermediate", ("src-attention", "src-rag")),
    FactDefinition("bellman", "reinforcement-learning", "A equação de Bellman separa recompensa imediata de valor futuro descontado.", "Ela torna um problema sequencial recursivo. O fator γ controla quanto as consequências futuras influenciam a decisão atual.", "V(s)=E[r+γV(s′)]", "advanced", ("src-rlbook",)),
    FactDefinition("agent-loop", "autonomous-agents", "Um agente fiável separa observação, decisão, ação e verificação.", "Cada ferramenta deve ter contrato, limite e resultado observável. A verificação impede que uma resposta textual seja confundida com uma ação realmente executada.", "observar → planear → agir → verificar", "intermediate", ("src-aima", "src-react")),
    FactDefinition("react-loop", "agent-architectures", "ReAct intercala raciocínio operacional com observações reais das ferramentas.", "O plano é revisto depois de cada resultado. Trajetórias limitadas e auditáveis são mais seguras do que ciclos sem condição de paragem.", "pensamento → ação → observação", "advanced", ("src-react", "src-reflexion")),
    FactDefinition("episodic-memory", "agent-memory", "Memória episódica guarda experiências; memória semântica guarda conhecimento consolidado.", "Recuperar tudo aumenta ruído e custo. Um agente deve selecionar memórias por relevância, atualidade e confiança.", "score = relevância × confiança × recência", "advanced", ("src-reflexion", "src-generative-agents")),
    FactDefinition("multi-agent", "multi-agent", "Mais agentes não garantem uma solução melhor.", "A coordenação acrescenta mensagens, conflitos e duplicação. Papéis claros e uma regra de agregação verificável são essenciais.", "resultado = agregar(propostas, evidência)", "advanced", ("src-generative-agents", "src-aima")),
    FactDefinition("agent-eval", "agent-evaluation", "Avaliar apenas a resposta final esconde ações inseguras no percurso.", "Mede sucesso, custo, chamadas inválidas, recuperação de erros e necessidade de intervenção humana por trajetória.", "taxa_sucesso, custo, violações, recuperação", "advanced", ("src-react", "src-ai-index")),
    FactDefinition("calibration-fairness", "responsible-ai", "Precisão global pode esconder falhas graves num subgrupo.", "Compara erro, calibração e cobertura entre grupos relevantes e documenta incerteza. A métrica adequada depende do dano possível.", "erro_grupo = falhas_grupo / casos_grupo", "advanced", ("src-ai-index",)),
    FactDefinition("finance-split", "finance-app", "Em finanças, dividir dados aleatoriamente pode ensinar o futuro ao passado.", "Usa divisões temporais e inclui custos, atrasos e survivorship bias. Uma estratégia só é avaliada em períodos posteriores ao treino.", "treino < validação < teste no tempo", "advanced", ("src-esl",)),
    FactDefinition("medical-metrics", "health-app", "Sensibilidade e especificidade respondem a perguntas diferentes.", "Sensibilidade mede positivos detetados; especificidade mede negativos corretamente rejeitados. O limiar deve refletir custos clínicos e prevalência.", "sensibilidade = TP/(TP+FN)", "intermediate", ("src-unet",)),
    FactDefinition("pid", "robotics-app", "Um controlador PID combina erro atual, acumulado e tendência do erro.", "O termo proporcional reage, o integral remove erro persistente e o derivativo amortece mudanças rápidas. Saturação exige anti-windup.", "u=Kₚe+Kᵢ∫e dt+K_d de/dt", "advanced", ("src-aima",)),
    FactDefinition("game-delta", "games-app", "Movimento dependente do número de frames muda de velocidade entre computadores.", "Multiplica velocidades pelo tempo decorrido e limita saltos muito grandes. A simulação pode usar passos fixos separados do desenho.", "posição += velocidade × delta_t", "intermediate", ("src-clrs",)),
    FactDefinition("implicit-feedback", "recommendation-app", "Um clique é feedback implícito, não uma declaração inequívoca de preferência.", "Posição, exposição e curiosidade influenciam o clique. Mantém uma linha de base e distingue não observado de rejeitado.", "score(u,i)=afinidade−viés_exposição", "advanced", ("src-esl",)),
    FactDefinition("time-validation", "time-series-app", "Validação temporal nunca deve baralhar observações futuras para o treino.", "Expanding windows simulam a informação disponível em cada data. Compara sempre com baselines sazonais simples.", "train[:t] → validate[t:t+h]", "intermediate", ("src-probml",)),
    FactDefinition("least-privilege", "cybersecurity-app", "Código deve receber apenas as permissões necessárias durante o menor tempo possível.", "Isolamento, allowlists e limites de recursos reduzem impacto mesmo quando há um erro. Validação de entrada não substitui sandboxing.", "permissões = mínimo(necessário)", "intermediate", ("src-python-docs",)),
    FactDefinition("numerical-stability", "science-app", "Expressões matematicamente equivalentes podem ter erros numéricos muito diferentes.", "Evita subtrair números quase iguais e acompanha escala, unidade e condicionamento. Valida com casos de referência.", "logsumexp(x)=m+log Σ exp(xᵢ−m)", "advanced", ("src-numpy",)),
    FactDefinition("quantization", "edge-mobile-app", "Quantização int8 reduz aproximadamente quatro vezes o armazenamento face a float32.", "O ganho real depende de operadores e hardware. Mede erro por camada e calibra com dados representativos antes de aceitar o modelo.", "real ≈ escala × (q − zero_point)", "advanced", ("src-pytorch-autograd", "src-ai-index")),
)


_TRACK_AREAS = {
    "computer-literacy": "prog-foundations",
    "logic-pseudocode": "prog-foundations",
    "python-foundations": "prog-foundations",
    "python-oop": "oop",
    "python-algorithms": "classic-algorithms",
    "python-data-structures": "data-structures",
    "math-programming": "linear-algebra",
    "testing-debugging": "software-engineering",
    "python-advanced": "python",
    "sql-databases": "databases",
    "web-apis": "web",
    "data-ai": "classical-ml",
}

_MODULE_AREAS = {
    "sets-and-relations": "data-structures",
    "probability-summary": "probability",
    "vectors-and-dot-product": "linear-algebra",
    "bounded-scheduling": "systems",
    "data-pipelines": "data-practice",
    "classical-ml": "classical-ml",
    "neural-agents": "neural-networks",
}

_AREA_SOURCES = {
    "prog-foundations": ("src-python-docs",),
    "python": ("src-python-docs", "src-fluent-python"),
    "oop": ("src-python-docs", "src-fluent-python"),
    "classic-algorithms": ("src-clrs",),
    "data-structures": ("src-clrs", "src-python-docs"),
    "linear-algebra": ("src-numpy",),
    "probability": ("src-probml",),
    "software-engineering": ("src-python-docs",),
    "systems": ("src-python-docs",),
    "databases": ("src-postgresql",),
    "web": ("src-mdn",),
    "data-practice": ("src-numpy", "src-pandas"),
    "classical-ml": ("src-sklearn", "src-esl"),
    "neural-networks": ("src-dlbook", "src-pytorch-autograd"),
}


def _module_fact(spec: tuple[str, str, str, str, str, str, str]) -> FactDefinition:
    slug, track, title, objective, explanation, starter, _test = spec
    area = _MODULE_AREAS.get(slug, _TRACK_AREAS[track])
    return FactDefinition(
        slug=f"curriculum-{slug}",
        area_id=area,
        fact=f"{title}: {objective}",
        explanation=explanation,
        formula_or_code=starter.strip(),
        complexity="intermediate" if track not in {"computer-literacy", "logic-pseudocode", "python-foundations"} else "beginner",
        source_ids=_AREA_SOURCES.get(area, ("src-python-docs",)),
    )


_LEGACY_CURRICULUM_FACTS = (
    FactDefinition("curriculum-visible-output", "prog-foundations", "Resultados observáveis: produzir e verificar output antes de abstrair.", "O output é evidência direta de uma transformação. Compara valores, espaços, acentos e linhas com uma expectativa escrita antes da execução.", "print('resultado:', 2 + 3)", source_ids=("src-python-docs",)),
    FactDefinition("curriculum-values-and-names", "prog-foundations", "Valores e nomes: ligar nomes claros a valores e transformar sem efeitos ocultos.", "Uma atribuição associa um nome a um valor. A expressão do lado direito é avaliada primeiro; o nome deve comunicar o papel desse resultado.", "total = preco * quantidade", source_ids=("src-python-docs",)),
    FactDefinition("curriculum-safe-decisions", "prog-foundations", "Decisões explícitas: cobrir ramos e fronteiras de uma condição.", "Testa pelo menos um caso verdadeiro, um falso e o valor exato de fronteira. `else` representa o caminho usado quando as condições anteriores não se verificam.", "estado = 'adulto' if idade >= 18 else 'menor'", source_ids=("src-python-docs",)),
    FactDefinition("curriculum-objects-and-state", "oop", "Objetos e estado: construir uma classe com invariantes simples.", "Cada instância conserva o seu estado. O construtor estabelece um estado inicial válido e os métodos preservam as regras após cada operação pública.", "class Contador:\n    def __init__(self):\n        self.valor = 0", "intermediate", ("src-python-docs", "src-fluent-python")),
    FactDefinition("curriculum-methods-and-invariants", "oop", "Métodos e invariantes: alterar estado sem quebrar regras do domínio.", "Valida a operação antes de confirmar uma alteração. Quando uma pré-condição falha, o objeto deve permanecer num estado válido e previsível.", "if valor > self.saldo:\n    return False", "intermediate", ("src-fluent-python",)),
    FactDefinition("curriculum-iteration-and-search", "classic-algorithms", "Iteração e pesquisa: percorrer uma sequência com critério de paragem claro.", "A pesquisa linear compara por ordem e termina ao encontrar o alvo ou ao esgotar a entrada. O caso ausente faz parte do contrato.", "for indice, valor in enumerate(valores):\n    if valor == alvo:\n        return indice", "intermediate", ("src-clrs",)),
    FactDefinition("curriculum-algorithm-boundaries", "classic-algorithms", "Casos-limite: testar vazio, mínimo e valores repetidos.", "Os limites tornam suposições visíveis. Um contrato deve explicar coleções vazias, um único elemento, repetição e falhas esperadas.", "casos = [[], [alvo], [alvo, alvo]]", "intermediate", ("src-clrs",)),
    FactDefinition("curriculum-maps-and-frequency", "data-structures", "Mapas e frequências: associar chaves únicas a contagens.", "Um dicionário responde eficientemente a perguntas por chave. A contagem começa num elemento neutro e é atualizada uma vez por observação.", "contagens[valor] = contagens.get(valor, 0) + 1", "intermediate", ("src-python-docs", "src-clrs")),
    FactDefinition("curriculum-sets-and-order", "data-structures", "Pertença e ordem: combinar `set` para pertença com `list` para ordem.", "O conjunto evita repetições; a lista conserva a ordem de primeira ocorrência. Duas estruturas podem representar responsabilidades diferentes do mesmo algoritmo.", "vistos, resultado = set(), []", "intermediate", ("src-python-docs", "src-clrs")),
)


_MODULE_CURRICULUM_FACTS = tuple(_module_fact(spec) for spec in ACADEMY_MODULES)

_CARD_OPERATIONS = (
    ("previsão", "prevê o resultado antes de executar e regista a razão"),
    ("traçado", "acompanha apenas as mudanças de estado relevantes"),
    ("fronteira", "procura o menor caso que muda o comportamento"),
    ("invariante", "declara o que tem de continuar verdadeiro em cada passo"),
    ("contrato", "separa entradas aceites, resultado e falhas esperadas"),
    ("diagnóstico", "localiza a primeira divergência em vez do último sintoma"),
    ("teste", "transforma uma expectativa concreta numa verificação repetível"),
    ("complexidade", "identifica a operação cujo número mais cresce com a entrada"),
    ("transferência", "aplica o mesmo contrato a dados e contexto diferentes"),
    ("comparação", "contrasta duas soluções pelo comportamento e pelos custos"),
    ("refactoring", "reduz duplicação sem alterar os resultados observáveis"),
)

_CARD_EVIDENCE = (
    ("exemplo mínimo", "usa primeiro uma entrada pequena que possas calcular à mão"),
    ("contraexemplo", "tenta falsificar a solução com vazio, repetição ou valor extremo"),
    ("explicação", "justifica cada decisão com o contrato, não com coincidência de output"),
    ("medição", "regista resultado, custo e estado antes/depois para comparar objetivamente"),
)


def _vertical_fact_bank() -> tuple[FactDefinition, ...]:
    facts = []
    for slug, track, title, objective, explanation, starter, _test in VERTICAL_CORE_MODULES:
        area = _MODULE_AREAS.get(slug, _TRACK_AREAS[track])
        for operation_index, (operation, action) in enumerate(_CARD_OPERATIONS):
            for evidence_index, (evidence, method) in enumerate(_CARD_EVIDENCE):
                facts.append(FactDefinition(
                    slug=f"core-card-{slug}-{operation_index:02d}-{evidence_index:02d}",
                    area_id=area,
                    fact=f"{title} · {operation}: {action}.",
                    explanation=(
                        f"{explanation} Para obter evidência por {evidence}, {method}. "
                        f"O objetivo verificável desta unidade é: {objective}"
                    ),
                    formula_or_code=starter.strip(),
                    complexity=("beginner" if track == "python-foundations" else "intermediate"),
                    source_ids=_AREA_SOURCES.get(area, ("src-python-docs",)),
                ))
    return tuple(facts)


_VERTICAL_PRACTICE_FACTS = _vertical_fact_bank()

_PROJECT_CURRICULUM_FACTS = tuple(
    FactDefinition(
        slug=f"curriculum-{slug}-project",
        area_id=_TRACK_AREAS[slug],
        fact=f"Projeto de {title}: criar e justificar um artefacto local verificável.",
        explanation=(
            f"Um projeto de {title} demonstra transferência quando declara requisitos, "
            "regista decisões, inclui testes reproduzíveis e explica pelo menos um caso-limite. "
            f"O foco técnico é: {description}"
        ),
        formula_or_code="requisitos → testes → implementação → revisão",
        complexity="intermediate",
        source_ids=_AREA_SOURCES.get(_TRACK_AREAS[slug], ("src-python-docs",)),
    )
    for slug, title, description, _technology, _position in ACADEMY_TRACKS
)


# A single, stable catalogue used by search, cards and curriculum evidence.
# Every generated item is original Aprendix copy assembled from the authored
# curriculum specifications above; no external body text is copied.
ALL_FACTS: tuple[FactDefinition, ...] = (
    *FACTS,
    *_LEGACY_CURRICULUM_FACTS,
    *_MODULE_CURRICULUM_FACTS,
    *_PROJECT_CURRICULUM_FACTS,
    *_VERTICAL_PRACTICE_FACTS,
)


# term, technology, concise definition, signature, example, related terms
EXTRA_GLOSSARY: tuple[tuple[str, str, str, str, str, tuple[str, ...]], ...] = (
    ("else", "python", "Introduz o ramo executado quando a condição anterior é falsa, ou o bloco final de certas estruturas de repetição e exceção.", "else:", "if saldo >= custo:\n    pagar()\nelse:\n    avisar()", ("if", "elif", "for", "try")),
    ("elif", "python", "Testa uma condição adicional quando os ramos anteriores de um `if` não foram escolhidos.", "elif condição:", "if n < 0: ...\nelif n == 0: ...", ("if", "else")),
    ("try", "python", "Delimita operações cujas exceções serão tratadas por blocos `except`, `else` ou `finally`.", "try: ... except TipoErro: ...", "try:\n    valor = int(texto)\nexcept ValueError:\n    valor = 0", ("except", "finally", "exception")),
    ("except", "python", "Trata apenas os tipos de exceção explicitamente indicados depois de uma operação protegida.", "except TipoErro as erro:", "except ValueError as erro:\n    print(erro)", ("try", "raise", "finally")),
    ("finally", "python", "Executa limpeza quer exista uma exceção quer a operação termine normalmente.", "finally:", "try:\n    usar()\nfinally:\n    fechar()", ("try", "with")),
    ("with", "python", "Usa um context manager para adquirir e libertar um recurso de forma determinística.", "with expressão as nome:", "with open(caminho) as ficheiro:\n    texto = ficheiro.read()", ("context manager", "finally", "open")),
    ("lambda", "python", "Cria uma função anónima limitada a uma única expressão.", "lambda argumentos: expressão", "chave = lambda item: item.preco", ("def", "function")),
    ("yield", "python", "Suspende uma função generator e entrega um valor, preservando o seu estado para a continuação.", "yield valor", "def pares():\n    for n in range(4):\n        if n % 2 == 0: yield n", ("generator", "iterator")),
    ("async", "python", "Declara código assíncrono que pode suspender cooperativamente em operações aguardáveis.", "async def função(...):", "async def obter():\n    return await pedido()", ("await", "asyncio")),
    ("await", "python", "Suspende a coroutine atual até um awaitable terminar, permitindo que o event loop avance outras tarefas.", "await awaitable", "resposta = await cliente.get(url)", ("async", "coroutine")),
    ("break", "python", "Termina imediatamente o ciclo `for` ou `while` mais interior.", "break", "for item in dados:\n    if item == alvo: break", ("continue", "for", "while")),
    ("continue", "python", "Salta o restante corpo da iteração atual e avança para a próxima.", "continue", "if inválido:\n    continue", ("break", "for", "while")),
    ("pass", "python", "Instrução que não executa operação alguma, usada onde a sintaxe exige um bloco.", "pass", "class Marcador:\n    pass", ("class", "def")),
    ("in", "python", "Testa pertença ou participa na iteração sobre os elementos de um objeto.", "elemento in coleção", "if chave in mapa: ...", ("set", "for")),
    ("is", "python", "Compara identidade de objetos; não substitui `==` para igualdade de valores.", "objeto is outro", "if resultado is None: ...", ("None", "equality")),
    ("None", "python", "Objeto singleton usado para representar ausência explícita de valor.", "None", "resultado = None", ("is", "optional")),
    ("match", "python", "Inicia pattern matching estrutural sobre a forma e os valores de um objeto.", "match valor:", "match ponto:\n    case (0, y): ...", ("case", "if")),
    ("case", "python", "Define um padrão possível dentro de uma instrução `match`.", "case padrão [if guarda]:", "case {'estado': 'ok'}: ...", ("match", "pattern")),
    ("assert", "python", "Verifica uma condição de desenvolvimento e lança `AssertionError` se for falsa; não valida input hostil em produção.", "assert condição, mensagem", "assert total >= 0", ("test", "raise")),
    ("raise", "python", "Interrompe o fluxo normal lançando uma exceção explícita.", "raise TipoErro(mensagem)", "raise ValueError('idade inválida')", ("exception", "try")),
    ("import", "python", "Carrega um módulo e liga um nome ao respetivo objeto de módulo ou membro.", "import módulo", "import math", ("module", "from")),
    ("from", "python", "Seleciona membros ou uma base relativa ao importar, e também aparece em `yield from`.", "from módulo import nome", "from pathlib import Path", ("import", "module")),
    ("all", "python", "Devolve verdadeiro quando todos os elementos são verdadeiros; numa coleção vazia devolve verdadeiro.", "all(iterável)", "all(n > 0 for n in valores)", ("any", "bool")),
    ("any", "python", "Devolve verdadeiro quando pelo menos um elemento é verdadeiro; numa coleção vazia devolve falso.", "any(iterável)", "any(erro for erro in erros)", ("all", "bool")),
    ("abs", "python", "Devolve o valor absoluto de um número ou usa o protocolo `__abs__` do objeto.", "abs(x)", "abs(-4)  # 4", ("math", "number")),
    ("isinstance", "python", "Testa se um objeto pertence a um tipo ou a uma hierarquia de tipos.", "isinstance(objeto, tipo)", "isinstance(valor, (int, float))", ("type", "class")),
    ("map", "python", "Produz preguiçosamente a aplicação de uma função a elementos de um ou mais iteráveis.", "map(função, iterável, ...)", "map(str.upper, nomes)", ("filter", "iterator")),
    ("filter", "python", "Produz os elementos para os quais um predicado é verdadeiro.", "filter(predicado, iterável)", "filter(str.isdigit, textos)", ("map", "iterator")),
    ("min", "python", "Seleciona o menor elemento ou o elemento com menor chave calculada.", "min(iterável, key=None)", "min(pessoas, key=lambda p: p.idade)", ("max", "sorted")),
    ("max", "python", "Seleciona o maior elemento ou o elemento com maior chave calculada.", "max(iterável, key=None)", "max(notas, default=0)", ("min", "sorted")),
    ("open", "python", "Abre um fluxo de ficheiro com modo e encoding explícitos; deve normalmente ser usado num `with`.", "open(path, mode='r', encoding=None)", "with open(path, encoding='utf-8') as f: ...", ("with", "pathlib")),
    ("property", "python", "Expõe métodos de acesso através da sintaxe de atributo, preservando um contrato público.", "property(fget, fset=None)", "@property\ndef total(self): return self._total", ("descriptor", "class")),
    ("super", "python", "Continua a procura de métodos pela ordem de resolução da classe, permitindo cooperação entre classes.", "super().método(...)", "super().__init__()", ("inheritance", "MRO")),
    ("pathlib", "python", "Módulo da biblioteca padrão para manipular caminhos como objetos portáveis.", "Path(caminho)", "ficheiros = Path('.').glob('*.py')", ("open", "filesystem")),
    ("dataclass", "python", "Decorador que gera inicialização, representação e comparação para classes orientadas a dados.", "@dataclass", "@dataclass(frozen=True)\nclass Ponto: x: float", ("class", "typing")),
    ("decorator", "python", "Função que recebe um objeto definido e devolve o objeto usado no seu lugar.", "@decorador", "@cache\ndef calcular(x): ...", ("function", "closure")),
    ("iterator", "python", "Objeto que entrega um elemento de cada vez através de `__next__` e sinaliza o fim com `StopIteration`.", "iter(objeto); next(iterator)", "it = iter([1, 2])", ("iterable", "generator")),
    ("generator", "python", "Iterator criado por uma função com `yield` ou por uma expressão generator.", "(expressão for item in iterável)", "quadrados = (n*n for n in dados)", ("yield", "iterator")),
    ("recursão", "algorithms", "Técnica em que uma função resolve o problema usando instâncias menores do mesmo problema e um caso base.", "T(n) = T(n-1) + custo", "def f(n): return 1 if n <= 1 else n*f(n-1)", ("stack", "dynamic programming")),
    ("complexidade temporal", "algorithms", "Descrição do crescimento do número de operações em função do tamanho da entrada.", "O(f(n))", "pesquisa binária: O(log n)", ("Big-O", "complexidade espacial")),
    ("pesquisa binária", "algorithms", "Procura num domínio ordenado descartando metade do intervalo em cada passo.", "O(log n)", "meio = (inicio + fim) // 2", ("sorting", "invariant")),
    ("BFS", "algorithms", "Pesquisa em largura que visita um grafo por níveis usando uma fila.", "O(V+E)", "fila.append(origem)", ("DFS", "queue", "graph")),
    ("DFS", "algorithms", "Pesquisa em profundidade que explora um ramo antes de regressar, com pilha explícita ou recursão.", "O(V+E)", "pilha = [origem]", ("BFS", "stack", "graph")),
    ("programação dinâmica", "algorithms", "Resolve subproblemas sobrepostos uma vez e reutiliza os resultados.", "estado + transição + caso base", "dp[i] = min(dp[i-1], dp[i-2]) + custo[i]", ("memoization", "recursão")),
    ("produto interno", "mathematics", "Soma dos produtos entre componentes correspondentes de dois vetores.", "x·w = Σᵢxᵢwᵢ", "score = sum(a*b for a,b in zip(x,w))", ("vetor", "cosine similarity")),
    ("derivada", "mathematics", "Taxa de variação local de uma função relativamente a uma variável.", "f′(x)=limₕ→0 [f(x+h)−f(x)]/h", "d(x²)/dx = 2x", ("gradiente", "regra da cadeia")),
    ("regra da cadeia", "mathematics", "Calcula a derivada de uma composição multiplicando derivadas locais.", "d f(g(x))/dx = f′(g(x))g′(x)", "backpropagation", ("derivada", "backpropagation")),
    ("variância", "statistics", "Média do quadrado dos desvios face à média, usada para quantificar dispersão.", "Var(X)=E[(X−μ)²]", "statistics.pvariance(valores)", ("média", "desvio padrão")),
    ("desvio padrão", "statistics", "Raiz quadrada da variância, expressa na mesma unidade dos dados.", "σ=√Var(X)", "statistics.pstdev(valores)", ("variância", "distribuição")),
    ("precisão", "machine-learning", "Proporção das previsões positivas que são realmente positivas.", "precision=TP/(TP+FP)", "avaliar falsos positivos", ("recall", "F1")),
    ("recall", "machine-learning", "Proporção dos positivos reais que o modelo conseguiu detetar.", "recall=TP/(TP+FN)", "avaliar falsos negativos", ("precisão", "sensibilidade", "F1")),
    ("F1", "machine-learning", "Média harmónica entre precisão e recall, útil quando ambos importam.", "F1=2PR/(P+R)", "f1_score(y_true, y_pred)", ("precisão", "recall")),
    ("cross-validation", "machine-learning", "Avaliação repetida em folds que estima desempenho e variação fora da amostra.", "K folds", "cross_val_score(modelo, X, y, cv=5)", ("train/test split", "data leakage")),
    ("data leakage", "machine-learning", "Uso acidental de informação indisponível no momento real da previsão.", "treino não pode observar validação/futuro", "ajustar scaler apenas no treino", ("cross-validation", "pipeline")),
    ("regularização", "machine-learning", "Restrição ou penalização que reduz soluções excessivamente ajustadas ao treino.", "L_total=L_dados+λR(θ)", "L2: λ||θ||²", ("overfitting", "loss")),
    ("feedforward", "deep-learning", "Passagem das entradas pelas camadas até à previsão, sem calcular ainda os gradientes.", "aˡ=φ(Wˡaˡ⁻¹+bˡ)", "previsão = modelo(x)", ("backpropagation", "rede neuronal")),
    ("ReLU", "deep-learning", "Ativação que mantém valores positivos e substitui negativos por zero.", "ReLU(x)=max(0,x)", "torch.relu(x)", ("activation", "sigmoid")),
    ("softmax", "deep-learning", "Transforma logits num vetor positivo que soma um, sensível a diferenças relativas.", "softmax(zᵢ)=exp(zᵢ)/Σⱼexp(zⱼ)", "probabilidades de classes", ("logit", "cross-entropy")),
    ("CNN", "deep-learning", "Rede que aplica filtros partilhados localmente, muito usada em dados espaciais.", "feature=input*kernel", "Conv2D(canais, filtros, kernel)", ("convolução", "computer vision")),
    ("RNN", "deep-learning", "Rede que atualiza um estado oculto ao percorrer uma sequência.", "hₜ=f(xₜ,hₜ₋₁)", "sequência → estados", ("LSTM", "sequence")),
    ("LSTM", "deep-learning", "RNN com portas que regulam escrita, esquecimento e leitura de memória.", "cₜ=fₜcₜ₋₁+iₜgₜ", "Long Short-Term Memory", ("RNN", "GRU")),
    ("RAG", "artificial-intelligence", "Arquitetura que recupera evidência antes de sintetizar uma resposta condicionada.", "pergunta → retrieval → contexto → síntese", "citar chunks recuperados", ("embedding", "information retrieval")),
    ("ReAct", "artificial-intelligence", "Padrão de agente que intercala raciocínio operacional, ação e nova observação.", "reason → act → observe", "usar ferramenta e verificar resultado", ("agente", "tool use", "Reflexion")),
    ("IoU", "computer-vision", "Razão entre interseção e união de duas regiões, usada em deteção e segmentação.", "IoU=|A∩B|/|A∪B|", "comparar máscara prevista e real", ("segmentação", "object detection")),
    ("Django model", "django", "Classe que declara dados persistentes, relações e regras de acesso através do ORM do Django.", "class Modelo(models.Model): ...", "class Artigo(models.Model):\n    titulo = models.CharField(max_length=200)", ("migration", "QuerySet", "ORM")),
    ("Django view", "django", "Função ou classe que recebe um pedido HTTP e produz uma resposta, normalmente coordenando domínio e apresentação.", "view(request, ...) -> response", "def detalhe(request, pk): ...", ("URLconf", "template", "HTTP")),
    ("Django template", "django", "Documento de apresentação que combina marcação com variáveis e tags limitadas, mantendo a lógica de negócio fora da vista.", "{% tag %} {{ variável }}", "<h1>{{ artigo.titulo }}</h1>", ("Django view", "context", "HTML")),
    ("Django migration", "django", "Transformação versionada do esquema que mantém a base de dados alinhada com o estado dos modelos.", "python manage.py migrate", "python manage.py makemigrations", ("Django model", "schema", "transaction")),
    ("QuerySet", "django", "Representação preguiçosa e combinável de uma consulta a objetos do ORM do Django.", "Modelo.objects.filter(...)", "ativos = Utilizador.objects.filter(ativo=True)", ("Django model", "ORM", "lazy evaluation")),
    ("path operation", "fastapi", "Combinação de caminho, método HTTP e função que implementa uma operação de API em FastAPI.", "@app.get('/recurso')", "@app.post('/itens')\ndef criar(item: Item): ...", ("HTTP", "OpenAPI", "response model")),
    ("dependency injection", "fastapi", "Mecanismo que resolve e fornece dependências declaradas, permitindo composição, testes e controlo do ciclo de vida.", "Depends(dependência)", "user = Depends(utilizador_atual)", ("path operation", "inversion of control", "fixture")),
    ("response model", "fastapi", "Contrato tipado usado para validar, documentar e filtrar os dados devolvidos por uma operação.", "response_model=Tipo", "@app.get('/itens', response_model=list[Item])", ("Pydantic", "OpenAPI", "schema")),
    ("OpenAPI", "web", "Especificação independente de linguagem para descrever operações, parâmetros, respostas e esquemas de uma API HTTP.", "openapi.json", "GET /itens -> 200: Item[]", ("HTTP", "JSON Schema", "path operation")),
    ("Flask blueprint", "flask", "Conjunto reutilizável de rotas e configuração que ajuda a decompor uma aplicação Flask.", "Blueprint(nome, __name__)", "api = Blueprint('api', __name__)", ("routing", "application factory", "Flask")),
    ("application context", "flask", "Contexto que torna disponíveis recursos associados à aplicação ativa durante uma operação.", "with app.app_context():", "with app.app_context(): inicializar_bd()", ("request context", "current_app", "lifecycle")),
    ("request context", "flask", "Contexto criado para um pedido e que expõe proxies como request e session apenas durante esse ciclo.", "with app.test_request_context(...):", "metodo = request.method", ("application context", "HTTP", "session")),
    ("SQLAlchemy Engine", "sqlalchemy", "Fábrica de conexões e ponto de entrada para executar operações contra uma base de dados configurada.", "create_engine(url)", "engine = create_engine('sqlite:///app.db')", ("connection pool", "transaction", "Session")),
    ("SQLAlchemy Session", "sqlalchemy", "Unidade de trabalho que acompanha objetos persistentes e coordena consultas, flush, commit e rollback.", "Session(engine)", "with Session(engine) as session: ...", ("Unit of Work", "ORM", "transaction")),
    ("Unit of Work", "software-engineering", "Padrão que acompanha alterações relacionadas e as confirma ou reverte como uma unidade consistente.", "begin → mutate → commit/rollback", "with session.begin(): guardar(pedido)", ("transaction", "SQLAlchemy Session", "repository")),
    ("declarative mapping", "sqlalchemy", "Forma de associar classes Python a tabelas e colunas através de metadata declarada.", "class Entidade(Base): ...", "id: Mapped[int] = mapped_column(primary_key=True)", ("ORM", "metadata", "SQLAlchemy Session")),
    ("pytest fixture", "pytest", "Função declarativa que prepara uma dependência de teste e pode controlar o seu âmbito e limpeza.", "@pytest.fixture", "def cliente(app): return app.test_client()", ("dependency injection", "test isolation", "pytest")),
    ("pytest parametrization", "pytest", "Execução do mesmo teste com casos de entrada e resultados esperados distintos.", "@pytest.mark.parametrize(...)", "@pytest.mark.parametrize('n,par', [(2, True), (3, False)])", ("test case", "boundary value", "pytest")),
    ("assertion introspection", "pytest", "Análise que o pytest faz de uma expressão assert para explicar valores e diferenças quando esta falha.", "assert obtido == esperado", "assert resultado.total == 3", ("assert", "diagnostic", "pytest")),
    ("MongoDB document", "mongodb", "Registo BSON com campos e valores aninháveis, armazenado dentro de uma coleção.", "{campo: valor}", "{'nome': 'Ada', 'skills': ['Python']}", ("collection", "BSON", "schema design")),
    ("aggregation pipeline", "mongodb", "Sequência ordenada de etapas que filtra, transforma, agrupa ou combina documentos.", "[{$match: ...}, {$group: ...}]", "db.vendas.aggregate(pipeline)", ("MongoDB document", "index", "query")),
    ("replica set", "mongodb", "Grupo de processos que mantém cópias do mesmo conjunto de dados para redundância e eleição de primário.", "primary + secondary nodes", "rs.status()", ("availability", "consistency", "failover")),
    ("sharding", "databases", "Particionamento horizontal que distribui dados e carga por vários nós segundo uma chave escolhida.", "shard key → partitions", "distribuir eventos por tenant e intervalo", ("partitioning", "replica set", "scalability")),
    ("Git commit", "git", "Snapshot identificado do conteúdo versionado, acompanhado por pais e metadados de autoria.", "git commit", "git commit -m 'Adiciona validação'", ("Git branch", "repository", "staging area")),
    ("Git branch", "git", "Nome móvel que aponta para um commit e permite desenvolver uma linha de histórico independente.", "git switch -c nome", "git switch -c feature/pesquisa", ("Git commit", "merge", "rebase")),
    ("Git merge", "git", "Integra histórias divergentes, criando quando necessário um commit com mais de um pai.", "git merge ramo", "git merge feature/pesquisa", ("Git branch", "merge conflict", "rebase")),
    ("Git rebase", "git", "Reaplica commits sobre uma nova base, reescrevendo os identificadores dessa linha de história.", "git rebase base", "git rebase main", ("Git commit", "Git merge", "history rewrite")),
    ("working tree", "git", "Conjunto de ficheiros atualmente materializados para edição, que pode divergir do índice e do último commit.", "git status", "editar → stage → commit", ("staging area", "Git commit", "repository")),
    ("Docker image", "docker", "Artefacto imutável por camadas que contém filesystem, configuração e metadados para iniciar contentores.", "docker build -t nome .", "docker image inspect nome", ("Docker container", "Dockerfile", "layer")),
    ("Docker container", "docker", "Processo isolado iniciado a partir de uma imagem, com filesystem gravável e recursos configurados.", "docker run imagem", "docker run --rm app:test", ("Docker image", "volume", "namespace")),
    ("Dockerfile", "docker", "Receita declarativa e ordenada para construir as camadas e a configuração de uma imagem.", "FROM ...\nRUN ...\nCMD ...", "FROM python:3.12-slim", ("Docker image", "build context", "layer")),
    ("Docker volume", "docker", "Armazenamento gerido fora da camada gravável do contentor para preservar ou partilhar dados.", "docker volume create nome", "docker run -v dados:/app/data imagem", ("Docker container", "persistence", "bind mount")),
    ("container registry", "docker", "Serviço que armazena e distribui imagens identificadas por repositório e tag ou digest.", "registry/repo:tag", "docker pull exemplo/app@sha256:...", ("Docker image", "digest", "supply chain")),
    ("wheel", "python-packaging", "Formato binário de distribuição Python que pode ser instalado sem executar um processo de build no destino.", "*.whl", "python -m pip install pacote.whl", ("sdist", "pyproject.toml", "distribution package")),
    ("sdist", "python-packaging", "Arquivo de distribuição de código-fonte que contém os elementos necessários para construir um pacote.", "*.tar.gz", "python -m build --sdist", ("wheel", "build backend", "pyproject.toml")),
    ("pyproject.toml", "python-packaging", "Ficheiro padrão para declarar sistema de build e configuração de ferramentas e projeto Python.", "[build-system] / [project]", "[project]\nname = 'exemplo'", ("wheel", "build backend", "dependency")),
    ("virtual environment", "python-packaging", "Ambiente isolado que possui o seu próprio contexto de instalação de pacotes Python.", "python -m venv .venv", ".venv\\Scripts\\python -m pip install -r requirements.txt", ("dependency", "pip", "reproducibility")),
    ("coroutine", "asyncio", "Função assíncrona suspensível ou o objeto aguardável produzido quando essa função é chamada.", "async def operação(): ...", "resultado = await operação()", ("await", "asyncio Task", "event loop")),
    ("asyncio Task", "asyncio", "Agendamento de uma coroutine no event loop que guarda o seu estado, resultado e cancelamento.", "asyncio.create_task(coro())", "tarefas = [asyncio.create_task(f(x)) for x in dados]", ("coroutine", "event loop", "cancellation")),
    ("event loop", "asyncio", "Coordenador que avança tarefas cooperativas quando operações aguardáveis ficam prontas.", "asyncio.run(main())", "asyncio.run(processar())", ("coroutine", "asyncio Task", "I/O concurrency")),
    ("awaitable", "asyncio", "Objeto que pode aparecer numa expressão await e produzir um resultado após eventual suspensão.", "await objeto", "dados = await fila.get()", ("coroutine", "Future", "event loop")),
)


# Canonical term followed by common Portuguese/English names, acronyms and
# spellings. Aliases only improve retrieval; they never duplicate or replace
# the reviewed definition of the canonical entry.
GLOSSARY_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("print", ("imprimir", "mostrar output", "output function")),
    ("len", ("comprimento", "tamanho", "length")),
    ("range", ("intervalo inteiro", "integer range")),
    ("list", ("lista", "array dinâmico", "python list")),
    ("dict", ("dicionário", "dictionary", "mapa", "mapping")),
    ("set", ("conjunto", "hash set")),
    ("tuple", ("tuplo", "immutable sequence")),
    ("def", ("definir função", "function definition", "função")),
    ("return", ("retornar", "devolver valor", "function return")),
    ("class", ("classe", "POO", "OOP", "object oriented programming")),
    ("method", ("método", "instance method")),
    ("invariant", ("invariante", "class invariant")),
    ("exception", ("exceção", "erro Python", "Python error")),
    ("SELECT", ("consulta SQL", "query select", "selecionar linhas")),
    ("JOIN", ("junção SQL", "combinar tabelas", "SQL join")),
    ("index", ("índice SQL", "database index", "índice de base de dados")),
    ("transaction", ("transação", "transação ACID", "database transaction")),
    ("NoSQL", ("base não relacional", "non relational database", "not only SQL")),
    ("Django", ("Django framework", "framework web Python")),
    ("FastAPI", ("Fast API", "API Python tipada")),
    ("Flask", ("Flask framework", "microframework Python")),
    ("NumPy", ("numpy array", "numerical Python")),
    ("pandas", ("DataFrame", "dados tabulares Python")),
    ("JavaScript", ("JS", "ECMAScript")),
    ("Bootstrap", ("Bootstrap CSS", "CSS framework")),
    ("recursão", ("recursion", "função recursiva")),
    ("complexidade temporal", ("time complexity", "custo temporal")),
    ("pesquisa binária", ("binary search", "busca binária")),
    ("BFS", ("breadth first search", "pesquisa em largura")),
    ("DFS", ("depth first search", "pesquisa em profundidade")),
    ("programação dinâmica", ("dynamic programming", "DP", "memoização tabulação")),
    ("produto interno", ("dot product", "inner product", "produto escalar")),
    ("derivada", ("derivative", "taxa de variação")),
    ("regra da cadeia", ("chain rule", "derivada de composição")),
    ("variância", ("variance", "dispersão quadrática")),
    ("desvio padrão", ("standard deviation", "sigma estatístico")),
    ("precisão", ("precision metric", "valor preditivo positivo")),
    ("recall", ("sensibilidade", "revocação", "true positive rate")),
    ("F1", ("F1 score", "F-score")),
    ("cross-validation", ("validação cruzada", "k-fold")),
    ("data leakage", ("fuga de dados", "information leakage")),
    ("regularização", ("regularization", "penalização do modelo")),
    ("feedforward", ("forward pass", "propagação direta")),
    ("ReLU", ("rectified linear unit", "unidade linear retificada")),
    ("CNN", ("convolutional neural network", "rede neuronal convolucional")),
    ("RNN", ("recurrent neural network", "rede neuronal recorrente")),
    ("RAG", ("retrieval augmented generation", "geração aumentada por recuperação")),
    ("ReAct", ("reason and act", "raciocinar e agir")),
    ("IoU", ("intersection over union", "interseção sobre união")),
    ("Django model", ("modelo Django", "ORM model")),
    ("Django view", ("view Django", "vista Django")),
    ("Django migration", ("migração Django", "schema migration Django")),
    ("QuerySet", ("consulta ORM Django", "Django query set")),
    ("dependency injection", ("injeção de dependências", "DI")),
    ("path operation", ("operação de rota", "FastAPI route")),
    ("SQLAlchemy Engine", ("engine SQLAlchemy", "motor de conexão")),
    ("SQLAlchemy Session", ("sessão SQLAlchemy", "ORM session")),
    ("Unit of Work", ("unidade de trabalho", "UoW")),
    ("pytest fixture", ("fixture pytest", "test fixture")),
    ("pytest parametrization", ("parametrização pytest", "parameterized test")),
    ("MongoDB document", ("documento MongoDB", "BSON document")),
    ("aggregation pipeline", ("pipeline de agregação", "MongoDB aggregate")),
    ("Git commit", ("commit Git", "snapshot Git")),
    ("Git branch", ("branch Git", "ramo Git")),
    ("Git merge", ("merge Git", "fusão de ramos")),
    ("Git rebase", ("rebase Git", "reaplicar commits")),
    ("working tree", ("árvore de trabalho", "working directory Git")),
    ("Docker image", ("imagem Docker", "container image")),
    ("Docker container", ("contentor Docker", "contêiner Docker")),
    ("Dockerfile", ("ficheiro Docker", "container build recipe")),
    ("Docker volume", ("volume Docker", "persistent container storage")),
    ("container registry", ("registo de imagens", "Docker registry")),
    ("wheel", ("Python wheel", "bdist wheel", "WHL")),
    ("sdist", ("source distribution", "distribuição de código fonte")),
    ("pyproject.toml", ("pyproject", "configuração de projeto Python")),
    ("virtual environment", ("ambiente virtual", "virtualenv", "venv")),
    ("coroutine", ("corrotina", "async function")),
    ("asyncio Task", ("tarefa asyncio", "async task")),
    ("event loop", ("ciclo de eventos", "asyncio loop")),
    ("awaitable", ("aguardável", "objeto awaitable")),
)
