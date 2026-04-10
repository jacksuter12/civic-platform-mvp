/**
 * annotation_anchor.js — Anchoring layer for the annotation system.
 *
 * Produces and resolves W3C Web Annotation Data Model selectors
 * (TextQuoteSelector, TextPositionSelector) using native browser APIs.
 * No external CDN dependency.
 *
 * Loaded as <script type="module"> so it can set window.AnnotationAnchor
 * after the document has been parsed. Regular scripts loaded after this
 * module can call its methods via window.AnnotationAnchor.
 */

// ---------------------------------------------------------------------------
// Internal helpers — text-node walking
// ---------------------------------------------------------------------------

/**
 * Walk all text nodes inside root in document order, yielding each one.
 */
function* _textNodes(root) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
  let node;
  while ((node = walker.nextNode())) {
    yield node;
  }
}

/**
 * Return the absolute character offset of a boundary point (container, offset)
 * within root's text content, measured across text nodes in document order.
 */
function _absoluteOffset(root, container, offset) {
  let pos = 0;
  for (const node of _textNodes(root)) {
    if (node === container) return pos + offset;
    pos += node.textContent.length;
  }
  return pos;
}

/**
 * Build a DOM Range from absolute start/end character offsets within root.
 * Returns null if the offsets can't be resolved (e.g. content changed).
 */
function _rangeFromOffsets(root, start, end) {
  let pos = 0;
  let startNode = null, startOff = 0;
  let endNode   = null, endOff   = 0;

  for (const node of _textNodes(root)) {
    const len = node.textContent.length;

    if (startNode === null && pos + len > start) {
      startNode = node;
      startOff  = start - pos;
    }
    if (endNode === null && pos + len >= end) {
      endNode = node;
      endOff  = end - pos;
      break;
    }
    pos += len;
  }

  if (!startNode || !endNode) return null;

  const range = document.createRange();
  range.setStart(startNode, startOff);
  range.setEnd(endNode, endOff);
  return range;
}

// ---------------------------------------------------------------------------
// Selector producers (describe a Range as serialisable data)
// ---------------------------------------------------------------------------

function _describeTextPosition(range, root) {
  const start = _absoluteOffset(root, range.startContainer, range.startOffset);
  const end   = _absoluteOffset(root, range.endContainer,   range.endOffset);
  return { type: "TextPositionSelector", start, end };
}

const CONTEXT = 32; // characters of prefix/suffix context to store

function _describeTextQuote(range, root) {
  const exact    = range.toString();
  const fullText = root.textContent;
  const start    = _absoluteOffset(root, range.startContainer, range.startOffset);
  const end      = start + exact.length;

  return {
    type:   "TextQuoteSelector",
    exact,
    prefix: fullText.substring(Math.max(0, start - CONTEXT), start),
    suffix: fullText.substring(end, end + CONTEXT),
  };
}

// ---------------------------------------------------------------------------
// Selector matchers (resolve stored data back to a Range)
// ---------------------------------------------------------------------------

/**
 * Try to find `selector.exact` in root, disambiguated by prefix/suffix.
 * Returns a Range or null.
 */
function _matchTextQuote(selector, root) {
  const { exact, prefix = "", suffix = "" } = selector;
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

/**
 * Resolve a TextPositionSelector back to a Range. Returns null if out of bounds.
 */
function _matchTextPosition(selector, root) {
  const total = root.textContent.length;
  if (selector.start >= total || selector.end > total) return null;
  return _rangeFromOffsets(root, selector.start, selector.end);
}

// ---------------------------------------------------------------------------
// Public API — window.AnnotationAnchor
// ---------------------------------------------------------------------------

window.AnnotationAnchor = {

  /**
   * Produce a serialisable anchor descriptor from a DOM Range inside rootElement.
   *
   * @param {Range}   range
   * @param {Element} rootElement
   * @returns {Promise<{type: string, selectors: Array}>}
   */
  async createAnchorFromSelection(range, rootElement) {
    return {
      type: "text-range",
      selectors: [
        _describeTextQuote(range, rootElement),
        _describeTextPosition(range, rootElement),
      ],
    };
  },

  /**
   * Produce a section-level anchor referencing an h2 by its id attribute.
   *
   * @param {string} sectionId
   * @returns {{type: string, section_id: string}}
   */
  createSectionAnchor(sectionId) {
    return { type: "section", section_id: sectionId };
  },

  /**
   * Resolve a stored anchor descriptor back to a DOM Range.
   *
   * For text-range anchors: tries TextQuoteSelector first (resilient to minor
   * edits), falls back to TextPositionSelector.
   * For section anchors: returns a Range covering the heading element.
   *
   * @param {Object}  anchorData
   * @param {Element} rootElement
   * @returns {Promise<Range|null>}
   */
  async resolveAnchor(anchorData, rootElement) {
    if (!anchorData) return null;

    if (anchorData.type === "section") {
      const el = document.getElementById(anchorData.section_id);
      if (!el) return null;
      const range = document.createRange();
      range.selectNodeContents(el);
      return range;
    }

    if (anchorData.type === "text-range") {
      const selectors = anchorData.selectors || [];
      const quoteSelector = selectors.find((s) => s.type === "TextQuoteSelector");
      const posSelector   = selectors.find((s) => s.type === "TextPositionSelector");

      if (quoteSelector) {
        const range = _matchTextQuote(quoteSelector, rootElement);
        if (range) return range;
      }

      if (posSelector) {
        const range = _matchTextPosition(posSelector, rootElement);
        if (range) return range;
      }
    }

    return null;
  },

  /**
   * Return the annotatable root element on the current page, or null.
   */
  getAnnotatableRoot() {
    return document.querySelector(
      "[data-annotation-target-type][data-annotation-target-id]"
    );
  },

  /**
   * Return {targetType, targetId} from the annotatable root's data attributes,
   * or null if the page has no annotatable root.
   */
  getCurrentTarget() {
    const el = this.getAnnotatableRoot();
    if (!el) return null;
    return {
      targetType: el.dataset.annotationTargetType,
      targetId:   el.dataset.annotationTargetId,
    };
  },
};
