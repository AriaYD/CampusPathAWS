/* eslint-disable no-restricted-globals */
/**
 * CampusPath 最小 Service Worker（P6-D）。
 *
 * 存在的理由只有两条：① Chrome 要有 SW 才给「安装到主屏」的提示；
 * ② 断网时给一页说人话的离线提示，而不是浏览器的恐龙。
 *
 * **三条硬规矩，每一条都是踩过的坑换来的：**
 *
 * 1. **HTML 永不进缓存**。Plan §10.2 记着 2026-08-02 的白屏事故：缓存节点
 *    把上一次部署的 HTML 发给用户，它引用的 chunk 已经不存在 → 整页白。
 *    SW 缓存 HTML 会把同一个事故变成**永久**版本——用户清不掉。
 *    所以导航请求一律 network-only，失败才给内联的离线页。
 * 2. **只缓存内容哈希过的静态资源**（`/_next/static/…`）。文件名里带哈希，
 *    内容变了名字就变，缓存永远不会变陈。
 * 3. **留卸载后门**。SW 是唯一能把用户**永久**锁在旧版本上的东西。
 *    `/sw-unregister` 页面与下面的 `SW_OFF` 消息都能把它连缓存一起铲干净。
 *
 * 不做 API 离线缓存（用户 2026-08-10 裁定）：后端是内存态 + 演示时钟，
 * 缓存下来的数据很快就是错的，而"看起来有数据但其实是旧的"比没数据更糟。
 */

const VERSION = "v1";
const STATIC_CACHE = `campuspath-static-${VERSION}`;

self.addEventListener("install", (event) => {
  // 预缓存清单为空是**故意的**：要预缓存的东西（chunk）文件名由构建期哈希
  // 决定，写死在这里只会过期。第一次访问时按需缓存即可。
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(
      names.filter((n) => n.startsWith("campuspath-") && n !== STATIC_CACHE)
        .map((n) => caches.delete(n)),
    );
    await self.clients.claim();
  })());
});

/** 卸载后门：页面发来 SW_OFF 就自尽，并把缓存全部删掉。 */
self.addEventListener("message", (event) => {
  if (event.data !== "SW_OFF") return;
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names.map((n) => caches.delete(n)));
    await self.registration.unregister();
    const clients = await self.clients.matchAll({ type: "window" });
    for (const client of clients) client.navigate(client.url);
  })());
});

const OFFLINE_HTML = `<!doctype html><html lang="zh-Hans"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CampusPath — 离线</title>
<style>
 html,body{margin:0;height:100%}
 body{background:#faf9f5;color:#29261b;display:flex;align-items:center;
      justify-content:center;padding:24px;
      font-family:system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
 main{max-width:30ch;text-align:center}
 h1{font-size:1.125rem;margin:0 0 .5rem}
 p{font-size:.875rem;line-height:1.6;color:#6b6353;margin:0 0 1.25rem}
 button{font:inherit;font-size:.875rem;padding:.7rem 1.2rem;border-radius:10px;
        border:0;background:#a04a2a;color:#fff;min-height:44px}
</style></head><body><main>
<h1>暂时连不上 · You're offline</h1>
<p>CampusPath 的内容需要联网获取——它不缓存你的档案与日程，所以断网时不会拿旧数据充数。<br>
Content needs a connection. We don't cache your profile or schedule, so nothing stale is shown.</p>
<button onclick="location.reload()">重试 · Retry</button>
</main></body></html>`;

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // ① 导航（HTML）：只走网络。断网才给离线页，**永不落盘**。
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() =>
        new Response(OFFLINE_HTML, {
          headers: { "Content-Type": "text/html; charset=utf-8" },
        })),
    );
    return;
  }

  // ② 内容哈希过的静态资源：cache-first，命中就不走网络。
  if (url.pathname.startsWith("/_next/static/")) {
    event.respondWith((async () => {
      const hit = await caches.match(request);
      if (hit) return hit;
      const res = await fetch(request);
      if (res.ok) {
        const cache = await caches.open(STATIC_CACHE);
        cache.put(request, res.clone());
      }
      return res;
    })());
    return;
  }

  // ③ 其余（含 /api 反代）：不插手。数据必须是新鲜的。
});
