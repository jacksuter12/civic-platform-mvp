# Session 3 — Annotation system foundation (backend + frontend)

**Paste this entire file into a fresh Claude Code instance.** Along with
this file, the user will paste a "Handoff from Session 2" block containing
the actual file paths and API shapes from Session 2. Read that handoff
first — it's the source of truth for what Session 2 built.

**Suggested Claude Code settings for this session:**
- Plan Mode: **ON** (Shift+Tab to toggle)
- Auto-accept Edits: **OFF**
- Thinking effort: **HIGH** (this is the heaviest session in the whole
  chunk — new anchoring subsystem, multi-strategy logic, large surface area)

**This session is larger than prior ones.** Expect ~1500 lines of code
across ~15 files. Take the plan phase seriously and do not rush execution.

---

## Step 0 — Branch check

Sessions 1 and 2 worked on `feature/proposal-review`. Confirm you're on it
and pull any recent commits:

```bash
git branch --show-current    # expect: feature/proposal-review
git pull
```

If not on the branch: `git checkout feature/proposal-review`.

---

## Important architectural context — read this first

The existing codebase has an annotation system used by the wiki. We are
**not modifying the wiki's annotation modules.** The wiki will continue to
work exactly as it does today.

Instead, we're building a **new, purpose-built annotation system for
proposals** that will live alongside the wiki system. Both systems hit the
same backend endpoints (`/api/v1/annotations/*`) with `target_type` branching,
but the frontend modules are separate:

- Wiki uses: `annotations.js`, `annotation_ui.js`, `annotation_anchor.js`
  (unchanged in this session)
- Proposals will use: `proposal_annotations.js`, `proposal_annotation_ui.js`,
  `proposal_anchor.js` (new in this session)

**Do not import from or modify the wiki annotation modules.** Read them
only to understand patterns you might want to improve on. The new system
should be strictly better where it differs.

The shared backend is fine because the data model is already target-agnostic.
New endpoints we add (feature, orphan) are guarded server-side to work only
when `target_type='proposal'`.

A later, separate chunk migrates the wiki to the new annotation system.
That migration is explicitly out of scope here.

## What you're building

A complete annotation system for the proposal review page. By the end:

- Users select text in the proposal → an annotation composer appears
- Submitting creates an annotation anchored to the selected text via
  multi-strategy anchoring (W3C-style selector array)
- Annotations render as cards in the right pane and as highlights in the doc
- Clicking a highlight scrolls to the card; clicking a card scrolls to the
  highlight
- Users can reply to annotations (threaded, nested visually)
- Users can react with endorse / needs-work
- Annotation author, proposal author, or facilitator can resolve; anyone
  with permission can reopen
- Facilitator can feature (pin) an annotation to the top; can also moderate
  (soft-delete with required reason)
- When the proposal body changes and an anchor no longer resolves,
  the client marks it orphaned and the annotation is visibly flagged

Polish features (filter UI, sort UI, polling refresh, keyboard navigation,
read-only mode, proper modals) come in Session 4. Session 3 builds the
foundation that makes those additions straightforward.

## Context — what's in place

From Session 1 (backend):
- `annotations` table has `resolved_at` and `resolved_by_id` columns
- `POST /api/v1/annotations/{id}/resolve` and `/unresolve` endpoints
- `_annotation_perms.py` with `require_can_annotate`, `require_can_resolve`,
  `require_can_moderate` — all branch on `target_type`
- Server-side markdown rendering (`body_html` on proposals)

From Session 2 (frontend):
- `/c/{slug}/thread/{tid}/proposal/{pid}` page renders; doc in `#pr-doc`
- Right pane `#pr-anno` contains `.pr-anno-head`, `.pr-anno-list` with a
  placeholder
- `api.js` has `resolveAnnotation`, `unresolveAnnotation`
- Script load order: `config.js → utils.js → auth.js → api.js → nav.js →
  toc.js → proposal_review.js`

## Hard constraints (from CLAUDE.md — re-verify before starting)

1. Wiki annotation modules are untouched. They must continue to work.
2. Phase gates enforced server-side. Client UI reflects them (read-only
   mode in VOTING+) — server enforces truth.
3. Reactions never determine default display order. The default sort is
   chronological by anchor position in the document. Users may manually
   select other sorts (reactions, recency) but that is user-chosen view
   state, not algorithmic amplification.
4. Audit log is append-only; every state change writes an event.
5. Every community-scoped event passes `community_id` (the proposal's
   thread's community).
6. `api.js` stays framework-agnostic — fetch + data only, no DOM.
7. No `localStorage` for app data state.

## Plan Mode — read these files first (mandatory)

Before producing a plan, read these files. Do not skip this step.

- `backend/app/models/annotation.py` — current schema shape
- `backend/app/schemas/annotation.py` — response schema
- `backend/app/api/v1/annotations.py` — existing routes (create, list,
  react, soft-delete, resolve from Session 1)
- `backend/app/api/v1/_annotation_perms.py` — Session 1's permission logic
- `backend/app/static/js/annotation_anchor.js` — **read to learn from, not
  to copy**. Note what anchoring strategy it uses and what its limitations
  are. Your new module should improve on it.
- `backend/app/static/js/annotation_ui.js` — same instruction as above
- `backend/app/static/js/annotations.js` — same
- `backend/app/templates/proposal_review.html` — where you'll inject
- `backend/app/static/js/proposal_review.js` — where you'll wire init
- `backend/app/static/css/proposal_review.css` — where annotation CSS goes
- `backend/app/core/audit.py` — audit log signature
- `backend/app/models/proposal.py` — for the Track Changes forward-compat
  schema work below

After reading, your plan must explicitly address:

1. What anchoring strategies will the new `proposal_anchor.js` use?
   (Recommended: W3C Web Annotation format with `TextQuoteSelector` +
   `TextPositionSelector` in a `selector` array, with a `RangeSelector`
   as optional third fallback.)
2. Does `annotations` table already have `parent_annotation_id` for
   threading? (If yes, reuse. If no, add in migration.)
3. What new fields need adding to the annotation migration?
4. What new endpoints need adding?
5. What's the DOM structure of the annotation UI? (Parent container for
   card list; card structure; reply nesting; composer positioning.)
6. How will highlights be rendered in the doc? (Wrapping spans with a
   class; clickable.)
7. **For the Track Changes forward-compat schema work (Work item 0
   below):** what's in the existing `ProposalVersion` model, and what
   does it currently get populated with at proposal-creation time?

## Work items

### 0. Backend — Track Changes forward-compat schema (DATA ONLY)

**Important: this work item adds columns and backfills data. It does NOT
build any Track Changes feature. It does NOT add endpoints, business
logic, or UI. It does NOT modify any existing route handlers.**

Track Changes (a PR-style "suggested revision" workflow for proposals) is
deferred to Chunk B. But the data model needs to be forward-compatible so
Chunk B isn't blocked by an annotation-shaped schema. Adding the columns
now is cheap; adding them later means a second migration over data the
annotations have already accumulated against. We're spending ~50 lines of
migration work to avoid coupling.

**What ships in Chunk B (NOT this session):** suggested-revision endpoints,
diff view UI, accept/reject/withdraw workflow, editor role/capability,
per-suggestion permission logic. None of that exists yet.

**What this session does:** add four columns to `proposal_versions` with
safe defaults, backfill existing rows, update the model.

#### Migration

Create: `backend/alembic/versions/{rev}_proposal_version_track_changes_schema.py`

Add columns to `proposal_versions`:

- `status` — enum `('accepted', 'suggested', 'rejected', 'withdrawn')`
  with NOT NULL constraint and `server_default='accepted'`. Use a real
  PostgreSQL enum type (`sa.Enum(..., name='proposal_version_status')`)
  rather than a string column.
- `authored_by_id` — UUID, nullable, FK to `users.id` ON DELETE SET NULL.
  Indicates who drafted this version, which may differ from the proposal
  owner once Track Changes is live. Backfill to `proposal.author_id` for
  every existing row.
- `parent_version_id` — UUID, nullable, FK to `proposal_versions.id` ON
  DELETE SET NULL. Points to the version a suggestion was based on.
  Backfill: leave NULL for now (existing versions have no suggestion
  history).
- `decided_at` — DateTime with timezone, nullable, default None. When the
  status transitioned out of `suggested`. Backfill: copy from
  `created_at` for existing accepted versions (they were "decided" the
  moment they were created since there's no suggestion phase yet).
- `decided_by_id` — UUID, nullable, FK to `users.id` ON DELETE SET NULL.
  Who accepted/rejected. Backfill: copy from `proposal.author_id` for
  existing accepted versions.
- `decision_reason` — Text, nullable, default None. Optional rationale
  on accept/reject. Backfill: leave NULL.

**Backfill logic** in the migration's upgrade(): JOIN `proposal_versions`
to `proposals` to populate `authored_by_id` and `decided_by_id` from the
proposal's `author_id`. Set `decided_at = created_at` for all existing
rows.

**downgrade():** drop all six columns and the enum type. Don't try to
preserve data.

This migration is **separate from** the annotations migration in Work
item 1. Do them as two distinct revisions so they can be reverted
independently.

#### Model update

Edit `backend/app/models/proposal.py`:

```python
import enum

class ProposalVersionStatus(str, enum.Enum):
    accepted = "accepted"      # currently authoritative, or historically so
    suggested = "suggested"    # proposed change, not yet decided
    rejected = "rejected"      # proposed change declined
    withdrawn = "withdrawn"    # editor withdrew before decision

class ProposalVersion(Base):
    # ... existing columns ...
    status: Mapped[ProposalVersionStatus] = mapped_column(
        sa.Enum(ProposalVersionStatus, name="proposal_version_status"),
        nullable=False,
        default=ProposalVersionStatus.accepted,
    )
    authored_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    parent_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("proposal_versions.id"),
        nullable=True,
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
```

#### Update existing version-creation code

Find every place a `ProposalVersion` is created (proposal creation,
amendment-accept flow, etc.). Set the new fields explicitly:

```python
ProposalVersion(
    # ... existing fields ...
    status=ProposalVersionStatus.accepted,
    authored_by_id=proposal.author_id,
    parent_version_id=None,
    decided_at=datetime.now(timezone.utc),
    decided_by_id=proposal.author_id,
    decision_reason=None,
)
```

This preserves current behavior. Every version created the old way is
immediately `accepted`, authored by and decided by the proposal author.
When Track Changes ships, suggestion-creation code will set different
values; existing routes are unchanged.

#### Schema update

Edit the `ProposalVersion` Pydantic schema (likely `backend/app/schemas/proposal.py`)
to include the new fields in the response model. Do not omit them — Chunk
B's UI will need them, and shipping them in the API now means no contract
break later.

#### Tests

Add to existing `test_proposal_creation.py` (or wherever proposal version
tests live):

- After creating a proposal, assert the new ProposalVersion has
  `status=='accepted'`, `authored_by_id == proposal.author_id`,
  `decided_by_id == proposal.author_id`, `parent_version_id is None`,
  `decided_at is not None`.
- Migration round-trip (upgrade → downgrade → upgrade) leaves the table
  in the expected state.
- Backfill correctness: an existing version (created by the migration
  against pre-existing data) has correct `authored_by_id` and
  `decided_by_id` matching its proposal's author.

**Do NOT add** any new endpoints, permission helpers, capability roles,
or UI. Track Changes business logic is Chunk B.

#### Decision log entry

Append to `docs/decisions.md` (commit separately from the code changes,
with a clear "decision log" commit message):

```markdown
## [current date] — Track Changes Deferred to Chunk B; Schema Forward-Compatible Now
**Status:** Active
**Domain:** Technical / Mechanism
**Context:** A "Track Changes" workflow (PR-style suggested revisions
to proposals, with editor attribution and accept/reject by proposal
author or facilitators) is wanted but is a chunk-sized feature in
itself. Building it alongside the annotation system would have doubled
Chunk A's scope.
**Decision:** Defer Track Changes to a dedicated Chunk B (~2-3 sessions).
Add the data model columns now (`ProposalVersion.status`,
`authored_by_id`, `parent_version_id`, `decided_at`, `decided_by_id`,
`decision_reason`) so Chunk A's annotation work and Chunk B's Track
Changes work don't collide on the schema. Existing version-creation
code populates the new fields with safe defaults that preserve current
behavior.
**Reasoning:** Migrations over a populated `annotations` table are more
painful than over an empty one. The columns are cheap to add now and
expensive to retrofit. Keeping the feature work entirely deferred while
the schema work happens up front is the right tradeoff.
**Implications:** No behavior change in this chunk. Chunk B will add:
new endpoints (`POST /proposals/{id}/suggestions`, accept/reject/withdraw),
an "editor" capability or role on `CommunityMembership` (orthogonal to
the existing tier system), diff view UI, suggestion review page or panel.
The new `parent_version_id` column will let Chunk B detect stale
suggestions (parent has been superseded). Suggested revisions and the
existing Amendment workflow will coexist — the semantic distinction
between them is documented in Chunk B's design.
**Revisit if:** Chunk B is deprioritized for >6 months, in which case
the columns become dead schema and we should reassess.
```

---

### 1. Backend — annotation migration

Create: `backend/alembic/versions/{rev}_annotation_threading_feature_orphan.py`

Add columns to `annotations`:

- `parent_annotation_id` (UUID, nullable, FK to `annotations.id` ON DELETE
  CASCADE) — only if not already present
- `featured_at` (DateTime with timezone, nullable, default None)
- `featured_by_id` (UUID, nullable, FK to `users.id` ON DELETE SET NULL)
- `orphaned_at` (DateTime with timezone, nullable, default None)

Add an index on `(target_type, target_id, created_at)` for efficient list
queries — check if it already exists first.

The `anchor` column should remain JSON. No schema change needed; we change
the shape of what's stored (selector array). Document the new anchor shape
in a docstring on the column.

Apply the migration. Test upgrade/downgrade round trip.

### 2. Backend — update model and schema

Add the new `Mapped[]` columns to `backend/app/models/annotation.py`.

Update `backend/app/schemas/annotation.py`:

- `AnnotationRead` (or equivalent) adds:
  - `parent_annotation_id: UUID | None`
  - `featured_at: datetime | None`
  - `featured_by_id: UUID | None`
  - `orphaned_at: datetime | None`
  - `replies: list["AnnotationRead"] = []` (nested — populated in list query)
  - `reactions: dict` (counts + current user's own reaction — check if
    already present; shape `{"endorse": 3, "needs_work": 1, "my": "endorse"}`)
  - `can_resolve: bool` (computed — see below)
  - `can_moderate: bool` (computed)
  - `can_feature: bool` (computed — facilitator only, proposal-type only)

- `AnnotationCreate` adds:
  - `parent_annotation_id: UUID | None = None` (for creating a reply)
  - Accept the W3C anchor shape in `anchor` JSON (document it; runtime
    validation can be minimal for MVP)

### 3. Backend — add permission check helpers

Add to `backend/app/api/v1/_annotation_perms.py`:

```python
async def check_can_resolve(
    db: AsyncSession, user: User | None, annotation: Annotation
) -> bool:
    """Non-raising version of require_can_resolve for UI hints."""
    if not user:
        return False
    try:
        await require_can_resolve(db, user, annotation)
        return True
    except HTTPException:
        return False


async def check_can_moderate(
    db: AsyncSession, user: User | None, annotation: Annotation
) -> bool:
    if not user:
        return False
    try:
        await require_can_moderate(db, user, annotation)
        return True
    except HTTPException:
        return False


async def require_can_feature(
    db: AsyncSession, user: User, annotation: Annotation
) -> tuple[Proposal, Thread]:
    """Only facilitators in community can feature; proposal-type only."""
    if annotation.target_type != "proposal":
        raise HTTPException(400, "Only proposal annotations can be featured")
    proposal, thread = await _get_community_context_for_proposal(
        db, annotation.target_id
    )
    membership = await _get_membership(db, user.id, thread.community_id)
    if not membership or TIER_RANK[membership.tier] < TIER_RANK[CommunityTier.FACILITATOR]:
        raise HTTPException(
            403, "Only community facilitators can feature annotations"
        )
    return proposal, thread


async def check_can_feature(
    db: AsyncSession, user: User | None, annotation: Annotation
) -> bool:
    if not user:
        return False
    try:
        await require_can_feature(db, user, annotation)
        return True
    except HTTPException:
        return False
```

Then use `check_*` functions when serializing the annotation response to
set the computed `can_*` fields.

### 4. Backend — add new routes

In `backend/app/api/v1/annotations.py`:

**Feature / unfeature:**

```python
@router.post("/annotations/{annotation_id}/feature", response_model=AnnotationRead)
async def feature_annotation(
    annotation_id: UUID,
    user: Annotated[User, Depends(get_registered_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    annotation = await db.get(Annotation, annotation_id)
    if not annotation:
        raise HTTPException(404)
    if annotation.featured_at is not None:
        raise HTTPException(409, "Already featured")

    proposal, thread = await require_can_feature(db, user, annotation)

    annotation.featured_at = datetime.now(timezone.utc)
    annotation.featured_by_id = user.id

    await log_event(
        db,
        event_type="ANNOTATION_FEATURED",
        actor_id=user.id,
        target_type="annotation",
        target_id=annotation.id,
        payload={"annotation_id": str(annotation.id)},
        community_id=thread.community_id,
    )

    await db.commit()
    await db.refresh(annotation)
    return annotation
```

Symmetric `unfeature` route. Audit event `ANNOTATION_UNFEATURED`.

**Mark orphaned (client reports):**

```python
@router.post("/annotations/{annotation_id}/mark-orphaned", response_model=AnnotationRead)
async def mark_orphaned(
    annotation_id: UUID,
    user: Annotated[User, Depends(get_registered_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    annotation = await db.get(Annotation, annotation_id)
    if not annotation:
        raise HTTPException(404)
    # Only proposal annotations get orphaned (wiki has different semantics).
    if annotation.target_type != "proposal":
        raise HTTPException(400)
    # Anyone viewing the proposal can report orphan — it's a factual claim
    # about anchor resolution, not a privileged action. Idempotent.
    if annotation.orphaned_at is None:
        annotation.orphaned_at = datetime.now(timezone.utc)
        # Get community for audit context.
        _, thread = await _get_community_context_for_proposal(
            db, annotation.target_id
        )
        await log_event(
            db,
            event_type="ANNOTATION_ORPHANED",
            actor_id=user.id,
            target_type="annotation",
            target_id=annotation.id,
            payload={"annotation_id": str(annotation.id)},
            community_id=thread.community_id,
        )
        await db.commit()
        await db.refresh(annotation)
    return annotation
```

**Threaded reply:**

If the existing annotation POST route already supports
`parent_annotation_id`, reuse it. If not, add handling: when
`parent_annotation_id` is present on create, the new annotation inherits
`target_type` and `target_id` from the parent (don't trust client input
for these on replies), and skips the anchor check (replies aren't
anchored — the parent's anchor is shared).

**List with threads:**

Update the list query (`GET /api/v1/annotations?target_type=...&target_id=...`)
to return top-level annotations (where `parent_annotation_id IS NULL`) with
their replies nested as `replies` array. Two approaches — pick one:

a. Single query with manual tree-assembly in Python (fetch all, then
   group by parent). Simpler, fine for <100 annotations per target.
b. Two queries + assembly. Also fine.

Default sort: chronological by created_at. Featured items surface first
(within the list, not across; featured doesn't break the chronological
order for non-featured items). Document this in code.

### 5. Backend — tests

Create/extend:

- `test_annotation_threading.py` — reply creation, tree structure in
  response, `target_type`/`target_id` inheritance on replies
- `test_annotation_feature.py` — feature/unfeature permission matrix,
  non-facilitator returns 403, wiki target_type returns 400
- `test_annotation_orphan.py` — mark-orphaned is idempotent, audit event
  written, only proposal target_type accepted
- Extend `test_annotation_perms.py` — `check_*` helpers return correct
  booleans matching the `require_*` behavior

Run `pytest -v`, ensure zero failures.

### 6. Frontend — `backend/app/static/js/proposal_anchor.js`

New module. **This is the most complex new file.** It handles text-range
anchoring using a multi-strategy approach (W3C Web Annotation Data Model).

Public API:

```javascript
window.ProposalAnchor = {
  // Given a Selection object (or Range), compute an anchor JSON with
  // multiple strategies. Returns { selector: [...] }.
  serialize(range, rootEl) { ... },

  // Given an anchor JSON, find a Range in rootEl. Returns Range or null
  // if no strategy resolves. Tries strategies in order.
  deserialize(anchor, rootEl) { ... },

  // Apply a highlight to a range. Wraps the range contents in
  // <span class="proposal-annotation-highlight" data-anno-id="{id}">.
  // Handles the case where the range spans multiple text nodes by
  // splitting at element boundaries (wrap each text-node chunk).
  applyHighlight(range, annotationId, highlightClass = 'proposal-annotation-highlight') { ... },

  // Remove all highlights with a given annotation ID.
  removeHighlight(annotationId) { ... },

  // Scroll the doc so a highlight is visible.
  scrollTo(annotationId) { ... },
};
```

**Strategy 1 — TextQuoteSelector (primary).**

Serialize:
```javascript
{
  type: "TextQuoteSelector",
  exact: "<the selected text>",
  prefix: "<up to 32 chars of text before>",
  suffix: "<up to 32 chars of text after>"
}
```

Deserialize: walk text nodes of `rootEl`, find all occurrences of `exact`.
If multiple, disambiguate using prefix + suffix. Return a Range covering
the match, or null.

**Strategy 2 — TextPositionSelector (fallback).**

Serialize:
```javascript
{
  type: "TextPositionSelector",
  start: <character offset from start of rootEl's text>,
  end: <character offset from start of rootEl's text>
}
```

Character offset = count of all text node characters up to and including
the selection start, walking the tree in document order. Skip whitespace?
No — keep the raw character count; it's more robust.

Deserialize: walk text nodes, count characters, build a Range that starts
at `start` and ends at `end`.

**Strategy 3 — RangeSelector (optional — skip for Session 3 if short on
time, add in Session 4).** DOM path-based. Most fragile; last resort.

**Deserialize algorithm:**

```javascript
deserialize(anchor, rootEl) {
  const selectors = anchor.selector || [];
  const quote = selectors.find(s => s.type === 'TextQuoteSelector');
  if (quote) {
    const range = findByTextQuote(rootEl, quote);
    if (range) return range;
  }
  const position = selectors.find(s => s.type === 'TextPositionSelector');
  if (position) {
    const range = findByTextPosition(rootEl, position);
    if (range) return range;
  }
  // All strategies failed → orphan
  return null;
}
```

**Highlight application — handle ranges that cross element boundaries.**
A naive `range.surroundContents(span)` fails if the range contains partial
elements. Use this approach: walk text nodes within the range; for each,
split the text node at the range boundaries and wrap the relevant portion
in a span. Each span gets the same `data-anno-id` so they all respond to
hover/click as one logical highlight.

When highlights overlap (two annotations on overlapping text), nest spans.
The outer highlight + inner highlight CSS uses different underline colors
or thicker borders. Keep it simple for v1 — just nest; style is polish.

**Reference:** the W3C Web Annotation spec has these selector formats.
The Hypothesis `dom-anchor-text-quote` and `dom-anchor-text-position`
npm packages are small (<200 LOC each); you can port the core logic.
**Do not fetch from a CDN — vendor the logic directly in the module file.**

This module should be ~250-350 lines including comments.

### 7. Frontend — `backend/app/static/js/proposal_annotations.js`

New module. Data layer and orchestration.

Public API:

```javascript
window.ProposalAnnotations = {
  // Called once from proposal_review.js.
  async init(config) {
    // config = {
    //   proposalId, threadStatus (e.g. 'PROPOSING'),
    //   docEl, sidebarEl, headerCountEl,
    //   currentUser, // { id, display_name } or null
    //   onChange,    // optional callback invoked after any state change
    // }
    this._config = config;
    this._annotations = [];  // flat array of top-level + nested in replies
    await this._load();
    this._render();
    this._bindTextSelection();
  },

  async reload() { ... },

  async create({ anchor, body, parentAnnotationId }) { ... },
  async reply(parentId, body) { return this.create({body, parentAnnotationId: parentId}); },
  async react(annotationId, reactionType) { ... },   // toggle
  async resolve(annotationId) { ... },
  async unresolve(annotationId) { ... },
  async feature(annotationId) { ... },
  async unfeature(annotationId) { ... },
  async moderate(annotationId, reason) { ... },
  async markOrphaned(annotationId) { ... },

  _load() { ... },   // fetch annotations, resolve anchors, apply highlights
  _render() { ... }, // call ProposalAnnotationUI.render with current state
  _bindTextSelection() { ... }, // listen for selection in docEl; show composer
};
```

Key behaviors:

- On load: fetch annotations from
  `GET /api/v1/annotations?target_type=proposal&target_id={proposalId}`.
- For each annotation, call `ProposalAnchor.deserialize(annotation.anchor, docEl)`.
  If it returns null and `annotation.orphaned_at` is null, call
  `this.markOrphaned(annotation.id)` (client reporting). If it returns a
  Range, call `ProposalAnchor.applyHighlight(range, annotation.id)`.
- After any mutation, re-fetch and re-render. Simple, reliable.
- Text selection handling: listen for `selectionchange` on document or
  `mouseup` in docEl. When the selection is non-empty and within docEl
  and the user is signed in and phase is PROPOSING: show the "Annotate"
  chip near the selection. On click: serialize the anchor, open the
  composer in the sidebar, store the pending anchor.

This module should be ~200-300 lines.

### 8. Frontend — `backend/app/static/js/proposal_annotation_ui.js`

New module. Pure rendering. Receives state from ProposalAnnotations and
renders into sidebarEl.

Public API:

```javascript
window.ProposalAnnotationUI = {
  init(config) { ... },
  render(annotations, state) { ... },     // state = { pendingAnchor, isReadOnly, ... }
  showComposer(anchor, { replyTo = null } = {}) { ... },
  hideComposer() { ... },
  scrollToCard(annotationId) { ... },
};
```

Card structure (as rendered HTML):

```html
<article class="proposal-annotation-card" data-anno-id="{id}"
         data-status="open|resolved" data-featured="true|false"
         data-orphaned="true|false">
  <header class="paa-card-head">
    <span class="paa-author">{display_name}</span>
    <time class="paa-ts">{timeAgo}</time>
    <span class="paa-featured-tag" hidden>Featured</span>
    <span class="paa-resolved-tag" hidden>Resolved</span>
    <span class="paa-orphaned-tag" hidden>Anchor changed</span>
    <button class="paa-menu-btn" hidden aria-label="Actions">⋯</button>
  </header>
  <blockquote class="paa-anchor-quote">{exact text from anchor}</blockquote>
  <div class="paa-body">{body}</div>
  <footer class="paa-card-actions">
    <button class="paa-react" data-reaction="endorse">Endorse · {n}</button>
    <button class="paa-react" data-reaction="needs_work">Needs work · {n}</button>
    <button class="paa-reply-btn">Reply</button>
    <button class="paa-resolve-btn" hidden>Resolve</button>
    <button class="paa-unresolve-btn" hidden>Reopen</button>
  </footer>
  <ol class="paa-replies">
    <!-- Nested reply cards here, recursively -->
  </ol>
  <form class="paa-reply-form" hidden>
    <textarea required></textarea>
    <button type="submit">Post reply</button>
    <button type="button" class="paa-reply-cancel">Cancel</button>
  </form>
</article>
```

Visibility rules (apply on render):
- `paa-featured-tag`: show when `featured_at` is not null
- `paa-resolved-tag`: show when `resolved_at` is not null
- `paa-orphaned-tag`: show when `orphaned_at` is not null
- `paa-resolve-btn`: show when `can_resolve` is true, not resolved,
  not read-only
- `paa-unresolve-btn`: show when `can_resolve` is true, resolved,
  not read-only
- `paa-menu-btn`: show when `can_moderate` is true OR `can_feature` is true.
  Menu contents depend on which flags are true.
- Reply button: hidden in read-only mode
- Composer: hidden in read-only mode

Event delegation: attach one click listener to sidebarEl, dispatch based
on target class.

Click a card (outside buttons) → `ProposalAnchor.scrollTo(id)` (scroll
doc to its anchor).

Click a highlight in docEl → `ProposalAnnotationUI.scrollToCard(id)`
(scroll sidebar to its card). This wire lives in ProposalAnnotations.

**Composer:** appears as a form replacing the placeholder when
`showComposer(anchor)` is called. Shows the quoted anchor text. Textarea
for body. Submit / cancel. For reply composition, `showComposer(null, { replyTo })`
uses the `paa-reply-form` inside the parent card instead.

**Moderation modal** (if triggered from menu) — Session 4 will make this
proper. For Session 3, use a simple `prompt()` for the reason or a minimal
inline form. Note this in the handoff.

This module should be ~400-500 lines.

### 9. Frontend — update `api.js`

Add to `backend/app/static/js/api.js`:

```javascript
api.fetchAnnotations = async (target_type, target_id) => { ... };
api.createAnnotation = async ({ target_type, target_id, anchor, body, parent_annotation_id }) => { ... };
api.reactToAnnotation = async (id, reaction_type) => { ... };
api.unreactAnnotation = async (id) => { ... };
api.featureAnnotation = async (id) => { ... };
api.unfeatureAnnotation = async (id) => { ... };
api.markAnnotationOrphaned = async (id) => { ... };
api.moderateAnnotation = async (id, reason) => { ... };
// resolveAnnotation / unresolveAnnotation already exist from Session 2
```

Confirm actual backend route paths match. If a reaction route differs
(e.g. POST `/annotations/{id}/reactions` vs. PATCH), match what's there.

### 10. Frontend — update `proposal_review.html`

Insert the new scripts in load order (between `api.js` and `nav.js`):

```html
<script src="/static/js/api.js"></script>
<script src="/static/js/proposal_anchor.js"></script>
<script src="/static/js/proposal_annotations.js"></script>
<script src="/static/js/proposal_annotation_ui.js"></script>
<script src="/static/js/nav.js"></script>
<script src="/static/js/toc.js"></script>
<script src="/static/js/proposal_review.js"></script>
```

Remove the `.pr-anno-placeholder` div inside `.pr-anno-list` — it's no
longer needed.

### 11. Frontend — update `proposal_review.js`

After `renderDoc(proposal)` finishes and `initTOC()` runs, initialize the
annotation system. Also fetch current user info for permission display:

```javascript
// After renderDoc + initTOC, before rendering signals/comments
await ProposalAnnotations.init({
  proposalId: proposal.id,
  threadStatus: thread.status,     // from thread fetch in Session 2
  docEl: document.getElementById('pr-doc'),
  sidebarEl: document.getElementById('pr-anno-list'),
  headerCountEl: document.getElementById('pr-anno-count'),
  currentUser: auth.isSignedIn()
    ? { id: auth.getUserId(), display_name: auth.getDisplayName() }
    : null,
});
```

If `auth.js` doesn't expose `getUserId()` / `getDisplayName()`, use a
`GET /api/v1/me` call at the top of `load()` and pass through. Document
actual approach in handoff.

### 12. CSS — add to `proposal_review.css`

Sections:

**Highlights in the doc:**

```css
.proposal-annotation-highlight {
  background: color-mix(in srgb, #FAC775 40%, transparent);
  border-bottom: 1.5px solid #BA7517;
  cursor: pointer;
  padding: 1px 0;
}
.proposal-annotation-highlight:hover {
  background: color-mix(in srgb, #FAC775 60%, transparent);
}
.proposal-annotation-highlight[data-featured="true"] {
  border-bottom-width: 2px;
}
.proposal-annotation-highlight[data-orphaned="true"] {
  background: repeating-linear-gradient(
    45deg, transparent, transparent 3px,
    color-mix(in srgb, #999 30%, transparent) 3px,
    color-mix(in srgb, #999 30%, transparent) 6px
  );
}
```

**Cards, replies, composer, menu, modal stub.** Match existing site
aesthetic (muted, library-like). ~200 lines of CSS total.

## Definition of done

**Track Changes schema (Work item 0):**

1. New ProposalVersion columns exist in DB: `status`, `authored_by_id`,
   `parent_version_id`, `decided_at`, `decided_by_id`, `decision_reason`.
2. `alembic upgrade head && alembic downgrade -1 && alembic upgrade head`
   round-trips cleanly across BOTH new migrations (the schema migration
   and the annotation migration).
3. Existing ProposalVersion rows have `status='accepted'`, `authored_by_id`
   and `decided_by_id` populated to the proposal author, `decided_at` set
   to `created_at`. Verify via direct DB query in your dev DB.
4. Creating a new proposal still works end-to-end and the new version
   inherits the safe defaults (test passes).
5. No existing route or test had to change behavior to keep working —
   only to set the new fields explicitly.

**Annotation system (Work items 1-12):**

6. `pytest -v` passes with zero failures.
7. Navigate to a proposal review page in PROPOSING phase.
8. Select text in the doc → "Annotate" chip appears → click → composer
   opens in sidebar with quoted text.
9. Submit an annotation → it appears as a card in the sidebar AND as a
   highlighted range in the doc.
10. Reload the page → the annotation persists, highlight reappears.
11. Click a highlight → sidebar scrolls to its card.
12. Click a card → doc scrolls to its highlight.
13. Reply to an annotation → reply nests under the parent card.
14. React with endorse → count increments; click again → count decrements
    (toggle).
15. As annotation author: resolve → card gets muted "Resolved" tag;
    unresolve round-trips.
16. As facilitator (set a test user's `CommunityMembership.tier` to
    `facilitator`): feature an annotation → gets "Featured" tag, surfaces
    at top of list; unfeature round-trips. Moderate an annotation with
    reason → annotation removed from sidebar; audit log shows
    `ANNOTATION_MODERATED` event with `community_id` and reason.
17. Edit the proposal body (via direct DB update or admin route) to remove
    an annotation's anchor text. Reload. The orphaned annotation:
    - Shows the "Anchor changed" flag
    - `orphaned_at` is set in DB
    - Audit log has `ANNOTATION_ORPHANED` event
18. **Wiki regression check**: open a wiki article with existing annotations.
    Verify they render, can be created, replied to, reacted to, moderated.
    No new errors. Wiki annotations do NOT show resolve or feature buttons.
19. No console errors on any page touched.
20. Advance a thread to VOTING: verify annotations still visible but no
    action buttons appear (read-only hints). This is basic — full
    read-only polish is Session 4.

## When you're done

### 1. Commit and push

This session produced two distinct sets of work that should be committed
separately so the history is readable and either can be reverted
independently:

```bash
# Commit A — Track Changes schema forward-compat (data only)
git add backend/alembic/versions/{the_proposal_version_track_changes_revision}*
git add backend/app/models/proposal.py backend/app/schemas/proposal.py
# Plus any test files for this commit and any version-creation code
# updates that set the new defaults.
git commit -m "Add ProposalVersion fields for Track Changes (schema only)

Adds status, authored_by_id, parent_version_id, decided_at, decided_by_id,
decision_reason. Backfills existing versions to status='accepted' with
proposal author as authored_by and decided_by. No behavior change.
Track Changes feature work is deferred to Chunk B."

# Commit B — annotation system foundation
git add -A
git commit -m "Session 3: new annotation system foundation for proposals

- Add migration: parent_annotation_id, featured_*, orphaned_at columns
- Add feature/unfeature/mark-orphaned endpoints
- Add can_resolve/can_moderate/can_feature computed fields
- New frontend modules: proposal_anchor.js (multi-strategy anchoring),
  proposal_annotations.js (data layer), proposal_annotation_ui.js (rendering)
- Wire into proposal_review.js and proposal_review.html
- Wiki annotation system left untouched"

git push
```

### 2. Add decision log entries

Append BOTH decision entries to `docs/decisions.md` — the one drafted in
Work item 0 (Track Changes deferral) and the one below (new annotation
system) — then commit them together:

```markdown
## [current date] — New Annotation System for Proposals, Wiki Migration Deferred
**Status:** Active
**Domain:** Technical
**Context:** Extending the wiki annotation system to proposals would constrain
the proposal annotation UX to wiki-editorial assumptions. Proposals need
richer anchoring, threading, resolve workflow, and facilitator moderation
than the wiki needs.
**Decision:** Build a new annotation system purpose-built for proposals
(proposal_anchor.js, proposal_annotations.js, proposal_annotation_ui.js).
Wiki continues to use its existing modules. Both share the backend
annotations table and routes, with target_type branching.
**Reasoning:** Proposal annotations drive allocation decisions — anchor
integrity and moderation workflows matter more than in editorial wiki
review. Designing for proposals without retrofitting from wiki produces a
better proposal UX. Two frontend codebases will coexist temporarily; a
future chunk migrates wiki to the new system.
**Implications:** Temporary divergence in frontend annotation logic.
Shared backend keeps data consistent. Wiki migration is future work — it
adds comments (for admins/moderators), upgrades the wiki to multi-strategy
anchoring, and consolidates the two frontend codebases into one.
**Revisit if:** Maintenance cost of two codebases outweighs the design
benefit, or wiki migration is deprioritized for >6 months.
```

Commit the decisions: `git commit -m "Log decisions: annotation system + Track Changes deferral"`

### 3. Take screenshots

Paste screenshots showing:
- Proposal review page with at least 3 annotations (mix of open, resolved,
  featured)
- An annotation with at least one reply
- The moderation action triggered (annotation removed after)
- An orphaned annotation
- A wiki page with its annotations still working (regression proof)

### 4. Print the handoff message

In your final chat response, print a handoff message in a single fenced
code block. Fill in every bracketed field:

````
```
# Handoff from Session 3

**Branch:** feature/proposal-review (commit: [short sha])
**Status:** [Complete | Partial | Failed]

**Migrations created (two distinct revisions):**
- Track Changes schema: [filename] revision [hash]
- Annotation threading/feature/orphan: [filename] revision [hash]

**New files created:**
- backend/app/static/js/proposal_anchor.js
- backend/app/static/js/proposal_annotations.js
- backend/app/static/js/proposal_annotation_ui.js
- [backend test files]
- [migration files — two of them]
- [any others]

**Files modified:**
- [list them]

**New API routes added:**
- POST /api/v1/annotations/{id}/feature
- POST /api/v1/annotations/{id}/unfeature
- POST /api/v1/annotations/{id}/mark-orphaned
- [any additional reply/reaction routes added or modified]

**Anchoring strategies implemented:**
- TextQuoteSelector: [yes / no]
- TextPositionSelector: [yes / no]
- RangeSelector: [yes / no / deferred to Session 4]

**Track Changes schema (Work item 0) — verified:**
- ProposalVersion.status enum created: [yes / no]
- Existing rows backfilled to status='accepted': [count: N]
- authored_by_id and decided_by_id populated from proposal author: [yes / no]
- decided_at set to created_at on existing rows: [yes / no]
- New proposal creation sets defaults correctly: [test passes / fails]
- Place(s) where ProposalVersion is created and the new fields are set:
  [list — e.g., "api/v1/proposals.py:create_proposal line 87",
   "api/v1/amendments.py:accept_amendment line 142"]
- No existing route or test had to change behavior to keep working: [confirmed]

**Annotation schema additions:**
- parent_annotation_id: [added / already existed / other]
- featured_at, featured_by_id: [added]
- orphaned_at: [added]
- replies nested in AnnotationRead: [yes / other shape]
- can_resolve / can_moderate / can_feature computed fields: [yes / other]

**auth.js surface actually used:**
- How currentUser was obtained: [auth.getUserId() / GET /me / other]

**Surprises / deviations from the plan:**
- [anything; "none" is valid]

**Known issues or TODOs left open for Session 4:**
- Moderation modal is a stub (using [prompt() / inline form] — Session 4
  replaces with proper modal)
- Filter UI (All / Open / Resolved / Featured): not built yet
- Sort UI (position / recency / reactions): not built yet
- Polling refresh: not built yet
- Orphan UX beyond the flag: [describe current state]
- Read-only mode visual treatment: [basic / needs polish]
- Keyboard nav: not built yet
- Focus management: not built yet
- Screen-reader announcements: not built yet
- [Other items]

**Verification results:**
- pytest: [N passed, M failed]
- Migration round trip: [success / failure]
- Create annotation (PROPOSING): [works / broken]
- Reply to annotation (threaded): [works / broken]
- React (endorse / needs_work) toggle: [works / broken]
- Resolve as annotation author: [works / broken]
- Resolve as proposal author: [works / broken]
- Resolve as facilitator: [works / broken]
- Resolve as non-permitted user (should 403): [blocked correctly / other]
- Unresolve round-trip: [works / broken]
- Feature as facilitator: [works / broken]
- Unfeature round-trip: [works / broken]
- Moderate with reason: [works / broken]
- Mark orphaned on anchor fail: [works / broken]
- Highlight ↔ card two-way scroll: [works / broken]
- Persistence across reload: [works / broken]
- VOTING phase shows read-only hints: [works / broken]
- No console errors: [confirmed / list them]
- WIKI REGRESSION CHECK: [all wiki behaviors still work / list breaks]

**Notes for Session 4 (annotation polish):**
- [Anything Session 4 needs to know. Specific DOM IDs/classes the UI
  module uses — helpful for building the filter/sort chips without
  re-discovery. Current state of the composer UX. Whether highlights
  use one span or multiple. Where the read-only banner should slot in.
  "None" is a valid answer.]
```
````

### 5. Stop

Do not proceed to Session 4. The user will start Session 4 in a fresh
Claude Code instance with this handoff message as input.
