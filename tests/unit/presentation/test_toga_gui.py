"""BeeWare adapter remains optional on non-iOS development hosts."""

import builtins

import pytest

from aprendix.presentation.toga_gui import TogaDependencyError, launch_toga


def test_toga_adapter_reports_missing_optional_dependency(monkeypatch) -> None:
    real_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name == "toga" or name.startswith("toga."):
            raise ImportError("blocked for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)

    with pytest.raises(TogaDependencyError, match="Toga is not installed"):
        launch_toga(object())
