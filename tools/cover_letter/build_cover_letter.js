// Renders a validated cover letter JSON (from make_cover_letter.py) with its own letterhead:
// name + headline on the left, contact stacked on the right, a colored accent rule, and the
// accent repeated on the "Re:" line and signature. Usage: node build_cover_letter.js <letter.json> <out.docx>
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, AlignmentType, BorderStyle, Footer,
  PositionalTab, PositionalTabAlignment, PositionalTabRelativeTo, PositionalTabLeader,
} = require("docx");

const FONT = "Calibri";
const SZ = 24;          // 12pt body: a 250-320 word letter fills most of the page
const INK = "1F2A44";   // deep navy for the name
const ACCENT = "0E7C7B"; // teal accent
const MUTED = "5B6472"; // grey for secondary text
const l = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));

const run = (text, o = {}) => new TextRun({ text, font: FONT, size: SZ, ...o });
const rightTab = () => new PositionalTab({
  alignment: PositionalTabAlignment.RIGHT, relativeTo: PositionalTabRelativeTo.MARGIN, leader: PositionalTabLeader.NONE,
});
// A letterhead row: left text, then right-aligned contact text on the same line.
const row = (left, right, leftStyle, after = 0) => new Paragraph({
  spacing: { after },
  children: [
    ...(left ? [run(left, leftStyle)] : []),
    new TextRun({ font: FONT, size: 18, color: MUTED, children: [rightTab(), right || ""] }),
  ],
});

// contact arrives as [location, phone, email, linkedin, github?]; stack it as email / phone · location / links
const [location, phone, email, ...links] = l.contact;
const letterhead = [
  row(l.name, email, { bold: true, size: 48, color: INK, characterSpacing: 20 }),
  row(l.headline, [phone, location].filter(Boolean).join("  ·  "), { size: 22, color: ACCENT, bold: true }),
  new Paragraph({
    spacing: { after: 360 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 18, color: ACCENT, space: 6 } },
    children: [new TextRun({ font: FONT, size: 18, color: MUTED, children: [rightTab(), links.join("  ·  ")] })],
  }),
];

const para = (text) => new Paragraph({ alignment: AlignmentType.JUSTIFIED, spacing: { after: 200, line: 276 }, children: [run(text)] });

// Footer: thin accent rule + name and contact, so the bottom of the page is anchored.
const footer = new Footer({ children: [new Paragraph({
  alignment: AlignmentType.CENTER,
  border: { top: { style: BorderStyle.SINGLE, size: 6, color: ACCENT, space: 6 } },
  children: [run([l.signature, email, phone].filter(Boolean).join("   ·   "), { size: 16, color: MUTED })],
})] });

const body = [
  ...letterhead,
  new Paragraph({ spacing: { after: 240 }, children: [run(l.date, { color: MUTED })] }),
  new Paragraph({ children: [run(l.company, { bold: true })] }),
  new Paragraph({ spacing: { after: 240 }, children: [run(`Re: ${l.role}`, { color: ACCENT, bold: true })] }),
  new Paragraph({ spacing: { after: 220 }, children: [run(l.greeting)] }),
  ...l.paragraphs.map(para),
  new Paragraph({ keepNext: true, spacing: { before: 160 }, children: [run("Sincerely,")] }),
  new Paragraph({ keepNext: true, spacing: { before: 300 }, children: [run(l.signature, { bold: true, color: INK, size: 28 })] }),
  new Paragraph({ children: [run(l.headline, { color: ACCENT, size: 20 })] }),
];

const doc = new Document({
  creator: l.signature,
  title: `${l.signature} - Cover Letter - ${l.company}`,
  styles: { default: { document: { run: { font: FONT, size: SZ } } } },
  sections: [{
    properties: { page: { size: { width: 12240, height: 15840 },
      margin: { top: 1008, bottom: 1008, left: 1296, right: 1296, footer: 576 } } },
    footers: { default: footer },
    children: body,
  }],
});

Packer.toBuffer(doc).then((b) => fs.writeFileSync(process.argv[3], b));
