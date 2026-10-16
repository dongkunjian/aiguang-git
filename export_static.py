"""静态导出：SQLite → web/data/feed.json + web/data/cn.json（供 Cloudflare Pages 纯静态托管）。
用法：python export_static.py

产物只有 JSON，前端一次性拉全量、客户端搜索/排序/分页，无需任何后端进程。
- feed.json：项目卡片数据（不预置镜像/代理链接，前端按 meta 配置自行拼接，改镜像站无需重导）
- cn.json  ：中文解读字典（full_name → 文本），前端首次需要时懒加载，避免主数据包随翻译量膨胀
"""
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from fetch.common import ROOT, load_config
from store import Store, now_str


def build_feed(cfg, store):
    """把库内项目整理成前端可直接消费的一包 JSON"""
    pairs = store.mirror_pairs()                      # github_fn → gitee_fn
    paired_gitee = set(pairs.values())                # 已并进 GitHub 卡的 Gitee 卡，默认流不重复出

    items = []
    for r in store.conn.execute("SELECT * FROM items"):
        fn = r["full_name"]
        if fn in paired_gitee:                        # 镜像卡：并入 GitHub 卡展示
            continue
        d = {
            "full_name": fn,
            "name": r["name"],
            "owner": r["owner"],
            "url": r["url"],
            "description": r["description"] or "",
            "language": r["language"] or "",
            "stars": r["stars"] or 0,
            "forks": r["forks"] or 0,
            "today_stars": r["today_stars"] or 0,
            "topics": json.loads(r["topics"] or "[]"),
            "sources": json.loads(r["sources"] or "[]"),
            "avatar": r["avatar"] or "",
            "pushed_at": r["pushed_at"] or "",
            "fetched_at": r["fetched_at"] or "",
        }
        if fn in pairs:                               # 这张 GitHub 卡有 Gitee 镜像：补镜像链接
            d["gitee_url"] = "https://gitee.com/" + pairs[fn][len("gitee/"):]
            if "Gitee" not in d["sources"]:
                d["sources"].append("Gitee")
        items.append(d)

    last = store.conn.execute("SELECT MAX(fetched_at) t FROM items").fetchone()["t"]
    meta = {
        "total": len(items),
        "last_fetch": last,
        "gh_mirror": (cfg.get("gh_mirror") or "").rstrip("/"),
        "gh_proxy": (cfg.get("gh_proxy") or "").rstrip("/"),
        "generated_at": now_str(),
    }
    return {"meta": meta, "items": items}


def export(cfg, store):
    out_dir = os.path.join(ROOT, "web", "data")
    os.makedirs(out_dir, exist_ok=True)

    feed = build_feed(cfg, store)
    feed_path = os.path.join(out_dir, "feed.json")
    with open(feed_path, "w", encoding="utf-8") as f:
        # 紧凑输出（无多余空格），配合 gzip 体积更小
        json.dump(feed, f, ensure_ascii=False, separators=(",", ":"))

    # 合并策略：仓库里已入库的 cn.json 是历史翻译基线（Actions 直传部署不回写 git，
    # 新翻译都落在 cache 的 db 里）。基线保底 + db 覆盖，保证解读只增不减。
    cn_path = os.path.join(out_dir, "cn.json")
    cn = {}
    if os.path.exists(cn_path):
        try:
            with open(cn_path, encoding="utf-8") as f:
                cn = json.load(f)
        except Exception:
            cn = {}
    for r in store.conn.execute("SELECT full_name, cn_text FROM interpret"):
        cn[r["full_name"]] = r["cn_text"]
    with open(cn_path, "w", encoding="utf-8") as f:
        json.dump(cn, f, ensure_ascii=False, separators=(",", ":"))

    return feed_path, cn_path, feed["meta"], len(cn)


def main():
    cfg = load_config()
    store = Store(cfg["db_path"])
    feed_path, cn_path, meta, n_cn = export(cfg, store)
    print(f"===== 静态导出 {meta['generated_at']} =====")
    print(f">>> feed.json  {meta['total']} 个项目 · {os.path.getsize(feed_path)/1024:.0f} KB")
    print(f">>> cn.json    {n_cn} 条解读 · {os.path.getsize(cn_path)/1024:.0f} KB")
    print(f">>> 上次抓货 {meta['last_fetch']}")


if __name__ == "__main__":
    main()
