"""Infrastructure namespace.

Adapters are imported from their concrete packages so mobile startup never
loads the desktop subprocess sandbox as an accidental package side effect.
"""

__all__: list[str] = []
