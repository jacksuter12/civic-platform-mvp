# Session 1 — Backend foundations for Proposal Review

**Paste this entire file into a fresh Claude Code instance.**

**Suggested Claude Code settings for this session:**
- Plan Mode: **ON** (Shift+Tab to toggle)
- Auto-accept Edits: **OFF**
- Thinking effort: **HIGH** (permission branching + migration backfill are the
  highest-risk work in this whole chunk)

---

## Step 0 — Feature branch setup

Before any code changes, set up a feature branch so this multi-session work
stays isolated from `main` until the whole chunk is merged.

Run these in order. If the working tree isn't clean, stop and ask the user
whether to stash or commit existing changes first.

```bash
git status                                           # confirm clean tree
git checkout main
git pull
git checkout -b feature/proposal-review
git push -u origin feature/proposal-review
```

After the branch is created and pushed, confirm in chat with the user
that you're on `feature/proposal-review` before continuing to the plan.
All commits in this session (and Sessions 2-4) land on this branch.

---

## What you're building

Backend foundations for a new Proposal Review feature. This session has no UI
changes — it lays the groundwork for Sessions 2-4. When done, a proposal's
JSON response includes rendered HTML, annotations can be resolved/unresolved,
and the permission logic for proposal annotations is in place.

## Context

The existing codebase has:
- A target-agnostic `annotations` table with `target_type` polymorphic over
  `wiki | post | proposal | document`
- Wiki annotations gated by `users.is_annotator` (platform-level capability)
- `CommunityMembership.tier` for community-scoped permissions
- An append-only audit log via `core/audit.log_event()`

You're adding:
- Server-side markdown rendering for proposal bodies
- A `resolved_at` + `resolved_by_id` column on annotations
- Resolve/unresolve endpoints
- A new permission helper that branches on `target_type` — wiki annotations
  keep their existing capability check; proposal annotations use community
  membership + phase gating

## Hard constraints (from CLAUDE.md — re-check before starting)

1. Audit log is append-only. Use `core/audit.log_event()` only.
2. Every community-scoped audit event must pass `community_id`.
3. Use `CommunityMembership.tier` for authorization, **never `users.tier`**
   (vestigial).
4. Phase gates are enforced server-side, not client-side.
5. Wiki annotations still require `annotator` capability. Proposal annotations
   use community membership. Branch on `target_type` — do not conflate.
6. `api.js` stays framework-agnostic: no DOM manipulation, only `fetch()` and
   data parsing. (Not touched this session but don't import api.js-style
   helpers into any new backend code.)

## Plan Mode — read these files first

Before producing a plan, read:
- `CLAUDE.md` (root) — constraint list above must be re-verified
- `backend/app/models/annotation.py` — current shape of the annotations table
- `backend/app/models/proposal.py` — Proposal + ProposalVersion models
- `backend/app/api/v1/annotations.py` (or wherever annotation routes live) —
  existing CRUD routes, look for the current permission check pattern
- `backend/app/api/v1/proposals.py` — where proposals are created
- `backend/app/api/deps.py` — existing dependency helpers
  (`RegisteredUser`, `FacilitatorUser`, etc.)
- `backend/app/core/audit.py` — audit log writer signature
- `backend/alembic/versions/` — glance at the latest migration to match style
- `backend/pyproject.toml` — current dependencies

## Work items

### 1. Dependencies

Add to `backend/pyproject.toml`:
- `markdown-it-py>=3.0.0`
- `mdit-py-plugins>=0.4.0`
- `bleach>=6.1.0`

Then run `pip install -e ".[dev]"` from `backend/`.

### 2. Create `backend/app/core/markdown.py`

One module, one public function. Full code:

```python
"""
Server-side markdown rendering for proposal bodies.

The same input always produces the same output — this is important because
annotation anchors reference text ranges in the rendered HTML. If rendering
were non-deterministic, anchors would drift.
"""
from markdown_it import MarkdownIt
from mdit_py_plugins.anchors import anchors_plugin
import bleach

_md = (
    MarkdownIt("commonmark", {"breaks": True, "linkify": True, "html": False})
    .enable("table")
    .enable("strikethrough")
    .use(anchors_plugin, min_level=2, max_level=3, slug_func=None, permalink=False)
)

_ALLOWED_TAGS = [
    "p", "br", "hr",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "strong", "em", "s", "del", "code", "pre",
    "ul", "ol", "li",
    "blockquote",
    "a",
    "table", "thead", "tbody", "tr", "th", "td",
    "span",
]
_ALLOWED_ATTRS = {
    "a": ["href", "title", "rel"],
    "h1": ["id"], "h2": ["id"], "h3": ["id"],
    "h4": ["id"], "h5": ["id"], "h6": ["id"],
    "th": ["align"], "td": ["align"],
    "span": ["class"],
}
_ALLOWED_PROTOCOLS = ["http", "https", "mailto"]


def render_markdown(source: str) -> str:
    """Render markdown → sanitized HTML. Safe for user-submitted input."""
    if not source:
        return ""
    html = _md.render(source)
    cleaned = bleach.clean(
        html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        protocols=_ALLOWED_PROTOCOLS,
        strip=True,
    )
    cleaned = bleach.linkify(
        cleaned,
        callbacks=[
            lambda attrs, new: {**attrs, (None, "rel"): "noopener nofollow ugc"},
        ],
    )
    return cleaned
```

### 3. Alembic migration

```
cd backend
alembic revision -m "add_annotation_resolve_and_proposal_body_html"
```

Edit the generated migration:

**upgrade():**
- Add to `annotations`: `resolved_at` (DateTime(timezone=True), nullable,
  default None)
- Add to `annotations`: `resolved_by_id` (UUID, nullable, FK to `users.id`
  ON DELETE SET NULL)
- Add to `proposals`: `body_html` (Text, NOT NULL, server_default='')
- Add to `proposal_versions`: `body_html` (Text, NOT NULL, server_default='')
- Backfill: for every proposal and proposal_version, render the existing
  `body` through `render_markdown` and UPDATE `body_html`. Use
  `op.get_bind()` + raw SELECT + Python loop + UPDATE. Import the renderer
  at the top of the migration file.

**downgrade():**
- Drop all four columns. Do not try to restore anything.

Apply: `alembic upgrade head`.

### 4. Update SQLAlchemy models

`backend/app/models/annotation.py` — add `Mapped` columns for `resolved_at`
and `resolved_by_id` matching the migration.

`backend/app/models/proposal.py` — add `body_html` to `Proposal` and to
`ProposalVersion`.

### 5. Update proposal schemas

`backend/app/schemas/proposal.py` — the read schema must include `body_html`.
Leave `body` in place (markdown source, useful for future editing).

### 6. Update proposal creation logic

`backend/app/api/v1/proposals.py`:

When a proposal is created, set `body_html = render_markdown(body)` on the
new row AND on the initial `ProposalVersion` snapshot.

If proposals have an update path or an amendment-accept flow that creates a
new `ProposalVersion` with different body text, render `body_html` there too.

Check the existing code for where `ProposalVersion` rows get inserted. If
there's a helper for creating versions, add the render call there — one place.

### 7. Create `backend/app/api/v1/_annotation_perms.py`

Full code:

```python
"""
Permission and phase-gate logic for annotation actions.

Separate file because these checks are called from multiple routes
(create, reply, react, resolve, unresolve, soft-delete) and the logic
should exist in exactly one place.
"""
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.annotation import Annotation
from app.models.community_membership import CommunityMembership, CommunityTier
from app.models.proposal import Proposal
from app.models.thread import Thread, ThreadStatus
from app.models.user import User


TIER_RANK = {
    CommunityTier.REGISTERED: 1,
    CommunityTier.PARTICIPANT: 2,
    CommunityTier.FACILITATOR: 3,
    CommunityTier.ADMIN: 4,
}


async def _get_community_context_for_proposal(
    db: AsyncSession, proposal_id
) -> tuple[Proposal, Thread]:
    result = await db.execute(select(Proposal).where(Proposal.id == proposal_id))
    proposal = result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(404, "Proposal not found")
    result = await db.execute(select(Thread).where(Thread.id == proposal.thread_id))
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(500, "Thread not found for proposal")
    return proposal, thread


async def _get_membership(
    db: AsyncSession, user_id, community_id
) -> CommunityMembership | None:
    result = await db.execute(
        select(CommunityMembership).where(
            CommunityMembership.user_id == user_id,
            CommunityMembership.community_id == community_id,
        )
    )
    return result.scalar_one_or_none()


async def require_can_annotate(
    db: AsyncSession, user: User, target_type: str, target_id
) -> tuple[Proposal | None, Thread | None]:
    """
    Returns (proposal, thread) when target_type='proposal' so callers can
    use them for audit logging without a redundant DB query. Returns
    (None, None) for target_type='wiki'. Raises HTTPException on denial.
    """
    if target_type == "wiki":
        if not user.is_annotator:
            raise HTTPException(403, "Annotator capability required for wiki annotations")
        return None, None

    if target_type == "proposal":
        proposal, thread = await _get_community_context_for_proposal(db, target_id)
        if thread.status != ThreadStatus.PROPOSING:
            raise HTTPException(
                403,
                "Annotations on proposals can only be created or modified "
                "during the PROPOSING phase",
            )
        membership = await _get_membership(db, user.id, thread.community_id)
        if not membership or TIER_RANK[membership.tier] < TIER_RANK[CommunityTier.REGISTERED]:
            raise HTTPException(403, "Community membership required")
        return proposal, thread

    raise HTTPException(400, f"Annotations on target_type={target_type!r} are not supported")


async def require_can_resolve(
    db: AsyncSession, user: User, annotation: Annotation
) -> tuple[Proposal, Thread]:
    if annotation.target_type != "proposal":
        raise HTTPException(400, "Only proposal annotations can be resolved")

    proposal, thread = await _get_community_context_for_proposal(db, annotation.target_id)

    if thread.status != ThreadStatus.PROPOSING:
        raise HTTPException(403, "Resolve/unresolve is only allowed during PROPOSING")

    if annotation.author_id == user.id:
        return proposal, thread
    if proposal.author_id == user.id:
        return proposal, thread
    membership = await _get_membership(db, user.id, thread.community_id)
    if membership and TIER_RANK[membership.tier] >= TIER_RANK[CommunityTier.FACILITATOR]:
        return proposal, thread

    raise HTTPException(
        403,
        "Only the annotation author, proposal author, or community "
        "facilitators can resolve this annotation",
    )


async def require_can_moderate(
    db: AsyncSession, user: User, annotation: Annotation
) -> tuple[Proposal | None, Thread | None]:
    if annotation.target_type == "wiki":
        if user.platform_role != "platform_admin" and not user.is_annotator:
            raise HTTPException(403, "Cannot moderate wiki annotations")
        return None, None

    if annotation.target_type == "proposal":
        proposal, thread = await _get_community_context_for_proposal(db, annotation.target_id)
        membership = await _get_membership(db, user.id, thread.community_id)
        if not membership or TIER_RANK[membership.tier] < TIER_RANK[CommunityTier.FACILITATOR]:
            raise HTTPException(
                403, "Only community facilitators can moderate proposal annotations"
            )
        return proposal, thread

    raise HTTPException(400, f"Cannot moderate annotations of type {annotation.target_type!r}")
```

Check the actual attribute name for the moderator check on wiki annotations.
If the existing wiki code uses different attributes than `is_annotator` /
`platform_role`, match what's already there. The goal is **preserve existing
behavior for wiki**; only add the new behavior for proposals.

### 8. Update annotation routes

In `backend/app/api/v1/annotations.py`:

For **create** (`POST /api/v1/annotations`):
- Replace any existing permission check with:
  `proposal, thread = await require_can_annotate(db, user, target_type, target_id)`
- When `target_type='proposal'`, pass `community_id=thread.community_id` to
  `log_event()`.
- When `target_type='wiki'`, pass `community_id=None`.

For **reply** and **react** endpoints:
- Same pattern — call `require_can_annotate` with the parent annotation's
  `target_type` and `target_id`. Pass `community_id` from the returned thread.

For **soft-delete / moderate**:
- Call `require_can_moderate` instead.
- Pass `community_id` from returned thread when `target_type='proposal'`.

### 9. Add resolve/unresolve endpoints

In `backend/app/api/v1/annotations.py`, add two new routes:

```python
@router.post("/annotations/{annotation_id}/resolve", response_model=AnnotationRead)
async def resolve_annotation(
    annotation_id: UUID,
    user: Annotated[User, Depends(get_registered_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    annotation = await db.get(Annotation, annotation_id)
    if not annotation:
        raise HTTPException(404)
    if annotation.resolved_at is not None:
        raise HTTPException(409, "Already resolved")

    proposal, thread = await require_can_resolve(db, user, annotation)

    annotation.resolved_at = datetime.now(timezone.utc)
    annotation.resolved_by_id = user.id

    await log_event(
        db,
        event_type="ANNOTATION_RESOLVED",
        actor_id=user.id,
        target_type="annotation",
        target_id=annotation.id,
        payload={
            "annotation_id": str(annotation.id),
            "annotation_target_type": annotation.target_type,
            "resolved_by_id": str(user.id),
        },
        community_id=thread.community_id,
    )

    await db.commit()
    await db.refresh(annotation)
    return annotation
```

Symmetric `unresolve_annotation` route:
- Returns 409 if `resolved_at is None`
- Sets `resolved_at = None`, `resolved_by_id = None`
- Logs `ANNOTATION_UNRESOLVED`

Match the actual dependency / user-fetching pattern used elsewhere in
`annotations.py`. The exact signatures above are illustrative.

### 10. Tests

Create these test files in `backend/tests/`:

**`test_annotation_perms.py`** — table-driven tests for
`require_can_annotate`. Cover:
- `target_type='wiki'` + user has annotator capability → passes
- `target_type='wiki'` + user without → 403
- `target_type='proposal'` + thread in PROPOSING + registered member → passes
- `target_type='proposal'` + thread in PROPOSING + non-member → 403
- `target_type='proposal'` + thread in DELIBERATING + registered member → 403
  (phase gate)
- `target_type='proposal'` + thread in VOTING + registered member → 403
- `target_type='document'` → 400

**`test_annotation_resolve.py`** — endpoint tests. Cover:
- Annotation author can resolve their own annotation
- Proposal author can resolve any annotation on their proposal
- Facilitator in community can resolve
- Non-member returns 403
- Registered non-author non-proposal-author returns 403
- Resolving already-resolved returns 409
- Cannot resolve when thread is in VOTING (403)
- Unresolve: resolved annotation returns to open
- Unresolve: unresolved annotation returns 409

**`test_proposal_markdown.py`** — rendering tests. Cover:
- Plain text passes through (wrapped in `<p>`)
- `## Heading` produces `<h2 id="heading">Heading</h2>`
- `### Sub` produces `<h3 id="sub">Sub</h3>`
- `<script>alert(1)</script>` is stripped
- External link gets `rel="noopener nofollow ugc"`
- Tables render correctly
- Empty string returns empty string

**Extend existing proposal tests** — assert that a newly created proposal
has a populated `body_html` field and that it matches
`render_markdown(body)`.

## Definition of done

Before you stop:
1. `pytest -v` passes with zero failures. Paste the output.
2. `alembic upgrade head` applies cleanly.
3. `alembic downgrade -1 && alembic upgrade head` works (forward/back
   migration is safe).
4. `curl /api/v1/proposals/{id}` (use an existing proposal ID from the dev
   DB) returns JSON with both `body` and `body_html`. `body_html` contains
   HTML with `id` attributes on h2/h3.
5. Creating an annotation on a proposal via `POST /api/v1/annotations`
   works during PROPOSING and fails with 403 during DELIBERATING.
6. Creating a wiki annotation still requires the annotator capability
   (regression check — paste the test output proving this).

## When you're done

After all verification steps above pass:

### 1. Commit and push

Commit the work on the `feature/proposal-review` branch:

```bash
git add -A
git commit -m "Session 1: backend foundations for proposal review

- Add markdown rendering for proposal bodies (body_html column)
- Add resolve/unresolve endpoints for annotations
- Add _annotation_perms helper with target_type branching
- Alembic migration + backfill for existing proposals"
git push
```

### 2. Print the handoff message

In your final chat response to the user, print a handoff message in a single
fenced code block so the user can copy it directly into the next Claude Code
instance. Use this exact structure — fill in the bracketed fields with real
values:

````
```
# Handoff from Session 1

**Branch:** feature/proposal-review (commit: [short sha])
**Status:** [Complete | Partial | Failed]

**Migration:** [filename] revision [hash]

**New files created:**
- [list them]

**Files modified:**
- [list them]

**Actual file paths / names that differed from the session plan:**
- [e.g., "annotation routes are in api/v1/annotations.py — matched plan"]
- [or "proposal creation is in api/v1/proposals.py:create_proposal line 87"]

**Dependencies installed:**
- markdown-it-py [version]
- mdit-py-plugins [version]
- bleach [version]

**Surprises / deviations from the plan:**
- [anything that didn't go as specified; "none" if nothing]

**Known issues or TODOs left open:**
- [anything Session 2 needs to know about; "none" is a valid answer]

**Verification results:**
- pytest: [N passed, M failed]
- alembic upgrade head: [success / failure]
- alembic downgrade -1 && upgrade head round trip: [success / failure]
- Sample proposal GET body_html populated: [yes / no]
- Create annotation in PROPOSING: [200 / other]
- Create annotation in DELIBERATING: [403 as expected / other]
- Wiki annotation regression check: [still works / broken]

**Notes for Session 2:**
- [anything worth flagging — actual route paths, models that got renamed,
  comment API shape, etc. "None" is a valid answer.]
```
````

### 3. Stop

Do not proceed to Session 2. The user will start Session 2 in a fresh
Claude Code instance with this handoff message as input.
