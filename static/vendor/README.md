Browser libraries used to render AI responses:

- `marked.umd.js`: Marked 18.1.2, MIT license (`LICENSE.marked`). Source: https://github.com/markedjs/marked
- `purify.min.js`: DOMPurify 3.4.17, Apache 2.0 / MPL 2.0 license (`LICENSE.dompurify`). Source: https://github.com/cure53/DOMPurify

Both files are served locally so Markdown rendering works with the existing static Vercel build. Marked parses Markdown; DOMPurify sanitizes the resulting HTML before it enters the page.
