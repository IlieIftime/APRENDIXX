# Iteração 19 — Paridade pedagógica mobile e APK final

A aplicação móvel deixou de tratar a conclusão de unidades como uma ação manual.
Cada unidade abre no IDE incorporado com enquadramento, objetivo, contrato e critérios
de avaliação; só uma correção local aprovada conclui a unidade. Treino e avaliação
usam casos protegidos, sendo que a avaliação não revela a causa nem os testes.

O percurso regista tentativas, tempo ativo, previsão, reflexão, aprovação autónoma e
transferência para uma variação. Previsões e reflexões permanecem cifradas no perfil.
O Android usa um intérprete AST limitado que não chama `exec`, `eval`, `compile`, rede,
ficheiros ou subprocessos. Construções avançadas fora desse subconjunto são remetidas
explicitamente para o sandbox desktop.

A base móvel schema 6 contém as 1 121 fontes validadas, 50 unidades, 1 137 cards e
3 315 entradas de dicionário. O APK release ARM64 incorpora exatamente essa base, é
assinado, não-debuggable e não pede permissão de Internet. A shell iOS recebeu o mesmo
fluxo pedagógico, mas a compilação e assinatura continuam obrigatoriamente dependentes
de macOS, Xcode e uma identidade Apple.

Gate reproduzível da lógica e do conteúdo:

```powershell
$env:PYTHONPATH = "src;mobile"
python scripts/audit_iteration19.py
```

Gate do APK em WSL:

```bash
bash mobile/scripts/validate_android.sh \
  dist/mobile/Aprendix-1.0.0-android-arm64-release.apk
```
