#!/usr/bin/env python3
"""List the URLs to submit to IndexNow after a deploy.

  python3 tools/indexnow_urls.py BASE_SHA [--all]

Maps content files changed since BASE_SHA to permalinks with `hugo list all`
(so slug rules are Hugo's own), keeps only URLs present in the built
public/sitemap.xml (drops noindex/taxonomy pages and deleted files), and
prints a JSON array. --all prints every sitemap URL (one-time seeding).
Direction doc §5 (11/16 row): IndexNow, judged by Bing organic sessions.
"""
import csv
import io
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MAX_URLS = 10000  # IndexNow per-request limit


def sitemap_urls() -> list[str]:
    xml = (ROOT / "public" / "sitemap.xml").read_text(encoding="utf-8")
    return re.findall(r"<loc>([^<]+)</loc>", xml)


def changed_paths(base: str) -> set[str]:
    out = subprocess.run(["git", "diff", "--name-only", "--diff-filter=AMR", f"{base}..HEAD", "--", "content/"],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return {p.strip() for p in out.splitlines() if p.strip().endswith(".md")}


def permalinks() -> dict[str, str]:
    out = subprocess.run(["hugo", "list", "all"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return {row["path"]: row["permalink"] for row in csv.DictReader(io.StringIO(out))}


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    in_sitemap = sitemap_urls()
    if "--all" in sys.argv[2:]:
        urls = in_sitemap
    else:
        allowed = set(in_sitemap)
        links = permalinks()
        urls = sorted({links[p] for p in changed_paths(sys.argv[1]) if links.get(p) in allowed})
    print(json.dumps(urls[:MAX_URLS], ensure_ascii=False))


if __name__ == "__main__":
    main()
