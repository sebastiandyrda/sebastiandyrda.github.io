#!/usr/bin/env python3
"""Compare the CV's publication lists against publications.bib and report drift.

This does NOT rewrite the CV. You keep editing the .tex by hand exactly as you
do now; this only tells you where the two documents disagree.

    python3 _scripts/check_cv.py [path/to/CV.tex]

Exit status 0 when they agree (or differ only in capitalisation), 1 otherwise,
so it can gate CI if you ever want it to.
"""

import difflib
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_pubs import parse_bib, fdict, bib_names  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIB = os.path.join(ROOT, "publications.bib")
CV = os.path.join(ROOT, "_cv", "CV_Sebastian_Dyrda.tex")

# CV \subsection* heading -> sitecategory in the .bib
CV_SECTIONS = {
    "Journal Articles": "journal",
    "Working Papers": "working",
    "Work in Progress (already presented)": "wip",
    "Other Publications": "other",
    "Discussions": "discussion",
}

LABEL = {"journal": "Journal Articles", "working": "Working Papers",
         "wip": "Work in Progress", "other": "Other Publications",
         "discussion": "Discussions"}

# Titles this similar are treated as the same paper with a wording difference,
# rather than as one entry missing from each side.
SAME_PAPER = 0.80


def unlatex(s):
    r"""Drop LaTeX markup, keeping the text. \'{\i}os -> ios, \textbf{X} -> X."""
    s = re.sub(r"\\([ij])(?![a-zA-Z])", r"\1", s)  # dotless \i \j, as in R\'{\i}os
    s = re.sub(r"\\[^A-Za-z\s]\s*", "", s)         # accents: \' \" \^ \~ \= \.
    s = re.sub(r"\\(?:emph|textbf|textit|textrm|text)\s*\{", "{", s)
    s = re.sub(r"\\[a-zA-Z]+\s*", " ", s)          # remaining control sequences
    s = s.replace("``", '"').replace("''", '"').replace("`", "'")
    s = s.replace("--", "-")
    s = re.sub(r"[{}\\]", "", s)
    return " ".join(s.split())


def fold(s):
    """Accent- and case-insensitive form used only for comparison."""
    s = unlatex(s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("-", " ")
    return " ".join(s.lower().split())


def norm_title(s):
    return re.sub(r"[^a-z0-9 ]+", "", fold(s)).strip()


def tidy(s):
    """Readable form for the report."""
    return unlatex(s).strip(' .,"')


def people(text):
    """['guangbin hong', 'joseph b steinberg'] from a byline, order-insensitive."""
    text = unlatex(text)
    text = re.sub(r"^\s*(with|by)\b", "", text, flags=re.I)
    parts = re.split(r";|,|\band\b", text)
    out = []
    for p in parts:
        p = fold(p).strip(" .")
        p = re.sub(r"[^a-z ]", "", p).strip()
        if p:
            out.append(p)
    return sorted(out)


def strip_href(s):
    r"""\href{url}{text} -> text, repeatedly."""
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r"\\href\{[^{}]*\}\{((?:[^{}]|\{[^{}]*\})*)\}", r"\1", s)
    return s


def parse_cv(path):
    text = open(path, encoding="utf-8").read()
    entries = []
    for heading, cat in CV_SECTIONS.items():
        m = re.search(r"\\subsection\*\{" + re.escape(heading) + r"\}(.*?)\\end\{enumerate\}",
                      text, re.S)
        if not m:
            print("  ! CV section not found: %s" % heading)
            continue
        body = m.group(1)
        body = body[body.find("\\begin{enumerate}"):]
        for raw in re.split(r"\n\s*\\item\s", body)[1:]:
            raw = raw.split("\\end{enumerate}")[0].strip()
            flat = strip_href(raw)
            tm = re.search(r"``(.+?)''", flat, re.S)
            title = tm.group(1) if tm else flat.split(",")[0]
            rest = flat[tm.end():] if tm else ""
            # Byline runs from "with"/"by" up to the next ; or emphasis command.
            am = re.search(r"\b(?:with|by)\b(.*)", rest, re.S)
            authors = re.split(r";|\\textbf|\\textit|\\emph", am.group(1))[0] if am else ""
            entries.append({"cat": cat, "title": tidy(title),
                            "key": norm_title(title), "who": people(authors)})
    return entries


def parse_bibfile(path):
    out = []
    for etype, key, fields in parse_bib(open(path, encoding="utf-8").read()):
        f = fdict(fields)
        cat = f.get("sitecategory", "").strip()
        if not cat:
            continue
        title = f.get("sitetitle") or f.get("title", "")
        if cat == "discussion":
            who = people(bib_names(f.get("author", ""), surnames_only=True))
        else:
            # siteauthors is "Name|url; Name|url" - drop the URLs.
            who = people(re.sub(r"\|[^;]*", "", f.get("siteauthors", "")))
        out.append({"cat": cat, "title": tidy(title), "key": norm_title(title), "who": who})
    return out


def main():
    cv_path = sys.argv[1] if len(sys.argv) > 1 else CV
    if not os.path.exists(cv_path):
        sys.exit("CV not found: %s" % cv_path)

    cv = parse_cv(cv_path)
    bib = parse_bibfile(BIB)
    print("parsed %d CV entries, %d .bib entries\n" % (len(cv), len(bib)))

    cv_by, bib_by = {e["key"]: e for e in cv}, {e["key"]: e for e in bib}
    pairs = [(bib_by[k], cv_by[k]) for k in set(cv_by) & set(bib_by)]

    # Anything unmatched: try to pair it with a near-identical title before
    # declaring it missing, so a reworded title reads as one problem, not two.
    lone_bib = [bib_by[k] for k in set(bib_by) - set(cv_by)]
    lone_cv = [cv_by[k] for k in set(cv_by) - set(bib_by)]
    for b in list(lone_bib):
        best, score = None, 0.0
        for c in lone_cv:
            r = difflib.SequenceMatcher(None, b["key"], c["key"]).ratio()
            if r > score:
                best, score = c, r
        if best and score >= SAME_PAPER:
            pairs.append((b, best))
            lone_bib.remove(b)
            lone_cv.remove(best)

    problems, minor = [], []
    for b in lone_bib:
        problems.append("MISSING FROM CV    [%s] %s" % (LABEL.get(b["cat"]), b["title"]))
    for c in lone_cv:
        problems.append("MISSING FROM SITE  [%s] %s" % (LABEL.get(c["cat"]), c["title"]))

    for b, c in sorted(pairs, key=lambda p: p[0]["title"]):
        if b["cat"] != c["cat"]:
            problems.append("SECTION DIFFERS    %s\n     site: %s\n     CV:   %s"
                            % (b["title"], LABEL.get(b["cat"]), LABEL.get(c["cat"])))
        if b["who"] != c["who"]:
            problems.append("AUTHORS DIFFER     %s\n     site: %s\n     CV:   %s"
                            % (b["title"], ", ".join(b["who"]) or "(none)",
                               ", ".join(c["who"]) or "(none)"))
        if b["title"] != c["title"]:
            same_words = b["title"].lower() == c["title"].lower()
            (minor if same_words else problems).append(
                "TITLE DIFFERS      site: %s\n     CV:   %s" % (b["title"], c["title"]))

    if problems:
        print("DIFFERENCES (%d)\n" % len(problems))
        for p in problems:
            print("  " + p)
        print()
    if minor:
        print("MINOR - capitalisation only (%d)\n" % len(minor))
        for m in minor:
            print("  " + m)
        print()
    if not problems and not minor:
        print("CV and publications.bib agree.")

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
