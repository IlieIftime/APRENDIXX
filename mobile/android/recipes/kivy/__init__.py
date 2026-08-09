"""Kivy recipe compatibility shim for Clang/NDK r28c."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pythonforandroid


_CORE_DIRECTORY = Path(pythonforandroid.__file__).resolve().parent / "recipes" / "kivy"
_SPECIFICATION = spec_from_file_location("aprendix_core_kivy_recipe", _CORE_DIRECTORY / "__init__.py")
if _SPECIFICATION is None or _SPECIFICATION.loader is None:
    raise RuntimeError("Não foi possível carregar o recipe Kivy oficial.")
_CORE_MODULE = module_from_spec(_SPECIFICATION)
_SPECIFICATION.loader.exec_module(_CORE_MODULE)


class AprendixKivyRecipe(_CORE_MODULE.KivyRecipe):
    """Retain the official recipe and relax one NDK 28 diagnostic.

    GLES declares ``glShaderSource`` with an additional const qualifier. Kivy
    2.3.x assigns it to an ABI-compatible function pointer lacking that outer
    qualifier. Clang 19 promoted this long-standing diagnostic to an error.
    """

    def get_recipe_dir(self):
        return str(_CORE_DIRECTORY)

    def get_recipe_env(self, arch, **kwargs):
        environment = super().get_recipe_env(arch, **kwargs)
        flag = " -Wno-error=incompatible-function-pointer-types"
        environment["CFLAGS"] = environment.get("CFLAGS", "") + flag
        environment["CXXFLAGS"] = environment.get("CXXFLAGS", "") + flag
        return environment


recipe = AprendixKivyRecipe()
