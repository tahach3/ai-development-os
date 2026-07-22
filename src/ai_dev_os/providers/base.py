"""Provider adapter base interface and registry helpers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..provider_config import ProviderConfig
from ..provider_models import (
    ProviderCapability,
    ProviderRequest,
    ProviderResultEnvelope,
)


class ProviderAdapter(ABC):
    provider_id: str
    adapter_version: str

    @abstractmethod
    def describe_capabilities(
        self,
        *,
        config: ProviderConfig,
        discovery: dict[str, Any] | None = None,
    ) -> ProviderCapability:
        raise NotImplementedError

    @abstractmethod
    def preview_invocation(self, request: ProviderRequest) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def execute(
        self,
        request: ProviderRequest,
        *,
        config: ProviderConfig,
        audit_store: Any,
        confinement_root: str | None = None,
    ) -> ProviderResultEnvelope:
        raise NotImplementedError
