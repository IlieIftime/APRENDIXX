# Iteração 17 — Atualizações semanais desktop

As atualizações de conteúdo são opcionais e nunca enviam dados do utilizador.
O registo e cada download têm de usar HTTPS no mesmo host autorizado. A consulta
respeita o intervalo semanal e pode aguardar uma ligação não medida ou energia
externa.

Antes de instalar, a interface apresenta título, resumo, fontes, percursos
afetados, tamanho e possibilidade de rollback. Só são aceites packs declarativos
com tamanho limitado, hashes completos e assinatura Ed25519 da distribuição.
Packs inválidos são postos em quarentena e a ativação é atómica.

Não existe instalação silenciosa: verificar, antever e instalar são operações
separadas. Sem um registo configurado, a aplicação permanece totalmente offline.

Gate reproduzível:

```powershell
python scripts/audit_iteration17.py
```
