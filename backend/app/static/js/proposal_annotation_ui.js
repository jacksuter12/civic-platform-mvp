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
  let _callbacks = {};
  let _composerEl = null;

  // ---------------------------------------------------------------------------
  // Init
  // ---------------------------------------------------------------------------

  /**
   * @param {{
   *   sidebarEl:    Element,
   *   docEl:        Element,
   *   currentUser:  {id, display_name} | null,
   *   isReadOnly:   boolean,
   *   onReact, onReply, onResolve, onUnresolve, onFeature, onUnfeature,
   *   onModerate, onSubmitNew, onCancelNew
   * }} config
   */
  function init(config) {
    _sidebarEl = config.sidebarEl;
    _docEl = config.docEl;
    _currentUser = config.currentUser;
    _isReadOnly = config.isReadOnly;
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

    // Keep composer if it's currently open (user is typing)
    const composerOpen = _composerEl && _sidebarEl.contains(_composerEl);

    // Clear sidebar
    _sidebarEl.innerHTML = '';

    if (composerOpen && _composerEl) {
      _sidebarEl.appendChild(_composerEl);
    }

    if (!annotations || annotations.length === 0) {
      if (!composerOpen) {
        const empty = document.createElement('div');
        empty.className = 'paa-empty';
        empty.textContent = _isReadOnly
          ? 'No annotations on this proposal.'
          : 'Select text in the proposal to add an annotation.';
        _sidebarEl.appendChild(empty);
      }
      return;
    }

    for (const anno of annotations) {
      _sidebarEl.appendChild(_buildCard(anno, false));
    }
  }

  // ---------------------------------------------------------------------------
  // Composer
  // ---------------------------------------------------------------------------

  /**
   * Show the top-level composer, replacing any empty state in the sidebar.
   * @param {Object}  anchor      - The pending anchor object
   * @param {Object}  [opts]      - { replyTo: annotationId | null }
   */
  function showComposer(anchor, opts) {
    if (opts && opts.replyTo) {
      // Reply composer is shown inline in the card — handled in _buildCard
      return;
    }

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

  function _buildCard(anno, isReply) {
    const isResolved = !!anno.resolved_at;
    const isFeatured = !!anno.featured_at;
    const isOrphaned = !!anno.orphaned_at;

    const card = document.createElement('article');
    card.className = 'proposal-annotation-card' + (isReply ? ' paa-reply-card' : '');
    card.dataset.annoId = anno.id;
    card.dataset.status = isResolved ? 'resolved' : 'open';
    card.dataset.featured = isFeatured ? 'true' : 'false';
    card.dataset.orphaned = isOrphaned ? 'true' : 'false';

    // Header
    const head = document.createElement('header');
    head.className = 'paa-card-head';
    head.innerHTML = `
      <span class="paa-author">${_esc(anno.author?.display_name || 'Unknown')}</span>
      <time class="paa-ts">${_timeAgo(anno.created_at)}</time>
      <span class="paa-featured-tag"${isFeatured ? '' : ' hidden'}>Featured</span>
      <span class="paa-resolved-tag"${isResolved ? '' : ' hidden'}>Resolved</span>
      <span class="paa-orphaned-tag"${isOrphaned ? '' : ' hidden'}>Anchor changed</span>
    `;

    // Action menu button (for moderators/facilitators)
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
      head.appendChild(menuBtn);
    }

    card.appendChild(head);

    // Anchor quote (only for top-level annotations with quote selectors)
    if (!isReply && anno.anchor_data && anno.anchor_data.selector) {
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
    if (!isReply) {
      const footer = document.createElement('footer');
      footer.className = 'paa-card-actions';

      const endorseCount = anno.reactions?.endorse || 0;
      const needsWorkCount = anno.reactions?.needs_work || 0;
      const myReaction = anno.my_reaction;

      footer.innerHTML = `
        <button class="paa-react${myReaction === 'endorse' ? ' is-active' : ''}"
                data-reaction="endorse" data-anno-id="${anno.id}"
                ${_isReadOnly || !_currentUser ? 'disabled' : ''}>
          Endorse · ${endorseCount}
        </button>
        <button class="paa-react${myReaction === 'needs_work' ? ' is-active' : ''}"
                data-reaction="needs_work" data-anno-id="${anno.id}"
                ${_isReadOnly || !_currentUser ? 'disabled' : ''}>
          Needs work · ${needsWorkCount}
        </button>
        ${!_isReadOnly && _currentUser ? `
          <button class="paa-reply-btn" data-anno-id="${anno.id}">Reply</button>
        ` : ''}
        ${anno.can_resolve && !isResolved && !_isReadOnly ? `
          <button class="paa-resolve-btn" data-anno-id="${anno.id}">Resolve</button>
        ` : ''}
        ${anno.can_resolve && isResolved && !_isReadOnly ? `
          <button class="paa-unresolve-btn" data-anno-id="${anno.id}">Reopen</button>
        ` : ''}
      `;
      card.appendChild(footer);
    }

    // Nested replies
    if (!isReply && anno.replies && anno.replies.length > 0) {
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
    if (!isReply && !_isReadOnly && _currentUser) {
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
      `;
      card.appendChild(replyForm);
    }

    // Clicking the card body (outside buttons) scrolls to the highlight
    card.addEventListener('click', (e) => {
      if (e.target.closest('button, form, textarea')) return;
      ProposalAnchor.scrollTo(anno.id);
    });

    return card;
  }

  function _buildReplyCard(anno) {
    const card = document.createElement('article');
    card.className = 'proposal-annotation-card paa-reply-card';
    card.dataset.annoId = anno.id;

    card.innerHTML = `
      <header class="paa-card-head">
        <span class="paa-author">${_esc(anno.author?.display_name || 'Unknown')}</span>
        <time class="paa-ts">${_timeAgo(anno.created_at)}</time>
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
    const btn = e.target.closest('button[data-action], button.paa-react, button.paa-reply-btn, button.paa-resolve-btn, button.paa-unresolve-btn, button.paa-menu-btn, button.paa-reply-cancel');
    if (!btn) return;

    const annoId = btn.dataset.annoId;

    if (btn.classList.contains('paa-react')) {
      const reactionType = btn.dataset.reaction;
      _callbacks.onReact(annoId, reactionType);
      return;
    }

    if (btn.classList.contains('paa-reply-btn')) {
      _toggleReplyForm(annoId);
      return;
    }

    if (btn.classList.contains('paa-reply-cancel')) {
      const form = btn.closest('form.paa-reply-form');
      if (form) form.hidden = true;
      return;
    }

    if (btn.classList.contains('paa-resolve-btn')) {
      _callbacks.onResolve(annoId);
      return;
    }

    if (btn.classList.contains('paa-unresolve-btn')) {
      _callbacks.onUnresolve(annoId);
      return;
    }

    if (btn.classList.contains('paa-menu-btn')) {
      _showMenu(btn);
      return;
    }
  }

  function _toggleReplyForm(parentId) {
    const card = _sidebarEl.querySelector(`[data-anno-id="${CSS.escape(parentId)}"]`);
    if (!card) return;
    const form = card.querySelector('form.paa-reply-form');
    if (!form) return;
    form.hidden = !form.hidden;
    if (!form.hidden) {
      form.querySelector('textarea').focus();
      // Wire submit if not already wired
      if (!form.dataset.wired) {
        form.dataset.wired = '1';
        form.addEventListener('submit', async (e) => {
          e.preventDefault();
          const body = form.querySelector('textarea').value.trim();
          if (!body) return;
          const btn = form.querySelector('[type="submit"]');
          btn.disabled = true;
          try {
            await _callbacks.onReply(parentId, body);
          } finally {
            btn.disabled = false;
          }
          form.hidden = true;
          form.reset();
        });
      }
    }
  }

  function _showMenu(menuBtn) {
    // Remove any existing menu
    document.querySelectorAll('.paa-menu-dropdown').forEach(el => el.remove());

    const annoId = menuBtn.dataset.annoId;
    const isFeatured = menuBtn.dataset.isFeatured === 'true';
    const canFeature = menuBtn.dataset.canFeature === 'true';
    const canModerate = menuBtn.dataset.canModerate === 'true';

    const menu = document.createElement('div');
    menu.className = 'paa-menu-dropdown';

    if (canFeature) {
      const featItem = document.createElement('button');
      featItem.textContent = isFeatured ? 'Unfeature' : 'Feature';
      featItem.addEventListener('click', () => {
        menu.remove();
        if (isFeatured) {
          _callbacks.onUnfeature(annoId);
        } else {
          _callbacks.onFeature(annoId);
        }
      });
      menu.appendChild(featItem);
    }

    if (canModerate) {
      const modItem = document.createElement('button');
      modItem.textContent = 'Moderate (remove)';
      modItem.className = 'paa-menu-item-danger';
      modItem.addEventListener('click', () => {
        menu.remove();
        _callbacks.onModerate(annoId);
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

    // Close when clicking elsewhere
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
  // Scroll to card
  // ---------------------------------------------------------------------------

  /**
   * Scroll the sidebar so the card for the given annotation is visible.
   * @param {string} annotationId
   */
  function scrollToCard(annotationId) {
    const card = _sidebarEl.querySelector(`[data-anno-id="${CSS.escape(annotationId)}"]`);
    if (card) {
      card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      card.classList.add('paa-card-flash');
      setTimeout(() => card.classList.remove('paa-card-flash'), 600);
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
    // Minimal fallback
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
    showComposer,
    hideComposer,
    scrollToCard,
  };

})();
