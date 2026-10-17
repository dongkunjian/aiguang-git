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


def main():
    cfg = load_config()
    store = Store(cfg["db_path"])
    print(f"===== 爱逛GIT 抓取 {now_str()} =====\n")
    total_new = run_pipeline(cfg, store)
    print(f"===== 完成：库内累计 {store.count()} 个项目，本次新增 {total_new} =====")


if __name__ == "__main__":
    main()
