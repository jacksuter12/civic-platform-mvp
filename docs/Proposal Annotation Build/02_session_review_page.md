# Session 2 — Proposal Review Page shell + TOC + signals + comments

**Paste this entire file into a fresh Claude Code instance.** Along with this
file, the user will paste a "Handoff from Session 1" block containing the
actual file paths and any deviations from the original plan. Read that handoff
first — it's the source of truth for what Session 1 actually built.

**Suggested Claude Code settings for this session:**
- Plan Mode: **ON** (Shift+Tab to toggle)
- Auto-accept Edits: **OFF**
- Thinking effort: **MEDIUM** (pattern-matching to existing templates and JS)

---

## Step 0 — Branch check

Session 1 created and pushed `feature/proposal-review`. Confirm you're on it:

```bash
git branch --show-current    # expect: feature/proposal-review
git pull                     # pull any commits from Session 1
```

If not on the branch, `git checkout feature/proposal-review`. If the branch
doesn't exist, something went wrong in Session 1 — stop and ask the user.

---

## What you're building

The `/c/{slug}/thread/{tid}/proposal/{pid}` page. Three-pane layout on
desktop: TOC (left), rendered proposal doc (center), annotations placeholder
(right). TOC auto-generates from H2/H3 headings with scroll-synced active
highlighting. Proposal-scoped signals work. Proposal comments work. The
thread page's Proposals section becomes a card grid linking to review pages.

Annotations are NOT wired in this session — the right pane shows a
placeholder. Session 3 handles that.

## Context

Session 1 added the backend foundations:
- `body_html` on proposals (cached rendered markdown, with id-tagged H2/H3)
- Resolve/unresolve endpoints (not used this session)
- Permission helpers (not used this session)

This session is purely frontend + one new HTML-serving route.

## Hard constraints (from CLAUDE.md — re-check before starting)

1. No build tooling. Plain HTML/CSS/JS served from FastAPI.
2. `api.js` stays framework-agnostic: only `fetch()` and data parsing. No DOM
   manipulation in `api.js`.
3. No `localStorage` for data state. (JWT stored by existing `auth.js` is
   fine — that's not app state.)
4. Reactions/signals never determine display order. Chronological only.
5. Phase gates enforced server-side; frontend reflects them but does not
   replace them.

## Plan Mode — read these files first

- `handoff_after_1.md` (from Session 1)
- `CLAUDE.md` (root)
- `backend/app/main.py` — current route registration
- `backend/app/templates/thread.html` — where the Proposals section lives now
- `backend/app/templates/wiki_article.html` — good reference for how annotation
  pages are structured (you'll mimic the pattern in Session 3)
- `backend/app/static/css/main.css` — existing design tokens
- `backend/app/static/js/api.js` — existing fetch helpers; you'll add to it
- `backend/app/static/js/nav.js` — how the nav bar is rendered
- `backend/app/static/js/auth.js` — `isSignedIn()`, `getToken()`
- `backend/app/static/js/utils.js` — `timeAgo`, `esc`, etc.
- `backend/app/static/js/thread.js` — where proposals currently render
- The signals API: how current signal-casting works on the thread page
  (look for signal-casting calls in `thread.js` + backend routes in
  `backend/app/api/v1/signals.py`)
- The proposal comments API: look for existing comment routes

## Work items

### 1. Add HTML-serving route

`backend/app/main.py`:

```python
@app.get("/c/{slug}/thread/{thread_id}/proposal/{proposal_id}")
async def proposal_review_page(slug: str, thread_id: str, proposal_id: str):
    return FileResponse("app/templates/proposal_review.html")
```

Match the existing pattern for other community-scoped routes. Register
wherever other page routes are registered.

### 2. Create `backend/app/templates/proposal_review.html`

A single-file HTML shell. All data loading happens in
`proposal_review.js`. Include the site nav the same way other pages do.

Core structure (adapt to match the existing site's header/nav include pattern):

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Proposal review</title>
  <link rel="stylesheet" href="/static/css/main.css">
  <link rel="stylesheet" href="/static/css/proposal_review.css">
</head>
<body>
  <div id="nav-root"></div>
  <main class="pr-page">
    <header class="pr-header">
      <div class="pr-crumb" id="pr-crumb"></div>
      <div class="pr-titlebar">
        <div class="pr-title-block">
          <span class="pr-phase-badge" id="pr-phase"></span>
          <h1 id="pr-title" class="pr-title"></h1>
          <div id="pr-meta" class="pr-meta"></div>
        </div>
        <div class="pr-actions">
          <button id="pr-toc-toggle" class="pr-btn" aria-pressed="true">
            Hide contents
          </button>
          <a id="pr-back" class="pr-btn" href="#">Back to thread</a>
        </div>
      </div>
    </header>

    <div class="pr-body" id="pr-body">
      <aside class="pr-toc" id="pr-toc" aria-label="Proposal contents">
        <div class="pr-toc-label">Contents</div>
        <nav id="pr-toc-nav"></nav>
      </aside>

      <article class="pr-doc" id="pr-doc">
        <div class="pr-doc-loading">Loading proposal…</div>
      </article>

      <aside class="pr-anno" id="pr-anno" aria-label="Annotations">
        <div class="pr-anno-head">
          <div class="pr-anno-title">
            Annotations · <span id="pr-anno-count">—</span>
          </div>
        </div>
        <div id="pr-anno-list" class="pr-anno-list">
          <div class="pr-anno-placeholder">
            Annotation UI loads in a future release.
          </div>
        </div>
      </aside>
    </div>

    <footer class="pr-footer">
      <section class="pr-signal">
        <div class="pr-signal-label">Your signal on this proposal</div>
        <div class="pr-signal-buttons" id="pr-signal-buttons"></div>
        <div class="pr-signal-dist" id="pr-signal-dist"></div>
      </section>
      <section class="pr-comments" id="pr-comments">
        <h2>Proposal comments</h2>
        <div id="pr-comments-list"></div>
        <form id="pr-comments-form" class="pr-comments-form">
          <textarea name="body"
                    placeholder="Add a comment on this proposal"
                    required></textarea>
          <button type="submit">Post comment</button>
        </form>
      </section>
    </footer>
  </main>

  <script src="/static/js/config.js"></script>
  <script src="/static/js/utils.js"></script>
  <script src="/static/js/auth.js"></script>
  <script src="/static/js/api.js"></script>
  <script src="/static/js/nav.js"></script>
  <script src="/static/js/toc.js"></script>
  <script src="/static/js/proposal_review.js"></script>
</body>
</html>
```

### 3. Create `backend/app/static/css/proposal_review.css`

Styles for the page. Must use existing main.css design tokens — match the
civic/library aesthetic already established.

**Layout breakpoints:**

```css
.pr-body {
  display: grid;
  gap: 0;
  grid-template-columns: 200px minmax(0, 1fr) 320px;
}

@media (max-width: 1023px) {
  .pr-body {
    grid-template-columns: minmax(0, 1fr) 280px;
  }
  .pr-toc { /* hidden by default, opened via toggle */
    display: none;
  }
  .pr-toc.is-open { display: block; }
}

@media (max-width: 767px) {
  .pr-body {
    grid-template-columns: minmax(0, 1fr);
  }
  .pr-toc, .pr-anno { display: none; }
  /* drawer + bottom sheet patterns come in Session 4 */
}
```

**Key styles to include:**
- Header: phase badge, title, meta, action buttons
- TOC pane: list of links, active state with left border accent, H3
  entries indented 10px extra and one step smaller
- Doc pane: typography for `.pr-doc h2`, `.pr-doc h3`, `.pr-doc p`,
  `.pr-doc ul`, `.pr-doc ol`, `.pr-doc table`, `.pr-doc blockquote`,
  `.pr-doc code`, `.pr-doc pre`. Generous line-height (~1.65) and readable
  max-width (~72ch) so long-form proposals are easy to read.
- Highlight style for annotated passages: amber underline
  (`text-decoration: underline wavy <color>` or bottom border). This class
  is applied by annotation modules in Session 3; define the style now so
  it's ready.
- Annotation pane: card styling, empty state
- Footer: signal buttons (neutral + selected states), comments list and form
- Loading and error states

### 4. Create `backend/app/static/js/toc.js`

Pure module. No external dependencies. Exposes a global `Toc` object:

```javascript
(function() {
  'use strict';

  let _containerEl = null;
  let _sourceEl = null;
  let _observer = null;
  let _isOpen = true;

  function _buildEntries() {
    const headings = _sourceEl.querySelectorAll('h2, h3');
    _containerEl.innerHTML = '';
    const entries = [];

    headings.forEach((h) => {
      if (!h.id) return;
      const a = document.createElement('a');
      a.href = '#' + h.id;
      a.className = h.tagName === 'H2'
        ? 'pr-toc-item'
        : 'pr-toc-item pr-toc-item--sub';
      a.textContent = h.textContent;
      a.dataset.tocId = h.id;
      a.addEventListener('click', (e) => {
        e.preventDefault();
        h.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
      _containerEl.appendChild(a);
      entries.push({ id: h.id, el: h, link: a });
    });

    return entries;
  }

  function _setupScrollSync(entries) {
    if (_observer) _observer.disconnect();
    _observer = new IntersectionObserver(
      (observed) => {
        observed.forEach((entry) => {
          if (!entry.isIntersecting) return;
          const id = entry.target.id;
          entries.forEach((e) => {
            e.link.classList.toggle('is-active', e.id === id);
          });
        });
      },
      {
        rootMargin: '-80px 0px -70% 0px',
        threshold: 0,
      }
    );
    entries.forEach((e) => _observer.observe(e.el));
  }

  window.Toc = {
    init({ containerEl, sourceEl }) {
      _containerEl = containerEl;
      _sourceEl = sourceEl;
      const entries = _buildEntries();
      if (entries.length > 0) {
        _setupScrollSync(entries);
      } else {
        _containerEl.innerHTML = '<div class="pr-toc-empty">No sections.</div>';
      }
    },
    toggle() {
      const panel = document.getElementById('pr-toc');
      if (!panel) return;
      _isOpen = !_isOpen;
      panel.classList.toggle('is-open', _isOpen);
    },
    get isOpen() { return _isOpen; },
  };
})();
```

The rootMargin value means: "fire when a heading is between 80px from the
top and 70% of the way down the viewport." Tune during verification if the
active-tracking feels laggy.

### 5. Create `backend/app/static/js/proposal_review.js`

Orchestrator. Reads URL, loads data in parallel, assembles UI.

```javascript
(function() {
  'use strict';

  const parts = window.location.pathname.split('/');
  const slug = parts[2];
  const threadId = parts[4];
  const proposalId = parts[6];

  async function load() {
    try {
      const loadPromises = [
        api.fetchProposal(proposalId),
        api.fetchSignalsForTarget('proposal', proposalId),
        api.fetchProposalComments(proposalId),
      ];
      if (auth.isSignedIn()) {
        loadPromises.push(api.fetchMySignalForTarget('proposal', proposalId));
      } else {
        loadPromises.push(Promise.resolve(null));
      }

      const [proposal, signals, comments, mySignal] = await Promise.all(loadPromises);

      renderHeader(proposal);
      renderDoc(proposal);
      initTOC();
      renderSignals(proposal, signals, mySignal);
      renderComments(comments);
      setupCommentForm();
    } catch (err) {
      console.error(err);
      document.getElementById('pr-doc').innerHTML =
        '<div class="pr-doc-error">Could not load proposal.</div>';
    }
  }

  function renderHeader(p) {
    document.getElementById('pr-crumb').textContent =
      `${p.community_slug || slug} › Thread › Proposal`;
    document.getElementById('pr-phase').textContent = capitalize(p.thread_status || '');
    document.getElementById('pr-title').textContent = p.title;
    document.getElementById('pr-meta').textContent =
      `by ${p.author_display_name} · v${p.version || 1} · ${timeAgo(p.created_at)}`;
    document.getElementById('pr-back').href = `/c/${slug}/thread/${threadId}`;
    document.title = `${p.title} · Proposal review`;
  }

  function renderDoc(p) {
    const doc = document.getElementById('pr-doc');
    doc.innerHTML = p.body_html;
  }

  function initTOC() {
    const toggleBtn = document.getElementById('pr-toc-toggle');
    Toc.init({
      containerEl: document.getElementById('pr-toc-nav'),
      sourceEl: document.getElementById('pr-doc'),
    });
    toggleBtn.addEventListener('click', () => {
      Toc.toggle();
      toggleBtn.textContent = Toc.isOpen ? 'Hide contents' : 'Show contents';
      toggleBtn.setAttribute('aria-pressed', String(Toc.isOpen));
    });
  }

  function renderSignals(proposal, signals, mySignal) {
    const container = document.getElementById('pr-signal-buttons');
    const types = ['support', 'concern', 'need_info', 'block'];
    const labels = {
      support: 'Support',
      concern: 'Concern',
      need_info: 'Need info',
      block: 'Block',
    };
    container.innerHTML = '';
    types.forEach(t => {
      const btn = document.createElement('button');
      btn.className = 'pr-signal-btn' +
        (mySignal && mySignal.signal_type === t ? ' is-chosen' : '');
      btn.dataset.signalType = t;
      btn.textContent = labels[t];
      btn.addEventListener('click', () => cast(t));
      if (!auth.isSignedIn()) btn.disabled = true;
      container.appendChild(btn);
    });
    renderDist(signals);
  }

  function renderDist(signals) {
    // Render the distribution bar. Match existing signal bar style from thread.js.
    const dist = document.getElementById('pr-signal-dist');
    // Compute counts + render proportional bar + legend.
    // Replicate existing style from the thread page's signal bar.
    // ...
  }

  async function cast(signalType) {
    try {
      await api.castSignal({
        target_type: 'proposal',
        target_id: proposalId,
        signal_type: signalType,
      });
      // Refresh just the signal UI, not the whole page.
      const [signals, mySignal] = await Promise.all([
        api.fetchSignalsForTarget('proposal', proposalId),
        api.fetchMySignalForTarget('proposal', proposalId),
      ]);
      renderSignals(null, signals, mySignal);
    } catch (err) {
      console.error(err);
      alert('Could not cast signal: ' + err.message);
    }
  }

  function renderComments(comments) { /* ... */ }
  function setupCommentForm() { /* ... */ }

  function capitalize(s) { return s ? s[0].toUpperCase() + s.slice(1) : ''; }

  load();
})();
```

Fill in `renderDist`, `renderComments`, `setupCommentForm` by mirroring the
equivalent logic in existing `thread.js`. Keep the patterns consistent so
styling and behavior feel the same across pages.

### 6. Update `backend/app/static/js/api.js`

Add new functions. Confirm first that similar functions don't already exist
under different names — some may be partially there.

```javascript
api.fetchProposal = async (id) => {
  const r = await fetch(`${API_BASE}/proposals/${id}`, { headers: authHeaders() });
  if (!r.ok) throw new Error(`Failed to load proposal: ${r.status}`);
  return r.json();
};

api.fetchProposalComments = async (id) => {
  const r = await fetch(`${API_BASE}/proposals/${id}/comments`, { headers: authHeaders() });
  if (!r.ok) throw new Error(`Failed to load comments: ${r.status}`);
  return r.json();
};

api.createProposalComment = async (id, body) => {
  const r = await fetch(`${API_BASE}/proposals/${id}/comments`, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ body }),
  });
  if (!r.ok) throw new Error(`Failed to post comment: ${r.status}`);
  return r.json();
};

api.fetchSignalsForTarget = async (target_type, target_id) => { /* ... */ };
api.fetchMySignalForTarget = async (target_type, target_id) => { /* ... */ };
api.castSignal = async ({target_type, target_id, signal_type}) => { /* ... */ };
api.resolveAnnotation = async (id) => { /* ... — used in Session 3 */ };
api.unresolveAnnotation = async (id) => { /* ... — used in Session 3 */ };
```

Match the actual backend route signatures for signals and comments — check
the existing backend files. If signal routes differ from the above
(e.g. `/threads/{id}/signals` instead of `/signals?target_type=...`), adapt.

Confirm `api.js` has **zero DOM references**.

### 7. Update the thread page Proposals section

In `backend/app/templates/thread.html` and/or `backend/app/static/js/thread.js`,
find where proposals currently render inline. Replace inline rendering with
a compact card grid.

Each card shows:
- Title (as link to review page)
- Author name + version badge
- Status badge (submitted / amended / withdrawn / passed / failed)
- Annotation count — use `/api/v1/annotations?target_type=proposal&target_id={pid}&count=true`
  if that's supported, otherwise fetch annotations and count client-side.
  If fetching in a loop is required, that's fine for MVP but add a TODO
  comment about batching.
- Comment count
- Signal mini-distribution (small horizontal bar, same color family as the
  main signal gauge)
- Primary action: "Open review →" linking to
  `/c/{slug}/thread/{threadId}/proposal/{proposalId}`

Grid CSS:
```css
.proposals-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 12px;
}
```

Keep the existing "Submit a proposal" form and PROPOSING-phase gating
untouched. Do NOT rework the thread page tabs — that's Chunk B.

## Definition of done

Before you stop:

1. Navigating to `/c/test/thread/{tid}/proposal/{pid}` in a browser renders
   the three-pane layout with the proposal markdown displayed in the center.

2. TOC auto-populates from H2/H3 headings in the proposal body. Clicking a
   TOC item smooth-scrolls to the heading. Scrolling the doc updates the
   active TOC entry.

3. The "Hide contents" / "Show contents" button toggles the TOC pane.

4. Proposal-scoped signals display current distribution and the signed-in
   user's active choice. Casting a signal updates the UI without full page
   reload.

5. Proposal comments load below the document. Posting a new comment via
   the form adds it to the list.

6. The thread page's Proposals section now renders compact cards; clicking
   a card's "Open review →" link navigates to the review page.

7. At 1000px viewport: two-pane layout (TOC collapsed by default; toggle
   button visible and working).

8. At 600px viewport: single-column (TOC and annotations hidden for now —
   Session 4 adds the drawer/bottom-sheet).

9. No console errors on any of the touched pages. No regressions on
   existing pages.

## When you're done

After all items in "Definition of done" above pass verification:

### 1. Commit and push

```bash
git add -A
git commit -m "Session 2: proposal review page shell + TOC + signals + comments

- Add /c/{slug}/thread/{tid}/proposal/{pid} route and template
- Add proposal_review.js orchestrator + toc.js module
- Add proposal_review.css with responsive breakpoints
- Wire proposal-scoped signals and comments
- Replace inline proposal rendering on thread page with card grid"
git push
```

### 2. Take screenshots

Take screenshots at three viewport widths (1280px, 1000px, 600px) and paste
them into chat so the user can see the visual result.

### 3. Print the handoff message

In your final chat response, print a handoff message in a single fenced code
block so the user can copy it directly into the next Claude Code instance.
Fill in every bracketed field with real values:

````
```
# Handoff from Session 2

**Branch:** feature/proposal-review (commit: [short sha])
**Status:** [Complete | Partial | Failed]

**New files created:**
- [list them]

**Files modified:**
- [list them]

**Actual API route shapes used:**
- GET proposal: [path]
- GET proposal comments: [path]
- POST proposal comment: [path]
- GET signals for target: [path]
- POST cast signal: [path]
- GET my signal: [path]
- GET annotations (count): [path — or "N+1 fallback, no count endpoint"]

**Annotation modules found in the wiki (for Session 3 reference):**
- File names: [e.g., annotations.js, annotation_ui.js, annotation_anchor.js]
- Load order on wiki_article.html: [document what you observed]
- Init signature: [how the modules are currently invoked — copy the exact
  init call from wiki_article.html or whatever JS wires them up]

**What the right pane currently shows:**
- [Should be the placeholder "Annotation UI loads in a future release" —
  confirm or describe what's there]

**Surprises / deviations from the plan:**
- [anything that didn't match the plan; "none" if nothing]

**Known issues or TODOs left open:**
- [e.g., "annotation count on thread page cards uses N+1 fetches — see
  TODO comment in thread.js line ~120; batch endpoint is future work"]

**Verification results:**
- Desktop (1280px) three-pane layout: [works / broken]
- Tablet (1000px) two-pane with TOC toggle: [works / broken]
- Mobile (600px) single-column: [works / broken]
- TOC auto-generation from H2/H3: [works / broken]
- TOC scroll-sync with IntersectionObserver: [works / broken]
- TOC click-to-scroll: [works / broken]
- Hide/Show contents toggle: [works / broken]
- Signal casting (support/concern/need_info/block): [works / broken]
- Signal UI updates without page reload: [works / broken]
- Proposal comments list + posting: [works / broken]
- Thread page proposal cards render: [works / broken]
- Thread page cards link to review page: [works / broken]
- No console errors: [confirmed / list errors]

**Notes for Session 3:**
- [Anything the annotation integration session needs to know. Examples:
  actual paths to annotation modules, how the wiki initializes them,
  any refactors needed to make them reusable, existing styles worth
  reusing. "None" is a valid answer.]
```
````

### 4. Stop

Do not proceed to Session 3. The user will start Session 3 in a fresh Claude
Code instance with this handoff message as input.
