/**
 * proposal_annotation_ui.js — Pure rendering for proposal annotations.
 *
 * Receives state from ProposalAnnotations and renders into the sidebar.
 * No fetch calls here — all data mutations go through ProposalAnnotations callbacks.
 *
 * Exposes: window.ProposalAnnotationUI
 */

(function () {
  'use strict';

  // ---------------------------------------------------------------------------
  // Module state
  // ---------------------------------------------------------------------------

  let _sidebarEl = null;
  let _docEl = null;
  let _currentUser = null;
  let _isReadOnly = false;
  let _threadStatus = null;
  let _callbacks = {};
  let _composerEl = null;

  // Persistent UI elements outside sidebarEl
  let _bannerEl = null;
  let _controlsEl = null;

  // Annotation lookup map (id → annotation) updated on every render
  let _annotationsMap = {};
  let _lastCounts = {};

  // Current filter/sort state (not persisted across page loads)
  let _currentFilter = 'all';
  let _currentSort = 'position';
  let _userRole = null; // 'author' | 'facilitator' | 'reviewer' | 'observer' | null

  // Moderation modal state
  let _modalEl = null;
  let _modalAnnoId = null;
  let _modalTriggerEl = null;
  let _modalKeydownHandler = null;

  // ---------------------------------------------------------------------------
  // Init
  // ---------------------------------------------------------------------------

  /**
   * @param {{
   *   sidebarEl:    Element,
   *   docEl:        Element,
   *   currentUser:  {id, display_name} | null,
   *   isReadOnly:   boolean,
   *   threadStatus: string,
   *   onReact, onReply, onResolve, onUnresolve, onFeature, onUnfeature,
   *   onModerate, onSubmitNew, onCancelNew
   * }} config
   */
  function init(config) {
    _sidebarEl = config.sidebarEl;
    _docEl = config.docEl;
    _currentUser = config.currentUser;
    _isReadOnly = config.isReadOnly;
    _threadStatus = config.threadStatus || null;
    _userRole = config.userRole || null;
    _callbacks = {
      onReact: config.onReact || (() => {}),
      onReply: config.onReply || (() => {}),
      onResolve: config.onResolve || (() => {}),
      onUnresolve: config.onUnresolve || (() => {}),
      onFeature: config.onFeature || (() => {}),
      onUnfeature: config.onUnfeature || (() => {}),
      onModerate: config.onModerate || (() => {}),
      onSubmitNew: config.onSubmitNew || (() => {}),
      onCancelNew: config.onCancelNew || (() => {}),
    };

    // Render persistent siblings above the list (outside sidebarEl)
    _renderBanner();
    _renderRoleBadge();
    _renderControls();

    // Single delegated click listener on sidebar
    _sidebarEl.addEventListener('click', _onSidebarClick);
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  /**
   * Re-render the entire sidebar from the annotations list.
   * @param {Array}  annotations  - Top-level annotation objects (replies nested)
   * @param {Object} state        - { pendingAnchor, isReadOnly }
   */
  function render(annotations, state) {
    _isReadOnly = state.isReadOnly;

    // Update lookup map
    _annotationsMap = Object.fromEntries((annotations || []).map(a => [a.id, a]));

    // Keep composer if it's currently open (user is typing)
    const composerOpen = _composerEl && _sidebarEl.contains(_composerEl);

    // Clear sidebar
    _sidebarEl.innerHTML = '';

    if (composerOpen && _composerEl) {
      _sidebarEl.insertBefore(_composerEl, _sidebarEl.firstChild);
    }

    if (!annotations || annotations.length === 0) {
      if (!composerOpen) {
        _renderEmpty();
      }
      _updateFilterCounts([]);
      return;
    }

    for (const anno of annotations) {
      _sidebarEl.appendChild(_buildCard(anno));
    }

    _updateFilterCounts(annotations);
    _applyCurrentSort();
  }

  // ---------------------------------------------------------------------------
  // Loading / error / empty states (called from ProposalAnnotations)
  // ---------------------------------------------------------------------------

  function renderLoading() {
    const composerOpen = _composerEl && _sidebarEl.contains(_composerEl);
    _sidebarEl.innerHTML = '';
    if (composerOpen && _composerEl) {
      _sidebarEl.insertBefore(_composerEl, _sidebarEl.firstChild);
    }
    const skeleton = document.createElement('div');
    skeleton.className = 'paa-skeleton';
    skeleton.innerHTML = '<div class="paa-skeleton-card"></div><div class="paa-skeleton-card"></div>';
    _sidebarEl.appendChild(skeleton);
  }

  function renderError(onRetry) {
    _sidebarEl.innerHTML = '';
    const el = document.createElement('div');
    el.className = 'paa-error-state';
    el.innerHTML = '<p class="paa-error-message">Could not load annotations.</p>';
    const retryBtn = document.createElement('button');
    retryBtn.className = 'paa-error-retry';
    retryBtn.textContent = 'Retry';
    retryBtn.addEventListener('click', () => { if (onRetry) onRetry(); });
    el.appendChild(retryBtn);
    _sidebarEl.appendChild(el);
  }

  function _renderEmpty() {
    const el = document.createElement('div');
    el.className = 'paa-empty-state';
    let msg;
    if (_currentUser && _threadStatus?.toLowerCase() === 'proposing') {
      msg = 'No annotations yet. Select text in the proposal to add one.';
    } else if (_currentUser) {
      msg = 'No annotations on this proposal.';
    } else {
      msg = 'No annotations yet. Sign in to add one during PROPOSING.';
    }
    el.innerHTML = `<p class="paa-empty-message">${_esc(msg)}</p>`;
    _sidebarEl.appendChild(el);
  }

  // ---------------------------------------------------------------------------
  // Persistent sidebar elements (inserted before sidebarEl as siblings)
  // ---------------------------------------------------------------------------

  function _renderBanner() {
    if (_bannerEl) { _bannerEl.remove(); _bannerEl = null; }
    if (!_threadStatus || _threadStatus?.toLowerCase() === 'proposing') return;

    const PHASE_TEXT = {
      deliberating: 'Annotations open during PROPOSING phase only.',
      voting: 'Annotations are read-only during voting.',
      closed: 'This thread is closed; annotations are read-only.',
      archived: 'This thread is closed; annotations are read-only.',
    };
    const text = PHASE_TEXT[_threadStatus.toLowerCase()] || 'Annotations are read-only.';

    _bannerEl = document.createElement('div');
    _bannerEl.className = 'paa-readonly-banner';
    _bannerEl.setAttribute('role', 'status');
    _bannerEl.innerHTML = `<strong>Annotations are read-only.</strong> ${_esc(text)}`;
    _sidebarEl.parentElement.insertBefore(_bannerEl, _sidebarEl);
  }

  let _roleBadgeEl = null;

  function _renderRoleBadge() {
    if (_roleBadgeEl) { _roleBadgeEl.remove(); _roleBadgeEl = null; }
    if (!_currentUser || _userRole === 'author') return;

    const ROLE_CONFIG = {
      author:      { label: 'Proposal author',  cls: 'paa-role--author' },
      facilitator: { label: 'Facilitator',       cls: 'paa-role--facilitator' },
      reviewer:    { label: 'Reviewer',          cls: 'paa-role--reviewer' },
      observer:    { label: 'Observer (read-only)', cls: 'paa-role--observer' },
    };
    const cfg = ROLE_CONFIG[_userRole];
    if (!cfg) return;

    _roleBadgeEl = document.createElement('div');
    _roleBadgeEl.className = `paa-role-badge ${cfg.cls}`;
    _roleBadgeEl.setAttribute('role', 'status');
    _roleBadgeEl.textContent = `You · ${cfg.label}`;
    _sidebarEl.parentElement.insertBefore(_roleBadgeEl, _sidebarEl);
  }

  function _renderControls() {
    if (_controlsEl) { _controlsEl.remove(); _controlsEl = null; }

    _controlsEl = document.createElement('div');
    _controlsEl.className = 'paa-controls';

    // Filter chips
    const filtersEl = document.createElement('div');
    filtersEl.className = 'paa-filters';
    filtersEl.setAttribute('role', 'tablist');
    filtersEl.setAttribute('aria-label', 'Filter annotations');

    ['all', 'open', 'resolved', 'featured'].forEach(f => {
      const btn = document.createElement('button');
      btn.className = 'paa-chip' + (f === _currentFilter ? ' is-on' : '');
      btn.dataset.filter = f;
      btn.setAttribute('role', 'tab');
      btn.setAttribute('aria-selected', f === _currentFilter ? 'true' : 'false');
      const label = f.charAt(0).toUpperCase() + f.slice(1);
      btn.innerHTML = `${label} <span class="paa-chip-count">0</span>`;
      btn.addEventListener('click', () => _setFilter(f));
      filtersEl.appendChild(btn);
    });

    // Sort selector
    const sortWrap = document.createElement('div');
    sortWrap.className = 'paa-sort-wrap';

    const sort = document.createElement('select');
    sort.className = 'paa-sort';
    sort.setAttribute('aria-label', 'Sort annotations');
    sort.innerHTML = `
      <option value="position" selected>By position</option>
      <option value="newest">Newest first</option>
      <option value="oldest">Oldest first</option>
      <option value="reactions">Most reactions</option>
    `;
    sort.addEventListener('change', () => {
      _currentSort = sort.value;
      _applyCurrentSort();
    });
    sortWrap.appendChild(sort);

    _controlsEl.appendChild(filtersEl);
    _controlsEl.appendChild(sortWrap);

    // Insert before sidebarEl; banner (if present) was already inserted before sidebarEl
    _sidebarEl.parentElement.insertBefore(_controlsEl, _sidebarEl);
  }

  function _setFilter(f) {
    _currentFilter = f;
    _sidebarEl.dataset.filter = f;
    if (_controlsEl) {
      _controlsEl.querySelectorAll('.paa-chip').forEach(chip => {
        const active = chip.dataset.filter === f;
        chip.classList.toggle('is-on', active);
        chip.setAttribute('aria-selected', active ? 'true' : 'false');
      });
    }
    _updateFilterEmptyState();
  }

  function _updateFilterCounts(annotations) {
    _lastCounts = {
      all: annotations.length,
      open: annotations.filter(a => !a.resolved_at).length,
      resolved: annotations.filter(a => a.resolved_at).length,
      featured: annotations.filter(a => a.featured_at).length,
    };
    if (_controlsEl) {
      _controlsEl.querySelectorAll('.paa-chip').forEach(chip => {
        const countEl = chip.querySelector('.paa-chip-count');
        if (countEl) countEl.textContent = String(_lastCounts[chip.dataset.filter] ?? 0);
      });
    }
    _updateFilterEmptyState();
  }

  function _updateFilterEmptyState() {
    const existing = _sidebarEl.querySelector('.paa-filter-empty');
    if (existing) existing.remove();
    if (!_currentFilter || _currentFilter === 'all') return;

    const count = _lastCounts[_currentFilter] ?? 0;
    const total = _lastCounts.all ?? 0;
    if (count === 0 && total > 0) {
      const msg = document.createElement('p');
      msg.className = 'paa-filter-empty';
      msg.textContent = `No ${_currentFilter} annotations.`;
      _sidebarEl.appendChild(msg);
    }
  }

  // ---------------------------------------------------------------------------
  // Sort
  // ---------------------------------------------------------------------------

  function _applyCurrentSort() {
    const cards = Array.from(
      _sidebarEl.querySelectorAll('.proposal-annotation-card:not(.paa-reply-card)')
    );
    if (cards.length <= 1) return;

    const sortFn = _getSortFn(_currentSort);
    const featured = cards.filter(c => c.dataset.featured === 'true');
    const nonFeatured = cards.filter(c => c.dataset.featured !== 'true');
    featured.sort(sortFn);
    nonFeatured.sort(sortFn);

    [...featured, ...nonFeatured].forEach(card => _sidebarEl.appendChild(card));

    // Keep composer first if still open
    if (_composerEl && _sidebarEl.contains(_composerEl)) {
      _sidebarEl.insertBefore(_composerEl, _sidebarEl.firstChild);
    }
    // Keep filter-empty message last
    const emptyMsg = _sidebarEl.querySelector('.paa-filter-empty');
    if (emptyMsg) _sidebarEl.appendChild(emptyMsg);
  }

  function _getSortFn(sortValue) {
    switch (sortValue) {
      case 'newest':
        return (a, b) => {
          const annoA = _annotationsMap[a.dataset.annoId];
          const annoB = _annotationsMap[b.dataset.annoId];
          if (!annoA || !annoB) return 0;
          return new Date(annoB.created_at) - new Date(annoA.created_at);
        };
      case 'oldest':
        return (a, b) => {
          const annoA = _annotationsMap[a.dataset.annoId];
          const annoB = _annotationsMap[b.dataset.annoId];
          if (!annoA || !annoB) return 0;
          return new Date(annoA.created_at) - new Date(annoB.created_at);
        };
      case 'reactions':
        return (a, b) => {
          const annoA = _annotationsMap[a.dataset.annoId];
          const annoB = _annotationsMap[b.dataset.annoId];
          if (!annoA || !annoB) return 0;
          const rA = (annoA.reactions?.endorse || 0) + (annoA.reactions?.needs_work || 0);
          const rB = (annoB.reactions?.endorse || 0) + (annoB.reactions?.needs_work || 0);
          if (rB !== rA) return rB - rA;
          return new Date(annoB.created_at) - new Date(annoA.created_at);
        };
      case 'position':
      default:
        return (a, b) => {
          const aOrph = a.dataset.orphaned === 'true';
          const bOrph = b.dataset.orphaned === 'true';
          if (aOrph && !bOrph) return 1;
          if (!aOrph && bOrph) return -1;
          return _annotationY(a.dataset.annoId) - _annotationY(b.dataset.annoId);
        };
    }
  }

  function _annotationY(annoId) {
    const span = document.querySelector(
      `.proposal-annotation-highlight[data-anno-id="${CSS.escape(annoId)}"]`
    );
    return span ? span.getBoundingClientRect().top + window.scrollY : Infinity;
  }

  // ---------------------------------------------------------------------------
  // Composer
  // ---------------------------------------------------------------------------

  /**
   * Show the top-level composer at the top of the sidebar.
   * @param {Object} anchor - The pending anchor object
   * @param {Object} [opts] - { replyTo: annotationId | null }
   */
  function showComposer(anchor, opts) {
    if (opts && opts.replyTo) return; // reply composer is handled inline

    hideComposer();

    const anchorText = anchor && anchor.selector
      ? (anchor.selector.find(s => s.type === 'TextQuoteSelector') || {}).exact || ''
      : '';

    const wrapper = document.createElement('div');
    wrapper.className = 'paa-composer';
    wrapper.innerHTML = `
      ${anchorText ? `<blockquote class="paa-composer-quote">${_esc(anchorText.slice(0, 200))}</blockquote>` : ''}
      <form class="paa-composer-form">
        <textarea class="paa-composer-textarea" placeholder="Add your annotation…" required rows="3" autofocus></textarea>
        <div class="paa-composer-actions">
          <button type="submit" class="paa-btn paa-btn-primary">Post</button>
          <button type="button" class="paa-btn paa-composer-cancel">Cancel</button>
        </div>
      </form>
    `;

    const form = wrapper.querySelector('form');
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const body = form.querySelector('textarea').value.trim();
      if (!body) return;
      const btn = form.querySelector('[type="submit"]');
      btn.disabled = true;
      try {
        await _callbacks.onSubmitNew(body);
      } finally {
        btn.disabled = false;
      }
      hideComposer();
    });

    wrapper.querySelector('.paa-composer-cancel').addEventListener('click', () => {
      hideComposer();
      _callbacks.onCancelNew();
      // Return focus to first filter chip as fallback
      const firstChip = _controlsEl && _controlsEl.querySelector('.paa-chip');
      if (firstChip) firstChip.focus();
    });

    _composerEl = wrapper;
    _sidebarEl.insertBefore(wrapper, _sidebarEl.firstChild);
    wrapper.querySelector('textarea').focus();
  }

  function hideComposer() {
    if (_composerEl) {
      _composerEl.remove();
      _composerEl = null;
    }
  }

  // ---------------------------------------------------------------------------
  // Card builder
  // ---------------------------------------------------------------------------

  function _buildCard(anno) {
    const isResolved = !!anno.resolved_at;
    const isFeatured = !!anno.featured_at;
    const isOrphaned = !!anno.orphaned_at;

    const card = document.createElement('article');
    card.className = 'proposal-annotation-card';
    card.dataset.annoId = anno.id;
    card.dataset.status = isResolved ? 'resolved' : 'open';
    card.dataset.featured = isFeatured ? 'true' : 'false';
    card.dataset.orphaned = isOrphaned ? 'true' : 'false';
    card.tabIndex = 0;

    // Header
    const head = document.createElement('header');
    head.className = 'paa-card-head';
    const isOwnAnnotation = _currentUser && anno.author?.id === _currentUser.id;
    head.innerHTML = `
      <div class="paa-author-ts">
        <span class="paa-author">${_esc(anno.author?.display_name || 'Unknown')}</span>
        ${isOwnAnnotation ? '<span class="paa-you-tag">You · Author</span>' : ''}
        <time class="paa-ts">${_timeAgo(anno.created_at)}</time>
      </div>
      <div class="paa-tags">
        <span class="paa-featured-tag"${isFeatured ? '' : ' hidden'}>Featured</span>
        <span class="paa-resolved-tag"${isResolved ? '' : ' hidden'}>Resolved</span>
        <span class="paa-orphaned-tag"${isOrphaned ? '' : ' hidden'}>Anchor changed</span>
      </div>
    `;

    if (anno.can_moderate || anno.can_feature) {
      const menuBtn = document.createElement('button');
      menuBtn.className = 'paa-menu-btn';
      menuBtn.setAttribute('aria-label', 'Actions');
      menuBtn.textContent = '⋯';
      menuBtn.dataset.action = 'menu';
      menuBtn.dataset.annoId = anno.id;
      menuBtn.dataset.isFeatured = isFeatured ? 'true' : 'false';
      menuBtn.dataset.canFeature = anno.can_feature ? 'true' : 'false';
      menuBtn.dataset.canModerate = anno.can_moderate ? 'true' : 'false';
      head.querySelector('.paa-author-ts').appendChild(menuBtn);
    }

    card.appendChild(head);

    // Orphan original text — show quoted passage above body
    if (isOrphaned) {
      const quoteSelector = anno.anchor_data?.selector?.find(s => s.type === 'TextQuoteSelector');
      if (quoteSelector && quoteSelector.exact) {
        const orphanQuote = document.createElement('blockquote');
        orphanQuote.className = 'paa-orphan-original-text';
        orphanQuote.textContent = 'Originally annotated: "' + quoteSelector.exact.slice(0, 200) + '"';
        card.appendChild(orphanQuote);
      }
    } else if (anno.anchor_data && anno.anchor_data.selector) {
      // Live anchor quote for non-orphaned annotations
      const quoteSelector = anno.anchor_data.selector.find(s => s.type === 'TextQuoteSelector');
      if (quoteSelector && quoteSelector.exact) {
        const quote = document.createElement('blockquote');
        quote.className = 'paa-anchor-quote';
        quote.textContent = quoteSelector.exact.slice(0, 200);
        card.appendChild(quote);
      }
    }

    // Body
    const body = document.createElement('div');
    body.className = 'paa-body';
    body.textContent = anno.body || '';
    card.appendChild(body);

    // Footer actions
    const footer = document.createElement('footer');
    footer.className = 'paa-card-actions';

    const endorseCount = anno.reactions?.endorse || 0;
    const needsWorkCount = anno.reactions?.needs_work || 0;
    const myReaction = anno.my_reaction;

    footer.innerHTML = `
      <button class="paa-react${myReaction === 'endorse' ? ' is-active' : ''}"
              data-reaction="endorse" data-anno-id="${anno.id}"
              ${_isReadOnly || !_currentUser ? 'disabled' : ''}>
        ↑ Endorse <span class="paa-react-count">(${endorseCount})</span>
      </button>
      <button class="paa-react${myReaction === 'needs_work' ? ' is-active' : ''}"
              data-reaction="needs_work" data-anno-id="${anno.id}"
              ${_isReadOnly || !_currentUser ? 'disabled' : ''}>
        ↓ Needs work <span class="paa-react-count">(${needsWorkCount})</span>
      </button>
      ${!_isReadOnly && _currentUser ? `
        <button class="paa-reply-btn" data-anno-id="${anno.id}">Reply</button>
      ` : ''}
    `;
    card.appendChild(footer);

    // Resolve / Reopen on its own row
    if (anno.can_resolve && !_isReadOnly) {
      const resolveRow = document.createElement('div');
      resolveRow.className = 'paa-resolve-row';
      resolveRow.innerHTML = isResolved
        ? `<button class="paa-unresolve-btn" data-anno-id="${anno.id}">Reopen</button>`
        : `<button class="paa-resolve-btn" data-anno-id="${anno.id}">Resolve</button>`;
      card.appendChild(resolveRow);
    }

    // Nested replies
    if (anno.replies && anno.replies.length > 0) {
      const repliesList = document.createElement('ol');
      repliesList.className = 'paa-replies';
      for (const reply of anno.replies) {
        const replyItem = document.createElement('li');
        replyItem.appendChild(_buildReplyCard(reply));
        repliesList.appendChild(replyItem);
      }
      card.appendChild(repliesList);
    }

    // Inline reply form (hidden by default)
    if (!_isReadOnly && _currentUser) {
      const replyForm = document.createElement('form');
      replyForm.className = 'paa-reply-form';
      replyForm.hidden = true;
      replyForm.dataset.parentId = anno.id;
      replyForm.innerHTML = `
        <textarea required placeholder="Write a reply…" rows="2"></textarea>
        <div class="paa-reply-form-actions">
          <button type="submit" class="paa-btn paa-btn-primary">Post reply</button>
          <button type="button" class="paa-btn paa-reply-cancel">Cancel</button>
        </div>
        <p class="paa-reply-error" hidden></p>
      `;
      card.appendChild(replyForm);
    }

    // Card body click → scroll doc to highlight (skip if orphaned or clicking interactive elements)
    card.addEventListener('click', (e) => {
      if (e.target.closest('button, form, textarea, .paa-menu-dropdown, a')) return;
      if (card.dataset.orphaned === 'true') return;
      ProposalAnchor.scrollTo(anno.id);
    });

    return card;
  }

  function _buildReplyCard(anno) {
    const card = document.createElement('article');
    card.className = 'proposal-annotation-card paa-reply-card';
    card.dataset.annoId = anno.id;
    card.tabIndex = 0;

    const isOwnReply = _currentUser && anno.author?.id === _currentUser.id;
    card.innerHTML = `
      <header class="paa-card-head">
        <div class="paa-author-ts">
          <span class="paa-author">${_esc(anno.author?.display_name || 'Unknown')}</span>
          ${isOwnReply ? '<span class="paa-you-tag">You · Author</span>' : ''}
          <time class="paa-ts">${_timeAgo(anno.created_at)}</time>
        </div>
      </header>
      <div class="paa-body">${_esc(anno.body || '')}</div>
      ${!_isReadOnly && _currentUser ? `
        <footer class="paa-card-actions">
          <button class="paa-react${anno.my_reaction === 'endorse' ? ' is-active' : ''}"
                  data-reaction="endorse" data-anno-id="${anno.id}">
            Endorse · ${anno.reactions?.endorse || 0}
          </button>
          <button class="paa-react${anno.my_reaction === 'needs_work' ? ' is-active' : ''}"
                  data-reaction="needs_work" data-anno-id="${anno.id}">
            Needs work · ${anno.reactions?.needs_work || 0}
          </button>
        </footer>
      ` : ''}
    `;

    return card;
  }

  // ---------------------------------------------------------------------------
  // Event delegation
  // ---------------------------------------------------------------------------

  function _onSidebarClick(e) {
    const btn = e.target.closest(
      'button[data-action], button.paa-react, button.paa-reply-btn, ' +
      'button.paa-resolve-btn, button.paa-unresolve-btn, button.paa-menu-btn, button.paa-reply-cancel'
    );
    if (!btn) return;

    const annoId = btn.dataset.annoId;

    if (btn.classList.contains('paa-react')) {
      _callbacks.onReact(annoId, btn.dataset.reaction);
      return;
    }

    if (btn.classList.contains('paa-reply-btn')) {
      _toggleReplyForm(annoId, btn);
      return;
    }

    if (btn.classList.contains('paa-reply-cancel')) {
      const form = btn.closest('form.paa-reply-form');
      if (form) {
        form.hidden = true;
        // Return focus to the Reply button that opened this form
        const parentId = form.dataset.parentId;
        const replyBtn = _sidebarEl.querySelector(
          `.paa-reply-btn[data-anno-id="${CSS.escape(parentId)}"]`
        );
        if (replyBtn) replyBtn.focus();
      }
      return;
    }

    if (btn.classList.contains('paa-resolve-btn')) {
      btn.disabled = true;
      _callbacks.onResolve(annoId).catch(err => {
        btn.disabled = false;
        _showInlineError(btn, err?.message || 'Could not resolve annotation.');
      });
      return;
    }

    if (btn.classList.contains('paa-unresolve-btn')) {
      btn.disabled = true;
      _callbacks.onUnresolve(annoId).catch(err => {
        btn.disabled = false;
        _showInlineError(btn, err?.message || 'Could not reopen annotation.');
      });
      return;
    }

    if (btn.classList.contains('paa-menu-btn')) {
      _showMenu(btn);
      return;
    }
  }

  function _toggleReplyForm(parentId, replyBtn) {
    console.log('[reply] toggleReplyForm called, parentId=', parentId);
    const card = _sidebarEl.querySelector(
      `.proposal-annotation-card[data-anno-id="${CSS.escape(parentId)}"]`
    );
    if (!card) { console.log('[reply] card not found'); return; }
    const form = card.querySelector('form.paa-reply-form');
    if (!form) { console.log('[reply] form not found in card'); return; }
    form.hidden = !form.hidden;
    console.log('[reply] form.hidden=', form.hidden, 'wired=', form.dataset.wired);
    if (!form.hidden) {
      form.querySelector('textarea').focus();
      if (!form.dataset.wired) {
        form.dataset.wired = '1';
        form.addEventListener('submit', async (e) => {
          e.preventDefault();
          const body = form.querySelector('textarea').value.trim();
          console.log('[reply] submit fired, body length=', body.length, 'parentId=', parentId);
          if (!body) { console.log('[reply] body empty, aborting'); return; }
          const submitBtn = form.querySelector('[type="submit"]');
          const errorEl = form.querySelector('.paa-reply-error');
          submitBtn.disabled = true;
          if (errorEl) errorEl.hidden = true;
          try {
            console.log('[reply] calling onReply…');
            await _callbacks.onReply(parentId, body);
            console.log('[reply] onReply resolved OK');
            form.hidden = true;
            form.reset();
          } catch (err) {
            console.error('[reply] onReply threw:', err);
            if (errorEl) {
              errorEl.textContent = err?.message || 'Could not post reply.';
              errorEl.hidden = false;
            }
          } finally {
            submitBtn.disabled = false;
          }
        });
      }
    }
  }

  function _showInlineError(nearEl, message) {
    const existing = nearEl.parentElement?.querySelector('.paa-inline-error');
    if (existing) existing.remove();
    const err = document.createElement('span');
    err.className = 'paa-inline-error';
    err.textContent = message;
    nearEl.insertAdjacentElement('afterend', err);
    setTimeout(() => { if (err.parentElement) err.remove(); }, 5000);
  }

  function _showMenu(menuBtn) {
    document.querySelectorAll('.paa-menu-dropdown').forEach(el => el.remove());

    const annoId = menuBtn.dataset.annoId;
    const isFeatured = menuBtn.dataset.isFeatured === 'true';
    const canFeature = menuBtn.dataset.canFeature === 'true';
    const canModerate = menuBtn.dataset.canModerate === 'true';

    const menu = document.createElement('div');
    menu.className = 'paa-menu-dropdown';

    if (canFeature) {
      const featItem = document.createElement('button');
      featItem.className = 'paa-menu-item';
      featItem.textContent = isFeatured ? 'Unfeature' : 'Feature';
      featItem.addEventListener('click', () => {
        menu.remove();
        if (isFeatured) _callbacks.onUnfeature(annoId);
        else _callbacks.onFeature(annoId);
      });
      menu.appendChild(featItem);
    }

    if (canModerate) {
      const modItem = document.createElement('button');
      modItem.className = 'paa-menu-item danger';
      modItem.textContent = 'Hide…';
      modItem.addEventListener('click', () => {
        menu.remove();
        const anno = _annotationsMap[annoId];
        if (anno) showModerateModal(anno, menuBtn);
      });
      menu.appendChild(modItem);
    }

    if (!menu.children.length) return;

    const rect = menuBtn.getBoundingClientRect();
    const scrollY = window.scrollY || window.pageYOffset;
    menu.style.position = 'absolute';
    menu.style.top = (rect.bottom + scrollY + 4) + 'px';
    menu.style.left = rect.left + 'px';
    menu.style.zIndex = '300';

    document.body.appendChild(menu);

    setTimeout(() => {
      document.addEventListener('click', function closeMenu(e) {
        if (!menu.contains(e.target)) {
          menu.remove();
          document.removeEventListener('click', closeMenu);
        }
      });
    }, 0);
  }

  // ---------------------------------------------------------------------------
  // Moderation modal
  // ---------------------------------------------------------------------------

  /**
   * Show the moderation modal for a given annotation.
   * @param {Object}  annotation  - Full annotation object from _annotationsMap
   * @param {Element} [triggerEl] - The ⋯ menu button (for focus return on close)
   */
  function showModerateModal(annotation, triggerEl) {
    hideModerateModal();

    _modalAnnoId = annotation.id;
    _modalTriggerEl = triggerEl || _sidebarEl.querySelector(
      `.paa-menu-btn[data-anno-id="${CSS.escape(annotation.id)}"]`
    );

    const authorName = annotation.author?.display_name || 'Unknown';
    const bodyFull = annotation.body || '';
    const bodyPreview = bodyFull.slice(0, 120) + (bodyFull.length > 120 ? '…' : '');

    _modalEl = document.createElement('div');
    _modalEl.className = 'paa-modal-backdrop';
    _modalEl.setAttribute('role', 'dialog');
    _modalEl.setAttribute('aria-modal', 'true');
    _modalEl.setAttribute('aria-labelledby', 'paa-modal-title');
    _modalEl.innerHTML = `
      <div class="paa-modal">
        <header class="paa-modal-head">
          <h3 id="paa-modal-title" class="paa-modal-title">Hide annotation</h3>
          <button class="paa-modal-close" aria-label="Cancel">×</button>
        </header>
        <div class="paa-modal-body">
          <p class="paa-modal-context">
            From <strong>${_esc(authorName)}</strong>:
            <span class="paa-modal-quote">${_esc(bodyPreview)}</span>
          </p>
          <label class="paa-modal-label" for="paa-modal-reason">
            Reason for hiding (required, visible in audit log)
          </label>
          <textarea id="paa-modal-reason" class="paa-modal-reason"
                    minlength="10" maxlength="500"
                    placeholder="Why is this annotation being hidden?"
                    required></textarea>
          <p class="paa-modal-counter" aria-live="polite">0 / 500 — minimum 10 characters</p>
          <p class="paa-modal-error" hidden></p>
        </div>
        <footer class="paa-modal-foot">
          <button class="paa-btn-ghost paa-modal-cancel">Cancel</button>
          <button class="paa-btn-danger paa-modal-submit" disabled>Hide annotation</button>
        </footer>
      </div>
    `;

    document.body.appendChild(_modalEl);

    const textarea = _modalEl.querySelector('#paa-modal-reason');
    const counter = _modalEl.querySelector('.paa-modal-counter');
    const submitBtn = _modalEl.querySelector('.paa-modal-submit');
    const errorEl = _modalEl.querySelector('.paa-modal-error');

    textarea.addEventListener('input', () => {
      const len = textarea.value.length;
      const valid = len >= 10 && len <= 500;
      counter.textContent = `${len} / 500`;
      counter.classList.toggle('is-invalid', !valid);
      submitBtn.disabled = !valid;
    });

    _modalEl.addEventListener('click', (e) => {
      if (e.target === _modalEl) hideModerateModal();
    });

    _modalEl.querySelector('.paa-modal-close').addEventListener('click', hideModerateModal);
    _modalEl.querySelector('.paa-modal-cancel').addEventListener('click', hideModerateModal);

    submitBtn.addEventListener('click', async () => {
      const reason = textarea.value.trim();
      if (reason.length < 10) return;
      submitBtn.disabled = true;
      errorEl.hidden = true;
      try {
        await _callbacks.onModerate(_modalAnnoId, reason);
        hideModerateModal();
      } catch (err) {
        errorEl.textContent = 'Failed to hide annotation. Please try again.';
        errorEl.hidden = false;
        submitBtn.disabled = false;
      }
    });

    // Focus trap + Escape
    _modalKeydownHandler = (e) => {
      if (e.key === 'Escape') { hideModerateModal(); return; }
      if (e.key === 'Tab') {
        const focusable = Array.from(_modalEl.querySelectorAll(
          'button:not([disabled]), textarea, [tabindex="0"]'
        ));
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault(); last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault(); first.focus();
        }
      }
    };
    document.addEventListener('keydown', _modalKeydownHandler);

    textarea.focus();
  }

  function hideModerateModal() {
    if (_modalKeydownHandler) {
      document.removeEventListener('keydown', _modalKeydownHandler);
      _modalKeydownHandler = null;
    }
    if (_modalEl) {
      _modalEl.remove();
      _modalEl = null;
    }
    // Return focus to the ⋯ button, or fall back to first filter chip
    if (_modalTriggerEl) {
      _modalTriggerEl.focus();
      _modalTriggerEl = null;
    } else {
      const firstChip = _controlsEl && _controlsEl.querySelector('.paa-chip');
      if (firstChip) firstChip.focus();
    }
    _modalAnnoId = null;
  }

  // ---------------------------------------------------------------------------
  // Scroll to card / focus card
  // ---------------------------------------------------------------------------

  /**
   * Scroll the sidebar so the card for the given annotation is visible, and flash it.
   * @param {string} annotationId
   */
  function scrollToCard(annotationId) {
    const card = _sidebarEl.querySelector(
      `.proposal-annotation-card[data-anno-id="${CSS.escape(annotationId)}"]`
    );
    if (card) {
      card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      card.classList.add('paa-card-flash');
      setTimeout(() => card.classList.remove('paa-card-flash'), 600);
    }
  }

  /**
   * Scroll to and focus the card for a given annotation ID.
   * Used after creating a new annotation or reply.
   * @param {string} annotationId
   */
  function focusCard(annotationId) {
    if (!annotationId) return;
    const card = _sidebarEl.querySelector(
      `.proposal-annotation-card[data-anno-id="${CSS.escape(annotationId)}"]`
    );
    if (card) {
      card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      card.focus();
    }
  }

  // ---------------------------------------------------------------------------
  // Utilities
  // ---------------------------------------------------------------------------

  function _esc(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function _timeAgo(iso) {
    if (!iso) return '';
    if (typeof timeAgo === 'function') return timeAgo(iso);
    const diff = Date.now() - new Date(iso).getTime();
    const m = Math.floor(diff / 60000);
    if (m < 1) return 'just now';
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    return `${Math.floor(h / 24)}d ago`;
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  window.ProposalAnnotationUI = {
    init,
    render,
    renderLoading,
    renderError,
    showComposer,
    hideComposer,
    scrollToCard,
    focusCard,
    showModerateModal,
    hideModerateModal,
  };

})();
