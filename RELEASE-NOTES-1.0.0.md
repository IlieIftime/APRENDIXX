# Aprendix 1.0.0

Primeira release integrada do ambiente local-first de aprendizagem.

- Academia com 12 percursos, progressão adaptativa, avaliações, projetos e portefólio local.
- Pesquisa híbrida BM25+dense, reranking, clusters, leitor normal/resumido/simplificado, dicionário e bibliografia orientada.
- IDE com execução/correção isolada, debugger, lint, testes públicos/ocultos/property-based, CopyKate e Pomodoro.
- Tutor offline fundamentado e analisador local de texto, código, pseudocódigo e imagens com confirmação de OCR.
- Cards autorais com referências e quatro sinais de utilidade; Sudoku e Minesweeper independentes do mastery.
- Catálogo expandido para 12 percursos/156 unidades, 96 cards autorais e dicionário com 142 entradas e 180 aliases explícitos.
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

Consulta `VALIDATION-1.0.0.md` para resultados medidos e limitações de validação física.
