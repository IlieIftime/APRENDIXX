# Iteração 20 — Desktop Learning Workspace

Estado: concluída nos gates automatizáveis em 12 de agosto de 2026. A subtree
mobile permaneceu congelada durante a execução; os ensaios físicos de múltiplos
monitores, screen reader e Authenticode continuam declarados como gates externos.

## Objetivo

Transformar o Aprendix Windows num espaço de aprendizagem compacto, coerente e
mensurável: consultar qualquer conteúdo sem barreiras, creditar apenas trabalho
elegível, apresentar progresso através de gráficos interpretáveis, tornar o grafo
semântico e integrar aula, enunciado, IDE, terminal, dicionário e projetos num fluxo
único. Conteúdo e fontes são fechados no desktop antes de voltar ao mobile.

## Diagnóstico confirmado

- O Painel atual é uma coluna extensa com plano, métricas, forecast, semana,
  gamificação, 30 nós e milestones, sem navegação interna ou séries temporais.
- A snapshot instalada contém cerca de 3 634 nós, mas apenas 56 são curriculares e
  quatro têm atividade. O grafo apresenta todos e o domínio global usa um universo
  demasiado amplo.
- As arestas misturam pré-requisito e coocorrência sem tipo ou explicação. O detalhe
  perde sucessos/falhas e não apresenta tempo, exercícios distintos ou retenção.
- O Curso esconde teoria e enunciado de unidades bloqueadas. Pelo caminho inverso,
  o IDE permite aprovar uma prática bloqueada e a camada atual pode creditá-la sem
  validar as dependências.
- Um projeto aberto no IDE conserva o exercício/enunciado anterior; `Corrigir` e
  `Ctrl+S` podem, por isso, usar o contexto errado.
- A teoria pré-prática existe, mas é uma micro-nota textual. O layout continua
  vertical: percurso, enunciado, editor e terminal empilhados.
- `Ctrl+F` abre o popup geral de engenharia; o dicionário por F1 abandona o IDE.
- Existem 1 131 cards autorais, mas 1 068 concentram-se em quatro áreas básicas;
  27 áreas-folha têm apenas um card. Nenhum card autoral tem visual dedicado.
- As referências do verso são inferidas pela área, em vez de estarem ligadas ao
  facto. Isto pode apresentar bibliografia correta para a área, mas errada para o
  card concreto.
- A pesquisa medida é rápida e relevante no golden set atual, mas o conjunto é
  enviesado para os próprios cards. O leitor ainda recebe texto PDF plano, com
  hifenização, quebras, tabelas e figuras insuficientemente preservadas.

## Princípios da iteração

1. **Consultar não é creditar.** Teoria, enunciados e projetos são sempre visíveis;
   pré-requisitos condicionam apenas progresso, XP, milestones e desbloqueios.
2. **Métricas explicáveis.** Cada número do Painel e do grafo tem definição, período,
   denominador e acesso ao detalhe que o originou.
3. **Conteúdo governado.** Texto Aprendix original; fontes externas para validação e
   localização, sem copiar páginas, figuras ou obras protegidas.
4. **Local-first.** Nenhuma jornada principal exige rede; web continua explícita,
   limitada, tratada e desativada por omissão.
5. **Desktop primeiro.** Não se altera a UI mobile durante esta iteração.

## 20.1 — Integridade pedagógica e migração

- Criar uma política central de acesso com estados separados:
  `viewable`, `credit_eligible`, `completed` e `reason_code`.
- Expor todas as 248 unidades para consulta, incluindo teoria, enunciado, exemplo,
  projeto, rubrica e referências.
- Permitir treino antecipado como exploração. A tentativa e o feedback ficam
  guardados, mas não alteram `learning_unit_progress`, XP, rank ou milestone.
- Validar dependências transacionalmente imediatamente antes de qualquer crédito.
- Depois de desbloquear, exigir uma nova aprovação elegível; uma aprovação antiga
  não é promovida retroativamente.
- Auditar progresso legado incompatível sem apagar histórico. Registos suspeitos são
  identificados num relatório agregado e não usados silenciosamente para desbloquear.
- Ligar cada capstone ao template, percurso, milestones e avaliação correspondentes.
  A existência de um projeto local qualquer deixa de satisfazer uma unidade.

## 20.2 — Analytics e arquitetura do Painel

- Criar contratos e queries para séries globais, por percurso e por nó, com períodos
  7/30/90 dias e intervalo personalizado.
- Calcular o global apenas sobre nós curriculares; conceitos de dicionário não entram
  no denominador de conclusão.
- Novo primeiro nível do Painel com no máximo seis indicadores:
  domínio, retenção, autonomia, tempo ativo versus planeado, consistência e próximo
  milestone. Cada indicador inclui tendência curta e definição acessível.
- Segundo menu interno:
  **Resumo**, **Atividade**, **Competências**, **Percursos** e **Plano**.
- Gráficos adequados à variável, sem decoração gratuita:
  linha para evolução, barras para tempo/volume, distribuição para estados de domínio
  e timeline para milestones. A comparação é apenas com o histórico do utilizador.
- Um clique num gráfico aplica período e granularidade aos restantes painéis e ao
  grafo, mantendo filtros visíveis.

## 20.3 — Grafo de competências semântico

- Separar relações `prerequisite`, `progression`, `related` e `co_occurrence`, com
  direção, peso, razão e origem. Coocorrência nunca substitui um pré-requisito.
- A vista inicial mostra apenas nós praticados/dominados no período. Uma opção
  explícita **Próximos elegíveis** acrescenta somente a fronteira recomendada; não
  revela milhares de nós intocados.
- Filtrar no backend e impor orçamento inicial de 150 nós/300 arestas.
- Integrar o grafo como submenu do Painel, sem abrir outra instância Aprendix.
  Implementar uma vista Kivy Canvas/Scatter com zoom, pan, drag, pesquisa, reset,
  legenda e navegação por teclado; manter o HTML/D3 apenas como exportação/fallback.
- Arestas usam direção, estilo e legenda coerentes. Selecionar uma aresta explica o
  motivo da ligação.
- Selecionar um nó mostra: exercícios distintos, tentativas, sucessos/falhas, taxa de
  sucesso, tempo ativo, dicas, retenção, autonomia, última prática, tendência e ação
  recomendada, com atalhos **Abrir curso** e **Praticar no IDE**.

## 20.4 — Documento pedagógico estruturado

- Introduzir blocos tipados para aula, enunciado e projeto: título, parágrafo, lista,
  código, assinatura, fórmula, tabela, imagem, diagrama, callout e referências.
- Guardar texto alternativo, proveniência, licença e hash para cada visual local.
- Renderizar código/`def`/`class` como blocos com realce sintático, não como texto
  indiferenciado.
- Manter fallback determinístico para conteúdo legado, mas materializar contexto,
  objetivo, contrato, entradas, restrições, exemplos e critérios como campos próprios.
- Expandir as 50 aulas teóricas atuais: objetivos, pré-requisitos, explicação precisa,
  exemplo orientador, casos-limite, verificação curta e duas fontes; três fontes em
  matéria avançada.
- Reestruturar os 59 exercícios da espinha dos cursos e os 20 projetos com revisão
  pedagógica automática. Os restantes exercícios usam o gerador estruturado validado.

## 20.5 — Fluxo aula → prática e workspace do IDE

- Ao iniciar uma lição nova, abrir a aula quase em ecrã inteiro. **Continuar para a
  prática** muda para o workspace; a previsão é identificada como opcional.
- Ao retomar, restaurar a última fase, posição do divisor, cursor, draft e painel.
- Na prática, editor à esquerda e enunciado à direita, com divisor arrastável e posição
  persistida. Em largura reduzida, alternar entre separadores Editor/Enunciado.
- Cabeçalho curto com curso, unidade, progresso e botões compactos Anterior/Seguinte.
- Barra principal com ícones locais inequívocos, tooltip e nome acessível. Eliminar
  caracteres dependentes de icon fonts.
- Barra lateral recolhida entre 56–64 dp, com ícones consistentes e tooltip.
- Terminal como drawer: barra de separadores sempre visível e corpo inicialmente
  fechado. `Run`, `Corrigir` e `Debug` abrem o painel relevante automaticamente.
- Desativar comandos concorrentes enquanto uma execução/correção está ativa.
- Expor as cores semânticas de informação, sucesso, aviso e erro e manter tema escuro,
  claro e alto contraste, incluindo overlays e ecrãs já instanciados.

## 20.6 — Pesquisa no editor, dicionário e modo Projeto

- `Ctrl+F` abre apenas uma barra inline de procura: contador, anterior/seguinte,
  Enter/Shift+Enter e Escape.
- `Ctrl+H` e botão dedicado abrem substituir, substituir seguinte e substituir tudo.
  Comparação/complexidade permanecem nas ferramentas avançadas.
- F1 ou duplo clique abre um inspetor translúcido dentro do IDE, com largura máxima
  aproximada de 420 dp e menos de metade do workspace. Não muda de rota.
- Mostrar 3–5 correspondências, definição, assinatura, relacionados, fontes e vários
  exemplos. Criar `glossary_examples` para dificuldade e contexto.
- Criar modos explícitos `EXERCISE` e `PROJECT` no IDE. Título, brief, ficheiros,
  `Ctrl+S`, `Corrigir`, rubrica e terminal dependem do modo ativo.
- No modo Projeto mostrar contexto, objetivo, entregáveis, requisitos, milestones,
  critérios de aceitação e rubrica. Oferecer **Começar vazio** e **Usar esqueleto**.
- A avaliação de projeto é independente dos testes do último exercício aberto.

## 20.7 — Cards, visuais e proveniência exata

- Navegação desktop: Esquerda = confuso, Direita = útil, Cima/Baixo = tema e Enter =
  virar. O rato usa zonas laterais do card e clique central para virar, sem quatro
  botões permanentes a ocupar espaço.
- Criar `card_source_links` com fonte, secção/locator, rationale e versão. O verso usa
  exclusivamente estas ligações, nunca inferência genérica pela área.
- Reequilibrar o catálogo por matriz área × nível × formato. Nesta iteração:
  - nenhuma área-folha avançada fica com menos de 12 cards;
  - áreas prioritárias de matemática, ML, DL, visão, NLP, RL e agentes chegam a 24;
  - cada área usa pelo menos quatro formatos entre conceito, fórmula, comparação,
    armadilha, microexemplo, aplicação e visual.
- Produzir diagramas, plots e imagens originais Aprendix quando acrescentem compreensão.
  Não extrair figuras protegidas de livros. Todos os assets ficam num armazenamento
  gerido por hash, com licença, alt text e teste de caminho.
- O deck continua adaptativo, mas intercala áreas e explica sempre por que mostrou o
  card.

## 20.8 — Pesquisa, Reader e bibliografia

- Indexar metadados de todas as fontes curadas; remover o limite que impede avaliar a
  maior parte das referências oficiais Python.
- Converter documentos aceites num modelo de blocos que preserve títulos, listas,
  código, tabelas, fórmulas, figuras e legendas quando tecnicamente possível.
- Aplicar normalização Unicode, remoção de controlos/cabeçalhos repetidos e
  de-hifenização conservadora sem unir identificadores ou código.
- Reader renderiza blocos em vez de um `TextInput` monolítico; Resumo e Simplificado
  são derivados da fonte aberta e preservam fórmulas/pressupostos importantes.
- Web permanece opt-in e usa apenas adapters allowlisted, HTTPS, limites, cache,
  provenance e regras de licença/robots. Snippets web não fingem ser conteúdo integral.
- Reavaliar clustering; resultados `noise` usam vizinhos semânticos verificados em vez
  de tópicos semelhantes vazios ou arbitrários.
- Criar holdout externo com pelo menos 100 queries e hard negatives para BFS/DFS, A*,
  pytest, SQL, matemática, mensagens de erro e OCR ruidoso.

## 20.9 — Qualidade, release Windows e condição para mobile

### Gates funcionais

- Todas as 248 unidades podem ser lidas sem desbloqueio.
- Aprovar uma prática bloqueada guarda exploração, mas não progresso, XP ou milestone.
- Após cumprir os pré-requisitos, uma nova aprovação credita exatamente uma vez.
- Um capstone só conta para o percurso correto depois de avaliação aprovada.
- Abrir um projeto nunca mostra nem executa os testes do exercício anterior.
- `Ctrl+S` em Projeto guarda o ficheiro do projeto; em Exercício guarda o draft.
- Aula nova abre antes da prática; a prática usa editor/enunciado lado a lado.
- Terminal começa recolhido e abre na operação adequada.
- `Ctrl+F` é inline; o inspetor do dicionário não abandona o IDE.
- O grafo inicial não inclui nós intocados e os detalhes reconciliam com a BD.
- Cada card visível tem pelo menos uma fonte exata e nenhum asset quebrado.

### Gates quantitativos

- Dashboard e grafo reconciliados por queries independentes para 7/30/90 dias.
- Grafo inicial ≤150 nós e ≤300 arestas; renderização alvo inferior a 500 ms.
- Dicionário exact/alias top-1 ≥98%, P95 local <150 ms; top 500 termos com pelo
  menos dois exemplos e duas referências.
- Pesquisa no holdout: Recall@10 ≥0,90, nDCG@10 ≥0,80 e P95 <500 ms.
- Corpus aceite sem U+FFFD nem controlos inesperados; fixtures confirmam código,
  tabelas, figuras e de-hifenização.

### Validação final

- Testes unitários, integração, migração e regressão integral.
- Matriz visual 1024×768, 1366×768 e 1920×1080, a 100–200% DPI.
- Jornadas completas por teclado e rato, contraste e foco visível.
- Build PyInstaller, self-test e smoke do EXE instalado.
- Manifesto/hashes e documentação atualizados.

Só depois de todos estes gates passarem se abre a Iteração 21 de portabilidade mobile.

## Ordem de execução

1. 20.1 — corrigir semântica e proteger dados;
2. 20.2 — criar analytics confiáveis;
3. 20.3 — reconstruir Painel e grafo;
4. 20.4 — estabilizar o modelo de documento;
5. 20.5–20.6 — reconstruir workspace, atalhos, dicionário e projetos;
6. 20.7–20.8 — equilibrar conteúdo, proveniência, visuais, Reader e pesquisa;
7. 20.9 — validar, empacotar e apenas então retomar mobile.
