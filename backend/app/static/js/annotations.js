/**
 * annotations.js — Orchestration layer for the annotation system.
 *
 * Coordinates between AnnotationAnchor (anchoring library wrapper) and the
 * API functions in api.js. Maintains an in-memory cache of annotations for
 * the current page.
 *
 * No DOM manipulation here. This module only fetches, caches, and resolves
 * annotations. The visible UI (drawer, highlights, indicators) is built in
 * a separate Prompt 5 module.
 *
 * Requires:
 *   - api.js      (loaded before this script)
 *   - annotation_anchor.js  (<script type="module">, sets window.AnnotationAnchor)
 *
 * Exposes: window.Annotations
 */
(function () {
  "use strict";

  // In-memory cache for the current page's annotations.
  let _cache = [];

  // ---------------------------------------------------------------------------
  // Internal helpers
  // ---------------------------------------------------------------------------

  function _target() {
    if (typeof AnnotationAnchor === "undefined") return null;
    return AnnotationAnchor.getCurrentTarget();
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  const Annotations = {

    /**
     * Initialise the annotation system for the current page.
     * Called at DOMContentLoaded. If the page has no annotatable root, does nothing.
     */
    async init() {
      const target = _target();
      if (!target) return;
      await this.fetchForCurrentPage();
    },

    /**
     * Fetch (or re-fetch) annotations for the current page and update the cache.
     * @returns {Promise<Array>} The updated annotation list.
     */
    async fetchForCurrentPage() {
      const target = _target();
      if (!target) return [];
      _cache = await listAnnotations(target.targetType, target.targetId);
      return _cache;
    },

    /**
     * Return cached annotations. Call fetchForCurrentPage() first to populate.
     * @returns {Array}
     */
    getAll() {
      return _cache;
    },

    /**
     * Return all annotations whose anchor_data matches the given anchor descriptor.
     * Matching is done by deep-comparing the JSON representation (both sides
     * are stringified to handle object equality). This is an exact match — for
     * approximate / resolved matching use resolveAnchorsToRanges().
     *
     * @param {Object} anchorData
     * @returns {Array}
     */
    getByAnchor(anchorData) {
      const key = JSON.stringify(anchorData);
      return _cache.filter((a) => JSON.stringify(a.anchor_data) === key);
    },

    /**
     * Create a new annotation on the current page.
     *
     * @param {Object}      anchorData   - From AnnotationAnchor.createAnchorFromSelection()
     * @param {string}      body         - Annotation text (1–5000 chars)
     * @param {string|null} parentId     - UUID of parent annotation for replies
     * @returns {Promise<Object>} The created annotation.
     */
    async create(anchorData, body, parentId = null) {
      const target = _target();
      if (!target) throw new Error("No annotatable target found on this page.");
      const annotation = await createAnnotation({
        targetType: target.targetType,
        targetId: target.targetId,
        anchorData,
        body,
        parentId,
      });
      // Add to cache immediately so callers see it without refetching.
      _cache = [..._cache, annotation];
      return annotation;
    },

    /**
     * Update the body of an existing annotation.
     *
     * @param {string} annotationId
     * @param {string} body
     * @returns {Promise<Object>} The updated annotation.
     */
    async update(annotationId, body) {
      const updated = await updateAnnotation(annotationId, body);
      _cache = _cache.map((a) => (a.id === annotationId ? updated : a));
      return updated;
    },

    /**
     * Soft-delete an annotation. The server replaces its body with a tombstone.
     *
     * @param {string} annotationId
     * @returns {Promise<void>}
     */
    async remove(annotationId) {
      await deleteAnnotation(annotationId);
      // Refetch to get the tombstoned state rather than keeping stale data.
      await this.fetchForCurrentPage();
    },

    /**
     * Add or replace a reaction on an annotation.
     *
     * @param {string} annotationId
     * @param {"endorse"|"needs_work"} reaction
     * @returns {Promise<Object>} Updated reaction state {endorse, needs_work, my_reaction}.
     */
    async react(annotationId, reaction) {
      return addReaction(annotationId, reaction);
    },

    /**
     * Remove the current user's reaction from an annotation.
     *
     * @param {string} annotationId
     * @returns {Promise<void>}
     */
    async unreact(annotationId) {
      return removeReaction(annotationId);
    },

    /**
     * Resolve all cached annotations to DOM Ranges.
     *
     * Returns a Map of annotation_id → Range (or null for orphaned anchors).
     * Orphaned anchors occur when the text the annotation was attached to has
     * changed or been removed since the annotation was created.
     *
     * @returns {Promise<Map<string, Range|null>>}
     */
    async resolveAnchorsToRanges() {
      if (typeof AnnotationAnchor === "undefined") return new Map();
      const root = AnnotationAnchor.getAnnotatableRoot();
      if (!root) return new Map();

      const results = new Map();
      await Promise.all(
        _cache.map(async (annotation) => {
          try {
            const range = await AnnotationAnchor.resolveAnchor(
              annotation.anchor_data,
              root
            );
            results.set(annotation.id, range);
          } catch (_) {
            results.set(annotation.id, null);
          }
        })
      );
      return results;
    },
  };

  window.Annotations = Annotations;
})();
