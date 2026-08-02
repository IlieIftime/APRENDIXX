# Aprendix 0.16.0 — relatório de implementação e validação

Data: 2026-08-01

## Resultado executivo

- Desktop Windows: implementado, empacotado e validado por self-test do próprio EXE.
- Android: APK único `arm64-v8a`, instalável e assinado com chave de debug; estrutura, assinatura, manifesto, permissões e conteúdo interno validados.
- iOS: código, configuração Briefcase e integração nativa preparados. A criação e assinatura de um IPA não foram executadas porque exigem macOS, Xcode, identidade Apple e provisioning profile.
- Testes: 165 aprovados, 0 falhados; compilação de bytecode e scans de release aprovados; cobertura combinada de 65%.

## Matriz dos sprints

| Sprint | Implementação verificada | Evidência principal |
|---|---|---|
| 1 | DDD, contratos Pydantic, migrações transacionais, SQLite e AES-256-GCM por campo | 11 migrações; integridade SQLite `ok`; 0 violações FK |
| 2 | ingestão idempotente, gravação atómica de tentativa/evento, exercícios iniciais e CLI | testes de repositório/eventos e self-test empacotado |
| 3 | estatísticas A1, grafo, recomendação Thompson/UCB + IRT e snapshots loopback | testes unitários; 242 nós na base local |
| 4 | templates seguros, variações A2 e fallback determinístico | testes do orquestrador e persistência das variações |
| 5 | CopyKate, alternativas estruturais, diffs AST e sandbox de subprocesso no desktop | sandbox empacotada produziu `42`; políticas AST aprovadas |
| 6 | GUI Kivy, shell Toga e grafo D3 local | smoke visual sem ecrã preto nem duplicação de janela |
| 7 | autocomplete estrutural, Pomodoro 25/50/90/120, proveniência e anti-copy | testes de sessões/telemetria e controlos ligados à UI |
| 8 | cache encriptada LRU/TTL, fila de sync de metadados e packaging | testes de cache/sync; EXE e helper separados |
| 9 | cards, dashboard, navegação premium e pesquisa assíncrona | 20 335 cards e controlos sem sobreposição no smoke visual |
| 10 | ingestão PDF/imagem/OCR/notebook/Python, embeddings q8 e proveniência | 387 documentos, 20 571 chunks e 20 571 embeddings |
| 11 | pesquisa BM25+dense, RRF, reranking cruzado compacto, filtros, fallback HTTPS limitado e síntese local | pesquisa real: 5 evidências, 2 tópicos semelhantes, sem web; warm 0,676 s |
| 12 | corretor POO/AST, testes dinâmicos isolados, scoring e exercícios extraídos no grafo | 259 exercícios; 23 com testes executáveis |
| 12.1 | pipeline híbrido e clustering HDBSCAN | 392 clusters; cobertura integral dos 20 571 chunks |
| 12.2 | cards recomendado/livre, temas e navegação de grafo | UI ligada ao A1, taxonomia e clusters |
| 12.3 | milestones fixos, variações A2 e IDE com executar/corrigir | 4 milestones, exercícios práticos e persistência imediata |
| 12.4 | CopyKate, autocomplete, Pomodoro, anti-copy e lifecycle cache/sync | integração desktop e testes de aceitação |
| 13 | caminhos móveis e execução sem subprocesso | intérprete AST allow-list, sem `eval`, `exec`, import, ficheiros ou rede |
| 14 | swipe cards, modo livre/recomendado e clusters touch-friendly | `SwipeCard`, revisão espaçada e navegação Kivy |
| 15 | IDE móvel, code-row, completions e progresso | teclas `{ } [ ] : = def class`, output, quiz e milestone 0–10 |
| 16 | chaves do dispositivo, notificações/haptics e packaging | Keystore Android, Keychain iOS, receiver não exportado e APK validado |

## Conteúdo e relações

Base desktop real em `%LOCALAPPDATA%\Aprendix\aprendix.db`:

- 259 exercícios, dos quais 23 têm testes determinísticos executáveis.
- 4 tracks Python, 9 capítulos, 40 unidades e 27 avaliações práticas, teóricas ou híbridas.
- 20 335 cards teóricos e 38 entradas de dicionário.
- 20 571 chunks, embeddings, classificações taxonómicas e memberships de cluster — cobertura 1:1.
- 5 052 relações bibliográficas `same-cluster`, sem ligações órfãs.
- Pesquisa/classificação reconhece Python, SQL, Java, NoSQL, Django, FastAPI, Flask, NumPy, pandas, SciPy, scikit-learn, PyTorch, TensorFlow, Jupyter, HTML, CSS, JavaScript, React, Bootstrap e Go.

O currículo executável permanece deliberadamente Python (bases, POO, algoritmia e estruturas de dados), de acordo com a restrição de segurança do MVP. As tecnologias adjacentes estão disponíveis na taxonomia, pesquisa e referência; não são executadas pelo sandbox Python.

A base lite móvel contém 6 cards, 6 exercícios práticos, 6 quizzes e 10 termos. O hash da base embebida no APK coincide com a fonte. É uma seleção pequena intencional para micro-learning offline, não uma cópia dos 149 MB da base desktop.

## Validações executadas

1. `pytest`: 165 aprovados, 0 falhados.
2. Cobertura: 65% sobre 4 639 statements, sem limiar artificial de aprovação.
3. `compileall`: `src`, `mobile` e `tests` aprovados.
4. Scan de placeholders e execução dinâmica no processo host: aprovado.
5. Self-test do `Aprendix.exe`: sandbox `ok`, stdout `42`, SQLite `ok`.
6. Base desktop: `PRAGMA integrity_check=ok`; 0 violações de foreign keys.
7. APK: ZIP íntegro, APK Signature Scheme v2 verificado, package/version/API/ABI confirmados.
8. APK: não pede `android.permission.INTERNET`; pede apenas notificações, vibração e a permissão interna não exportada do AndroidX.
9. APK: `AprendixReminderReceiver` existe e tem `android:exported=false`; as três classes Java nativas aparecem nos DEX.
10. APK: módulos móveis compilados e seed DB presentes em `assets/private.tar`.
11. iOS: sintaxe dos scripts shell aprovada e o guard fora de macOS termina corretamente com código 2.
12. Instalador Windows: criou uma venv externa, recompilou, instalou numa pasta versionada e atualizou o atalho.
13. EXE instalado: self-test aprovado, janela `Aprendix` responsiva e encerramento normal confirmado.
14. Instalador Android por ADB: APK e ADB detetados, estado/autorização do dispositivo verificados e saída controlada confirmada sem dispositivo ligado.
15. Desinstalador Windows: leitura de `installation.json`, dry-run real e remoção isolada em ambiente temporário aprovados; dados do utilizador preservados.

## Artefactos e hashes

| Artefacto | Bytes | SHA-256 | Assinatura |
|---|---:|---|---|
| `dist/Aprendix.exe` | 120 607 308 | `98D2881F3D28C401FB03395A576B0445CC756BC40D84F5CBE4950267034A81FD` | sem Authenticode |
| `dist/AprendixSandbox/AprendixSandbox.exe` | 4 972 472 | `562428D430A24F3F60AE81AF511A415D6CBB056E50A06E8E28DC7DD769DCC19E` | sem Authenticode |
| `dist/mobile/Aprendix-0.16.0-android-arm64-debug.apk` | 21 910 108 | `985451EB3AFEF1D28B58765B0A07C1529E3092AC4400762AB110118AE468D60E` | Android debug, APK v2 |

## Limites que não devem ser confundidos com validação concluída

- Não havia dispositivo/emulador Android ligado; não foi possível executar um smoke test físico. O APK é debug-signed e diretamente instalável, mas não é um artefacto Play Store.
- Windows não consegue produzir nem assinar legitimamente um IPA. O build iOS final tem de ser executado num Mac com Xcode e credenciais do proprietário.
- Os EXE não têm assinatura Authenticode; o Windows pode apresentar SmartScreen até serem assinados por um certificado do proprietário.
- `graph_edges` começa vazio num perfil quase novo: as arestas adaptativas de coocorrência surgem após eventos em dois ou mais nós. As relações bibliográficas e dependências curriculares já estão populadas separadamente.
