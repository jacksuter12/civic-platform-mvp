/**
 * config.js — Supabase connection config and browser client.
 *
 * SUPABASE_URL and SUPABASE_ANON_KEY are injected by the FastAPI config_js
 * route in main.py (from environment variables). Do not hardcode them here.
 * This file is not served in production — the dynamic route takes priority.
 *
 * Exposes: supabaseClient (global)
 */

const { createClient } = window.supabase;
const supabaseClient = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
