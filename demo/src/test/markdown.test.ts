import { describe, it, expect } from "vitest";
import { renderMarkdown } from "@/lib/markdown";

describe("renderMarkdown", () => {
  it("renders ATX headings at the correct level", () => {
    const html = renderMarkdown("# H1\n## H2\n### H3");
    expect(html).toContain("<h1>H1</h1>");
    expect(html).toContain("<h2>H2</h2>");
    expect(html).toContain("<h3>H3</h3>");
  });

  it("renders fenced code blocks with the language attribute", () => {
    const html = renderMarkdown("```python\nprint(\"hi\")\n```");
    expect(html).toContain('<pre><code data-lang="python">');
    expect(html).toContain("print(&quot;hi&quot;)");
  });

  it("renders inline code, bold, italic, and links", () => {
    const html = renderMarkdown("Plain `code`, **bold**, _italic_, [a](https://example.com).");
    expect(html).toContain("<code>code</code>");
    expect(html).toContain("<strong>bold</strong>");
    expect(html).toContain("<em>italic</em>");
    expect(html).toContain('href="https://example.com"');
  });

  it("renders unordered + ordered lists", () => {
    const ulHtml = renderMarkdown("- one\n- two");
    expect(ulHtml).toContain("<ul>");
    expect(ulHtml).toContain("<li>one</li>");
    const olHtml = renderMarkdown("1. one\n2. two");
    expect(olHtml).toContain("<ol>");
    expect(olHtml).toContain("<li>two</li>");
  });

  it("renders blockquotes and horizontal rules", () => {
    const html = renderMarkdown("> quoted\n\n---\n");
    expect(html).toContain("<blockquote>quoted</blockquote>");
    expect(html).toContain("<hr/>");
  });

  it("renders pipe tables with a divider row", () => {
    const html = renderMarkdown(`| h1 | h2 |\n|----|----|\n| a | b |\n`);
    expect(html).toContain("<table>");
    expect(html).toContain("<th>h1</th>");
    expect(html).toContain("<td>a</td>");
  });

  it("strips HTML comments without rendering them as paragraphs", () => {
    const html = renderMarkdown("<!-- secret -->\n# Title\n");
    expect(html).not.toContain("secret");
    expect(html).toContain("<h1>Title</h1>");
  });

  it("escapes HTML in plain text", () => {
    const html = renderMarkdown("a < b && c > d");
    expect(html).toContain("&lt;");
    expect(html).toContain("&amp;");
    expect(html).toContain("&gt;");
  });
});
