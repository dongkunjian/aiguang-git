"""深挖矿机：星标游标法。每个主题记住上次挖到的最低星数，
下次搜 stars:min..cursor-1 继续往深处挖，源源不断出新货。
每次挖矿每主题 1 次搜索请求（匿名 10 次/分钟限额内）。"""
from .common import gh_get, norm_repo

K = "cursor:"


def _get_cursor(store, topic):
    r = store.conn.execute("SELECT v FROM mine_state WHERE k=?",
                           (K + topic,)).fetchone()
    return int(r["v"]) if r else None


def _set_cursor(store, topic, val):
    store.conn.execute("INSERT OR REPLACE INTO mine_state VALUES (?,?)",
                       (K + topic, str(val)))


def mine(cfg, store):
    """沿各主题星标梯子往下挖一层，返回新入库数量"""
    min_s = int(cfg.get("min_stars", 50))
    per = 100
    total_new = 0
    for t in cfg.get("topics", []):
        cur = _get_cursor(store, t)
        if cur is not None and cur <= min_s:
            continue  # 该主题已挖到底
        rng = f"{min_s}..{cur}" if cur else f">={min_s}"
        try:
            r = gh_get("https://api.github.com/search/repositories", cfg,
                       params={"q": f"topic:{t} stars:{rng}",
                               "sort": "stars", "order": "desc", "per_page": per})
            arr = r.json().get("items", [])
        except Exception:
            continue
        if not arr:
            _set_cursor(store, t, min_s)
            continue
        items = [norm_repo(x, [f"挖矿·{t}"]) for x in arr]
        n_new, _ = store.upsert_items(items)
        total_new += n_new
        smin = min(x.get("stargazers_count", 0) for x in arr)
        # 游标严格下降，防止星数密集时原地空转
        nxt = smin if (cur is None or smin < cur) else cur - 1
        if len(arr) < per:
            nxt = min_s  # 不足一页说明挖到底了
        _set_cursor(store, t, max(nxt, min_s))
    store.conn.commit()
    return total_new
