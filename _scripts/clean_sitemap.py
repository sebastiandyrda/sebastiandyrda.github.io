#!/usr/bin/env python3
"""Normalise sitemap.xml so it lists the URLs the site actually links to.

Quarto writes <loc>https://dyrda.info/research/index.html</loc>, but every link
on the site points at /research/. Left alone that is two URLs for one page, and
search engines may index both and split the ranking signal between them.

Run as a Quarto post-render step (see _quarto.yml).
"""

import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITEMAP = os.path.join(ROOT, "_site", "sitemap.xml")


def main():
    if not os.path.exists(SITEMAP):
        # No site-url configured yet, so Quarto emitted no sitemap. Not an error.
        print("clean_sitemap: no sitemap.xml, skipping")
        return 0

    xml = io.open(SITEMAP, encoding="utf-8").read()
    before = xml

    # .../index.html -> .../   and   /index.html at the root -> /
    xml = re.sub(r"(<loc>[^<]*?/)index\.html(</loc>)", r"\1\2", xml)

    # 404.html has no business in a sitemap.
    xml = re.sub(r"\s*<url>\s*<loc>[^<]*?/404\.html</loc>.*?</url>", "", xml, flags=re.S)

    if xml != before:
        io.open(SITEMAP, "w", encoding="utf-8").write(xml)

    locs = re.findall(r"<loc>([^<]+)</loc>", xml)
    print("clean_sitemap: %d URLs" % len(locs))
    for u in sorted(locs):
        print("  " + u)
    return 0


if __name__ == "__main__":
    sys.exit(main())
