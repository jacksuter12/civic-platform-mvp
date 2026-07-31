"""
llm_panel — the LLM deliberation panel.

A research instrument that runs multi-model deliberations through the civic
platform's own phase-gated infrastructure.

This package is a peer of `backend/`, not a part of it. It reaches the platform
over HTTP only and must never import from `app.*`. See README.md.

Sprint 1 ships the seeding layer (`conditions`, `jwt_util`, `platform_client`,
`seed`). The orchestrator modules arrive in Sprint 2.
"""
