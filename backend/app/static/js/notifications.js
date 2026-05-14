/**
 * notifications.js — /notifications page.
 * Fetches, renders, and manages the notification inbox.
 * Requires auth.js and nav.js to be loaded first.
 */
(function () {
  var PAGE_SIZE = 50;
  var currentFilter = "all";
  var currentOffset = 0;
  var totalCount = 0;

  function timeAgo(isoString) {
    var diff = Math.floor((Date.now() - new Date(isoString).getTime()) / 1000);
    if (diff < 60) return "just now";
    if (diff < 3600) return Math.floor(diff / 60) + "m ago";
    if (diff < 86400) return Math.floor(diff / 3600) + "h ago";
    if (diff < 604800) return Math.floor(diff / 86400) + "d ago";
    return new Date(isoString).toLocaleDateString();
  }

  function renderItem(n) {
    var unreadClass = n.is_read ? "" : " unread";
    var dotClass = n.is_read ? " read" : "";
    var href = n.link || "#";
    return (
      `<a class="notif-item${unreadClass}" href="${href}" data-id="${n.id}" data-read="${n.is_read}">` +
      `<span class="notif-dot${dotClass}"></span>` +
      `<span class="notif-body">` +
      `<span class="notif-headline">${escHtml(n.headline)}</span>` +
      `<span class="notif-time">${timeAgo(n.created_at)}</span>` +
      `</span></a>`
    );
  }

  function escHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function renderList(notifications, append) {
    var container = document.getElementById("notif-list-container");
    if (!append) container.innerHTML = "";

    if (notifications.length === 0 && !append) {
      container.innerHTML = `<div class="notif-empty">You have no ${currentFilter === "unread" ? "unread " : ""}notifications.</div>`;
      return;
    }

    var list = append
      ? container.querySelector(".notif-list") || createList(container)
      : createList(container);

    notifications.forEach(function (n) {
      list.insertAdjacentHTML("beforeend", renderItem(n));
    });

    // Attach click handlers for marking read
    list.querySelectorAll('.notif-item[data-read="false"]').forEach(function (el) {
      el.addEventListener("click", function (e) {
        e.preventDefault();
        var id = this.dataset.id;
        var href = this.getAttribute("href");
        markRead(id).then(function () {
          if (href && href !== "#") window.location.href = href;
        });
      });
    });

    // Load more button
    var existing = container.querySelector(".notif-load-more");
    if (existing) existing.remove();
    if (currentOffset < totalCount) {
      var btn = document.createElement("button");
      btn.className = "notif-load-more";
      btn.textContent = "Load more";
      btn.addEventListener("click", loadMore);
      container.appendChild(btn);
    }
  }

  function createList(container) {
    var list = document.createElement("div");
    list.className = "notif-list";
    container.appendChild(list);
    return list;
  }

  async function fetchNotifications(offset, append) {
    try {
      if (typeof auth === "undefined" || !auth.isSignedIn()) {
        window.location.href = "/signin";
        return;
      }
      var token = await auth.getToken();
      var unreadOnly = currentFilter === "unread" ? "&unread_only=true" : "";
      var resp = await fetch(
        `/api/v1/notifications?limit=${PAGE_SIZE}&offset=${offset}${unreadOnly}`,
        { headers: { Authorization: "Bearer " + token } }
      );
      if (!resp.ok) throw new Error("Failed to load notifications");
      var data = await resp.json();
      totalCount = data.total;
      currentOffset = offset + data.notifications.length;
      renderList(data.notifications, append);
    } catch (err) {
      document.getElementById("notif-list-container").innerHTML =
        `<div class="notif-empty">Failed to load notifications.</div>`;
    }
  }

  function loadMore() {
    fetchNotifications(currentOffset, true);
  }

  async function markRead(id) {
    try {
      var token = await auth.getToken();
      await fetch(`/api/v1/notifications/${id}/read`, {
        method: "PATCH",
        headers: { Authorization: "Bearer " + token },
      });
      var el = document.querySelector(`.notif-item[data-id="${id}"]`);
      if (el) {
        el.classList.remove("unread");
        el.dataset.read = "true";
        var dot = el.querySelector(".notif-dot");
        if (dot) dot.classList.add("read");
      }
    } catch (_) {}
  }

  async function markAllRead() {
    try {
      var token = await auth.getToken();
      await fetch("/api/v1/notifications/mark-all-read", {
        method: "POST",
        headers: { Authorization: "Bearer " + token },
      });
      // Refresh the list
      currentOffset = 0;
      fetchNotifications(0, false);
      // Reset bell
      var slot = document.getElementById("cpc-bell-slot");
      if (slot && typeof bellHTML === "function") slot.innerHTML = bellHTML(0);
    } catch (_) {}
  }

  function initTabs() {
    document.querySelectorAll(".notif-tab").forEach(function (tab) {
      tab.addEventListener("click", function () {
        document.querySelectorAll(".notif-tab").forEach(function (t) {
          t.classList.remove("active");
        });
        this.classList.add("active");
        currentFilter = this.dataset.filter;
        currentOffset = 0;
        fetchNotifications(0, false);
      });
    });
  }

  function init() {
    if (typeof auth !== "undefined" && !auth.isSignedIn()) {
      window.location.href = "/signin";
      return;
    }
    initTabs();
    document.getElementById("notif-mark-all").addEventListener("click", markAllRead);
    fetchNotifications(0, false);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
