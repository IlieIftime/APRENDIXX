# Aprendix 1.0.0

Primeira release integrada do ambiente local-first de aprendizagem.

- Academia com 12 percursos, progressão adaptativa, avaliações, projetos e portefólio local.
- Pesquisa híbrida BM25+dense, reranking, clusters, leitor normal/resumido/simplificado, dicionário e bibliografia orientada.
- IDE com execução/correção isolada, debugger, lint, testes públicos/ocultos/property-based, CopyKate e Pomodoro.
- Tutor offline fundamentado e analisador local de texto, código, pseudocódigo e imagens com confirmação de OCR.
- Cards autorais com referências e quatro sinais de utilidade; Sudoku e Minesweeper independentes do mastery.
- Catálogo expandido para 12 percursos/248 unidades, 3 063 exercícios, 1 131 cards autorais e dicionário com 3 343 entradas e 9 757 aliases explícitos.
- 166 referências locais deduplicadas foram catalogadas apenas por metadados, sem copiar livros ou guardar caminhos absolutos; com fontes primárias e 921 entradas granulares da documentação oficial Python, o catálogo governado totaliza 1 121 fontes únicas.
- O núcleo Python Base/POO/Algoritmos/Estruturas de Dados recebeu 23 módulos, 2 990 variações de prática e oito projetos adicionais com proveniência bibliográfica.
- Desktop Windows, APK Android sideloadable e projeto iOS preparado para build/assinatura obrigatória em macOS.
- Packs de conteúdo Ed25519, perfil portátil cifrado, backups, telemetria estritamente local e controlos de acessibilidade.
- APK release arm64 assinado, sem permissão de Internet, com Python 3.11/OpenSSL 3 e criptografia nativa Android.
- Transferência cifrada e determinística de tentativas, revisões e unidades concluídas entre desktop e mobile.
- Packs assinados passam do broker para o catálogo pesquisável através de importação transacional, promoção de versão e rollback coerente.
- Android acrescenta seleção de imagem/câmara para OCR, barra de símbolos no IDE, orientação horizontal durante edição e pausas temporizadas em Games; a fonte iOS recebeu paridade de tutor, projetos, IDE e Games.
- OCR local com reconstrução espacial de linhas/indentação e benchmark digital reproduzível.
- OCR aceita as variantes WebP VP8/VP8L/VP8X e passa um benchmark multiformato/degradado com 64 payloads hostis rejeitados.
- Tema de alto contraste usa texto preto sobre acento amarelo; rácios WCAG e touch targets são auditados a 100–200% DPI lógico.
- Soak reproduzível de 200 ciclos cobre pesquisa, dicionário, health, memória, threads e integridade SQLite.
- Arranque Windows em `onedir`, com aviso nativo imediato, ecrãs carregados sob procura e índices reutilizados quando atuais; P95 quente de primeiro frame inferior a 3 s.
- Iteração 13 acrescenta layout responsivo testado em nove viewports, compilador
  pedagógico determinístico para 4 462 itens com quarentena efetiva, previsão
  personalizada e relatório semanal, histórico cifrado de debugger/testes e
  pistas acionáveis de erros do IDE.
- Todos os 71 objetivos curriculares estão agora ligados a bibliografia técnica;
  os 1 131 cards autorais estão ligados ao grafo adaptativo. Atualizações remotas
  exigem uma antevisão explícita de tamanho, fontes, percursos e rollback antes
  da instalação, sem upload de dados do utilizador.
- O mobile apresenta atividade e tendência dos últimos sete dias e reutiliza as
  explicações de depuração locais. O gate automatizado ponta a ponta da Iteração
  13 cobre 16 jornadas desktop/mobile sem incluir dados privados no relatório.
- A Iteração 14 liga microteoria, exemplo e prática no IDE; acrescenta enunciados
  Simples/Guiados/Técnicos e ajuda gradual baseada nas tentativas persistidas,
  com proteção de avaliações e sem exposição de testes ocultos.
- A Iteração 15 persiste o ciclo por objetivo, diagnostica a causa da falha,
  propõe remediação e só revela uma solução cifrada depois de quatro falhas em
  treino e de esta passar integralmente no corretor. Avaliações permanecem protegidas.
- As Iterações 16–17 fecham a meta de fontes do plano e validam atualizações
  semanais opt-in, assinadas, limitadas, antevistas e reversíveis.
- A Iteração 19 leva as 1 121 fontes ao seed mobile e liga cada unidade ao IDE:
  conclusão por correção protegida, diagnóstico por tentativa, avaliação sem
  fuga de testes e evidência cifrada de autonomia e transferência. O APK ARM64
  foi reconstruído e a shell iOS recebeu o mesmo percurso pedagógico.
- A Iteração 20 fecha primeiro o desktop: todas as 248 unidades são consultáveis,
  mas treino bloqueado é apenas exploração e não atribui XP/progresso. O Painel
  ganhou analytics explicáveis e grafo semântico filtrado; o IDE integra aula,
  enunciado, editor, terminal, procura/substituição, dicionário e projetos.
- O schema 37 acrescenta documentos por blocos, proveniência exata por card,
  assets locais por hash, exemplos de glossário e pesquisa do catálogo completo.
  O desktop contém 1 827 cards equilibrados, 100 visuais originais e um holdout
  externo de 120 consultas com hard negatives.

Consulta `VALIDATION-1.0.0.md` para resultados medidos e limitações de validação física.
