# Plano integrado — árvore de conhecimento e leitura assistida

Data: 2026-08-01  
Estado: implementado, validado e empacotado na release 0.17.0.

## Objetivo

Transformar Cards e Pesquisa num percurso coerente que permita descobrir uma área,
seguir pré-requisitos, pesquisar a biblioteca local e consultar cada resultado em três
níveis: resumo, explicação simplificada com rigor e conteúdo normal. O utilizador deve
conseguir resolver termos desconhecidos no próprio leitor, sem abandonar a aplicação.

## Princípios aplicados

1. Local-first e anónimo; a rede nunca é necessária para consultar o catálogo.
2. Prática antes da teoria nos percursos executáveis.
3. Conteúdo pedagógico e sínteses escritos de raiz pelo Aprendix.
4. Obras externas guardadas como metadados, ligação oficial e síntese original; sem
   copiar livros ou artigos protegidos.
5. Texto integral apenas para ficheiros que o utilizador forneceu e ingeriu localmente.
6. A versão simplificada preserva fórmulas, pressupostos e limitações e identifica-se
   sempre como síntese automática.

## Árvore curricular

- Programação e Computação
  - fundamentos, Python, POO, estruturas de dados, algoritmos clássicos;
  - engenharia de software, bases de dados, web, sistemas/redes/DevOps.
- Matemática e Dados
  - álgebra linear, cálculo, probabilidade/estatística, otimização;
  - ciência e engenharia de dados.
- Inteligência Artificial
  - fundamentos de IA e ML clássico/probabilístico/ensembles;
  - ANNs, deep learning, CNNs, RNNs, Transformers e IA generativa;
  - visão computacional, NLP e aprendizagem por reforço;
  - agentes autónomos, arquiteturas, memória, multiagente e avaliação;
  - IA responsável, explicável, privada e robusta.
- Áreas Aplicadas
  - finanças, saúde/bioinformática, robótica, jogos, recomendação;
  - séries temporais, cibersegurança, computação científica e edge/mobile.

Cada nó possui ordem recomendada, descrição, atalhos “Começar” e “Aprofundar”,
contagem de cards/fontes e relação pai-filho. Um filtro num ramo inclui todos os seus
descendentes.

## Pesquisa e leitor

O pipeline combina:

1. filtro hierárquico por ramo;
2. BM25 e embeddings q8 locais;
3. Reciprocal Rank Fusion e reranking cruzado compacto;
4. fontes curadas por autor/área;
5. síntese extrativa citada;
6. expansão do resultado com chunks adjacentes;
7. resumo hierárquico, pontos essenciais e matemática guiada;
8. glossário contextual detetado no texto;
9. bibliografia relacionada pelo ramo curricular.

A assistência gerada fica encriptada em SQLite e é reutilizada. Uma pergunta específica
gera uma síntese temporária orientada à pergunta sem alterar o original.

## Fontes externas curadas

O catálogo inclui, entre outras, fontes oficiais de Cormen/Leiserson/Rivest/Stein,
Hastie/Tibshirani/Friedman, Murphy, Goodfellow/Bengio/Courville, Sutton/Barto,
Russell/Norvig, Vaswani et al., He et al., Yao et al., Shinn et al. e Stanford HAI.
As referências usam páginas oficiais, DOI ou arXiv; guardam apenas ficha bibliográfica e
síntese original Aprendix.

## Desktop

- Cards: seleção por árvore, tecnologia, tema e cluster; modo livre/recomendado.
- Pesquisa: árvore, atalhos, filtros existentes e resultados expansíveis.
- Leitor: separadores Resumo, Versão simples e Conteúdo normal; tutor de conceitos e
  bibliografia orientada; abertura explícita da fonte oficial.

## Mobile

- Base lite versionada com a mesma árvore e bibliografia essencial.
- Cards recomendados/livres filtráveis por ramo.
- Pesquisa offline, atalhos e leitor em Kivy/Android.
- Pesquisa e leitor equivalentes no shell nativo Toga/iOS.
- Execução de código continua restrita aos seis exercícios Python validados; cards
  conceptuais abrem o leitor em vez de fingirem ter um exercício executável.

## Critérios de aceitação

- Migração SQLite idempotente e sem órfãos.
- Pelo menos 40 áreas, autores/fonte primária nas áreas críticas e atalhos em todos os nós.
- Todos os chunks locais classificados em pelo menos uma área.
- Pesquisa por ramo devolve conteúdo local e bibliografia relevante.
- Resultado local abre as três vistas e apresenta conceitos quando aplicável.
- Mobile funciona totalmente offline e mantém a base abaixo de 200 MB.
- Testes unitários, funcionais, suite completa, integrity check, smoke visual e validação
  dos artefactos aprovados antes da entrega.
