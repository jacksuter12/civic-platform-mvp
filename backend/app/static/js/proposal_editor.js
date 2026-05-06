/**
 * proposal_editor.js — Shared markdown editor component.
 *
 * Usage:
 *   const inst = window.ProposalEditor.mount(containerEl, options);
 *   inst.destroy(); // cleans up event listeners and empties container
 *
 * options:
 *   initialTitle      string  (shown when showTitle=true)
 *   initialBody       string  markdown source
 *   showTitle         bool    show the title input (new-proposal page)
 *   showEditSummary   bool    show the edit-summary input (inline edit)
 *   submitLabel       string  text for the submit button
 *   onSubmit          async ({ title, body, edit_summary }) => void
 *   onCancel          () => void
 *
 * Calls global functions from api.js (previewProposalMarkdown).
 * No DOM manipulation outside the provided container element.
 */
(function () {
  'use strict';

  window.ProposalEditor = {
    mount(container, options) {
      const inst = new EditorInstance(container, options);
      inst.render();
      return inst;
    },
  };

  class EditorInstance {
    constructor(container, opts) {
      this.container = container;
      this.opts = opts;
      this.title = opts.initialTitle || '';
      this.body = opts.initialBody || '';
      this.editSummary = '';
      this.activeTab = 'write';
      this.previewDebounce = null;
      this._beforeUnload = null;
      this._initialSnapshot = this._snapshot();
    }

    render() {
      this.container.innerHTML = this._html();
      this._wireEvents();
    }

    _html() {
      const opts = this.opts;
      return `
        <div class="pe-editor">
          ${opts.showTitle ? `
            <label class="pe-label" for="pe-title">
              Title <span class="pe-hint">10–200 characters</span>
            </label>
            <input id="pe-title" class="pe-input" type="text"
                   minlength="10" maxlength="200" required
                   placeholder="A clear, specific title"
                   value="${escAttr(this.title)}">
          ` : ''}

          <div class="pe-tabs" role="tablist">
            <button type="button" class="pe-tab is-on" data-tab="write"
                    role="tab" aria-selected="true">Write</button>
            <button type="button" class="pe-tab" data-tab="preview"
                    role="tab" aria-selected="false">Preview</button>
          </div>

          <div class="pe-write-pane">
            <div class="pe-toolbar" role="toolbar" aria-label="Formatting">
              ${this._toolbarHtml()}
            </div>
            <textarea class="pe-textarea" id="pe-body"
                      placeholder="Use ## for section headings. Markdown is supported."
                      required>${escText(this.body)}</textarea>
            <p class="pe-counter" aria-live="polite">
              <span id="pe-char-count">${this.body.length}</span>&thinsp;/&thinsp;5,000 characters
            </p>
          </div>

          <div class="pe-preview-pane" hidden>
            <div class="pe-preview-doc">
              <p class="pe-preview-empty">Switch to Write to start.</p>
            </div>
          </div>

          ${opts.showEditSummary ? `
            <label class="pe-label" for="pe-summary">
              What changed?
              <span class="pe-hint">Required (10–200 chars). Visible in audit log and version history.</span>
            </label>
            <input id="pe-summary" class="pe-input" type="text"
                   minlength="10" maxlength="200" required
                   placeholder="e.g. Addressed Alice’s concern about the budget line">
          ` : ''}

          <div class="pe-actions">
            <button type="button" class="pe-btn-ghost" id="pe-cancel">Cancel</button>
            <button type="button" class="pe-btn-primary" id="pe-submit">
              ${escText(opts.submitLabel || 'Save')}
            </button>
            <span class="pe-status" id="pe-status" aria-live="polite"></span>
          </div>
        </div>
      `;
    }

    _toolbarHtml() {
      const buttons = [
        { action: 'h1',    label: 'H1',  title: 'Heading 1 (# )' },
        { action: 'h2',    label: 'H2',  title: 'Heading 2 (## )' },
        { action: 'h3',    label: 'H3',  title: 'Heading 3 (### )' },
        { divider: true },
        { action: 'bold',   label: 'B',   title: 'Bold (Ctrl+B)' },
        { action: 'italic', label: 'I',   title: 'Italic (Ctrl+I)' },
        { divider: true },
        { action: 'ul',    label: '•', title: 'Bullet list' },
        { action: 'ol',    label: '1.',  title: 'Numbered list' },
        { divider: true },
        { action: 'link',  label: '↗', title: 'Insert link' },
        { action: 'code',  label: '</>',  title: 'Code block' },
        { action: 'table', label: '⊤', title: 'Insert table' },
      ];
      return buttons.map(b => {
        if (b.divider) return '<span class="pe-toolbar-divider" aria-hidden="true"></span>';
        return `<button type="button" class="pe-toolbar-btn"
                        data-action="${b.action}"
                        title="${escAttr(b.title)}"
                        aria-label="${escAttr(b.title)}">${escText(b.label)}</button>`;
      }).join('');
    }

    _wireEvents() {
      const c = this.container;
      const ta = c.querySelector('#pe-body');

      // Tab switching
      c.querySelectorAll('.pe-tab').forEach(tab => {
        tab.addEventListener('click', () => this._switchTab(tab.dataset.tab));
      });

      // Toolbar buttons
      c.querySelectorAll('.pe-toolbar-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          this._applyAction(btn.dataset.action);
          ta.focus();
        });
      });

      // Body changes
      ta.addEventListener('input', () => {
        this.body = ta.value;
        c.querySelector('#pe-char-count').textContent = ta.value.length;
        if (this.activeTab === 'preview') {
          clearTimeout(this.previewDebounce);
          this.previewDebounce = setTimeout(() => this._refreshPreview(), 800);
        }
      });

      // Title input
      const titleEl = c.querySelector('#pe-title');
      if (titleEl) {
        titleEl.addEventListener('input', () => { this.title = titleEl.value; });
      }

      // Edit summary
      const summaryEl = c.querySelector('#pe-summary');
      if (summaryEl) {
        summaryEl.addEventListener('input', () => { this.editSummary = summaryEl.value; });
      }

      // Submit / Cancel
      c.querySelector('#pe-submit').addEventListener('click', () => this._submit());
      c.querySelector('#pe-cancel').addEventListener('click', () => this._cancel());

      // Keyboard shortcuts in textarea
      ta.addEventListener('keydown', (e) => {
        if ((e.metaKey || e.ctrlKey) && !e.shiftKey) {
          if (e.key === 'b') { e.preventDefault(); this._applyAction('bold'); }
          else if (e.key === 'i') { e.preventDefault(); this._applyAction('italic'); }
        }
      });

      // Paste HTML → Markdown conversion via Turndown (optional CDN dep)
      if (window.TurndownService && window.turndownPluginGfm) {
        const _td = new window.TurndownService({
          headingStyle: 'atx',
          codeBlockStyle: 'fenced',
          bulletListMarker: '-',
        });
        _td.use(window.turndownPluginGfm.gfm);
        ta.addEventListener('paste', (e) => {
          const html = e.clipboardData?.getData('text/html');
          if (!html || !html.trim()) return;
          e.preventDefault();
          this._insertAtCursor(ta, _td.turndown(html));
        });
      }

      // Warn before unload if dirty
      this._beforeUnload = (e) => {
        if (this._isDirty()) {
          e.preventDefault();
          e.returnValue = '';
        }
      };
      window.addEventListener('beforeunload', this._beforeUnload);
    }

    _applyAction(action) {
      const ta = this.container.querySelector('#pe-body');
      switch (action) {
        case 'h1':     return this._applyLinePrefix(ta, '# ');
        case 'h2':     return this._applyLinePrefix(ta, '## ');
        case 'h3':     return this._applyLinePrefix(ta, '### ');
        case 'bold':   return this._applyWrap(ta, '**', '**');
        case 'italic': return this._applyWrap(ta, '*', '*');
        case 'ul':     return this._applyLinePrefix(ta, '- ');
        case 'ol':     return this._applyLinePrefix(ta, '1. ', true);
        case 'link':   return this._applyLink(ta);
        case 'code':   return this._applyCodeBlock(ta);
        case 'table':  return this._applyTable(ta);
      }
    }

    _applyWrap(ta, before, after) {
      const start = ta.selectionStart;
      const end   = ta.selectionEnd;
      const sel   = ta.value.substring(start, end);
      ta.value = ta.value.substring(0, start) + before + sel + after + ta.value.substring(end);
      ta.setSelectionRange(start + before.length, start + before.length + sel.length);
      this._syncBody(ta);
    }

    _applyLinePrefix(ta, prefix, ordered = false) {
      const start     = ta.selectionStart;
      const end       = ta.selectionEnd;
      const lineStart = ta.value.lastIndexOf('\n', start - 1) + 1;
      let   lineEnd   = ta.value.indexOf('\n', end);
      if (lineEnd === -1) lineEnd = ta.value.length;

      const lines = ta.value.substring(lineStart, lineEnd).split('\n');
      const allHavePrefix = lines.every(l => l.startsWith(prefix));

      const transformed = lines.map((l, i) => {
        if (allHavePrefix) {
          return l.startsWith(prefix) ? l.slice(prefix.length) : l;
        }
        // Strip any existing heading/list prefix before applying the new one
        const stripped = l.replace(/^(#+\s|[-*]\s|\d+\.\s)/, '');
        return ordered ? `${i + 1}. ${stripped}` : prefix + stripped;
      }).join('\n');

      ta.value = ta.value.substring(0, lineStart) + transformed + ta.value.substring(lineEnd);
      ta.setSelectionRange(lineStart, lineStart + transformed.length);
      this._syncBody(ta);
    }

    _applyLink(ta) {
      const url = window.prompt('URL:', 'https://');
      if (url === null || url.trim() === '') return;
      const start = ta.selectionStart;
      const end   = ta.selectionEnd;
      const sel   = ta.value.substring(start, end) || 'link text';
      const repl  = `[${sel}](${url})`;
      ta.value = ta.value.substring(0, start) + repl + ta.value.substring(end);
      ta.setSelectionRange(start + 1, start + 1 + sel.length);
      this._syncBody(ta);
    }

    _applyCodeBlock(ta) {
      const start = ta.selectionStart;
      const end   = ta.selectionEnd;
      const sel   = ta.value.substring(start, end);
      const repl  = '\n```\n' + (sel || 'code') + '\n```\n';
      ta.value = ta.value.substring(0, start) + repl + ta.value.substring(end);
      const inner = start + 5;
      ta.setSelectionRange(inner, inner + (sel.length || 4));
      this._syncBody(ta);
    }

    _applyTable(ta) {
      const tmpl = '\n| Header 1 | Header 2 | Header 3 |\n|---|---|---|\n| cell | cell | cell |\n| cell | cell | cell |\n';
      const start = ta.selectionStart;
      ta.value = ta.value.substring(0, start) + tmpl + ta.value.substring(start);
      ta.setSelectionRange(start + 3, start + 11); // select "Header 1"
      this._syncBody(ta);
    }

    _syncBody(ta) {
      this.body = ta.value;
      this.container.querySelector('#pe-char-count').textContent = ta.value.length;
    }

    _insertAtCursor(ta, text) {
      const start = ta.selectionStart;
      const end   = ta.selectionEnd;
      ta.value = ta.value.substring(0, start) + text + ta.value.substring(end);
      const newPos = start + text.length;
      ta.setSelectionRange(newPos, newPos);
      this._syncBody(ta);
    }

    _switchTab(which) {
      this.activeTab = which;
      const c = this.container;
      c.querySelectorAll('.pe-tab').forEach(t => {
        const on = t.dataset.tab === which;
        t.classList.toggle('is-on', on);
        t.setAttribute('aria-selected', String(on));
      });
      c.querySelector('.pe-write-pane').hidden  = (which !== 'write');
      c.querySelector('.pe-preview-pane').hidden = (which !== 'preview');
      if (which === 'preview') this._refreshPreview();
    }

    async _refreshPreview() {
      const target = this.container.querySelector('.pe-preview-doc');
      const md = this.body.trim();
      if (!md) {
        target.innerHTML = '<p class="pe-preview-empty">Nothing to preview yet.</p>';
        return;
      }
      target.innerHTML = '<p class="pe-preview-loading">Rendering…</p>';
      try {
        const { html } = await previewProposalMarkdown(md);
        target.innerHTML = html || '<p class="pe-preview-empty">Empty output.</p>';
      } catch (err) {
        console.error('[ProposalEditor] preview error:', err);
        target.innerHTML = '<p class="pe-preview-error">Could not render preview.</p>';
      }
    }

    async _submit() {
      const opts = this.opts;
      this._clearStatus();

      if (opts.showTitle) {
        const t = this.title.trim();
        if (t.length < 10 || t.length > 200) {
          return this._showStatus('Title must be 10–200 characters.', 'error');
        }
      }
      if (this.body.trim().length < 50 || this.body.trim().length > 5000) {
        return this._showStatus('Description must be 50–5,000 characters.', 'error');
      }
      if (opts.showEditSummary && this.editSummary.trim().length < 10) {
        return this._showStatus('Edit summary required (min 10 characters).', 'error');
      }

      const btn = this.container.querySelector('#pe-submit');
      btn.disabled = true;
      this._showStatus('Saving…', 'pending');

      // Remove beforeunload before submitting so a successful navigation
      // (window.location.href in onSubmit) doesn't trigger the "unsaved changes" warning.
      // Re-added in the catch block if submit fails.
      const savedHandler = this._beforeUnload;
      if (savedHandler) {
        window.removeEventListener('beforeunload', savedHandler);
        this._beforeUnload = null;
      }

      try {
        await opts.onSubmit({
          title: this.title.trim(),
          body: this.body,
          edit_summary: this.editSummary.trim() || undefined,
        });
        this._initialSnapshot = this._snapshot();
        // Caller handles navigation or unmount on success
      } catch (err) {
        // Submit failed — restore the beforeunload guard
        this._beforeUnload = savedHandler;
        if (savedHandler) window.addEventListener('beforeunload', savedHandler);
        console.error('[ProposalEditor] submit error:', err);
        this._showStatus(err.message || 'Save failed.', 'error');
        btn.disabled = false;
      }
    }

    _cancel() {
      if (this._isDirty() && !window.confirm('Discard unsaved changes?')) return;
      this.opts.onCancel?.();
    }

    _isDirty() {
      return this._snapshot() !== this._initialSnapshot;
    }

    _snapshot() {
      return JSON.stringify({ title: this.title, body: this.body, summary: this.editSummary });
    }

    _showStatus(msg, kind) {
      const el = this.container.querySelector('#pe-status');
      if (!el) return;
      el.textContent = msg;
      el.dataset.kind = kind || '';
    }

    _clearStatus() {
      const el = this.container.querySelector('#pe-status');
      if (el) { el.textContent = ''; el.dataset.kind = ''; }
    }

    destroy() {
      if (this._beforeUnload) {
        window.removeEventListener('beforeunload', this._beforeUnload);
        this._beforeUnload = null;
      }
      clearTimeout(this.previewDebounce);
      this.container.innerHTML = '';
    }
  }

  function escAttr(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function escText(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }
})();
