"""Export the ci-tec Markdown content as editable pdfLaTeX source."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

def escape(text):
    mapping = {'\\': r'\textbackslash{}', '&': r'\&', '%': r'\%', '$': r'\$', '#': r'\#', '_': r'\_', '{': r'\{', '}': r'\}', '~': r'\textasciitilde{}', '^': r'\textasciicircum{}', '<': r'\textless{}', '>': r'\textgreater{}'}
    return ''.join(mapping.get(c, c) for c in text)

def inline(text):
    parts = re.split(r'(\*\*.+?\*\*|`.+?`)', text)
    return ''.join(r'\textbf{' + escape(p[2:-2]) + '}' if p.startswith('**') else escape(p[1:-1]) if p.startswith('`') else escape(p) for p in parts)

def main():
    lines = (ROOT/'README_CI_TEC.md').read_text(encoding='utf-8').splitlines()
    out = [r'''% Compile with: pdflatex README_CI_TEC.tex
% Editable source with the same content as the accompanying PDF.
% The PDF is rendered by ReportLab; LaTeX pagination can differ.
\documentclass[a4paper,9pt]{extarticle}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{helvet}
\renewcommand{\familydefault}{\sfdefault}
\usepackage[margin=15mm]{geometry}
\usepackage[table]{xcolor}
\usepackage{longtable,array,enumitem,microtype}
\usepackage{titlesec}
\definecolor{navy}{HTML}{19384A}
\definecolor{pale}{HTML}{EFF5F7}
\titleformat{\section}{\large\bfseries\color{navy}}{}{0pt}{}
\setlength{\parindent}{0pt}
\setlength{\parskip}{6pt}
\setlength{\emergencystretch}{4em}
\renewcommand{\arraystretch}{1.3}
\pagestyle{empty}
\begin{document}''']
    i=0
    while i<len(lines):
        line=lines[i]
        if line.startswith('```'):
            i+=1
            block=[]
            while i<len(lines) and not lines[i].startswith('```'):
                block.append(lines[i])
                i+=1
            out.append('\\begin{verbatim}\n'+'\n'.join(block)+'\n\\end{verbatim}')
            i+=1
            continue
        if line.startswith('|'):
            rows=[]
            while i<len(lines) and lines[i].startswith('|'):
                if not re.fullmatch(r'[| :\-]+',lines[i]):
                    rows.append([inline(x.strip()) for x in lines[i].strip('|').split('|')])
                i+=1
            out.append(r'\begingroup\small\begin{longtable}{>{\raggedright\arraybackslash}p{0.39\linewidth}>{\raggedright\arraybackslash}p{0.55\linewidth}}')
            header=r'\rowcolor{navy} '+ ' & '.join(r'\color{white}\bfseries '+x for x in rows[0])+r' \\'
            out.extend([header,r'\endfirsthead',header,r'\endhead'])
            for n,row in enumerate(rows[1:]):
                out.append((r'\rowcolor{pale} ' if n%2==0 else '')+' & '.join(row)+r' \\')
            out.append(r'\end{longtable}\endgroup')
            continue
        if line.startswith('# '): out.append(r'{\Huge\bfseries\color{navy} '+inline(line[2:])+r'}\par')
        elif line.startswith('## '): out.append(r'\section*{'+inline(line[3:])+'}')
        elif line.startswith('- '): out.append(r'\noindent\textbullet\ '+inline(line[2:])+r'\par')
        elif line: out.append(inline(line)+r'\par')
        i+=1
    out.append(r'\end{document}')
    (ROOT/'README_CI_TEC.tex').write_text('\n\n'.join(out)+'\n',encoding='utf-8')

if __name__=='__main__': main()
