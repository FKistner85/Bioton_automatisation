"""Build one bookmarked PDF handbook from the package's maintained READMEs.

Requires reportlab and pypdf. No pipeline outputs, credentials or remote files
are read. The Markdown documents remain the source of truth.
"""
from __future__ import annotations

import html
import json
from pathlib import Path
import re
import textwrap

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle,
    Preformatted, CondPageBreak,
)
from reportlab.platypus.tableofcontents import TableOfContents
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output/pdf/README_Paket.pdf"
NAVY = colors.HexColor("#183B51")
TEAL = colors.HexColor("#007F83")
WIDTH = A4[0] - 88


def source_files():
    leading = ["README.md", "README_CI_TEC.md", "MASTER_TABLE_README.md",
               "Readmes/README_INDEX.md", "Readmes/pipeline_phases.md",
               "Readmes/slurm_worker_limits.md", "Readmes/master_reconciliation.md", "Readmes/DOCUMENTATION_REVIEW.md",
               "PIPELINE_SCHRITTE_DE.md", "scripts_local_run/README.md",
               "HOREKA_RECOVERY_RUNBOOK_DE.md", "HOREKA_GEE_SECRET_SETUP_DE.md",
               "GITHUB_WORKFLOW.md", "NOMENCLATURE_MIGRATION.md"]
    files = [ROOT / p for p in leading]
    files.extend(sorted((ROOT / "Readmes").glob("*/README*.md")))
    return list(dict.fromkeys(p for p in files if p.is_file()))


def fonts():
    choices = [
        (Path("C:/Windows/Fonts/arial.ttf"), Path("C:/Windows/Fonts/arialbd.ttf"), Path("C:/Windows/Fonts/consola.ttf")),
        (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")),
    ]
    for regular, bold, mono in choices:
        if all(p.is_file() for p in (regular, bold, mono)):
            for name, path in (("Doc", regular), ("DocBold", bold), ("DocMono", mono)):
                pdfmetrics.registerFont(TTFont(name, str(path)))
            pdfmetrics.registerFontFamily("Doc", normal="Doc", bold="DocBold", italic="Doc", boldItalic="DocBold")
            return
    raise RuntimeError("Install Arial/Consolas or DejaVu fonts before rendering.")


def clean(text):
    return text.replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-").replace("\u00a0", " ")


def inline(raw):
    # Preserve link labels in print; source paths are stated at every chapter.
    raw = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", raw)
    parts = re.split(r"(`[^`]+`)", html.unescape(raw))
    rendered = []
    for part in parts:
        if part.startswith("`") and part.endswith("`"):
            rendered.append('<font name="DocMono">' + html.escape(clean(part[1:-1])) + '</font>')
        else:
            rendered.append(re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", html.escape(clean(part))))
    return "".join(rendered)


def styles():
    return {
        "body": ParagraphStyle("body", fontName="Doc", fontSize=9, leading=12.6, spaceAfter=6, splitLongWords=True),
        "h2": ParagraphStyle("h2", fontName="DocBold", fontSize=13, leading=17, textColor=NAVY, spaceBefore=12, spaceAfter=7, keepWithNext=True),
        "h3": ParagraphStyle("h3", fontName="DocBold", fontSize=10.5, leading=14, textColor=TEAL, spaceBefore=10, spaceAfter=5, keepWithNext=True),
        "chapter": ParagraphStyle("chapter", fontName="DocBold", fontSize=19, leading=24, textColor=NAVY, spaceAfter=10, keepWithNext=True),
        "small": ParagraphStyle("small", fontName="Doc", fontSize=7.5, leading=10, textColor=colors.HexColor("#556570"), spaceAfter=10, splitLongWords=True),
        "cell": ParagraphStyle("cell", fontName="Doc", fontSize=7.6, leading=10.2, splitLongWords=True),
        "head": ParagraphStyle("head", fontName="DocBold", fontSize=7.6, leading=10.2, textColor=colors.white, splitLongWords=True),
        "code": ParagraphStyle("code", fontName="DocMono", fontSize=7.5, leading=10, spaceBefore=3, spaceAfter=8, backColor=colors.HexColor("#F1F4F6")),
    }


def flowables(source, sty):
    lines = source.splitlines()
    result = []
    pos = 0
    while pos < len(lines):
        line = lines[pos].strip()
        if not line or line.startswith("<!--"):
            pos += 1
            continue
        if line.startswith("```"):
            language = line[3:]
            pos += 1
            code = []
            while pos < len(lines) and not lines[pos].strip().startswith("```"):
                code.extend(textwrap.wrap(clean(lines[pos].expandtabs(4)), width=97,
                                          replace_whitespace=False, drop_whitespace=False) or [""])
                pos += 1
            # Code is printed verbatim. Mermaid diagrams are labelled as source.
            if language == "mermaid":
                result.append(Paragraph("Diagramm (Mermaid-Quelle)", sty["small"]))
            result.append(Preformatted("\n".join(code), sty["code"]))
            pos += 1
            continue
        if line.startswith("|"):
            rows = []
            while pos < len(lines) and lines[pos].strip().startswith("|"):
                current = lines[pos].strip()
                if not re.fullmatch(r"[|:\-\s]+", current):
                    # Literal pipes in Markdown code spans must not split cells.
                    parts = re.split(r"\|(?=(?:[^`]*`[^`]*`)*[^`]*$)", current.strip("|"))
                    rows.append([part.strip() for part in parts])
                pos += 1
            cols = max(map(len, rows))
            rows = [row + [""] * (cols - len(row)) for row in rows]
            if cols == 3 and any("Code" in c for c in rows[0]):
                widths = [WIDTH * .35, WIDTH * .43, WIDTH * .22]
            elif cols == 2:
                widths = [WIDTH * .35, WIDTH * .65]
            else:
                widths = [WIDTH / cols] * cols
            data = [[Paragraph(inline(cell), sty["head" if r == 0 else "cell"]) for cell in row] for r, row in enumerate(rows)]
            table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F5F6")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LINEBELOW", (0, 0), (-1, 0), .4, NAVY),
            ]))
            result.extend([table, Spacer(1, 8)])
            continue
        if re.match(r"^#{1,6} ", line):
            level = len(line.split(" ", 1)[0])
            result.append(CondPageBreak(65))
            result.append(Paragraph(inline(line.lstrip("# ")), sty["h2" if level <= 2 else "h3"]))
            pos += 1
            continue
        if re.fullmatch(r"[-*_]{3,}", line):
            pos += 1
            continue
        if re.match(r"^([-*] |\d+\. |>)", line):
            result.append(Paragraph(inline(line), sty["body"]))
            pos += 1
            continue
        paragraph = [line]
        pos += 1
        while pos < len(lines) and lines[pos].strip() and not re.match(r"^(#|\||```|[-*] |\d+\. |>|<!--)", lines[pos].strip()):
            paragraph.append(lines[pos].strip())
            pos += 1
        result.append(Paragraph(inline(" ".join(paragraph)), sty["body"]))
    return result


class Handbook(SimpleDocTemplate):
    def afterFlowable(self, item):
        if getattr(item, "chapter_key", None):
            self.canv.bookmarkPage(item.chapter_key)
            self.canv.addOutlineEntry(item.getPlainText(), item.chapter_key, level=0)
            self.notify("TOCEntry", (0, item.getPlainText(), self.page, item.chapter_key))


def page_header(canvas, doc):
    canvas.saveState()
    canvas.setFont("Doc", 7)
    canvas.setFillColor(colors.HexColor("#556570"))
    canvas.drawString(44, A4[1] - 27, "BIO-O-TON  /  README-HANDBUCH")
    canvas.drawRightString(A4[0] - 44, A4[1] - 27, "Code- und Dokumentationsstand 24.09.2026")
    canvas.line(44, A4[1] - 33, A4[0] - 44, A4[1] - 33)
    canvas.drawString(44, 25, "Quellen: Markdown-Dateien des Pipeline-Pakets")
    canvas.drawRightString(A4[0] - 44, 25, str(doc.page))
    canvas.restoreState()


def main():
    fonts()
    sty = styles()
    paths = source_files()
    story = [Spacer(1, 65), Paragraph("Bio-O-Ton", sty["chapter"]),
             Paragraph("Pipeline-Handbuch und Fehlerreferenz", sty["chapter"]),
             Spacer(1, 15), Paragraph("READMEs und Betriebsanleitungen / Deutsch und Englisch", sty["h2"]),
             Paragraph("Stand: 24. September 2026", sty["body"]),
             Paragraph(f"{len(paths)} Quelldokumente. Separater Kern- und Bioakustiklauf, Master-Schema v6, Schritt-Diagnosen und Vorbereitung fuer Horeka 2.", sty["body"]),
             Paragraph("Dieses Handbuch beschreibt den Code- und Dokumentationsstand vom 24.09.2026 einschliesslich der Master-Zusammenfuehrung und der ci-tec-Abstimmungsliste. Ausfuehrungs- und Veroeffentlichungsnachweise stehen im jeweiligen Laufbericht; eine Horeka-2-Migration wird hier nicht als ausgefuehrt dargestellt. Historische Audit-Inhalte bleiben als solche gekennzeichnet.", sty["body"]),
             PageBreak(), Paragraph("Inhaltsverzeichnis", sty["chapter"])]
    toc = TableOfContents()
    toc.levelStyles = [ParagraphStyle("toc", fontName="Doc", fontSize=8.7, leading=12, spaceBefore=4, leftIndent=0, firstLineIndent=0)]
    story.extend([toc, PageBreak()])
    for index, path in enumerate(paths):
        source = path.read_text(encoding="utf-8-sig")
        first, _, rest = source.partition("\n")
        title = first.lstrip("# ")
        chapter = Paragraph(f"{index + 1:02d}  {inline(title)}", sty["chapter"])
        chapter.chapter_key = f"chapter-{index}"
        story.extend([chapter, Paragraph(inline(path.relative_to(ROOT).as_posix()), sty["small"])])
        story.extend(flowables(rest, sty))
        if index < len(paths) - 1:
            story.append(PageBreak())
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = Handbook(str(OUTPUT), pagesize=A4, leftMargin=44, rightMargin=44,
                   topMargin=48, bottomMargin=43, title="Bio-O-Ton README-Paket", author="Bio-O-Ton")
    doc.multiBuild(story, onFirstPage=page_header, onLaterPages=page_header)
    reader = PdfReader(OUTPUT)
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
    for expected in ("slurm_bioacoustics.sh", "datetime_local", "utc_local_conflict", "required_models_incomplete"):
        if expected not in extracted:
            raise AssertionError(f"Missing PDF content: {expected}")
    manifest = {"pdf": str(OUTPUT.relative_to(ROOT)), "pages": len(reader.pages),
                "sources": [p.relative_to(ROOT).as_posix() for p in paths],
                "bookmarks": len(reader.outline), "text_checks": "passed"}
    (OUTPUT.parent / "README_Paket_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
