/**
 * api.js — All communication with the FastAPI backend.
 *
 * Design principle: This file contains ONLY fetch() calls and data parsing.
 * No DOM manipulation here. This file will survive unchanged when we migrate to React.
 *
 * Every function returns a Promise that resolves to parsed JSON data,
 * or throws an Error with a human-readable message.
 */

const API_BASE = "/api/v1";

/**
 * Core fetch wrapper. Handles auth headers and error responses uniformly.
 * All other functions call this.
 */
async function apiFetch(path, options = {}) {
  const token = auth.getToken();

  const headers = {
    "Content-Type": "application/json",
    ...(token ? { "Authorization": `Bearer ${token}` } : {}),
    ...(options.headers || {}),
  };

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const err = await response.json();
      detail = err.detail || detail;
    } catch (_) {}
    throw new Error(detail);
  }

  // 204 No Content — return null
  if (response.status === 204) return null;

  return response.json();
}

// ===== Threads =====

/**
 * Fetch a list of threads.
 * @param {Object} params - Optional filters: domainSlug, status, limit, offset
 * @returns {Promise<Array>} Array of ThreadSummary objects
 */
async function getThreads({ domainSlug, status, limit = 20, offset = 0 } = {}) {
  const params = new URLSearchParams();
  if (domainSlug) params.set("domain_slug", domainSlug);
  if (status)     params.set("status", status);
  params.set("limit", limit);
  params.set("offset", offset);

  return apiFetch(`/threads?${params}`);
}

/**
 * Fetch a single thread with full detail (posts, proposals, my_signal).
 * @param {string} threadId - UUID
 */
async function getThread(threadId) {
  return apiFetch(`/threads/${threadId}`);
}

// ===== Signals =====

/**
 * Cast or update the current user's signal on a thread.
 * @param {string} threadId - UUID
 * @param {string} signalType - "support" | "concern" | "need_info" | "block"
 * @param {string|null} note - Optional 280-char note
 */
async function castSignal(threadId, signalType, note = null) {
  return apiFetch(`/signals`, {
    method: "POST",
    body: JSON.stringify({ thread_id: threadId, signal_type: signalType, note }),
  });
}

// ===== Posts =====

/**
 * Fetch top-level posts for a thread with replies nested (max 2 levels).
 * @param {string} threadId - UUID
 */
async function getPosts(threadId) {
  return apiFetch(`/posts/thread/${threadId}`);
}

/**
 * Create a post in a thread.
 * @param {string} threadId - UUID
 * @param {string} body - Post content
 * @param {string|null} parentId - UUID of parent post for replies
 */
async function createPost(threadId, body, parentId = null) {
  return apiFetch(`/posts`, {
    method: "POST",
    body: JSON.stringify({ thread_id: threadId, body, parent_id: parentId }),
  });
}

// ===== Proposals =====

async function getProposals(threadId) {
  return apiFetch(`/proposals/thread/${threadId}`);
}

async function createProposal(threadId, title, description) {
  return apiFetch(`/proposals?thread_id=${encodeURIComponent(threadId)}`, {
    method: "POST",
    body: JSON.stringify({ title, description }),
  });
}

// ===== Thread phase =====

/**
 * Advance a thread to the next phase (facilitator only).
 * @param {string} threadId - UUID
 * @param {string} targetStatus - e.g. "deliberating"
 * @param {string} reason - Required, recorded in audit log
 */
async function advancePhase(threadId, targetStatus, reason) {
  return apiFetch(`/threads/${threadId}/advance`, {
    method: "PATCH",
    body: JSON.stringify({ target_status: targetStatus, reason }),
  });
}

// ===== Votes =====

/**
 * Cast a vote on a proposal.
 * @param {string} proposalId - UUID
 * @param {string} choice - "YES" | "NO" | "ABSTAIN"
 */
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
