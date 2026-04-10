/**
 * annotation_ui.js — DOM-layer for the annotation system.
 *
 * Builds the toggle button, side drawer, annotation cards, highlight
 * marks, floating "Add comment" button, composers, reactions, edit
 * and delete flows.
 *
 * Requires (in load order):
 *   1. api.js            — fetch helpers (defines getMe, addReaction, etc.)
 *   2. annotations.js    — defines window.Annotations
 *   3. annotation_anchor.js (module) — defines window.AnnotationAnchor
 *
 * This is the only file in the annotation system that touches the DOM.
 * api.js and annotations.js must remain DOM-free.
 *
 * Exposes: window.AnnotationUI
 */
(function () {
  "use strict";

  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------

  let _user = null;        // full user object from /auth/me
  let _isAnnotator = false;
  let _isAdmin = false;
  let _drawerOpen = false;

  // Map<annotationId, Range|null> — populated by resolveAnchorsToRanges()
  let _anchorRanges = new Map();

  // DOM elements we created so we can clean them up
  let _highlights = [];    // <mark> and section marker <span> elements
  let _sectionBtns = [];   // "Add comment to this section" <button> elements

  // Refs to drawer parts
  let _toggleBtn = null;
  let _drawer = null;
  let _drawerBody = null;
  let _drawerComposerWrap = null;

  // Floating button tracking
  let _floatingBtn = null;

  // ---------------------------------------------------------------------------
  // Entry point
  // ---------------------------------------------------------------------------

  async function init() {
    // Annotation UI only visible to authenticated users
    if (!auth.isSignedIn()) return;

    // Fetch fresh user data so is_annotator is current (not stale cache)
    try {
      _user = await getMe();
      auth.setUser(_user);
    } catch (_) {
      _user = auth.getUser();
    }
    if (!_user) return;

    // isAnnotator: the is_annotator flag OR admin tier (matches server logic)
    _isAnnotator = !!(_user.is_annotator || _user.tier === "admin");
    _isAdmin = _user.tier === "admin";

    // Only activate on pages with an annotatable root
    if (!_getAnnotatableRoot()) return;

    buildToggleButton();
    buildDrawer();

    // Restore drawer state from sessionStorage
    const saved = sessionStorage.getItem("annotation-drawer-open");
    if (saved === "true") {
      await _openDrawer();
    } else {
      // Still update the toggle count from the already-fetched cache
      _updateToggleCount();
    }

    // Selection listener (annotators only)
    if (_isAnnotator) {
      document.addEventListener("mouseup", _onMouseUp);
    }

    document.addEventListener("keydown", _onKeyDown);
  }

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  function _getAnnotatableRoot() {
    if (typeof AnnotationAnchor === "undefined") return null;
    return AnnotationAnchor.getAnnotatableRoot();
  }

  /**
   * Return a user-friendly error string for an API error.
   * Token-expiry errors get a "please sign in" message instead of the
   * raw JWT error text.
   */
  function _errorMessage(e) {
    const raw = (e && e.message) || "";
    const isExpired =
      raw.toLowerCase().includes("expired") ||
      raw.toLowerCase().includes("invalid token") ||
      !auth.isSignedIn();
    if (isExpired) {
      return "Your session has expired \u2014 please sign in again to leave comments.";
    }
    return raw || "Something went wrong. Please try again.";
  }

  /** Format a UTC datetime string as a relative time label. */
  function _timeAgo(dateStr) {
    if (!dateStr) return "";
    const date = new Date(dateStr);
    const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
    if (seconds < 60) return "just now";
    if (seconds < 3600) return Math.floor(seconds / 60) + "m ago";
    if (seconds < 86400) return Math.floor(seconds / 3600) + "h ago";
    if (seconds < 86400 * 7) return Math.floor(seconds / 86400) + "d ago";
    return date.toLocaleDateString();
  }

  // ---------------------------------------------------------------------------
  // Toggle button
  // ---------------------------------------------------------------------------

  function buildToggleButton() {
    _toggleBtn = document.createElement("button");
    _toggleBtn.className = "annotation-toggle-btn";
    _toggleBtn.setAttribute("aria-label", "Toggle annotation comments");
    _toggleBtn.addEventListener("click", _toggleDrawer);
    document.body.appendChild(_toggleBtn);
    _updateToggleCount();
  }

  function _updateToggleCount() {
    if (!_toggleBtn) return;
    const all = Annotations.getAll();
    const count = all.filter((a) => !a.deleted_at && !a.parent_id).length;
    _toggleBtn.textContent = `Comments (${count})`;
    // Hide the toggle while the drawer is open — the × in the drawer header
    // handles closing, so there's no need for a redundant button in the corner.
    _toggleBtn.style.display = _drawerOpen ? "none" : "";
  }

  // ---------------------------------------------------------------------------
  // Drawer shell
  // ---------------------------------------------------------------------------

  function buildDrawer() {
    _drawer = document.createElement("div");
    _drawer.className = "annotation-drawer";
    _drawer.setAttribute("aria-label", "Comments");
    _drawer.setAttribute("role", "complementary");

    // Header
    const header = document.createElement("div");
    header.className = "annotation-drawer-header";

    const titleEl = document.createElement("span");
    titleEl.className = "annotation-drawer-title";
    titleEl.textContent = "Comments";

    const closeBtn = document.createElement("button");
    closeBtn.className = "annotation-drawer-close";
    closeBtn.textContent = "×";
    closeBtn.setAttribute("aria-label", "Close comments");
    closeBtn.addEventListener("click", _closeDrawer);

    header.appendChild(titleEl);
    header.appendChild(closeBtn);
    _drawer.appendChild(header);

    // Scrollable body
    _drawerBody = document.createElement("div");
    _drawerBody.className = "annotation-drawer-body";
    _drawer.appendChild(_drawerBody);

    // Composer area (at the bottom of the drawer, for new top-level annotations)
    _drawerComposerWrap = document.createElement("div");
    _drawerComposerWrap.className = "annotation-composer-wrap";
    _drawerComposerWrap.style.display = "none";
    _drawer.appendChild(_drawerComposerWrap);

    document.body.appendChild(_drawer);
  }

  // ---------------------------------------------------------------------------
  // Drawer open / close
  // ---------------------------------------------------------------------------

  async function _openDrawer() {
    _drawerOpen = true;
    _drawer.classList.add("is-open");
    document.body.classList.add("annotation-drawer-open");
    sessionStorage.setItem("annotation-drawer-open", "true");
    _updateToggleCount();
    await _renderDrawer();
    _applyHighlights();
    _addSectionButtons();
  }

  function _closeDrawer() {
    _drawerOpen = false;
    _drawer.classList.remove("is-open");
    document.body.classList.remove("annotation-drawer-open");
    sessionStorage.setItem("annotation-drawer-open", "false");
    _updateToggleCount();
    _removeHighlights();
    _removeSectionButtons();
    _hideFloatingButton();
    _closeComposer();
  }

  async function _toggleDrawer() {
    if (_drawerOpen) {
      _closeDrawer();
    } else {
      await _openDrawer();
    }
  }

  // ---------------------------------------------------------------------------
  // Render the drawer body
  // ---------------------------------------------------------------------------

  async function _renderDrawer() {
    _drawerBody.innerHTML =
      '<div class="annotation-loading">Loading…</div>';

    try {
      await Annotations.fetchForCurrentPage();
      _anchorRanges = await Annotations.resolveAnchorsToRanges();
    } catch (e) {
      _drawerBody.innerHTML =
        '<div class="annotation-loading">Failed to load comments.</div>';
      return;
    }

    const all = Annotations.getAll();
    const topLevel = all.filter((a) => !a.parent_id);
    const replies = all.filter((a) => !!a.parent_id);

    // Orphaned = top-level annotation whose anchor doesn't resolve
    const orphaned = topLevel.filter((a) => {
      if (a.anchor_data && a.anchor_data.type === "section") {
        // Section annotations are orphaned only if the element ID is gone
        const el = document.getElementById(a.anchor_data.section_id);
        return !el;
      }
      return _anchorRanges.get(a.id) === null;
    });
    const anchored = topLevel.filter((a) => !orphaned.includes(a));

    _drawerBody.innerHTML = "";

    if (orphaned.length > 0) {
      _drawerBody.appendChild(_renderOrphanedSection(orphaned, replies));
    }

    if (anchored.length === 0) {
      const empty = document.createElement("div");
      empty.className = "annotation-empty";
      empty.textContent = _isAnnotator
        ? 'No comments yet. Select text in the article and click "Add comment" to be the first.'
        : "No comments yet.";
      _drawerBody.appendChild(empty);
    } else {
      _drawerBody.appendChild(_renderAnnotationList(anchored, replies));
    }

    _updateToggleCount();
  }

  // ---------------------------------------------------------------------------
  // Orphaned section
  // ---------------------------------------------------------------------------

  function _renderOrphanedSection(orphaned, replies) {
    const section = document.createElement("div");
    section.className = "annotation-orphaned-section";

    const header = document.createElement("button");
    header.className = "annotation-orphaned-header";
    header.textContent = `Orphaned comments (${orphaned.length}) — the text these were attached to has been edited`;
    header.setAttribute("aria-expanded", "false");

    const body = document.createElement("div");
    body.className = "annotation-orphaned-body";
    body.style.display = "none";

    orphaned.forEach((annotation) => {
      const myReplies = replies.filter(
        (r) => r.parent_id === annotation.id
      );
      body.appendChild(_renderCard(annotation, myReplies, true));
    });

    header.addEventListener("click", () => {
      const expanded = header.getAttribute("aria-expanded") === "true";
      header.setAttribute("aria-expanded", String(!expanded));
      body.style.display = expanded ? "none" : "block";
    });

    section.appendChild(header);
    section.appendChild(body);
    return section;
  }

  // ---------------------------------------------------------------------------
  // Main annotation list
  // ---------------------------------------------------------------------------

  function _renderAnnotationList(topLevel, replies) {
    const list = document.createElement("div");
    list.className = "annotation-list";

    const sorted = _sortByDocPosition(topLevel);
    sorted.forEach((annotation) => {
      const myReplies = replies.filter(
        (r) => r.parent_id === annotation.id
      );
      list.appendChild(_renderCard(annotation, myReplies, false));
    });

    return list;
  }

  /** Sort top-level annotations by their position in the document. */
  function _sortByDocPosition(annotations) {
    return [...annotations].sort((a, b) => {
      const ra = _anchorRanges.get(a.id);
      const rb = _anchorRanges.get(b.id);
      if (ra && rb) {
        try {
          const cmp = ra.compareBoundaryPoints(Range.START_TO_START, rb);
          if (cmp !== 0) return cmp;
        } catch (_) {}
      }
      // Fallback: section anchors — use heading's offsetTop
      if (a.anchor_data && a.anchor_data.type === "section") {
        const elA = document.getElementById(a.anchor_data.section_id);
        const elB = b.anchor_data && document.getElementById(b.anchor_data.section_id);
        if (elA && elB) return elA.offsetTop - elB.offsetTop;
      }
      return new Date(a.created_at) - new Date(b.created_at);
    });
  }

  // ---------------------------------------------------------------------------
  // Annotation card
  // ---------------------------------------------------------------------------

  function _renderCard(annotation, replies, isOrphaned) {
    const isDeleted = !!annotation.deleted_at;
    const isOwn = _user && annotation.author.id === _user.id;

    const card = document.createElement("div");
    card.className = "annotation-card";
    card.dataset.annotationId = annotation.id;
    if (isDeleted) card.classList.add("is-deleted");
    if (isOrphaned) card.classList.add("is-orphaned");

    // Anchor preview
    card.appendChild(_renderAnchorPreview(annotation.anchor_data, isOrphaned));

    // Meta row
    const meta = document.createElement("div");
    meta.className = "annotation-card-meta";

    const authorEl = document.createElement("span");
    authorEl.className = "annotation-author";
    authorEl.textContent = annotation.author.display_name;
    if (isOwn) {
      const badge = document.createElement("span");
      badge.className = "annotation-you-badge";
      badge.textContent = " (you)";
      authorEl.appendChild(badge);
    }

    const timeEl = document.createElement("span");
    timeEl.className = "annotation-time";
    timeEl.textContent = _timeAgo(annotation.created_at);
    if (annotation.updated_at) {
      const edited = document.createElement("span");
      edited.className = "annotation-edited";
      edited.textContent = " · edited";
      timeEl.appendChild(edited);
    }

    meta.appendChild(authorEl);
    meta.appendChild(timeEl);
    card.appendChild(meta);

    // Body
    const bodyEl = document.createElement("div");
    bodyEl.className = "annotation-card-body";
    if (isDeleted) {
      bodyEl.classList.add("is-tombstone");
      bodyEl.textContent = "[Comment deleted]";
    } else {
      bodyEl.textContent = annotation.body;
    }
    card.appendChild(bodyEl);

    // Actions (reactions, reply, edit, delete) — only on non-deleted annotations
    if (!isDeleted) {
      const actions = document.createElement("div");
      actions.className = "annotation-actions";

      // Reaction buttons
      const reactionsEl = _renderReactions(annotation, isOwn);
      actions.appendChild(reactionsEl);

      // Reply (only on top-level; annotators only)
      if (_isAnnotator && !annotation.parent_id) {
        const replyBtn = document.createElement("button");
        replyBtn.className = "annotation-action-btn annotation-reply-btn";
        replyBtn.textContent = "Reply";
        replyBtn.addEventListener("click", () =>
          _openInlineComposer(annotation, card)
        );
        actions.appendChild(replyBtn);
      }

      // Edit (own only)
      if (isOwn) {
        const editBtn = document.createElement("button");
        editBtn.className = "annotation-action-btn";
        editBtn.textContent = "Edit";
        editBtn.addEventListener("click", () =>
          _startEdit(annotation, card, bodyEl)
        );
        actions.appendChild(editBtn);

        const delBtn = document.createElement("button");
        delBtn.className = "annotation-action-btn annotation-delete-btn";
        delBtn.textContent = "Delete";
        delBtn.addEventListener("click", () => _confirmDelete(annotation, card));
        actions.appendChild(delBtn);
      }

      // Admin delete (not own)
      if (_isAdmin && !isOwn) {
        const adminDelBtn = document.createElement("button");
        adminDelBtn.className = "annotation-action-btn annotation-delete-btn";
        adminDelBtn.textContent = "Delete (admin)";
        adminDelBtn.addEventListener("click", () =>
          _confirmDelete(annotation, card)
        );
        actions.appendChild(adminDelBtn);
      }

      card.appendChild(actions);
    }

    // Replies (sorted chronological, one level deep)
    if (replies && replies.length > 0) {
      const repliesEl = document.createElement("div");
      repliesEl.className = "annotation-replies";
      [...replies]
        .sort((a, b) => new Date(a.created_at) - new Date(b.created_at))
        .forEach((reply) => {
          repliesEl.appendChild(_renderCard(reply, [], isOrphaned));
        });
      card.appendChild(repliesEl);
    }

    return card;
  }

  // ---------------------------------------------------------------------------
  // Anchor preview element
  // ---------------------------------------------------------------------------

  function _renderAnchorPreview(anchorData, isOrphaned) {
    const wrap = document.createElement("div");
    wrap.className = "annotation-anchor-preview";

    const span = document.createElement("span");
    span.className = "annotation-anchor-text";

    if (!anchorData) {
      wrap.appendChild(span);
      return wrap;
    }

    if (anchorData.type === "section") {
      const el = document.getElementById(anchorData.section_id);
      const title = el ? el.textContent.trim() : anchorData.section_id;
      span.textContent = "§ " + title;
    } else if (anchorData.type === "text-range") {
      const selectors = anchorData.selectors || [];
      const quote = selectors.find((s) => s.type === "TextQuoteSelector");
      if (quote && quote.exact) {
        span.textContent = "\u201C" + quote.exact + "\u201D";
        if (isOrphaned) {
          const note = document.createElement("span");
          note.className = "annotation-orphan-note";
          note.textContent = " (original text no longer found)";
          span.appendChild(note);
        }
      }
    }

    wrap.appendChild(span);
    return wrap;
  }

  // ---------------------------------------------------------------------------
  // Reaction buttons
  // ---------------------------------------------------------------------------

  function _renderReactions(annotation, isOwn) {
    const el = document.createElement("span");
    el.className = "annotation-reactions";

    const myReaction = annotation.my_reaction;
    // Can react: must be annotator, not own annotation, annotation not deleted
    const canReact = _isAnnotator && !isOwn && !annotation.deleted_at;
    const ownTitle = "You can\u2019t react to your own comment";

    function _makeReactionBtn(reaction, label) {
      const btn = document.createElement("button");
      btn.className =
        "annotation-reaction-btn" +
        (myReaction === reaction ? " is-active" : "");
      btn.textContent = label;

      if (canReact) {
        btn.title = reaction === "endorse" ? "Endorse" : "Needs work";
        btn.addEventListener("click", () =>
          _handleReact(annotation, reaction, el)
        );
      } else {
        btn.disabled = true;
        btn.title = isOwn ? ownTitle : "";
      }
      return btn;
    }

    const endorseCount = annotation.reactions ? annotation.reactions.endorse : 0;
    const needsWorkCount = annotation.reactions ? annotation.reactions.needs_work : 0;

    el.appendChild(_makeReactionBtn("endorse", "\u25b2 " + endorseCount));
    el.appendChild(_makeReactionBtn("needs_work", "\u2691 " + needsWorkCount));

    return el;
  }

  // ---------------------------------------------------------------------------
  // Highlights in the article body
  // ---------------------------------------------------------------------------

  async function _applyHighlights() {
    _removeHighlights();

    const root = _getAnnotatableRoot();
    if (!root) return;

    const topLevel = Annotations.getAll().filter((a) => !a.parent_id);

    // Group text-range annotations by exact anchor key so we highlight once
    // per unique range even if multiple annotations share it.
    const textGroups = new Map(); // anchorKey -> { range, annotations[] }

    for (const annotation of topLevel) {
      if (!annotation.anchor_data) continue;

      if (annotation.anchor_data.type === "section") {
        const sectionId = annotation.anchor_data.section_id;
        const heading = document.getElementById(sectionId);
        if (!heading) continue;
        // Add marker only once per heading
        if (heading.querySelector(".annotation-section-marker")) continue;

        const marker = document.createElement("span");
        marker.className = "annotation-section-marker";
        marker.setAttribute("aria-label", "Has comments");
        marker.title = "Has comments — click to jump";
        marker.dataset.sectionId = sectionId;
        marker.addEventListener("click", () => _scrollToSection(sectionId));
        heading.insertBefore(marker, heading.firstChild);
        _highlights.push(marker);
      } else if (annotation.anchor_data.type === "text-range") {
        const range = _anchorRanges.get(annotation.id);
        if (!range) continue; // orphaned
        const key = JSON.stringify(annotation.anchor_data);
        if (!textGroups.has(key)) {
          textGroups.set(key, { range, annotations: [] });
        }
        textGroups.get(key).annotations.push(annotation);
      }
    }

    // Apply one <mark> per unique text range
    for (const { range, annotations } of textGroups.values()) {
      try {
        const mark = document.createElement("mark");
        mark.className = "annotation-highlight";
        const count = annotations.length;
        mark.title = count === 1 ? "1 comment" : count + " comments";
        mark.dataset.annotationId = annotations[0].id;

        mark.addEventListener("click", () => {
          _scrollToAnnotation(annotations[0].id);
        });

        const cloned = range.cloneRange();
        try {
          cloned.surroundContents(mark);
        } catch (_) {
          // Range spans multiple nodes (e.g. crosses element boundary)
          const fragment = cloned.extractContents();
          mark.appendChild(fragment);
          cloned.insertNode(mark);
        }
        _highlights.push(mark);
      } catch (e) {
        // Don't let one failed highlight break others
        console.warn("annotation_ui: could not apply highlight", e);
      }
    }
  }

  function _removeHighlights() {
    for (const el of _highlights) {
      if (!el.parentNode) continue;
      if (el.tagName === "MARK") {
        // Unwrap: move children before the mark, then remove
        const parent = el.parentNode;
        while (el.firstChild) {
          parent.insertBefore(el.firstChild, el);
        }
        parent.removeChild(el);
      } else {
        // Section markers and other injected elements
        el.parentNode.removeChild(el);
      }
    }
    _highlights = [];
  }

  function _scrollToAnnotation(annotationId) {
    const card = _drawerBody.querySelector(
      '[data-annotation-id="' + annotationId + '"]'
    );
    if (!card) return;
    card.scrollIntoView({ behavior: "smooth", block: "nearest" });
    card.classList.add("annotation-flash");
    setTimeout(() => card.classList.remove("annotation-flash"), 1500);
  }

  function _scrollToSection(sectionId) {
    const all = Annotations.getAll();
    const first = all.find(
      (a) =>
        a.anchor_data &&
        a.anchor_data.type === "section" &&
        a.anchor_data.section_id === sectionId
    );
    if (first) _scrollToAnnotation(first.id);
  }

  // ---------------------------------------------------------------------------
  // Section-level "Add comment to this section" buttons
  // ---------------------------------------------------------------------------

  function _addSectionButtons() {
    if (!_isAnnotator) return;
    _removeSectionButtons();

    const root = _getAnnotatableRoot();
    if (!root) return;

    root.querySelectorAll("h2[id]").forEach((heading) => {
      const btn = document.createElement("button");
      btn.className = "annotation-section-btn";
      btn.textContent = "Add comment to this section";
      btn.dataset.sectionId = heading.id;
      btn.addEventListener("click", () => {
        const anchor = AnnotationAnchor.createSectionAnchor(heading.id);
        _openMainComposer(anchor);
      });
      heading.insertAdjacentElement("afterend", btn);
      _sectionBtns.push(btn);
    });
  }

  function _removeSectionButtons() {
    _sectionBtns.forEach((btn) => {
      if (btn.parentNode) btn.parentNode.removeChild(btn);
    });
    _sectionBtns = [];
  }

  // ---------------------------------------------------------------------------
  // Floating "Add comment" button on text selection
  // ---------------------------------------------------------------------------

  function _onMouseUp(e) {
    // Clicks inside the drawer don't trigger the floating button
    if (_drawer && _drawer.contains(e.target)) return;

    const selection = window.getSelection();
    if (!selection || selection.isCollapsed || !selection.toString().trim()) {
      _hideFloatingButton();
      return;
    }

    const root = _getAnnotatableRoot();
    if (!root) return;

    const range = selection.getRangeAt(0);
    if (!root.contains(range.commonAncestorContainer)) {
      _hideFloatingButton();
      return;
    }

    _showFloatingButton(range);
  }

  function _showFloatingButton(range) {
    _hideFloatingButton();

    // Clone the range immediately — clicking the button clears the browser
    // selection before the click handler fires, so we can't re-read it then.
    const savedRange = range.cloneRange();

    const rect = range.getBoundingClientRect();
    _floatingBtn = document.createElement("button");
    _floatingBtn.className = "annotation-float-btn";
    _floatingBtn.textContent = "Add comment";
    _floatingBtn.style.left = rect.left + rect.width / 2 + "px";
    _floatingBtn.style.top = Math.max(rect.top - 44, 70) + "px";

    // preventDefault on mousedown keeps the text selection alive.
    // stopPropagation on both mousedown AND mouseup prevents _onMouseUp
    // from seeing these events — if it did, it would see a live selection
    // and call _showFloatingButton again, removing this button before
    // the click event fires.
    _floatingBtn.addEventListener("mousedown", (e) => {
      e.preventDefault();
      e.stopPropagation();
    });
    _floatingBtn.addEventListener("mouseup", (e) => {
      e.stopPropagation();
    });

    _floatingBtn.addEventListener("click", async () => {
      const root = _getAnnotatableRoot();
      if (!root) return;

      try {
        const anchor = await AnnotationAnchor.createAnchorFromSelection(
          savedRange,
          root
        );
        _hideFloatingButton();
        // Open the drawer first if it's closed, then show the composer.
        if (!_drawerOpen) await _openDrawer();
        _openMainComposer(anchor);
      } catch (e) {
        console.error("annotation_ui: failed to create anchor", e);
      }
    });

    document.body.appendChild(_floatingBtn);
  }

  function _hideFloatingButton() {
    if (_floatingBtn) {
      if (_floatingBtn.parentNode) _floatingBtn.parentNode.removeChild(_floatingBtn);
      _floatingBtn = null;
    }
  }

  // ---------------------------------------------------------------------------
  // Main composer (bottom of drawer — for new top-level annotations)
  // ---------------------------------------------------------------------------

  function _openMainComposer(anchor) {
    _drawerComposerWrap.innerHTML = "";
    _drawerComposerWrap.style.display = "block";
    _buildComposerForm(_drawerComposerWrap, anchor, null, _closeComposer, async (anchor, body) => {
      const created = await Annotations.create(anchor, body, null);
      _closeComposer();
      await _renderDrawer();
      _applyHighlights();
      _addSectionButtons();
      _scrollToAnnotation(created.id);
    });
    // Scroll the composer into view
    _drawerComposerWrap.scrollIntoView({ behavior: "smooth", block: "end" });
  }

  function _closeComposer() {
    _drawerComposerWrap.innerHTML = "";
    _drawerComposerWrap.style.display = "none";
  }

  // ---------------------------------------------------------------------------
  // Inline reply composer (below a card)
  // ---------------------------------------------------------------------------

  function _openInlineComposer(parentAnnotation, parentCard) {
    // Toggle: clicking reply twice removes the composer
    const existing = parentCard.querySelector(".annotation-inline-composer");
    if (existing) {
      existing.parentNode.removeChild(existing);
      return;
    }

    const wrap = document.createElement("div");
    wrap.className = "annotation-inline-composer";

    _buildComposerForm(
      wrap,
      parentAnnotation.anchor_data,
      null,
      () => { if (wrap.parentNode) wrap.parentNode.removeChild(wrap); },
      async (_anchor, body) => {
        const created = await Annotations.create(
          parentAnnotation.anchor_data,
          body,
          parentAnnotation.id
        );
        if (wrap.parentNode) wrap.parentNode.removeChild(wrap);
        await _renderDrawer();
        _applyHighlights();
        _scrollToAnnotation(created.id);
      },
      true // isReply — hide anchor preview, smaller textarea
    );

    parentCard.appendChild(wrap);
    const ta = wrap.querySelector("textarea");
    if (ta) ta.focus();
  }

  // ---------------------------------------------------------------------------
  // Shared composer form builder
  // ---------------------------------------------------------------------------

  /**
   * Build a composer form inside `container`.
   * @param {Element}  container
   * @param {Object}   anchorData
   * @param {string|null} initialBody  — for edit mode (pre-filled)
   * @param {Function} onCancel
   * @param {Function} onSubmit(anchorData, body) — async, should throw on error
   * @param {boolean}  isReply — omits anchor preview, smaller textarea
   */
  function _buildComposerForm(
    container,
    anchorData,
    initialBody,
    onCancel,
    onSubmit,
    isReply = false
  ) {
    // Anchor preview (top-level only)
    if (!isReply && anchorData) {
      const preview = document.createElement("div");
      preview.className = "annotation-composer-preview";
      const previewInner = _renderAnchorPreview(anchorData, false);
      preview.appendChild(previewInner);
      container.appendChild(preview);
    }

    const textarea = document.createElement("textarea");
    textarea.className = "annotation-composer-textarea";
    textarea.placeholder = isReply ? "Write a reply…" : "Add your comment…";
    textarea.rows = isReply ? 3 : 5;
    if (initialBody) textarea.value = initialBody;

    const errorEl = document.createElement("div");
    errorEl.className = "annotation-composer-error";
    errorEl.style.display = "none";

    const btns = document.createElement("div");
    btns.className = "annotation-composer-btns";

    const cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.className = "annotation-composer-cancel";
    cancelBtn.textContent = "Cancel";
    cancelBtn.addEventListener("click", () => {
      if (textarea.value.trim() && !initialBody) {
        if (window.confirm("Discard your comment?")) onCancel();
      } else {
        onCancel();
      }
    });

    const submitBtn = document.createElement("button");
    submitBtn.type = "button";
    submitBtn.className = "annotation-composer-submit";
    submitBtn.textContent = isReply ? "Reply" : (initialBody ? "Save" : "Submit");
    submitBtn.disabled = !textarea.value.trim();

    textarea.addEventListener("input", () => {
      submitBtn.disabled = !textarea.value.trim();
    });

    submitBtn.addEventListener("click", async () => {
      const body = textarea.value.trim();
      if (!body) return;

      submitBtn.disabled = true;
      const origLabel = submitBtn.textContent;
      submitBtn.textContent = "Saving…";
      errorEl.style.display = "none";

      try {
        await onSubmit(anchorData, body);
      } catch (e) {
        errorEl.textContent = _errorMessage(e);
        errorEl.style.display = "block";
        submitBtn.disabled = false;
        submitBtn.textContent = origLabel;
      }
    });

    btns.appendChild(cancelBtn);
    btns.appendChild(submitBtn);

    container.appendChild(textarea);
    container.appendChild(errorEl);
    container.appendChild(btns);
  }

  // ---------------------------------------------------------------------------
  // Edit flow
  // ---------------------------------------------------------------------------

  function _startEdit(annotation, card, bodyEl) {
    // Prevent double-edit
    if (card.querySelector(".annotation-composer-textarea")) return;

    const originalText = annotation.body;
    bodyEl.style.display = "none";

    const editWrap = document.createElement("div");

    _buildComposerForm(
      editWrap,
      null,      // no anchor preview in edit mode
      originalText,
      () => {
        if (editWrap.parentNode) editWrap.parentNode.removeChild(editWrap);
        bodyEl.style.display = "";
      },
      async (_anchor, body) => {
        await Annotations.update(annotation.id, body);
        if (editWrap.parentNode) editWrap.parentNode.removeChild(editWrap);
        bodyEl.style.display = "";
        await _renderDrawer();
        _applyHighlights();
      }
    );

    card.insertBefore(editWrap, bodyEl.nextSibling);
    const ta = editWrap.querySelector("textarea");
    if (ta) ta.focus();
  }

  // ---------------------------------------------------------------------------
  // Delete flow
  // ---------------------------------------------------------------------------

  function _confirmDelete(annotation, card) {
    // Toggle: clicking delete again dismisses the confirmation
    const existing = card.querySelector(".annotation-delete-confirm");
    if (existing) {
      existing.parentNode.removeChild(existing);
      return;
    }

    const confirm = document.createElement("div");
    confirm.className = "annotation-delete-confirm";

    const msg = document.createElement("span");
    msg.textContent = "Delete this comment?";

    const yesBtn = document.createElement("button");
    yesBtn.className = "annotation-delete-yes";
    yesBtn.textContent = "Yes, delete";

    const noBtn = document.createElement("button");
    noBtn.className = "annotation-composer-cancel";
    noBtn.textContent = "Cancel";
    noBtn.addEventListener("click", () => {
      if (confirm.parentNode) confirm.parentNode.removeChild(confirm);
    });

    const errorEl = document.createElement("span");
    errorEl.className = "annotation-composer-error";
    errorEl.style.display = "none";

    yesBtn.addEventListener("click", async () => {
      yesBtn.disabled = true;
      yesBtn.textContent = "Deleting…";
      errorEl.style.display = "none";
      try {
        await Annotations.remove(annotation.id);
        await _renderDrawer();
        _applyHighlights();
        _updateToggleCount();
      } catch (e) {
        errorEl.textContent = _errorMessage(e);
        errorEl.style.display = "inline";
        yesBtn.disabled = false;
        yesBtn.textContent = "Yes, delete";
      }
    });

    confirm.appendChild(msg);
    confirm.appendChild(yesBtn);
    confirm.appendChild(noBtn);
    confirm.appendChild(errorEl);
    card.appendChild(confirm);
  }

  // ---------------------------------------------------------------------------
  // Reaction handling
  // ---------------------------------------------------------------------------

  async function _handleReact(annotation, reaction, reactionsEl) {
    const wasActive = annotation.my_reaction === reaction;

    try {
      let result;
      if (wasActive) {
        await Annotations.unreact(annotation.id);
        // unreact returns null (204); update cache manually
        annotation.my_reaction = null;
        // Re-fetch accurate counts
        await Annotations.fetchForCurrentPage();
        await _renderDrawer();
        _applyHighlights();
        return;
      } else {
        result = await Annotations.react(annotation.id, reaction);
      }

      if (result) {
        // Update the annotation object in-place for the re-render
        annotation.my_reaction = result.my_reaction;
        annotation.reactions = {
          endorse: result.endorse,
          needs_work: result.needs_work,
        };
        // Re-render just the reactions element to avoid full drawer re-render
        const newReactionsEl = _renderReactions(
          annotation,
          annotation.author.id === _user.id
        );
        reactionsEl.parentNode.replaceChild(newReactionsEl, reactionsEl);
      }
    } catch (e) {
      // Show brief inline error
      const errEl = document.createElement("span");
      errEl.className = "annotation-composer-error";
      errEl.textContent = _errorMessage(e);
      if (reactionsEl.parentNode) {
        reactionsEl.parentNode.insertBefore(errEl, reactionsEl.nextSibling);
        setTimeout(() => {
          if (errEl.parentNode) errEl.parentNode.removeChild(errEl);
        }, 3000);
      }
    }
  }

  // ---------------------------------------------------------------------------
  // Keyboard handler
  // ---------------------------------------------------------------------------

  function _onKeyDown(e) {
    if (e.key === "Escape" && _drawerOpen) {
      _closeDrawer();
    }
  }

  // ---------------------------------------------------------------------------
  // Public interface
  // ---------------------------------------------------------------------------

  window.AnnotationUI = { init };
})();
