"""star 历史相似推荐：读你的公开 star → 提取口味画像 → 搜相似好货"""
import time
from collections import Counter

from .common import days_ago, gh_get, norm_repo


def fetch(cfg):
    user = (cfg.get("github_username") or "").strip()
    if not user:
        print("[stars] 未配置 github_username，跳过（填上你的 GitHub 用户名即开启）")
        return []

    starred, page = [], 1
    while page <= 3:  # 最近 300 个 star 足够画像
        try:
            r = gh_get(f"https://api.github.com/users/{user}/starred", cfg,
                       params={"per_page": 100, "page": page})
        except Exception as e:
            print(f"[stars] 拉 star 列表失败: {e}")
            return []
        arr = r.json()
        if not arr:
            break
        starred += arr
        page += 1

    mine = {it["full_name"] for it in starred}
    topics = Counter(t for it in starred for t in (it.get("topics") or []))
    langs = Counter(it["language"] for it in starred if it.get("language"))
    print(f"[stars] 口味画像：语言 {dict(langs.most_common(5))}")
    print(f"[stars] 口味画像：主题 {dict(topics.most_common(8))}")

    queries = [f"topic:{t} stars:>100" for t, _ in topics.most_common(5)]
    queries += [f"language:{l} stars:>500 created:>{days_ago(180)}"
                for l, _ in langs.most_common(3)]

    items, seen = [], set()
    for q in queries:
        try:
            r = gh_get("https://api.github.com/search/repositories", cfg,
                       params={"q": q, "sort": "updated", "order": "desc", "per_page": 15})
            arr = r.json().get("items", [])
        except Exception as e:
            print(f"[stars] 搜索失败 [{q}]: {e}")
            continue
        for it in arr:
            if it["full_name"] in mine or it["full_name"] in seen:
                continue
            seen.add(it["full_name"])
            items.append(norm_repo(it, ["star-rec"]))
        time.sleep(7)  # 搜索限流
    print(f"[stars] 相似推荐 {len(items)} 条（已排除你已 star 的 {len(mine)} 个）")
    return items
