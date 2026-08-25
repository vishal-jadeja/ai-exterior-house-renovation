# Phase 4 — Renovation visualization (4h)

## Goal
Show the user's own house with the selected materials applied, structure preserved, with
before/after comparison. Must work with zero API keys.

## Scope (spec 5.4)
- `RenderProvider` protocol: `render(image, regions+masks, assignments) -> image`.
- `LocalCompositeRenderer` (always available): tile texture → perspective-warp into region quad →
  luminance-preserving blend (keeps shadows/lighting) → feathered mask composite. Paint = tint.
- `CloudflareInpaintRenderer`: Workers AI `stable-diffusion-v1-5-inpainting`, per-region mask +
  material prompt; result pasted back only inside mask.
- `FalInpaintRenderer`: FLUX fill endpoint, same contract.
- `FallbackChainRenderer`: tries `RENDER_PROVIDER_ORDER`; records `provider_used` + per-provider log.
- Render job; renders stored as images; web before/after slider + side-by-side + provider badge.

## Checklist
- [x] Providers + chain + unit test for local renderer on synthetic image
- [x] `POST /designs/{id}/render`, `GET /designs/{id}/renders`
- [x] Web compare view

## Acceptance criteria
- Redesigned image keeps windows/doors/structure; cladding/paint visibly applied.
- Removing all keys → still renders via local provider; quota error → falls through to next tier.

## Outcome notes
- Hosted providers (Cloudflare Workers AI, fal.ai) are implemented against their documented HTTP APIs and take the local composite as the init image; they could not be exercised end-to-end without API keys. The chain reports them as `skipped` and the local compositor always produces the result.
- Regions are grouped by material before calling hosted inpainting so a render costs ~2-4 calls instead of one per region (free-tier friendly).
