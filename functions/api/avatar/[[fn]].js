// 头像边缘代理：前端带 ?u=<原始头像地址>，这里在 Cloudflare 边缘取回并缓存，
// 客户端只需访问本站域名，国内不再裂图。拉不到时前端自动退回首字母彩色块。
const ALLOW_HOSTS = new Set([
  'avatars.githubusercontent.com',
  'github.com',
  'portrait.gitee.com',
  'gitee.com',
  'www.gitee.com',
]);

export async function onRequestGet(context) {
  const { request } = context;
  const u = new URL(request.url).searchParams.get('u');
  if (!u) return new Response('', { status: 400 });

  let target;
  try {
    target = new URL(u);
  } catch (e) {
    return new Response('', { status: 400 });
  }
  // 白名单域名，避免被当成开放代理滥用
  if (!ALLOW_HOSTS.has(target.host)) return new Response('', { status: 403 });

  const cache = caches.default;
  const hit = await cache.match(request);
  if (hit) return hit;

  let upstream;
  try {
    upstream = await fetch(target.toString(), {
      headers: { 'User-Agent': 'aiguang-git/0.1' },
    });
  } catch (e) {
    return new Response('', { status: 502 });
  }
  if (!upstream.ok) return new Response('', { status: upstream.status });

  const body = await upstream.arrayBuffer();
  const res = new Response(body, {
    headers: {
      'Content-Type': upstream.headers.get('Content-Type') || 'image/png',
      'Cache-Control': 'public, max-age=604800',
      'Access-Control-Allow-Origin': '*',
    },
  });
  context.waitUntil(cache.put(request, res.clone()));
  return res;
}
