"""GitHub Trending 热榜（HTML 爬虫，无官方 API）"""
from bs4 import BeautifulSoup

from .common import gh_get


def _int(text):
    digits = text.strip().replace(",", "")
    return int("".join(c for c in digits if c.isdigit()) or 0)


def fetch(cfg):
    since = cfg.get("trending_since", "daily")
    slugs = [""] + [l.lower().replace(" ", "-") for l in cfg.get("languages", [])]
    seen = set()
    items = []
    for slug in slugs:
        url = f"https://github.com/trending/{slug}" if slug else "https://github.com/trending"
        try:
            r = gh_get(url, cfg, params={"since": since}, raw=True)
        except Exception as e:
            print(f"[trending] {slug or 'all'} 失败: {e}")
            continue
        soup = BeautifulSoup(r.text, "html.parser")
        n = 0
        for art in soup.select("article.Box-row"):
            a = art.select_one("h2 a")
            if not a or not a.get("href"):
                continue
            full = a["href"].strip("/")
            if full in seen:
                continue
            seen.add(full)
            owner, _, name = full.partition("/")
            desc_el = art.select_one("p")
            lang_el = art.select_one('[itemprop="programmingLanguage"]')
            muted = art.select("a.Link--muted")
            today_el = art.select_one("span.float-sm-right")
            img = art.select_one("img")
            items.append({
                "full_name": full,
                "name": name,
                "owner": owner,
                "url": f"https://github.com/{full}",
                "description": desc_el.get_text(strip=True) if desc_el else "",
                "language": lang_el.get_text(strip=True) if lang_el else "",
                "stars": _int(muted[0].get_text()) if len(muted) > 0 else 0,
                "forks": _int(muted[1].get_text()) if len(muted) > 1 else 0,
                "today_stars": _int(today_el.get_text()) if today_el else 0,
                "topics": [],
                "sources": ["trending"],
                "avatar": img["src"] if img and img.get("src") else "",
                "pushed_at": "",
                "updated_at": "",
            })
            n += 1
        print(f"[trending] {slug or 'all'}: {n} 条")
    return items
