/**
 * proposal_review.js — Orchestrator for /c/{slug}/thread/{tid}/proposal/{pid}.
 *
 * Reads URL segments, loads data in parallel, assembles UI.
 * All fetch() calls go through api.js. All DOM manipulation is here.
 */

(function () {
  'use strict';

  const parts = window.location.pathname.split('/');
  // /c/{slug}/thread/{threadId}/proposal/{proposalId}
  //  0  1  2    3      4    5       6          7
  const slug      = parts[2];
  const threadId  = parts[4];
  const proposalId = parts[6];

  const SIG_META = [
    { type: 'support',   label: 'Support',   icon: '↑' },
    { type: 'concern',   label: 'Concern',   icon: '↓' },
    { type: 'need_info', label: 'Need info', icon: '?' },
    { type: 'block',     label: 'Block',     icon: '✕' },
  ];

  // ----------------------------------------------------------------
  // Bootstrap
  // ----------------------------------------------------------------

  async function load() {
    try {
      const loadPromises = [
        getProposal(proposalId),
        getThread(threadId),
        getProposalComments(proposalId),
        fetchSignalsForTarget('proposal', proposalId),
      ];
      if (auth.isSignedIn()) {
        loadPromises.push(fetchMySignalForTarget('proposal', proposalId));
      } else {
        loadPromises.push(Promise.resolve(null));
      }

      const [proposal, thread, comments, signals, mySignal] = await Promise.all(loadPromises);

      renderHeader(proposal, thread);
      renderDoc(proposal);
      initTOC();
      initAnnoToggle();
      renderSignals(signals, mySignal);
      renderComments(comments);
      setupCommentForm();

      // Annotation system — init after doc is rendered so anchors can be found
      const currentUser = auth.isSignedIn() ? auth.getUser() : null;
      const userRole = _computeUserRole(currentUser, proposal, slug);
      await ProposalAnnotations.init({
        proposalId: proposal.id,
        threadStatus: thread.status,
        docEl: document.getElementById('pr-doc'),
        sidebarEl: document.getElementById('pr-anno-list'),
        headerCountEl: document.getElementById('pr-anno-count'),
        currentUser: currentUser ? { id: currentUser.id, display_name: currentUser.display_name } : null,
        userRole,
      });
    } catch (err) {
      console.error(err);
      document.getElementById('pr-doc').innerHTML =
        '<div class="pr-doc-error">Could not load proposal.</div>';
    }
  }

  // ----------------------------------------------------------------
  // Header
  // ----------------------------------------------------------------

  function renderHeader(p, thread) {
    document.getElementById('pr-crumb').innerHTML =
      `<a href="/c/${slug}">${esc(slug)}</a> › <a href="/c/${slug}/thread/${threadId}">${esc(thread.title || 'Thread')}</a> › Proposal`;
    const phaseBadge = document.getElementById('pr-phase');
    phaseBadge.textContent = capitalize(thread.status || '');
    document.getElementById('pr-title').textContent = p.title;
    const authorName = p.created_by?.display_name || 'Unknown';
    document.getElementById('pr-meta').textContent =
      `by ${authorName} · v${p.current_version_number || 1} · ${timeAgo(p.created_at)}`;
    document.getElementById('pr-back').href = `/c/${slug}/thread/${threadId}`;
    document.title = `${p.title} · Proposal review`;

    if (p.can_edit) {
      const editBtn = document.getElementById('pr-edit-btn');
      editBtn.hidden = false;
      editBtn.addEventListener('click', (e) => { e.preventDefault(); enterEditMode(p); });
    }

    if (p.can_delete) {
      const deleteBtn = document.getElementById('pr-delete-btn');
      deleteBtn.hidden = false;
      deleteBtn.addEventListener('click', (e) => { e.preventDefault(); _showDeleteModal(p); });
    }
  }

  // ----------------------------------------------------------------
  // Delete modal
  // ----------------------------------------------------------------

  function _showDeleteModal(proposal) {
    const overlay = document.createElement('div');
    overlay.className = 'paa-modal-backdrop';
    overlay.innerHTML = `
      <div class="paa-modal" role="dialog" aria-modal="true" aria-labelledby="pr-del-title">
        <header class="paa-modal-head">
          <span id="pr-del-title" class="paa-modal-title">Delete this proposal?</span>
        </header>
        <div class="paa-modal-body">
          <p>This will remove the proposal from the thread. The deletion will be recorded
          in the audit log. This action cannot be undone from the UI.</p>
        </div>
        <footer class="paa-modal-foot">
          <button id="pr-del-cancel" class="paa-btn-ghost" autofocus>Cancel</button>
          <button id="pr-del-confirm" class="paa-btn-danger">Delete proposal</button>
        </footer>
      </div>`;
    document.body.appendChild(overlay);

    const close = () => overlay.remove();
    overlay.querySelector('#pr-del-cancel').addEventListener('click', close);
    overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });

    overlay.querySelector('#pr-del-confirm').addEventListener('click', async () => {
      const confirmBtn = overlay.querySelector('#pr-del-confirm');
      confirmBtn.disabled = true;
      try {
        await deleteProposal(proposal.id);
        window.location.href = `/c/${slug}/thread/${threadId}`;
      } catch (err) {
        confirmBtn.disabled = false;
        alert('Could not delete proposal: ' + err.message);
      }
    });
  }

  // ----------------------------------------------------------------
  // Inline edit mode
  // ----------------------------------------------------------------

  let _editorInstance = null;
  let _docOriginalHtml = null;

  function enterEditMode(proposal) {
    if (_editorInstance) return;
    const docEl = document.getElementById('pr-doc');
    _docOriginalHtml = docEl.innerHTML;
    docEl.innerHTML = '<div id="pr-edit-mount"></div>';

    _editorInstance = window.ProposalEditor.mount(
      document.getElementById('pr-edit-mount'),
      {
        initialTitle: proposal.title,
        initialBody: proposal.description,
        showTitle: true,
        showEditSummary: true,
        submitLabel: 'Save changes',
        onSubmit: async ({ body, title, edit_summary }) => {
          const updated = await editProposal(proposal.id, title || proposal.title, body, edit_summary);
          exitEditMode();
          document.getElementById('pr-doc').innerHTML = updated.body_html;
          Toc.init({
            containerEl: document.getElementById('pr-toc-nav'),
            sourceEl:    document.getElementById('pr-doc'),
          });
          if (window.ProposalAnnotations?.reload) {
            await window.ProposalAnnotations.reload();
          }
          Object.assign(proposal, updated);
          // Update header elements that aren't re-rendered
          document.getElementById('pr-title').textContent = proposal.title;
          document.title = `${proposal.title} · Proposal review`;
          document.getElementById('pr-meta').textContent =
            `by ${proposal.created_by?.display_name || 'Unknown'} · v${proposal.current_version_number || 1} · ${timeAgo(proposal.created_at)}`;
        },
        onCancel: () => exitEditMode(),
      }
    );
    document.getElementById('pr-toc')?.classList.add('is-muted-edit');
    document.getElementById('pr-anno')?.classList.add('is-muted-edit');
  }

  function exitEditMode() {
    if (!_editorInstance) return;
    _editorInstance.destroy();
    _editorInstance = null;
    const docEl = document.getElementById('pr-doc');
    if (_docOriginalHtml !== null) {
      docEl.innerHTML = _docOriginalHtml;
      _docOriginalHtml = null;
    }
    document.getElementById('pr-toc')?.classList.remove('is-muted-edit');
    document.getElementById('pr-anno')?.classList.remove('is-muted-edit');
  }

  // ----------------------------------------------------------------
  // Document
  // ----------------------------------------------------------------

  function renderDoc(p) {
    const doc = document.getElementById('pr-doc');
    if (p.body_html) {
      doc.innerHTML = p.body_html;
    } else {
      // Fallback: plain-text description when body_html not yet populated
      doc.innerHTML = `<p>${esc(p.description)}</p>`;
    }
  }

  // ----------------------------------------------------------------
  // TOC
  // ----------------------------------------------------------------

  function initTOC() {
    const toggleBtn = document.getElementById('pr-toc-toggle');
    Toc.init({
      containerEl: document.getElementById('pr-toc-nav'),
      sourceEl:    document.getElementById('pr-doc'),
    });
    toggleBtn.addEventListener('click', () => {
      Toc.toggle();
      toggleBtn.textContent = Toc.isOpen ? 'Hide contents' : 'Show contents';
      toggleBtn.setAttribute('aria-pressed', String(Toc.isOpen));
    });
  }

  // ----------------------------------------------------------------
  // Annotation sidebar toggle
  // ----------------------------------------------------------------

  function initAnnoToggle() {
    const toggleBtn = document.getElementById('pr-anno-toggle');
    if (!toggleBtn) return;
    toggleBtn.addEventListener('click', () => {
      const anno = document.getElementById('pr-anno');
      const body = document.getElementById('pr-body');
      if (!anno || !body) return;
      const isOpen = anno.classList.toggle('is-open');
      body.classList.toggle('anno-hidden', !isOpen);
      toggleBtn.textContent = isOpen ? 'Hide annotations' : 'Show annotations';
      toggleBtn.setAttribute('aria-pressed', String(isOpen));
    });
  }

  // ----------------------------------------------------------------
  // Signals
  // ----------------------------------------------------------------

  function renderSignals(signals, mySignal) {
    const container = document.getElementById('pr-signal-buttons');
    container.innerHTML = '';
    const signedIn = auth.isSignedIn();

    SIG_META.forEach(m => {
      const isChosen = mySignal && mySignal.signal_type === m.type;
      const btn = document.createElement('button');
      btn.className = 'pr-sig-btn' + (isChosen ? ' is-chosen' : '');
      btn.dataset.signalType = m.type;
      btn.textContent = `${m.icon} ${m.label} (${signals[m.type] || 0})`;
      btn.title = isChosen
        ? `Click to remove your ${m.label} signal`
        : m.label;
      if (!signedIn) {
        btn.disabled = true;
        btn.title = 'Sign in to cast a signal';
      }
      btn.addEventListener('click', () => castSignalUI(m.type, mySignal));
      container.appendChild(btn);
    });

    renderDist(signals);
  }

  function renderDist(signals) {
    const dist = document.getElementById('pr-signal-dist');
    const total = SIG_META.reduce((sum, m) => sum + (signals[m.type] || 0), 0);
    if (total === 0) {
      dist.innerHTML = '<span class="pr-sig-none">No signals yet.</span>';
      return;
    }
    dist.innerHTML = SIG_META
      .filter(m => signals[m.type] > 0)
      .map(m => `<span class="pr-sig-chip" data-type="${m.type}">${m.icon} ${signals[m.type]}</span>`)
      .join('');
  }

  async function castSignalUI(signalType, currentMySignal) {
    try {
      if (currentMySignal && currentMySignal.signal_type === signalType) {
        await removeSignal('proposal', proposalId);
      } else {
        await castSignal('proposal', proposalId, signalType);
      }
      const [signals, mySignal] = await Promise.all([
        fetchSignalsForTarget('proposal', proposalId),
        fetchMySignalForTarget('proposal', proposalId),
      ]);
      renderSignals(signals, mySignal);
    } catch (err) {
      console.error(err);
      alert('Could not cast signal: ' + err.message);
    }
  }

  // ----------------------------------------------------------------
  // Comments
  // ----------------------------------------------------------------

  function renderComments(comments) {
    const list = document.getElementById('pr-comments-list');
    if (!comments || comments.length === 0) {
      list.innerHTML = '<div class="pr-comments-empty">No comments yet.</div>';
      return;
    }
    list.innerHTML = comments.map(c => `
      <div class="pr-comment">
        <div class="pr-comment-header">
          <span class="pr-comment-author">${esc(c.author?.display_name || 'Unknown')}</span>
          <span class="pr-comment-time">${timeAgo(c.created_at)}</span>
        </div>
        <div class="pr-comment-body">${esc(c.body)}</div>
      </div>`).join('');
  }

  function setupCommentForm() {
    const form = document.getElementById('pr-comments-form');
    if (!auth.isSignedIn()) {
      form.innerHTML = '<p style="font-size:13px;color:#888"><a href="/signin">Sign in</a> to post a comment.</p>';
      return;
    }
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const body = form.querySelector('textarea[name="body"]').value.trim();
      const errorEl = document.getElementById('pr-comment-error');
      errorEl.textContent = '';
      if (!body) return;
      const submitBtn = form.querySelector('button[type="submit"]');
      submitBtn.disabled = true;
      try {
        const newComment = await createProposalComment(proposalId, body);
        const list = document.getElementById('pr-comments-list');
        const emptyMsg = list.querySelector('.pr-comments-empty');
        if (emptyMsg) emptyMsg.remove();
        const item = document.createElement('div');
        item.className = 'pr-comment';
        item.innerHTML = `
          <div class="pr-comment-header">
            <span class="pr-comment-author">${esc(newComment.author?.display_name || 'You')}</span>
            <span class="pr-comment-time">just now</span>
          </div>
          <div class="pr-comment-body">${esc(newComment.body)}</div>`;
        list.appendChild(item);
        form.reset();
      } catch (err) {
        errorEl.textContent = err.message || 'Could not post comment.';
      } finally {
        submitBtn.disabled = false;
      }
    });
  }

  // ----------------------------------------------------------------
  // Role computation for annotation pane badge
  // ----------------------------------------------------------------

  function _computeUserRole(user, proposal, communitySlug) {
    if (!user) return null;
    if (user.id === proposal.created_by?.id) return 'author';
    const membership = (user.community_memberships || []).find(
      m => m.community_slug === communitySlug
    );
    if (!membership) return 'observer';
    const FACILITATOR_TIERS = ['facilitator', 'admin'];
    if (FACILITATOR_TIERS.includes(membership.tier)) return 'facilitator';
    return 'reviewer';
  }

  // ----------------------------------------------------------------
  // Utilities
  // ----------------------------------------------------------------

  function capitalize(s) {
    return s ? s[0].toUpperCase() + s.slice(1) : '';
  }

  load();
})();
