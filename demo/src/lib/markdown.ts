// Tiny markdown renderer for the /docs surface. Intentionally minimal — no full
// CommonMark engine — but covers the subset our content uses: ATX headings,
// fenced code blocks, inline code, bold, italics, links, lists, blockquotes,
// horizontal rules, and pipe tables.

function escapeHtml(input: string): string {
  return input
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function inline(text: string): string {
  let out = escapeHtml(text);
  out = out.replace(/`([^`]+)`/g, (_, code: string) => `<code>${code}</code>`);
  out = out.replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    (_, label: string, href: string) => {
      const safeHref = href.startsWith("http")
        ? href
        : href.startsWith("/")
        ? href
        : `#${href}`;
      return `<a href="${safeHref}" target="_blank" rel="noreferrer noopener">${label}</a>`;
    },
  );
  out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  out = out.replace(/(^|\W)\*([^*\s][^*]*)\*(?=\W|$)/g, "$1<em>$2</em>");
  out = out.replace(/(^|\W)_([^_\s][^_]*)_(?=\W|$)/g, "$1<em>$2</em>");
  return out;
}

interface TableState {
  active: boolean;
  headerEmitted: boolean;
  rows: string[];
}

export function renderMarkdown(src: string): string {
  // Strip HTML comments (we use them for SYNC IMPACT REPORT blocks).
  const cleaned = src.replace(/<!--[\s\S]*?-->/g, "");
  const lines = cleaned.split(/\r?\n/);
  const out: string[] = [];
  let inCode = false;
  let codeBuf: string[] = [];
  let codeLang = "";
  let inList: null | "ul" | "ol" = null;
  const table: TableState = { active: false, headerEmitted: false, rows: [] };

  const closeList = () => {
    if (inList) {
      out.push(`</${inList}>`);
      inList = null;
    }
  };

  const flushTable = () => {
    if (!table.active) return;
    out.push("</tbody></table>");
    table.active = false;
    table.headerEmitted = false;
    table.rows = [];
  };

  for (const raw of lines) {
    if (inCode) {
      if (raw.startsWith("```")) {
        out.push(
          `<pre><code${codeLang ? ` data-lang="${escapeHtml(codeLang)}"` : ""}>${escapeHtml(
            codeBuf.join("\n"),
          )}</code></pre>`,
        );
        codeBuf = [];
        codeLang = "";
        inCode = false;
      } else {
        codeBuf.push(raw);
      }
      continue;
    }
    if (raw.startsWith("```")) {
      closeList();
      flushTable();
      inCode = true;
      codeLang = raw.slice(3).trim();
      continue;
    }
    const headingMatch = /^(#{1,6})\s+(.*)$/.exec(raw);
    if (headingMatch && headingMatch[1] && headingMatch[2] !== undefined) {
      closeList();
      flushTable();
      const level = headingMatch[1].length;
      const text = inline(headingMatch[2].trim());
      out.push(`<h${level}>${text}</h${level}>`);
      continue;
    }
    if (/^\s*\|.*\|\s*$/.test(raw)) {
      closeList();
      const cells = raw.trim().slice(1, -1).split("|").map((c) => c.trim());
      if (
        !table.active &&
        !table.headerEmitted &&
        cells.every((c) => c.length > 0)
      ) {
        table.active = true;
        table.rows = [cells.map((c) => `<th>${inline(c)}</th>`).join("")];
        continue;
      }
      if (
        table.active &&
        !table.headerEmitted &&
        cells.every((c) => /^[-:]+$/.test(c))
      ) {
        out.push("<table><thead><tr>", ...table.rows, "</tr></thead><tbody>");
        table.headerEmitted = true;
        table.rows = [];
        continue;
      }
      if (table.active && table.headerEmitted) {
        out.push(
          `<tr>${cells.map((c) => `<td>${inline(c)}</td>`).join("")}</tr>`,
        );
        continue;
      }
    } else if (table.active) {
      flushTable();
    }
    if (/^\s*[-*]\s+/.test(raw)) {
      flushTable();
      if (inList !== "ul") {
        closeList();
        out.push("<ul>");
        inList = "ul";
      }
      out.push(`<li>${inline(raw.replace(/^\s*[-*]\s+/, ""))}</li>`);
      continue;
    }
    if (/^\s*\d+\.\s+/.test(raw)) {
      flushTable();
      if (inList !== "ol") {
        closeList();
        out.push("<ol>");
        inList = "ol";
      }
      out.push(`<li>${inline(raw.replace(/^\s*\d+\.\s+/, ""))}</li>`);
      continue;
    }
    if (/^\s*>\s?/.test(raw)) {
      closeList();
      flushTable();
      out.push(`<blockquote>${inline(raw.replace(/^\s*>\s?/, ""))}</blockquote>`);
      continue;
    }
    if (/^---+\s*$/.test(raw)) {
      closeList();
      flushTable();
      out.push("<hr/>");
      continue;
    }
    if (raw.trim() === "") {
      closeList();
      flushTable();
      continue;
    }
    closeList();
    out.push(`<p>${inline(raw)}</p>`);
  }
  if (inCode) {
    out.push(
      `<pre><code${codeLang ? ` data-lang="${escapeHtml(codeLang)}"` : ""}>${escapeHtml(
        codeBuf.join("\n"),
      )}</code></pre>`,
    );
  }
  closeList();
  flushTable();
  return out.join("\n");
}
