# Validação final — Aprendix 0.18.0

Data: 2 de agosto de 2026. Estado: aprovado no ambiente Windows de construção.

## Resultado funcional

- Navegação desktop com scroll visível/arrastável, tema claro/escuro e correção de escala DPI.
- Dicionário local-first com 101 entradas no desktop, incluindo `else`, ranking top-k, referências navegáveis e fallback web tratado quando não há correspondência exata.
- Cards substituídos por 48 factos originais “Sabias que?”, filtráveis, com feedback A1, navegação, verso e fontes. Conteúdo detetado após a fronteira de uma publicação anexada foi colocado em quarentena.
- Pesquisa híbrida BM25 + vetorial de 384 dimensões + fusão/reranking, clusters, filtros e leitor com resumo, modo matemático simplificado, conteúdo selecionável, recursos visuais e tutor por duplo clique.
- IDE com enunciados limpos, copiar/redimensionar, diagnóstico de sintaxe/indentação, temporização, sandbox isolado, correção e avanço após aprovação.
- Plano de estudo, avaliações teóricas em treino/avaliação temporizada, marcos e grafo navegável com zoom, arrasto e seleção.
- Aba Games integrada somente depois da validação pedagógica: Sudoku e Minesweeper, sem animações e com três dificuldades.
- Paridade funcional relevante no Android; shell Toga/iOS atualizado no código-fonte para Cards, leitor, dicionário e Games.

## Testes e verificações

- `176 passed`, `0 failed`; cobertura global por ramos/linhas: 65%.
- `18 passed` no subconjunto mobile.
- Compilação de bytecode: aprovada.
- Varredura por `TODO`, `FIXME`, `NotImplementedError` e execução dinâmica fora das fronteiras autorizadas: aprovada.
- Self-test do EXE instalado: schema 14, SQLite `ok`, 48 cards autorais, entrada `else`, Games e sandbox aprovados; o sandbox devolveu `42` com exit code 0.
- Smoke test do EXE instalado: processos responsivos após 10 segundos; captura DPI-aware confirmou dashboard preenchido, layout sem sobreposição e scrollbar visível.
- Instalador: criou venv isolada, instalação 0.18.0, manifesto e atalho correto.
- Desinstalador: dry-run leu os manifestos 0.17.0 e 0.18.0, identificou ambas as venvs e preservou os dados do utilizador.

## Integridade do conhecimento

- 389 documentos, 20 627 chunks cifrados, embeddings e linhas taxonómicas.
- 19 908 chunks aceites e integralmente ligados à árvore; 719 chunks em quarentena e zero ligações de chunks rejeitados.
- 392 clusters, 5 052 elos bibliográficos, 259 exercícios, 27 itens de avaliação, 46 áreas e 24 fontes curadas.
- SQLite: `integrity_check=ok`; violações de chaves estrangeiras: 0.
- Seed móvel: 54 cards, 94 termos, 24 fontes, 46 áreas, 92 atalhos; o SHA-256 dentro do APK coincide com o ficheiro-fonte.

## Artefactos

| Artefacto | SHA-256 | Estado |
| --- | --- | --- |
| `dist/Aprendix.exe` | `01F9BAD926679430079E173A1BB4E5289976EE3FAD81C6E982E65F3D2A3A2576` | versão 0.18.0; self-test aprovado |
| `dist/AprendixSandbox/AprendixSandbox.exe` | `2BB052FFD7605D3F8B00E3C53E34A1091F2C2C9A61669DB951A8D589DA75C36C` | helper isolado aprovado |
| `dist/mobile/Aprendix-0.18.0-android-arm64-debug.apk` | `EBCE41D6BFB7F0A477B5F65970079250CA7D19D814A26EF3C035FCE5E2C4B080` | APK íntegro e assinatura v2 válida |

O APK declara Android API 26–34, ABI `arm64-v8a` e não solicita `INTERNET`. É uma build de sideload assinada com certificado de depuração. O EXE não tem assinatura Authenticode; o Windows pode apresentar SmartScreen.

## Limites externos honestos

- Não havia dispositivo Android ligado, portanto não foi possível automatizar o smoke test em hardware físico. O manifesto, ABI, permissões, assinatura, arquivo e base empacotada foram validados.
- Um APK não instala em iPhone/iPad. O projeto iOS exige macOS, Xcode e assinatura Apple; nenhuma IPA é alegada como construída neste Windows.
- A abertura de referências depende da aplicação externa associada e, para URLs, de conectividade. O ensino, a pesquisa local, o IDE, os cards e os jogos continuam disponíveis offline.
