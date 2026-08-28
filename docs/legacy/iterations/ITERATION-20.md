# Iteração 20 — Desktop Learning Workspace

A Iteração 20 fecha primeiro o produto Windows e mantém a subtree `mobile/`
congelada. A consulta de conteúdo e o crédito pedagógico passaram a ser estados
independentes: todas as 248 unidades podem ser abertas, mas uma prática antecipada
é registada apenas como exploração. O crédito, XP e milestones só são atribuídos
depois de uma nova aprovação elegível e são idempotentes. Capstones exigem o
template, percurso, milestones e avaliação correspondentes; progresso legado
incompatível é preservado, sinalizado e excluído dos desbloqueios.

## Workspace e progresso

O Painel foi dividido em Resumo, Atividade, Competências, Percursos, Plano e
Grafo. As séries de 7/30/90 dias e intervalo personalizado partilham filtros e
usam apenas nós curriculares no denominador. Os seis indicadores apresentam
definição e denominador. O grafo integrado mostra atividade do período e,
opcionalmente, a fronteira elegível, com um limite de 150 nós/300 arestas.
Relações de pré-requisito, progressão, afinidade e coocorrência têm semântica,
direção, origem e explicação próprias.

No IDE, aula, prática e projeto são modos explícitos. A primeira visita abre a
aula; a prática usa editor e enunciado lado a lado com divisor persistente e
alternância em largura reduzida. O terminal começa recolhido e abre no separador
pedido por Executar, Corrigir ou Debug. `Ctrl+F`/`Ctrl+H` usam a barra inline; F1
e duplo clique abrem o dicionário sobre o workspace. O modo Projeto tem brief,
ficheiros, rubrica, milestones, gravação e avaliação próprios, sem reutilizar os
testes do exercício anterior.

## Conteúdo, cards e pesquisa

O schema 37 introduz documentos pedagógicos por blocos, assets locais
endereçados pelo SHA-256, fontes por documento, fontes exatas por card, exemplos
de dicionário e um índice FTS do catálogo completo. Foram materializados os
documentos estruturados das 59 aulas, 59 práticas da espinha e 20 projetos. O
fallback de conteúdo legado preserva títulos, listas, código, fórmulas, tabelas,
figuras e callouts sempre que são reconhecíveis.

O catálogo contém 1 827 cards autorais. Todas as áreas-folha têm pelo menos 12
cards e quatro formatos; áreas prioritárias de matemática, ML, DL, visão, NLP,
RL e agentes têm pelo menos 24. Cada card tem proveniência exata e os visuais
originais Aprendix são SVG locais, seguros e com texto alternativo. O top 500 do
dicionário tem pelo menos dois exemplos e duas referências por termo.

A pesquisa passou a abranger cards, exercícios, aulas, projetos, glossário e
fontes. O Reader recebe blocos normalizados em vez de depender apenas de texto
PDF monolítico. O holdout v2 contém 120 consultas distintas e hard negatives.
Os valores medidos da máquina de release ficam no relatório JSON, em vez de
serem duplicados neste documento.

## Gate reproduzível

```powershell
$env:PYTHONPATH = "src"
python scripts/audit_iteration20.py
```

O auditor cria um perfil temporário, mede apenas agregados e valida integridade
SQLite/schema, consulta versus crédito, capstones, analytics 7/30/90 contra SQL,
grafo filtrado, documentos estruturados, cards/assets, dicionário, pesquisa e o
contrato do workspace. O resultado é `ITERATION-20-AUDIT-1.0.0.json`: os 11
checks independentes estão aprovados e o resultado agregado é `passed=true`.

Os testes focados podem ser repetidos com:

```powershell
python -m pytest -q tests/test_iteration20_audit.py `
  tests/unit/application/test_iteration20_credit_integrity.py `
  tests/unit/application/test_iteration20_analytics.py `
  tests/unit/infrastructure/test_iteration20_visible_graph.py `
  tests/unit/application/test_pedagogical_documents.py `
  tests/unit/infrastructure/test_pedagogical_catalog_repository.py
```

## Release Windows validada

- A suíte automatizada integral do checkout final terminou com exit code 0.
- O PyInstaller produziu a aplicação desktop em modo `onedir` e o helper de
  sandbox como executáveis separados; ambos foram instalados na versão 1.0.0.
- O self-test executado através do `Aprendix.exe` instalado terminou com
  `passed=true`: schema 37 íntegro, sandbox operacional, 1 827 factos autorais
  e 20 projetos disponíveis.
- O manifesto determinístico inclui a aplicação, o sandbox, o registo de
  instalação, o relatório desta iteração e a documentação. A verificação dos
  hashes contra a instalação e os inputs de build terminou com exit code 0.
- O smoke visual DPI-aware do EXE final, num perfil local temporário, confirmou a
  sequência splash → janela `Aprendix`, um único processo, três amostras
  responsivas e encerramento normal. Foram inspecionados o Painel, a aula e a
  prática a 1222×956 físicos/150% DPI: separadores, cabeçalho compacto, botão
  `Corrigir`, editor vazio e terminal recolhido ficaram sem sobreposição.

## Limites declarados

O gate automático não substitui revisão física em 1024×768, 1366×768 e
1920×1080 a 100–200% DPI, teste com screen reader, DPI misto em dois monitores
ou assinatura Authenticode. Esses pontos continuam assinalados como externos no
JSON. PyInstaller, self-test do EXE instalado e verificação do manifesto estão
fechados; isto não transforma os ensaios físicos acima em resultados automáticos.
