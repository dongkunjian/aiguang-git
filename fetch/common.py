"""抓取层公共工具：配置加载 / HTTP / 数据归一化"""
import json
import os
from datetime import datetime, timedelta, timezone

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CST = timezone(timedelta(hours=8))

UA = {"User-Agent": "aiguang-git/0.1", "Accept": "application/vnd.github+json"}

# 环境变量 → 配置项。云上密钥走环境变量注入，不打进镜像、不落仓库。
ENV_MAP = {
    "AIGUANG_GITHUB_TOKEN": "github_token",
    "AIGUANG_GITEE_TOKEN": "gitee_token",
    "AIGUANG_ACCESS_CODE": "access_code",
    "AIGUANG_MYMEMORY_EMAIL": "mymemory_email",
    "AIGUANG_DATA_DIR": "data_dir",
    "AIGUANG_DB_PATH": "db_path",
    "PORT": "port",
}


def load_config():
    """配置优先级：内置默认 → config.json → 环境变量（后者覆盖前者）。
    容器里通常只有一个数据卷 + 环境变量，没有 config.json，所以必须能缺省运行。"""
    cfg = {}
    for p in (os.path.join(ROOT, "config.example.json"),
              os.path.join(ROOT, "config.json")):
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                cfg.update(json.load(f))
    for env, key in ENV_MAP.items():
        v = os.environ.get(env)
        if v:
            cfg[key] = int(v) if key == "port" and v.isdigit() else v

    # SQLite / 头像缓存 / 备份都落在这个目录；容器里把它挂成持久卷
    data_dir = cfg.get("data_dir") or os.path.join(ROOT, "data")
    cfg["data_dir"] = data_dir
    db = cfg.get("db_path") or "aiguang.db"
    cfg["db_path"] = db if os.path.isabs(db) else os.path.join(data_dir, os.path.basename(db))
    return cfg


def gh_get(url, cfg, params=None, raw=False):
    headers = dict(UA)
    if cfg.get("github_token"):
        headers["Authorization"] = f"Bearer {cfg['github_token']}"
    if raw:
        headers["Accept"] = "text/html,application/xhtml+xml"
    r = requests.get(url, headers=headers, params=params, timeout=20)
    r.raise_for_status()
    return r


def norm_repo(it, sources):
    """GitHub API 的 repo JSON → 统一 item"""
    return {
        "full_name": it["full_name"],
        "name": it["name"],
        "owner": it["owner"]["login"],
        "url": it["html_url"],
        "description": it.get("description") or "",
        "language": it.get("language") or "",
        "stars": it.get("stargazers_count", 0),
        "forks": it.get("forks_count", 0),
        "today_stars": 0,
        "topics": it.get("topics") or [],
        "sources": sources,
        "avatar": (it.get("owner") or {}).get("avatar_url", ""),
        "pushed_at": it.get("pushed_at") or "",
        "updated_at": it.get("updated_at") or "",
    }


def days_ago(n):
    return (datetime.now(timezone.utc) - timedelta(days=n)).strftime("%Y-%m-%d")
