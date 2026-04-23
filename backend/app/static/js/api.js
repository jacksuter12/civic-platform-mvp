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

  if (token && auth.isTokenExpired()) {
    auth.clearToken();
    throw new Error("Session expired — please sign in again.");
  }

  const headers = {
    "Content-Type": "application/json",
    ...(token ? { "Authorization": `Bearer ${token}` } : {}),
    ...(options.headers || {}),
  };

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (!response.ok) {
    if (response.status === 401) {
      auth.clearToken();
      throw new Error("Session expired — please sign in again.");
    }
    let detail = `HTTP ${response.status}`;
    try {
      const err = await response.json();
      if (typeof err.detail === "string") {
        detail = err.detail;
      } else if (Array.isArray(err.detail)) {
        // FastAPI 422 validation errors: each item has loc + msg
        detail = err.detail.map(e => {
          const field = e.loc ? e.loc.slice(1).join(".") : "";
          return field ? `${field}: ${e.msg}` : e.msg;
        }).join("; ");
      }
    } catch (_) {}
    throw new Error(detail);
  }

  if (response.status === 204) return null;
  return response.json();
}

// ===== Threads =====

async function getThreads({ communitySlug, domainSlug, status, limit = 20, offset = 0 } = {}) {
  const params = new URLSearchParams();
  if (communitySlug) params.set("community_slug", communitySlug);
  if (domainSlug)    params.set("domain_slug", domainSlug);
  if (status)        params.set("status", status);
  params.set("limit", limit);
  params.set("offset", offset);
  return apiFetch(`/threads?${params}`);
}

async function getThread(threadId) {
  return apiFetch(`/threads/${threadId}`);
}

async function createThread(communityId, domainId, title, prompt, context) {
  return apiFetch("/threads", {
    method: "POST",
    body: JSON.stringify({ community_id: communityId, domain_id: domainId, title, prompt, context }),
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

// ===== Audit Log =====

async function getAuditLog({ eventType, targetType, targetId, actorId, limit = 50, offset = 0 } = {}) {
  const params = new URLSearchParams();
  if (eventType)  params.set("event_type",  eventType);
  if (targetType) params.set("target_type", targetType);
  if (targetId)   params.set("target_id",   targetId);
  if (actorId)    params.set("actor_id",    actorId);
  params.set("limit",  limit);
  params.set("offset", offset);
  return apiFetch(`/audit?${params}`);
}

// ===== Domains =====

async function getDomains(communitySlug) {
  const params = communitySlug ? `?community_slug=${encodeURIComponent(communitySlug)}` : "";
  return apiFetch(`/domains${params}`);
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

async function submitFacilitatorRequest(reason, communityId = null) {
  const body = { reason };
  if (communityId) body.community_id = communityId;
  return apiFetch("/auth/facilitator-request", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

async function getMyFacilitatorRequest() {
  return apiFetch("/auth/facilitator-request");
}

async function getFacilitatorRequests(communitySlug = null) {
  const params = communitySlug ? `?community_slug=${encodeURIComponent(communitySlug)}` : "";
  return apiFetch(`/admin/facilitator-requests${params}`);
}

async function approveFacilitatorRequest(requestId) {
  return apiFetch(`/admin/facilitator-requests/${requestId}/approve`, { method: "POST" });
}

async function denyFacilitatorRequest(requestId) {
  return apiFetch(`/admin/facilitator-requests/${requestId}/deny`, { method: "POST" });
}

// ===== Annotations =====

/**
 * List annotations for a target. Public — no auth required.
 * @param {string} targetType - e.g. "wiki"
 * @param {string} targetId   - e.g. the article slug
 * @param {boolean} includeDeleted - admin only; ignored for non-admins
 */
async function listAnnotations(targetType, targetId, includeDeleted = false) {
  const params = new URLSearchParams({
    target_type: targetType,
    target_id: targetId,
    include_deleted: includeDeleted,
  });
  return apiFetch(`/annotations?${params}`);
}

/**
 * Create an annotation. Requires annotator or admin role.
 * @param {{targetType, targetId, anchorData, body, parentId}} opts
 */
async function createAnnotation({ targetType, targetId, anchorData, body, parentId = null }) {
  return apiFetch("/annotations", {
    method: "POST",
    body: JSON.stringify({
      target_type: targetType,
      target_id: targetId,
      anchor_data: anchorData,
      body,
      parent_id: parentId,
    }),
  });
}

/**
 * Edit an annotation's body. Author or admin only.
 * @param {string} annotationId
 * @param {string} body
 */
async function updateAnnotation(annotationId, body) {
  return apiFetch(`/annotations/${annotationId}`, {
    method: "PATCH",
    body: JSON.stringify({ body }),
  });
}

/**
 * Soft-delete an annotation. Author or admin only.
 * @param {string} annotationId
 */
async function deleteAnnotation(annotationId) {
  return apiFetch(`/annotations/${annotationId}`, { method: "DELETE" });
}

/**
 * Add or replace a reaction on an annotation. Annotator or admin only.
 * @param {string} annotationId
 * @param {"endorse"|"needs_work"} reaction
 */
async function addReaction(annotationId, reaction) {
  return apiFetch(`/annotations/${annotationId}/reactions`, {
    method: "POST",
    body: JSON.stringify({ reaction }),
  });
}

/**
 * Remove the current user's reaction from an annotation. Idempotent.
 * @param {string} annotationId
 */
async function removeReaction(annotationId) {
  return apiFetch(`/annotations/${annotationId}/reactions`, { method: "DELETE" });
}

// ===== Admin — Annotator capability =====

/**
 * Grant annotator capability to a user.
 * Route: POST /admin/users/{userId}/annotator
 * @param {string} userId
 * @param {string|null} reason
 */
async function grantAnnotator(userId, reason = null) {
  return apiFetch(`/admin/users/${userId}/annotator`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

/**
 * Revoke annotator capability from a user.
 * Route: DELETE /admin/users/{userId}/annotator
 * @param {string} userId
 * @param {string|null} reason
 */
async function revokeAnnotator(userId, reason = null) {
  return apiFetch(`/admin/users/${userId}/annotator`, {
    method: "DELETE",
    body: JSON.stringify({ reason }),
  });
}

/**
 * List all users (admin only).
 * Route: GET /admin/users
 * @param {{ search?: string, limit?: number, offset?: number }} opts
 */
async function listUsers({ search = null, limit = 200, offset = 0 } = {}) {
  const params = new URLSearchParams({ limit, offset });
  if (search) params.set("search", search);
  return apiFetch(`/admin/users?${params}`);
}

// ===== Communities =====

async function getCommunity(slug) {
  return apiFetch(`/communities/${encodeURIComponent(slug)}`);
}

async function listCommunities() {
  return apiFetch("/communities");
}

async function joinCommunity(slug) {
  return apiFetch(`/communities/${encodeURIComponent(slug)}/join`, { method: "POST" });
}

async function getCommunityMembers(slug, { limit = 100, offset = 0 } = {}) {
  const params = new URLSearchParams({ limit, offset });
  return apiFetch(`/communities/${encodeURIComponent(slug)}/members?${params}`);
}

async function getCommunityAuditLog(slug, { eventType, targetType, targetId, actorId, limit = 50, offset = 0 } = {}) {
  const params = new URLSearchParams();
  if (eventType)  params.set("event_type",  eventType);
  if (targetType) params.set("target_type", targetType);
  if (targetId)   params.set("target_id",   targetId);
  if (actorId)    params.set("actor_id",    actorId);
  params.set("limit",  limit);
  params.set("offset", offset);
  return apiFetch(`/communities/${encodeURIComponent(slug)}/audit?${params}`);
}

async function createCommunity(data) {
  return apiFetch("/communities", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

async function updateCommunity(slug, data) {
  return apiFetch(`/communities/${encodeURIComponent(slug)}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

async function addCommunityMember(slug, email, tier = "registered") {
  return apiFetch(`/communities/${encodeURIComponent(slug)}/members`, {
    method: "POST",
    body: JSON.stringify({ email, tier }),
  });
}
