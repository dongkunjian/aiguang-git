"""一键抓取四路货源并入库。用法：python run_fetch.py"""
import inspect
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from fetch import bosses, gitee, skills, stars, topics, trending
from fetch.common import load_config
from store import Store, now_str

PIPELINE = [
    ("Trending 热榜", trending),
    ("主题订阅", topics),
    ("star 相似推荐", stars),
    ("大佬动态", bosses),
    ("Gitee 好物", gitee),
    ("Skill 好物", skills),
]


def run_pipeline(cfg, store):
    """逐路抓取入库；支持 store 参数的模块（如 gitee 算今日增量）自动传入"""
    total_new = 0
    for name, mod in PIPELINE:
        if "store" in inspect.signature(mod.fetch).parameters:
            items = mod.fetch(cfg, store=store)
        else:
            items = mod.fetch(cfg)
        n_new, n_upd = store.upsert_items(items)
        total_new += n_new
        print(f">>> {name}: 抓到 {len(items)} 条（新入库 {n_new} / 更新 {n_upd}）\n")
    n_mirror = store.refresh_mirrors()
    if n_mirror:
        print(f">>> 镜像归并: {n_mirror} 对 GitHub/Gitee 双源合并\n")
    return total_new


def batch_interpret(cfg, store, limit=30):
    """每日为还没有中文解读的项目预生成翻译（限量，优先热项目；失败不缓存，明日重试）"""
    from fetch import interpret as interp_mod
    rows = store.conn.execute(
        "SELECT full_name FROM items WHERE full_name NOT IN (SELECT full_name FROM interpret)"
        " ORDER BY stars DESC LIMIT ?", (limit,)).fetchall()
    n = 0
    for r in rows:
        try:
            interp_mod.interpret(cfg, store, r["full_name"])
            n += 1
        except Exception as e:
            print(f"[interpret] {r['full_name']} 失败: {e}")
    return n


def main():
    cfg = load_config()
    store = Store(cfg["db_path"])
    print(f"===== 爱逛GIT 抓取 {now_str()} =====\n")
    total_new = run_pipeline(cfg, store)
    n_tr = batch_interpret(cfg, store)
    print(f">>> 预翻译: 本次新译 {n_tr} 个项目解读\n")
    print(f"===== 完成：库内累计 {store.count()} 个项目，本次新增 {total_new} =====")


if __name__ == "__main__":
    main()
