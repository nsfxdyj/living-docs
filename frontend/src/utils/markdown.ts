// Markdown rendering pipeline: markdown-it for parsing, highlight.js for
// fenced code blocks, and DOMPurify to sanitize the final HTML.
import hljs from 'highlight.js'
import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'

import 'highlight.js/styles/github.css'

const md = new MarkdownIt({
  html: false, // never pass raw HTML through; DOMPurify is the second net
  linkify: true,
  highlight(code, lang) {
    if (lang && hljs.getLanguage(lang)) {
      const { value } = hljs.highlight(code, { language: lang })
      return `<pre><code class="hljs language-${lang}">${value}</code></pre>`
    }
    const { value } = hljs.highlightAuto(code)
    return `<pre><code class="hljs">${value}</code></pre>`
  },
})

/** Render Markdown source to sanitized HTML safe for v-html. */
export function renderMarkdown(source: string): string {
  return DOMPurify.sanitize(md.render(source))
}
