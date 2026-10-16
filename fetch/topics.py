"""兴趣主题订阅：公开搜索 API（匿名 10 次/分，带限速）"""
import time

from .common import gh_get, norm_repo


def fetch(cfg):
    items = []
    min_stars = cfg.get("min_stars", 50)
    for t in cfg.get("topics", []):
        try:
            r = gh_get(
                "https://api.github.com/search/repositories", cfg,
                params={
                    "q": f"topic:{t} stars:>={min_stars}",
                    "sort": "updated", "order": "desc", "per_page": 20,
                },
            )
            arr = r.json().get("items", [])
        except Exception as e:
            print(f"[topics] {t} 失败: {e}")
            continue
        for it in arr:
            items.append(norm_repo(it, [f"topic:{t}"]))
        print(f"[topics] {t}: {len(arr)} 条")
        time.sleep(7)  # 匿名搜索限流 10 次/分
    return items
