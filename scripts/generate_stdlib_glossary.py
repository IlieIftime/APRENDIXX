"""Generate an original metadata glossary for Python's public standard library.

The script inspects signatures and public symbol names.  Definitions are
Aprendix-authored from symbol kind, module purpose and conservative name hints;
CPython docstrings and documentation prose are deliberately not copied.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    ROOT / "src" / "aprendix" / "presentation" / "assets"
    / "stdlib-glossary.json"
)

MODULES = (
    "abc", "argparse", "array", "ast", "asyncio", "base64", "binascii",
    "bisect", "calendar", "cmath", "codecs", "collections", "collections.abc",
    "concurrent.futures", "contextlib", "contextvars", "copy", "csv",
    "dataclasses", "datetime", "decimal", "difflib", "email", "email.message",
    "email.parser", "enum", "fnmatch", "fractions", "functools", "gc", "getopt",
    "gettext", "glob", "graphlib", "gzip", "hashlib", "heapq", "hmac", "html",
    "html.parser", "http", "http.client", "http.server", "importlib",
    "importlib.metadata", "importlib.resources", "inspect", "io", "ipaddress",
    "itertools", "json", "keyword", "logging", "lzma", "math", "mimetypes",
    "operator", "os", "os.path", "pathlib", "pickle", "pkgutil", "platform",
    "pprint", "queue", "random", "re", "sched", "secrets", "selectors", "shelve",
    "shlex", "shutil", "signal", "socket", "sqlite3", "statistics", "string",
    "struct", "subprocess", "sys", "tarfile", "tempfile", "textwrap", "threading",
    "time", "timeit", "token", "tokenize", "tomllib", "traceback", "types",
    "typing", "unicodedata", "unittest", "unittest.mock", "urllib.parse", "uuid",
    "warnings", "weakref", "xml.etree.ElementTree", "zipfile", "zoneinfo",
)

CATEGORY_PURPOSE = {
    "algorithms": "algoritmos, iteração, ordenação e estruturas auxiliares",
    "concurrency": "concorrência, sincronização e coordenação de tarefas",
    "data": "estruturas, serialização e transformação de dados",
    "files": "caminhos, ficheiros, arquivos e recursos locais",
    "language": "semântica, introspeção, tipos e ferramentas da linguagem",
    "network": "protocolos e comunicação; no Aprendix a execução de rede permanece bloqueada",
    "security": "hashes, autenticação e geração de valores seguros",
    "testing": "testes, diagnóstico, logging e medição",
    "text": "texto, padrões, codificação e formatos documentais",
    "time": "datas, horas, calendários e agendamento",
}

CATEGORY_MODULES = {
    "algorithms": {"bisect", "collections", "collections.abc", "functools", "graphlib", "heapq", "itertools", "operator", "queue", "random", "statistics"},
    "concurrency": {"asyncio", "concurrent.futures", "contextvars", "queue", "sched", "signal", "subprocess", "threading"},
    "files": {"glob", "gzip", "importlib.resources", "lzma", "mimetypes", "os", "os.path", "pathlib", "shelve", "shutil", "tarfile", "tempfile", "zipfile"},
    "language": {"abc", "ast", "dataclasses", "enum", "gc", "importlib", "importlib.metadata", "inspect", "keyword", "pkgutil", "platform", "sys", "token", "tokenize", "types", "typing", "weakref"},
    "network": {"http", "http.client", "http.server", "ipaddress", "selectors", "socket", "urllib.parse"},
    "security": {"hashlib", "hmac", "secrets"},
    "testing": {"logging", "pprint", "timeit", "traceback", "unittest", "unittest.mock", "warnings"},
    "text": {"argparse", "base64", "binascii", "codecs", "csv", "difflib", "email", "email.message", "email.parser", "fnmatch", "getopt", "gettext", "html", "html.parser", "json", "re", "shlex", "string", "struct", "textwrap", "tomllib", "unicodedata", "xml.etree.ElementTree"},
    "time": {"calendar", "datetime", "time", "zoneinfo"},
}


def _category(module: str) -> str:
    for category, modules in CATEGORY_MODULES.items():
        if module in modules:
            return category
    return "data"


def _kind(value: object) -> str | None:
    if inspect.isclass(value):
        return "classe"
    if inspect.isroutine(value) or callable(value):
        return "função"
    if isinstance(value, (str, bytes, int, float, complex, bool, tuple, frozenset, type(None))):
        return "constante"
    return None


def _action(name: str, kind: str) -> str:
    lowered = name.casefold()
    hints = (
        (("parse", "loads", "decode", "from"), "interpretar ou converter uma representação de entrada"),
        (("dump", "write", "encode", "format", "to"), "produzir uma representação de saída explícita"),
        (("find", "search", "match", "get", "lookup", "resolve"), "consultar ou localizar um elemento segundo um critério"),
        (("iter", "walk", "scan"), "percorrer valores sem assumir que cabem todos em memória"),
        (("is", "has", "can", "check", "valid"), "testar uma condição e devolver evidência booleana"),
        (("add", "append", "insert", "update", "set", "replace"), "construir ou atualizar estado segundo o contrato da API"),
        (("remove", "delete", "discard", "pop", "clear"), "remover informação com uma política explícita para ausências"),
        (("sort", "order", "bisect", "heap"), "manter ou explorar uma relação de ordem"),
        (("open", "read", "load"), "obter dados de uma fonte declarada e gerir o respetivo ciclo de vida"),
    )
    for tokens, action in hints:
        if any(token in lowered for token in tokens):
            return action
    if kind == "classe":
        return "criar objetos que agrupam estado e comportamento deste domínio"
    if kind == "constante":
        return "representar um valor público usado pelos contratos do módulo"
    return "realizar uma operação pública definida pelo módulo"


def _signature(name: str, value: object, kind: str) -> str:
    if kind == "constante":
        return name
    try:
        return name + str(inspect.signature(value))
    except (TypeError, ValueError):
        return f"{name}(...)"


def generate() -> dict[str, object]:
    entries = []
    failures = []
    seen = set()
    for module_name in MODULES:
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            failures.append({"module": module_name, "error": type(exc).__name__})
            continue
        category = _category(module_name)
        purpose = CATEGORY_PURPOSE[category]
        for name, value in inspect.getmembers(module):
            if name.startswith("_") or len(name) > 100:
                continue
            kind = _kind(value)
            if kind is None:
                continue
            identity = f"{module_name}.{name}"
            if identity.casefold() in seen:
                continue
            seen.add(identity.casefold())
            action = _action(name, kind)
            entries.append({
                "term": identity,
                "technology": "python",
                "definition": (
                    f"`{identity}` é uma {kind} pública da biblioteca padrão para {purpose}. "
                    f"Usa-a para {action}, confirmando tipos, retorno, exceções e casos-limite."
                ),
                "signature": _signature(name, value, kind),
                "example": f"from {module_name} import {name}\nhelp({name})",
                "related": [module_name, category, kind],
                "aliases": [
                    f"{name} em {module_name}",
                    f"Python {module_name} {name}",
                    f"{module_name}: {name}",
                ],
                "source_ids": ["src-python-docs"],
                "provenance": "stdlib-public-api-introspection-original-summary",
            })
    entries.sort(key=lambda item: item["term"].casefold())
    return {
        "schema_version": 1,
        "policy": {"copied_docstrings": False, "public_api_only": True},
        "entry_count": len(entries),
        "entries": entries,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = generate()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{output} | entradas={payload['entry_count']} | falhas={len(payload['failures'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
