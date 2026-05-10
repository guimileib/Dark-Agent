"""DarkAgent Pro v2.0 - Sistema de processamento de vídeos com IA"""

__version__ = "2.0.1"
__author__ = "Guilherme"
__email__ = "suporte@darkagent.pro"

# Lazy imports — subpackages are only loaded when actually accessed.
# This prevents heavy modules (torch, whisper, selenium) from being
# imported just because someone does `import src`.

__all__ = ['models', 'core', 'config', 'utils']


def __getattr__(name):
    if name in __all__:
        import importlib
        return importlib.import_module(f".{name}", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
