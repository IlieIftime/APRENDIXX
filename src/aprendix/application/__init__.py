"""Application services with lazy exports for lightweight mobile imports."""

from importlib import import_module

__all__ = [
    "ConstraintSelectionError",
    "ContentOrchestrator",
    "CopyKateService",
    "NLPUnavailableError",
    "OrchestrationError",
    "QuantizedNLPAdapter",
    "TemplateRenderError",
    "UnknownTemplateError",
]


_EXPORT_MODULES = {
    "CopyKateService": "aprendix.application.copykate",
    "ConstraintSelectionError": "aprendix.application.content_orchestrator",
    "ContentOrchestrator": "aprendix.application.content_orchestrator",
    "OrchestrationError": "aprendix.application.content_orchestrator",
    "TemplateRenderError": "aprendix.application.content_orchestrator",
    "UnknownTemplateError": "aprendix.application.content_orchestrator",
    "NLPUnavailableError": "aprendix.application.content_ports",
    "QuantizedNLPAdapter": "aprendix.application.content_ports",
}


def __getattr__(name: str):
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(name)
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value
