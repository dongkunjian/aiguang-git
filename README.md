# 爱逛GIT

每天自动聚合 GitHub 热榜 / 主题新货 / star 相似推荐 / 大佬动态 / Gitee 国产名品，
单页应用逛街式浏览，自动中文解读，支持收藏、搜索、个性化热榜。

**线上形态：Cloudflare Pages 静态托管 + GitHub Actions 定时抓取。全免费、不依赖任何常驻服务器，也不依赖你本地电脑（关机照常运行）。**

## 架构（全 Cloudflare + GitHub，¥0/月）

```
GitHub Actions（每日定时）
   └─ 跑 Python 抓五路货源 → 写入 SQLite → 导出 web/data/feed.json
   └─ 把导出的数据提交回仓库
        └─ Cloudflare Pages（Git 集成，输出目录 web）
              └─ 提交即自动重建 → 免费 *.pages.dev 域名
```

- **抓取**（I/O + 解析重活）跑在 GitHub Actions，免费、可 cron 定时
- **页面**是纯静态 `web/`，托管在 Cloudflare Pages，手机/iPad/桌面自适应
- **薄动态层**用 Pages Functions（`functions/`）：头像边缘代理、星到 GitHub、手动触发抓取
- 收藏存浏览器 localStorage，中文解读打包进 `web/data/cn.json`，全站无后端进程

## 功能速览

- 五路货源：Trending 热榜、主题订阅、star 相似推荐、大佬动态、Gitee 好物（54 种子 + 32 名组织扩展）
- GitHub / Gitee 镜像自动归并：同名同语言同描述的项目合并为双源卡，卡片直达 Gitee 镜像
- 中文解读：`cn.json` 进视口懒加载铺出，云端慢速预译、缓存秒回
- 个性化热榜：收藏 ♥ / GitHub 星标 ★ 记录语言与 topics 偏好，hot 排序越逛越懂你（本地记忆）
- 头像边缘代理：经 Pages Function 取回并缓存，国内不再裂图；拉不到自动首字母彩色块
- 新货红点：库内总数比上次浏览多时，抓新货按钮右上角亮 +N
- 静态数据：前端一次性拉全量，客户端搜索/排序/分页，无需后端接口

## 线上部署（Cloudflare Pages）

1. 代码已在 GitHub 仓库 `dongkunjian/aiguang-git`。
2. 仓库 **Settings → Secrets and variables → Actions** 添加 3 个 Secret：
   `AIGUANG_GITHUB_TOKEN`、`AIGUANG_GITEE_TOKEN`、`AIGUANG_MYMEMORY_EMAIL`。
3. 在仓库网页端新建 `.github/workflows/fetch.yml`（命令行推送受 GitHub 权限限制，需在网页里 Add file → Create new file，路径填 `.github/workflows/fetch.yml`），内容见下方「定时抓取工作流」。
4. Cloudflare 控制台 → **Workers & Pages → 创建 → Pages → 连接到 Git** → 选该仓库 →
   构建配置：框架预设 `None`、构建命令**留空**、构建输出目录 `web` → 保存并部署。
5. 得到 `aiguang-git.pages.dev`，国内可直连。想用自有域名：Pages 项目 → **自定义域** 绑定。

可选增强：

- Pages 项目 → **Settings → 环境变量（加密）** 加 `GH_TOKEN`、`GH_REPO`（值 `dongkunjian/aiguang-git`），启用「星到 GitHub」与「↻ 抓新货」。
- Pages 项目 → **Cloudflare Access** 开启邮箱验证（免费 50 用户），替代旧口令门禁。

## 定时抓取工作流

`.github/workflows/fetch.yml`（在 GitHub 网页端新建并粘贴）：

```yaml
name: 抓取并部署
on:
  schedule:
    - cron: '0 22 * * *'
  workflow_dispatch: {}
permissions:
  contents: write
jobs:
  fetch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: 恢复数据库缓存
        uses: actions/cache@v4
        with:
          path: data/aiguang.db
          key: aiguang-db-${{ github.run_id }}
          restore-keys: |
            aiguang-db-
      - name: 安装依赖
        run: pip install requests beautifulsoup4
      - name: 抓取入库
        env:
          AIGUANG_GITHUB_TOKEN: ${{ secrets.AIGUANG_GITHUB_TOKEN }}
          AIGUANG_GITEE_TOKEN: ${{ secrets.AIGUANG_GITEE_TOKEN }}
          AIGUANG_MYMEMORY_EMAIL: ${{ secrets.AIGUANG_MYMEMORY_EMAIL }}
        run: python run_fetch.py
      - name: 导出静态数据
        run: python export_static.py
      - name: 提交数据（触发 Pages 重建）
        run: |
          git config user.name "aiguang-git-bot"
          git config user.email "actions@users.noreply.github.com"
          git add web/data
          if git diff --cached --quiet; then
            echo "数据无变化，跳过提交"
          else
            git commit -m "自动抓取：更新好物数据 $(date -u +%Y-%m-%d)"
            git push
          fi
```

## 本地开发 / 预览

```powershell
# 1. 装依赖（Python 3.11+）
pip install requests beautifulsoup4

# 2. 抓货入库 + 导出静态数据
python run_fetch.py
python export_static.py

# 3. 纯静态预览（最贴近线上形态；头像代理/星标等 Functions 接口在本地不可用）
python -m http.server 8090 --directory web
#    浏览器打开 http://127.0.0.1:8090

# 或者跑本地 FastAPI（含 /api/avatar 等接口，需 config.json 的 access_code）
python server.py
```

## config.json 字段说明

线上跑 `run_fetch.py` 时，密钥一律走环境变量（`AIGUANG_GITHUB_TOKEN` 等），仓库里只放不含密钥的 `config.example.json`。

| 字段 | 说明 |
|---|---|
| `github_token` | GitHub 个人令牌（勾 `public_repo`），用于星标 API 和提高限额 |
| `github_username` | 你的 GitHub 用户名（star 相似推荐用） |
| `topics` | 主题订阅关键词列表 |
| `bosses` | 关注的大佬 GitHub 账号列表 |
| `languages` | 关注语言，热榜过滤用 |
| `trending_since` | 热榜周期：`daily` / `weekly` / `monthly` |
| `min_stars` | 入库最低星数门槛 |
| `db_path` | SQLite 库文件路径（仅本地/CI 用） |
| `gh_mirror` | GitHub 镜像站（卡片「镜像↗」链接用） |
| `gh_proxy` | GitHub 加速代理前缀 |
| `gitee_token` | Gitee 私人令牌；解除匿名限流，Gitee 货源稳定抓取必备 |

## 常用 API（Cloudflare Pages Functions）

| 接口 | 说明 |
|---|---|
| `GET /api/avatar/{full_name}?u=` | 头像边缘代理缓存（`u` 为原始头像地址） |
| `POST /api/gh_star` | 星到自己的 GitHub 账号（需 Pages 环境变量 `GH_TOKEN`） |
| `POST /api/refresh` | 触发云端 Actions 抓取（需 `GH_TOKEN` + `GH_REPO`） |
| `GET /api/refresh/status` | 抓取是否仍在进行 |

前端数据是静态文件：`GET /data/feed.json`（项目卡片）、`GET /data/cn.json`（中文解读）。

## 目录结构

```
├── web/                 # Pages 部署目录（站点本体）
│   ├── index.html       # 纯静态单页前端
│   ├── data/            # 导出数据 feed.json / cn.json（Actions 定时提交）
│   └── _routes.json     # 限定 Functions 只处理 /api/*
├── functions/api/       # Pages Functions：avatar / gh_star / refresh
├── export_static.py     # SQLite → web/data 静态导出
├── run_fetch.py         # 五路抓取入库（CI / 本地）
├── store.py             # SQLite 存储层（去重合并 / 偏好 / 镜像归并）
├── fetch/               # 货源模块 + 中文解读 + 深挖矿工
├── server.py            # 本地开发用 FastAPI（线上不再使用）
├── .github/workflows/   # Actions 定时抓取并提交数据
└── data/                # 本地库 / 头像 / 备份（gitignore）
```
