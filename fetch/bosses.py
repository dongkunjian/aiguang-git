"""大佬/组织动态：公开 events 里他们 star / 新建了什么"""
import time

from .common import gh_get, norm_repo


def fetch(cfg):
    bosses = cfg.get("bosses", [])
    if not bosses:
        print("[bosses] 未配置大佬名单，跳过（config.json 里 bosses 数组填 GitHub ID）")
        return []
    items, seen = [], set()
    for b in bosses:
        try:
            r = gh_get(f"https://api.github.com/users/{b}/events/public", cfg,
                       params={"per_page": 30})
            events = r.json()
        except Exception as e:
            print(f"[bosses] {b} 动态拉取失败: {e}")
            continue
        n = 0
        for ev in events:
            if ev.get("type") not in ("WatchEvent", "CreateEvent"):
                continue
            repo = (ev.get("repo") or {}).get("name")
            if not repo or repo in seen:
                continue
            seen.add(repo)
            try:
                it = gh_get(f"https://api.github.com/repos/{repo}", cfg).json()
            except Exception:
                continue
            items.append(norm_repo(it, [f"boss:{b}"]))
            n += 1
            if n >= 10:  # 每位大佬最多贡献 10 条，防刷屏
                break
            time.sleep(1)
        print(f"[bosses] {b}: {n} 条")
    return items
