# Vendored JavaScript Dependencies

## Apache Annotator

Not vendored — loaded at runtime from `https://esm.sh/@apache-annotator/dom@0.2.0`.

**Source:** https://esm.sh/@apache-annotator/dom@0.2.0  
**npm package:** @apache-annotator/dom@0.2.0  
**License:** Apache-2.0  
**Project:** https://annotator.apache.org/  
**Why:** Implements W3C Web Annotation Data Model TextQuoteSelector and
TextPositionSelector algorithms. Loaded as an ES module via esm.sh because
the package ships ESM-only (no UMD/IIFE bundle). The module is loaded in
annotation_anchor.js via `<script type="module">`.

If the esm.sh CDN becomes unavailable, vendor the bundle by downloading:
  curl -sL "https://esm.sh/@apache-annotator/dom@0.2.0/es2022/dom.mjs" \
       -o annotation_apache_dom.mjs
and update the import URL in annotation_anchor.js to `/static/js/vendor/annotation_apache_dom.mjs`.
