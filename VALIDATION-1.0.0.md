# Validação final — Aprendix 1.0.0

Data: 9 de agosto de 2026  
Ambiente de release: Windows 11, Python 3.12.10, PyInstaller 6.21.0

## Resultado executivo corrigido

Este documento regista um **baseline técnico 1.0.0**, não a conclusão integral
do Plano Mestre AAA. A regressão automatizada e a instalação física Windows
passaram; o APK Android release foi construído, assinado e validado
estaticamente. Não foram encontradas falhas críticas abertas no ambiente
Windows testado.

Permanecem, porém, gates internos e externos abertos. Em particular, as metas
editoriais CURR-1 ainda não foram atingidas, a paridade mobile não foi validada
em dispositivos reais e faltam ensaios físicos de screen reader, DPI misto,
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
| 0 — Fundação | baseline, métricas locais, diagnóstico e 14 feature flags | schema 33 íntegro; runtime `healthy` |
| 1 — UX | temas escuro/claro/contraste, escala tipográfica, navegação, histórico e comandos | contraste WCAG/touch/DPI lógico automatizados; smoke visual do EXE |
| 2 — Progresso | evidência, mastery, recomendações, plano semanal e metas pessoais | 3 398 nós; recomendações sempre ligadas a exercícios; testes e self-test |
| 3 — Academia | 12 percursos, prática antes da teoria, avaliações, milestones e projetos | 248 unidades, 3 063 exercícios e 20 projetos/modelos; catálogo testado |
| 4 — Pesquisa | BM25, dense quantizado, fusão, reranking, clusters, filtros e explicabilidade | benchmark SEARCH-1 aprovado |
| 5 — Atualizações | broker opt-in, fontes governadas, quarentena, `.apxpack` Ed25519, importação transacional, preview, rollback e cache | testes de adulteração, traversal, ativação e rollback |
| 6 — IDE | editor, lint, execução/correção/debug isolados, testes e CopyKate | sandbox real no EXE, stdout `42`, memória limitada |
| 7 — Conteúdo UI | dicionário rankeado, 3 343 entradas + 9 757 aliases, 1 131 cards autorais e bibliografia orientada | API pública da stdlib, conceitos centrais, cards e fontes testados |
| 8 — Tutor | recuperação local fundamentada, estratégias, cache e recusa em avaliação | resposta com evidência no self-test |
| 9 — Projetos | projetos guiados, versões, avaliação e portefólio local | 12 templates e testes de exportação/avaliação |
| 10 — Plataformas | Windows instalado; Android APK release; fonte/bridge iOS | Windows aprovado; gates físicos mobile abaixo |
| 11 — Multimodal | texto, código, pseudocódigo, OCR com confirmação e oito ações | benchmark OCR; PNG/JPEG/WebP/degradação e 64 imagens hostis testados |
| 12 — Games | Sudoku e Minesweeper, três dificuldades, pausa sem mastery | grelhas/estado/isolamento testados |
| 13 — Hardening | threat model, fuzz/adversarial, SBOM, auditoria, hashes e recuperação | gates automáticos e desktop aprovados |

## Testes e qualidade

- Regressão integral atual: **293 passed**, 1 aviso esperado. A cobertura é regenerada por `scripts/verify_release.ps1` na build final.
- O aviso cria deliberadamente uma entrada ZIP duplicada para provar que um pack
  hostil é rejeitado; não corresponde a comportamento de produção.
- Foram exercitados testes unitários, integração, transações, migrações,
  idempotência, corrupção/rollback, parsers, sandbox, pesquisa, perfil portátil,
  currículo, UI controller, Android runtime e jogos.
- Self-test do binário instalado: `passed=true`, integridade SQLite `ok`, schema
  33, sandbox `ok`, limite de memória ativo, 1 131 cards autorais, dicionário, tutor, jogos,
  projetos e funcionalidades alargadas operacionais.
- Smoke visual real: janela `Aprendix` responsiva e conteúdo Curso/IDE renderizado,
  sem o anterior `KeyError: surface`, sem janela duplicada e sem tela preta.
- Captura: `build/installed-no-resize-15s.png`.

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
- SHA-256: consultar `RELEASE-MANIFEST-1.0.0.json`, gerado depois do self-test do EXE instalado.
- Runtime `_internal`: 321 ficheiros, 265 596 590 bytes, tree SHA-256
  `7da89b65e504cfe7ec1b0bab1110aef3d317ab4f0ba9676bfd903fccc2f54b26`
- Sandbox SHA-256: `04C6328F2A95257136ECE0E239650C92A520E87CD097FAC1B28A7B94EF89EE7D`
- Atalho do Ambiente de Trabalho validado contra o executável 1.0.0.
- O desinstalador em `DryRun` detetou 0.17.0, 0.18.0 e 1.0.0 pelos manifestos,
  sem remover ficheiros e preservando os dados pessoais por omissão.

O EXE não tem assinatura Authenticode por não existir um certificado Windows
privado disponível neste ambiente. O Windows SmartScreen pode, por isso, pedir
confirmação. O hash e a árvore completa estão no manifesto da release.

## Artefacto Android

- `dist/mobile/Aprendix-1.0.0-android-arm64-release.apk`
- 30 216 583 bytes
- SHA-256: `9C1869F0271DC1622CB3A2B26C262CCF772988F80CD28E2B8059CC8918FF0F3F`
- Assinatura APK Scheme v2, RSA-4096; certificado SHA-256
  `bde9cfad47f6b5cc629c003d8b72ce27759eb8640efd567f5952411e3000f1be`.
- Android mínimo API 26, target/compile API 35, ABI `arm64-v8a`, release não
  debuggable.
- Sem permissão `INTERNET`; apenas notificações, vibração e a permissão interna
  não exportada gerada pelo Android.
- Python 3.11.14, Kivy 2.3.1, python-for-android 2026.05.09, NDK 28c e OpenSSL 3.
- APK validado por `unzip -t`, `apksigner`, `aapt`, inspeção de permissões,
  payload, ABI, bibliotecas e base `knowledge-lite`.

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

Para declarar o Plano Mestre AAA concluído faltam gates internos de produto e
gates externos que não podem ser simulados neste host.

Gates internos prioritários:

1. expandir as 200 fontes bibliográficas reais e deduplicadas até à meta editorial de 1 000, sem fabricar referências;
2. executar revisão humana ampla do conteúdo importado e das referências;
3. validar screen reader, DPI misto e UX tátil em hardware real;
4. executar soak prolongado, bateria e medições em hardware fraco/dispositivos físicos.

Gates externos:

1. instalar o APK num Android ARM64/API 26+ e executar smoke tátil/offline;
2. num Mac, executar `mobile/scripts/build_ios.sh`, assinar no Xcode e testar num
   iPhone/iPad;
3. opcionalmente assinar o EXE com um certificado Authenticode de publicação.

Os gates externos dependem de hardware, sistema operativo ou credenciais. Eles
não substituem os gates internos ainda abertos, registados pelo auditor AAA.
