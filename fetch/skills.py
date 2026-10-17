"""Skill 好物：GitHub 上的 AI Agent Skill 生态（SKILL.md / claude-skills 等）。
搜索 API 多路查询：星数榜=最热、更新时间榜=最新；今日增量用 star_snap 快照差分。"""
import time

from .common import gh_get, norm_repo

QUERIES = [
    # (查询, 排序, source 标签)
    ("topic:claude-skills", "stars", "skill:热榜"),
    ("topic:agent-skills", "stars", "skill:热榜"),
    ("claude skill in:name,description,topics stars:>20", "stars", "skill:热榜"),
    ("claude skill in:name,description,topics stars:>5", "updated", "skill:最新"),
    ("skill.md in:readme stars:>10", "updated", "skill:最新"),
]


def fetch(cfg, store=None):
    items = []
    for q, sort, tag in QUERIES:
        try:
            r = gh_get(
                "https://api.github.com/search/repositories", cfg,
                params={"q": q, "sort": sort, "order": "desc", "per_page": 50},
            )
            arr = r.json().get("items", [])
        except Exception as e:
            print(f"[skills] {q[:30]}… 失败: {e}")
            time.sleep(5)
            continue
        for it in arr:
            it2 = norm_repo(it, [tag])
            # 今日增量：与当天首次快照差分（次日起重跑即得真实今日新增星）
            if store is not None:
                it2["today_stars"] = store.gitee_today(it2["full_name"], it2["stars"])
            items.append(it2)
        print(f"[skills] {tag} ({q[:30]}…): {len(arr)} 条")
        time.sleep(3)  # 带 token 搜索限流 30 次/分，保守一点
    return items
