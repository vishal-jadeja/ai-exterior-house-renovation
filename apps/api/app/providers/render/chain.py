"""FallbackChainRenderer — try providers in configured order; local composite is the floor."""

from __future__ import annotations

import numpy as np

from app.core.config import get_settings
from app.core.logging import get_logger
from app.providers.render.base import ProviderUnavailable, RenderProvider, RenderRequest
from app.providers.render.diffusion import CloudflareInpaintRenderer, FalInpaintRenderer
from app.providers.render.local import LocalCompositeRenderer

log = get_logger("render.chain")

REGISTRY: dict[str, type] = {
    "fal": FalInpaintRenderer,
    "cloudflare": CloudflareInpaintRenderer,
    "local": LocalCompositeRenderer,
}


class FallbackChainRenderer:
    name = "chain"

    def __init__(self, order: list[str] | None = None) -> None:
        order = order or get_settings().render_provider_order
        names = [n for n in order if n in REGISTRY]
        if "local" not in names:
            names.append("local")
        self.providers: list[RenderProvider] = [REGISTRY[n]() for n in names]

    def available(self) -> bool:
        return True

    async def render(self, req: RenderRequest) -> tuple[np.ndarray, str]:
        last_exc: Exception | None = None
        for p in self.providers:
            if not p.available():
                req.log.append(
                    {"provider": p.name, "status": "skipped", "reason": "not configured"}
                )
                continue
            try:
                out = await p.render(req)
                return out, p.name
            except ProviderUnavailable as exc:
                req.log.append(
                    {"provider": p.name, "status": "unavailable", "reason": str(exc)[:300]}
                )
                log.warning("provider_unavailable", provider=p.name, reason=str(exc)[:200])
                last_exc = exc
            except Exception as exc:  # noqa: BLE001 - degrade, never fail the render
                req.log.append({"provider": p.name, "status": "error", "reason": str(exc)[:300]})
                log.exception("provider_error", provider=p.name)
                last_exc = exc
        raise RuntimeError(f"all render providers failed: {last_exc}")
