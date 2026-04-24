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
      renderSignals(signals, mySignal);
      renderComments(comments);
      setupCommentForm();
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
    document.getElementById('pr-crumb').textContent =
      `${slug} › Thread › Proposal`;
    const phaseBadge = document.getElementById('pr-phase');
    phaseBadge.textContent = capitalize(thread.status || '');
    document.getElementById('pr-title').textContent = p.title;
    const authorName = p.created_by?.display_name || 'Unknown';
    document.getElementById('pr-meta').textContent =
      `by ${authorName} · v${p.current_version_number || 1} · ${timeAgo(p.created_at)}`;
    document.getElementById('pr-back').href = `/c/${slug}/thread/${threadId}`;
    document.title = `${p.title} · Proposal review`;
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
  // Utilities
  // ----------------------------------------------------------------

  function capitalize(s) {
    return s ? s[0].toUpperCase() + s.slice(1) : '';
  }

  load();
})();
