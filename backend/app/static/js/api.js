/**
 * api.js — All communication with the FastAPI backend.
 *
 * Design principle: ONLY fetch() calls and data parsing here.
 * No DOM manipulation. This file survives unchanged when we migrate to React.
 *
 * Every function returns a Promise resolving to parsed JSON,
 * or throws an Error with a human-readable message.
 */

const API_BASE = "/api/v1";

/**
 * Core fetch wrapper. Handles auth headers and error responses uniformly.
 */
async function apiFetch(path, options = {}) {
  const token = auth.getToken();

  const headers = {
    "Content-Type": "application/json",
    ...(token ? { "Authorization": `Bearer ${token}` } : {}),
    ...(options.headers || {}),
  };

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const err = await response.json();
      detail = err.detail || detail;
    } catch (_) {}
    throw new Error(detail);
  }

  if (response.status === 204) return null;
  return response.json();
}

// ===== Threads =====

async function getThreads({ domainSlug, status, limit = 20, offset = 0 } = {}) {
  const params = new URLSearchParams();
  if (domainSlug) params.set("domain_slug", domainSlug);
  if (status)     params.set("status", status);
  params.set("limit", limit);
  params.set("offset", offset);
  return apiFetch(`/threads?${params}`);
}

async function getThread(threadId) {
  return apiFetch(`/threads/${threadId}`);
}

async function createThread(domainId, title, prompt, context) {
  return apiFetch("/threads", {
    method: "POST",
    body: JSON.stringify({ domain_id: domainId, title, prompt, context }),
  });
}

async function advancePhase(threadId, targetStatus, reason) {
  return apiFetch(`/threads/${threadId}/advance`, {
    method: "PATCH",
    body: JSON.stringify({ target_status: targetStatus, reason }),
  });
}

// ===== Posts =====

/**
 * Fetch all posts for a thread as a flat list (chronological, any depth).
 * Client builds the tree from parent_id links.
 */
async function getPostsFlat(threadId) {
  return apiFetch(`/posts/thread/${threadId}/flat`);
}

/** @deprecated Use getPostsFlat for new code. */
async function getPosts(threadId) {
  return apiFetch(`/posts/thread/${threadId}`);
}

async function createPost(threadId, body, parentId = null) {
  return apiFetch(`/posts`, {
    method: "POST",
    body: JSON.stringify({ thread_id: threadId, body, parent_id: parentId }),
  });
}

// ===== Signals =====

/**
 * Cast or update the current user's signal on any target.
 * @param {string} targetType - "thread"|"post"|"proposal"|"proposal_comment"|"amendment"
 * @param {string} targetId   - UUID
 * @param {string} signalType - "support"|"concern"|"need_info"|"block"
 */
async function castSignal(targetType, targetId, signalType) {
  return apiFetch(`/signals`, {
    method: "POST",
    body: JSON.stringify({ target_type: targetType, target_id: targetId, signal_type: signalType }),
  });
}

/**
 * Remove the current user's signal from a target (toggle-off).
 */
async function removeSignal(targetType, targetId) {
  const params = new URLSearchParams({ target_type: targetType, target_id: targetId });
  return apiFetch(`/signals?${params}`, { method: "DELETE" });
}

/**
 * Batch-fetch signal counts for multiple targets of the same type.
 * Returns { "<uuid>": { support, concern, need_info, block, total, my_signal } }
 * my_signal is null if unauthenticated or no signal cast.
 *
 * @param {string}   targetType - one of the SignalTargetType values
 * @param {string[]} targetIds  - array of UUIDs
 */
async function getSignalsBatch(targetType, targetIds) {
  if (!targetIds || targetIds.length === 0) return {};
  const params = new URLSearchParams({
    target_type: targetType,
    target_ids: targetIds.join(","),
  });
  return apiFetch(`/signals/batch?${params}`);
}

// ===== Proposals =====

async function getProposals(threadId) {
  return apiFetch(`/proposals/thread/${threadId}`);
}

async function createProposal(threadId, title, description, requestedAmount = null) {
  return apiFetch(`/proposals?thread_id=${encodeURIComponent(threadId)}`, {
    method: "POST",
    body: JSON.stringify({ title, description, requested_amount: requestedAmount }),
  });
}

/**
 * Edit proposal content (author only, PROPOSING phase).
 * @param {string} proposalId
 * @param {string} title
 * @param {string} description
 * @param {string} editSummary - Required. Recorded in version history.
 */
async function editProposal(proposalId, title, description, editSummary) {
  return apiFetch(`/proposals/${proposalId}`, {
    method: "PATCH",
    body: JSON.stringify({ title, description, edit_summary: editSummary }),
  });
}

/**
 * Fetch the full version history for a proposal (reverse chronological).
 */
async function getProposalVersions(proposalId) {
  return apiFetch(`/proposals/${proposalId}/versions`);
}

// ===== Proposal Comments =====

async function getProposalComments(proposalId) {
  return apiFetch(`/proposals/${proposalId}/comments`);
}

async function createProposalComment(proposalId, body, parentId = null) {
  return apiFetch(`/proposals/${proposalId}/comments`, {
    method: "POST",
    body: JSON.stringify({ body, parent_id: parentId }),
  });
}

// ===== Amendments =====

async function getAmendments(proposalId) {
  return apiFetch(`/proposals/${proposalId}/amendments`);
}

async function createAmendment(proposalId, title, originalText, proposedText, rationale) {
  return apiFetch(`/proposals/${proposalId}/amendments`, {
    method: "POST",
    body: JSON.stringify({
      title,
      original_text: originalText,
      proposed_text: proposedText,
      rationale,
    }),
  });
}

/**
 * Accept or reject an amendment (proposal author only).
 * @param {string} status - "accepted" | "rejected"
 * @param {string|null} reviewerNote - Optional note
 */
async function reviewAmendment(proposalId, amendmentId, status, reviewerNote = null) {
  return apiFetch(`/proposals/${proposalId}/amendments/${amendmentId}/review`, {
    method: "PATCH",
    body: JSON.stringify({ status, reviewer_note: reviewerNote }),
  });
}

// ===== Votes =====

async function castVote(proposalId, choice) {
  return apiFetch(`/votes/${proposalId}`, {
    method: "POST",
    body: JSON.stringify({ choice }),
  });
}

// ===== Domains =====

async function getDomains() {
  return apiFetch("/domains");
}

// ===== Auth / Me =====

async function getMe() {
  return apiFetch("/auth/me");
}

async function updateDisplayName(displayName) {
  return apiFetch("/auth/me", {
    method: "PATCH",
    body: JSON.stringify({ display_name: displayName }),
  });
}

// ===== Facilitator Requests =====

async function submitFacilitatorRequest(reason) {
  return apiFetch("/auth/facilitator-request", {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

async function getMyFacilitatorRequest() {
  return apiFetch("/auth/facilitator-request");
}

async function getFacilitatorRequests() {
  return apiFetch("/admin/facilitator-requests");
}

async function approveFacilitatorRequest(requestId) {
  return apiFetch(`/admin/facilitator-requests/${requestId}/approve`, { method: "POST" });
}

async function denyFacilitatorRequest(requestId) {
  return apiFetch(`/admin/facilitator-requests/${requestId}/deny`, { method: "POST" });
}
