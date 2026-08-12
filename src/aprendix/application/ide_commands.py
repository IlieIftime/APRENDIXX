"""Toolkit-neutral command catalogue for the learning IDE."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IdeCommand:
    id: str
    title: str
    symbol: str
    shortcut: str = ""
    keywords: tuple[str, ...] = ()


IDE_COMMANDS = (
    IdeCommand("run", "Executar código", "RUN", "Ctrl+Enter", ("run", "f5")),
    IdeCommand("correct", "Corrigir exercício", "OK", "Ctrl+Shift+Enter", ("testar", "avaliar")),
    IdeCommand("debug", "Iniciar debugger", "DBG", "F6", ("depurar", "breakpoint")),
    IdeCommand("save", "Guardar rascunho", "SAVE", "Ctrl+S", ("draft", "persistir")),
    IdeCommand("find", "Procurar e substituir", "FIND", "Ctrl+F", ("search", "replace")),
    IdeCommand("format", "Formatar código", "{ }", "Shift+Alt+F", ("pep8", "alinhar")),
    IdeCommand("copy", "Copiar código", "COPY", "Ctrl+Shift+C", ("clipboard",)),
    IdeCommand("zoom_in", "Aumentar editor", "A+", "Ctrl++", ("fonte", "zoom")),
    IdeCommand("zoom_out", "Diminuir editor", "A-", "Ctrl+-", ("fonte", "zoom")),
    IdeCommand("toggle_brief", "Recolher ou expandir enunciado", "DOC", "Ctrl+B", ("docstring", "célula")),
    IdeCommand("toggle_panel", "Abrir ou fechar painel inferior", "PANEL", "Ctrl+J", ("output", "problemas")),
    IdeCommand("tutor", "Pedir pista ao tutor", "?", "Ctrl+I", ("ajuda", "socrático")),
    IdeCommand("copykate", "Analisar estilo com CopyKate", "CK", "", ("assistente", "estilo")),
    IdeCommand("variation", "Criar nova variação", "VAR", "", ("a2", "praticar")),
    IdeCommand("complete", "Autocomplete estrutural", "TAB", "", ("sugerir", "estrutura")),
    IdeCommand("focus", "Iniciar foco de 25 minutos", "25m", "", ("pomodoro", "tempo")),
)


def _fold(value: str) -> str:
    return "".join(
        character for character in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(character)
    )


def search_ide_commands(query: str, *, limit: int = 12) -> tuple[IdeCommand, ...]:
    words = tuple(_fold(query).split())
    matches = []
    for position, command in enumerate(IDE_COMMANDS):
        haystack = _fold(" ".join((command.id, command.title, command.shortcut, *command.keywords)))
        if words and not all(word in haystack for word in words):
            continue
        prefix = 0 if not words or _fold(command.title).startswith(" ".join(words)) else 1
        matches.append((prefix, position, command))
    matches.sort(key=lambda item: (item[0], item[1]))
    return tuple(item[2] for item in matches[:max(1, min(30, limit))])
