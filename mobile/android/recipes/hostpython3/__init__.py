"""Keep hostpython ABI identical to the Android Python ABI."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pythonforandroid


_CORE_DIRECTORY = Path(pythonforandroid.__file__).resolve().parent / "recipes" / "hostpython3"
_SPECIFICATION = spec_from_file_location("aprendix_core_hostpython3_recipe", _CORE_DIRECTORY / "__init__.py")
if _SPECIFICATION is None or _SPECIFICATION.loader is None:
    raise RuntimeError("Não foi possível carregar o recipe hostpython oficial.")
_CORE_MODULE = module_from_spec(_SPECIFICATION)
_SPECIFICATION.loader.exec_module(_CORE_MODULE)


class AprendixHostPython3Recipe(_CORE_MODULE.HostPython3Recipe):
    version = "3.11.14"

    def get_recipe_dir(self):
        return str(_CORE_DIRECTORY)


recipe = AprendixHostPython3Recipe()
