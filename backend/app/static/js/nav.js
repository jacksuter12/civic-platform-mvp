/**
 * nav.js — Shared navigation bar injected into #nav-placeholder.
 * Requires auth.js to be loaded first on pages that use auth.
 * Uses no external libraries. Under 100 lines of JS.
 */
(function () {
  const LINKS = [
    { label: "Home",         href: "/" },
    { label: "How It Works", href: "/how-it-works" },
    { label: "Quiz",         href: "/quiz" },
    { label: "Communities",  href: "/communities" },
    { label: "Wiki",         href: "/wiki" },
    { label: "Audit Log",    href: "/audit" },
  ];

  function adminLink(user) {
    if (!user) return "";
    // Platform admin gets the global admin panel
    if (user.tier === "admin") {
      return `<a href="/admin" class="cpc-nav-link">Admin</a>`;
    }
    // Community facilitators/admins get their community admin panel
    const memberships = user.communityMemberships || user.community_memberships || [];
    const adminMembership = memberships.find(function (m) {
      return m.tier === "facilitator" || m.tier === "admin";
    });
    if (adminMembership) {
      const slug = adminMembership.communitySlug || adminMembership.community_slug;
      return `<a href="/c/${slug}/admin" class="cpc-nav-link">Community Admin</a>`;
    }
    return "";
  }

  function authLink() {
    try {
      if (typeof auth !== "undefined" && auth.isSignedIn()) {
        const user = auth.getUser();
        return adminLink(user) + `<a href="/account" class="cpc-nav-auth">Account</a>`;
      }
    } catch (_) {}
    return `<a href="/signin" class="cpc-nav-auth">Sign In</a>`;
  }

  function render() {
    const path = window.location.pathname;
    const linksHTML = LINKS.map(function (l) {
      const active = l.href === "/" ? path === "/" : path.startsWith(l.href);
      return `<a href="${l.href}" class="cpc-nav-link${active ? " cpc-active" : ""}">${l.label}</a>`;
    }).join("");

    return `
<style>
#cpc-nav {
  position: fixed; top: 0; left: 0; right: 0;
  background: #fff;
  border-bottom: 1px solid #e0e0e0;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  z-index: 1000;
  height: 56px;
}
.cpc-nav-inner {
  max-width: 1100px; margin: 0 auto; padding: 0 24px;
  height: 100%; display: flex; align-items: center; justify-content: space-between;
}
.cpc-nav-logo {
  font-size: 17px; font-weight: 600; color: #1a1a1a;
  text-decoration: none; letter-spacing: -0.01em; flex-shrink: 0;
}
.cpc-nav-logo:hover { color: #2a5c9a; text-decoration: none; }
.cpc-nav-links { display: flex; align-items: center; gap: 28px; }
.cpc-nav-link { font-size: 14px; color: #555; text-decoration: none; white-space: nowrap; }
.cpc-nav-link:hover { color: #1a1a1a; text-decoration: none; }
.cpc-active { color: #1a1a1a; border-bottom: 2px solid #2a5c9a; padding-bottom: 2px; }
.cpc-nav-auth { font-size: 14px; color: #2a5c9a; font-weight: 500; text-decoration: none; white-space: nowrap; }
.cpc-nav-auth:hover { text-decoration: underline; }
.cpc-hamburger { display: none; background: none; border: none; font-size: 22px; cursor: pointer; color: #1a1a1a; padding: 4px; line-height: 1; }
body { padding-top: 56px !important; }
@media (max-width: 768px) {
  .cpc-hamburger { display: block; }
  .cpc-nav-links {
    display: none; position: absolute; top: 56px; left: 0; right: 0;
    background: #fff; border-bottom: 1px solid #e0e0e0;
    flex-direction: column; align-items: stretch; gap: 0;
    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
  }
  .cpc-nav-links.open { display: flex; }
  .cpc-nav-link, .cpc-nav-auth { padding: 13px 24px; font-size: 15px; border-bottom: 1px solid #f0f0f0; }
  .cpc-active { border-bottom: 1px solid #f0f0f0; border-left: 3px solid #2a5c9a; padding-left: 21px; }
}
</style>
<nav id="cpc-nav">
  <div class="cpc-nav-inner">
    <a href="/" class="cpc-nav-logo">Civic Power</a>
    <div class="cpc-nav-links" id="cpc-nav-links">
      ${linksHTML}
      ${authLink()}
    </div>
    <button class="cpc-hamburger" id="cpc-hamburger" aria-label="Toggle navigation">☰</button>
  </div>
</nav>`;
  }

  function initTooltipToggle() {
    if (localStorage.getItem("tooltips-disabled") === "true") {
      document.body.classList.add("tooltips-disabled");
    }
  }

  function init() {
    const placeholder = document.getElementById("nav-placeholder");
    if (!placeholder) return;
    placeholder.outerHTML = render();
    document.getElementById("cpc-hamburger").addEventListener("click", function () {
      const links = document.getElementById("cpc-nav-links");
      links.classList.toggle("open");
      this.textContent = links.classList.contains("open") ? "✕" : "☰";
    });
    initTooltipToggle();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
