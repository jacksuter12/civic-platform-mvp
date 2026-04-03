/**
 * auth.js — JWT storage and current-user state.
 *
 * The JWT from Supabase is stored in localStorage under "civic_token".
 * Pages check this on load to show/hide auth-gated UI.
 *
 * The Supabase client (supabaseClient) is only available on signin.html.
 * All other pages use only the storage layer below.
 */

const auth = {
  TOKEN_KEY: "civic_token",
  USER_KEY: "civic_user",
  // Supabase stores its own session under this key — clear it on sign-out
  // so /signin doesn't auto-sign-in after the user has signed out.
  SUPABASE_SESSION_KEY: "sb-ctdlkwsgoqymonyvjpmu-auth-token",

  getToken() {
    return localStorage.getItem(this.TOKEN_KEY);
  },

  setToken(jwt) {
    localStorage.setItem(this.TOKEN_KEY, jwt);
  },

  clearToken() {
    localStorage.removeItem(this.TOKEN_KEY);
    localStorage.removeItem(this.USER_KEY);
    localStorage.removeItem(this.SUPABASE_SESSION_KEY);
  },

  isSignedIn() {
    return !!this.getToken();
  },

  /**
   * Returns the cached user object (tier, display_name, etc.)
   * Populated after sign-in by calling GET /auth/me.
   */
  getUser() {
    const raw = localStorage.getItem(this.USER_KEY);
    return raw ? JSON.parse(raw) : null;
  },

  setUser(user) {
    localStorage.setItem(this.USER_KEY, JSON.stringify(user));
  },

  /**
   * Convenience: does the current user have at least a given tier?
   * Tier order: registered < participant < facilitator < admin
   */
  hasTier(required) {
    const order = ["registered", "participant", "facilitator", "admin"];
    const user = this.getUser();
    if (!user) return false;
    return order.indexOf(user.tier) >= order.indexOf(required);
  },
};
