# Iteração 21 — Desktop Book IDE, inteligência local e circuitos profissionais

Estado: planeada  
Plataforma desta iteração: Windows Desktop  
Data de referência: 13 de agosto de 2026  
Dependência: Iteração 20 concluída  
Mobile: congelado até ao fecho dos gates desktop desta iteração

## 1. Objetivo

Transformar o Aprendix num espaço de aprendizagem e programação com uma leitura
visual semelhante a um livro aberto: editor à esquerda, enunciado e apoio à
direita e terminal transversal na zona inferior. Em paralelo, esta iteração
deve tornar fórmulas matemáticas legíveis, eliminar problemas de símbolos e
encoding, aprofundar a análise estática, corrigir a prioridade da pesquisa e
criar percursos profissionais reais sobre o núcleo Python.

A expansão de conteúdo pedida é **aditiva** e só conta itens ativos, distintos,
validados e com proveniência. Inserir linhas repetidas ou conteúdo colocado em
quarentena não satisfaz o objetivo.

## 2. Baseline auditada

Contagens medidas no perfil Windows atual:

| Domínio | Estado atual utilizável | Dívida identificada | Meta no final |
|---|---:|---:|---:|
| Fontes curadas | 1 120 | forte enviesamento para documentação stdlib | pelo menos 1 620 (+500) |
| Cards editoriais ativos | 1 827 | 20 343 chunks importados ainda classificados/indexados como cards | pelo menos 2 827 (+1 000) |
| Termos do dicionário | 3 343 | 3 260 são Python; restantes áreas têm pouca profundidade | pelo menos 4 343 (+1 000) |
| Exercícios aceites | 3 063 | 236 em quarentena; muitas recombinações de poucos contratos | pelo menos 3 563 (+500) |
| Projetos aceites | 20 | sem associação N:N a profissões | pelo menos 70 (+50) |
| Soluções de referência validadas | 0 materializadas | tabela existe, mas está vazia | 500 novas + soluções dos exercícios de percurso prioritários |
| Percursos | 12 | espelham cursos 1:1 numa cadeia linear | 5 circuitos profissionais em DAG |

Achados funcionais que orientam a ordem do trabalho:

- O IDE já possui editor/enunciado horizontal e painel inferior, mas abaixo de
  1080 dp muda prematuramente para uma só página. A 150% DPI isto acontece mesmo
  numa janela fisicamente larga.
- Abrir o terminal pode recolher o enunciado e a altura do terminal não é
  ajustável.
- O modelo guarda blocos de fórmula com LaTeX, texto falado e variáveis, mas a
  UI mostra o comando LaTeX cru.
- A pesquisa geral mistura fontes, leituras, exercícios e cards no mesmo nível.
  Por exemplo, consultas técnicas podem devolver vários `aprendix://` antes de
  bibliografia ou documentação realmente relevante.
- O analisador usa `ast`, mas não produz uma tabela de símbolos, CFG verdadeiro,
  grafo de chamadas, inferência conservadora de tipos ou diagnósticos profundos.
- O conteúdo editorial inspecionado está maioritariamente em UTF-8 correto. Os
  quadrados/símbolos estranhos resultam sobretudo de glifos usados como ícones,
  falta de fontes Unicode empacotadas e decoding inseguro de entradas Web/OCR.

## 3. Princípios obrigatórios

1. Local-first, perfil anónimo e funcionamento integral offline.
2. Nenhum código fornecido pelo utilizador é executado durante análise estática.
   Uma execução/traço opcional usa apenas o sandbox já isolado.
3. O corpo pedagógico é original. Fontes protegidas contribuem com metadados,
   conceitos e referência exata, nunca com cópia extensa.
4. Conteúdo importado é evidência de leitura; não se transforma automaticamente
   num card de curiosidade.
5. Consulta de aulas/enunciados continua livre; crédito curricular mantém os
   pré-requisitos definidos na Iteração 20.
6. LaTeX é uma linguagem de entrada para o renderer, não um texto a apresentar
   nem um processo externo a executar.
7. “Saída esperada” ou “traço de execução” descreve uma execução com sucesso.
   “Traceback” fica reservado a exceções reais e é mostrado de forma sanitizada.
8. Botões por ícone mantêm nome acessível, tooltip, estado de foco e atalho. Um
   ícone nunca é a única explicação disponível.
9. Mobile permanece intocado até o `.exe` desktop passar todos os gates.

## 4. Ordem de execução

### 21.0 — Higiene e versionamento do catálogo

Esta etapa precede toda a expansão para impedir que conteúdo novo seja indexado
ao lado de dados antigos sem governação.

Implementar uma migração SQLite transacional, prevista como schema 38, com:

- release de catálogo, fingerprint, estado `active`, `retired` ou `quarantined`
  e versão do gerador;
- chave canónica de fonte, priorizando DOI, URL normalizado e, por fim, hash de
  título/autores/ano;
- distinção explícita entre `source`, `reading_chunk`, `lesson`, `exercise`,
  `project`, `editorial_card` e `glossary`;
- associação N:N de percursos, objetivos, projetos e profissões;
- walkthrough/traço esperado e política de revelação por exercício;
- índices por release, estado, tipo, percurso e sequência.

Os 20 343 cards derivados de documentos importados devem ser retirados do pool
de cards e preservados como chunks de leitura. Não se apaga histórico de revisão,
tentativas, progresso ou projetos locais. A pesquisa e o compilador passam a
considerar apenas itens ativos e aprovados.

Gates:

- backup e rollback testados;
- migração limpa e upgrade de um perfil real produzem o mesmo estado lógico;
- seed executado duas vezes mantém contagens e fingerprints;
- `foreign_key_check` vazio e `integrity_check=ok`;
- zero cards sem apresentação, qualidade e fontes no deck ou índice editorial;
- zero itens retirados nos resultados normais de pesquisa.

### 21.1 — Design system, iconografia e texto seguro

Criar uma camada visual reutilizável em vez de símbolos Unicode dispersos:

- família de ícones SVG original do Aprendix para Painel, Curso, IDE, Pesquisa,
  Cards, Dicionário, Tutor, Projetos, Analisar, Games, Dados, executar, corrigir,
  depurar, formatar, procurar, copiar, terminal, problemas, testes e ajuda;
- `IconAction` com alvo mínimo de 44 dp, tooltip visual, nome acessível, foco por
  teclado, estados hover/pressed/disabled e indicação do atalho;
- rail lateral compacto, expansível e persistente; o texto completo continua
  disponível no modo expandido e na paleta `Ctrl+K`;
- fontes Unicode licenciadas e empacotadas: uma sans para UI, uma mono para
  código e uma matemática; fallback explícito por plataforma;
- auditoria que proíbe glifos privados, emojis e caracteres-font usados como
  ícones funcionais.

Introduzir `TextNormalizationService` com perfis distintos:

- prosa: BOM/charset, NFC/NFKC controlado, newline e caracteres de controlo;
- código Python: `tokenize.open`, encoding declarado e preservação semântica;
- notebooks: UTF-8/UTF-8-SIG e validação JSON;
- fórmulas: preservar comandos permitidos, sem normalização destrutiva;
- Web: BOM, charset HTTP, `<meta charset>`, detector local de fallback e
  quarentena se a descodificação continuar ambígua;
- OCR: conservar original e confiança; reparação de mojibake apenas se for
  reversível e reduzir comprovadamente o score de anomalia.

`U+FFFD` deixa de ser apagado silenciosamente. A ingestão falha ou coloca o item
em quarentena com proveniência e diagnóstico.

Gates:

- corpus com `ação`, `€`, `→`, `≤`, `α`, acentos, aspas e código declarado;
- testes de UTF-8, CP1252 legítimo, mojibake reversível e texto irrecuperável;
- nenhum quadrado de substituição nas fontes empacotadas;
- todo botão compacto possui tooltip, acessibilidade e atalho quando aplicável.

### 21.2 — Fórmulas matemáticas offline partilhadas

Criar um `MathRendererPort` e um `FormulaView` único para IDE, Cards, Pesquisa e
Reader.

Pipeline desktop:

1. validar um subconjunto delimitado de LaTeX matemático;
2. renderizar localmente com MathText/Agg, sem distribuição LaTeX externa;
3. guardar PNG/SVG transparente em cache content-addressed;
4. incluir fórmula, tema, DPI, escala e versão do renderer no hash;
5. apresentar texto falado, significado das variáveis e LaTeX copiável como
   alternativa acessível;
6. em caso de erro, mostrar o texto falado e uma mensagem curta, nunca bloquear
   o ecrã ou apresentar uma pilha interna.

Estender cards de fórmula para guardarem `latex`, `spoken`, `variables` e um
exemplo resolvido. Migrar os 254 cards marcados como fórmula, rejeitando fórmulas
duplicadas ou sem significado pedagógico.

Gates:

- snapshots nos temas claro, escuro e alto contraste;
- frações, potências, índices, somatórios, raízes, matrizes e letras gregas;
- nenhuma barra invertida/comando LaTeX visível no modo normal;
- limite de tamanho, profundidade e tempo para input hostil;
- cache reproduzível e totalmente offline.

### 21.3 — IDE em formato de livro

Recompor o workspace segundo o desenho fornecido:

```text
┌─────────────────────────────────────────────────────────────┐
│ barra de contexto, percurso, exercício e comandos          │
├──────┬──────────────────────┬───────────────────────────────┤
│ rail │ editor de código     │ enunciado / aula / apoio      │
│      │                      │                               │
│      ├──────────────────────┴───────────────────────────────┤
│      │ terminal / problemas / testes / debug / tutor       │
└──────┴──────────────────────────────────────────────────────┘
```

Requisitos:

- `ide_desk` vertical contendo `book_split`, divisor horizontal e terminal;
- página esquerda com editor, gutter, separadores de ficheiro e find/replace;
- página direita com tabs Enunciado, Aula, Pistas, Solução possível e Execução
  esperada;
- divisor vertical ajustável e persistente, mantendo mínimos de 360 dp para o
  editor e 320 dp para o apoio;
- terminal recolhido com 36–40 dp e aberto entre 20% e 35% da altura útil,
  ajustável e persistente;
- o terminal ocupa toda a largura do livro e nunca recolhe automaticamente o
  enunciado;
- em ecrãs sem 700 dp úteis, fallback explícito por tabs Editor/Apoio, mantendo
  o terminal transversal;
- política responsiva baseada na largura útil do workspace, não na largura
  global nem num limiar fixo de 1080 dp;
- toolbar principal por ícones; texto apenas nas ações pedagógicas ambíguas,
  tooltips e paleta de comandos;
- atalhos coerentes: executar, corrigir, depurar, terminal, procurar,
  substituir, copiar, formatar, aumentar/diminuir texto e mudar de tab;
- terminal com tabs compactas Output, Problemas, Testes, Debug e Tutor.

Gates geométricos:

- 1024×768@100%, 1366×768, 1920×1080 e 1222×956@150%; varrimento 100–200% DPI;
- duas páginas visíveis sempre que os mínimos couberem;
- terminal aberto tem a mesma largura do livro e não cobre conteúdo;
- divisores e painel restauram proporções após reinício;
- editor inicia vazio e `Corrigir` permanece sempre encontrável;
- navegação integral por teclado e foco visível.

### 21.4 — Enunciado curto, solução e execução explicada

Evoluir o documento de exercício para blocos estruturados:

- título e contexto curto;
- objetivo observável;
- entradas, constantes, variáveis, tipos e significado;
- assinatura/contrato quando aplicável;
- fórmula renderizada e explicação das variáveis;
- exemplo de entrada/saída ou tabela esperada;
- decomposição top-down opcional;
- casos-limite e critérios de aceitação;
- solução de referência validada;
- traço de execução por passos e stdout esperado;
- erros/tracebacks pedagógicos apenas para exceções relevantes.

Modos:

- **Simples:** objetivo, contrato, um exemplo e três a cinco passos curtos;
- **Guiado:** acrescenta top-down, variáveis/tipos, casos-limite e pistas;
- **Técnico:** especificação integral, complexidade, invariantes e fontes.

A aba direita permite avançar continuamente de exercício em exercício. Ao
aprovar, mostra resultado, reflexão opcional e ação Seguinte, sem regressar ao
painel. A solução completa fica disponível em treino após quatro tentativas
falhadas ou depois de concluir o exercício; fica bloqueada durante avaliações.
Cada revelação fica registada e afeta autonomia, não impede a aprendizagem.

O exercício “Capital acumulado” fornecido torna-se caso de aceitação canónico:

- fórmula de capital composto renderizada;
- tabela para 2021–2023 e taxas 2%, 2,5% e 3%;
- constantes/variáveis explicitadas;
- decomposição top-down;
- solução Python validada no sandbox;
- stdout esperado alinhado e traço das variáveis por iteração;
- exemplo separado de traceback apenas para um erro real deliberado.

Gates:

- zero código/encoding acidental no enunciado;
- leitura simples não excede o orçamento visual definido para uma página;
- todas as soluções materializadas compilam e passam testes públicos/ocultos;
- stdout e traceback nunca são rotulados um como o outro;
- solução não pode ser revelada numa avaliação bloqueada.

### 21.5 — Pesquisa geral source-first

Separar os pools de recuperação:

1. fontes e documentos/leituras;
2. aulas, dicionário, exercícios e projetos;
3. cards editoriais internos.

Política de ranking:

- pesquisa técnica geral apresenta primeiro bibliografia, documentação, papers,
  livros e leituras com evidência;
- no top 3 devem existir pelo menos duas fontes/documentos reais quando o
  catálogo possuir correspondências adequadas;
- conteúdos `aprendix://` só podem liderar para intenções explícitas como
  “curso”, “aula”, “card”, “exercício” ou “projeto Aprendix”;
- aplicar um mínimo de cobertura lexical ou correspondência semântica forte;
- BM25/dense recuperam por pool, o reranker trabalha dentro de níveis de
  autoridade e uma fusão calibrada compõe a página final;
- diversidade MMR não pode promover um hard negative;
- ausência de evidência produz uma resposta honesta, não conteúdo vagamente
  semelhante;
- o resumo é sintetizado a partir das fontes exibidas e as fórmulas usam
  `FormulaView`.

Os 20 343 antigos cards importados deixam de ser entidades `card` no índice e
continuam disponíveis como chunks de Reader sujeitos à qualidade da ingestão.

Gates:

- benchmark com pelo menos 250 consultas, incluindo as cinco profissões;
- Recall@10 ≥ 0,98, nDCG@10 ≥ 0,95 e P95 < 150 ms no hardware de referência;
- política source-first top-3 cumprida sempre que existirem fontes relevantes;
- zero `aprendix://` no top 3 de pesquisa geral, salvo intenção interna explícita;
- regressões obrigatórias: “capital acumulado juros compostos”, “decoradores
  Python” e “backpropagation regra da cadeia”;
- hard negatives, queries sem resposta, filtros e modo offline.

### 21.6 — Analisador estático profundo

Substituir o relatório superficial por um pipeline limitado e explicável:

1. deteção de linguagem e tokenização com recuperação de sintaxe parcial;
2. parsing AST com limites de bytes, nós, profundidade e tempo;
3. tabela de símbolos e âmbitos;
4. funções, classes, assinaturas, parâmetros, decoradores e herança;
5. definições/usos, variáveis indefinidas, não usadas e shadowing de built-ins;
6. inferência conservadora de tipos, com confiança e justificação;
7. CFG real por função, grafo de chamadas e código inacessível;
8. complexidade ciclomática e temporal/espacial por função;
9. efeitos laterais, exceções possíveis, imports e políticas de segurança;
10. casos de teste concretos derivados do contrato observado.

Criar DTOs próprios para `Diagnostic`, `Symbol`, `Function`, `Class`, `TypeFact`,
`CFGBlock`, `CallEdge`, `ComplexityFinding`, `SecurityFinding` e
`TestSuggestion`. Cada diagnóstico inclui código, severidade, linha, coluna,
mensagem, evidência, confiança e eventual correção segura.

As ações passam a ser distintas: Explicar, Completar, Converter, Encontrar
problemas, Criar testes, Visualizar fluxo e Ligar ao curso. A UI apresenta tabs
Resumo, Problemas, Símbolos, Fluxo, Tipos, Complexidade e Testes. Uma opção
separada “Executar e traçar” reutiliza o debugger/sandbox e exige consentimento
explícito; a análise estática nunca chama `exec`, `eval`, import do snippet,
subprocesso ou rede.

Gates:

- golden corpus de pelo menos 50 snippets Python/pseudocódigo;
- sintaxe incompleta, scopes, closures, tipos, imports, classes, CFG, chamadas,
  unreachable code, exceções e shadowing;
- nenhuma chamada de execução durante análise, provada por monkeypatch;
- ações produzem relatórios materialmente diferentes;
- budgets de tempo/memória/profundidade e cancelamento;
- relatório do exemplo de capital identifica `math`, constantes, variáveis,
  ciclos, fórmula, outputs e complexidade sem chamar `print`/`range` de inputs.

### 21.7 — Circuitos profissionais sobre o núcleo Python

Converter os percursos 1:1 numa DAG curricular com um núcleo comum:

`Literacia → Lógica → Python Base → Testes/Debug → Git/Packaging`

Depois, disponibilizar cinco circuitos selecionáveis:

1. **Python/Backend Engineer** — POO, estruturas/algoritmos, Python avançado,
   SQL, APIs, Django/FastAPI, segurança e arquitetura.
2. **Data Analyst** — Python, SQL, estatística, NumPy/Pandas, limpeza,
   visualização, experimentação e séries temporais.
3. **Data Engineer** — Python avançado, SQL/NoSQL, modelação, ETL, qualidade,
   orquestração e observabilidade.
4. **AI/ML Engineer** — algoritmos, matemática, dados, ML clássico, deep
   learning, visão computacional, NLP, agentes, MLOps e IA responsável.
5. **Cybersecurity Automation Analyst** — Python, sistemas, redes,
   criptografia aplicada, secure coding, Web/AppSec, logs, deteção e automação.

Cada circuito define competências de entrada/saída, sequência recomendada,
alternativas, evidências, milestones, avaliações e capstones. O utilizador pode
consultar qualquer unidade; só o crédito sequencial e a recomendação dependem
dos pré-requisitos. Selecionar Python sugere os ramos POO, algoritmia, SQL/NoSQL,
dados e ML compatíveis com o objetivo profissional, sem impor uma cadeia única.

Gates:

- DAG acíclica e todos os nós essenciais alcançáveis;
- nenhum circuito sem avaliações e capstone;
- objetivos e projetos ligados N:N aos circuitos;
- recomendação explica “porquê agora”, pré-requisitos e resultado profissional;
- troca de circuito preserva todo o progresso já demonstrado.

### 21.8 — Expansão governada do conteúdo

Executar a expansão por lotes pequenos, compilados e auditados antes da ativação
atómica da release.

#### 500 novas fontes

Distribuição mínima:

- Python, runtime, testes e packaging: 80;
- engenharia, algoritmos e sistemas: 70;
- SQL, NoSQL, analytics e data engineering: 100;
- IA, ML, DL, visão, NLP, agentes e MLOps: 120;
- cibersegurança, redes, AppSec e forense: 70;
- backend, APIs e DevOps: 35;
- ética, acessibilidade e prática profissional: 25.

Somente documentação primária, standards, papers, livros reconhecidos e
relatórios institucionais. DOI/URL e autoria são verificados; ficheiros locais
mantêm URI e página/seção. Não guardar corpo integral sem licença.

#### 1 000 novos cards

- Python: 220;
- software/backend/testes: 120;
- bases de dados/data engineering: 140;
- matemática/estatística/analytics: 150;
- IA/ML/DL/CV/NLP/agentes: 220;
- cibersegurança: 100;
- sistemas, ética e prática profissional: 50.

Cada card contém uma afirmação útil semanticamente única, duas fontes exatas
(três para fórmulas avançadas), formato pedagógico, nível, área, circuito e
eventual recurso visual relevante. Gráficos decorativos não contam.

#### 1 000 novos termos de dicionário

- Python avançado: 100;
- algoritmos, estruturas e matemática discreta: 140;
- bases de dados e engenharia de dados: 160;
- estatística e IA: 180;
- cibersegurança, redes, sistemas e criptografia: 160;
- Web, arquitetura e DevOps: 100;
- analytics e visualização: 80;
- qualidade, acessibilidade, ética e performance: 80.

Cada entrada tem termo canónico, dois a cinco aliases, definição curta, pelo
menos dois exemplos progressivos, pelo menos duas fontes e relações válidas.
Aliases não são contados como termos independentes.

#### 500 novos exercícios

- Python core: 100;
- POO, arquitetura e testes: 70;
- algoritmos e estruturas: 70;
- SQL, NoSQL e modelação: 60;
- dados, estatística e visualização: 60;
- IA, ML, DL, CV, NLP e agentes: 70;
- cibersegurança, sistemas e redes: 50;
- backend e APIs: 20.

Cada exercício tem contrato próprio, enunciado nos três modos, testes públicos e
ocultos, solução validada em sandbox, explicação, traço de execução e fontes.
Deduplicação usa fingerprint de contrato+AST+testes e similaridade semântica;
trocar apenas o contexto narrativo não cria um exercício novo.

#### 50 novos projetos

Criar 10 projetos por circuito profissional, com 10 de iniciação, 20
intermédios e 20 avançados. Cada projeto é totalmente offline e inclui fixtures,
brief curto/completo, quatro a seis milestones, rubrica mensurável, testes,
ameaças/casos-limite, pelo menos três fontes, objetivos e circuito N:N.

Gates globais de conteúdo:

- deltas exatos de itens ativos e aprovados;
- zero duplicados exatos e zero near-duplicates acima do limiar acordado;
- 100% de cards, termos, exercícios e projetos novos com fontes;
- 100% das 500 soluções passam os respetivos testes no sandbox;
- revisão automática de legibilidade, rigor, dificuldade e cobertura;
- ativação da release é atómica; qualquer falha mantém a versão anterior ativa.

### 21.9 — Validação E2E, empacotamento e instalação

Executar, por esta ordem:

1. unit tests dos novos contratos, políticas puras e algoritmos;
2. migração limpa, upgrade, rollback e preservação de perfil;
3. integração BD/FTS/embeddings/cache;
4. benchmarks de pesquisa, analisador e conteúdo;
5. jornadas funcionais IDE → aula → exercício → execução → correção → solução →
   próximo exercício;
6. jornadas por cada circuito profissional;
7. testes de teclado, contraste, fontes, fórmulas, scroll e DPI;
8. smoke visual do código-fonte e do `.exe` instalado;
9. PyInstaller com fontes, SVGs, renderer matemático e assets;
10. self-test, SBOM, hashes, manifesto e atalho Windows.

O build só é instalado depois de a suíte integral terminar com exit code zero.
O relatório final deve distinguir testes automáticos de verificações físicas
externas, sem declarar como testado o que não foi observado.

## 5. Definition of Done

A Iteração 21 fica concluída apenas quando:

- o IDE reproduz o livro de duas páginas e o terminal transversal do desenho;
- a versão compacta mantém acesso explícito ao editor, apoio e terminal;
- botões principais usam ícones originais, tooltips e nomes acessíveis;
- fórmulas aparecem matematicamente compostas nos quatro contextos, sem LaTeX
  cru no modo normal;
- o corpus de encoding passa sem quadrados, mojibake silencioso ou perda oculta;
- o analisador produz símbolos, funções/classes, tipos, CFG, chamadas,
  complexidade, diagnósticos e testes sem executar código;
- a pesquisa geral é source-first e os casos de regressão estão corretos;
- os cinco circuitos profissionais estão navegáveis, explicáveis e ligados ao
  progresso;
- existem +500 fontes, +1 000 cards, +1 000 termos, +500 exercícios e +50
  projetos **ativos, únicos, validados e com proveniência**;
- os antigos chunks importados não contaminam o deck nem o ranking editorial;
- migração, integridade, suíte integral, benchmarks, build, self-test e smoke do
  `.exe` passam;
- não foi introduzida qualquer dependência de cloud ou alteração mobile.

## 6. Entregáveis

- schema 38 e scripts de migração/rollback;
- catálogo versionado e compilador de qualidade atualizado;
- componentes `IconAction`, tooltip, fontes, `FormulaView` e divisores do IDE;
- workspace de livro e painel direito pedagógico;
- modelo estruturado de enunciado/solução/traço;
- pesquisa source-first e novo benchmark;
- analisador estático profundo e golden corpus;
- cinco circuitos profissionais;
- release de conteúdo com os deltas definidos;
- `ITERATION-21-AUDIT-1.0.0.json`, documentação de validação, novo `.exe`,
  manifesto e instalação Windows verificada.
