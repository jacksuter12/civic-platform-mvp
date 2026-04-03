/**
 * config.js — Supabase connection config and browser client.
 *
 * Loaded only on signin.html (before auth.js). Not needed on other pages
 * since they use only the stored JWT via auth.js, not the Supabase SDK.
 *
 * Exposes: supabaseClient (global)
 */

const SUPABASE_URL     = "https://ctdlkwsgoqymonyvjpmu.supabase.co";
const SUPABASE_ANON_KEY = "sb_publishable_EniY88UvJMzNdCpmd73yRw_gMfETh5p";

const { createClient } = window.supabase;
const supabaseClient = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
