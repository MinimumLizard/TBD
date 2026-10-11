import "server-only";

import { marked } from "marked";

// METHOD.md pages are written in this repository and reviewed (and copy-linted) like code; raw HTML in them is
// still escaped, so a method page can only ever produce Markdown's own elements.
export function methodHtml(markdown: string): string {
  const renderer = new marked.Renderer();
  renderer.html = ({ text }) => text.replace(/</g, "&lt;").replace(/>/g, "&gt;");
  return marked.parse(markdown, { renderer, async: false }) as string;
}
