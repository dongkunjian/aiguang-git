"""SQLite 存储层：item 去重入库 + 收藏"""
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone

CST = timezone(timedelta(hours=8))


def now_str():
    return datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")


SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  full_name   TEXT PRIMARY KEY,
  name        TEXT,
  owner       TEXT,
  url         TEXT,
  description TEXT,
  language    TEXT,
  stars       INTEGER DEFAULT 0,
  forks       INTEGER DEFAULT 0,
  today_stars INTEGER DEFAULT 0,
  topics      TEXT DEFAULT '[]',
  sources     TEXT DEFAULT '[]',
  avatar      TEXT,
  pushed_at   TEXT,
  fetched_at  TEXT,
  updated_at  TEXT
);
CREATE TABLE IF NOT EXISTS favs (
  full_name TEXT PRIMARY KEY,
  fav_at    TEXT
);
CREATE TABLE IF NOT EXISTS interpret (
  full_name  TEXT PRIMARY KEY,
  cn_text    TEXT,
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS mine_state (
  k TEXT PRIMARY KEY,
  v TEXT
);
CREATE TABLE IF NOT EXISTS star_snap (
  full_name TEXT,
  day       TEXT,
  stars     INTEGER,
  PRIMARY KEY (full_name, day)
);
CREATE TABLE IF NOT EXISTS mirror_map (
  gitee_fn  TEXT PRIMARY KEY,
  github_fn TEXT
);
CREATE TABLE IF NOT EXISTS prefs (
  tag TEXT PRIMARY KEY,
  w   REAL DEFAULT 0
);
"""


class Store:
    def __init__(self, db_path):
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def upsert_items(self, items):
        """按 full_name 去重合并：sources 取并集，today_stars 取最大值"""
        cur = self.conn.cursor()
        n_new = n_upd = 0
        for it in items:
            row = cur.execute(
                "SELECT sources, today_stars FROM items WHERE full_name=?",
                (it["full_name"],),
            ).fetchone()
            topics = json.dumps(it.get("topics", []), ensure_ascii=False)
            if row is None:
                cur.execute(
                    "INSERT INTO items (full_name,name,owner,url,description,language,stars,"
                    "forks,today_stars,topics,sources,avatar,pushed_at,fetched_at,updated_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        it["full_name"], it.get("name"), it.get("owner"), it.get("url"),
                        it.get("description"), it.get("language"), it.get("stars", 0),
                        it.get("forks", 0), it.get("today_stars", 0), topics,
                        json.dumps(it.get("sources", []), ensure_ascii=False),
                        it.get("avatar"), it.get("pushed_at"), now_str(),
                        it.get("updated_at"),
                    ),
                )
                n_new += 1
            else:
                sources = sorted(set(json.loads(row["sources"])) | set(it.get("sources", [])))
                today = max(row["today_stars"] or 0, it.get("today_stars", 0))
                cur.execute(
                    "UPDATE items SET name=?,owner=?,url=?,description=?,language=?,stars=?,"
                    "forks=?,today_stars=?,topics=?,sources=?,avatar=?,pushed_at=?,"
                    "fetched_at=?,updated_at=? WHERE full_name=?",
                    (
                        it.get("name"), it.get("owner"), it.get("url"),
                        it.get("description"), it.get("language"), it.get("stars", 0),
                        it.get("forks", 0), today, topics,
                        json.dumps(sources, ensure_ascii=False),
                        it.get("avatar"), it.get("pushed_at"), now_str(),
                        it.get("updated_at"), it["full_name"],
                    ),
                )
                n_upd += 1
        self.conn.commit()
        return n_new, n_upd

    def count(self):
        return self.conn.execute("SELECT COUNT(*) c FROM items").fetchone()["c"]

    def cache_interpret(self, full_name, text):
        self.conn.execute("INSERT OR REPLACE INTO interpret VALUES (?,?,?)",
                          (full_name, text, now_str()))
        self.conn.commit()

    def gitee_today(self, full_name, stars):
        """Gitee 没有官方今日星：以当天首次快照为基线，返回真实增量"""
        day = now_str()[:10]
        r = self.conn.execute("SELECT stars FROM star_snap WHERE full_name=? AND day=?",
                              (full_name, day)).fetchone()
        if r is None:
            self.conn.execute("INSERT OR IGNORE INTO star_snap VALUES (?,?,?)",
                              (full_name, day, stars))
            return 0
        return max(0, stars - (r["stars"] or 0))

    def refresh_mirrors(self):
        """GitHub 卡与 Gitee 卡疑似同一项目（镜像）→ 记映射表，展示时合并。
        判定保守：name 完全相同 + 语言一致（或一方为空）+ 描述相容（相等/包含/一方为空）"""
        rows = self.conn.execute(
            "SELECT full_name, name, description, language FROM items").fetchall()
        gh = {}
        for r in rows:
            if not r["full_name"].startswith("gitee/"):
                gh[(r["name"] or "").lower()] = r
        n = 0
        for r in rows:
            if not r["full_name"].startswith("gitee/"):
                continue
            g = gh.get((r["name"] or "").lower())
            if not g:
                continue
            gl, hl = (r["language"] or ""), (g["language"] or "")
            if gl and hl and gl != hl:
                continue
            gd, hd = (r["description"] or "").strip(), (g["description"] or "").strip()
            if gd and hd and gd != hd and gd[:20] not in hd and hd[:20] not in gd:
                # 前缀不相容时再看整体相似度（镜像仓简介常有措辞微调）
                import difflib
                if difflib.SequenceMatcher(None, gd, hd).ratio() < 0.55:
                    continue
            self.conn.execute("INSERT OR IGNORE INTO mirror_map VALUES (?,?)",
                              (r["full_name"], g["full_name"]))
            n += 1
        self.conn.commit()
        return n

    def mirror_pairs(self):
        """github_fn → gitee_fn 映射（合并展示用）"""
        return {r["github_fn"]: r["gitee_fn"]
                for r in self.conn.execute("SELECT * FROM mirror_map")}

    def bump_prefs(self, full_name, delta):
        """收藏/星标行为 → 记录语言与 topics 偏好权重（hot 排序个性化倾斜）"""
        r = self.conn.execute("SELECT language, topics FROM items WHERE full_name=?",
                              (full_name,)).fetchone()
        if not r:
            return
        tags = ([r["language"]] if r["language"] else []) + json.loads(r["topics"] or "[]")
        for t in tags:
            self.conn.execute(
                "INSERT INTO prefs VALUES (?,?) ON CONFLICT(tag) DO UPDATE SET w=MAX(0,w+?)",
                (t, max(delta, 0), delta))
        self.conn.execute("DELETE FROM prefs WHERE w<=0")
        self.conn.commit()

    def prefs_map(self):
        return {r["tag"]: r["w"] for r in self.conn.execute("SELECT tag, w FROM prefs")}

    def backup(self, dest_path):
        """sqlite 在线备份（一致性快照）"""
        dst = sqlite3.connect(dest_path)
        try:
            self.conn.backup(dst)
        finally:
            dst.close()
