/** @odoo-module **/

import { markup } from "@odoo/owl";
import { escape } from "@web/core/utils/strings";

/**
 * Minimal, safe Markdown renderer for assistant answers.
 *
 * The text is HTML-escaped first, then only a small whitelist of constructs is
 * turned into tags: paragraphs, line breaks, bullet / numbered lists (with one
 * level of nesting), headings (rendered as bold lines), **bold**, *italic*
 * and `code`.
 */
function renderInline(text) {
    return text
        .replace(/`([^`]+)`/g, "<code>$1</code>")
        .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
        .replace(/__([^_]+)__/g, "<strong>$1</strong>")
        .replace(/(^|[\s(])\*([^*\s][^*]*?)\*(?=[\s).,;:!?]|$)/g, "$1<em>$2</em>");
}

const LIST_ITEM = /^(\s*)(?:([-*•])|(\d+)[.)])\s+(.*)$/;

function renderList(list) {
    const items = list.items
        .map((item) => `<li>${renderInline(item.text)}${item.children ? renderList(item.children) : ""}</li>`)
        .join("");
    const start = list.tag === "ol" && list.start > 1 ? ` start="${list.start}"` : "";
    return `<${list.tag}${start}>${items}</${list.tag}>`;
}

export function renderMarkdown(source) {
    const lines = escape(source || "").split(/\r?\n/);
    const out = [];
    let paragraph = [];
    let list = null; // { tag, start, indent, items: [{ text, children }] }

    const flushParagraph = () => {
        if (paragraph.length) {
            out.push(`<p>${paragraph.map(renderInline).join("<br/>")}</p>`);
            paragraph = [];
        }
    };
    const flushList = () => {
        if (list) {
            out.push(renderList(list));
            list = null;
        }
    };

    for (const raw of lines) {
        const line = raw.trimEnd();
        const item = line.match(LIST_ITEM);
        const heading = line.match(/^\s*#{1,6}\s+(.*)$/);

        if (!line.trim()) {
            // blank lines inside a list do not end it (models often space items out)
            flushParagraph();
            continue;
        }
        if (item) {
            const indent = item[1].length;
            const tag = item[2] ? "ul" : "ol";
            const text = item[4];
            flushParagraph();
            const parent = list && list.items[list.items.length - 1];
            if (list && indent > list.indent && parent) {
                // nested item under the previous top-level item
                parent.children = parent.children || { tag, start: 1, items: [] };
                parent.children.items.push({ text });
                continue;
            }
            if (list && list.tag !== tag) {
                flushList();
            }
            list = list || { tag, start: item[3] ? Number(item[3]) : 1, indent, items: [] };
            list.items.push({ text });
            continue;
        }
        if (heading) {
            flushParagraph();
            flushList();
            out.push(`<p class="o_aai_assistant_heading"><strong>${renderInline(heading[1])}</strong></p>`);
            continue;
        }
        if (list && /^\s{2,}\S/.test(raw)) {
            // indented continuation of the previous list item
            const last = list.items[list.items.length - 1];
            last.text += " " + line.trim();
            continue;
        }
        flushList();
        paragraph.push(line);
    }
    flushParagraph();
    flushList();
    return markup(out.join(""));
}
