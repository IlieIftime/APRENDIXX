# Aprendix

> A privacy-first, local-first environment for learning programming through guided practice, feedback, and measurable progress.

Aprendix is an adaptive programming-learning platform for desktop and mobile. It combines structured lessons, an embedded Python IDE, local code execution, explainable progress tracking, source-grounded learning content, and offline-first storage.

The application is designed for learners who want to practice programming without depending on a permanent cloud account or sending their code and learning history to a remote service.

## Highlights

- **Adaptive learning paths** based on objectives, attempts, mastery, and transfer evidence.
- **Integrated Python IDE** with execution, correction, debugging, linting, tests, drafts, projects, and code history.
- **Protected assessments** with public, hidden, and property-based tests.
- **Explainable feedback** that distinguishes syntax errors, logic errors, edge cases, and incomplete solutions.
- **Offline tutor** that retrieves local evidence before generating guidance.
- **Hybrid local search** combining lexical retrieval, dense features, ranking, filters, and source provenance.
- **Learning catalogue** with lessons, theory cards, exercises, glossary entries, projects, and curated references.
- **Local content ingestion** for PDFs, images, notebooks, and Python files.
- **OCR-assisted analysis** for code, pseudocode, and technical material.
- **Encrypted local profile** for attempts, drafts, projects, tutor history, progress, and sensitive application data.
- **Desktop, Android, and iOS support** with platform-specific security adapters.
- **Offline games** such as Sudoku and Minesweeper that remain separate from learning mastery.
- **Optional signed content updates** with preview, validation, quarantine, activation, and rollback.

## Why Aprendix?

Most programming-learning tools separate reading, practice, code execution, and progress tracking across different systems. Aprendix brings those activities into one local learning loop:

1. Learn a concept.
2. Predict how a solution should work.
3. Implement it in the embedded IDE.
4. Run or submit the code locally.
5. Receive bounded and explainable feedback.
6. Remediate the underlying misconception.
7. Demonstrate independent understanding and transfer.
8. Continue with the next recommended objective.

The system is intentionally designed around practice and evidence rather than passive content consumption.

## Current scope

Aprendix currently focuses on Python as its executable learning environment.

The catalogue also contains material and navigation tracks covering areas such as:

- Python and the Python standard library;
- pytest and Python tooling;
- algorithms and data structures;
- object-oriented programming;
- SQL and databases;
- JavaScript, HTML, and CSS;
- React and Bootstrap;
- Go;
- data engineering and machine learning concepts;
- software engineering and systems topics.

Only Python code is executed by the current desktop learning environment. Other technologies are currently represented as learning content and navigation tracks rather than fully isolated execution sandboxes.

## Platform support

| Platform | Status | Main technology |
| --- | --- | --- |
| Windows desktop | Supported build path | Python, Kivy, PyInstaller |
| Android | Sideloadable release path | Kivy, Buildozer, python-for-android |
| iOS/iPadOS | Build-ready source path | BeeWare/Toga, Briefcase, Xcode |
| Linux/macOS development | Supported for development and mobile tooling | Python and shell tooling |

The repository contains separate build and installation workflows for each platform.

## Core features

### Adaptive curriculum

The curriculum is organized around learning tracks, units, objectives, exercises, assessments, milestones, and guided projects.

The learning engine records local evidence such as:

- exercise attempts;
- successful and failed evaluations;
- time spent;
- hint requests;
- predictions and reflections;
- independent passes;
- transfer attempts;
- assessment results.

Recommendations are generated from persisted learning evidence and are intended to remain explainable to the learner.

### Integrated IDE

The desktop and mobile learning flows include an embedded editor for Python exercises and guided units.

The IDE supports:

- code editing;
- local execution;
- isolated correction;
- static diagnostics;
- debugging support;
- public and hidden tests;
- property-based tests;
- code drafts;
- project files and versions;
- structural autocomplete;
- prompt variation;
- focus timers;
- dictionary lookup;
- tutor access;
- learning-session state.

### Smart correction and remediation

Submissions are parsed and evaluated through a policy-controlled correction pipeline.

Feedback can identify different classes of problems, including:

- syntax errors;
- runtime errors;
- logic errors;
- edge cases;
- missing constructs;
- incomplete test coverage;
- structural or quality issues.

Assessment feedback is deliberately restricted. Hidden test details are not exposed as a shortcut to the solution.

### Local tutor and knowledge search

Aprendix searches local and curated sources before considering optional external retrieval.

The knowledge layer supports:

- lexical search;
- quantized local feature embeddings;
- reciprocal-rank fusion;
- reranking;
- filters by technology, theme, author, content type, complexity, and date;
- source provenance;
- summaries;
- simplified explanations;
- normal reading mode;
- glossary lookup;
- tutor responses grounded in retrieved evidence.

Optional local Ollama synthesis can be enabled through `APRENDIX_OLLAMA_MODEL`. Without that setting, the application uses deterministic local synthesis.

### Content ingestion

The ingestion pipeline can process:

- PDF documents;
- JPEG and JPG images;
- Jupyter notebooks;
- Python source files.

It performs bounded extraction, normalization, hashing, chunking, local feature generation, provenance recording, and encrypted persistence.

Ingestion is explicit and does not run automatically when the application starts.

```powershell
aprendix-ingest
aprendix-ingest --dry-run --max-files 20
aprendix-cluster --min-cluster-size 5
```

### Privacy and local storage

Aprendix stores the learning profile locally by default.

Sensitive values are protected with authenticated encryption. Depending on the platform, encryption keys are stored through:

- a separate protected desktop key file;
- Android Keystore;
- iOS Keychain with device-only accessibility.

The following types of data may be encrypted locally:

- display names;
- event payloads;
- submitted source code;
- execution output;
- drafts;
- projects;
- tutor history;
- cache values;
- profile transfer data;
- synchronization queue data.

The default architecture does not upload learner source code, execution output, or private learning history.

Optional synchronization is metadata-oriented and does not transmit learner source code or execution output.

## Security model

Aprendix applies multiple defensive controls:

- strict Pydantic contracts at application boundaries;
- SQLite migrations and transactional repositories;
- AES-256-GCM field encryption;
- authenticated associated data for encrypted records;
- AST validation for learner code;
- bounded execution time and output;
- isolated desktop subprocesses;
- Windows Job Object limits;
- POSIX resource limits where available;
- Android Keystore-backed encryption;
- iOS Keychain-backed encryption;
- signed content packs using Ed25519;
- path traversal and archive validation;
- content quarantine before activation;
- atomic content activation and rollback.

### Important security limitation

The desktop subprocess runner is defense-in-depth for a single-user application. It is not a container, virtual machine, or kernel-level sandbox.

Aprendix should not be used as a multi-tenant untrusted-code execution service without an additional operating-system or infrastructure-level isolation layer.

On Android, learner exercises are interpreted by a restricted AST interpreter. The mobile interpreter intentionally does not use `exec`, `eval`, `compile`, subprocesses, filesystem access, or network access for learner code.

## Architecture

Aprendix follows a layered architecture:

```text
Presentation
     │
     ▼
Application services
     │
     ▼
Domain contracts and rules
     ▲
     │
Infrastructure adapters
```

The composition root is `aprendix.bootstrap`.

Application services depend on protocols and contracts rather than concrete infrastructure. Database, encryption, search, OCR, HTTP, cache, subprocess, and GUI implementations remain behind adapters.

## Repository structure

```text
src/aprendix/
  application/       Use cases, learning services, curriculum, search, tutor,
                     correction, progress, projects, games, and contracts
  domain/            Stable domain types and persisted enumerations
  infrastructure/   SQLite, encryption, ingestion, OCR, search, sandbox,
                     packaging, updates, and platform adapters
  presentation/     CLI, Kivy desktop UI, graph viewer, assets, and UI services
  bootstrap.py      Runtime composition root and application entry points

mobile/
  aprendix_mobile/   Mobile runtime, UI, encrypted state, restricted execution,
                     OCR, projects, notifications, and platform integration
  android/           Buildozer/python-for-android hooks, recipes, and Java bridge
  ios/               Native Keychain, OCR, notifications, and haptics bridge
  scripts/           Android and iOS build and validation scripts
  assets/            Bounded mobile knowledge seed and manifests

tests/
  unit/              Unit tests for application, infrastructure, and presentation
  mobile/            Mobile runtime, packaging, and security tests
  security/          Boundary and adversarial tests

scripts/
  audit_*.py         Aggregate release and iteration audits
  benchmark_*.py     Reproducible local benchmarks
  build_*.ps1        Desktop and platform build helpers
  verify_*.ps1       Release and installation verification
  install_windows.ps1
  uninstall_windows.ps1

packaging/
  *.spec             PyInstaller specifications and packaged helpers

docs/
  architecture/      Architecture, security, and threat-model documentation
  guides/            Installation, recovery, and platform guides
  plans/             Active and reusable product plans
  releases/          Release notes and validation reports
  legacy/iterations/ Historical iteration specifications

reports/
  *.json              Aggregate, privacy-safe audit and benchmark evidence
```

## Requirements

For development:

- Python 3.11 or newer;
- a virtual environment;
- a supported operating system for the selected target;
- optional platform-specific build tools.

The core runtime requires:

- `cryptography`;
- `pydantic`.

Optional dependency groups provide GUI, OCR/RAG, clustering, desktop packaging, BeeWare, and mobile packaging support.

## Development setup

Create a virtual environment and install the development dependencies:

```powershell
python -m venv .venv
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Run the test suite:

```powershell
python -m pytest
```

Run the command-line application:

```powershell
aprendix
```

Run the desktop GUI:

```powershell
aprendix-gui
```

The GUI falls back to the CLI when the optional Kivy dependency is unavailable.

You can also launch the package directly:

```powershell
python -m aprendix
```

## Desktop build

Install the desktop build dependencies:

```powershell
python -m pip install -e ".[dev,desktop-build,gui,rag]"
```

Build the Windows desktop application:

```powershell
./scripts/build_desktop.ps1
```

The generated application is placed under:

```text
dist/Aprendix/
```

The main executable is:

```text
dist/Aprendix/Aprendix.exe
```

### Windows installation

For a complete local installation on Windows:

```text
Instalar-Aprendix.bat
```

The installer creates a dedicated build environment, runs the test suite, builds the desktop application, installs the application under the local user profile, performs a self-test, and can create a desktop shortcut.

To remove the installation:

```text
Desinstalar-Aprendix.bat
```

User data and progress are preserved by default. Removing user data requires an explicit option.

## Android build

Android builds require Linux, macOS, or WSL2.

Install the mobile build dependencies:

```bash
python -m pip install -e '.[dev,mobile-build]'
```

For the first WSL2 setup:

```bash
bash mobile/scripts/setup_android_wsl.sh
```

Build a development APK:

```bash
bash mobile/scripts/build_android.sh
```

Build a signed release APK:

```bash
bash mobile/scripts/build_android_release.sh
```

Validate an APK:

```bash
bash mobile/scripts/validate_android.sh
```

The Android release configuration currently targets:

- Android API 35;
- minimum API 26;
- `arm64-v8a`;
- Python 3.11;
- Kivy;
- python-for-android;
- NDK r28c.

The release APK is designed to operate without the `INTERNET` permission. Physical installation and touch validation must still be performed on a real Android device.

See [`docs/guides/INSTALL-MOBILE.md`](docs/guides/INSTALL-MOBILE.md) for installation, signing, and device instructions.

## iOS build

iOS builds require:

- macOS;
- Xcode;
- an Apple development identity or Apple Account;
- Python 3.11 or newer;
- Briefcase;
- a physical device for final installation testing.

Build the iOS project:

```bash
bash mobile/scripts/build_ios.sh
```

The script:

1. creates an iOS virtual environment;
2. installs the required dependencies;
3. runs the mobile test suite;
4. creates the Briefcase Xcode project;
5. integrates the native Keychain, OCR, notifications, and haptics bridge;
6. compiles the project.

The generated Xcode project is placed under:

```text
build/aprendix/iOS/
```

Signing, installation, archiving, and IPA export are completed in Xcode.

## Release verification

Run the release verification workflow from PowerShell:

```powershell
./scripts/verify_release.ps1
```

The repository also contains aggregate validation reports under [`reports/`](reports/README.md).

The main release documentation is:

- [`docs/releases/RELEASE-NOTES-1.0.1.md`](docs/releases/RELEASE-NOTES-1.0.1.md)
- [`docs/releases/VALIDATION-1.0.1.md`](docs/releases/VALIDATION-1.0.1.md)
- [`docs/guides/INSTALL-MOBILE.md`](docs/guides/INSTALL-MOBILE.md)
- [`docs/README.md`](docs/README.md)

## Testing and quality

The test suite covers:

- application services;
- curriculum and learning sessions;
- adaptive progress and recommendations;
- search and catalogue quality;
- tutor behaviour;
- correction and remediation;
- SQLite migrations and repositories;
- encryption;
- sandbox and grading policies;
- content packs and rollback;
- OCR and ingestion;
- accessibility calculations;
- desktop integration;
- Android runtime and packaging;
- mobile state and profile transfer;
- games;
- release audits and bounded soak tests.

Privacy-safe audit and benchmark scripts generate aggregate evidence without including learner source code, private answers, user identifiers, or user paths.

Examples:

```powershell
python scripts/audit_aaa.py
python scripts/audit_iteration20.py
python scripts/benchmark_baseline.py
python scripts/benchmark_soak.py
```

## Data locations

Runtime databases, encryption keys, caches, and progress data should be stored in the platform application-data directory.

Do not place runtime databases or key files inside the repository, especially when the repository is located in a synchronized folder.

Create a local profile backup with:

```powershell
python scripts/backup_profile.py --label my-backup
```

Profile export and import are also available through the application interface using an encrypted passphrase-protected format.

## Content updates

Content updates are opt-in.

A content update can be:

1. discovered through an allowlisted HTTPS registry;
2. previewed before installation;
3. downloaded within configured size limits;
4. verified using hashes and Ed25519 signatures;
5. quarantined and validated;
6. activated atomically;
7. rolled back if required.

Content packs must not be treated as arbitrary executable code.

## Project status

Aprendix is an actively developed local-first learning platform and should be considered a product prototype/release candidate rather than a hosted production service.

The Windows desktop release path has automated build and self-test coverage. Android and iOS still require final validation on physical devices for platform-specific concerns such as:

- installation;
- touch interaction;
- screen readers;
- mixed-DPI displays;
- long-running performance;
- battery consumption;
- device-specific rendering;
- iOS signing and provisioning.

See [`VALIDATION-1.0.1.md`](docs/releases/VALIDATION-1.0.1.md) for the complete validation record and known external gates.

## Documentation

The documentation is organized by purpose:

- [`docs/architecture/`](docs/architecture/) — architecture and security design;
- [`docs/guides/`](docs/guides/) — installation and recovery;
- [`docs/plans/`](docs/plans/) — product and technical plans;
- [`docs/releases/`](docs/releases/) — release notes and validation;
- [`docs/legacy/iterations/`](docs/legacy/iterations/) — historical iteration records;
- [`reports/`](reports/) — aggregate audit and benchmark evidence.

## Contributing

Before submitting a change:

1. create or activate a Python 3.11+ virtual environment;
2. install the development dependencies;
3. run the complete test suite;
4. update relevant documentation;
5. avoid adding private data, absolute user paths, generated profiles, keys, or release secrets;
6. preserve the local-first and privacy-by-design boundaries;
7. add tests for new application, security, packaging, or platform behaviour.

Recommended validation command:

```powershell
python -m pytest
```

For platform-specific changes, also run the relevant build or validation script.

## License

Aprendix is distributed under the license declared in [`LICENSE`](LICENSE).

Before publishing a release, keep the repository metadata, `pyproject.toml`, package metadata, and `LICENSE` file aligned. The current repository contains conflicting license declarations that should be resolved explicitly.

## Acknowledgements

Aprendix includes vendored D3 assets for the local knowledge-graph view. The applicable D3 license is included at:

[`src/aprendix/presentation/assets/D3-LICENSE.txt`](src/aprendix/presentation/assets/D3-LICENSE.txt)
