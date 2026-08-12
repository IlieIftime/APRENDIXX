# Validação final — Aprendix 1.0.0

Data: 12 de agosto de 2026
Ambiente de release: Windows 11, Python 3.12.10, PyInstaller 6.22.0

## Resultado executivo corrigido

Este documento regista o baseline técnico 1.0.0 do Plano Mestre AAA.
A regressão automatizada, os gates 14–17/19–20 e o self-test Windows passaram. A
Iteração 19 portou para Android/iOS o percurso unidade→IDE→correção→evidência e
reconstruiu o APK com a base governada atual. Não foram encontradas falhas
críticas abertas no ambiente Windows nem nos gates automáticos mobile.

As metas editoriais mensuráveis CURR-1 estão agora aprovadas. Permanecem gates
externos: a paridade mobile ainda não foi validada em dispositivos reais e
faltam ensaios físicos de screen reader, DPI misto,
toque, bateria e desempenho prolongado. As matrizes automáticas de contraste,
DPI lógico, multimodal adversarial e soak limitado estão aprovadas. O broker semanal já está
ligado por opt-in, allowlist, assinatura, quarentena e rollback. A fonte de
verdade quantitativa passa a ser
`python scripts/audit_aaa.py`; o auditor usa um perfil temporário e nunca inclui
texto, código ou identificadores do utilizador.

Por isso, qualquer linha abaixo que diga "integrado" significa que existe um
caminho funcional e testado no baseline, não que todos os critérios do respetivo
gate AAA estejam fechados.

## Auditoria por fase

| Fase | Resultado integrado | Evidência/gate |
| --- | --- | --- |
| 0 — Fundação | baseline, métricas locais, diagnóstico e 14 feature flags | schema 37 íntegro; runtime `healthy` |
| 1 — UX | temas escuro/claro/contraste, escala tipográfica, navegação, histórico e comandos | contraste WCAG/touch/DPI lógico automatizados; smoke visual do EXE |
| 2 — Progresso | evidência, mastery, recomendações, plano semanal e metas pessoais | 3 398 nós; recomendações sempre ligadas a exercícios; testes e self-test |
| 3 — Academia | 12 percursos, prática antes da teoria, avaliações, milestones e projetos | 248 unidades, 3 063 exercícios e 20 projetos/modelos; catálogo testado |
| 4 — Pesquisa | BM25, dense quantizado, fusão, reranking, clusters, filtros e explicabilidade | benchmark SEARCH-1 aprovado |
| 5 — Atualizações | broker opt-in, fontes governadas, quarentena, `.apxpack` Ed25519, importação transacional, preview, rollback e cache | testes de adulteração, traversal, ativação e rollback |
| 6 — IDE | editor, lint, execução/correção/debug isolados, testes e CopyKate | sandbox real no EXE, stdout `42`, memória limitada |
| 7 — Conteúdo UI | dicionário rankeado, 3 343 entradas + 9 757 aliases, 1 131 cards autorais e bibliografia orientada | 1 121 fontes únicas; 71/71 objetivos com pelo menos três fontes |
| 8 — Tutor | recuperação local fundamentada, estratégias, cache e recusa em avaliação | resposta com evidência no self-test |
| 9 — Projetos | projetos guiados, versões, avaliação e portefólio local | 12 templates e testes de exportação/avaliação |
| 10 — Plataformas | Windows instalado; Android APK release; fonte/bridge iOS | Windows aprovado; gates físicos mobile abaixo |
| 11 — Multimodal | texto, código, pseudocódigo, OCR com confirmação e oito ações | benchmark OCR; PNG/JPEG/WebP/degradação e 64 imagens hostis testados |
| 12 — Games | Sudoku e Minesweeper, três dificuldades, pausa sem mastery | grelhas/estado/isolamento testados |
| 13 — Hardening | threat model, fuzz/adversarial, SBOM, auditoria, hashes e recuperação | gates automáticos e desktop aprovados |
| 13.1 — Integração final | responsividade, compilador pedagógico, previsão semanal, IDE/debug, bibliografia, updates e paridade mobile | 16/16 jornadas automatizadas aprovadas em `ITERATION-13-AUDIT-1.0.0.json` |
| 14 — Percurso no IDE | microteoria→prática, três modos de enunciado, ajuda gradual e feedback por tentativa | 59/59 práticas ligadas a teoria e exemplo; gate aprovado em `ITERATION-14-AUDIT-1.0.0.json` |
| 15 — Aprendizagem adaptativa | sessão por objetivo, diagnóstico, remediação, solução validada, avaliações e transferência | seis gates aprovados em `ITERATION-15-AUDIT-1.0.0.json` |
| 16 — Fontes governadas | catálogo oficial/local sem cópia integral ou referências inventadas | 1 121 fontes e cobertura bibliográfica 1,0 em `ITERATION-16-AUDIT-1.0.0.json` |
| 17 — Atualizações | ciclo semanal opt-in, allowlist, preview, assinatura, cache, quarentena e rollback | gate offline reprodutível aprovado em `ITERATION-17-AUDIT-1.0.0.json` |
| 19 — Mobile final | unidade no IDE, correção protegida, diagnóstico, evidência autónoma/transferência e seed governada | gate lógico aprovado; APK assinado validado em `ITERATION-19-AUDIT-1.0.0.json` |
| 20 — Desktop Learning Workspace | consulta separada de crédito, analytics explicáveis, grafo filtrado, documentos estruturados, IDE integrado e catálogo completo | gate agregado em `ITERATION-20-AUDIT-1.0.0.json`; gates físicos declarados no relatório |

## Testes e qualidade

- A suíte automatizada integral do checkout final terminou com **exit code 0**.
  A validação conserva o log de execução como fonte de verdade, sem repetir aqui
  uma contagem que possa ficar desatualizada quando os gates de release mudam.
- O aviso cria deliberadamente uma entrada ZIP duplicada para provar que um pack
  hostil é rejeitado; não corresponde a comportamento de produção.
- Foram exercitados testes unitários, integração, transações, migrações,
  idempotência, corrupção/rollback, parsers, sandbox, pesquisa, perfil portátil,
  currículo, UI controller, Android runtime e jogos.
- O PyInstaller produziu e instalou a aplicação `onedir` e o helper de sandbox
  separado. O self-test do **EXE instalado** terminou com `passed=true`,
  integridade SQLite `ok`, schema 37, sandbox `ok`, 1 827 factos autorais e 20
  projetos, além de dicionário, tutor, jogos e funcionalidades alargadas.
- `scripts/verify_release_manifest.py` terminou com exit code 0: o manifesto
  coincide com o runtime instalado e com os inputs de build registados.

### Iteração 13

O auditor agregado executou 16 jornadas e aprovou 16: base de dados, currículo,
IDE/sandbox, diagnóstico estático, pesquisa híbrida, dicionário, cards, grafo,
tutor, snippets, games, compilador pedagógico, progresso adaptativo,
bibliografia, responsividade e paridade funcional mobile. Foram compilados
 4 462 itens pedagógicos, sem quarentenas críticas no catálogo distribuído; os
71/71 objetivos têm pelo menos uma ligação bibliográfica e todos os cards
autorais são associados a um nó do grafo. O relatório não contém texto, código,
identificadores ou caminhos do utilizador.
- A paridade automatizada mobile confirmou 1 137 cards, 12 cursos e 50 unidades
  no payload lite regenerado para esta iteração.
- Smoke visual real: janela `Aprendix` responsiva e conteúdo Curso/IDE renderizado,
  sem o anterior `KeyError: surface`, sem janela duplicada e sem tela preta.
- Captura: `build/installed-no-resize-15s.png`.

### Iteração 14

O gate dedicado aprovou os cinco critérios: percurso prático presente, 59/59
práticas com microteoria, 59/59 com exemplo orientador, renderização dos modos
Simples/Guiado/Técnico e escada ordenada localização→conceito→estratégia→exemplo
análogo. Um teste de integração confirma ainda a contagem persistida das
tentativas e dos pedidos de ajuda. Em avaliação, a política bloqueia pistas
estratégicas e exemplos; nenhum feedback contém a asserção de um teste oculto.

### Iterações 15–17

O ciclo de aprendizagem foi exercitado de ponta a ponta: sessão retomável e
cifrada, quatro falhas progressivas, diagnóstico de sintaxe, remediação e
solução de referência validada pelo corretor. Aprovação independente e de
transferência foram registadas separadamente; existem 177 itens de avaliação.

O catálogo passou para 1 121 fontes únicas: 34 fontes primárias, 166 registos
locais apenas por metadados e 921 entradas da documentação oficial Python. Os
71 objetivos têm pelo menos três fontes. O broker semanal foi validado sem rede
real com consentimento, política Wi-Fi, HTTPS allowlisted, antevisão explícita,
assinatura/hash, ativação atómica e cache de sete dias.

### Iteração 20

O gate desktop constrói um perfil temporário e reconcilia analytics de 7/30/90
dias com queries SQLite independentes. Verifica as 248 unidades consultáveis, a
ausência de XP/progresso numa aprovação bloqueada, os capstones por percurso, o
grafo inicial limitado a atividade real e o detalhe do nó. Também valida a
materialização das 59 aulas, 59 práticas da espinha e 20 projetos em blocos
tipados, proveniência exata dos 1 827 cards, assets por hash, profundidade do top
500 do dicionário e o holdout de pesquisa com 120 consultas. As métricas medidas
e tempos da máquina de release estão no JSON, que não contém dados do utilizador.
Os **11/11 checks** independentes estão aprovados e o resultado agregado é
`passed=true`.

O contrato responsivo e a composição integrada da UI são automatizados. A
revisão física em três resoluções a 100–200% DPI, screen reader e DPI misto
continua explicitamente externa; não é convertida num falso resultado automático.
O gate automatizado Windows fecha ainda a suíte integral, a geração PyInstaller
da aplicação e do sandbox, o self-test instalado e a verificação do manifesto.

## Benchmarks

### Pesquisa local

50 golden queries: Recall@10 **0,9667**, MRR **0,8660**, NDCG@10 **0,8893**,
P95 **438,61 ms**. Gate `<500 ms`: **aprovado**.

O benchmark de operações sobre perfil novo mediu pesquisa comum em P95 **94,19 ms**
e dicionário exato em P95 **19,81 ms**, já com 1 131 cards e 3 343 entradas.

### OCR local

4 imagens digitais reproduzíveis: precisão global **98,75%**, pior caso
**98,08%**. Gate `>=95%`: **aprovado**. As imagens temporárias são removidas.

### Multimodal adversarial

PNG, JPEG comprimido, WebP lossless, rotação de 1,5° e baixo contraste foram
processados sem crash e com confirmação obrigatória; no dataset sintético desta
release todos obtiveram 100% de correspondência. Os 64 payloads binários
malformados foram rejeitados. Gate automatizado: **aprovado**.

### Acessibilidade e DPI

Os três temas passam contraste de texto normal `>=4,5:1`, foco `>=3:1` e texto
sobre acento `>=4,5:1`. Touch targets lógicos mínimos de 44 dp foram calculados
para 100%, 125%, 150%, 175% e 200% DPI. Gate automático: **aprovado**; screen
reader, multi-monitor/DPI misto e toque físico permanecem gates de hardware.

### Soak local limitado

200 ciclos de pesquisa/dicionário/health: zero falhas, zero threads residuais,
integridade SQLite `ok`, 90 918 bytes de crescimento retido e 1 054 221 bytes
de pico Python rastreado. O soak prolongado em hardware fraco continua externo.

### Arranque Windows

- Aviso nativo de preparação: P95 **719 ms**.
- Primeiro frame real em cinco execuções: **2 070–2 303 ms**.
- Medição da janela após a primeira inicialização: P95 **2 254 ms**.
- Primeira abertura fria observada: **4 041 ms**; o plano exclui esta primeira
  inicialização do orçamento P95 de 3 s.

O desktop passou de um executável autoextraível de ~13,2 s para uma instalação
`onedir`, mantendo um único `Aprendix.exe` como ponto de entrada. Os restantes
ecrãs são criados apenas na primeira navegação e os índices só são reconstruídos
quando a sua população fica desatualizada.

## Artefactos Windows

- Executável instalado: `C:\Users\iliei\AppData\Local\Programs\Aprendix\1.0.0\Aprendix.exe`
- SHA-256: `63132FAD26192F92A88E5F3B2756EC7062CCDD5901A418EAA006AF3E4B15A394`.
- Runtime `_internal`: 320 ficheiros, 268 410 441 bytes, tree SHA-256
  `E944613204F1C939CAD52DCB7D390735EA46246D1DA93F76B346B64BCFC407D8`
- Sandbox SHA-256: `E374117E0B95EB42199EAF5DA67138EF3D07E59AC7AAF1B37D33402F914B508D`
- Atalho do Ambiente de Trabalho validado contra o executável 1.0.0.
- O desinstalador em `DryRun` detetou 0.17.0, 0.18.0 e 1.0.0 pelos manifestos,
  sem remover ficheiros e preservando os dados pessoais por omissão.

O EXE não tem assinatura Authenticode por não existir um certificado Windows
privado disponível neste ambiente. O Windows SmartScreen pode, por isso, pedir
confirmação. O hash e a árvore completa estão no manifesto da release.

## Artefacto Android

- `dist/mobile/Aprendix-1.0.0-android-arm64-release.apk`
- 30 849 511 bytes
- SHA-256: `23F34CF68C6C1AA8C7273C1FD66B35AF8589D0A9AFF4ED5D1B475CBBB38EEE75`
- Assinatura APK Scheme v2, RSA-4096; certificado SHA-256
  `bde9cfad47f6b5cc629c003d8b72ce27759eb8640efd567f5952411e3000f1be`.
- Android mínimo API 26, target/compile API 35, ABI `arm64-v8a`, release não
  debuggable.
- Sem permissão `INTERNET`; apenas notificações, vibração e a permissão interna
  não exportada gerada pelo Android.
- Python 3.11.14, Kivy 2.3.1, python-for-android 2026.05.09, NDK 28c e OpenSSL 3.
- APK validado por `unzip -t`, `apksigner`, `aapt`, inspeção de permissões,
  payload, ABI, bibliotecas e base `knowledge-lite`.
- A base incorporada é schema 6, conteúdo `2026.08-iteration19`, com 1 121
  fontes, 50 unidades e 3 315 conceitos; o hash interno coincide com o manifesto.
- Unidades abrem no IDE móvel e só são concluídas pelo corretor AST local; treino,
  avaliação protegida, previsão/reflexão cifradas e evidência de transferência
  passaram no gate automatizado.

Não havia dispositivo Android/ADB ligado. A instalação e a jornada tátil num
telefone real permanecem um gate físico externo; o BAT de ADB valida a ligação
antes de instalar.

## iOS/iPadOS

A subtree mobile contém a shell Toga, persistência, contratos, Keychain,
notificações/haptics e o script Briefcase/Xcode. Windows não consegue executar
`xcodebuild`, produzir um IPA assinado ou validar um iPhone. O gate final exige
um Mac com Xcode, uma identidade de assinatura e um dispositivo real, seguindo
`INSTALL-MOBILE.md`.

## Segurança e dependências

- SBOM CycloneDX criado.
- `pip-audit`: **79 dependências, 0 vulnerabilidades conhecidas** no snapshot.
- SQLite sensível cifrado com AES-256-GCM; perfil portátil v2 usa
  PBKDF2-HMAC-SHA256 + AES-GCM; Android usa Keystore/JCA nativos.
- Packs de conteúdo exigem assinatura Ed25519, hashes, manifesto e validação de
  caminhos antes da ativação atómica.
- Código do utilizador é filtrado por AST e executado no helper isolado com
  timeout e Job Objects/limites de memória; os testes não encontraram bypass.
- O APK não inclui a dependência Python `cryptography` nem OpenSSL 1.1.

## Gates ainda necessários

Para declarar o Plano Mestre AAA concluído em todas as plataformas faltam gates
externos que não podem ser simulados neste host.

Gates desktop automatizados fechados nesta iteração:

1. catálogo com 1 121 fontes reais/metadados oficiais e IDs/URLs únicos;
2. cobertura tripla de fontes nos 71 objetivos e auditor AAA quantitativo aprovado;
3. regressão integral, self-test do EXE instalado e smoke de janela responsiva;
4. build PyInstaller da aplicação e sandbox, manifesto/hashes verificados;
5. atualização semanal assinada, explícita e reversível.

O smoke final usou um perfil temporário isolado e captura DPI-aware a
1222×956 físicos/150% DPI. O EXE apresentou o Painel, a aula e a prática sem o
ecrã preto ou as sobreposições anteriormente observadas; manteve um processo,
respondeu em três amostras consecutivas e encerrou por `WM_CLOSE` sem terminação
forçada. Este gate não substitui a matriz física multi-monitor abaixo.

Gates externos:

1. instalar o APK num Android ARM64/API 26+ e executar smoke tátil/offline;
2. num Mac, executar `mobile/scripts/build_ios.sh`, assinar no Xcode e testar num
   iPhone/iPad;
3. opcionalmente assinar o EXE com um certificado Authenticode de publicação.
4. validar screen reader, DPI misto, toque, soak prolongado e bateria em hardware real.

Os gates externos dependem de hardware, sistema operativo ou credenciais e não
podem ser certificados apenas pela máquina Windows de desenvolvimento.
