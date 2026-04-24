/**
 * toc.js — Table of contents module for the proposal review page.
 *
 * Exposes window.Toc. Call Toc.init() after the document content is injected.
 * Builds TOC entries from h2/h3 elements in sourceEl and syncs active state
 * via IntersectionObserver.
 */

(function () {
  'use strict';

  let _containerEl = null;
  let _sourceEl = null;
  let _observer = null;
  let _isOpen = true;

  function _buildEntries() {
    const headings = _sourceEl.querySelectorAll('h2, h3');
    _containerEl.innerHTML = '';
    const entries = [];

    headings.forEach((h) => {
      if (!h.id) return;
      const a = document.createElement('a');
      a.href = '#' + h.id;
      a.className = h.tagName === 'H2'
        ? 'pr-toc-item'
        : 'pr-toc-item pr-toc-item--sub';
      a.textContent = h.textContent;
      a.dataset.tocId = h.id;
      a.addEventListener('click', (e) => {
        e.preventDefault();
        h.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
      _containerEl.appendChild(a);
      entries.push({ id: h.id, el: h, link: a });
    });

    return entries;
  }

  function _setupScrollSync(entries) {
    if (_observer) _observer.disconnect();
    _observer = new IntersectionObserver(
      (observed) => {
        observed.forEach((entry) => {
          if (!entry.isIntersecting) return;
          const id = entry.target.id;
          entries.forEach((e) => {
            e.link.classList.toggle('is-active', e.id === id);
          });
        });
      },
      {
        rootMargin: '-80px 0px -70% 0px',
        threshold: 0,
      }
    );
    entries.forEach((e) => _observer.observe(e.el));
  }

  window.Toc = {
    init({ containerEl, sourceEl }) {
      _containerEl = containerEl;
      _sourceEl = sourceEl;
      const entries = _buildEntries();
      if (entries.length > 0) {
        _setupScrollSync(entries);
      } else {
        _containerEl.innerHTML = '<div class="pr-toc-empty">No sections.</div>';
      }
    },
    toggle() {
      const panel = document.getElementById('pr-toc');
      if (!panel) return;
      _isOpen = !_isOpen;
      panel.classList.toggle('is-open', _isOpen);
    },
    get isOpen() { return _isOpen; },
  };
})();
