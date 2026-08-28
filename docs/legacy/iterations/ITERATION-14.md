# Iteração 14 — Percurso pedagógico integrado no IDE

## Resultado

A Iteração 14 transforma o IDE num percurso de aprendizagem contínuo e mantém
compatibilidade com o catálogo existente. Cada prática curricular abre primeiro
uma microteoria local, permite alternar imediatamente para o contrato do
exercício e conserva o avanço automático após aprovação.

## Capacidades entregues

- Enunciados em três modos persistentes: **Simples**, **Guiado** e **Técnico**.
- Microteoria e exemplo do capítulo disponíveis sem abandonar o IDE.
- Primeira visita com sequência microteoria → prática; revisitas respeitam a
  preferência local do utilizador.
- Ajuda por tentativas persistidas: localização, conceito, estratégia e exemplo
  análogo curado.
- Avaliações bloqueiam a escada antes de estratégia/exemplo; testes ocultos não
  são revelados.
- Feedback inclui número da tentativa, score, categoria do erro e próximo passo.
- Pedidos de ajuda são registados no modelo de progresso como `hint_count`.
- A solução continua vazia quando o exercício abre; o conteúdo pedagógico fica
  na célula documental e não é inserido no editor.

## Gate reproduzível

Executar:

```powershell
python scripts/audit_iteration14.py
```

O relatório `ITERATION-14-AUDIT-1.0.0.json` usa um perfil anónimo temporário e
mede cobertura de teoria/exemplo, modos de enunciado e ordem da ajuda sem guardar
texto ou identificadores do utilizador.
