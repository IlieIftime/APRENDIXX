# Aprendix 0.17.0 — relatório final de implementação e validação

Data: 2026-08-01  
Plataforma de validação: Windows 11, Python 3.12.10; Android toolchain em WSL.

## Resultado executivo

A árvore de conhecimento, Cards, Pesquisa, leitor pedagógico e tutor contextual estão
ligados ao runtime Desktop e ao runtime Mobile. A migração SQLite 12 foi aplicada sem
perda de dados; todos os 20 579 chunks locais possuem pelo menos uma classificação. O
plano PDF foi ingerido com oito páginas/chunks e proveniência local.

A última varredura detetou e corrigiu um defeito de fusão: a pesquisa podia ultrapassar
`max_results`, repetir o mesmo título por vários chunks e considerar bibliografia local
como insuficiente antes de tentar a Web. A resposta final consolida títulos, respeita o
limite e inclui as fontes curadas no cálculo de confiança local. O teste de regressão
integra a suite.

## Funcionalidade ligada

- 46 áreas hierárquicas, com pais, descendentes, ordem recomendada e contagens;
- 92 atalhos de pesquisa e 17 fontes primárias/curadas com síntese original;
- classificação explicável dos chunks e filtro que expande ramos inteiros;
- pesquisa BM25 + vetor q8 + RRF + reranking conjunto, clustering HDBSCAN e filtros;
- Cards livres/recomendados por área, tecnologia, tema e cluster;
- vista expandida com resumo, pontos essenciais, versão simplificada rigorosa,
  conteúdo normal, notas matemáticas, glossário contextual e bibliografia relacionada;
- cache encriptada das leituras sem pergunta; consultas orientadas não alteram o original;
- ecrãs equivalentes em Kivy/Windows, Kivy/Android e Toga/iOS;
- 46 cards, 17 fontes, 92 atalhos e 30 conceitos no seed offline mobile; apenas os seis
  desafios Python validados abrem o executor restrito.

## Base Desktop real

| Elemento | Total |
|---|---:|
| documentos / chunks / embeddings | 388 / 20 579 / 20 579 |
| chunks classificados / relações de área | 20 579 / 65 556 |
| áreas / atalhos / fontes curadas | 46 / 92 / 17 |
| theory cards / exercícios | 20 343 / 259 |
| nós do grafo / clusters | 242 / 392 |
| ligações bibliográficas | 5 052 |
| tracks / capítulos / unidades / avaliações | 4 / 9 / 40 / 27 |

`PRAGMA integrity_check` devolveu `ok`; `PRAGMA foreign_key_check` devolveu zero
violações. A versão máxima em `schema_migrations` é 12. Num dry run real de agentes
autónomos, seis resultados pedidos produziram cinco títulos únicos relevantes,
confiança local 0,713 e nenhuma chamada Web. Uma leitura local produziu 491 caracteres
de resumo, 673 de explicação simplificada, 7 924 de conteúdo original, sete conceitos e
cinco fontes relacionadas. O arranque quente do runtime mediu 0,047 s.

## Testes e varreduras

- `scripts/verify_release.ps1`: aprovado;
- pytest: **170 passed**, zero falhas, cobertura total branch-aware **66%**;
- compilação de bytecode de `src`, `mobile` e `tests`: aprovada;
- varredura `TODO|FIXME|NotImplementedError`: limpa;
- varredura de `eval/exec` fora das fronteiras de sandbox/correção: limpa;
- testes unitários e funcionais de migrações, criptografia, pesquisa, leitura, grafo,
  ingestão, curriculum, CopyKate, IDE, Android e instalação: aprovados.

## Windows

| Artefacto | Bytes | SHA-256 |
|---|---:|---|
| `dist/Aprendix.exe` | 120 641 593 | `DBD19BB1D56555AD4540F56E6968B91FE5E1B698185FC0250455CF7CB0AC331C` |
| `dist/AprendixSandbox/AprendixSandbox.exe` | 4 953 415 | `46DC4BD990A95ABBC97F08EA2E46BAB7548FD1EBE1355DED5A3CE88F56B78641` |

O instalador criou/reutilizou a venv isolada
`%LOCALAPPDATA%\AprendixBuild\venv-desktop-0.17.0`, instalou em
`%LOCALAPPDATA%\Programs\Aprendix\0.17.0`, comparou os hashes, executou o sandbox
(`stdout=42`, exit 0) e confirmou integridade SQLite `ok`. O atalho
`Aprendix.lnk` aponta para o executável 0.17.0. O smoke test do EXE instalado abriu a
janela `Aprendix`, confirmou `Responding=True` e fechou-a normalmente.

Os binários Windows não possuem assinatura Authenticode. O desinstalador foi validado
em diretório isolado e por dry run; lê os manifestos das versões antiga/atual, remove
instalações e venvs autorizadas e preserva os dados do utilizador por omissão.

## Android

| Artefacto | Bytes | SHA-256 |
|---|---:|---|
| `dist/mobile/Aprendix-0.17.0-android-arm64-debug.apk` | 22 000 000 | `B4F559D97F7C99944C0EDA4EA8BCD027A97FF0FC3ADD02E97FE67295A48DF72D` |
| `mobile/assets/knowledge-lite.db` | 135 168 | `1D3F8FD79FC1C248E2320A8B5CACA3A3CE4DDF9A1EAE52252FAAD2878397BB89` |

O APK é ZIP válido, contém ABI `arm64-v8a`, package
`io.aprendix.aprendix`, `versionName=0.17.0`, min SDK 26 e target SDK 34. A assinatura
APK v2 foi verificada; o certificado debug tem SHA-256
`41f919380f980a4e7f9b51c34e47ed547795c6e2023e4d0adea3052d6e7f2dff`. As únicas
permissões funcionais são notificações e vibração; não existe `INTERNET`. O reminder
receiver e o provider AndroidX têm `exported=false`. O seed empacotado coincide com o
asset fonte e passa `integrity_check=ok`.

Não havia dispositivo Android ligado nem `adb` no PATH do host, portanto o ensaio de
toque num aparelho físico não foi executado. A instalação direta e por ADB está
documentada em `INSTALL-MOBILE.md` e automatizada por `Instalar-Android-ADB.bat`.

## iOS

O shell Toga, runtime offline, Keychain, haptics/notificações e script de integração
Xcode estão presentes e os testes Python/guard do host passaram. Um IPA assinado não
pode ser produzido ou validado num host Windows: requer macOS, Xcode, Team Apple,
certificado e provisioning para os dispositivos. O processo correto de build, instalação
e export Ad Hoc está descrito em `INSTALL-MOBILE.md`.

## Limites assumidos

- A pesquisa Web é opt-in, limitada e só ocorre se a evidência local/curada for fraca.
- Obras externas são metadados, ligações oficiais e sínteses Aprendix; texto integral
  provém apenas dos ficheiros locais do utilizador.
- O modelo de resumo é determinístico e local por omissão. Ollama permanece opcional e
  apenas em loopback.
- O APK atual tem assinatura debug para sideload privado, não assinatura de loja.
