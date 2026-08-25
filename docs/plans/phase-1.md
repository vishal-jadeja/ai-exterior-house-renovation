# Phase 1 — Auth, projects, upload & quality gate (2.5h)

## Goal
Multi-user foundation and the first step of the user workflow: upload a facade photo, get it
validated, sanitized, stored, and scored for usability with actionable guidance.

## Scope (spec 5.1, 6)
- Register / login / refresh / logout. Argon2 hashes, JWT access (15 min) + rotating refresh
  (httpOnly, SameSite cookie), refresh-token versioning for logout-all.
- Rate limits on auth and upload endpoints.
- Projects CRUD scoped to owner (404 on foreign IDs).
- Upload: magic-byte check, size/dimension limits, Pillow re-encode (strips EXIF/GPS, kills
  polyglots). Only the sanitized JPEG is persisted (raw upload bytes are discarded after
  validation, never written to storage) in MinIO/R2 under `projects/{id}/...`, presigned GET.
- Quality gate: blur (Laplacian variance), resolution, exposure, contrast → score + guidance list.
  Reject unusable images with a clear message; warn on borderline.
- Web: auth pages, project list, project page with dropzone + quality feedback.

## Checklist
- [x] `POST /auth/register|login|refresh|logout`, `GET /auth/me`
- [x] `GET|POST /projects`, `GET|PATCH|DELETE /projects/{id}`
- [x] `POST /projects/{id}/images` (multipart) → sanitized image + quality result
- [x] `GET /projects/{id}/images/{image_id}` returns the image with a presigned `url` field
- [x] Storage provider abstraction (S3-compatible)
- [x] Web: login/register, projects list, upload with guidance
- [x] Tests: auth flow, ownership isolation, quality gate on sharp vs blurred fixture

## Acceptance criteria
- Blurry/tiny image → 422 with guidance; sharp image → stored and displayed.
- User B cannot read user A's project (404).
