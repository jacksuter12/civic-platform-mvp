/**
 * thread.js — Full UI logic for the thread detail page.
 *
 * Architecture:
 *  - All fetch() calls in api.js. No network here.
 *  - All DOM here. No DOM in api.js.
 *  - Event delegation on document — survives innerHTML re-renders.
 *  - Signals batch-fetched after initial tree render.
 *  - One inline reply/comment form open at a time.
 *
 * Phase gates are enforced server-side. Client-side gates are
 * belt-and-suspenders only — never the sole enforcement point.
 */

// ===================================================================
// State
// ===================================================================

const S = {
  threadId:      null,
  communitySlug: null,
  thread:        null,
  me:            null,         // null if not signed in
  posts:         [],           // flat list from /posts/flat
  proposals:     [],
  pData:         {},           // proposalId → { comments: [], amendments: [] }
  signals:       {},           // "<type>:<id>" → SignalCountsOut
  collapsed:     new Set(),    // post IDs with collapsed subtree
  rootCollapsed: new Set(),    // root post IDs shown as summary-only
  openForm:      null,         // id of element currently hosting an inline form
};

// ===================================================================
// Pure utilities
// ===================================================================

function sigKey(type, id) { return `${type}:${id}`; }

function getSig(type, id) {
  return S.signals[sigKey(type, id)] || { support: 0, concern: 0, need_info: 0, block: 0, total: 0, my_signal: null };
}

/** Build { roots, childrenOf } from a flat post list. */
function buildTree(posts) {
  const childrenOf = {};
  const rootSet    = [];
  posts.forEach(p => {
    childrenOf[p.id] = [];
  });
  posts.forEach(p => {
    if (p.parent_id && childrenOf[p.parent_id]) {
      childrenOf[p.parent_id].push(p);
    } else {
      rootSet.push(p);
    }
  });
  return { roots: rootSet, childrenOf };
}

// ===================================================================
// Phase / tier helpers
// ===================================================================

const PHASE_SEQ = ["open", "deliberating", "proposing", "voting", "closed", "archived"];

function nextPhase(s) {
  const i = PHASE_SEQ.indexOf(s);
  return (i >= 0 && i < PHASE_SEQ.length - 1) ? PHASE_SEQ[i + 1] : null;
}

const canPost    = () => auth.hasTier("registered") && ["open", "deliberating"].includes(S.thread?.status);
const canSignal  = () => auth.isSignedIn();
const inProposing = () => S.thread?.status === "proposing";
const inVoting    = () => S.thread?.status === "voting";
const showProposals = () => ["proposing", "voting", "closed", "archived"].includes(S.thread?.status);

// ===================================================================
// Signal bar rendering
// ===================================================================

const SIG_META = [
  { type: "support",   label: "Agree",      icon: "↑" },
  { type: "concern",   label: "Disagree",  icon: "↓" },
  { type: "need_info", label: "Need Info", icon: "?" },
  { type: "block",     label: "Block",     icon: "✕" },
];

/**
 * Render a reusable signal bar for any target.
 * interactive=true → clickable buttons.
 * interactive=false → read-only count chips.
 */
function renderSignalBar(targetType, targetId, { interactive = false, showLabel = false } = {}) {
  const sig = getSig(targetType, targetId);
  const blockWarn = sig.block > 0
    ? `<span class="sig-block-warn" title="${sig.block} block${sig.block !== 1 ? "s" : ""} — strong unresolved objection">⚠ ${sig.block} block${sig.block !== 1 ? "s" : ""}</span>`
    : "";

  if (!interactive || !canSignal()) {
    // Read-only counts
    const chips = SIG_META
      .filter(m => sig[m.type] > 0)
      .map(m => `<span class="sig-chip sig-chip-${m.type}" title="${m.label}">${m.icon} ${sig[m.type]}</span>`)
      .join("");
    return `
      <div class="signal-bar-wrap" data-signal-bar data-target-type="${esc(targetType)}" data-target-id="${esc(targetId)}">
        <div class="sig-chips">${chips || '<span class="sig-none">no signals</span>'}</div>
        ${blockWarn}
      </div>`;
  }

  // Interactive buttons
  const btns = SIG_META.map(m => {
    const active = sig.my_signal === m.type;
    return `
      <button
        class="sig-btn sig-btn-${m.type}${active ? " sig-active" : ""}"
        data-action="${active ? "remove-signal" : "cast-signal"}"
        data-target-type="${esc(targetType)}"
        data-target-id="${esc(targetId)}"
        data-signal-type="${m.type}"
        title="${active ? "Click to remove your " + m.label + " signal" : m.label}"
      >${m.icon}${showLabel ? " " + m.label : ""} <span class="sig-count">${sig[m.type]}</span></button>`;
  }).join("");

  return `
    <div class="signal-bar-wrap" data-signal-bar data-target-type="${esc(targetType)}" data-target-id="${esc(targetId)}">
      <div class="sig-buttons">${btns}</div>
      ${blockWarn}
    </div>`;
}

// ===================================================================
// Post tree rendering
// ===================================================================

const DEPTH_COLORS = ["#bbb", "#7cb9e8", "#90be6d", "#f9c74f", "#f28482"];
const MAX_DEPTH    = 8;

function renderPost(post, depth, childrenOf, { maxDepth = MAX_DEPTH, commentMode = false } = {}) {
  const indent    = Math.min(depth * 16, 128);
  const borderClr = DEPTH_COLORS[depth % DEPTH_COLORS.length];

  const children = (childrenOf[post.id] || []);
  const hasReplies = children.length > 0;
  const isCollapsed = S.collapsed.has(post.id);

  // Removed posts: show tombstone but keep children
  const bodyHtml = post.is_removed
    ? `<div class="post-removed">[removed]</div>`
    : `<div class="post-body">${esc(post.body)}</div>`;

  const authorHtml = post.is_removed ? "" : `
    <span class="post-author">${esc(post.author?.display_name || "Unknown")}</span>
    <span class="post-time">${timeAgo(post.created_at)}</span>`;

  // Signal bar for this post
  const interactive = canSignal() && !commentMode;
  const sigBar = renderSignalBar(commentMode ? "proposal_comment" : "post", post.id, { interactive });

  // Reply button (posts only; only in allowed phases)
  const showReply = !commentMode && canPost() && depth < MAX_DEPTH;
  const atMaxDepth = !commentMode && depth >= MAX_DEPTH;
  const replyBtn = showReply
    ? `<button class="post-reply-btn" data-action="open-reply" data-post-id="${esc(post.id)}">Reply</button>`
    : atMaxDepth ? `<span class="max-depth-msg">Max depth reached</span>` : "";

  // Comment reply (comments only)
  const commentReplyBtn = commentMode && inProposing() && auth.hasTier("registered")
    ? `<button class="post-reply-btn" data-action="open-comment-reply" data-post-id="${esc(post.id)}" data-proposal-id="${esc(post.proposal_id)}">Reply</button>`
    : "";

  const actionsHtml = `<div class="post-actions">${replyBtn}${commentReplyBtn}</div>`;

  // Children toggle
  const toggleHtml = hasReplies ? `
    <button
      class="children-toggle"
      data-action="toggle-children"
      data-post-id="${esc(post.id)}"
    >${isCollapsed ? "▶" : "▼"} ${children.length} repl${children.length !== 1 ? "ies" : "y"}</button>` : "";

  // Render children (depth+1) — hidden if collapsed
  const childrenHtml = hasReplies
    ? `<div class="post-children" data-children-of="${esc(post.id)}"${isCollapsed ? ' style="display:none"' : ""}>
         ${children.map(c => renderPost(c, depth + 1, childrenOf, { maxDepth, commentMode })).join("")}
       </div>`
    : "";

  return `
    <div class="post-item post-depth-${Math.min(depth, 7)}" data-post-id="${esc(post.id)}" style="margin-left:${indent}px; border-left:2px solid ${borderClr}; padding-left:10px; margin-bottom:10px;">
      <div class="post-header">${authorHtml}</div>
      ${bodyHtml}
      ${sigBar}
      ${actionsHtml}
      <div class="reply-slot" data-reply-slot="${esc(post.id)}"></div>
      ${toggleHtml}
      ${childrenHtml}
    </div>`;
}

function renderRootPost(post, childrenOf) {
  const children = (childrenOf[post.id] || []);
  const totalReplies = countDescendants(post.id, childrenOf);
  const isRootCollapsed = S.rootCollapsed.has(post.id);

  if (isRootCollapsed) {
    const preview = post.is_removed ? "[removed]" : (post.body || "").slice(0, 100) + ((post.body || "").length > 100 ? "…" : "");
    return `
      <div class="post-root" data-root-id="${esc(post.id)}">
        <div class="post-root-summary">
          <span class="post-author">${esc(post.is_removed ? "" : post.author?.display_name || "")}</span>
          <span class="post-preview">${esc(preview)}</span>
          <span class="post-meta">${totalReplies} repl${totalReplies !== 1 ? "ies" : "y"}</span>
          <button class="collapse-link" data-action="expand-root" data-root-id="${esc(post.id)}">Expand</button>
        </div>
      </div>`;
  }

  return `
    <div class="post-root" data-root-id="${esc(post.id)}">
      <div class="post-root-actions">
        <button class="collapse-link" data-action="collapse-root" data-root-id="${esc(post.id)}">Collapse thread</button>
      </div>
      ${renderPost(post, 0, childrenOf)}
    </div>`;
}

function countDescendants(id, childrenOf) {
  let count = 0;
  (childrenOf[id] || []).forEach(c => { count += 1 + countDescendants(c.id, childrenOf); });
  return count;
}

// ===================================================================
// New-post form (top-level posts)
// ===================================================================

function renderNewPostForm() {
  if (!canPost()) {
    if (!auth.isSignedIn()) {
      return `<div class="phase-locked"><a href="/signin">Sign in</a> to join the discussion.</div>`;
    }
    const msgs = {
      proposing: "Posts are locked during the proposing phase.",
      voting:    "Posts are locked during the voting phase.",
      closed:    "This thread is closed.",
      archived:  "This thread is archived.",
    };
    const status = S.thread?.status;
    const msg = msgs[status] || "";
    return msg ? `<div class="phase-locked">${msg}</div>` : "";
  }
  return `
    <form id="new-post-form" class="post-form" data-action-form="new-post" data-thread-id="${esc(S.threadId)}" novalidate>
      <textarea id="new-post-body" placeholder="Write a post… (10–3000 characters)" minlength="10" maxlength="3000" rows="4"></textarea>
      <div class="form-footer">
        <span class="form-error" id="new-post-error"></span>
        <button type="submit" class="btn-primary">Post</button>
      </div>
    </form>`;
}

// ===================================================================
// Version history accordion
// ===================================================================

function renderVersionHistory(proposal) {
  const vNum = proposal.current_version_number || 1;
  const count = proposal.versions_count || 0;
  if (count === 0) {
    return `<div class="version-label">Version ${vNum} · No edits yet</div>`;
  }
  return `
    <div class="version-label">Version ${vNum}</div>
    <details class="version-details" data-versions-for="${esc(proposal.id)}">
      <summary class="version-summary">Version history (${count} revision${count !== 1 ? "s" : ""})</summary>
      <div class="version-list-loading">Loading…</div>
    </details>`;
}

// ===================================================================
// Proposal edit form
// ===================================================================

function renderProposalEditForm(proposal) {
  return `
    <form class="proposal-edit-form" data-action-form="edit-proposal" data-proposal-id="${esc(proposal.id)}" novalidate>
      <div class="form-field">
        <label>Title</label>
        <input type="text" name="title" value="${esc(proposal.title)}" minlength="10" maxlength="200" required>
      </div>
      <div class="form-field">
        <label>Description</label>
        <textarea name="description" minlength="50" maxlength="5000" rows="6" required>${esc(proposal.description)}</textarea>
      </div>
      <div class="form-field">
        <label>Edit summary <span class="field-hint">— required, visible in version history</span></label>
        <textarea name="edit_summary" placeholder="What changed and why?" minlength="10" maxlength="500" rows="2" required></textarea>
      </div>
      <div class="form-footer">
        <span class="form-error" data-error-for="edit-${esc(proposal.id)}"></span>
        <button type="button" data-action="cancel-edit-proposal" data-proposal-id="${esc(proposal.id)}" class="btn-secondary">Cancel</button>
        <button type="submit" class="btn-primary">Save revision</button>
      </div>
    </form>`;
}

// ===================================================================
// Vote section
// ===================================================================

function renderVoteSection(proposal) {
  if (!inVoting()) return "";
  const vs = proposal.vote_summary || {};
  const tally = `
    <div class="vote-tally">
      <span class="vote-yes">↑ Yes: ${vs.yes || 0}</span>
      <span class="vote-no">↓ No: ${vs.no || 0}</span>
      <span class="vote-abstain">– Abstain: ${vs.abstain || 0}</span>
      <span class="vote-total">${vs.total || 0} votes</span>
    </div>`;

  if (!auth.hasTier("participant")) return tally;

  if (proposal.my_vote) {
    const labels = { yes: "Yes", no: "No", abstain: "Abstain" };
    return `${tally}<div class="vote-cast-notice">You voted <strong>${labels[proposal.my_vote] || proposal.my_vote}</strong> · Votes are final</div>`;
  }

  return `
    ${tally}
    <div class="vote-buttons">
      <button data-action="cast-vote" data-proposal-id="${esc(proposal.id)}" data-choice="yes" class="vote-btn vote-yes">↑ Yes</button>
      <button data-action="cast-vote" data-proposal-id="${esc(proposal.id)}" data-choice="no"  class="vote-btn vote-no">↓ No</button>
      <button data-action="cast-vote" data-proposal-id="${esc(proposal.id)}" data-choice="abstain" class="vote-btn vote-abstain">– Abstain</button>
    </div>
    <span class="form-error" data-error-for="vote-${esc(proposal.id)}"></span>`;
}

// ===================================================================
// Proposal comments section
// ===================================================================

function renderProposalComments(proposalId) {
  const comments = S.pData[proposalId]?.comments || [];
  const canComment = inProposing() && auth.hasTier("registered");
  const readOnly   = ["voting", "closed", "archived"].includes(S.thread?.status);

  const { roots, childrenOf } = buildTree(comments.map(c => ({ ...c, proposal_id: proposalId })));
  const commentsHtml = roots.length === 0
    ? `<div class="empty-state">No comments yet.</div>`
    : roots.map(c => renderPost(c, 0, childrenOf, { maxDepth: 4, commentMode: true })).join("");

  const addForm = canComment ? `
    <form class="comment-add-form" data-action-form="add-comment" data-proposal-id="${esc(proposalId)}" novalidate>
      <textarea name="body" placeholder="Add a comment… (1–2000 characters)" maxlength="2000" rows="3"></textarea>
      <div class="form-footer">
        <span class="form-error" data-error-for="comment-${esc(proposalId)}"></span>
        <button type="submit" class="btn-primary btn-sm">Comment</button>
      </div>
    </form>` : "";

  const label = readOnly ? "Deliberation closed" : `Discussion (${comments.length})`;

  return `
    <div class="proposal-comments-section">
      <div class="subsection-heading">${esc(label)}</div>
      ${addForm}
      <div class="comments-tree" data-comments-tree="${esc(proposalId)}">${commentsHtml}</div>
    </div>`;
}

// ===================================================================
// Amendments section
// ===================================================================

function renderAmendment(amendment, proposal) {
  const isAuthor = S.me && proposal.created_by?.id === S.me.id;
  const canReview = isAuthor && amendment.status === "pending" && inProposing();
  const interactive = canSignal() && inProposing();
  const sigBar = renderSignalBar("amendment", amendment.id, { interactive });

  const statusClass = { pending: "badge-pending", accepted: "badge-accepted", rejected: "badge-rejected" }[amendment.status] || "";
  const statusNote = amendment.status === "accepted"
    ? `<div class="amendment-accepted-note">Proposer accepted — check current proposal text for incorporation.</div>`
    : "";

  const reviewBtns = canReview ? `
    <div class="amendment-review-btns">
      <button data-action="accept-amendment" data-proposal-id="${esc(proposal.id)}" data-amendment-id="${esc(amendment.id)}" class="btn-accept">Accept</button>
      <button data-action="reject-amendment" data-proposal-id="${esc(proposal.id)}" data-amendment-id="${esc(amendment.id)}" class="btn-reject">Reject</button>
    </div>` : "";

  return `
    <div class="amendment-card amendment-${esc(amendment.status)}" data-amendment-id="${esc(amendment.id)}">
      <div class="amendment-header">
        <span class="amendment-title">${esc(amendment.title)}</span>
        <span class="amendment-badge ${statusClass}">${esc(amendment.status)}</span>
        <span class="amendment-meta">by ${esc(amendment.author?.display_name)} · ${timeAgo(amendment.created_at)}</span>
      </div>
      <div class="amendment-body">
        <div class="amendment-original">
          <span class="amendment-label">Original:</span>
          <span class="amendment-text-original">${esc(amendment.original_text)}</span>
        </div>
        <div class="amendment-proposed">
          <span class="amendment-label">Proposed:</span>
          <span class="amendment-text-proposed">${esc(amendment.proposed_text)}</span>
        </div>
        <div class="amendment-rationale">
          <span class="amendment-label">Rationale:</span> ${esc(amendment.rationale)}
        </div>
      </div>
      ${statusNote}
      ${sigBar}
      ${reviewBtns}
    </div>`;
}

function renderAmendmentsSection(proposal) {
  const amendments = S.pData[proposal.id]?.amendments || [];
  const isAuthor = S.me && proposal.created_by?.id === S.me.id;
  const canAmend = inProposing() && auth.hasTier("participant") && !isAuthor;
  const readOnly  = !inProposing();

  const amendHtml = amendments.length === 0
    ? `<div class="empty-state">No amendments proposed yet.</div>`
    : amendments.map(a => renderAmendment(a, proposal)).join("");

  const addBtn = canAmend ? `
    <button data-action="open-amendment-form" data-proposal-id="${esc(proposal.id)}" class="btn-secondary btn-sm">+ Propose an amendment</button>
    <div class="amendment-form-slot" data-amendment-form-slot="${esc(proposal.id)}"></div>
  ` : "";

  const label = readOnly ? "Amendments (read-only)" : `Amendments (${amendments.length})`;

  return `
    <div class="proposal-amendments-section">
      <div class="subsection-heading">${esc(label)}</div>
      ${addBtn}
      <div class="amendments-list">${amendHtml}</div>
    </div>`;
}

// ===================================================================
// Proposal card
// ===================================================================

function renderProposalCard(proposal) {
  const STATUS_LABELS = {
    submitted: "Submitted", under_review: "Under Review",
    voting: "Open for Vote", passed: "Passed",
    rejected: "Rejected", implemented: "Implemented",
  };
  const label  = STATUS_LABELS[proposal.status] || proposal.status;
  const amount = proposal.requested_amount
    ? `<span class="proposal-amount">$${Number(proposal.requested_amount).toLocaleString()} requested</span>` : "";

  const isAuthor = S.me && proposal.created_by?.id === S.me.id;
  const canEdit  = isAuthor && inProposing();

  const sigInteractive = canSignal() && !["closed", "archived"].includes(S.thread?.status);
  const sigBar = renderSignalBar("proposal", proposal.id, { interactive: sigInteractive });

  const editBtn = canEdit
    ? `<button data-action="open-edit-proposal" data-proposal-id="${esc(proposal.id)}" class="btn-secondary btn-sm">Edit proposal</button>` : "";

  const showVotes = ["voting", "closed", "archived"].includes(S.thread?.status);
  const voteSection = showVotes ? renderVoteSection(proposal) : "";

  const showComments = showProposals();
  const showAmendments = inProposing();

  return `
    <div class="proposal-card" data-proposal-id="${esc(proposal.id)}">
      <div class="proposal-card-header">
        <h3 class="proposal-title">${esc(proposal.title)}</h3>
        <span class="proposal-status-badge proposal-status-${esc(proposal.status)}">${label}</span>
      </div>
      <div class="proposal-meta">
        by ${esc(proposal.created_by?.display_name || "Unknown")} · ${timeAgo(proposal.created_at)}
        ${amount}
      </div>
      <div class="proposal-description" data-proposal-description="${esc(proposal.id)}">${esc(proposal.description)}</div>
      ${renderVersionHistory(proposal)}
      ${sigBar}
      ${editBtn}
      <div class="proposal-edit-slot" data-edit-slot="${esc(proposal.id)}"></div>
      ${voteSection}
      ${showComments ? renderProposalComments(proposal.id) : ""}
      ${showAmendments ? renderAmendmentsSection(proposal) : ""}
    </div>`;
}

// ===================================================================
// New-proposal form
// ===================================================================

function renderNewProposalForm() {
  if (!inProposing() || !auth.hasTier("participant")) return "";
  return `
    <form class="proposal-form" data-action-form="create-proposal" novalidate>
      <div class="form-field">
        <label>Title <span class="field-hint">10–200 characters</span></label>
        <input type="text" name="title" placeholder="A clear, specific title" minlength="10" maxlength="200" required>
      </div>
      <div class="form-field">
        <label>Description <span class="field-hint">50–5000 characters</span></label>
        <textarea name="description" placeholder="Describe the proposal, its rationale, and how it would work…" minlength="50" maxlength="5000" rows="6" required></textarea>
      </div>
      <div class="form-footer">
        <span class="form-error" data-error-for="new-proposal"></span>
        <button type="submit" class="btn-primary">Submit Proposal</button>
      </div>
    </form>`;
}

// ===================================================================
// Facilitator panel
// ===================================================================

const PHASE_LABELS = {
  open: "Open", deliberating: "Deliberating", proposing: "Proposing",
  voting: "Voting", closed: "Closed", archived: "Archived",
};
const PHASE_NEXT_DESC = {
  open:         "Move to Deliberating — participants begin discussing.",
  deliberating: "Move to Proposing — participants submit formal proposals.",
  proposing:    "Move to Voting — proposals are locked; participants cast votes.",
  voting:       "Move to Closed — voting ends; outcomes recorded in audit log.",
};

function renderFacilitatorPanel() {
  if (!auth.hasTier("facilitator")) return "";
  const status = S.thread.status;
  if (["closed", "archived"].includes(status)) return "";
  const next = nextPhase(status);
  if (!next) return "";
  const nextLabel = PHASE_LABELS[next] || next;

  return `
    <div class="facilitator-panel" id="facilitator-panel">
      <div class="facilitator-badge-row">
        <span class="facilitator-badge">Facilitator Controls</span>
        <span>Current phase: <strong>${PHASE_LABELS[status] || status}</strong></span>
      </div>
      <div class="facilitator-desc">${PHASE_NEXT_DESC[status] || ""}</div>
      <form id="advance-form" data-action-form="advance-phase" novalidate>
        <div class="form-field">
          <label for="advance-reason">Reason for advancing <span class="field-hint">— required, recorded in audit log (10–500 characters)</span></label>
          <textarea id="advance-reason" placeholder="Explain why the thread is moving to ${nextLabel}…" minlength="10" maxlength="500" rows="3"></textarea>
        </div>
        <div class="form-footer">
          <span class="form-error" id="advance-error"></span>
          <button type="submit" class="btn-advance" id="advance-btn" disabled>Advance to ${esc(nextLabel)} →</button>
        </div>
      </form>
    </div>`;
}

// ===================================================================
// Thread-level signal section
// ===================================================================

function renderThreadSignals() {
  const sc  = S.thread.signal_counts || {};
  const sig = getSig("thread", S.threadId);
  const interactive = canSignal();

  // Override with live counts from thread object on first render
  // (before batch signal fetch completes)
  const counts = {
    support: sig.total > 0 ? sig.support : (sc.support || 0),
    concern: sig.total > 0 ? sig.concern : (sc.concern || 0),
    need_info: sig.total > 0 ? sig.need_info : (sc.need_info || 0),
    block: sig.total > 0 ? sig.block : (sc.block || 0),
    total: sig.total > 0 ? sig.total : (sc.total || 0),
    my_signal: sig.my_signal || S.thread.my_signal || null,
  };

  // Temporarily load these into state so renderSignalBar picks them up
  S.signals[sigKey("thread", S.threadId)] = counts;

  return renderSignalBar("thread", S.threadId, { interactive, showLabel: true });
}

// ===================================================================
// Full page render
// ===================================================================

function renderPage() {
  const t = S.thread;
  const { roots, childrenOf } = buildTree(S.posts);

  document.title = `${t.title} — Civic Platform`;

  const contextHtml = t.context
    ? `<div class="context-text">${esc(t.context)}</div>` : "";

  const postsHtml = roots.length === 0
    ? `<div class="empty-state">No posts yet. Be the first to contribute.</div>`
    : roots.map(p => renderRootPost(p, childrenOf)).join("");

  const proposalsHtml = showProposals() ? `
    <div class="detail-section" id="proposals-section">
      <div class="section-heading">Proposals · ${S.proposals.length} submitted</div>
      ${S.proposals.map(p => renderProposalCard(p)).join("")}
      ${renderNewProposalForm()}
    </div>` : "";

  document.getElementById("thread-container").innerHTML = `
    <div class="thread-header">
      <a href="/c/${S.communitySlug}/threads" class="back-link">← All Discussions</a>
      <div class="thread-header-top">
        <h1 class="thread-detail-title">${esc(t.title)}</h1>
        <span class="${phaseBadgeClass(t.status)}">${capitalize(t.status)}</span>
      </div>
      <div class="thread-header-meta">
        Started by ${esc(t.created_by?.display_name)} · ${timeAgo(t.created_at)}
        · ${t.post_count} post${t.post_count !== 1 ? "s" : ""}
        · ${t.proposal_count} proposal${t.proposal_count !== 1 ? "s" : ""}
      </div>
    </div>

    ${renderFacilitatorPanel()}

    <div class="detail-section" id="signal-section">
      <div class="section-heading">Community Signals</div>
      ${renderThreadSignals()}
      <p class="sig-note">Signals are anonymous and aggregated. Cast one to register your position.</p>
    </div>

    <div class="detail-section">
      <div class="section-heading">Deliberation Question</div>
      <div class="prompt-text">${esc(t.prompt)}</div>
      ${contextHtml}
    </div>

    <div class="detail-section" id="discussion-section">
      <div class="section-heading">Discussion · ${t.post_count} post${t.post_count !== 1 ? "s" : ""}</div>
      <div id="new-post-form-container">${renderNewPostForm()}</div>
      <div id="posts-container">${postsHtml}</div>
    </div>

    ${proposalsHtml}
  `;
}

// ===================================================================
// Signal hydration (batch-fetch all visible content)
// ===================================================================

async function hydrateSignals() {
  // Collect IDs by target type
  const byType = {
    thread:           [S.threadId],
    post:             S.posts.map(p => p.id),
    proposal:         S.proposals.map(p => p.id),
    proposal_comment: [],
    amendment:        [],
  };

  Object.values(S.pData).forEach(pd => {
    (pd.comments || []).forEach(c => byType.proposal_comment.push(c.id));
    (pd.amendments || []).forEach(a => byType.amendment.push(a.id));
  });

  // Parallel batch fetches per type
  await Promise.all(
    Object.entries(byType)
      .filter(([, ids]) => ids.length > 0)
      .map(async ([type, ids]) => {
        try {
          const data = await getSignalsBatch(type, ids);
          Object.entries(data).forEach(([id, sig]) => {
            S.signals[sigKey(type, id)] = sig;
          });
        } catch (_) { /* signals are best-effort */ }
      })
  );

  // Re-render each signal bar in place
  document.querySelectorAll("[data-signal-bar]").forEach(el => {
    const type = el.dataset.targetType;
    const id   = el.dataset.targetId;
    const interactive = el.closest("#signal-section")
      ? canSignal()
      : canSignal() && !["closed", "archived"].includes(S.thread?.status);
    el.outerHTML = renderSignalBar(type, id, { interactive, showLabel: type === "thread" });
  });
}

// ===================================================================
// Event handlers
// ===================================================================

function err(container, msg) {
  if (!container) return;
  const el = typeof container === "string" ? document.querySelector(`[data-error-for="${container}"]`) : container;
  if (el) el.textContent = msg;
}

function openInlineReplyForm(slotId, proposalId = null) {
  // Close any already-open form first
  if (S.openForm) {
    const prev = document.querySelector(`[data-reply-slot="${S.openForm}"]`)
               || document.querySelector(`[data-amendment-form-slot="${S.openForm}"]`);
    if (prev) prev.innerHTML = "";
  }
  S.openForm = slotId;

  if (proposalId) {
    // Comment reply form
    const slot = document.querySelector(`[data-reply-slot="${slotId}"]`);
    if (!slot) return;
    slot.innerHTML = `
      <form class="inline-reply-form" data-action-form="add-comment-reply" data-post-id="${esc(slotId)}" data-proposal-id="${esc(proposalId)}" novalidate>
        <textarea name="body" placeholder="Write a reply… (1–2000 characters)" maxlength="2000" rows="3" autofocus></textarea>
        <div class="form-footer">
          <span class="form-error" data-error-for="reply-comment-${esc(slotId)}"></span>
          <button type="button" data-action="cancel-reply" data-slot-id="${esc(slotId)}" class="btn-secondary btn-sm">Cancel</button>
          <button type="submit" class="btn-primary btn-sm">Reply</button>
        </div>
      </form>`;
  } else {
    // Post reply form
    const slot = document.querySelector(`[data-reply-slot="${slotId}"]`);
    if (!slot) return;
    slot.innerHTML = `
      <form class="inline-reply-form" data-action-form="post-reply" data-parent-id="${esc(slotId)}" novalidate>
        <textarea name="body" placeholder="Write a reply… (10–3000 characters)" minlength="10" maxlength="3000" rows="3" autofocus></textarea>
        <div class="form-footer">
          <span class="form-error" data-error-for="reply-${esc(slotId)}"></span>
          <button type="button" data-action="cancel-reply" data-slot-id="${esc(slotId)}" class="btn-secondary btn-sm">Cancel</button>
          <button type="submit" class="btn-primary btn-sm">Reply</button>
        </div>
      </form>`;
  }
}

async function handleClick(e) {
  const btn = e.target.closest("[data-action]");
  if (!btn) return;

  const action = btn.dataset.action;

  // ---- Signal cast ----
  if (action === "cast-signal") {
    const { targetType, targetId, signalType } = btn.dataset;
    btn.disabled = true;
    try {
      await castSignal(targetType, targetId, signalType);
      const fresh = await getSignalsBatch(targetType, [targetId]);
      S.signals[sigKey(targetType, targetId)] = fresh[targetId];
      const bar = document.querySelector(`[data-signal-bar][data-target-type="${targetType}"][data-target-id="${targetId}"]`);
      if (bar) bar.outerHTML = renderSignalBar(targetType, targetId, { interactive: true, showLabel: targetType === "thread" });
    } catch (ex) {
      btn.disabled = false;
    }
    return;
  }

  // ---- Signal remove ----
  if (action === "remove-signal") {
    const { targetType, targetId } = btn.dataset;
    btn.disabled = true;
    try {
      await removeSignal(targetType, targetId);
      const fresh = await getSignalsBatch(targetType, [targetId]);
      S.signals[sigKey(targetType, targetId)] = fresh[targetId];
      const bar = document.querySelector(`[data-signal-bar][data-target-type="${targetType}"][data-target-id="${targetId}"]`);
      if (bar) bar.outerHTML = renderSignalBar(targetType, targetId, { interactive: true, showLabel: targetType === "thread" });
    } catch (ex) {
      btn.disabled = false;
    }
    return;
  }

  // ---- Toggle children ----
  if (action === "toggle-children") {
    const postId = btn.dataset.postId;
    const children = document.querySelector(`[data-children-of="${postId}"]`);
    if (!children) return;
    const hidden = children.style.display === "none";
    children.style.display = hidden ? "" : "none";
    S.collapsed[hidden ? "delete" : "add"](postId);
    btn.textContent = `${hidden ? "▼" : "▶"} ${children.children.length} repl${children.children.length !== 1 ? "ies" : "y"}`;
    return;
  }

  // ---- Collapse / expand root ----
  if (action === "collapse-root") {
    const rootId = btn.dataset.rootId;
    S.rootCollapsed.add(rootId);
    const root = document.querySelector(`[data-root-id="${rootId}"]`);
    if (root) {
      const post = S.posts.find(p => p.id === rootId);
      const { childrenOf } = buildTree(S.posts);
      if (post) root.outerHTML = renderRootPost(post, childrenOf);
    }
    return;
  }
  if (action === "expand-root") {
    const rootId = btn.dataset.rootId;
    S.rootCollapsed.delete(rootId);
    const root = document.querySelector(`[data-root-id="${rootId}"]`);
    if (root) {
      const post = S.posts.find(p => p.id === rootId);
      const { childrenOf } = buildTree(S.posts);
      if (post) root.outerHTML = renderRootPost(post, childrenOf);
    }
    return;
  }

  // ---- Open inline reply form (post) ----
  if (action === "open-reply") {
    openInlineReplyForm(btn.dataset.postId);
    return;
  }

  // ---- Open inline reply form (comment) ----
  if (action === "open-comment-reply") {
    openInlineReplyForm(btn.dataset.postId, btn.dataset.proposalId);
    return;
  }

  // ---- Cancel inline reply form ----
  if (action === "cancel-reply") {
    const slot = document.querySelector(`[data-reply-slot="${btn.dataset.slotId}"]`);
    if (slot) slot.innerHTML = "";
    if (S.openForm === btn.dataset.slotId) S.openForm = null;
    return;
  }

  // ---- Open proposal edit form ----
  if (action === "open-edit-proposal") {
    const pid = btn.dataset.proposalId;
    const proposal = S.proposals.find(p => p.id === pid);
    if (!proposal) return;
    const slot = document.querySelector(`[data-edit-slot="${pid}"]`);
    if (!slot) return;
    slot.innerHTML = renderProposalEditForm(proposal);
    btn.style.display = "none";
    return;
  }
  if (action === "cancel-edit-proposal") {
    const pid = btn.dataset.proposalId;
    const slot = document.querySelector(`[data-edit-slot="${pid}"]`);
    if (slot) slot.innerHTML = "";
    const editBtn = document.querySelector(`[data-action="open-edit-proposal"][data-proposal-id="${pid}"]`);
    if (editBtn) editBtn.style.display = "";
    return;
  }

  // ---- Open amendment form ----
  if (action === "open-amendment-form") {
    const pid = btn.dataset.proposalId;
    if (S.openForm) {
      const prev = document.querySelector(`[data-amendment-form-slot="${S.openForm}"]`);
      if (prev) prev.innerHTML = "";
    }
    S.openForm = pid;
    const slot = document.querySelector(`[data-amendment-form-slot="${pid}"]`);
    if (!slot) return;
    slot.innerHTML = `
      <form class="amendment-form" data-action-form="create-amendment" data-proposal-id="${esc(pid)}" novalidate>
        <div class="form-field">
          <label>Title</label>
          <input type="text" name="title" placeholder="Brief title for this amendment" minlength="5" maxlength="200" required>
        </div>
        <div class="form-field">
          <label>Original text <span class="field-hint">— paste the passage being changed</span></label>
          <textarea name="original_text" rows="3" minlength="10" required></textarea>
        </div>
        <div class="form-field">
          <label>Proposed text <span class="field-hint">— what you want it changed to</span></label>
          <textarea name="proposed_text" rows="3" minlength="10" required></textarea>
        </div>
        <div class="form-field">
          <label>Rationale <span class="field-hint">— why this improves the proposal (10–1000 chars)</span></label>
          <textarea name="rationale" rows="2" minlength="10" maxlength="1000" required></textarea>
        </div>
        <div class="form-footer">
          <span class="form-error" data-error-for="amendment-${esc(pid)}"></span>
          <button type="button" data-action="cancel-amendment-form" data-proposal-id="${esc(pid)}" class="btn-secondary btn-sm">Cancel</button>
          <button type="submit" class="btn-primary btn-sm">Submit Amendment</button>
        </div>
      </form>`;
    return;
  }
  if (action === "cancel-amendment-form") {
    const pid = btn.dataset.proposalId;
    const slot = document.querySelector(`[data-amendment-form-slot="${pid}"]`);
    if (slot) slot.innerHTML = "";
    if (S.openForm === pid) S.openForm = null;
    return;
  }

  // ---- Accept / reject amendment ----
  if (action === "accept-amendment" || action === "reject-amendment") {
    const pid = btn.dataset.proposalId;
    const aid = btn.dataset.amendmentId;
    const status = action === "accept-amendment" ? "accepted" : "rejected";
    btn.disabled = true;
    try {
      await reviewAmendment(pid, aid, status);
      // Refresh amendments
      const fresh = await getAmendments(pid);
      S.pData[pid] = S.pData[pid] || {};
      S.pData[pid].amendments = fresh;
      refreshProposalCard(pid);
    } catch (ex) {
      btn.disabled = false;
    }
    return;
  }

  // ---- Cast vote ----
  if (action === "cast-vote") {
    const { proposalId, choice } = btn.dataset;
    const confirmed = window.confirm(`Cast vote: ${capitalize(choice)}?\n\nVotes are permanent and cannot be changed.`);
    if (!confirmed) return;
    btn.disabled = true;
    try {
      await castVote(proposalId, choice);
      const fresh = await getProposals(S.threadId);
      S.proposals = fresh;
      refreshProposalCard(proposalId);
    } catch (ex) {
      const errEl = document.querySelector(`[data-error-for="vote-${proposalId}"]`);
      if (errEl) errEl.textContent = ex.message || "Could not cast vote.";
      btn.disabled = false;
    }
    return;
  }
}

/** Re-render a single proposal card in-place without full page reload. */
function refreshProposalCard(proposalId) {
  const proposal = S.proposals.find(p => p.id === proposalId);
  if (!proposal) return;
  const card = document.querySelector(`[data-proposal-id="${proposalId}"].proposal-card`);
  if (!card) return;
  card.outerHTML = renderProposalCard(proposal);
}

async function handleSubmit(e) {
  const form = e.target;
  const actionForm = form.dataset.actionForm;
  if (!actionForm) return;
  e.preventDefault();

  // ---- New top-level post ----
  if (actionForm === "new-post") {
    const body = form.querySelector("#new-post-body")?.value.trim() || "";
    const errEl = document.getElementById("new-post-error");
    if (body.length < 10) { if (errEl) errEl.textContent = "Posts must be at least 10 characters."; return; }
    if (errEl) errEl.textContent = "";
    const btn = form.querySelector("button[type=submit]");
    if (btn) { btn.disabled = true; btn.textContent = "Posting…"; }
    try {
      await createPost(S.threadId, body, null);
      S.posts = await getPostsFlat(S.threadId);
      document.getElementById("posts-container").innerHTML =
        buildTree(S.posts).roots.map(p => renderRootPost(p, buildTree(S.posts).childrenOf)).join("");
      form.reset();
    } catch (ex) {
      if (errEl) errEl.textContent = ex.message || "Could not post.";
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = "Post"; }
    }
    return;
  }

  // ---- Inline post reply ----
  if (actionForm === "post-reply") {
    const parentId = form.dataset.parentId;
    const body = form.querySelector("textarea")?.value.trim() || "";
    const errEl = form.querySelector(`[data-error-for="reply-${parentId}"]`);
    if (body.length < 10) { if (errEl) errEl.textContent = "Replies must be at least 10 characters."; return; }
    if (errEl) errEl.textContent = "";
    const btn = form.querySelector("button[type=submit]");
    if (btn) { btn.disabled = true; btn.textContent = "Posting…"; }
    try {
      await createPost(S.threadId, body, parentId);
      S.posts = await getPostsFlat(S.threadId);
      const { roots, childrenOf } = buildTree(S.posts);
      document.getElementById("posts-container").innerHTML =
        roots.map(p => renderRootPost(p, childrenOf)).join("");
      S.openForm = null;
    } catch (ex) {
      if (errEl) errEl.textContent = ex.message || "Could not post.";
      if (btn) { btn.disabled = false; btn.textContent = "Reply"; }
    }
    return;
  }

  // ---- New proposal ----
  if (actionForm === "create-proposal") {
    const title = form.querySelector("[name=title]")?.value.trim() || "";
    const description = form.querySelector("[name=description]")?.value.trim() || "";
    const errEl = form.querySelector(`[data-error-for="new-proposal"]`);
    if (title.length < 10)    { if (errEl) errEl.textContent = "Title must be at least 10 characters."; return; }
    if (description.length < 50) { if (errEl) errEl.textContent = "Description must be at least 50 characters."; return; }
    if (errEl) errEl.textContent = "";
    const btn = form.querySelector("button[type=submit]");
    if (btn) { btn.disabled = true; btn.textContent = "Submitting…"; }
    try {
      await createProposal(S.threadId, title, description);
      S.proposals = await getProposals(S.threadId);
      await loadProposalData();
      renderPage();
      await hydrateSignals();
    } catch (ex) {
      if (errEl) errEl.textContent = ex.message || "Could not submit proposal.";
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = "Submit Proposal"; }
    }
    return;
  }

  // ---- Edit proposal ----
  if (actionForm === "edit-proposal") {
    const pid = form.dataset.proposalId;
    const title = form.querySelector("[name=title]")?.value.trim() || "";
    const description = form.querySelector("[name=description]")?.value.trim() || "";
    const editSummary = form.querySelector("[name=edit_summary]")?.value.trim() || "";
    const errEl = form.querySelector(`[data-error-for="edit-${pid}"]`);
    if (title.length < 10)     { if (errEl) errEl.textContent = "Title must be at least 10 characters."; return; }
    if (description.length < 50) { if (errEl) errEl.textContent = "Description must be at least 50 characters."; return; }
    if (editSummary.length < 10) { if (errEl) errEl.textContent = "Edit summary must be at least 10 characters."; return; }
    if (errEl) errEl.textContent = "";
    const btn = form.querySelector("button[type=submit]");
    if (btn) { btn.disabled = true; btn.textContent = "Saving…"; }
    try {
      const updated = await editProposal(pid, title, description, editSummary);
      const idx = S.proposals.findIndex(p => p.id === pid);
      if (idx >= 0) S.proposals[idx] = updated;
      refreshProposalCard(pid);
    } catch (ex) {
      if (errEl) errEl.textContent = ex.message || "Could not save.";
      if (btn) { btn.disabled = false; btn.textContent = "Save revision"; }
    }
    return;
  }

  // ---- Add proposal comment ----
  if (actionForm === "add-comment") {
    const pid = form.dataset.proposalId;
    const body = form.querySelector("[name=body]")?.value.trim() || "";
    const errEl = form.querySelector(`[data-error-for="comment-${pid}"]`);
    if (!body) { if (errEl) errEl.textContent = "Comment cannot be empty."; return; }
    if (errEl) errEl.textContent = "";
    const btn = form.querySelector("button[type=submit]");
    if (btn) { btn.disabled = true; btn.textContent = "Commenting…"; }
    try {
      await createProposalComment(pid, body, null);
      S.pData[pid] = S.pData[pid] || {};
      S.pData[pid].comments = await getProposalComments(pid);
      refreshProposalCard(pid);
      form.reset();
    } catch (ex) {
      if (errEl) errEl.textContent = ex.message || "Could not post comment.";
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = "Comment"; }
    }
    return;
  }

  // ---- Reply to proposal comment ----
  if (actionForm === "add-comment-reply") {
    const pid = form.dataset.proposalId;
    const parentId = form.dataset.postId;
    const body = form.querySelector("textarea")?.value.trim() || "";
    const errEl = form.querySelector(`[data-error-for="reply-comment-${parentId}"]`);
    if (!body) { if (errEl) errEl.textContent = "Reply cannot be empty."; return; }
    if (errEl) errEl.textContent = "";
    const btn = form.querySelector("button[type=submit]");
    if (btn) { btn.disabled = true; btn.textContent = "Replying…"; }
    try {
      await createProposalComment(pid, body, parentId);
      S.pData[pid] = S.pData[pid] || {};
      S.pData[pid].comments = await getProposalComments(pid);
      S.openForm = null;
      refreshProposalCard(pid);
    } catch (ex) {
      if (errEl) errEl.textContent = ex.message || "Could not reply.";
      if (btn) { btn.disabled = false; btn.textContent = "Reply"; }
    }
    return;
  }

  // ---- Create amendment ----
  if (actionForm === "create-amendment") {
    const pid = form.dataset.proposalId;
    const title = form.querySelector("[name=title]")?.value.trim() || "";
    const originalText = form.querySelector("[name=original_text]")?.value.trim() || "";
    const proposedText = form.querySelector("[name=proposed_text]")?.value.trim() || "";
    const rationale = form.querySelector("[name=rationale]")?.value.trim() || "";
    const errEl = form.querySelector(`[data-error-for="amendment-${pid}"]`);
    if (!title || title.length < 5) { if (errEl) errEl.textContent = "Title must be at least 5 characters."; return; }
    if (!originalText || originalText.length < 10) { if (errEl) errEl.textContent = "Original text must be at least 10 characters."; return; }
    if (!proposedText || proposedText.length < 10) { if (errEl) errEl.textContent = "Proposed text must be at least 10 characters."; return; }
    if (!rationale || rationale.length < 10) { if (errEl) errEl.textContent = "Rationale must be at least 10 characters."; return; }
    if (errEl) errEl.textContent = "";
    const btn = form.querySelector("button[type=submit]");
    if (btn) { btn.disabled = true; btn.textContent = "Submitting…"; }
    try {
      await createAmendment(pid, title, originalText, proposedText, rationale);
      S.pData[pid] = S.pData[pid] || {};
      S.pData[pid].amendments = await getAmendments(pid);
      S.openForm = null;
      refreshProposalCard(pid);
    } catch (ex) {
      if (errEl) errEl.textContent = ex.message || "Could not submit amendment.";
      if (btn) { btn.disabled = false; btn.textContent = "Submit Amendment"; }
    }
    return;
  }

  // ---- Phase advance ----
  if (actionForm === "advance-phase") {
    const reason = document.getElementById("advance-reason")?.value.trim() || "";
    const errEl  = document.getElementById("advance-error");
    if (reason.length < 10) { if (errEl) errEl.textContent = "Reason must be at least 10 characters."; return; }
    const next = nextPhase(S.thread.status);
    if (!next) return;
    const confirmed = window.confirm(`Advance to "${PHASE_LABELS[next]}"?\n\nThis is permanent.`);
    if (!confirmed) return;
    const btn = document.getElementById("advance-btn");
    if (errEl) errEl.textContent = "";
    if (btn) { btn.disabled = true; btn.textContent = "Advancing…"; }
    try {
      await advancePhase(S.threadId, next, reason);
      await reload();
    } catch (ex) {
      if (errEl) errEl.textContent = ex.message || "Could not advance phase.";
      if (btn) { btn.disabled = false; btn.textContent = `Advance to ${PHASE_LABELS[next]} →`; }
    }
    return;
  }
}

async function handleInput(e) {
  // Enable/disable the advance button as the user types
  if (e.target.id === "advance-reason") {
    const btn = document.getElementById("advance-btn");
    if (btn) btn.disabled = e.target.value.trim().length < 10;
    return;
  }

  // Version history accordion lazy-load
  const details = e.target.closest("details.version-details");
  if (details && details.open) {
    const pid = details.dataset.versionsFor;
    if (!pid) return;
    const list = details.querySelector(".version-list-loading");
    if (!list) return; // already loaded
    try {
      const versions = await getProposalVersions(pid);
      const html = versions.length === 0 ? "<div class='empty-state'>No revisions yet.</div>" :
        versions.map(v => `
          <div class="version-entry">
            <span class="version-num">v${v.version_number}</span>
            <span class="version-time">${timeAgo(v.created_at)}</span>
            <span class="version-summary">${esc(v.edit_summary)}</span>
          </div>`).join("");
      details.querySelector(".version-list-loading").outerHTML = `<div class="version-list">${html}</div>`;
    } catch (_) {
      if (list) list.textContent = "Could not load history.";
    }
  }
}

// ===================================================================
// Data loading helpers
// ===================================================================

async function loadProposalData() {
  if (S.proposals.length === 0) return;
  const results = await Promise.all(
    S.proposals.map(p =>
      Promise.all([getProposalComments(p.id), getAmendments(p.id)])
        .then(([comments, amendments]) => ({ id: p.id, comments, amendments }))
        .catch(() => ({ id: p.id, comments: [], amendments: [] }))
    )
  );
  results.forEach(({ id, comments, amendments }) => {
    S.pData[id] = { comments, amendments };
  });
}

async function reload() {
  const [thread, posts, proposals] = await Promise.all([
    getThread(S.threadId),
    getPostsFlat(S.threadId),
    showProposals() ? getProposals(S.threadId) : Promise.resolve([]),
  ]);
  S.thread    = thread;
  S.posts     = posts;
  S.proposals = proposals;
  S.signals   = {};
  await loadProposalData();
  renderPage();
  await hydrateSignals();
}

// ===================================================================
// Init
// ===================================================================

async function init() {
  const container = document.getElementById("thread-container");
  const pathname = window.location.pathname;

  // Parse /c/{slug}/thread/{id}
  const communityMatch = pathname.match(/^\/c\/([^/]+)\/thread\/([^/]+)/);
  if (communityMatch) {
    S.communitySlug = communityMatch[1];
    S.threadId = communityMatch[2].replace(/\/$/, "");
  } else {
    // Fallback for legacy /thread/{id} (should only occur before redirects are in place)
    S.threadId = (pathname.split("/thread/")[1] || "").replace(/\/$/, "");
    S.communitySlug = "test";
  }

  if (!S.threadId) {
    container.innerHTML = `<div class="error-message">Invalid thread URL.</div>`;
    return;
  }

  // Load current user (optional — page is readable without auth)
  if (auth.isSignedIn()) {
    try { S.me = await getMe(); } catch (_) {}
  }

  try {
    const [thread, posts] = await Promise.all([
      getThread(S.threadId),
      getPostsFlat(S.threadId),
    ]);
    S.thread = thread;
    S.posts  = posts;

    // Load proposals only in relevant phases
    if (showProposals()) {
      S.proposals = await getProposals(S.threadId);
      await loadProposalData();
    }

    renderPage();

    // Event delegation — all interactions handled here
    document.addEventListener("click",  handleClick);
    document.addEventListener("submit", handleSubmit);
    document.addEventListener("toggle", handleInput);  // <details> toggle
    document.getElementById("advance-reason")?.addEventListener("input", handleInput);
    // Attach advance-reason listener after render (delegated via document)
    document.addEventListener("input", handleInput);

    // Batch-fetch and hydrate signals (non-blocking)
    hydrateSignals().catch(() => {});

  } catch (ex) {
    container.innerHTML = `
      <div class="error-message">Could not load thread: ${esc(ex.message)}</div>
      <p style="margin-top:16px"><a href="/c/${S.communitySlug}/threads">← Back to discussions</a></p>`;
  }
}

init();
