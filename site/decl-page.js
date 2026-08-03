// notes#73: KaTeX pass for the prerendered per-declaration pages.
//
// The pages are self-contained static HTML: a crawler (and a reader with script disabled)
// gets the declaration's prose with the TeX delimiters intact, which is what makes them
// indexable at all. This file is the one client-side enhancement on top of that — it turns
// those delimiters into rendered math, using the same vendored KaTeX bundle and the same
// delimiter set as the SPA.
//
// It lives in its own file rather than an inline <script> because the pages ship the
// site's strict CSP (`script-src 'self'`, no 'unsafe-inline'), copied verbatim from
// index.html. Nothing here touches routing: these pages have no hash route and do not load
// app.js.
document.addEventListener('DOMContentLoaded', function () {
  if (typeof window.renderMathInElement !== 'function') return;
  window.renderMathInElement(document.getElementById('app') || document.body, {
    delimiters: [
      { left: '$$', right: '$$', display: true },
      { left: '$', right: '$', display: false },
    ],
    throwOnError: false,
  });
});
