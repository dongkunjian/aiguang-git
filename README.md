# 爱逛GIT

每天自动聚合 GitHub 热榜 / 主题新货 / star 相似推荐 / 大佬动态 / Gitee 国产名品，
单页应用逛街式浏览，自动中文解读，支持收藏、搜索、个性化热榜。

FastAPI + SQLite + 无框架单页前端，零构建、零依赖前端。

## 功能速览

- 五路货源：Trending 热榜、主题订阅、star 相似推荐、大佬动态、Gitee 好物（54 种子 + 32 名组织扩展）
- GitHub / Gitee 镜像自动归并：同名同语言同描述的项目合并为双源卡，卡片直达 Gitee 镜像
- 中文解读：进视口自动铺出，后台慢速预译（MyMemory 免费额度），缓存秒回
- 个性化热榜：收藏 ♥ / GitHub 星标 ★ 自动记录语言与 topics 偏好，hot 排序越逛越懂你
- 头像服务端缓存代理：国内不再裂图，拉不到自动首字母彩色 SVG 兜底
- 新货红点：有新项目入库时 Logo 旁出红点，点 Logo / 抓货完成清零
- SQLite 每日自动备份 → `data/backup/`，保留最近 7 份
- config.json 热加载：改令牌 / 镜像 / 口令 / 翻译邮箱免重启（`POST /api/reload`）
- 访问口令门禁：外网暴露时全站校验，口令正确一次种 cookie 一年有效

## 部署

```powershell
# 1. 装依赖（Python 3.11+）
pip install fastapi uvicorn requests

# 2. 配置（复制下方模板按需修改）
notepad config.json

# 3. 首次抓货入库
python run_fetch.py

# 4. 起服务（默认 0.0.0.0:8321）
python server.py

# 5. 浏览器打开 http://127.0.0.1:8321
```

## config.json 字段说明

| 字段 | 说明 |
|---|---|
| `github_token` | GitHub 个人令牌（勾 `public_repo`），用于星标 API 和提高限额 |
| `github_username` | 你的 GitHub 用户名（star 相似推荐用） |
| `topics` | 主题订阅关键词列表 |
| `bosses` | 关注的大佬 GitHub 账号列表 |
| `languages` | 关注语言，热榜过滤用 |
| `trending_since` | 热榜周期：`daily` / `weekly` / `monthly` |
| `min_stars` | 入库最低星数门槛 |
| `db_path` | SQLite 库文件路径 |
| `host` / `port` | 服务监听地址与端口（改这两项需重启） |
| `access_code` | 访问口令；非空时全站校验（外网暴露必配），空则免密 |
| `mymemory_email` | MyMemory 翻译注册邮箱；填入后日翻译额度 ×10，改完 `POST /api/reload` 即生效 |
| `gh_mirror` | GitHub 镜像站（卡片「镜像↗」链接用），如 `https://bgithub.xyz` |
| `gh_proxy` | GitHub 加速代理前缀，如 `https://ghfast.top` |
| `gitee_token` | Gitee 私人令牌；解除匿名限流（403），Gitee 货源稳定抓取必备 |

除 `host` / `port` 外，改完任意字段调用 `POST /api/reload` 即生效，免重启。

## 公网暴露（Cloudflare 命名隧道）

```powershell
# 隧道配置在 .cloudflared/config.yml（已 gitignore，含隧道凭据）
# 前台调试：
cloudflared tunnel --config .cloudflared/config.yml run

# 生产守护（推荐）：看门狗循环，服务停拉服务、隧道断拉隧道，60s 巡检
powershell -WindowStyle Hidden -File .cloudflared/start.ps1
```

## 常用 API

| 接口 | 说明 |
|---|---|
| `GET /api/feed?sort=hot&q=&src=&fav=` | 信息流（hot/rising/new/stars/rand） |
| `GET /api/item/{full_name}` | 项目详情 |
| `GET /api/item/{full_name}/cn?cached=1` | 中文解读（cached=1 只读缓存） |
| `POST /api/fav` | 收藏 / 取消收藏 |
| `POST /api/gh_star` | star 到自己 GitHub 账号 |
| `POST /api/refresh` | 异步全量抓货 |
| `POST /api/mine` | 刷到底自动深挖新货 |
| `POST /api/reload` | config.json 热加载 |
| `GET /api/avatar/{full_name}` | 头像缓存代理 |
| `GET /api/meta` | 库内统计 |

`/api/` 接口在开启口令时需带 `?code=` 或请求头 `X-Code`。

## 目录结构

```
├── server.py        # FastAPI 服务（feed/详情/收藏/刷新/头像代理/备份/热加载）
├── run_fetch.py     # 一键五路抓取入库（可独立跑，也可由 /api/refresh 调用）
├── store.py         # SQLite 存储层（去重合并/偏好/镜像归并/备份）
├── fetch/           # 五路货源 + 中文解读 + 深挖矿工
├── web/index.html   # 无框架单页前端
├── data/            # 库文件 / 头像缓存 / 每日备份（gitignore）
└── .cloudflared/    # 隧道配置 + 看门狗脚本（gitignore）
```
