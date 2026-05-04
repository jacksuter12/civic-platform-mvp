# Session 4 — Annotation polish (filters, modal, polling, scroll fix)

**Paste this entire file into a fresh Claude Code instance.** Along with
this file, the user will paste the "Handoff from Session 3" block. Read
that handoff first — it documents the exact DOM IDs, class names, and
known issues this session must address.

**Suggested Claude Code settings for this session:**
- Plan Mode: **ON** (Shift+Tab to toggle)
- Auto-accept Edits: **OFF**
- Thinking effort: **MEDIUM** (mostly UI work on a known foundation; no new
  data layer)

---

## Step 0 — Branch check

```bash
git branch --show-current    # expect: feature/proposal-review
git pull
```

---

## What you're building

Polish the annotation system that Session 3 stood up. The foundation is
solid; this session fixes one bug Session 3 left behind, replaces a stub
that shouldn't ship, and adds the polish that makes the system feel like
a tool people want to use:

1. **Bug fix** — wire the card→highlight scroll direction (Session 3 only
   wired highlight→card)
2. **Proper moderation modal** — replace `window.prompt()` with a real
   modal in the sidebar
3. **Filter chips** — All / Open / Resolved / Featured above the
   annotation list
4. **Sort selector** — Position in document (default), Newest first,
   Oldest first, Most reactions
5. **Polling refresh** — pick up new annotations from other users without
   page reload, with focus/blur pause
6. **Orphan UX upgrade** — show the original anchor text on orphaned cards
   so the annotation isn't reduced to floating commentary
7. **Read-only banner** — explicit visual treatment for VOTING and later
   phases
8. **Focus management** — after creating an annotation or reply, scroll
   to and focus the new card; after closing the composer, return focus
   to the trigger
9. **Empty / loading / error states** — first-load skeleton, no-results
   empty, fetch-failed retry button

**Out of scope for this session** (Session 5 — mobile + a11y):
- Keyboard navigation across cards (J/K/N/R/Esc)
- Screen-reader aria-live announcements
- Touch text selection on mobile
- TOC drawer and annotations bottom sheet for mobile

## Hard constraints (re-verify before starting)

1. Reactions never determine display order. Even when "Most reactions"
   sort is selected, that's an explicit user choice — the default sort
   stays "position in document," and the sort selector defaults back to
   that on every page load. Sort preference is NOT persisted to
   localStorage.
2. Filter chips are user view state only. They never gate visibility for
   other users. The backend keeps returning all annotations.
3. Audit log unchanged this session — no new event types.
4. `api.js` stays framework-agnostic.
5. Wiki annotation modules stay untouched.

## Plan Mode — read these files first

- `backend/app/static/js/proposal_anchor.js` — has `scrollTo(annotationId)`
  per the handoff; confirm signature
- `backend/app/static/js/proposal_annotations.js` — orchestrator; where
  polling will hook in
- `backend/app/static/js/proposal_annotation_ui.js` — render layer; this
  is where most changes land
- `backend/app/static/css/proposal_review.css` — existing annotation styles
- `backend/app/templates/proposal_review.html` — DOM structure of the
  sidebar
- `backend/app/static/js/proposal_review.js` — orchestration entry point

After reading, your plan must explicitly address:

1. Where in `proposal_annotation_ui.js` is the card click handler (or is
   there one yet)? Card→highlight scroll wires there.
2. What's the current empty-state message rendered when there are zero
   annotations? Where is it set?
3. Does `proposal_anchor.js` retain the original `exact` text from the
   anchor JSON when an annotation orphans? (It must — that text is what
   we'll show on orphaned cards in Work item 6.)
4. Is there any existing modal / dialog pattern in the codebase to match
   styling? Check `main.css` and other templates for reference.

## Work items

### 1. Wire card→highlight scroll (bug fix from Session 3)

The handoff documents this explicitly: clicking a card does NOT scroll
the doc to the highlight; only the reverse direction works.

In `proposal_annotation_ui.js`, find the event delegation listener on
`sidebarEl`. Add a handler for clicks on the card body that aren't on
buttons or inside the reply form:

```javascript
// Inside the sidebarEl click delegation handler:
const card = e.target.closest('.proposal-annotation-card');
if (!card) return;
// Skip if click was on an action button, the menu, or a form element
if (e.target.closest('button, form, .paa-menu-dropdown, a')) return;
const annoId = card.dataset.annoId;
const orphaned = card.dataset.orphaned === 'true';
if (orphaned) return;  // No anchor to scroll to
window.ProposalAnchor.scrollTo(annoId);
```

The order of click checks matters — check for buttons/forms FIRST so a
click on a "Reply" button doesn't also trigger a scroll.

Add a flash animation on the highlight when it's scrolled to (mirror of
the `.paa-card-flash` pattern Session 3 already established for the
opposite direction). Add a `.proposal-annotation-highlight-flash` class
in CSS — a 600ms outline-pulse identical in feel to the card flash.

`proposal_anchor.js` `scrollTo` adds the flash class to all spans with
the matching `data-anno-id`, then removes after 600ms via setTimeout.

### 2. Proper moderation modal

Replace the `window.prompt()` stub. The new modal lives inside the
sidebar so it doesn't fight with the rest of the page.

**DOM structure** — added by `proposal_annotation_ui.js` on first use,
not pre-rendered:

```html
<div class="paa-modal-backdrop" role="dialog" aria-modal="true"
     aria-labelledby="paa-modal-title">
  <div class="paa-modal">
    <header class="paa-modal-head">
      <h3 id="paa-modal-title">Hide annotation</h3>
      <button class="paa-modal-close" aria-label="Cancel">×</button>
    </header>
    <div class="paa-modal-body">
      <p class="paa-modal-context">
        From <strong>{author}</strong>:
        <span class="paa-modal-quote">{annotation body, truncated to ~120 chars}</span>
      </p>
      <label class="paa-modal-label" for="paa-modal-reason">
        Reason for hiding (required, visible in audit log)
      </label>
      <textarea id="paa-modal-reason" minlength="10" maxlength="500"
                placeholder="Why is this annotation being hidden?"
                required></textarea>
      <p class="paa-modal-counter" aria-live="polite">10–500 characters</p>
    </div>
    <footer class="paa-modal-foot">
      <button class="paa-btn-ghost paa-modal-cancel">Cancel</button>
      <button class="paa-btn-danger paa-modal-submit" disabled>Hide annotation</button>
    </footer>
  </div>
</div>
```

**Behavior:**
- Backdrop click closes the modal (via class on event target)
- Escape key closes the modal
- Submit button enabled only when textarea length ≥ 10
- Counter updates on input ("47 / 500", red color when invalid)
- On submit: call `ProposalAnnotations.moderate(annoId, reason)`, await
  it, close modal on success, leave modal open with error message on
  failure
- On open: the textarea receives focus; on close, focus returns to the
  ⋯ menu button on the moderated card (or the sidebar header if the
  card has been removed)

**Focus trap** — basic version: when the modal is open, listen for
keydown of Tab; if `document.activeElement` is the last focusable
element and Tab (not Shift+Tab) is pressed, redirect to the first
focusable; symmetric for the inverse case. ~15 lines of code; no
external library.

**CSS** — modal centered, max-width 480px, scrollable body if textarea
exceeds the available space. Backdrop is rgba(0,0,0,0.4). Match site
aesthetic (muted, library, not flashy).

**Public API on `ProposalAnnotationUI`:** add
`showModerateModal(annotation)` and `hideModerateModal()`. The ⋯ menu's
"Hide…" item calls `showModerateModal(annotation)` instead of
`window.prompt`.

### 3. Filter chips

Above `#pr-anno-list`, add a row of chips. Render them in
`proposal_annotation_ui.js` as part of the sidebar setup (call from
`init`), so they appear on every page load with a default of "All
selected."

```html
<div class="paa-filters" role="tablist" aria-label="Filter annotations">
  <button class="paa-chip is-on" data-filter="all" role="tab" aria-selected="true">
    All <span class="paa-chip-count">12</span>
  </button>
  <button class="paa-chip" data-filter="open" role="tab" aria-selected="false">
    Open <span class="paa-chip-count">9</span>
  </button>
  <button class="paa-chip" data-filter="resolved" role="tab" aria-selected="false">
    Resolved <span class="paa-chip-count">3</span>
  </button>
  <button class="paa-chip" data-filter="featured" role="tab" aria-selected="false">
    Featured <span class="paa-chip-count">1</span>
  </button>
</div>
```

**Filter behavior** — pure CSS-driven via `data-filter` attribute on
the list:

```css
.paa-list[data-filter="open"] .proposal-annotation-card[data-status="resolved"] { display: none; }
.paa-list[data-filter="resolved"] .proposal-annotation-card[data-status="open"] { display: none; }
.paa-list[data-filter="featured"] .proposal-annotation-card[data-featured="false"] { display: none; }
```

**Counts** — computed at render time from the loaded annotations array:
```javascript
const counts = {
  all: annotations.length,
  open: annotations.filter(a => !a.resolved_at).length,
  resolved: annotations.filter(a => a.resolved_at).length,
  featured: annotations.filter(a => a.featured_at).length,
};
```

Chip click toggles the active chip and updates `data-filter` on the list.
No persistence; resets to "all" on every page load.

**Empty state inside a filter** — when a filter eliminates all visible
cards, show a small inline "No {filter} annotations" message. Use a
sibling div that's CSS-shown only when the list has zero un-hidden cards.
Simplest implementation: count visible cards in JS after filter change;
toggle the message div.

**Reactions are NOT a filter axis.** This is intentional — reactions are
editorial feedback, not a category. Don't add a "Has endorsements" chip
or similar.

### 4. Sort selector

Next to the filter chips (or at the right edge of the same row, with
flex space-between), add a sort `<select>`:

```html
<select class="paa-sort" aria-label="Sort annotations">
  <option value="position" selected>By position in document</option>
  <option value="newest">Newest first</option>
  <option value="oldest">Oldest first</option>
  <option value="reactions">Most reactions</option>
</select>
```

**Sort behavior:**

- `position` (default) — sort by where the annotation's anchor appears
  in the document. Featured annotations break this rule and surface to
  the top, in their own position-order among themselves. Use the y-coord
  of the first highlight span in the doc:
  ```javascript
  function annotationY(a) {
    const el = document.querySelector(
      `.proposal-annotation-highlight[data-anno-id="${a.id}"]`
    );
    return el ? el.getBoundingClientRect().top + window.scrollY : Infinity;
  }
  ```
  Orphaned annotations sort to the bottom of their group.

- `newest` — sort by `created_at` descending. Featured still surface
  first.

- `oldest` — sort by `created_at` ascending. Featured still surface
  first.

- `reactions` — sort by total reaction count descending
  (`endorse + needs_work`). Featured first. Ties broken by `created_at`
  descending. **Add a small caveat tooltip on the option label**:
  "Reactions never determine default visibility" — small text, on hover
  of an info icon adjacent to the selector.

Sort is applied at render time. Re-sort + re-render on selector change.
**Not persisted** — every page load defaults back to `position`.

**Implementation note:** keep the DOM order of cards consistent with
the sort. Don't use CSS `order` for sorting; use real DOM reordering
(`appendChild` to move cards). This makes screen reader and keyboard
nav (Session 5) match what's visible.

### 5. Polling refresh

Pick up new annotations from other users without requiring a page
reload.

**Approach:** simple polling with focus/blur pause. WebSockets / SSE are
overkill for this and add infrastructure cost.

**In `proposal_annotations.js`:**

```javascript
// State
this._pollIntervalMs = 30000;        // 30 seconds when focused
this._pollIntervalMsBlurred = 300000; // 5 minutes when not focused
this._pollTimer = null;
this._lastPollAt = null;

start_polling() {
  this._scheduleNextPoll();
  document.addEventListener('visibilitychange', () => this._scheduleNextPoll());
  window.addEventListener('focus', () => this._scheduleNextPoll());
  window.addEventListener('blur', () => this._scheduleNextPoll());
}

_scheduleNextPoll() {
  clearTimeout(this._pollTimer);
  const interval = document.hidden ? this._pollIntervalMsBlurred : this._pollIntervalMs;
  this._pollTimer = setTimeout(() => this._poll(), interval);
}

async _poll() {
  if (this._inFlight) return this._scheduleNextPoll();
  this._inFlight = true;
  try {
    const fresh = await api.fetchAnnotations('proposal', this._config.proposalId);
    this._mergeUpdates(fresh);
  } catch (err) {
    // Silent failure — log but don't disrupt the user
    console.warn('Annotation poll failed', err);
  } finally {
    this._inFlight = false;
    this._scheduleNextPoll();
  }
}

_mergeUpdates(fresh) {
  // Compare counts and update timestamps. If anything changed:
  //   - Re-render the sidebar
  //   - Re-apply highlights for new annotations
  //   - Remove highlights for moderated annotations
  //   - Update existing card states (resolved/featured/orphaned)
  // Preserve the user's current scroll position and any open composer/reply form state.
}
```

**Preserve transient UI state during merge:**
- If the user has a composer open, do NOT close it
- If the user has a reply form open on a card, do NOT close it
- If the user is mid-typing in any textarea, do NOT clear it
- Card scroll position is preserved by re-rendering in place rather than
  emptying and rebuilding

The simplest implementation that respects this: render in place by
diffing the current DOM against the new annotation array — for each new
annotation, append a card; for each removed annotation, remove the card;
for each updated annotation, update the card's data attributes and
content. Don't blow away the entire list every poll.

**Show a subtle "X new annotations" toast** when the poll discovers new
annotations from other users (not your own). Top-right of the sidebar,
auto-dismisses after 5 seconds, click-to-dismiss. Don't notify on your
own annotations (compare actor against `currentUser.id`).

Stop polling when the page is unloaded; clear the timer on
`beforeunload` or the orchestrator's teardown if there is one.

### 6. Orphan UX upgrade

Right now an orphaned annotation gets a grey "Anchor changed" badge but
the card body is just the user's annotation text floating in space. The
reader has no idea what the annotation was originally about.

**Add to the orphaned card** — show the original anchor's `exact` text
(stored in the annotation's `anchor_data` JSON) as a quoted block right
above the annotation body:

```html
<article class="proposal-annotation-card" data-orphaned="true" ...>
  <header>... + .paa-orphaned-tag ...</header>
  <blockquote class="paa-orphan-original-text">
    Originally annotated: "{anchor_data.exact}"
  </blockquote>
  <div class="paa-body">{body}</div>
  ...
</article>
```

Style the quote in a muted color with an italic font and a striped left
border (different from `.paa-anchor-quote` so it reads as historical
context, not a live anchor).

This makes orphaned annotations useful as historical record even after
their anchor breaks. The user can read both the original passage and
the commentary and decide what to do with it.

**Optional follow-up (defer if short on time):** add an "Archive
annotation" button visible only to the annotation author and
facilitators — flips a different field (`archived_at`) to fully hide
the orphan. This is small but adds a backend field; **defer to a
later chunk** unless the plan phase determines it's trivial.

### 7. Read-only banner

For threads in VOTING / CLOSED / ARCHIVED phases, replace the current
empty-state message hint with an explicit banner inside `.pr-anno`,
above the filter chips:

```html
<div class="paa-readonly-banner" role="status">
  <strong>Annotations are read-only.</strong> This thread is in {phase}.
  New annotations and edits can be made when a thread is in PROPOSING.
</div>
```

Style: warm muted yellow background, dark text, small icon. Same family
as the existing phase badge.

When the banner is shown:
- Filter chips remain functional (read-only doesn't mean can't filter)
- Sort selector remains functional
- The "+ Add" button (if present from the chip area) is hidden, not
  disabled — disabled buttons in a read-only context add no signal
- Existing cards still allow expanding replies (read-only means no
  *creating*, not no *reading*)

**Phase mapping:**
- PROPOSING → no banner; full edit mode
- DELIBERATING → banner: "Annotations open during PROPOSING phase only"
- VOTING → banner: "Annotations are read-only during voting"
- CLOSED / ARCHIVED → banner: "This thread is closed; annotations are
  read-only"

The text for each phase is a small lookup map in `proposal_annotation_ui.js`.

### 8. Focus management

After certain interactions, programmatically move focus:

- **After submitting a new annotation:** focus moves to the newly
  created card (use card's `tabindex="0"` and call `.focus()` on the
  article element after the re-render).
- **After submitting a reply:** focus moves to the new reply card.
- **After closing the composer (cancel or submit):** focus returns to
  where the composer was opened from — either the `.paa-annotate-chip`
  element (if it still exists; it usually doesn't after submit), or the
  sidebar's filter chip row as a fallback.
- **After closing the moderation modal:** focus returns to the ⋯ menu
  button on the relevant card (handled in Work item 2).
- **After the cancel/dismiss of a reply form:** focus returns to the
  Reply button that opened it.

Add `tabindex="0"` to `article.proposal-annotation-card` so cards are
focusable. CSS for `:focus-visible` on the card: a 2px outline accent
matching the highlight color, NOT browser-default blue.

This is foundational for keyboard navigation in Session 5; build it now
so Session 5's J/K nav has something to focus.

### 9. Empty / loading / error states

**Loading state** — when the page first loads and annotations haven't
arrived yet, show a minimal skeleton in `#pr-anno-list`:

```html
<div class="paa-skeleton">
  <div class="paa-skeleton-card"></div>
  <div class="paa-skeleton-card"></div>
</div>
```

CSS: 60px-tall grey blocks with subtle shimmer animation. Just two
cards; don't try to mimic the real card density.

**Empty state — no annotations at all on the proposal:**

```html
<div class="paa-empty-state">
  <p class="paa-empty-message">
    {if currentUser && phase === 'PROPOSING'}
      No annotations yet. Select text in the proposal to add one.
    {else if currentUser}
      No annotations on this proposal.
    {else}
      No annotations yet. Sign in to add one during PROPOSING.
  </p>
</div>
```

**Empty state — filter eliminated all visible cards (handled in
Work item 3):** "No {filter} annotations." — small, italic.

**Error state — initial fetch failed:**

```html
<div class="paa-error-state">
  <p class="paa-error-message">Could not load annotations.</p>
  <button class="paa-error-retry">Retry</button>
</div>
```

Retry button calls `ProposalAnnotations.reload()`.

The `_load()` function in `proposal_annotations.js` becomes:

```javascript
async _load() {
  this._renderLoading();
  try {
    const annotations = await api.fetchAnnotations(...);
    this._annotations = annotations;
    this._render();
  } catch (err) {
    this._renderError(err);
  }
}
```

## Definition of done

1. **Card click scrolls doc to the highlight** (Session 3 bug fix).
   Confirm by clicking 5 different cards and watching the doc scroll.
   The clicked highlight gets a flash animation. Clicking on action
   buttons does NOT trigger a scroll.

2. **Moderation modal**:
   - ⋯ menu → "Hide…" opens the modal (no `window.prompt` anywhere)
   - Modal traps focus; Escape closes it; backdrop click closes it
   - Submit disabled until reason length ≥ 10
   - Counter updates on input and shows red on invalid length
   - Submit succeeds → modal closes, annotation removed from sidebar
   - Submit fails (e.g., 403) → error visible in modal, modal stays open
   - Focus returns to the ⋯ menu button on close

3. **Filter chips** — All / Open / Resolved / Featured. Counts accurate.
   Click changes which cards are visible. No reaction-based filter.
   Empty-state message appears when filter eliminates all cards.

4. **Sort selector** — four options, default "position." Sort updates
   DOM order (cards physically reordered), not just visual. Featured
   annotations always first within the sort. Default resets to
   "position" on every page load.

5. **Polling**:
   - New annotations from other users appear within 30 seconds without
     reload (test by creating an annotation in a second browser tab/user)
   - Toast appears: "X new annotations"
   - Open composer / reply form / typing-in-progress NOT disrupted
     during merge
   - Polling pauses when page is hidden (verify by switching tabs and
     watching network in devtools)
   - Polling stops on `beforeunload` (verify no requests after navigation)

6. **Orphan UX**: orphaned cards show the original anchor text in a
   muted quoted block above the annotation body.

7. **Read-only banner**: visible in DELIBERATING / VOTING / CLOSED /
   ARCHIVED phases; not visible in PROPOSING. Text differs per phase.
   Filter chips and sort still work in read-only.

8. **Focus management**: after creating an annotation, focus moves to
   the new card. After closing the moderation modal, focus returns to
   the ⋯ button. Cards have visible focus rings (custom, not browser
   default blue).

9. **Empty / loading / error states**: visible at the right times.
   Initial load shows a skeleton. Empty state changes copy based on
   sign-in state and phase. Error state has a retry button that
   actually retries.

10. `pytest -v` still passes (no test changes expected — this session is
    almost entirely frontend).

11. **No console errors** on page load, after annotation creation, after
    moderation, after polling cycles.

12. **Wiki regression check** — wiki annotations still work. Sanity
    check.

## When you're done

### 1. Commit and push

```bash
git add -A
git commit -m "Session 4: annotation polish

- Wire card→highlight scroll (bug fix from Session 3)
- Replace window.prompt() moderation stub with proper modal + focus trap
- Add filter chips (All / Open / Resolved / Featured)
- Add sort selector (position / newest / oldest / reactions)
- Add polling refresh with focus/blur pause and merge-without-disrupt
- Show original anchor text on orphaned annotation cards
- Add explicit read-only banner for non-PROPOSING phases
- Add focus management for create/reply/cancel and modal close
- Add loading skeleton, empty states, and error retry"
git push
```

### 2. Take screenshots

- Filter chips with each state selected
- Sort selector with the dropdown open
- Moderation modal open
- Orphaned annotation card showing original anchor text
- Read-only banner in VOTING phase
- "X new annotations" toast (capture mid-poll)
- Loading skeleton (devtools throttle to slow 3G or use a network breakpoint)

### 3. Print the handoff message

````
```
# Handoff from Session 4

**Branch:** feature/proposal-review (commit: [short sha])
**Status:** [Complete | Partial | Failed]

**Files modified:**
- [list — expect proposal_annotation_ui.js, proposal_annotations.js,
  proposal_anchor.js, proposal_review.css, proposal_review.html]

**New CSS classes added (for Session 5 reference):**
- [.paa-modal-backdrop / .paa-modal / .paa-modal-* family]
- [.paa-filters / .paa-chip / .paa-chip-count]
- [.paa-sort]
- [.paa-readonly-banner]
- [.paa-toast]
- [.paa-skeleton]
- [.paa-empty-state / .paa-error-state]
- [.paa-orphan-original-text]
- [.proposal-annotation-highlight-flash]
- [any others]

**Polling implementation:**
- Interval (focused): [30s as specified / other]
- Interval (blurred): [5min / other]
- Pauses on document.hidden: [yes / no]
- Merge strategy: [in-place diff / full re-render / other]
- Toast for new annotations: [implemented / deferred]

**Modal implementation:**
- Focus trap: [yes / no]
- Escape closes: [yes / no]
- Backdrop click closes: [yes / no]
- Reason length validation: [client-side at >=10 / matches server
  / both]
- Focus return on close: [to ⋯ button / sidebar header fallback / other]

**Filter and sort:**
- Filter is CSS-driven via data-filter: [yes / other approach]
- Sort reorders DOM nodes: [yes / uses CSS order / other]
- Both reset on page load: [confirmed]
- Reaction sort caveat tooltip: [implemented / deferred]

**Bug fix verification:**
- Card→highlight scroll: [works / broken]
- Click on action button does NOT scroll: [confirmed / regression]
- Highlight flash on scroll-to: [works / deferred]

**Read-only banner:**
- Shown in DELIBERATING: [yes / no — per spec]
- Shown in VOTING: [yes / per spec]
- Shown in CLOSED/ARCHIVED: [yes / per spec]
- Hidden in PROPOSING: [yes / per spec]
- Phase-specific text: [4 distinct messages / fewer / other]

**Focus management:**
- New annotation → focus on new card: [works / broken]
- Cancel composer → focus to trigger: [works / broken]
- Modal close → focus to ⋯ button: [works / broken]
- Custom focus ring on cards: [implemented]

**Surprises / deviations from the plan:**
- [anything; "none" valid]

**Known issues or TODOs left open for Session 5:**
- Keyboard nav (J/K/N/R/Esc): not built
- Aria-live announcements: not built
- TOC drawer for mobile: not built
- Annotations bottom sheet for mobile: not built
- Touch text selection on mobile: not tested / not built
- Mobile composer UX: not designed yet
- [Other items]

**Verification results:**
- pytest: [N passed]
- Card→highlight scroll: [works]
- Moderation modal: [works]
- Filter chips: [works]
- Sort options: [works for all 4]
- Polling picks up second-tab annotations: [works in N seconds]
- Polling does not disrupt open composer: [confirmed]
- Polling pauses on tab hidden: [confirmed]
- Orphan card shows original text: [works]
- Read-only banner: [correct in all 4 phases]
- Focus management: [works]
- Loading skeleton: [appears on slow connection]
- Error retry: [works on simulated 500]
- No console errors: [confirmed / list]
- WIKI REGRESSION CHECK: [unchanged]

**Notes for Session 5 (mobile + a11y):**
- [DOM IDs / classes Session 5 will need: filter row, sort selector,
  modal, banner, toast — all listed above]
- [Current mobile breakpoints in CSS: ...]
- [Known mobile problems already visible: ...]
- [Whether anything in the polling logic is mobile-hostile]
```
````

### 4. Stop

Do not proceed to Session 5. The user will start Session 5 in a fresh
Claude Code instance with this handoff message as input.
