"""Provider registry.

Only the Demo provider exists in M3. `get_provider` falls back to Demo whenever the requested
provider is unknown or not configured (for example: no API key), so an agent always has a
working provider and Demo Mode needs nothing.
"""

from __future__ import annotations

from app.providers.base import AgentContext, AgentReply, Provider, TaskContext, ToolRequest
from app.providers.demo import DEMO_PREFIX, DemoProvider

_DEMO = DemoProvider()
_PROVIDERS: dict[str, Provider] = {_DEMO.name: _DEMO}


def register_provider(provider: Provider) -> None:
    _PROVIDERS[provider.name] = provider


def unregister_provider(name: str) -> None:
    if name != _DEMO.name:
        _PROVIDERS.pop(name, None)


def provider_names() -> list[str]:
    """The providers an agent can be set to."""
    return sorted(_PROVIDERS)


def get_provider(name: str | None = None) -> Provider:
    """The named provider when it is registered and configured, otherwise Demo."""
    provider = _PROVIDERS.get(name or _DEMO.name)
    if provider is None or not provider.is_configured():
        return _DEMO
    return provider


__all__ = [
    "DEMO_PREFIX",
    "AgentContext",
    "AgentReply",
    "DemoProvider",
    "Provider",
    "TaskContext",
    "ToolRequest",
    "get_provider",
    "provider_names",
    "register_provider",
    "unregister_provider",
]
