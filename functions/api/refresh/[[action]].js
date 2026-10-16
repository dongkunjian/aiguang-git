// 抓新货 / 查状态（对应 /api/refresh 与 /api/refresh/status）
// 触发 GitHub Actions 里的抓取工作流，抓完由工作流重新导出 feed.json 并推回仓库，
// Pages 随即自动重新部署 —— 抓取全程在云端，无需本地电脑。
// 需要在 Cloudflare Pages 项目里配环境变量：
//   GH_TOKEN    GitHub 令牌（public_repo + workflow 权限）
//   GH_REPO     仓库全名，如 dongkunjian/aiguang-git
//   GH_WORKFLOW 工作流文件名（默认 fetch.yml）
//   GH_REF      触发分支（默认 main）
const UA = { 'User-Agent': 'aiguang-git/0.1', 'Accept': 'application/vnd.github+json' };
const json = (o, s = 200) => new Response(JSON.stringify(o), {
  status: s, headers: { 'Content-Type': 'application/json' },
});

function seg(params) {
  const a = params.action;
  if (!a) return '';
  return Array.isArray(a) ? a.join('/') : a;
}

async function latestRun(env) {
  if (!env.GH_TOKEN || !env.GH_REPO) return null;
  const wf = env.GH_WORKFLOW || 'fetch.yml';
  const r = await fetch(
    `https://api.github.com/repos/${env.GH_REPO}/actions/workflows/${wf}/runs?per_page=1`,
    { headers: { ...UA, 'Authorization': 'Bearer ' + env.GH_TOKEN } });
  if (!r.ok) return null;
  const d = await r.json();
  return (d.workflow_runs || [])[0] || null;
}

export async function onRequest(context) {
  const { request, env, params } = context;
  const action = seg(params);

  // GET /api/refresh/status → 最近一次抓取是否仍在跑
  if (action === 'status') {
    const run = await latestRun(env);
    if (!run) return json({ running: false, unknown: true, last: '' });
    return json({
      running: run.status !== 'completed',
      last: run.updated_at || '',
      conclusion: run.conclusion || '',
    });
  }

  // POST /api/refresh → workflow_dispatch 触发抓取
  if (request.method !== 'POST') return json({ error: 'method not allowed' }, 405);
  if (!env.GH_TOKEN || !env.GH_REPO) {
    return json({ error: '未配置 GH_TOKEN / GH_REPO，无法触发云端抓取' }, 400);
  }
  const wf = env.GH_WORKFLOW || 'fetch.yml';
  const r = await fetch(
    `https://api.github.com/repos/${env.GH_REPO}/actions/workflows/${wf}/dispatches`,
    {
      method: 'POST',
      headers: { ...UA, 'Authorization': 'Bearer ' + env.GH_TOKEN, 'Content-Type': 'application/json' },
      body: JSON.stringify({ ref: env.GH_REF || 'main' }),
    });
  if (r.status === 204) return json({ ok: true });
  const t = await r.text();
  return json({ error: '触发失败：GitHub 返回 ' + r.status + ' ' + t.slice(0, 120) }, 502);
}
