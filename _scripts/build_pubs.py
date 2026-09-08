#!/usr/bin/env python3
"""Turn publications.bib into the HTML partials the site includes.

Run automatically by Quarto (see the pre-render hook in _quarto.yml).
No third-party dependencies - stdlib only.
"""

import os
import re
import sys
import html
import subprocess
import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIB = os.path.join(ROOT, "publications.bib")
OUT = os.path.join(ROOT, "_generated")

# Which sections land on which page, in order.
PAGES = [
    ("research", [
        ("working", "Working Papers"),
        ("journal", "Journal Articles"),
        ("wip", "Work in Progress"),
        ("other", "Other Publications"),
    ]),
    ("discussions", [
        ("discussion", None),   # page <h1> already says it
    ]),
]

# LaTeX escapes that show up in author names, mapped to plain Unicode.
ACCENTS = [
    (r"\{\\'\{?([aeiouyAEIOUY])\}?\}", {"a": "á", "e": "é", "i": "í", "o": "ó",
                                        "u": "ú", "y": "ý", "A": "Á", "E": "É",
                                        "I": "Í", "O": "Ó", "U": "Ú", "Y": "Ý"}),
]


CV_PDF = "files/CV_Sebastian_Dyrda.pdf"


def cv_updated():
    """When the CV PDF last changed, for the line on the CV page.

    Read from the commit that last touched the file rather than its mtime:
    a CI checkout rewrites every mtime to the moment of the clone, which
    would date the CV "today" on every single deploy. Needs full history -
    the workflow sets fetch-depth: 0 for exactly this.
    """
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%cI", "--", CV_PDF],
                             cwd=ROOT, capture_output=True, text=True, timeout=15)
        stamp = out.stdout.strip()[:10]
        if stamp:
            return datetime.date.fromisoformat(stamp)
    except Exception:
        pass
    path = os.path.join(ROOT, CV_PDF)
    if os.path.exists(path):
        return datetime.date.fromtimestamp(os.path.getmtime(path))
    return None


def write_cv_date():
    d = cv_updated()
    if not d:
        return ""
    text = "%d %s %d" % (d.day, d.strftime("%B"), d.year)
    with open(os.path.join(OUT, "cvdate.md"), "w", encoding="utf-8") as fh:
        fh.write('<p class="cv-updated">Last updated %s</p>\n' % text)
    return text


def strip_latex(s):
    """Convert the LaTeX-isms we actually use into display text."""
    s = re.sub(r"\{\\'\{?([a-zA-Z])\}?\}|\\'\{?([a-zA-Z])\}?",
               lambda m: {"a": "á", "e": "é", "i": "í", "o": "ó", "u": "ú",
                          "y": "ý", "A": "Á", "E": "É", "I": "Í", "O": "Ó",
                          "U": "Ú", "Y": "Ý", "n": "ń", "s": "ś", "c": "ć",
                          "z": "ź"}.get(m.group(1) or m.group(2),
                                        m.group(1) or m.group(2)),
               s)
    s = s.replace("``", "“").replace("''", "”")
    s = s.replace("--", "–")
    s = s.replace("{", "").replace("}", "")
    return s.strip()


def parse_bib(text):
    """Yield (entrytype, key, [(field, value), ...]) for each @entry."""
    entries = []
    i = 0
    while True:
        at = text.find("@", i)
        if at == -1:
            break
        # Skip an @ that sits inside a comment line.
        line_start = text.rfind("\n", 0, at) + 1
        if text[line_start:at].lstrip().startswith("%"):
            i = at + 1
            continue
        m = re.match(r"@(\w+)\s*\{", text[at:])
        if not m:
            i = at + 1
            continue
        etype = m.group(1).lower()
        # Walk braces from the entry's opening brace to find its end.
        open_at = at + m.end() - 1
        depth, j = 0, open_at
        for j in range(open_at, len(text)):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    break
        inner = text[open_at + 1:j]
        km = re.match(r"\s*([^,\s]+)\s*,", inner)
        if not km:
            i = j + 1
            continue
        entries.append((etype, km.group(1), parse_fields(inner[km.end():])))
        i = j + 1
    return entries


def fdict(fields):
    """Field list -> {name: value}, dropping the delimiter marker."""
    return dict((k, v) for k, v, _ in fields)


def parse_fields(body):
    """Split an entry body into ordered (name, value, delimiter) triples.

    The delimiter is kept so the [BibTeX] popup can re-emit each field the
    way it was written - "{...}" stays quoted rather than becoming {{...}}.
    """
    fields, i, n = [], 0, len(body)
    while i < n:
        m = re.compile(r"\s*(\w+)\s*=\s*").match(body, i)
        if not m:
            i += 1
            continue
        name = m.group(1).lower()
        i = m.end()
        if i < n and body[i] == "{":
            depth, start = 0, i
            while i < n:
                if body[i] == "{":
                    depth += 1
                elif body[i] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            value = body[start + 1:i]
            delim = "{"
            i += 1
        elif i < n and body[i] == '"':
            start = i + 1
            i = body.find('"', start)
            value = body[start:i]
            delim = '"'
            i += 1
        else:
            start = i
            while i < n and body[i] not in ",\n":
                i += 1
            value = body[start:i].strip()
            delim = ""
        fields.append((name, value, delim))
        while i < n and body[i] in ", \n\t":
            i += 1
    return fields


def pairs(raw):
    """Parse "Label|href; Label|href" into [(label, href), ...]."""
    out = []
    for chunk in raw.split(";"):
        chunk = " ".join(chunk.split())
        if not chunk:
            continue
        if "|" in chunk:
            label, href = chunk.split("|", 1)
            out.append((strip_latex(label.strip()), href.strip()))
        else:
            out.append((strip_latex(chunk), None))
    return out


def conjoin(bits):
    """A / A and B / A, B and C."""
    if not bits:
        return ""
    if len(bits) == 1:
        return bits[0]
    if len(bits) == 2:
        return "%s and %s" % (bits[0], bits[1])
    return "%s and %s" % (", ".join(bits[:-1]), bits[-1])


def byline(raw):
    """Render the "with A, B and C" line, linking names that have a URL."""
    bits = []
    for name, href in pairs(raw):
        name = html.escape(name)
        bits.append('<a href="%s" target="_blank">%s</a>' % (html.escape(href), name)
                    if href else name)
    return "with " + conjoin(bits)


def bib_names(raw, surnames_only=False):
    """Turn a BibTeX author field into display names.

    "Last, First" -> "First Last", or just "Last" when surnames_only.
    A name written without a comma is assumed to already end in the surname.
    """
    bits = []
    for part in re.split(r"\s+and\s+", raw.strip()):
        part = " ".join(part.split())
        if not part:
            continue
        if "," in part:
            last, first = [x.strip() for x in part.split(",", 1)]
            part = last if surnames_only else ("%s %s" % (first, last)).strip()
        elif surnames_only:
            part = part.split()[-1]
        bits.append(html.escape(strip_latex(part)))
    return conjoin(bits)


def bibtex_text(etype, key, fields):
    """Re-emit the entry with site-only fields removed, for the popup."""
    keep = [(k, v, d) for k, v, d in fields
            if not k.startswith("site") and k != "abstract"]
    width = max(len(k) for k, _, _ in keep)
    lines = ["@%s{%s," % (etype, key)]
    for k, v, d in keep:
        v = " ".join(v.split()) if "\n" in v else v
        wrapped = '"%s"' % v if d == '"' else "{%s}" % v
        lines.append("    %-*s = %s," % (width, k, wrapped))
    lines.append("}")
    return "\n".join(lines)


SITE_URL = "https://dyrda.info"
PAGES_DIR = os.path.join(ROOT, "research")

# A paper only gets its own page once it has an abstract. Everything without
# one keeps a plain, unlinked title in the list exactly as before, so this
# rolls out a paper at a time and never leaves a half-built page behind.
PAGE_CATS = ("working", "journal", "wip", "other")


def slugify(s):
    s = strip_latex(s).lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[\u2018\u2019']", "", s)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"-{2,}", "-", s).strip("-")


def page_slug(f):
    """URL segment for a paper page: siteslug if pinned, else from the title.

    Pinning matters because the slug is the URL - retitling a paper would
    otherwise silently move a page that other sites may already link to.
    """
    if f.get("siteslug"):
        return slugify(f["siteslug"])
    return slugify(f.get("sitetitle") or f.get("title", ""))


def has_page(f):
    return bool(f.get("abstract", "").strip()) and f.get("sitecategory") in PAGE_CATS


def abstract_text(raw):
    return " ".join(raw.split())


def citation_meta(key, f, etype):
    """Google Scholar's tags. One paper per URL is the only shape it reads."""
    out = []

    def tag(name, value):
        out.append('<meta name="%s" content="%s">' % (name, html.escape(value, quote=True)))

    tag("citation_title", strip_latex(f.get("sitetitle") or f.get("title", "")))
    for part in re.split(r"\s+and\s+", f.get("author", "").strip()):
        part = " ".join(part.split())
        if part:
            tag("citation_author", strip_latex(part))
    if f.get("year"):
        tag("citation_publication_date", strip_latex(f["year"]))
    tag("citation_abstract_html_url", "%s/research/%s/" % (SITE_URL, page_slug(f)))
    for label, href in pairs(f.get("sitelinks", "")):
        if href and href.startswith("/files/") and href.endswith(".pdf"):
            tag("citation_pdf_url", SITE_URL + href)
            break
    if f.get("sitejournal"):
        tag("citation_journal_title", strip_latex(f["sitejournal"]))
    elif etype == "techreport":
        if f.get("institution"):
            tag("citation_technical_report_institution", strip_latex(f["institution"]))
        if f.get("number"):
            tag("citation_technical_report_number", strip_latex(f["number"]))
    if f.get("doi"):
        tag("citation_doi", strip_latex(f["doi"]))
    return out


def render_paper_page(etype, key, fields):
    """Write research/<slug>/index.qmd for one paper.

    Quarto picks up inputs a pre-render script creates in the same pass
    (verified), so these behave like _generated/ - never edited by hand,
    never committed.
    """
    f = fdict(fields)
    slug = page_slug(f)
    title = strip_latex(f.get("sitetitle") or f.get("title", ""))
    abstract = abstract_text(f["abstract"])

    body = []
    if f.get("siteauthors"):
        body.append('<span class="pub-authors">%s</span>' % byline(f["siteauthors"]))
    if f.get("sitejournal"):
        venue = '<i class="venue">%s</i>' % html.escape(strip_latex(f["sitejournal"]))
        if f.get("siteinfo"):
            venue += ", " + html.escape(strip_latex(f["siteinfo"]))
        body.append('<span class="pub-venue">%s</span>' % venue)
    elif f.get("siteinfo"):
        body.append('<span class="pub-venue">%s</span>' % html.escape(strip_latex(f["siteinfo"])))
    if f.get("sitenote"):
        body.append('<span class="pub-note">%s</span>' % " ".join(f["sitenote"].split()))

    links = ['<a class="pub-link" href="%s">%s</a>' % (html.escape(h), html.escape(l))
             for l, h in pairs(f.get("sitelinks", "")) if h]
    if f.get("sitebib", "yes").lower() != "no":
        links.append('<button type="button" class="pub-link bib-btn" data-bib="%s">BibTeX</button>'
                     % html.escape(key))

    meta = "\n".join("  " + m for m in citation_meta(key, f, etype))
    desc = abstract[:155].rsplit(" ", 1)[0] + "..." if len(abstract) > 155 else abstract

    doc = []
    doc.append("---")
    doc.append('title: %s' % yaml_str(title))
    doc.append('pagetitle: %s' % yaml_str(title))
    doc.append('description: %s' % yaml_str(desc))
    doc.append("header-includes: |")
    doc.append(meta)
    doc.append("---")
    doc.append("")
    doc.append('::: {.paper-meta}')
    doc.extend(body)
    doc.append(':::')
    doc.append("")
    doc.append('<h2 class="section-head">Abstract</h2>')
    doc.append("")
    doc.append('::: {.paper-abstract}')
    # quote=False: this sits in a markdown div, so apostrophes and quotes
    # should stay literal characters rather than becoming entities.
    doc.append(html.escape(abstract, quote=False))
    doc.append(':::')
    doc.append("")
    if links:
        doc.append('<span class="pub-links paper-links">%s</span>' % "\n".join(links))
        doc.append("")
    doc.append('<p class="paper-back"><a href="../">&larr; All research</a></p>')
    doc.append("")
    doc.append("{{< include /_generated/bibdata.md >}}")
    doc.append("")

    d = os.path.join(PAGES_DIR, slug)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "index.qmd"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(doc))
    return slug


def yaml_str(s):
    return '"%s"' % s.replace("\\", "\\\\").replace('"', '\\"')


def prune_pages(keep):
    """Drop page directories whose paper lost its abstract or changed slug.

    Without this a renamed paper leaves its old URL live and indexed, which
    is worse than never having published it.
    """
    if not os.path.isdir(PAGES_DIR):
        return
    for name in os.listdir(PAGES_DIR):
        d = os.path.join(PAGES_DIR, name)
        stub = os.path.join(d, "index.qmd")
        if os.path.isdir(d) and name not in keep and os.path.exists(stub):
            os.remove(stub)
            try:
                os.rmdir(d)
            except OSError:
                pass


def render_entry(idx, etype, key, fields):
    f = fdict(fields)
    title = f.get("sitetitle") or f.get("title", "")
    parts = ['<li id="%s">' % html.escape(key)]
    # Linked only when the paper has a page. Styled to look identical to the
    # unlinked span at rest, so the list reads exactly as it did before.
    if has_page(f):
        parts.append('<a class="pub-title" href="/research/%s/">%s</a>'
                     % (page_slug(f), html.escape(strip_latex(title))))
    else:
        parts.append('<span class="pub-title">%s</span>' % html.escape(strip_latex(title)))

    if f.get("siteauthors"):
        parts.append('<span class="pub-authors">%s</span>' % byline(f["siteauthors"]))
    elif f.get("sitecategory") == "discussion" and f.get("author"):
        # For a discussion, "author" is whoever wrote the paper being discussed;
        # surnames only, as in a reference list.
        parts.append('<span class="pub-authors">by %s</span>'
                     % bib_names(f["author"], surnames_only=True))
    if f.get("sitejournal"):
        venue = '<i class="venue">%s</i>' % html.escape(strip_latex(f["sitejournal"]))
        if f.get("siteinfo"):
            venue += ", " + html.escape(strip_latex(f["siteinfo"]))
        parts.append('<span class="pub-venue">%s</span>' % venue)
    elif f.get("siteinfo"):
        parts.append('<span class="pub-venue">%s</span>' % html.escape(strip_latex(f["siteinfo"])))
    if f.get("sitenote"):
        parts.append('<span class="pub-note">%s</span>' % " ".join(f["sitenote"].split()))

    links = []
    for label, href in pairs(f.get("sitelinks", "")):
        if href:
            links.append('<a class="pub-link" href="%s">%s</a>' % (html.escape(href), html.escape(label)))
    if f.get("sitebib", "yes").lower() != "no":
        links.append('<button type="button" class="pub-link bib-btn" data-bib="%s">BibTeX</button>'
                     % html.escape(key))
    if links:
        parts.append('<span class="pub-links">%s</span>' % "\n".join(links))

    parts.append("</li>")
    return "\n".join(parts)


def render_featured(fields):
    """The home page's featured card, built from the entry flagged sitefeatured.

    Hand-writing this card in index.qmd meant the title, byline, venue and
    links existed in two places; an acceptance would have had to be applied
    twice, and the home page is where a stale status shows most.
    """
    f = fdict(fields)
    title = html.escape(strip_latex(f.get("sitetitle") or f.get("title", "")))
    links = pairs(f.get("sitelinks", ""))
    href = links[0][1] if links else None

    out = ['<div class="featured-card">']
    out.append('<a class="featured-title" href="%s">%s</a>' % (html.escape(href), title)
               if href else '<span class="featured-title">%s</span>' % title)
    if f.get("siteauthors"):
        out.append('<span class="featured-authors">%s</span>' % byline(f["siteauthors"]))
    if f.get("sitejournal"):
        venue = '<i class="venue">%s</i>' % html.escape(strip_latex(f["sitejournal"]))
        if f.get("siteinfo"):
            venue += ", " + html.escape(strip_latex(f["siteinfo"]))
        out.append('<span class="featured-venue">%s</span>' % venue)
    pills = ['<a class="pub-link" href="%s">%s</a>' % (html.escape(h), html.escape(l))
             for l, h in links if h]
    if pills:
        out.append('<span class="featured-links">%s</span>' % "\n".join(pills))
    out.append("</div>")
    return "\n".join(out)


def main():
    if not os.path.exists(BIB):
        sys.exit("publications.bib not found at %s" % BIB)
    text = open(BIB, encoding="utf-8").read()
    entries = parse_bib(text)
    if not entries:
        sys.exit("no entries parsed from publications.bib")

    os.makedirs(OUT, exist_ok=True)

    by_cat = {}
    for etype, key, fields in entries:
        f = fdict(fields)
        cat = f.get("sitecategory", "").strip()
        if not cat:
            continue
        by_cat.setdefault(cat, []).append((etype, key, fields))
    for cat in by_cat:
        by_cat[cat].sort(key=lambda e: int(fdict(e[2]).get("siteorder", "999")))

    slugs = []
    for etype, key, fields in entries:
        if has_page(fdict(fields)):
            slugs.append(render_paper_page(etype, key, fields))
    prune_pages(set(slugs))

    counts = []
    for page, sections in PAGES:
        chunks = []
        for cat, heading in sections:
            items = by_cat.get(cat, [])
            if not items:
                continue
            counts.append("%s %d" % (heading or "Discussions", len(items)))
            if heading:
                chunks.append('<h2 class="section-head">%s</h2>' % heading)
            chunks.append('<ol class="pub-list">')
            for i, (etype, key, fields) in enumerate(items, 1):
                chunks.append(render_entry(i, etype, key, fields))
            chunks.append("</ol>")
        with open(os.path.join(OUT, page + ".md"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(chunks) + "\n")

    # One hidden <script type="text/plain"> per entry; the JS reads these.
    store = []
    for etype, key, fields in entries:
        if fdict(fields).get("sitebib", "yes").lower() == "no":
            continue
        store.append('<script type="text/plain" class="bib-src" data-key="%s">%s</script>'
                     % (html.escape(key), html.escape(bibtex_text(etype, key, fields))))
    with open(os.path.join(OUT, "bibdata.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(store) + "\n")

    featured = [e for e in entries if fdict(e[2]).get("sitefeatured", "").lower() == "yes"]
    with open(os.path.join(OUT, "featured.md"), "w", encoding="utf-8") as fh:
        fh.write(render_featured(featured[0][2]) + "\n" if featured else "")

    cv = write_cv_date()
    print("build_pubs: %d entries -> %s | CV %s | paper pages: %s"
          % (len(entries), ", ".join(counts), cv or "date unknown",
             ", ".join(slugs) or "none"))


if __name__ == "__main__":
    main()
