# Validação da pesquisa e leitura v2

Data: 2026-08-02

## Estado validado

- Schema SQLite: 23; `PRAGMA quick_check`: `ok`.
- Biblioteca real: 389 documentos ativos e 19 908 chunks aceites.
- Pesquisa lexical pública: FTS5/BM25F, limitada por proveniência a conteúdo `permitted`.
- Pesquisa privada: filtros Bloom HMAC por chunk; nenhum token de PDF é guardado em claro.
- Pesquisa semântica: embeddings `int8` existentes e 159 264 buckets LSH com digest HMAC.
- Fusão: BM25F + shortlist privado + dense + RRF + reranking + MMR.
- Interpretação: intenção, aliases/acrónimos e correções conservadoras.
- UI: “Porque apareceu”, confiança, latência, cancelamento, comparação de 2–4 fontes.
- Leitor: original, resumo, simplificação matemática, imagens, duplo clique no tutor,
  referências, bookmarks e notas cifradas.

## Gate SEARCH-1 no perfil real

Resultado persistido em `build/SEARCH-QUALITY-REAL-PHASE5.json`:

- Recall@10: 0,9667
- MRR: 0,9250
- nDCG@10: 0,9384 (alvo >= 0,80)
- P95: 367,5 ms (alvo < 500 ms)
- Estado: aprovado

O conjunto contém dez consultas com julgamentos explícitos para Python, algoritmos,
ML, deep learning, bases de dados, segurança e agentes.

## Segurança e recuperação

- Conteúdo `local-private` é excluído das tabelas FTS5 em texto simples.
- Os filtros privados usam HMAC derivado da chave AES do perfil e namespace próprio.
- Notas são AES-256-GCM; texto selecionado é representado apenas por SHA-256.
- Backups consistentes foram criados antes dos schemas 20, 21, 22 e 23, incluindo
  base SQLite, chave e manifesto SHA-256.

## Testes

- Suite completa antes do cancelamento UI: 206 testes aprovados em 31,46 s.
- Suite focada final de pesquisa, leitor, cifra e apresentação: 33 testes aprovados.
- O benchmark é executável por `py -3 scripts/benchmark_search.py` e guarda apenas
  métricas agregadas, nunca o texto das perguntas do utilizador.
