/**
 * utils.js — Shared formatting and DOM helpers.
 * No API calls or auth logic here.
 */

/**
 * Format an ISO timestamp to a human-readable relative time.
 * e.g. "3 hours ago", "2 days ago"
 */
function timeAgo(isoString) {
  const date = new Date(isoString);
  const now = new Date();
  const seconds = Math.floor((now - date) / 1000);

  if (seconds < 60)    return "just now";
  if (seconds < 3600)  return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

/**
 * Get the CSS class for a phase badge.
 * e.g. "open" → "phase-open"
 */
function phaseBadgeClass(status) {
  return `phase-badge phase-${status}`;
}

/**
 * Capitalize first letter of a string.
 * e.g. "need_info" → "Need info"
 */
function capitalize(str) {
  return str.charAt(0).toUpperCase() + str.slice(1).replace(/_/g, " ");
}

/**
 * Show an error message inside a container element.
 */
function showError(containerId, message) {
  const el = document.getElementById(containerId);
  if (el) {
    el.innerHTML = `<div class="error-message">${message}</div>`;
  }
}

/**
 * Signal type emoji/icon map for display.
 */
const SIGNAL_ICONS = {
  support:   "↑",
  concern:   "↓",
  need_info: "?",
  block:     "✕",
};

function esc(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

/**
 * Badge marking an account as software-operated.
 *
 * Takes any UserPublic-shaped object (post authors, proposal authors,
 * amendment authors, thread starters — they all use the same schema) and
 * returns markup, or "" for a human.
 *
 * Always rendered when the flag is set. This is the one label a reader must
 * never have to go looking for.
 */
function botBadge(user) {
  if (!user || !user.is_synthetic) return "";
  return `<span class="bot-badge" title="This account is operated by software, not a person.">Bot</span>`;
}
