"""Toolkit-neutral navigation history, deep links, and command discovery."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import parse_qs, urlparse


class Route(str, Enum):
    DASHBOARD = "dashboard"
    CURRICULUM = "curriculum"
    IDE = "learning"
    SEARCH = "search"
    CARDS = "cards"
    DICTIONARY = "reference"
    TUTOR = "tutor"
    PROJECTS = "projects"
    ANALYZER = "analyzer"
    GAMES = "games"
    READER = "reader"
    DATA = "data"


@dataclass(frozen=True, slots=True)
class DeepLink:
    route: Route
    parameters: dict[str, str] = field(default_factory=dict)


def parse_deep_link(value: str) -> DeepLink:
    parsed = urlparse(value.strip())
    if parsed.scheme != "aprendix" or not parsed.netloc or parsed.path not in {"", "/"}:
        raise ValueError("invalid Aprendix deep link")
    try:
        route = Route(parsed.netloc)
    except ValueError as exc:
        raise ValueError("unknown Aprendix route") from exc
    allowed = {"id", "query", "area"}
    parameters: dict[str, str] = {}
    for name, values in parse_qs(parsed.query, keep_blank_values=False).items():
        if name not in allowed or len(values) != 1 or len(values[0]) > 500:
            raise ValueError("invalid Aprendix deep-link parameter")
        parameters[name] = values[0]
    return DeepLink(route=route, parameters=parameters)


@dataclass(slots=True)
class NavigationHistory:
    current: Route = Route.DASHBOARD
    _back: list[Route] = field(default_factory=list)
    _forward: list[Route] = field(default_factory=list)
    max_entries: int = 50

    def navigate(self, target: Route | str) -> Route:
        target = Route(target)
        if target == self.current:
            return self.current
        self._back.append(self.current)
        self._back = self._back[-self.max_entries:]
        self.current = target
        self._forward.clear()
        return self.current

    def back(self) -> Route:
        if not self._back:
            return self.current
        self._forward.append(self.current)
        self.current = self._back.pop()
        return self.current

    def forward(self) -> Route:
        if not self._forward:
            return self.current
        self._back.append(self.current)
        self.current = self._forward.pop()
        return self.current

    @property
    def can_go_back(self) -> bool:
        return bool(self._back)

    @property
    def can_go_forward(self) -> bool:
        return bool(self._forward)


@dataclass(frozen=True, slots=True)
class NavigationCommand:
    id: str
    title: str
    route: Route
    keywords: tuple[str, ...] = ()


DEFAULT_COMMANDS = (
    NavigationCommand("go.dashboard", "Abrir painel", Route.DASHBOARD, ("progresso", "plano")),
    NavigationCommand("go.course", "Continuar curso", Route.CURRICULUM, ("aprender", "unidade")),
    NavigationCommand("go.ide", "Abrir IDE", Route.IDE, ("código", "exercício", "debug")),
    NavigationCommand("go.search", "Pesquisar conhecimento", Route.SEARCH, ("tema", "fonte")),
    NavigationCommand("go.cards", "Rever cards", Route.CARDS, ("sabias", "revisão")),
    NavigationCommand("go.dictionary", "Consultar dicionário", Route.DICTIONARY, ("conceito", "definição")),
    NavigationCommand("go.tutor", "Abrir tutor offline", Route.TUTOR, ("explicar", "socrático", "ajuda")),
    NavigationCommand("go.projects", "Abrir projetos", Route.PROJECTS, ("portefólio", "capstone", "briefing")),
    NavigationCommand("go.analyzer", "Analisar trecho", Route.ANALYZER, ("imagem", "pseudocódigo", "ocr", "snippet")),
    NavigationCommand("go.games", "Abrir Games", Route.GAMES, ("pausa", "sudoku", "minesweeper")),
    NavigationCommand("go.data", "Dados e atualizações", Route.DATA, ("perfil", "exportar", "pack", "backup")),
)


def _fold(value: str) -> str:
    return "".join(
        character for character in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(character)
    )


class CommandPalette:
    def __init__(self, commands: tuple[NavigationCommand, ...] = DEFAULT_COMMANDS) -> None:
        if len({command.id for command in commands}) != len(commands):
            raise ValueError("command ids must be unique")
        self._commands = commands

    def search(self, query: str, *, limit: int = 8) -> tuple[NavigationCommand, ...]:
        if not 1 <= limit <= 30:
            raise ValueError("command limit must be between 1 and 30")
        words = tuple(_fold(query).split())
        ranked: list[tuple[int, int, NavigationCommand]] = []
        for position, command in enumerate(self._commands):
            haystack = _fold(" ".join((command.title, command.id, *command.keywords)))
            if words and not all(word in haystack for word in words):
                continue
            prefix = 0 if not words or _fold(command.title).startswith(" ".join(words)) else 1
            ranked.append((prefix, position, command))
        ranked.sort(key=lambda item: (item[0], item[1]))
        return tuple(item[2] for item in ranked[:limit])
