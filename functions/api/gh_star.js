// star 到用户自己的 GitHub 账号（POST /api/gh_star）
// 需要在 Cloudflare Pages 项目里配环境变量（加密）：
//   GH_TOKEN  带 public_repo 权限的 GitHub 个人令牌
const UA = { 'User-Agent': 'aiguang-git/0.1', 'Accept': 'application/vnd.github+json' };
const json = (o, s = 200) => new Response(JSON.stringify(o), {
  status: s, headers: { 'Content-Type': 'application/json' },
});

export async function onRequestPost({ request, env }) {
  let body;
  try {
    body = await request.json();
  } catch (e) {
    return json({ error: '请求格式错误' }, 400);
  }
  const fn = String(body.full_name || '');
  if (fn.split('/').length !== 2) {
    return json({ error: 'Gitee 项目请直接到 Gitee 页面收藏' }, 400);
  }
  if (!env.GH_TOKEN) {
    return json({ error: '未配置 GitHub 令牌：请在 Cloudflare Pages 环境变量里添加 GH_TOKEN（勾 public_repo）' }, 400);
  }

  const r = await fetch('https://api.github.com/user/starred/' + fn, {
    method: body.on ? 'PUT' : 'DELETE',
    headers: { ...UA, 'Authorization': 'Bearer ' + env.GH_TOKEN },
  });
  if (r.status === 204) return json({ ok: true, star: !!body.on });
  return json({ error: 'GitHub 返回 ' + r.status + '，令牌可能失效或缺 public_repo 权限' }, 502);
}
