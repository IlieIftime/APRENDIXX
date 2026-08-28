# Iteração 21 — Book IDE, pesquisa e conteúdo governado

A Iteração 21 fecha a nova experiência desktop antes de retomar a versão
mobile. O IDE usa uma composição em formato de livro: editor à esquerda,
enunciado/aula/apoio à direita e um terminal transversal recolhível. Em largura
insuficiente, as duas páginas tornam-se separadores explícitos sem perder o
terminal. As ações compactas usam ícones SVG locais, nome acessível e tooltip;
texto pedagógico ambíguo continua escrito por extenso.

## Conteúdo de aprendizagem

O schema 38 introduz uma release transacional do catálogo, estado por item,
chaves canónicas de fonte, percursos profissionais N:N e políticas cifradas de
revelação. Cards legados derivados de chunks permanecem preservados como
leitura, mas ficam arquivados e não entram no deck nem na pesquisa editorial.
O lote desta iteração tem como gate acrescentar exatamente 500 fontes curadas, 1 000 cards editoriais,
1 000 entradas canónicas de dicionário, 500 exercícios e 50 projetos. Os
exercícios têm fonte, testes, solução de referência cifrada, walkthrough e
traço esperado. O auditor executa todas as 500 soluções no corretor isolado e
só aprova o lote quando cada uma passa.

Cinco circuitos profissionais partilham um núcleo Python e formam DAGs sem
ciclos: Engenharia Python/Backend, Análise de Dados, Engenharia de Dados,
Engenharia de AI/ML e Automação de Cibersegurança. Cada circuito liga etapas a
percursos, áreas e projetos; consultar conteúdo continua independente de obter
crédito sequencial.

O caso canónico “Capital acumulado” inclui a fórmula de juro composto, a tabela
de 2021–2023 para 2%, 2,5% e 3%, decomposição, solução local e traço. “Execução
esperada” descreve stdout/comportamento; “traceback” fica reservado a uma
exceção real. A solução completa é progressiva e nunca é revelada pela política
de avaliação bloqueada.

## Pesquisa, análise e apresentação

A pesquisa separa fontes/leituras, conteúdo pedagógico e cards. Consultas
técnicas gerais são source-first e conteúdo interno só lidera quando a intenção
é explicitamente Curso, Aula, Card, Exercício ou Projeto Aprendix. O holdout v3
tem 284 consultas, hard negatives e regressões para capital acumulado,
decoradores e backpropagation.

O Analisador passa a produzir diagnósticos localizados, símbolos e âmbitos,
funções/classes, tipos conservadores, CFG, grafo de chamadas, complexidade,
segurança, exceções e sugestões de testes. A análise é exclusivamente estática:
executar e traçar continua uma ação separada no sandbox.

Fórmulas são renderizadas offline com um subconjunto limitado de MathText/Agg,
cache content-addressed e alternativa falada. IDE, Cards, Pesquisa e Reader
partilham o mesmo contrato. A normalização de texto respeita o encoding Python,
UTF-8 de notebooks, charset Web, OCR e mojibake reversível; `U+FFFD` provoca
quarentena/erro em vez de ser apagado.

## Gate reproduzível

```powershell
$env:PYTHONPATH = "src"
python scripts/audit_iteration21.py
```

O comando cria um perfil temporário e escreve
`ITERATION-21-AUDIT-1.0.0.json`. O relatório contém apenas agregados. Valida
schema/integridade, release e deltas, exclusão dos cards legados, cinco DAGs,
soluções/políticas e o caso Capital acumulado, holdout v3 source-first, corpus
golden do analisador sem execução, geometria responsiva, fórmulas e texto.
No checkout final, os 14 gates ficaram aprovados. O holdout v3 mediu
Recall@10 de 0,9965, nDCG@10 de 0,9811, zero hard negatives no top 3 e P95 de
130,37 ms. As 500 soluções de referência passaram os respetivos testes no
processo isolado.

Teste focado:

```powershell
python -m pytest -q tests/test_iteration21_audit.py `
  tests/unit/application/test_iteration21_search_source_first.py `
  tests/unit/application/test_iteration21_text_normalization.py `
  tests/unit/presentation/test_iteration21_book_math.py
```

## Limites declarados

O gate automatizado não equivale a revisão física em 1024×768, 1366×768 e
1920×1080 entre 100–200% DPI, teste com screen reader/teclado/rato, dois
monitores com DPI misto ou assinatura Authenticode. O JSON mantém estes quatro
pontos como gates externos. Esta iteração também não altera nem valida por
inferência a subtree mobile; ela permanece congelada até ao fecho Windows.
