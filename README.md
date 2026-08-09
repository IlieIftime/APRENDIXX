# Aprendix 1.0.0

Validated release artefacts and the full sprint audit are recorded in
[`VALIDATION-1.0.0.md`](VALIDATION-1.0.0.md). O pacote Android desta release é
`dist/mobile/Aprendix-1.0.0-android-arm64-release.apk`.

Aprendix is a local-first, privacy-by-design programming learning MVP for
desktop, Android, and iOS. Practice is stored on-device, the adaptive engine is
auditable, and network synchronization is optional and metadata-only.

## Delivered scope

All twelve planned sprints are represented:

1. DDD package layout, strict Pydantic contracts, SQLite migrations, AES-256-GCM
   field encryption, and transactional repositories.
2. Idempotent event ingestion, atomic attempt/event recording, three stable
   starter exercises, and an interactive CLI.
3. Per-user knowledge statistics, event-to-node mapping, co-occurrence edges,
   Thompson/UCB + 1PL IRT recommendations, and loopback graph snapshots.
4. Safe exercise templates, compatible randomized constraints, faded guidance,
   and a quantized-NLP port with deterministic rule-based fallback.
5. CopyKate edit n-grams, three structural alternatives, bounded AST diffs,
   explanations, and policy-gated isolated subprocess execution.
6. Optional Kivy GUI, native BeeWare/Toga iOS shell, and an offline D3
   knowledge-graph view with vendored assets.
7. Proficiency-aware structural token completion, 25/50/90/120-minute focus
   timers, edit provenance, prompt variation, and explanation-based anti-copy.
8. Encrypted LRU/TTL cache, deterministic metadata sync merge/queue, PyInstaller,
   Buildozer, and Briefcase configuration.
9. Premium card navigation, explanatory cards with local images/code, mastery
   dashboard, and asynchronous filtered search UI.
10. PDF/JPG OCR/notebook/Python ingestion, a specialist exercise parser,
    quantized offline embeddings, encrypted chunks/vectors, and provenance.
11. Hybrid local search with metadata filters, bounded HTTPS fallback,
    extractive synthesis, and optional loopback-only Ollama synthesis.
12. A POO-capable AST policy, isolated dynamic tests, deterministic scoring,
    and extracted exercises linked into the adaptive graph.

Desktop integration 12.1–12.4 is wired end-to-end:

- BM25 + quantized dense retrieval, reciprocal-rank fusion, compact joint
  reranking, persisted HDBSCAN clusters, technologies and themes;
- recommended/free card navigation and the interactive D3 graph in Dashboard;
- fixed milestones, A2 prompt variations, embedded Python IDE, isolated Run
  and Correct actions, encrypted local projects and immediate A1 updates;
- CopyKate, structural autocomplete, 25/50/90/120 focus timers, anti-copy
  justification, encrypted draft cache and metadata-only offline sync queue.

The desktop curriculum now exposes 12 guided tracks, 156 practice-first units,
108 theoretical/practical/hybrid assessments, 12 local project templates,
fixed milestone gates, and an encrypted glossary whose 142 canonical concepts
are linked into the 175-node skill graph. The UI
offers persistent dark/light themes and dictionary lookup from both its own
screen and the embedded IDE.

The independent `mobile/` subtree ships a deliberately smaller offline seed:
102 hierarchical cards, 34 curated sources, 92 search shortcuts, 135 glossary
entries plus 180 explicit aliases, six executable practical challenges and six
theory checks. Android
uses an AST interpreter that never calls
`exec`, `eval`, `compile`, subprocesses, files or the network; attempts and quiz
feedback are encrypted with a DEK protected by Android Keystore. The iOS shell
uses Keychain (`ThisDeviceOnly`), native notifications and haptics through the
bridge integrated by the macOS build script.

Release 1.0.0 additionally quarantines complete publications accidentally
appended to an indexed PDF, provides 96 original “Sabias que?” facts, adds
ranked dictionary lookup with aliases and guarded web fallback, fixes
scrolling/open-source/tutor interactions, adds local IDE diagnostics and timed
assessment modes, and introduces the final non-animated Games tab (Sudoku and
Minesweeper, three difficulties). See [`PLAN-0.18.0.md`](PLAN-0.18.0.md).

The searchable taxonomy includes Python and its main frameworks/data ecosystem,
SQL, Java, NoSQL, HTML, CSS, JavaScript, React, Bootstrap and Go. In this desktop
MVP only Python code is executable; the other technologies are documentation and
navigation tracks until dedicated sandboxes are implemented.

## Architecture

```text
Presentation  ──→  Application  ──→  Domain
      │                  ↑
      └── composition ───┤
Infrastructure ──────────┘
```

`aprendix.bootstrap` is the composition root. Application services depend on
protocols, while SQLite, encryption, HTTP, cache, subprocess, and GUI details
remain adapters.

Important modules:

- `application/graph.py`: graph worker and Bandit + IRT recommender;
- `application/content_orchestrator.py`: exercise and hint orchestration;
- `application/copykate*.py`: imitation, alternatives, and AST explanations;
- `application/mobile.py`: completion, focus, and anti-copy logic;
- `application/sync.py`: metadata-only merge contracts;
- `application/knowledge.py`: dashboard, hybrid retrieval, and safe synthesis;
- `application/smart_corrector.py`: AST/test correction orchestration;
- `infrastructure/ingestion.py`: PDF, OCR, chunking, and local embeddings;
- `infrastructure/db/knowledge_repository.py`: encrypted RAG/vector storage;
- `infrastructure/db/`: migrations and repositories;
- `infrastructure/sandbox/`: learner-code policy and child runner;
- `presentation/`: CLI, Kivy shell, local HTTP endpoint, and D3 view.

## Development

Python 3.11 or newer is required.

```powershell
python -m venv .venv
python -m pip install -e ".[dev]"
python -m pytest
```

Run the CLI:

```powershell
aprendix
```

Run the GUI, with automatic CLI fallback when Kivy is unavailable:

```powershell
aprendix-gui
```

CLI source entry is multiline and ends with a line containing only `END`.

## Instalação Windows por duplo clique

Executa `Instalar-Aprendix.bat`. O instalador:

1. cria uma venv dedicada em `%LOCALAPPDATA%\AprendixBuild\venv-desktop-1.0.0`;
2. instala Kivy, OCR, clustering, PyInstaller e as dependências do projeto;
3. executa a suite de testes;
4. produz os EXE e copia a instalação autónoma para
   `%LOCALAPPDATA%\Programs\Aprendix\1.0.0`;
5. executa o self-test do EXE já instalado e cria `Aprendix.lnk` no Ambiente de Trabalho;
6. abre a aplicação após uma instalação bem-sucedida.

Depois da instalação, a venv não precisa de ser ativada manualmente. Abre a
aplicação pelo atalho ou diretamente através do EXE na pasta instalada. O
instalador mantém automaticamente o helper de sandbox junto do executável.

Para uma reinstalação totalmente limpa, executa primeiro
`Desinstalar-Aprendix.bat`. O desinstalador lê e valida os manifestos
`installation.json`, remove as instalações e as venvs Aprendix antiga/atual e
elimina apenas o atalho que aponte para a pasta oficial. A base de dados e o
progresso são preservados; só são removidos quando se passa explicitamente a
opção `-RemoveUserData`.

## Local ingestion and smart search

Cards e Pesquisa incluem agora uma árvore curricular com 12 percursos e 156 unidades, atalhos
recomendados, bibliografia curada e um leitor com resumo, versão simplificada rigorosa,
conteúdo normal e tutor de conceitos. A arquitetura e critérios encontram-se em
`PLAN-KNOWLEDGE-NAVIGATION.md`.

After local, bibliographic and Web fusion, search consolidates duplicate documents
and strictly respects the requested result limit. Curated references count as local
evidence, so a sufficient bibliographic answer never activates the network.

The explicit `aprendix-ingest` command scans the configured sources, computes
streaming SHA-256 fingerprints, skips duplicates, extracts PDF/OCR text without
executing source content, creates quantized local vectors, and stores encrypted
chunks, cards, exercises, and provenance in SQLite. Ingestion never runs
automatically at application startup.

```powershell
aprendix-ingest
aprendix-ingest --dry-run --max-files 20
aprendix-cluster --min-cluster-size 5
```

Search supports technology, theme, HDBSCAN cluster, author preference,
theory/exercise/paper, complexity, and publication dates. It searches locally
first; the Web option starts disabled and permits a
bounded fallback only when local confidence is low. Set
`APRENDIX_OLLAMA_MODEL` to the name of an already installed local Ollama model
to enable local-LLM synthesis. Without it, deterministic extractive synthesis
remains fully offline.

## Local graph endpoint

The adapter binds only to loopback and requires an explicit user UUID:

```python
from aprendix.bootstrap import build_runtime
from aprendix.presentation.graph_http import GraphSnapshotServer

runtime = build_runtime()
provider = runtime.graph_snapshot_service.get_snapshot
with GraphSnapshotServer(provider, port=8765) as server:
    input(f"GET {server.url}?user_id={runtime.user.id}\nPress Enter to stop.")
```

## Security boundaries

- Display names, event payloads, submitted source, output, cache values, cache
  indexes, and sync queues use authenticated AES-256-GCM encryption.
- Encryption keys are stored separately through the `KeyStore` protocol.
  Desktop uses a separate local key file. Android wraps a random data key with
  a non-exportable Keystore key; iOS stores its data key in Keychain as
  `AfterFirstUnlockThisDeviceOnly`. Host key files require an explicit test-only
  opt-in and are never selected by mobile entry points.
- Field encryption is not whole-file SQLCipher encryption. Table names,
  relationships, timestamps, and other non-sensitive metadata remain visible.
- Submitted Python is parsed against a conservative AST policy, then executed
  only in `python -I -S` child processes with time/output limits. POSIX adds
  address-space, CPU, file-size, and file-descriptor limits.
- The subprocess runner is defense-in-depth for a single-user desktop product,
  not a container, virtual machine, or kernel sandbox. Windows builds attach the
  child to a Job Object with process-memory, CPU-time and kill-on-close limits;
  POSIX builds apply `resource` limits. Multi-tenant execution still requires an
  external OS sandbox.
- Learner source and output never enter sync metadata. No remote transport is
  enabled by default.

Runtime database and key files belong in the platform application-data
directory, never in this OneDrive-backed source tree.

## Packaging

Desktop:

```powershell
python -m pip install -e ".[dev,desktop-build,gui]"
./scripts/build_desktop.ps1
```

Android, from Linux/macOS or WSL2:

```bash
bash mobile/scripts/setup_android_wsl.sh   # first setup in Ubuntu/WSL2
bash mobile/scripts/build_android.sh
```

The reproducible Android toolchain is pinned to python-for-android
`v2026.05.09`, Python 3.11.14, Kivy 2.3.1, API 35 and NDK r28c. The resulting
single, non-debuggable release APK is copied to `dist/mobile/`; install it by
transferring that one file to the device and allowing installation from the
chosen file manager. It contains no `INTERNET` permission and is signed with
the persistent local release identity kept outside the repository.

iOS with Toga/Briefcase, from macOS with Xcode:

```bash
bash mobile/scripts/build_ios.sh
```

The iOS command creates the Briefcase Xcode project, integrates the native
Keychain/notifications/haptics bridge, and builds it. Signing, device install,
archiving, and any Ad Hoc IPA export are completed in Xcode; a provisioning
profile and a macOS/Xcode host are mandatory. See `INSTALL-MOBILE.md`.

Release verification:

```powershell
./scripts/verify_release.ps1
```

D3 7.9.0 is vendored under `presentation/assets`; its ISC license is included
as `D3-LICENSE.txt`.
