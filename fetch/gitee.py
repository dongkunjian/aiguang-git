"""Gitee 好物：匿名仓库 API 拉国内名品（种子名单 + 名组织扩展）；
config 配 gitee_token 后追加搜索通道（Gitee 搜索 API 匿名返回空，必须令牌）"""
import requests

UA = {"User-Agent": "aiguang-git/0.1"}
API = "https://gitee.com/api/v5"

SEEDS = [  # Gitee 上久经验证的国产名品（逐个经 API 确认存在）
    # 若依系
    "y_project/RuoYi", "y_project/RuoYi-Vue", "y_project/RuoYi-Cloud",
    # dromara 系
    "dromara/sa-token", "dromara/MaxKey", "dromara/Jpom", "dromara/liteflow",
    "dromara/forest", "dromara/hertzbeat", "dromara/mica-mqtt",
    # 脚手架 / 后台管理
    "baomidou/mybatis-plus", "macrozheng/mall", "macrozheng/mall-swarm",
    "elunez/eladmin", "stylefeng/guns", "smallc/SpringBlade", "jeecg/jeecg-boot",
    "jeecg/JimuReport", "lenve/vhr",
    # 工具 / 其他
    "dromara/hutool", "linlinjava/litemall", "Talelin/lin-cms-vue",
    "zlt2000/microservices-platform", "halo-dev/halo",
    # 大厂 / 开源组织
    "mindspore/mindspore", "openharmony/arkui_ace_engine",
    # 第二批扩容（2026-10-16 经 API 逐个确认）
    "ssssssss-team/magic-api", "ssssssss-team/spider-flow", "thinkgem/jeesite4",
    "paascloud/paascloud-master", "ZHENFENG13/My-Blog", "anji-plus/report",
    "forezp/SpringCloudLearning", "shuzheng/zheng", "iBase4J/iBase4J",
    "tywo45/t-io", "jfinal/jfinal", "xiaonuobase/snowy", "WeiYe-Jing/datax-web",
    "noear/solon", "mybatis-flex/mybatis-flex", "go-admin-team/go-admin",
    "tiger1103/gfast", "farsunset/cim", "javen205/IJPay", "gz-yami/mall4j",
    "zlgopen/awtk", "jetlinks/jetlinks-community", "pnoker/iot-dc3",
    "iioter/iotgateway", "xia-chu/ZLMediaKit", "xiaoym/knife4j",
    "xuxueli0323/xxl-job", "kekingcn/file-online-preview", "anji-plus/captcha",
    "rtthread/rt-thread",
]
ORGS = ["dromara", "y_project", "baomidou", "macrozheng", "elunez",
        "jeecg", "mindspore", "stylefeng", "linlinjava", "log4j", "chinabugotech",
        # 第二批扩容组织
        "openharmony", "anji-plus", "noear", "mybatis-flex", "go-admin-team",
        "jetlinks", "kekingcn", "ssssssss-team", "thinkgem", "xiaonuobase",
        "gz-yami", "xuxueli0323", "farsunset", "tiger1103", "zlgopen",
        "pnoker", "iioter", "xia-chu", "javen205", "halo-dev", "zlt2000"]
ORG_MIN_STARS = 500  # 组织扩展的高门槛，防灌水


def _norm(it):
    owner = (it.get("namespace") or {}).get("path") or (it.get("owner") or {}).get("login", "")
    url = it.get("html_url") or ""
    if url.endswith(".git"):  # Gitee API 返回的 html_url 带 .git 克隆后缀，等价于网页地址，去掉更干净
        url = url[:-4]
    return {
        "full_name": f"gitee/{owner}/{it.get('path') or it.get('name', '')}",
        "name": it.get("path") or it.get("name", ""),
        "owner": owner,
        "url": url,
        "description": it.get("description") or "",
        "language": it.get("language") or "",
        "stars": it.get("stargazers_count", 0),
        "forks": it.get("forks_count", 0),
        "today_stars": 0,  # 真实增量在 fetch 里按当日快照基线计算
        "topics": [l.get("name") for l in (it.get("project_labels") or []) if l.get("name")],
        "sources": ["Gitee"],
        "avatar": (it.get("owner") or {}).get("avatar_url", ""),
        "pushed_at": it.get("pushed_at") or "",
        "updated_at": it.get("updated_at") or "",
    }


def _get(path, params=None, token=""):
    """Gitee 匿名请求会被限流（403 Rate Limit Exceeded），必须带令牌；
    偶发超时/连接中断重试一次"""
    p = dict(params or {})
    if token:
        p["access_token"] = token
    for _ in range(2):
        try:
            r = requests.get(API + path, params=p, headers=UA, timeout=15)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
    return None


def fetch(cfg, store=None):
    seen, out = set(), []
    tok = (cfg.get("gitee_token") or "").strip()

    def take(it, min_stars=0):
        if not isinstance(it, dict) or it.get("stargazers_count", 0) < min_stars:
            return
        d = _norm(it)
        if d["full_name"] in seen or not d["url"]:
            return
        if store is not None:  # 当日快照基线 → 真实今日增量
            d["today_stars"] = store.gitee_today(d["full_name"], d["stars"])
        seen.add(d["full_name"])
        out.append(d)

    for fn in SEEDS:
        it = _get(f"/repos/{fn}", token=tok)
        if it:
            take(it)
        else:
            print(f"    [Gitee] 种子 {fn} 拉取失败")
    print(f"    [Gitee] 种子: {len(out)} 个")

    n0 = len(out)
    for org in ORGS:
        arr = _get(f"/users/{org}/repos", {"per_page": 100, "sort": "updated"}, token=tok)
        for it in arr or []:
            take(it, ORG_MIN_STARS)
    print(f"    [Gitee] 组织扩展: +{len(out) - n0} 个")

    if store is not None:
        store.conn.commit()  # 落盘当日星快照（明日增量基线）

    # 注：Gitee 官方仓库搜索接口 /search/repositories 实测对任何关键词均返回空数组（带令牌也是），
    # 故不采用；货源 = 精选种子 + 名组织扩展。令牌的核心作用是解除匿名限流（403），保证抓取稳定。
    # topics 取自仓库详情 project_labels；today_stars 用当日快照基线算真实增量。
    return out
