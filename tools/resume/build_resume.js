// Renders Florian's standard resume from a resolved JSON (made by build_resume.py).
// Single-column ATS-friendly layout with the cover letter's navy/teal accent.
// Usage: node build_resume.js <resolved.json> <out.docx>
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, ExternalHyperlink, AlignmentType, BorderStyle, LevelFormat,
  PositionalTab, PositionalTabAlignment, PositionalTabRelativeTo, PositionalTabLeader,
} = require("docx");

const r = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const FONT = "Calibri";
const SZ = r.layout.body;          // half-points
const INK = "1F2A44";              // navy
const ACCENT = "0E7C7B";           // teal
const MUTED = "4B5563";

const run = (text, o = {}) => new TextRun({ text, font: FONT, size: SZ, ...o });
const link = (text, url, o = {}) => new ExternalHyperlink({ link: url, children: [run(text, { color: ACCENT, ...o })] });
const rightTab = () => new PositionalTab({
  alignment: PositionalTabAlignment.RIGHT, relativeTo: PositionalTabRelativeTo.MARGIN, leader: PositionalTabLeader.NONE,
});

const heading = (text) => new Paragraph({
  spacing: { before: r.layout.sectionBefore, after: 80 },
  border: { bottom: { style: BorderStyle.SINGLE, size: 10, color: ACCENT, space: 2 } },
  children: [run(text.toUpperCase(), { bold: true, size: SZ + 2, color: INK, characterSpacing: 10 })],
});

const entryTitle = (e) => new Paragraph({
  spacing: { before: r.layout.entryBefore },
  keepNext: true,
  children: [
    run(e.title, { bold: true, color: INK }),
    ...(e.url ? [run("  ·  ", { color: MUTED }), link(e.url, `https://${e.url}`, { size: SZ - 2 })] : []),
    new TextRun({ font: FONT, size: SZ, bold: true, color: INK, children: [rightTab(), e.date || ""] }),
  ],
});
const sub = (text) => new Paragraph({ keepNext: true, spacing: { after: 20 }, children: [run(text, { italics: true, color: MUTED })] });
const bullet = (text) => new Paragraph({
  numbering: { reference: "b", level: 0 }, spacing: { after: r.layout.bulletAfter, line: r.layout.line }, children: [run(text)],
});
const skill = (label, items) => new Paragraph({
  spacing: { after: 0, line: r.layout.line },
  children: [run(label + ": ", { bold: true, color: INK }), run(items.join(", "))],
});

// Contact line: plain items, then clickable profile links.
const contact = [];
r.contact.forEach((c, i) => {
  if (i) contact.push(run("  |  ", { size: SZ - 3, color: MUTED }));
  contact.push(c.url ? link(c.text, c.url, { size: SZ - 3 }) : run(c.text, { size: SZ - 3, color: MUTED }));
});

const body = [
  new Paragraph({ alignment: AlignmentType.CENTER, children: [run(r.name, { bold: true, size: 40, color: INK, characterSpacing: 30 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 20 }, children: [run(r.headline, { bold: true, color: ACCENT, size: SZ + 1 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 40 }, children: contact }),
];

for (const s of r.sections) {
  body.push(heading(s.title));
  if (s.kind === "text") body.push(new Paragraph({ alignment: AlignmentType.JUSTIFIED, spacing: { line: r.layout.line }, children: [run(s.text)] }));
  if (s.kind === "skills") s.lines.forEach((l) => body.push(skill(l.label, l.items)));
  if (s.kind === "entries") for (const e of s.entries) {
    body.push(entryTitle(e));
    if (e.subtitle) body.push(sub(e.subtitle));
    e.bullets.forEach((b) => body.push(bullet(b)));
  }
}

const doc = new Document({
  creator: r.name,
  title: `${r.name} - Resume`,
  styles: { default: { document: { run: { font: FONT, size: SZ } } } },
  numbering: { config: [{ reference: "b", levels: [{ level: 0, format: LevelFormat.BULLET, text: String.fromCharCode(0x2022),
    alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 340, hanging: 200 } } } }] }] },
  sections: [{
    properties: { page: { size: { width: 12240, height: 15840 }, margin: r.layout.margin } },
    children: body,
  }],
});

Packer.toBuffer(doc).then((b) => fs.writeFileSync(process.argv[3], b));
