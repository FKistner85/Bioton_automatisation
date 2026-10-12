"""Render the short ci-tec README from its Markdown source (reportlab)."""
from pathlib import Path
from html import escape
import re
import argparse

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Preformatted, KeepTogether
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ROOT = Path(__file__).resolve().parents[1]


def inline(text):
    text = escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    return re.sub(r"`(.+?)`", r"\1", text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'README_CI_TEC.pdf')
    output = parser.parse_args().output
    output.parent.mkdir(parents=True, exist_ok=True)
    choices = [
        (Path('C:/Windows/Fonts/arial.ttf'), Path('C:/Windows/Fonts/arialbd.ttf'), Path('C:/Windows/Fonts/consola.ttf')),
        (Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'), Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'), Path('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf')),
    ]
    for regular, bold, mono in choices:
        if all(p.is_file() for p in (regular, bold, mono)):
            for name, font in [('Doc', regular), ('DocBold', bold), ('DocMono', mono)]:
                pdfmetrics.registerFont(TTFont(name, str(font)))
            pdfmetrics.registerFontFamily('Doc', normal='Doc', bold='DocBold', italic='Doc', boldItalic='DocBold')
            break
    else:
        raise RuntimeError('Install Arial/Consolas or DejaVu fonts before rendering.')
    navy = colors.HexColor("#19384A")
    styles = {
        "title": ParagraphStyle("title", fontName="DocBold", fontSize=21, leading=25, textColor=navy, spaceAfter=7),
        "h": ParagraphStyle("h", fontName="DocBold", fontSize=12, leading=15, textColor=navy, spaceBefore=9, spaceAfter=5, keepWithNext=True),
        "body": ParagraphStyle("body", fontName="Doc", fontSize=9, leading=12, spaceAfter=6),
        "cell": ParagraphStyle("cell", fontName="Doc", fontSize=8.5, leading=11),
        "head": ParagraphStyle("head", fontName="DocBold", fontSize=9, leading=12, textColor=colors.white),
        "code": ParagraphStyle("code", fontName="DocMono", fontSize=8.5, leading=11, spaceAfter=7),
    }
    lines = (ROOT / "README_CI_TEC.md").read_text(encoding="utf-8").splitlines()
    story = []
    pos = 0
    while pos < len(lines):
        line = lines[pos]
        if line.startswith("```"):
            pos += 1
            block = []
            while pos < len(lines) and not lines[pos].startswith("```"):
                block.append(lines[pos])
                pos += 1
            story.append(KeepTogether([Preformatted("\n".join(block), styles["code"])]))
            pos += 1
            continue
        if line.startswith("|"):
            group = []
            while pos < len(lines) and lines[pos].startswith("|"):
                if not re.fullmatch(r"[| :\-]+", lines[pos]):
                    group.append([cell.strip() for cell in lines[pos].strip("|").split("|")])
                pos += 1
            data = [[Paragraph(inline(cell).replace(", ", ",<br/>") if n else inline(cell), styles["head" if not i else "cell"])
                     for n, cell in enumerate(row)] for i, row in enumerate(group)]
            # Column names wrap at commas; prose flows normally.
            for i, row in enumerate(group[1:], 1):
                data[i][0] = Paragraph(inline(row[0]).replace(", ", ",<br/>"), styles["cell"])
                data[i][1] = Paragraph(inline(row[1]), styles["cell"])
            table = Table(data, colWidths=[211, 300], hAlign="LEFT", repeatRows=1)
            table.setStyle(TableStyle([
                ("BACKGROUND", (0,0), (-1,0), navy), ("VALIGN", (0,0), (-1,-1), "TOP"),
                ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.HexColor("#EFF5F7"), colors.white]),
                ("LEFTPADDING", (0,0), (-1,-1), 7), ("RIGHTPADDING", (0,0), (-1,-1), 7),
                ("TOPPADDING", (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6),
            ]))
            story += [table, Spacer(1, 7)]
            continue
        if line:
            if line.startswith('## Clean-data filters'):
                story.append(PageBreak())
            if line.startswith(('## Abstimmung mit ci-tec', '## Vorgaben und offene Punkte')):
                story.append(PageBreak())
            kind = "title" if line.startswith("# ") else "h" if line.startswith("## ") else "body"
            text = re.sub(r"^#{1,2} ", "", line)
            story.append(Paragraph(inline(text), styles[kind]))
        pos += 1
    SimpleDocTemplate(str(output), pagesize=A4,
                      leftMargin=42, rightMargin=42, topMargin=32, bottomMargin=32,
                      title="Master table - ci-tec", author="Bio-O-Ton").build(story)
    print(output)


if __name__ == "__main__":
    main()
