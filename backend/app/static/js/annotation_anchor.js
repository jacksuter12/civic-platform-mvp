/**
 * annotation_anchor.js — Anchoring layer for the annotation system.
 *
 * Wraps the Apache Annotator library to produce and resolve W3C Web Annotation
 * Data Model selectors (TextQuoteSelector, TextPositionSelector), plus a
 * section-level fallback selector.
 *
 * Loaded as <script type="module"> so it can import native ESM. Sets
 * window.AnnotationAnchor so that regular scripts loaded after this module
 * can call its methods.
 *
 * Library: @apache-annotator/dom@0.2.0
 * Source:  https://cdn.jsdelivr.net/npm/@apache-annotator/dom@0.2.0/+esm
 * License: Apache-2.0
 *
 * Note: esm.sh was avoided because it incorrectly bundles a regenerator
 * polyfill for this package, causing a runtime error in modern browsers.
 * jsDelivr's +esm flag serves the package's own ESM output directly.
 */

import {
  describeTextQuote,
  createTextQuoteSelectorMatcher,
  describeTextPosition,
  createTextPositionSelectorMatcher,
} from 'https://cdn.jsdelivr.net/npm/@apache-annotator/dom@0.2.0/+esm';

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/**
 * Return the first item yielded by an async iterable, or null if empty.
 * @param {AsyncIterable<*>} asyncIter
 * @returns {Promise<*|null>}
 */
async function firstResult(asyncIter) {
  for await (const item of asyncIter) {
    return item;
  }
  return null;
}

// ---------------------------------------------------------------------------
// Public API — window.AnnotationAnchor
// ---------------------------------------------------------------------------

window.AnnotationAnchor = {

  /**
   * Produce a serializable anchor descriptor from a DOM Range inside rootElement.
   *
   * @param {Range}   range        - DOM Range from window.getSelection().getRangeAt(0)
   * @param {Element} rootElement  - The annotatable root element
   * @returns {Promise<{type: string, selectors: Array}>}
   */
  async createAnchorFromSelection(range, rootElement) {
    const [quoteSelector, posSelector] = await Promise.all([
      describeTextQuote(range, rootElement),
      describeTextPosition(range, rootElement),
    ]);

    return {
      type: 'text-range',
      selectors: [
        {
          type: 'TextQuoteSelector',
          exact: quoteSelector.exact,
          prefix: quoteSelector.prefix || '',
          suffix: quoteSelector.suffix || '',
        },
        {
          type: 'TextPositionSelector',
          start: posSelector.start,
          end: posSelector.end,
        },
      ],
    };
  },

  /**
   * Produce a section-level anchor referencing an h2 by its id attribute.
   *
   * @param {string} sectionId - The value of the id attribute on an h2 element
   * @returns {{type: string, section_id: string}}
   */
  createSectionAnchor(sectionId) {
    return { type: 'section', section_id: sectionId };
  },

  /**
   * Resolve a stored anchor descriptor back to a DOM Range.
   *
   * For text-range anchors: tries TextQuoteSelector first (resilient to minor
   * text edits), falls back to TextPositionSelector.
   * For section anchors: returns a Range covering the section element.
   *
   * @param {Object}  anchorData   - Descriptor from createAnchorFromSelection / createSectionAnchor
   * @param {Element} rootElement  - The annotatable root element
   * @returns {Promise<Range|null>}
   */
  async resolveAnchor(anchorData, rootElement) {
    if (!anchorData) return null;

    // Section anchor
    if (anchorData.type === 'section') {
      const el = document.getElementById(anchorData.section_id);
      if (!el) return null;
      const range = document.createRange();
      range.selectNodeContents(el);
      return range;
    }

    // Text-range anchor
    if (anchorData.type === 'text-range') {
      const selectors = anchorData.selectors || [];
      const quoteSelector = selectors.find((s) => s.type === 'TextQuoteSelector');
      const posSelector = selectors.find((s) => s.type === 'TextPositionSelector');

      // TextQuoteSelector first — more resilient to minor content edits
      if (quoteSelector) {
        try {
          const matcher = createTextQuoteSelectorMatcher(quoteSelector);
          const match = await firstResult(matcher(rootElement));
          if (match) return match;
        } catch (_) {
          // Fall through to position selector
        }
      }

      // TextPositionSelector fallback — precise but brittle if text shifts
      if (posSelector) {
        try {
          const matcher = createTextPositionSelectorMatcher(posSelector);
          const match = await firstResult(matcher(rootElement));
          if (match) return match;
        } catch (_) {
          // Anchor is orphaned
        }
      }
    }

    return null;
  },

  /**
   * Return the annotatable root element on the current page, or null.
   * Looks for [data-annotation-target-type][data-annotation-target-id].
   *
   * @returns {Element|null}
   */
  getAnnotatableRoot() {
    return document.querySelector(
      '[data-annotation-target-type][data-annotation-target-id]'
    );
  },

  /**
   * Return {targetType, targetId} from the annotatable root's data attributes,
   * or null if the page has no annotatable root.
   *
   * @returns {{targetType: string, targetId: string}|null}
   */
  getCurrentTarget() {
    const el = this.getAnnotatableRoot();
    if (!el) return null;
    return {
      targetType: el.dataset.annotationTargetType,
      targetId: el.dataset.annotationTargetId,
    };
  },
};
