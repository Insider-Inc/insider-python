"""Single source of truth for the SDK version.

Kept separate from `pyproject.toml` at runtime to avoid an `importlib.metadata`
lookup on every beacon. Bump this and `[project].version` together when
cutting a release.
"""

__version__ = "0.1.0"
