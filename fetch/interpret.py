"""中文解读：抓 README 要点 → MyMemory 免费翻译 → SQLite 缓存（按需生成，成功才缓存）"""
import re

import requests

from .common import UA
from store import now_str

CJK = re.compile("[一-鿿]")
MM_API = "https://api.mymemory.translated.net/get"


def _is_cn(text):
    """中文占比超 15% 视为中文内容，无需翻译"""
    return bool(text) and len(CJK.findall(text)) / max(len(text), 1) > 0.15


def _chunks(text, size=450):
    """MyMemory 单次 q 限长，按段打包切块"""
    buf = ""
    for para in text.split("\n"):
        para = para.strip()
        if not para:
            continue
        while len(para) > size:
            if buf:
                yield buf
                buf = ""
            yield para[:size]
            para = para[size:]
        if len(buf) + len(para) + 1 > size:
            yield buf
            buf = para
        else:
            buf = f"{buf}\n{para}" if buf else para
    if buf:
        yield buf


def _clean_md(md, limit=900):
    """README → 纯文字要点：去图片/徽章/HTML/链接语法"""
    lines = []
    for ln in md.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("![") or "shields.io" in ln or ln.startswith("<"):
            continue
        if "](#" in ln:  # 目录锚点链接行，纯噪声
            continue
        ln = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", ln)
        ln = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", ln)  # 允许空文本，连吃徽章残留的 []()
        ln = re.sub(r"<[^>]+>", "", ln)
        ln = ln.lstrip("#>*-` ").strip()
        if ln:
            lines.append(ln)
        if sum(len(x) for x in lines) > limit:
            break
    return "\n".join(lines)[:limit]


def _fetch_readme(full_name, cfg):
    if full_name.startswith("gitee/"):
        path = full_name[len("gitee/"):]
        for br in ("master", "main"):
            try:
                r = requests.get(f"https://gitee.com/{path}/raw/{br}/README.md",
                                 headers=dict(UA), timeout=20)
                if r.status_code == 200 and r.text.strip():
                    return r.text
            except Exception:
                pass
        return ""
    headers = dict(UA)
    headers["Accept"] = "application/vnd.github.raw"
    if cfg.get("github_token"):
        headers["Authorization"] = f"Bearer {cfg['github_token']}"
    try:
        r = requests.get(f"https://api.github.com/repos/{full_name}/readme",
                         headers=headers, timeout=20)
        return r.text if r.status_code == 200 else ""
    except Exception:
        return ""


def _mm(text, cfg):
    """主通道 MyMemory：匿名 5000 字/天，config 填 mymemory_email 提到 50000"""
    email = (cfg.get("mymemory_email") or "").strip()
    out = []
    for chunk in _chunks(text):
        params = {"q": chunk, "langpair": "en|zh-CN"}
        if email:
            params["de"] = email
        r = requests.get(MM_API, params=params, timeout=25)
        d = r.json()
        t = ((d.get("responseData") or {}).get("translatedText") or "").strip()
        up = t.upper()
        if r.status_code != 200 or not t or "MYMEMORY WARNING" in up or "QUERY LENGTH LIMIT" in up:
            return None
        out.append(t)
    return "\n".join(out)


def _google(text):
    """备胎② Google 公开端点 gtx：translate.googleapis.com，无需密钥"""
    out = []
    for chunk in _chunks(text):
        r = requests.get("https://translate.googleapis.com/translate_a/single",
                         params={"client": "gtx", "sl": "auto", "tl": "zh-CN",
                                 "dt": "t", "q": chunk},
                         headers=dict(UA), timeout=25)
        if r.status_code != 200:
            return None
        arr = r.json()
        t = "".join(seg[0] for seg in (arr[0] or []) if seg and seg[0]).strip()
        if not t:
            return None
        out.append(t)
    return "\n".join(out)


def _bing(text):
    """备用通道 Bing：从 translator 页刮临时令牌，无需密钥，国内可达"""
    r = requests.get("https://www.bing.com/translator", headers=UA, timeout=20)
    m = re.search(r'params_AbusePreventionHelper\s*=\s*\[(\d+),"([^"]+)"', r.text)
    ig = re.search(r'IG:"([^"]+)"', r.text)
    if not m:
        return None
    key, token = m.group(1), m.group(2)
    out = []
    for chunk in _chunks(text):
        rr = requests.post("https://www.bing.com/ttranslatev3",
                           params={"isVertical": "1", "IG": ig.group(1) if ig else ""},
                           data={"fromLang": "en", "to": "zh-Hans", "text": chunk,
                                 "token": token, "key": key},
                           headers=UA, timeout=25)
        arr = rr.json()
        t = arr[0]["translations"][0]["text"].strip() if isinstance(arr, list) and arr else ""
        if not t:
            return None
        out.append(t)
    return "\n".join(out)


def _translate(text, cfg):
    """成功返回译文；源文已是中文原样返回；全部通道失败返回 None。
    备胎链自动切换：MyMemory → Google gtx → Bing，任一可用即用"""
    if not text.strip():
        return ""
    if _is_cn(text):
        return text
    for ch in (lambda: _mm(text, cfg), lambda: _google(text), lambda: _bing(text)):
        try:
            t = ch()
            if t is not None:
                return t
        except Exception:
            continue
    return None


def interpret(cfg, store, full_name):
    """生成/读取中文解读。翻译全失败时不缓存，下次重试。"""
    row = store.conn.execute(
        "SELECT cn_text FROM interpret WHERE full_name=?", (full_name,)).fetchone()
    if row:
        return row["cn_text"]

    item = store.conn.execute(
        "SELECT description FROM items WHERE full_name=?", (full_name,)).fetchone()
    desc = ((item["description"] if item else "") or "").strip()
    head = _clean_md(_fetch_readme(full_name, cfg))

    parts, cacheable = [], True
    if desc:
        t = _translate(desc, cfg)
        if t is None:
            cacheable = False
            parts.append("【一句话】（翻译接口暂时不可用，先看原文）\n" + desc)
        else:
            parts.append("【一句话】\n" + t)
    if head:
        t = _translate(head, cfg)
        if t is None:
            cacheable = False
            parts.append("【README 速览】（翻译接口暂时不可用，先看原文节选）\n" + head[:600])
        else:
            parts.append("【README 速览】\n" + t)
    text = "\n\n".join(parts).strip() or "这个项目没有简介和 README，暂无解读内容。"
    if cacheable:
        store.cache_interpret(full_name, text)
    return text
