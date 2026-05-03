/**
 * proposal_anchor.js — Multi-strategy text anchoring for proposal annotations.
 *
 * Implements W3C Web Annotation Data Model selector array with two strategies:
 *   1. TextQuoteSelector  (primary — resilient to minor edits)
 *   2. TextPositionSelector (fallback — character offset based)
 *
 * Exposes window.ProposalAnchor. No CDN dependencies; all logic is self-contained.
 *
 * Design notes vs. the wiki AnnotationAnchor module:
 * - Serializes into { selector: [...] } (W3C format) instead of { type, selectors }
 * - applyHighlight handles cross-element ranges by walking text nodes individually
 * - Multiple spans per annotation share data-anno-id so they act as one highlight
 * - No async — all operations are synchronous DOM/text-node walks
 */

(function () {
  'use strict';

  const CONTEXT_CHARS = 32; // prefix/suffix context length for TextQuoteSelector

  // ---------------------------------------------------------------------------
  // Text-node walking utilities
  // ---------------------------------------------------------------------------

  /**
   * Iterate all text nodes inside root in document order.
   * @param {Node} root
   * @returns {Generator<Text>}
   */
  function* _textNodes(root) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
    let node;
    while ((node = walker.nextNode())) {
      yield node;
    }
  }

  /**
   * Compute the absolute character offset of (container, offset) within root.
   * Counts characters across text nodes in document order.
   */
  function _absoluteOffset(root, container, offset) {
    let pos = 0;
    for (const node of _textNodes(root)) {
      if (node === container) return pos + offset;
      pos += node.textContent.length;
    }
    return pos; // past end — shouldn't happen for valid ranges
  }

  /**
   * Build a DOM Range from absolute character start/end offsets within root.
   * Returns null if offsets are out of bounds.
   */
  function _rangeFromOffsets(root, start, end) {
    let pos = 0;
    let startNode = null, startOff = 0;
    let endNode = null, endOff = 0;

    for (const node of _textNodes(root)) {
      const len = node.textContent.length;

      if (startNode === null && pos + len > start) {
        startNode = node;
        startOff = start - pos;
      }
      // Note: >= so a zero-length end at the start of a node is handled
      if (endNode === null && pos + len >= end) {
        endNode = node;
        endOff = end - pos;
        break;
      }
      pos += len;
    }

    if (!startNode || !endNode) return null;

    try {
      const range = document.createRange();
      range.setStart(startNode, startOff);
      range.setEnd(endNode, endOff);
      return range;
    } catch (_) {
      return null;
    }
  }

  // ---------------------------------------------------------------------------
  // TextQuoteSelector
  // ---------------------------------------------------------------------------

  function _makeTextQuoteSelector(range, root) {
    const exact = range.toString();
    const fullText = root.textContent;
    const start = _absoluteOffset(root, range.startContainer, range.startOffset);
    const end = start + exact.length;
    return {
      type: 'TextQuoteSelector',
      exact,
      prefix: fullText.substring(Math.max(0, start - CONTEXT_CHARS), start),
      suffix: fullText.substring(end, end + CONTEXT_CHARS),
    };
  }

  function _matchTextQuote(selector, root) {
    const { exact, prefix = '', suffix = '' } = selector;
    const fullText = root.textContent;
    let searchFrom = 0;

    while (searchFrom < fullText.length) {
      const idx = fullText.indexOf(exact, searchFrom);
      if (idx === -1) break;

      const actualPrefix = fullText.slice(Math.max(0, idx - prefix.length), idx);
      const actualSuffix = fullText.slice(idx + exact.length, idx + exact.length + suffix.length);

      const prefixOk = !prefix || actualPrefix === prefix;
      const suffixOk = !suffix || actualSuffix === suffix;

      if (prefixOk && suffixOk) {
        return _rangeFromOffsets(root, idx, idx + exact.length);
      }
      searchFrom = idx + 1;
    }
    return null;
  }

  // ---------------------------------------------------------------------------
  // TextPositionSelector
  // ---------------------------------------------------------------------------

  function _makeTextPositionSelector(range, root) {
    const start = _absoluteOffset(root, range.startContainer, range.startOffset);
    const end = _absoluteOffset(root, range.endContainer, range.endOffset);
    return { type: 'TextPositionSelector', start, end };
  }

  function _matchTextPosition(selector, root) {
    const total = root.textContent.length;
    if (selector.start >= total || selector.end > total) return null;
    return _rangeFromOffsets(root, selector.start, selector.end);
  }

  // ---------------------------------------------------------------------------
  // Highlight application — handles cross-element ranges
  // ---------------------------------------------------------------------------

  /**
   * Wrap selected text in highlight spans. A Range that crosses element
   * boundaries can't be wrapped with surroundContents(), so we walk text
   * nodes inside the range and wrap each chunk individually. All spans share
   * the same data-anno-id so they behave as one logical highlight.
   *
   * @param {Range}   range
   * @param {string}  annotationId
   * @param {string}  [highlightClass]
   */
  function _applyHighlight(range, annotationId, highlightClass) {
    highlightClass = highlightClass || 'proposal-annotation-highlight';
    if (!range || range.collapsed) return;

    // Collect text nodes that fall within the range
    const walker = document.createTreeWalker(
      range.commonAncestorContainer.nodeType === Node.TEXT_NODE
        ? range.commonAncestorContainer.parentNode
        : range.commonAncestorContainer,
      NodeFilter.SHOW_TEXT,
      null
    );

    const textNodes = [];
    let node;
    while ((node = walker.nextNode())) {
      if (range.intersectsNode(node)) {
        textNodes.push(node);
      }
    }

    // Wrap each text node chunk in a span
    for (const textNode of textNodes) {
      // Determine the slice of this text node that falls within the range
      const nodeStart = (textNode === range.startContainer) ? range.startOffset : 0;
      const nodeEnd = (textNode === range.endContainer)
        ? range.endOffset
        : textNode.textContent.length;

      if (nodeStart >= nodeEnd) continue;

      // Split the text node if needed to isolate just the highlighted portion
      let target = textNode;
      if (nodeStart > 0) {
        target = textNode.splitText(nodeStart);
      }
      if (nodeEnd - nodeStart < target.textContent.length) {
        target.splitText(nodeEnd - nodeStart);
      }

      // Wrap in highlight span
      const span = document.createElement('span');
      span.className = highlightClass;
      span.dataset.annoId = annotationId;
      target.parentNode.insertBefore(span, target);
      span.appendChild(target);
    }
  }

  /**
   * Remove all highlight spans for a given annotation ID.
   * Restores the wrapped text nodes back into the DOM.
   * @param {string} annotationId
   */
  function _removeHighlight(annotationId) {
    const spans = document.querySelectorAll(
      `[data-anno-id="${CSS.escape(annotationId)}"]`
    );
    spans.forEach(span => {
      const parent = span.parentNode;
      while (span.firstChild) {
        parent.insertBefore(span.firstChild, span);
      }
      parent.removeChild(span);
      parent.normalize();
    });
  }

  /**
   * Scroll the document pane so the first highlight span for annotationId
   * is visible, then briefly flash all matching spans.
   * @param {string} annotationId
   */
  function _scrollTo(annotationId) {
    const spans = document.querySelectorAll(
      `.proposal-annotation-highlight[data-anno-id="${CSS.escape(annotationId)}"]`
    );
    if (!spans.length) return;
    spans[0].scrollIntoView({ behavior: 'smooth', block: 'center' });
    spans.forEach(s => s.classList.add('proposal-annotation-highlight-flash'));
    setTimeout(() => {
      spans.forEach(s => s.classList.remove('proposal-annotation-highlight-flash'));
    }, 600);
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  window.ProposalAnchor = {

    /**
     * Serialize a DOM Range into a W3C anchor object with a selector array.
     *
     * @param {Range}   range   - The selection range
     * @param {Element} rootEl  - The root element containing the document text
     * @returns {{ selector: Array }} W3C selector array
     */
    serialize(range, rootEl) {
      if (!range || !rootEl || range.collapsed) return null;
      return {
        selector: [
          _makeTextQuoteSelector(range, rootEl),
          _makeTextPositionSelector(range, rootEl),
        ],
      };
    },

    /**
     * Deserialize an anchor object back to a DOM Range. Tries TextQuote first
     * (resilient to minor edits), then TextPosition as fallback.
     *
     * @param {Object}  anchor  - { selector: [...] } or legacy shape
     * @param {Element} rootEl  - The root element
     * @returns {Range|null}    - null means the anchor is orphaned
     */
    deserialize(anchor, rootEl) {
      if (!anchor || !rootEl) return null;

      const selectors = anchor.selector || [];

      const quoteSelector = selectors.find(s => s.type === 'TextQuoteSelector');
      if (quoteSelector) {
        const range = _matchTextQuote(quoteSelector, rootEl);
        if (range) return range;
      }

      const posSelector = selectors.find(s => s.type === 'TextPositionSelector');
      if (posSelector) {
        const range = _matchTextPosition(posSelector, rootEl);
        if (range) return range;
      }

      return null; // all strategies failed — anchor is orphaned
    },

    /**
     * Apply a highlight to a range. Wraps text nodes in spans with
     * class="proposal-annotation-highlight" and data-anno-id. Handles
     * cross-element ranges correctly.
     *
     * @param {Range}   range
     * @param {string}  annotationId
     * @param {string}  [highlightClass]
     */
    applyHighlight(range, annotationId, highlightClass) {
      _applyHighlight(range, annotationId, highlightClass);
    },

    /**
     * Remove all highlight spans for the given annotation ID.
     * @param {string} annotationId
     */
    removeHighlight(annotationId) {
      _removeHighlight(annotationId);
    },

    /**
     * Scroll the document so the first highlight for annotationId is visible.
     * @param {string} annotationId
     */
    scrollTo(annotationId) {
      _scrollTo(annotationId);
    },
  };

})();
