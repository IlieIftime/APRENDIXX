"""Original advanced card bank with deterministic breadth and provenance.

Only compact technical assertions authored for Aprendix live here.  Source IDs
point to approved bibliography metadata; no source prose or figures are copied.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class FactFactory(Protocol):
    def __call__(
        self,
        slug: str,
        area_id: str,
        fact: str,
        explanation: str,
        formula_or_code: str = "",
        complexity: str = "beginner",
        source_ids: tuple[str, ...] = (),
        card_format: str = "concept",
        visual_hint: str = "",
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class ConceptSeed:
    name: str
    mechanism: str
    expression: str
    boundary: str


@dataclass(frozen=True, slots=True)
class AreaSeed:
    title: str
    sources: tuple[str, ...]
    concepts: tuple[ConceptSeed, ...]


def _c(name: str, mechanism: str, expression: str, boundary: str) -> ConceptSeed:
    return ConceptSeed(name, mechanism, expression, boundary)


AREA_SEEDS: dict[str, AreaSeed] = {
    "prog-foundations": AreaSeed("Fundamentos de programação", ("src-python-docs", "src-pytest"), (
        _c("contrato observável", "separa entradas válidas, saída e falhas", "entrada → transformação → saída", "uma saída plausível não prova todos os ramos"),
        _c("estado explícito", "atribui nomes a valores cuja mudança pode ser seguida", "estado_novo = transição(estado, evento)", "efeitos ocultos tornam o diagnóstico ambíguo"),
        _c("controlo de fluxo", "escolhe ramos e repetições por condições verificáveis", "if condição: ramo_a else: ramo_b", "fronteiras como zero e vazio exigem testes próprios"),
        _c("decomposição", "divide uma tarefa em funções pequenas com uma responsabilidade", "resultado = etapa_b(etapa_a(dados))", "fragmentar sem contrato apenas desloca complexidade"),
    )),
    "python": AreaSeed("Python avançado", ("src-python-docs", "src-fluent-python"), (
        _c("protocolo de iteração", "iter produz um iterator e next avança até StopIteration", "iter(objeto); next(iterator)", "materializar tudo elimina a vantagem de execução preguiçosa"),
        _c("descritores", "controlam acesso a atributos através de __get__, __set__ e __delete__", "descritor.__get__(instância, tipo)", "precedência entre descritores e __dict__ altera o resultado"),
        _c("context managers", "emparelham aquisição e libertação mesmo perante exceções", "with recurso as valor: ...", "__exit__ só suprime uma exceção quando devolve verdadeiro"),
        _c("concorrência cooperativa", "coroutines cedem controlo nos pontos await", "resultado = await operação()", "código de CPU sem await bloqueia o event loop"),
    )),
    "oop": AreaSeed("Programação orientada a objetos", ("src-fluent-python", "src-python-docs"), (
        _c("invariante", "define uma condição preservada por todas as operações públicas", "estado_válido antes ∧ operação ⇒ estado_válido depois", "validar depois de alterar pode deixar estado parcial"),
        _c("composição", "delega responsabilidades a colaboradores com contratos estreitos", "serviço = Serviço(repositório, relógio)", "uma hierarquia profunda acopla comportamentos não usados"),
        _c("polimorfismo", "aceita objetos pelo comportamento necessário e não pela origem nominal", "processar(item: Protocolo)", "testar tipo concreto reduz extensibilidade"),
        _c("objeto-valor", "representa uma grandeza por conteúdo e pode ser imutável", "Dinheiro(valor, moeda)", "identidade e igualdade precisam de semânticas distintas"),
    )),
    "data-structures": AreaSeed("Estruturas de dados", ("src-clrs", "src-python-docs"), (
        _c("tabela de dispersão", "mapeia um hash para posições e confirma igualdade em colisões", "índice = hash(chave) mod capacidade", "hash adversarial ou elevada ocupação degrada operações"),
        _c("heap", "mantém o menor ou maior elemento na raiz com custo logarítmico", "pai(i)=(i-1)//2", "um heap não mantém todos os elementos globalmente ordenados"),
        _c("árvore balanceada", "limita altura para manter procura e atualização logarítmicas", "altura ∈ O(log n)", "inserções ordenadas quebram uma árvore não balanceada"),
        _c("grafo", "modela entidades e relações por vértices e arestas", "G=(V,E)", "matriz e lista de adjacência têm custos distintos em grafos esparsos"),
    )),
    "classic-algorithms": AreaSeed("Algoritmos clássicos", ("src-clrs",), (
        _c("divide and conquer", "resolve partes menores e combina resultados", "T(n)=aT(n/b)+f(n)", "a combinação pode dominar o custo das subsoluções"),
        _c("programação dinâmica", "guarda subproblemas sobrepostos definidos por estado e transição", "dp[estado]=melhor(transições)", "um estado incompleto mistura problemas diferentes"),
        _c("algoritmo guloso", "escolhe uma opção local apoiada por uma propriedade de troca", "solução += melhor_opção_viável", "uma escolha intuitiva não basta sem prova ou contraexemplo"),
        _c("amortização", "distribui operações raras caras por uma sequência de operações", "custo_amortizado = custo_total / operações", "o pior caso de uma operação individual continua possível"),
    )),
    "software-engineering": AreaSeed("Engenharia de software", ("src-pytest", "src-git", "src-docker"), (
        _c("teste de contrato", "fixa comportamento público sem depender da implementação interna", "dado → quando → então", "mocks excessivos podem testar apenas a própria configuração"),
        _c("integração contínua", "repete build, análise e testes num ambiente limpo", "commit → build → gates → artefacto", "um pipeline verde não cobre requisitos nunca testados"),
        _c("versionamento semântico", "comunica compatibilidade por major, minor e patch", "MAJOR.MINOR.PATCH", "alterações de dados podem quebrar mesmo sem mudar uma API"),
        _c("observabilidade", "correlaciona logs, métricas e traces com contexto mínimo", "evento + identidade + tempo + resultado", "registar segredos transforma diagnóstico em incidente"),
    )),
    "databases": AreaSeed("Bases de dados", ("src-postgresql", "src-sqlalchemy"), (
        _c("isolamento", "controla quais escritas concorrentes uma transação consegue observar", "BEGIN … COMMIT", "transações longas aumentam contenção e versões retidas"),
        _c("índice composto", "ordena várias colunas para servir filtros e ordenações específicas", "INDEX(a,b)", "a ordem das colunas determina os prefixos aproveitáveis"),
        _c("normalização", "separa factos para reduzir anomalias de atualização", "dependência funcional X → Y", "desnormalizar sem medição cria duplicação difícil de reconciliar"),
        _c("plano de execução", "transforma SQL num conjunto de operadores físicos", "scan → join → aggregate", "estimativas de cardinalidade erradas propagam escolhas caras"),
    )),
    "web": AreaSeed("Engenharia Web", ("src-mdn", "src-fastapi", "src-django"), (
        _c("semântica HTTP", "distingue método, recurso, representação e código de estado", "método + URI + headers + body", "repetir uma escrita não idempotente pode duplicar efeitos"),
        _c("cache validation", "usa validadores para confirmar se uma representação mudou", "If-None-Match: ETag", "cachear resposta privada sem chave correta expõe dados"),
        _c("acessibilidade", "expõe nome, papel, estado e ordem de foco compreensíveis", "HTML semântico + teclado + contraste", "ARIA não corrige um controlo nativo mal escolhido"),
        _c("segurança de origem", "separa origens por esquema, host e porta", "origin=(scheme,host,port)", "CORS é política do browser e não autenticação do servidor"),
    )),
    "systems": AreaSeed("Sistemas e concorrência", ("src-python-asyncio", "src-docker", "src-python-docs"), (
        _c("condição de corrida", "faz o resultado depender da ordem imprevisível de acessos partilhados", "read → modify → write", "um teste repetidamente verde não prova ausência de interleavings"),
        _c("backpressure", "impede produtores de excederem consumidores e memória disponível", "taxa_entrada ≤ capacidade_consumo", "uma fila ilimitada apenas adia a falha"),
        _c("deadlock", "forma um ciclo de espera por recursos que nunca é resolvido", "A espera B ∧ B espera A", "adquirir locks numa ordem global reduz ciclos"),
        _c("isolamento de processo", "limita memória, permissões e efeitos de uma execução", "processo + limites + allowlist", "isolamento lógico no mesmo processo não contém código hostil"),
    )),
    "linear-algebra": AreaSeed("Álgebra linear", ("src-numpy", "src-dlbook"), (
        _c("produto interno", "soma produtos componente a componente e mede alinhamento", "x·w=Σᵢxᵢwᵢ", "a similaridade de cosseno exige normalização das normas"),
        _c("transformação linear", "preserva soma e multiplicação por escalar", "A(αx+βy)=αAx+βAy", "uma translação com bias é afim, não linear"),
        _c("valores singulares", "decompõem uma matriz em direções ortogonais e escalas", "A=UΣVᵀ", "valores muito pequenos indicam direções numericamente frágeis"),
        _c("projeção", "decompõe um vetor numa componente dentro de um subespaço", "projᵤ(x)=u(uᵀx)/(uᵀu)", "uma base não ortogonal exige resolver coeficientes acoplados"),
        _c("condicionamento", "mede a amplificação de perturbações pela operação", "κ(A)=||A||·||A⁻¹||", "mais precisão numérica não corrige um modelo mal condicionado"),
        _c("broadcasting", "alinha dimensões compatíveis sem copiar conceptualmente cada valor", "(n,1)+(1,m)→(n,m)", "formas compatíveis podem ainda representar uma operação sem sentido"),
    )),
    "calculus": AreaSeed("Cálculo", ("src-dlbook", "src-probml", "src-pytorch-autograd"), (
        _c("derivada", "mede a variação local no limite de uma perturbação", "f′(x)=limₕ→0[f(x+h)-f(x)]/h", "não diferenciabilidade exige subgradiente ou outra formulação"),
        _c("regra da cadeia", "compõe derivadas locais ao longo de dependências", "∂L/∂x=(∂L/∂y)(∂y/∂x)", "gradientes podem desaparecer ou explodir em composições longas"),
        _c("gradiente", "reúne derivadas parciais na direção de maior subida local", "∇f=[∂f/∂x₁,…,∂f/∂xₙ]", "a direção local não garante um ótimo global"),
        _c("Hessiana", "descreve curvatura por derivadas parciais de segunda ordem", "Hᵢⱼ=∂²f/∂xᵢ∂xⱼ", "armazenar a matriz completa é caro em alta dimensão"),
        _c("integração numérica", "aproxima acumulação por avaliações discretas", "∫f(x)dx≈Σ f(xᵢ)Δx", "passos largos perdem variação entre amostras"),
        _c("diferenciação automática", "aplica regras exatas a um grafo de operações", "valor forward + adjunto backward", "não é diferenciação simbólica nem diferença finita"),
    )),
    "probability": AreaSeed("Probabilidade", ("src-probml",), (
        _c("condicionamento", "atualiza o espaço de resultados depois de observar evidência", "P(A|B)=P(A∩B)/P(B)", "condicionar num evento de probabilidade zero exige outro tratamento"),
        _c("Bayes", "combina prior e verosimilhança numa posterior normalizada", "P(H|D)=P(D|H)P(H)/P(D)", "uma prior demasiado rígida domina poucos dados"),
        _c("esperança", "é a média ponderada pela distribuição e não o resultado mais provável", "E[X]=ΣₓxP(X=x)", "a esperança pode não ser um valor possível da variável"),
        _c("variância", "mede dispersão quadrática em torno da esperança", "Var(X)=E[X²]-E[X]²", "outliers recebem peso quadrático"),
        _c("independência condicional", "remove uma dependência depois de conhecido um terceiro evento", "X ⟂ Y | Z", "independência marginal e condicional não são equivalentes"),
        _c("Monte Carlo", "aproxima expectativas por amostras da distribuição", "Ê[f(X)]=(1/N)Σf(xᵢ)", "amostras correlacionadas reduzem a dimensão efetiva"),
    )),
    "optimization": AreaSeed("Otimização", ("src-dlbook", "src-sklearn"), (
        _c("descida do gradiente", "move parâmetros contra a inclinação local", "θ←θ-η∇L(θ)", "uma taxa grande ultrapassa vales e uma pequena converge lentamente"),
        _c("momentum", "acumula uma direção suavizada para atravessar curvatura desigual", "v←βv+(1-β)g; θ←θ-ηv", "momentum elevado pode oscilar sem amortecimento suficiente"),
        _c("restrição", "limita a região admissível ou adiciona uma penalização", "min L(θ) sujeito a g(θ)≤0", "penalização finita não garante sempre a restrição exata"),
        _c("convexidade", "faz qualquer mínimo local ser global no domínio convexo", "f(λx+(1-λ)y)≤λf(x)+(1-λ)f(y)", "redes profundas não satisfazem convexidade global"),
        _c("early stopping", "interrompe quando validação deixa de melhorar", "parar após patience épocas", "usar o teste para decidir a paragem contamina a avaliação"),
        _c("escala de features", "equilibra a geometria das direções de atualização", "z=(x-μ)/σ", "ajustar μ e σ fora do treino causa leakage"),
    )),
    "data-practice": AreaSeed("Prática de dados", ("src-pandas", "src-numpy", "src-sklearn"), (
        _c("contrato de esquema", "declara nomes, tipos, nulabilidade e domínios esperados", "schema(dados)=versão", "inferir tipos a cada execução torna falhas tardias"),
        _c("data leakage", "permite ao treino observar informação indisponível na previsão real", "fit apenas no treino", "normalizar antes do split já transmite estatísticas"),
        _c("proveniência", "regista origem, transformação, versão e hash de cada conjunto", "fonte → transformação → artefacto", "um nome de ficheiro não identifica conteúdo imutável"),
        _c("dados em falta", "distingue ausência, não aplicável e falha de medição", "máscara + valor + motivo", "preencher tudo com zero muda a distribuição e o significado"),
        _c("validação temporal", "respeita a ordem causal entre treino e avaliação", "treino[:t] → validação[t:t+h]", "baralhar séries temporais introduz informação futura"),
        _c("monitorização de drift", "compara distribuições e desempenho após deployment", "D(P_treino,P_atual)", "mudança de input não implica automaticamente perda de qualidade"),
    )),
    "ai-foundations": AreaSeed("Fundamentos de IA", ("src-aima",), (
        _c("estado de procura", "resume apenas informação necessária para ações futuras", "problema=(estado,ações,transição,custo,objetivo)", "um estado incompleto confunde trajetórias diferentes"),
        _c("heurística admissível", "nunca sobrestima o custo restante", "h(n)≤h*(n)", "admissibilidade não implica consistência em qualquer formulação"),
        _c("planeamento", "procura uma sequência de ações cujos efeitos satisfazem um objetivo", "estado′=resultado(estado,ação)", "efeitos não modelados invalidam o plano no ambiente real"),
        _c("decisão sob incerteza", "maximiza utilidade esperada em vez de certeza impossível", "a*=argmaxₐ E[U|a,e]", "probabilidades mal calibradas alteram a decisão ótima"),
    )),
    "probabilistic-ml": AreaSeed("Machine learning probabilístico", ("src-probml",), (
        _c("modelo generativo", "define uma distribuição conjunta sobre observações e latentes", "p(x,z)=p(z)p(x|z)", "identificabilidade fraca permite explicações equivalentes"),
        _c("máxima verosimilhança", "escolhe parâmetros que tornam os dados observados mais prováveis", "θ̂=argmaxθ Σ log p(xᵢ|θ)", "sem regularização pode sobreajustar conjuntos pequenos"),
        _c("MAP", "combina log-verosimilhança e log-prior numa estimativa pontual", "θ_MAP=argmaxθ [log p(D|θ)+log p(θ)]", "uma estimativa pontual esconde incerteza posterior"),
        _c("inferência variacional", "aproxima a posterior por uma família tratável", "min_q KL(q(z)||p(z|x))", "a família escolhida limita dependências representáveis"),
        _c("calibração", "alinha confiança prevista com frequência observada", "P(Y=1|p̂≈r)≈r", "boa discriminação não garante calibração"),
        _c("posterior preditiva", "integra previsões sobre a incerteza dos parâmetros", "p(y*|x*,D)=∫p(y*|x*,θ)p(θ|D)dθ", "plug-in no valor médio tende a subestimar incerteza"),
    )),
    "ensemble-learning": AreaSeed("Ensembles", ("src-esl", "src-sklearn"), (
        _c("bagging", "reduz variância agregando modelos treinados em amostras bootstrap", "ŷ=(1/M)Σfₘ(x)", "erros fortemente correlacionados limitam o ganho"),
        _c("random forest", "descorrelaciona árvores também amostrando features em cada divisão", "bootstrap + subespaço aleatório", "árvores rasas demais introduzem viés"),
        _c("boosting", "adiciona aprendizes que corrigem resíduos do conjunto atual", "Fₘ=Fₘ₋₁+ηhₘ", "muitas etapas ou η grande podem sobreajustar ruído"),
        _c("stacking", "aprende um meta-modelo sobre previsões fora do fold", "z=[f₁(x),…,fₘ(x)]", "usar previsões in-sample causa leakage no meta-modelo"),
        _c("votação calibrada", "combina probabilidades comparáveis e não apenas classes", "p=Σwₘpₘ/Σwₘ", "probabilidades não calibradas dão peso enganador"),
        _c("diversidade", "mede se modelos cometem erros diferentes nos mesmos exemplos", "ganho ∝ qualidade + diversidade", "adicionar cópias do mesmo modelo pouco altera o erro"),
    )),
    "deep-learning": AreaSeed("Deep learning", ("src-dlbook", "src-pytorch-autograd"), (
        _c("backpropagation", "propaga adjuntos pelo grafo computacional em ordem inversa", "∂L/∂w=(∂L/∂y)(∂y/∂w)", "gradientes acumulados exigem limpeza explícita entre batches"),
        _c("inicialização", "define a escala inicial para preservar variância entre camadas", "Var(w)≈2/fan_in", "pesos idênticos impedem quebra de simetria"),
        _c("normalização", "estabiliza estatísticas de ativações durante o treino", "x̂=(x-μ)/√(σ²+ε)", "estatísticas de treino e inferência podem divergir"),
        _c("regularização", "reduz dependência excessiva do conjunto de treino", "L_total=L_dados+λ||θ||²", "regularização forte também destrói sinal útil"),
        _c("função de ativação", "introduz não linearidade entre transformações afins", "a=φ(Wx+b)", "sem não linearidade várias camadas colapsam numa só transformação"),
        _c("batching", "estima o gradiente com subconjuntos vetorizados", "g≈(1/B)Σ∇ℓᵢ", "batches muito pequenos aumentam ruído e muito grandes exigem memória"),
    )),
    "convolutional-networks": AreaSeed("Redes convolucionais", ("src-resnet", "src-dlbook", "src-unet"), (
        _c("convolução", "partilha um kernel por posições espaciais", "y[i,j]=Σₐ,ᵦK[a,b]x[i+a,j+b]", "stride e padding alteram resolução e alinhamento"),
        _c("campo recetivo", "descreve a região de input que influencia uma ativação", "r_l=r_{l-1}+(k_l-1)j_{l-1}", "campo teórico grande não garante uso efetivo de toda a região"),
        _c("residual connection", "soma uma transformação ao caminho identidade", "y=F(x)+x", "formas incompatíveis exigem projeção no atalho"),
        _c("pooling", "agrega vizinhanças para reduzir resolução", "y=max(x_vizinhança)", "downsampling precoce pode apagar detalhes pequenos"),
        _c("encoder-decoder", "comprime contexto e recupera resolução para previsão densa", "features → bottleneck → mapa", "upsampling sem skip connections perde localização fina"),
        _c("augmentação", "aplica transformações que preservam o rótulo", "x′=T(x), y′=y", "uma transformação não plausível ensina invariâncias erradas"),
    )),
    "sequence-models": AreaSeed("Modelos sequenciais", ("src-dlbook", "src-attention"), (
        _c("estado recorrente", "resume o prefixo processado numa representação atualizada", "h_t=f(x_t,h_{t-1})", "compressão num único estado perde dependências longas"),
        _c("LSTM", "usa portas para controlar memória, escrita e exposição", "c_t=f_t⊙c_{t-1}+i_t⊙g_t", "portas saturadas reduzem gradientes úteis"),
        _c("teacher forcing", "usa o token real anterior durante treino autoregressivo", "p(y_t|y_{<t},x)", "na inferência o modelo observa os próprios erros acumulados"),
        _c("masking", "exclui padding ou futuro de operações sequenciais", "score + máscara → softmax", "uma máscara invertida permite fuga de informação"),
        _c("CTC", "soma alinhamentos possíveis entre sequência e rótulos", "p(y|x)=Σ_{π→y}p(π|x)", "independência condicional limita algumas dependências de output"),
        _c("decoding", "procura uma sequência provável sem enumerar todas", "beam top-k por passo", "beam maior aumenta custo e não garante melhor utilidade"),
    )),
    "transformers": AreaSeed("Transformers", ("src-attention", "src-vit"), (
        _c("self-attention", "mistura values segundo compatibilidade entre queries e keys", "softmax(QKᵀ/√d_k)V", "custo quadrático cresce com o comprimento da sequência"),
        _c("multi-head attention", "aprende projeções paralelas com subespaços diferentes", "Concat(head₁,…,head_h)Wᴼ", "mais heads com dimensão fixa tornam cada head menor"),
        _c("posição", "adiciona informação de ordem ausente no mecanismo de conjunto", "z_i=x_i+p_i", "extrapolar além do treino depende do esquema posicional"),
        _c("causal mask", "impede cada posição de observar tokens futuros", "M_{ij}=-∞ se j>i", "uma máscara errada torna a perplexidade artificialmente baixa"),
        _c("residual + norm", "mantém caminhos de gradiente em blocos empilhados", "x←x+subcamada(norm(x))", "pre-norm e post-norm têm dinâmica de treino diferente"),
        _c("KV cache", "reutiliza keys e values do prefixo durante geração", "cache_t=cache_{t-1}∪(K_t,V_t)", "memória cresce com contexto, layers e batch"),
    )),
    "generative-ai": AreaSeed("IA generativa", ("src-dlbook", "src-attention", "src-ai-index"), (
        _c("modelo autoregressivo", "fatora a sequência pelo produto de probabilidades condicionais", "p(x)=∏_t p(x_t|x_{<t})", "erro local acumula-se ao gerar sequências longas"),
        _c("VAE", "otimiza reconstrução e proximidade a uma prior latente", "ELBO=E_q[log p(x|z)]-KL(q(z|x)||p(z))", "peso excessivo no KL pode colapsar o latente"),
        _c("GAN", "opõe gerador e discriminador num jogo minimax", "min_G max_D E log D(x)+E log(1-D(G(z)))", "instabilidade e mode collapse exigem diagnóstico por diversidade"),
        _c("difusão", "aprende a inverter passos graduais de ruído", "x_t=√ᾱ_t x_0+√(1-ᾱ_t)ε", "mais passos melhoram aproximação mas aumentam latência"),
        _c("sampling", "transforma logits numa distribuição controlada por temperatura e truncagem", "p_i∝exp(z_i/T)", "temperatura baixa não torna uma afirmação factual"),
        _c("avaliação gerativa", "combina qualidade, cobertura, segurança e avaliação humana cega", "métrica = vetor, não número único", "uma métrica lexical penaliza paráfrases corretas"),
    )),
    "computer-vision": AreaSeed("Visão computacional", ("src-resnet", "src-vit", "src-unet"), (
        _c("IoU", "mede a sobreposição pela interseção dividida pela união", "IoU=|A∩B|/|A∪B|", "objetos pequenos sofrem grandes variações por poucos píxeis"),
        _c("non-maximum suppression", "remove caixas redundantes por score e sobreposição", "reter maior score; suprimir IoU>τ", "objetos próximos podem ser suprimidos indevidamente"),
        _c("segmentação", "atribui uma classe ou instância a cada píxel", "máscara ∈ classes^{H×W}", "accuracy global esconde classes pequenas"),
        _c("normalização de imagem", "alinha canais à escala esperada pelo modelo", "x′=(x-μ_c)/σ_c", "trocar RGB por BGR altera todas as features"),
        _c("patch embedding", "converte regiões de imagem numa sequência de vetores", "N=HW/P² tokens", "patches grandes perdem pormenor local"),
        _c("data augmentation", "simula variações visuais preservando o alvo", "(x,y)→(T(x),y)", "flip pode mudar rótulos com lateralidade"),
    )),
    "natural-language": AreaSeed("Processamento de linguagem natural", ("src-attention", "src-rag"), (
        _c("tokenização", "mapeia texto para subunidades e identificadores", "texto→tokens→ids", "espaços e Unicode podem mudar a segmentação"),
        _c("embedding contextual", "representa um token segundo a frase onde ocorre", "h_i=encoder(tokens)_i", "similaridade vetorial não prova equivalência factual"),
        _c("cross-entropy", "penaliza a probabilidade atribuída ao token correto", "L=-Σ_t log p(y_t|y_{<t},x)", "perplexidade baixa não mede utilidade ou segurança"),
        _c("retrieval augmented generation", "recupera evidência antes de sintetizar", "pergunta→retrieval→contexto→resposta", "recuperação irrelevante ancora uma resposta errada"),
        _c("entity recognition", "localiza spans e atribui tipos semânticos", "tokens→BIO tags→entidades", "fronteiras aninhadas exigem esquema apropriado"),
        _c("avaliação semântica", "combina correspondência, factualidade e cobertura por exemplo", "score=(correção,cobertura,fé à fonte)", "uma única referência pode admitir várias respostas corretas"),
    )),
    "reinforcement-learning": AreaSeed("Reinforcement learning", ("src-rlbook",), (
        _c("retorno", "acumula recompensas futuras com desconto", "G_t=Σ_{k≥0}γ^k R_{t+k+1}", "γ pequeno ignora consequências tardias"),
        _c("equação de Bellman", "decompõe valor em recompensa imediata e valor futuro", "Vπ(s)=Eπ[R+γVπ(S′)]", "aproximação e bootstrapping podem amplificar erro"),
        _c("Q-learning", "atualiza valor para uma ação usando o melhor próximo valor", "Q←Q+α[r+γ max_a Q(s′,a)-Q]", "off-policy com função não linear pode ser instável"),
        _c("policy gradient", "aumenta probabilidade de ações com vantagem positiva", "∇J=E[∇logπ(a|s)A(s,a)]", "alta variância exige baseline ou mais amostras"),
        _c("exploração", "recolhe informação sacrificando retorno imediato", "ε-greedy ou bônus de incerteza", "ε fixo continua ações aleatórias mesmo após convergência"),
        _c("offline RL", "aprende apenas de trajetórias já recolhidas", "D={(s,a,r,s′)} sem novas ações", "ações fora da distribuição têm valores extrapolados frágeis"),
    )),
    "agent-architectures": AreaSeed("Arquiteturas de agentes", ("src-react", "src-aima"), (
        _c("ciclo observar-agir", "atualiza a decisão depois de cada resultado do ambiente", "observar→planear→agir→verificar", "ignorar observações reais transforma o plano em ficção"),
        _c("contrato de ferramenta", "declara argumentos, autorização, efeito e resultado observável", "tool(input válido)→result|error", "texto bem formado não prova que a ação ocorreu"),
        _c("planeamento limitado", "impõe orçamento de passos, tempo e custo antes da execução", "while objetivo não atingido and budget>0", "um ciclo sem condição de paragem consome recursos indefinidamente"),
        _c("ReAct", "intercala decisão operacional, ferramenta e nova observação", "reason→act→observe", "raciocínio sem evidência pode propagar uma premissa errada"),
        _c("router", "seleciona uma capacidade por intenção, risco e confiança", "rota=argmax score(capacidade|pedido)", "roteamento confiante para ferramenta errada aumenta dano"),
        _c("verificador", "compara o resultado com critérios independentes do gerador", "resultado+critério→aceitar|rever", "autoavaliação com a mesma evidência partilha os mesmos vieses"),
    )),
    "agent-memory": AreaSeed("Memória de agentes", ("src-reflexion", "src-generative-agents", "src-rag"), (
        _c("memória episódica", "guarda experiências delimitadas por tempo, ação e resultado", "episódio=(contexto,ação,resultado)", "episódios sem resultado não ensinam eficácia"),
        _c("memória semântica", "consolida afirmações estáveis com fonte e confiança", "facto+fonte+versão+confiança", "resumos repetidos podem perder qualificações importantes"),
        _c("retrieval", "ordena memórias por relevância, recência e confiança", "score=w_rR+w_tT+w_cC", "recência excessiva elimina precedentes raros relevantes"),
        _c("esquecimento", "remove ou arquiva entradas redundantes, expiradas ou invalidadas", "TTL + superseded_by + revisão", "apagar sem trilho impede auditar decisões antigas"),
        _c("reflexão", "transforma falhas observadas numa regra testável para outra tentativa", "falha→causa→regra→novo teste", "uma narrativa plausível sem teste não é aprendizagem"),
        _c("isolamento por utilizador", "impede recuperação cruzada entre perfis locais", "chave=(user_id,memory_id)", "um índice global sem filtro vaza contexto privado"),
    )),
    "multi-agent": AreaSeed("Sistemas multiagente", ("src-generative-agents", "src-aima"), (
        _c("decomposição por papéis", "atribui responsabilidades não sobrepostas e entregas verificáveis", "tarefa→{papel:contrato}", "papéis vagos duplicam trabalho e omitem fronteiras"),
        _c("protocolo de mensagem", "define identidade, intenção, payload, versão e correlação", "message=(from,to,type,id,body)", "mensagens sem idempotência repetem efeitos"),
        _c("consenso", "escolhe um valor comum apesar de atrasos ou falhas admitidas", "propor→votar→confirmar", "maioria simples não resolve todos os modelos adversariais"),
        _c("agregação", "combina propostas segundo evidência e regra declarada", "resultado=agregar(propostas,evidência)", "votar sem verificar premissas multiplica o mesmo erro"),
        _c("coordenação", "ordena dependências e recursos partilhados entre agentes", "DAG de tarefas + locks limitados", "coordenação pode custar mais do que execução direta"),
        _c("contenção", "mede conflito por ferramentas, memória ou orçamento comuns", "utilização + espera + retries", "aumentar agentes sob recurso fixo reduz throughput"),
    )),
    "agent-evaluation": AreaSeed("Avaliação de agentes", ("src-react", "src-ai-index", "src-reflexion"), (
        _c("sucesso da tarefa", "verifica estado externo e critérios, não apenas resposta textual", "success=all(assertions(environment))", "uma afirmação de sucesso pode contradizer o ambiente"),
        _c("qualidade da trajetória", "mede passos inválidos, recuperação, custo e evidência", "trajetória→(sucesso,custo,risco,retries)", "avaliar só o último passo esconde ações perigosas"),
        _c("holdout", "reserva tarefas e variações nunca usadas no ajuste", "train ∩ holdout=∅", "templates quase idênticos permitem memorização indireta"),
        _c("intervenção humana", "regista quando e porquê foi necessária supervisão", "intervenções / tarefas", "taxa baixa não significa risco baixo se casos graves forem raros"),
        _c("robustez", "repete objetivos sob ruído, indisponibilidade e instruções ambíguas", "score médio + pior quantil", "a média esconde falhas catastróficas na cauda"),
        _c("reprodutibilidade", "fixa versões, seeds, ferramentas e snapshots do ambiente", "run_id→config+inputs+outputs", "serviços externos mutáveis impedem repetição exata"),
    )),
    "responsible-ai": AreaSeed("IA responsável", ("src-ai-index", "src-probml"), (
        _c("avaliação por subgrupo", "mede desempenho e incerteza em grupos relevantes", "métrica_g para cada g", "precisão global pode esconder dano concentrado"),
        _c("calibração", "compara confiança com frequência observada", "ECE=Σ_b |acc(b)-conf(b)|·|b|/n", "poucos exemplos tornam bins instáveis"),
        _c("model card", "documenta finalidade, dados, métricas, limites e uso proibido", "modelo+versão+contexto+limites", "documentação não substitui controlos de runtime"),
        _c("human oversight", "define decisões que exigem revisão e capacidade de reversão", "risco≥limiar→revisão", "um humano sem contexto apenas carimba a automação"),
    )),
    "finance-app": AreaSeed("Programação em finanças", ("src-esl", "src-probml"), (
        _c("backtest temporal", "treina apenas no passado e avalia períodos posteriores", "train<t_validate<t_test", "baralhar dados financeiros ensina o futuro"),
        _c("custos de transação", "subtrai spread, comissões e impacto de mercado", "retorno_líquido=bruto-custos", "uma vantagem pequena desaparece com turnover elevado"),
        _c("drawdown", "mede a queda desde o máximo acumulado", "DD_t=1-V_t/max_{u≤t}V_u", "retorno médio não revela profundidade das perdas"),
        _c("survivorship bias", "inclui entidades que desapareceram do universo histórico", "universo_t conforme existia em t", "usar constituintes atuais melhora artificialmente o passado"),
    )),
    "health-app": AreaSeed("Computação em saúde", ("src-unet", "src-probml"), (
        _c("sensibilidade", "mede positivos reais detetados", "TP/(TP+FN)", "um limiar escolhido sem custo clínico é arbitrário"),
        _c("especificidade", "mede negativos reais rejeitados", "TN/(TN+FP)", "prevalência diferente altera valores preditivos"),
        _c("validação externa", "testa noutra instituição, período ou população", "treino_A→teste_B", "split interno não mede mudança de protocolo"),
        _c("rastreabilidade", "liga cada resultado a modelo, input, versão e revisão", "prediction_id→proveniência completa", "guardar apenas a classe impede auditoria posterior"),
    )),
    "robotics-app": AreaSeed("Robótica", ("src-aima", "src-rlbook"), (
        _c("fusão sensorial", "combina medições segundo ruído e dinâmica", "posterior∝likelihood×prior", "sensores correlacionados não podem ser tratados como independentes"),
        _c("PID", "combina erro atual, acumulado e derivada", "u=K_p e+K_i∫e dt+K_d de/dt", "saturação sem anti-windup acumula integral"),
        _c("cinemática", "mapeia configuração articular para pose", "x=f(q); ẋ=J(q)q̇", "singularidades tornam algumas direções inalcançáveis localmente"),
        _c("safety envelope", "restringe ações a estados e velocidades admitidos", "ação∈A_segura(estado)", "um planner ótimo fora do envelope continua inseguro"),
    )),
    "games-app": AreaSeed("Programação de jogos", ("src-clrs", "src-aima"), (
        _c("passo temporal", "separa atualização de simulação e desenho", "estado←update(estado,Δt)", "Δt variável grande torna colisões instáveis"),
        _c("spatial partition", "limita testes de colisão a vizinhanças", "grid[cell]→objetos próximos", "células mal dimensionadas concentram todos os objetos"),
        _c("state machine", "representa modos e transições explícitas", "(estado,event)→estado′", "booleans independentes permitem combinações impossíveis"),
        _c("pathfinding", "procura caminho por custo e heurística admissível", "f(n)=g(n)+h(n)", "navegação dinâmica exige invalidar caminhos obsoletos"),
    )),
    "recommendation-app": AreaSeed("Sistemas de recomendação", ("src-esl", "src-probml"), (
        _c("feedback implícito", "distingue exposição, interação e preferência incerta", "evento=(item,exposto,ação,tempo)", "não clicar num item nunca visto não é rejeição"),
        _c("matrix factorization", "aproxima afinidade por vetores latentes", "r̂_ui=p_uᵀq_i+b_u+b_i", "cold start carece de interações para estimar vetores"),
        _c("diversidade", "penaliza listas redundantes apesar de scores altos", "utility=relevância-λ·similaridade", "diversidade sem relevância também reduz utilidade"),
        _c("avaliação online", "mede impacto causal por grupo aleatório e guardrails", "Δ=E[métrica|tratamento]-E[métrica|controlo]", "CTR isolado pode incentivar conteúdo nocivo"),
    )),
    "time-series-app": AreaSeed("Séries temporais", ("src-probml", "src-pandas"), (
        _c("lag", "usa valores passados como informação de previsão", "x_t=[y_{t-1},…,y_{t-p}]", "lags que atravessam o horizonte introduzem fuga"),
        _c("sazonalidade", "representa padrões repetidos por período", "y_t≈trend_t+season_{t mod s}", "uma mudança de calendário quebra um período fixo"),
        _c("walk-forward", "refaz treino e avaliação respeitando o relógio", "train[:t]→test[t:t+h]", "uma única janela não mede variação no tempo"),
        _c("prediction interval", "fornece uma faixa com cobertura pretendida", "P(L_t≤Y_t≤U_t)≈1-α", "intervalos estreitos sem cobertura são falsa precisão"),
    )),
    "cybersecurity-app": AreaSeed("Cibersegurança", ("src-python-docs", "src-docker"), (
        _c("least privilege", "concede apenas capacidades necessárias pelo tempo mínimo", "permissões=interseção do necessário", "validar input não substitui isolamento"),
        _c("defesa em profundidade", "combina controlos independentes em fronteiras diferentes", "prevenir+detetar+conter+recuperar", "camadas idênticas partilham o mesmo modo de falha"),
        _c("gestão de segredos", "mantém credenciais fora de código, logs e artefactos", "secret_id→store protegido→rotação", "ofuscação ou base64 não é encriptação"),
        _c("threat modeling", "liga ativos, fronteiras, ameaças e mitigação verificável", "ativo→ameaça→controlo→teste", "listas genéricas sem arquitetura não priorizam risco"),
    )),
    "science-app": AreaSeed("Computação científica", ("src-numpy", "src-probml"), (
        _c("estabilidade numérica", "reformula expressões para reduzir cancelamento e overflow", "logsumexp(x)=m+logΣexp(xᵢ-m)", "equivalência algébrica não implica erro flutuante igual"),
        _c("unidades", "transporta dimensão física com valores e operações", "[resultado]=[entrada]×[coeficiente]", "números compatíveis em escala podem ter unidades incompatíveis"),
        _c("reprodutibilidade", "fixa dados, código, parâmetros, seed e ambiente", "artefacto=hash(inputs+config+code)", "uma seed não torna threads e hardware sempre determinísticos"),
        _c("análise de sensibilidade", "mede quanto o resultado varia com parâmetros", "S_i≈Δy/Δθ_i", "variar um parâmetro ignora interações fortes"),
    )),
    "edge-mobile-app": AreaSeed("IA em edge e mobile", ("src-pytorch-autograd", "src-ai-index"), (
        _c("quantização", "mapeia floats para inteiros por escala e zero point", "x≈s(q-z)", "outliers ampliam a escala e reduzem resolução útil"),
        _c("latência end-to-end", "inclui pré-processamento, inferência e pós-processamento", "T_total=T_pre+T_model+T_post", "benchmark só do kernel não prevê fluidez da app"),
        _c("memória de pico", "soma pesos, ativações e buffers simultâneos", "M_peak=max_t M_alocado(t)", "ficheiro pequeno pode expandir muito em runtime"),
        _c("fallback offline", "mantém comportamento seguro quando modelo ou rede falha", "resultado=modelo se válido senão regra local", "fallback não testado torna a indisponibilidade imprevisível"),
    )),
}


PRIORITY_AREAS = frozenset({
    "linear-algebra", "calculus", "probability", "optimization", "data-practice",
    "probabilistic-ml", "ensemble-learning", "deep-learning",
    "convolutional-networks", "sequence-models", "transformers", "generative-ai",
    "computer-vision", "natural-language", "reinforcement-learning",
    "agent-architectures", "agent-memory", "multi-agent", "agent-evaluation",
})

_FORMATS = (
    "concept", "formula", "comparison", "pitfall",
    "microexample", "application", "visual",
)


def _render(seed: AreaSeed, concept: ConceptSeed, card_format: str, index: int) -> tuple[str, str, str]:
    if card_format == "concept":
        fact = f"{seed.title} — {concept.name}: {concept.mechanism}."
        explanation = (
            f"O mecanismo deve ser ligado a entradas, estado e resultado observável. "
            f"A representação técnica é `{concept.expression}`. Limite importante: {concept.boundary}."
        )
    elif card_format == "formula":
        fact = f"A expressão `{concept.expression}` torna explícita uma relação central de {concept.name}."
        explanation = (
            f"Em {seed.title}, {concept.mechanism}. Lê cada símbolo pelo seu papel e confirma "
            f"as formas, unidades ou domínios antes de calcular. Caso-limite: {concept.boundary}."
        )
    elif card_format == "comparison":
        fact = f"{concept.name} só deve ser preferido depois de comparado com uma baseline mais simples."
        explanation = (
            f"A baseline verifica se a complexidade acrescentada por `{concept.expression}` produz ganho real. "
            f"O princípio técnico é: {concept.mechanism}. A comparação falha se ignorar que {concept.boundary}."
        )
    elif card_format == "pitfall":
        fact = f"Armadilha em {concept.name}: {concept.boundary}."
        explanation = (
            f"O comportamento esperado é que {concept.mechanism}. Cria um teste mínimo que contrarie a "
            f"suposição e observa `{concept.expression}` antes e depois da alteração."
        )
    elif card_format == "microexample":
        fact = f"Um microexemplo de {concept.name} deve isolar `{concept.expression}` numa entrada calculável à mão."
        explanation = (
            f"Usa um caso normal e um caso de fronteira, prevê o resultado e só depois executa. "
            f"Isto evidencia como {concept.mechanism}; inclui o limite: {concept.boundary}."
        )
    elif card_format == "application":
        fact = f"Ao aplicar {concept.name}, mede o resultado e o custo do mecanismo, não apenas a sua presença."
        explanation = (
            f"A relação operacional é `{concept.expression}` e {concept.mechanism}. Regista uma métrica de "
            f"qualidade, uma de recursos e o cenário onde {concept.boundary}."
        )
    else:
        fact = f"Um diagrama de {concept.name} deve ligar causas, transformação e evidência sem esconder o limite."
        explanation = (
            f"Representa `{concept.expression}` como fluxo e anota que {concept.mechanism}. "
            f"Marca explicitamente a fronteira: {concept.boundary}."
        )
    return fact, explanation, concept.expression


def build_advanced_facts(factory: FactFactory) -> tuple[object, ...]:
    """Build at least 12 cards per leaf and 24 for priority technical leaves."""

    facts: list[object] = []
    for area_id in sorted(AREA_SEEDS):
        seed = AREA_SEEDS[area_id]
        target = 24 if area_id in PRIORITY_AREAS else 12
        for index in range(target):
            concept = seed.concepts[index % len(seed.concepts)]
            card_format = _FORMATS[index % len(_FORMATS)]
            fact, explanation, expression = _render(seed, concept, card_format, index)
            facts.append(factory(
                slug=f"advanced-{area_id}-{index + 1:02d}",
                area_id=area_id,
                fact=fact,
                explanation=explanation,
                formula_or_code=expression,
                complexity="advanced",
                source_ids=seed.sources,
                card_format=card_format,
                visual_hint=(
                    f"{seed.title}: {concept.name}; fluxo entre pressuposto, mecanismo, "
                    "evidência e caso-limite"
                ),
            ))
    return tuple(facts)
