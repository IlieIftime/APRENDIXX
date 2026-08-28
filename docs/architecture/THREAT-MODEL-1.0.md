# Aprendix 1.0 — threat model

Data de revisão: 2026-08-09. Âmbito: desktop Windows, APK Android e fontes iOS.

## Ativos e fronteiras

- O perfil, progresso, código, OCR e histórico do tutor permanecem no dispositivo.
- Campos sensíveis usam AES-256-GCM e associated data por registo; a chave fica separada da base de dados.
- Código do aluno atravessa uma fronteira de processo. A política AST é defesa em profundidade; o limite de segurança é o subprocesso isolado, o timeout e, em Windows, um Job Object com memória/CPU e encerramento de descendentes.
- Imagens, `.apxprofile` e `.apxpack` são entradas não confiáveis. Há limites de tamanho/dimensões, validação de estrutura, hashes e autenticação antes de promoção.
- O updater conectado não faz parte do processo principal. A aplicação permanece operacional sem rede.

## Ameaças e controlos

| Ameaça | Controlos | Risco residual |
| --- | --- | --- |
| Execução arbitrária no IDE | `python -I -S`, builtins mínimos, imports/I/O/reflexão bloqueados, subprocesso, timeout, output cap, Job Object/RLIMIT | Zero-day do runtime/OS |
| Escape por testes ocultos/debugger | IPC JSON autenticado, namespace limitado, expressões sem calls/atributos privados, mesmos limites de processo | Bugs nativos de dependências |
| Pack adulterado/zip bomb/path traversal | Ed25519, SHA-256, JSON canónico, allowlist MIME/sufixo, limites, proibição de symlink/duplicados, staging atómico e rollback | Compromisso da chave de assinatura |
| Imagem malformada ou gigante | MIME mágico, ≤20 MB/25 MP, decoder local, ficheiro temporário eliminado, OCR requer confirmação | Vulnerabilidade no decoder/OCR |
| Roubo ou alteração de perfil | AES-GCM, ficheiro de chave com permissões restritas, `.apxprofile` v2 com PBKDF2-HMAC-SHA256 (600 000 iterações) + AES-GCM; leitor desktop compatível com v1/Scrypt | Máquina já comprometida enquanto a app está aberta |
| Exfiltração | Android sem permissão INTERNET; desktop só usa adapters allowlisted sob ação explícita; tutor/OCR locais | Links externos abertos pelo utilizador |
| Perda/corrupção | Transações SQLite, WAL, backup consistente com checksum, migrações, integrity/foreign-key checks | Perda simultânea de disco e backup |
| Conteúdo incorreto/contaminado | Fontes allowlisted, proveniência, fronteiras de publicação, cards autorais, quarentena/editorial gate | Erro editorial não detetado |

## Operação de chaves

A chave de campos e a base de dados formam um par. O backup consistente inclui ambos; deve ser guardado num suporte cifrado e offline. Uma rotação requer re-encriptação transacional de todos os campos e só deve ser feita por uma ferramenta de migração versionada — nunca substituindo manualmente `fields.key`. Em Android/iOS, a chave está no Keystore/Keychain e não é exportada; a transferência usa uma chave derivada da frase-passe.

No APK, AES-GCM é executado pelo Android Keystore/JCA através do bridge nativo. O payload Python não inclui `cryptography`; o runtime Android está fixado no toolchain python-for-android 2026.05.09 e OpenSSL 3, evitando o OpenSSL 1.1 obsoleto que existia no protótipo anterior.

## Evidência de hardening

Testes cobrem inputs binários aleatórios, adulteração e traversal de packs, perfis truncados/adulterados, imagens inválidas, timeout, memória, output, imports, reflexão e expressões de debug. O SBOM e os hashes dos artefactos acompanham a release. Não se declara validação física iOS sem Mac/Xcode e dispositivo real.
