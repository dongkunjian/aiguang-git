"""爱逛GIT API 服务：feed / 详情 / 收藏 / 刷新。启动：python server.py"""
import glob as _glob
import json
import os
import threading

import requests
from fastapi import FastAPI, Query, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from fetch.common import ROOT, UA, load_config
from store import Store, now_str

cfg = load_config()
store = Store(cfg["db_path"])
app = FastAPI(title="爱逛GIT")

CODE = (cfg.get("access_code") or "").strip()


LOGIN_HTML = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>爱逛GIT · 访问口令</title><style>
body{font-family:-apple-system,"PingFang SC",sans-serif;background:#f6f7f9;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}
.box{background:#fff;border-radius:16px;box-shadow:0 2px 12px rgba(0,0,0,.08);padding:36px 32px;text-align:center;max-width:320px;width:88%}
h1{font-size:22px;color:#2563eb;margin:0 0 8px}p{color:#6b7280;font-size:14px;margin:0 0 20px}
input{width:100%;padding:12px 14px;border:1px solid #ddd;border-radius:10px;font-size:16px;outline:none;box-sizing:border-box}
input:focus{border-color:#2563eb}
button{margin-top:14px;width:100%;padding:12px;border:none;border-radius:10px;background:#2563eb;color:#fff;font-size:16px;font-weight:700;cursor:pointer}
.err{color:#dc2626;font-size:13px;margin-top:10px;display:none}
</style></head><body><form class="box" method="get" action="/">
<h1>爱逛GIT</h1><p>输入访问口令进入（只需输一次，之后自动记住）</p>
<input name="code" type="password" placeholder="访问口令" autofocus autocomplete="off">
<button type="submit">进入</button>
<div class="err" id="e">口令不对，再试一次</div>
<script>if(location.search.includes('code='))document.getElementById('e').style.display='block'</script>
</form></body></html>"""


@app.middleware("http")
async def gate(request, call_next):
    """access_code 非空时全站校验（外网暴露用），空则放行。
    口令通过一次即种 cookie（一年有效），之后裸地址直接进，不用再带 ?code="""
    if CODE:
        q = request.query_params.get("code")
        if q == CODE and not request.url.path.startswith("/api/"):
            # 页面入口口令正确：种 cookie 并跳回干净地址（地址栏不再带口令）
            r = RedirectResponse(request.url.path)
            r.set_cookie("ag_auth", CODE, max_age=86400 * 365,
                         httponly=True, samesite="lax")
            return r
        if (request.headers.get("X-Code") == CODE
                or request.cookies.get("ag_auth") == CODE or q == CODE):
            return await call_next(request)
        if request.url.path.startswith("/api/"):
            return JSONResponse({"error": "需要访问口令"}, status_code=401)
        return HTMLResponse(LOGIN_HTML, status_code=401)
    return await call_next(request)


def fav_set():
    return {r[0] for r in store.conn.execute("SELECT full_name FROM favs")}


MIRROR = (cfg.get("gh_mirror") or "").rstrip("/")
PROXY = (cfg.get("gh_proxy") or "").rstrip("/")


@app.post("/api/reload")
def reload_cfg():
    """config.json 热加载：改令牌/镜像/口令/翻译邮箱等免重启（host/port 除外）"""
    global cfg, CODE, MIRROR, PROXY
    cfg = load_config()
    CODE = (cfg.get("access_code") or "").strip()
    MIRROR = (cfg.get("gh_mirror") or "").rstrip("/")
    PROXY = (cfg.get("gh_proxy") or "").rstrip("/")
    return {"ok": True}


def row_to_item(r, favs, pairs=None):
    d = dict(r)
    d["topics"] = json.loads(d["topics"] or "[]")
    d["sources"] = json.loads(d["sources"] or "[]")
    d["fav"] = d["full_name"] in favs
    d["mirror_url"] = d["url"].replace("https://github.com", MIRROR, 1) if MIRROR else d["url"]
    d["proxy_url"] = f"{PROXY}/{d['url']}" if PROXY else d["url"]
    if pairs and d["full_name"] in pairs:  # 该 GitHub 卡有对应 Gitee 镜像：合并成双源卡
        d["gitee_url"] = "https://gitee.com/" + pairs[d["full_name"]][len("gitee/"):]
        if "Gitee" not in d["sources"]:
            d["sources"].append("Gitee")
    return d


AVATAR_DIR = os.path.join(cfg["data_dir"], "avatars")
os.makedirs(AVATAR_DIR, exist_ok=True)
_avatar_bad = set()  # 拉不动的地址记入会话黑名单，避免反复打外部请求
_AV_EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif",
           "image/webp": ".webp", "image/svg+xml": ".svg"}


def _avatar_svg(letter):
    """裂图兜底：首字母彩色占位图（服务端直出，永不断头）"""
    ch = (letter or "?")[0].upper()
    hue = (ord(ch) * 47) % 360
    svg = (f"<svg xmlns='http://www.w3.org/2000/svg' width='52' height='52'>"
           f"<rect width='52' height='52' rx='12' fill='hsl({hue},58%,68%)'/>"
           f"<text x='26' y='36' font-size='26' text-anchor='middle' "
           f"font-family='sans-serif' fill='#fff'>{ch}</text></svg>")
    return Response(svg, media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/avatar/{fn:path}")
def avatar(fn: str):
    """头像服务端缓存代理：抓一次存 data/avatars/，国内不再裂图"""
    parts = fn.split("/")
    letter = parts[-2] if len(parts) >= 2 else fn
    base = os.path.join(AVATAR_DIR, fn.replace("/", "__"))
    hit = _glob.glob(base + ".*")
    if hit:
        return FileResponse(hit[0], headers={"Cache-Control": "public, max-age=604800"})
    if fn in _avatar_bad:
        return _avatar_svg(letter)
    row = store.conn.execute("SELECT avatar FROM items WHERE full_name=?",
                             (fn,)).fetchone()
    url = (row["avatar"] or "") if row else ""
    if url:
        try:
            r = requests.get(url, headers=UA, timeout=10)
            ct = r.headers.get("Content-Type", "").split(";")[0].lower()
            if r.status_code == 200 and (ct in _AV_EXT or r.content[:8].startswith(b"\x89PNG")):
                ext = _AV_EXT.get(ct, ".png")
                with open(base + ext, "wb") as f:
                    f.write(r.content)
                return FileResponse(base + ext,
                                    headers={"Cache-Control": "public, max-age=604800"})
        except Exception:
            pass
    _avatar_bad.add(fn)
    return _avatar_svg(letter)


@app.get("/api/feed")
def feed(offset: int = 0, limit: int = Query(30, le=100), sort: str = "hot",
         q: str = "", src: str = "", fav: int = 0):
    where, args = [], []
    if fav:
        where.append("full_name IN (SELECT full_name FROM favs)")
    if q:
        like = f"%{q}%"
        # 搜名字/简介/topics/已生成的中文解读，中文关键词也能搜到货
        where.append("(full_name LIKE ? OR description LIKE ? OR topics LIKE ?"
                     " OR full_name IN (SELECT full_name FROM interpret WHERE cn_text LIKE ?))")
        args += [like, like, like, like]
    if src == "Gitee":
        where.append("full_name LIKE 'gitee/%'")
    elif src == "GitHub":
        where.append("full_name NOT LIKE 'gitee/%'")
    elif src:
        where.append("sources LIKE ?")
        args.append(f'%"{src}%')
    else:
        # 默认流：与 GitHub 卡合并的 Gitee 镜像卡不重复出现（展示为双源卡）
        where.append("full_name NOT IN (SELECT gitee_fn FROM mirror_map)")
    wsql = (" WHERE " + " AND ".join(where)) if where else ""
    order_args = []
    if sort == "hot":
        # 个性化倾斜：收藏/星标过的语言与 topics 记权重，hot 排序加权上浮
        pr = store.prefs_map()
        if pr:
            bonus = " + ".join(
                f"(CASE WHEN topics LIKE ? OR language = ? THEN {min(w, 10) * 25.0:.1f} ELSE 0 END)"
                for w in pr.values())
            order = f"today_stars + {bonus} DESC, stars DESC"
            for t in pr:
                order_args += [f'%"{t}"%', t]
        else:
            order = "today_stars DESC, stars DESC"
    else:
        order = {
            "rising": "CAST(today_stars AS REAL)/MAX(stars,1) DESC, today_stars DESC",
            "new": "fetched_at DESC",
            "stars": "stars DESC",
            "rand": "RANDOM()",
        }.get(sort, "today_stars DESC, stars DESC")
    total = store.conn.execute(f"SELECT COUNT(*) c FROM items{wsql}", args).fetchone()["c"]
    rows = store.conn.execute(
        f"SELECT * FROM items{wsql} ORDER BY {order} LIMIT ? OFFSET ?",
        args + order_args + [limit, offset]).fetchall()
    favs = fav_set()
    pairs = store.mirror_pairs()
    return {"total": total, "items": [row_to_item(r, favs, pairs) for r in rows]}


@app.get("/api/item/{fn:path}/cn")
def item_cn(fn: str, cached: int = 0):
    """中文解读：cached=1 只读缓存不生成（卡片进视口自动铺出用）；
    否则首次生成（约几秒），之后走缓存秒回。fn 支持 gitee/ 前缀三段名"""
    r = store.conn.execute("SELECT full_name FROM items WHERE full_name=?",
                           (fn,)).fetchone()
    if not r:
        return JSONResponse({"error": "未收录该项目"}, status_code=404)
    if cached:
        row = store.conn.execute("SELECT cn_text FROM interpret WHERE full_name=?",
                                 (fn,)).fetchone()
        return {"full_name": fn, "cn": row["cn_text"] if row else None}
    return {"full_name": fn, "cn": _gen_cn(fn)}


@app.get("/api/item/{fn:path}")
def item(fn: str):
    r = store.conn.execute("SELECT * FROM items WHERE full_name=?", (fn,)).fetchone()
    if not r:
        return JSONResponse({"error": "未收录该项目"}, status_code=404)
    return row_to_item(r, fav_set(), store.mirror_pairs())


class FavIn(BaseModel):
    full_name: str
    on: bool


@app.post("/api/fav")
def fav(body: FavIn):
    if body.on:
        store.conn.execute("INSERT OR IGNORE INTO favs VALUES (?,?)",
                           (body.full_name, now_str()))
    else:
        store.conn.execute("DELETE FROM favs WHERE full_name=?", (body.full_name,))
    store.conn.commit()
    store.bump_prefs(body.full_name, 1 if body.on else -1)  # 记/消偏好，hot 排序越逛越懂你
    return {"ok": True, "fav": body.on}


@app.post("/api/gh_star")
def gh_star(body: FavIn):
    """收藏（star）到用户自己的 GitHub 账号：需要 config.json 配 github_token"""
    if body.full_name.count("/") != 1:
        return JSONResponse({"error": "Gitee 项目请直接到 Gitee 页面收藏"}, status_code=400)
    if not cfg.get("github_token"):
        return JSONResponse(
            {"error": "还没配 GitHub 令牌：在 config.json 的 github_token 填入你的 GitHub 个人令牌（勾 public_repo），重启后可用"},
            status_code=400)
    import requests as rq
    r = rq.request("PUT" if body.on else "DELETE",
                   f"https://api.github.com/user/starred/{body.full_name}",
                   headers={**UA, "Authorization": f"Bearer {cfg['github_token']}"},
                   timeout=20)
    if r.status_code == 204:
        store.bump_prefs(body.full_name, 2 if body.on else -2)  # 星标比收藏信号更强
        return {"ok": True, "star": body.on}
    return JSONResponse({"error": f"GitHub 返回 {r.status_code}，令牌可能失效"}, status_code=502)


@app.get("/api/meta")
def meta():
    last = store.conn.execute("SELECT MAX(fetched_at) t FROM items").fetchone()["t"]
    return {"total": store.count(), "favs": len(fav_set()), "last_fetch": last,
            "gh_mirror": MIRROR, "gh_proxy": PROXY}


_refresh = {"running": False, "last": "", "last_new": 0}


def _do_refresh():
    from run_fetch import run_pipeline
    try:
        _refresh["last_new"] = run_pipeline(cfg, store)
        _refresh["last"] = now_str()
    finally:
        _refresh["running"] = False


@app.post("/api/refresh")
def refresh():
    if _refresh["running"]:
        return {"ok": False, "msg": "正在抓取中"}
    _refresh["running"] = True
    threading.Thread(target=_do_refresh, daemon=True).start()
    return {"ok": True}


@app.get("/api/refresh/status")
def refresh_status():
    return dict(_refresh)


_mine = {"running": False, "last_new": 0, "last": ""}


def _do_mine():
    from fetch.miner import mine
    try:
        _mine["last_new"] = mine(cfg, store)
        _mine["last"] = now_str()
        store.refresh_mirrors()  # 新货入库后顺带归并双源镜像
    finally:
        _mine["running"] = False


@app.post("/api/mine")
def mine_start():
    """无限下拉的货源：用户刷到底时自动深挖一层新货"""
    if _mine["running"]:
        return {"ok": False, "msg": "正在深挖中"}
    _mine["running"] = True
    threading.Thread(target=_do_mine, daemon=True).start()
    return {"ok": True}


@app.get("/api/mine/status")
def mine_status():
    return dict(_mine)


_cn_locks = {}
_cn_mu = threading.Lock()


def _gen_cn(fn):
    """解读生成去重：前台浏览与后台慢译共用一把锁，同项目只译一次"""
    from fetch.interpret import interpret
    with _cn_mu:
        lk = _cn_locks.setdefault(fn, threading.Lock())
    with lk:
        return interpret(cfg, store, fn)


def _auto_cn_worker():
    """后台缓慢翻译：热度优先逐个预译，约 65s 一个；
    翻译配额耗尽（生成失败不缓存）自动歇 30 分钟再试"""
    import time
    while True:
        row = store.conn.execute(
            "SELECT full_name FROM items WHERE full_name NOT IN (SELECT full_name FROM interpret)"
            " ORDER BY today_stars DESC, stars DESC LIMIT 1").fetchone()
        if not row:
            time.sleep(600)  # 全部译完，歇着等新货
            continue
        _gen_cn(row["full_name"])
        done = store.conn.execute("SELECT 1 FROM interpret WHERE full_name=?",
                                  (row["full_name"],)).fetchone()
        time.sleep(65 if done else 1800)


threading.Thread(target=_auto_cn_worker, daemon=True).start()


def _backup_worker():
    """SQLite 每日自动备份 → data/backup/，保留最近 7 份（每小时检查一次）"""
    import time
    bdir = os.path.join(cfg["data_dir"], "backup")
    os.makedirs(bdir, exist_ok=True)
    while True:
        try:
            dst = os.path.join(bdir, f"aiguang-{now_str()[:10]}.db")
            if not os.path.exists(dst):
                store.backup(dst)
                olds = sorted(f for f in os.listdir(bdir) if f.startswith("aiguang-"))
                for f in olds[:-7]:
                    os.remove(os.path.join(bdir, f))
        except Exception:
            pass
        time.sleep(3600)


threading.Thread(target=_backup_worker, daemon=True).start()

if store.count() == 0:  # 空库（全新部署/新挂卷）：自动灌一次货，页面不至于空着
    threading.Thread(target=_do_refresh, daemon=True).start()

app.mount("/", StaticFiles(directory=os.path.join(ROOT, "web"), html=True), name="web")

if __name__ == "__main__":
    import uvicorn
    # 云平台通常用 PORT 环境变量指定监听端口，优先取它
    port = int(os.environ.get("PORT") or cfg.get("port", 8321))
    uvicorn.run(app, host=cfg.get("host", "0.0.0.0"), port=port)
