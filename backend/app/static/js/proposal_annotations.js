/**
 * proposal_annotations.js — Data layer and orchestration for proposal annotations.
 *
 * Coordinates between ProposalAnchor (anchoring), the API (api.js), and
 * ProposalAnnotationUI (rendering). After any mutation it re-fetches and re-renders.
 *
 * Depends on (loaded before this file):
 *   - api.js          (fetchAnnotations, createProposalAnnotation, etc.)
 *   - proposal_anchor.js  (window.ProposalAnchor)
 *   - proposal_annotation_ui.js  (window.ProposalAnnotationUI)
 *
 * Exposes: window.ProposalAnnotations
 */

(function () {
  'use strict';

  // ---------------------------------------------------------------------------
  // Module state
  // ---------------------------------------------------------------------------

  let _config = null;       // { proposalId, threadStatus, docEl, sidebarEl, headerCountEl, currentUser }
  let _annotations = [];    // flat list of top-level annotations (replies nested inside)
  let _pendingAnchor = null; // { anchor, range } — set while composer is open
  let _chipEl = null;       // the floating "Annotate" button near the selection
  let _lastCreatedId = null; // ID of the most recently created annotation, for focus management

  // Polling state
  let _pollTimer = null;
  let _pollIntervalMs = 30000;        // 30 seconds when focused
  let _pollIntervalMsBlurred = 300000; // 5 minutes when hidden
  let _inFlight = false;
  let _knownAnnotationIds = new Set();

  // ---------------------------------------------------------------------------
  // Init
  // ---------------------------------------------------------------------------

  /**
   * Initialize the annotation system.
   *
   * @param {{
   *   proposalId:     string,
   *   threadStatus:   string,   // e.g. 'PROPOSING'
   *   docEl:          Element,  // #pr-doc
   *   sidebarEl:      Element,  // #pr-anno-list
   *   headerCountEl:  Element,  // #pr-anno-count
   *   currentUser:    {id: string, display_name: string} | null
   * }} config
   */
  async function init(config) {
    _config = config;
    ProposalAnnotationUI.init({
      sidebarEl: config.sidebarEl,
      docEl: config.docEl,
      currentUser: config.currentUser,
      isReadOnly: !_isWritable(),
      threadStatus: config.threadStatus,
      onReact: (id, reactionType) => react(id, reactionType),
      onReply: (parentId, body) => reply(parentId, body),
      onResolve: (id) => resolve(id),
      onUnresolve: (id) => unresolve(id),
      onFeature: (id) => feature(id),
      onUnfeature: (id) => unfeature(id),
      onModerate: (id, reason) => moderate(id, reason),
      onSubmitNew: (body) => _submitPendingAnnotation(body),
      onCancelNew: () => { _pendingAnchor = null; _removeChip(); },
    });

    await _load();
    _bindTextSelection();
    _bindHighlightClicks();
    _startPolling();
  }

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  function _isWritable() {
    return _config && _config.threadStatus?.toLowerCase() === 'proposing' && _config.currentUser;
  }

  function _totalCount(annotations) {
    return annotations.reduce((n, a) => n + 1 + (a.replies ? a.replies.length : 0), 0);
  }

  // ---------------------------------------------------------------------------
  // Data fetch + render
  // ---------------------------------------------------------------------------

  async function _load() {
    ProposalAnnotationUI.renderLoading();
    try {
      _annotations = await fetchAnnotations('proposal', _config.proposalId);
    } catch (e) {
      console.error('[ProposalAnnotations] fetch failed', e);
      ProposalAnnotationUI.renderError(() => _load());
      return;
    }

    _applyHighlights();
    _knownAnnotationIds = new Set(_annotations.map(a => a.id));
    _render();

    if (_lastCreatedId) {
      ProposalAnnotationUI.focusCard(_lastCreatedId);
      _lastCreatedId = null;
    }
  }

  function _applyHighlights() {
    _clearHighlights();
    const docEl = _config.docEl;
    for (const anno of _annotations) {
      if (anno.deleted_at) continue;
      if (!anno.anchor_data || !anno.anchor_data.selector) continue;
      const range = ProposalAnchor.deserialize(anno.anchor_data, docEl);
      if (range) {
        ProposalAnchor.applyHighlight(range, anno.id);
      } else if (!anno.orphaned_at) {
        markAnnotationOrphaned(anno.id).catch(() => {});
      }
    }
  }

  function _clearHighlights() {
    const spans = _config.docEl.querySelectorAll('.proposal-annotation-highlight');
    spans.forEach(span => {
      const parent = span.parentNode;
      while (span.firstChild) parent.insertBefore(span.firstChild, span);
      parent.removeChild(span);
    });
  }

  function _render() {
    const count = _totalCount(_annotations);
    if (_config.headerCountEl) {
      _config.headerCountEl.textContent = String(count);
    }
    ProposalAnnotationUI.render(_annotations, {
      pendingAnchor: _pendingAnchor,
      isReadOnly: !_isWritable(),
    });
  }

  // ---------------------------------------------------------------------------
  // Polling
  // ---------------------------------------------------------------------------

  function _startPolling() {
    _scheduleNextPoll();
    document.addEventListener('visibilitychange', () => _scheduleNextPoll());
    window.addEventListener('focus', () => _scheduleNextPoll());
    window.addEventListener('blur', () => _scheduleNextPoll());
    window.addEventListener('beforeunload', () => clearTimeout(_pollTimer));
  }

  function _scheduleNextPoll() {
    clearTimeout(_pollTimer);
    const interval = document.hidden ? _pollIntervalMsBlurred : _pollIntervalMs;
    _pollTimer = setTimeout(() => _poll(), interval);
  }

  async function _poll() {
    if (_inFlight) return _scheduleNextPoll();
    _inFlight = true;
    try {
      const fresh = await fetchAnnotations('proposal', _config.proposalId);
      await _mergeUpdates(fresh);
    } catch (err) {
      console.warn('[ProposalAnnotations] poll failed', err);
    } finally {
      _inFlight = false;
      _scheduleNextPoll();
    }
  }

  async function _mergeUpdates(fresh) {
    const freshIds = new Set(fresh.map(a => a.id));
    const hasChanges =
      fresh.length !== _annotations.length ||
      fresh.some(a => !_knownAnnotationIds.has(a.id)) ||
      _annotations.some(a => !freshIds.has(a.id));

    if (!hasChanges) return;

    // Find new annotations not by the current user (for toast)
    const newAnnos = fresh.filter(a => !_knownAnnotationIds.has(a.id));
    const newFromOthers = newAnnos.filter(
      a => !_config.currentUser || a.author?.id !== _config.currentUser.id
    );

    // Save open reply forms before re-render
    const openReplyForms = {};
    _config.sidebarEl.querySelectorAll('.paa-reply-form:not([hidden])').forEach(f => {
      openReplyForms[f.dataset.parentId] = f.querySelector('textarea').value;
    });

    _annotations = fresh;
    _knownAnnotationIds = freshIds;

    _applyHighlights();
    _render();

    // Restore open reply forms
    Object.entries(openReplyForms).forEach(([parentId, value]) => {
      const card = _config.sidebarEl.querySelector(
        `.proposal-annotation-card[data-anno-id="${CSS.escape(parentId)}"]`
      );
      if (!card) return;
      const form = card.querySelector('.paa-reply-form');
      if (form) {
        form.hidden = false;
        if (value) form.querySelector('textarea').value = value;
      }
    });

    if (newFromOthers.length > 0) {
      _showToast(`${newFromOthers.length} new annotation${newFromOthers.length > 1 ? 's' : ''}`);
    }
  }

  function _showToast(message) {
    const parent = _config.sidebarEl.parentElement;
    const existing = parent.querySelector('.paa-toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = 'paa-toast';
    toast.textContent = message;
    toast.addEventListener('click', () => toast.remove());
    parent.appendChild(toast);
    setTimeout(() => { if (toast.parentElement) toast.remove(); }, 5000);
  }

  // ---------------------------------------------------------------------------
  // Text selection → "Annotate" chip
  // ---------------------------------------------------------------------------

  function _bindTextSelection() {
    document.addEventListener('mouseup', _onMouseUp);
  }

  function _onMouseUp() {
    if (!_isWritable()) return;

    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || !sel.rangeCount) {
      _removeChip();
      return;
    }

    const range = sel.getRangeAt(0);
    if (!_config.docEl.contains(range.commonAncestorContainer)) {
      _removeChip();
      return;
    }

    const selectedText = sel.toString().trim();
    if (!selectedText) {
      _removeChip();
      return;
    }

    const anchor = ProposalAnchor.serialize(range, _config.docEl);
    if (!anchor) {
      _removeChip();
      return;
    }

    _showChip(range.getBoundingClientRect(), anchor, range);
  }

  function _showChip(rect, anchor, range) {
    _removeChip();

    const chip = document.createElement('button');
    chip.className = 'paa-annotate-chip';
    chip.textContent = '+ Annotate';
    chip.setAttribute('aria-label', 'Annotate selected text');

    const docRect = _config.docEl.getBoundingClientRect();
    const scrollY = window.scrollY || window.pageYOffset;
    chip.style.position = 'absolute';
    chip.style.top = (rect.bottom + scrollY + 6) + 'px';
    chip.style.left = Math.max(rect.left, docRect.left) + 'px';
    chip.style.zIndex = '200';

    chip.addEventListener('mousedown', (e) => {
      e.preventDefault();
      _pendingAnchor = { anchor, range };
      _removeChip();
      window.getSelection().removeAllRanges();
      ProposalAnnotationUI.showComposer(anchor);
    });

    document.body.appendChild(chip);
    _chipEl = chip;
  }

  function _removeChip() {
    if (_chipEl) {
      _chipEl.remove();
      _chipEl = null;
    }
  }

  // ---------------------------------------------------------------------------
  // Highlight → card cross-scroll
  // ---------------------------------------------------------------------------

  function _bindHighlightClicks() {
    _config.docEl.addEventListener('click', (e) => {
      const span = e.target.closest('.proposal-annotation-highlight');
      if (!span) return;
      const id = span.dataset.annoId;
      if (id) ProposalAnnotationUI.scrollToCard(id);
    });
  }

  // ---------------------------------------------------------------------------
  // Mutations
  // ---------------------------------------------------------------------------

  async function _submitPendingAnnotation(body) {
    if (!_pendingAnchor) return;
    const { anchor } = _pendingAnchor;
    _pendingAnchor = null;
    await create({ anchor_data: anchor, body });
  }

  async function create({ anchor_data, body, parent_id = null }) {
    const created = await createProposalAnnotation({
      target_type: 'proposal',
      target_id: _config.proposalId,
      anchor_data,
      body,
      parent_id,
    });
    if (created && created.id) {
      _lastCreatedId = created.id;
    }
    await _load();
  }

  async function reply(parentId, body) {
    return create({ anchor_data: {}, body, parent_id: parentId });
  }

  async function react(annotationId, reactionType) {
    const anno = _findAnnotation(annotationId);
    if (anno && anno.my_reaction === reactionType) {
      await unreactAnnotation(annotationId);
    } else {
      await reactToAnnotation(annotationId, reactionType);
    }
    await _load();
  }

  async function resolve(annotationId) {
    await resolveAnnotation(annotationId);
    await _load();
  }

  async function unresolve(annotationId) {
    await unresolveAnnotation(annotationId);
    await _load();
  }

  async function feature(annotationId) {
    await featureAnnotation(annotationId);
    await _load();
  }

  async function unfeature(annotationId) {
    await unfeatureAnnotation(annotationId);
    await _load();
  }

  async function moderate(annotationId, reason) {
    await moderateAnnotation(annotationId, reason);
    await _load();
  }

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  function _findAnnotation(id) {
    for (const a of _annotations) {
      if (a.id === id) return a;
      for (const r of (a.replies || [])) {
        if (r.id === id) return r;
      }
    }
    return null;
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  window.ProposalAnnotations = {
    init,
    reload: _load,
    create,
    reply,
    react,
    resolve,
    unresolve,
    feature,
    unfeature,
    moderate,
  };

})();
