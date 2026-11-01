#!/usr/bin/env python3
"""defab_gate v3 — deterministic publish gate for review articles.

Rules (direction doc: company/affiliate_traffic_direction_20261101.md §4-2):
  R1 count   review counts in body must match front matter (total_reviews / review_count);
             counts attributed to sources we never snapshot (Amazon, YouTube, X) are not allowed
  R1 rating  star ratings in body must match front matter `rating` (±0.05)
  R2 first   first-party claims (当サイト調査, 実測, 筆者が使って ...) — the site has no own testing
  R3 anchor  link text that reads like an article title must not point at an affiliate URL
  R4 hygiene example.com links, dead internal links, "2024年…時点" style stale prices

Usage:
  python3 tools/defab_gate_v3.py scan [--out PATH]      # report mode, all articles, exit 0
  python3 tools/defab_gate_v3.py check FILE...          # fail mode, exit 1 on any violation
  python3 tools/defab_gate_v3.py ci BASE_SHA            # check content files changed since BASE_SHA
"""
import json
import pathlib
import re
import subprocess
import sys
import urllib.parse

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
REVIEWS = ROOT / "content" / "reviews"

UNSNAPSHOTTED = r"(?:Amazon|アマゾン|YouTube|ユーチューブ|X|Twitter|価格\.com|カカクコム|SNS)"
SOURCE_COUNT = re.compile(UNSNAPSHOTTED + r"[^。\n]{0,12}?([0-9][0-9,]*)\s*(?:件|人|名|本)")
COUNT = re.compile(r"([0-9][0-9,]{1,})\s*件(?:の|を|超|以上)?(?:口コミ|レビュー|評価)")
RATING = re.compile(r"(?:★|星|評価|平均)\s*([1-5]\.[0-9]{1,2})")
FIRST_PARTY = re.compile(
    r"当サイト(?:で|では|が|の)?(?:調査|検証|計測|測定|実測|比較|テスト)(?!時点)"
    r"|当サイト調査(?!時点)|編集部|筆者が|私が(?:使|試|買)|実際に使って(?:みた|みる|いる)|使ってみた(?!い)"
)
MEASURED = re.compile(r"実測|実機で")
MEASURED_OK = re.compile(r"YouTube|ユーチューブ|公式|メーカー|レビュアー|ユーザー|購入者|口コミ|投稿|動画|報告")
LINK = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)\s]+)[^)]*\)")
AFFILIATE = re.compile(r"hb\.afl\.rakuten|af\.moshimo\.com|/go/rakuten|amazon\.co\.jp|a\.r10\.to")
ARTICLE_ANCHOR = re.compile(r"[0-9０-９]+選|活用術|記事|まとめ(?!買)|ガイド|徹底(?:比較|解説)|完全版|ランキング")
STALE_PRICE = re.compile(r"20(?:1[0-9]|2[0-4])年[0-9]{0,2}月?(?:[0-9]{1,2}日)?(?:時点|現在)")
EXAMPLE = re.compile(r"example\.(?:com|jp|org)")


def split_front(text):
    if not text.startswith("---"):
        return {}, text
    _, fm, body = text.split("---", 2)
    try:
        return yaml.safe_load(fm) or {}, body
    except yaml.YAMLError:
        return {}, body


def num(s):
    try:
        return int(str(s).replace(",", ""))
    except ValueError:
        return None


def valid_paths():
    """Internal URL paths that resolve: review slugs + aliases + static files + built pages."""
    paths = set()
    for p in REVIEWS.glob("*.md"):
        fm, _ = split_front(p.read_text(encoding="utf-8"))
        slug = fm.get("slug") or p.stem
        paths.add(f"/reviews/{slug}/")
        for a in fm.get("aliases") or []:
            paths.add(a if a.endswith("/") else a + "/")
    public = ROOT / "public"
    if public.exists():
        for idx in public.rglob("index.html"):
            paths.add("/" + str(idx.parent.relative_to(public)).strip(".") + "/")
    for d in (ROOT / "static", ROOT / "content"):
        for f in d.rglob("*"):
            if f.is_dir():
                paths.add("/" + str(f.relative_to(d)) + "/")
            else:
                paths.add("/" + str(f.relative_to(d)))
    return {urllib.parse.unquote(x).replace("//", "/") for x in paths}


def sentence_at(body, pos):
    start = max(body.rfind("。", 0, pos), body.rfind("\n", 0, pos)) + 1
    end_candidates = [i for i in (body.find("。", pos), body.find("\n", pos)) if i != -1]
    return body[start:min(end_candidates) if end_candidates else len(body)]


def check_file(path, paths):
    text = path.read_text(encoding="utf-8")
    fm, body = split_front(text)
    if fm.get("draft") or fm.get("noindex") is True:
        return []
    out = []

    def add(rule, m, msg):
        line = body.count("\n", 0, m.start()) + text[: len(text) - len(body)].count("\n") + 1
        out.append({"rule": rule, "line": line, "msg": msg, "text": m.group(0)[:60]})

    allowed = {n for n in (num(fm.get("total_reviews")), num(fm.get("review_count"))) if n}
    for m in SOURCE_COUNT.finditer(body):
        add("R1-count", m, "count attributed to an unsnapshotted source")
    for m in COUNT.finditer(body):
        n = num(m.group(1))
        if n and n not in allowed:
            add("R1-count", m, f"count {n} not in front matter {sorted(allowed)}")
    rating = fm.get("rating")
    if isinstance(rating, (int, float)) and rating > 0:
        for m in RATING.finditer(body):
            if abs(float(m.group(1)) - float(rating)) > 0.05:
                add("R1-rating", m, f"rating {m.group(1)} != front matter {rating}")

    for m in FIRST_PARTY.finditer(body):
        add("R2-first", m, "first-party claim (no own testing)")
    for m in MEASURED.finditer(body):
        if not MEASURED_OK.search(sentence_at(body, m.start())):
            add("R2-first", m, "measurement without an external source")

    for m in LINK.finditer(body):
        anchor, url = m.group(1), m.group(2)
        if AFFILIATE.search(url) and ARTICLE_ANCHOR.search(anchor):
            add("R3-anchor", m, "article-like anchor points at an affiliate URL")
        if EXAMPLE.search(url):
            add("R4-example", m, "example domain link")
        elif url.startswith("/") and not url.startswith("//"):
            p = urllib.parse.unquote(url.split("#")[0].split("?")[0])
            if p and p not in paths and (p.rstrip("/") + "/") not in paths:
                add("R4-deadlink", m, f"internal link target missing: {p}")
    for m in STALE_PRICE.finditer(body):
        add("R4-stale", m, "stale dated price/as-of statement")
    return out


def scan(out_path):
    paths = valid_paths()
    results = {}
    for p in sorted(REVIEWS.glob("*.md")):
        v = check_file(p, paths)
        if v:
            results[p.name] = v
    by_rule = {}
    for vs in results.values():
        for v in vs:
            by_rule[v["rule"]] = by_rule.get(v["rule"], 0) + 1
    total = len(list(REVIEWS.glob("*.md")))
    out = pathlib.Path(out_path)
    out.write_text(json.dumps({"total_articles": total, "violating_articles": len(results),
                               "by_rule": by_rule, "articles": results}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"scanned {total} articles: {len(results)} violating")
    for r, n in sorted(by_rule.items()):
        print(f"  {r}: {n}")
    print(f"report -> {out}")
    return 0


def check(files):
    paths = valid_paths()
    bad = 0
    for f in files:
        p = pathlib.Path(f)
        if not p.exists() or p.suffix != ".md":
            continue
        for v in check_file(p, paths):
            bad += 1
            print(f"{p.name}:{v['line']}: [{v['rule']}] {v['msg']} :: {v['text']}")
    if bad:
        print(f"defab_gate v3: {bad} violation(s)")
        return 1
    print("defab_gate v3: OK")
    return 0


def ci(base):
    if not base or set(base) == {"0"}:
        return 0
    diff = subprocess.run(["git", "diff", "--name-only", "--diff-filter=AM", base, "HEAD", "--", "content/reviews/"],
                          cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    return check([ROOT / f for f in diff])


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "scan"
    if cmd == "scan":
        out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else "/tmp/defab_v3_report.json"
        sys.exit(scan(out))
    if cmd == "check":
        sys.exit(check(sys.argv[2:]))
    if cmd == "ci":
        sys.exit(ci(sys.argv[2] if len(sys.argv) > 2 else ""))
    sys.exit(__doc__)
