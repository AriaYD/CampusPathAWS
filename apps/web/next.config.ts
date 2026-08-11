import type { NextConfig } from "next";

/**
 * 前端与 API 同源：`/api/v1/*` 反向代理到 FastAPI。
 *
 * 这样浏览器不需要 CORS，API 也不必为了一个演示前端放开跨域——
 * 少一处需要有人记得收回去的放宽。
 */
const API_ORIGIN = process.env.CAMPUSPATH_API_ORIGIN ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  /**
   * 浏览器实测走 `127.0.0.1`，而 dev server 默认只认 `localhost`——
   * 于是 `/_next/*` 被当成跨源请求拦掉，结果是**整页静默不 hydrate**：
   * SSR 的 HTML 照常显示，看着完全正常，但 effect 不跑、onClick 无效，
   * 浏览器控制台里只有一条 websocket 失败，没有任何红字。
   * 只在 dev 生效，不影响生产构建。
   */
  allowedDevOrigins: ["127.0.0.1", "localhost"],

  /**
   * dev 指示器在手机宽度下**四个角都会压到东西**，实测挑代价最小的一个：
   * bottom-left 压底部标签栏第一格（档案）、bottom-right 压「更多」格、
   * top-right 压顶栏的「⋯」菜单——这三个都是**唯一入口**，被盖住就点不到。
   * top-left 只压到 Logo 的左边缘，而 Logo 是回首页的**冗余**入口
   * （标签栏本就有档案页），代价最小。
   * 不设 `false`——它还负责显示编译/运行时错误，关掉等于把报错一起关了。
   * 仅影响 dev；线上是生产构建，本就没有这颗指示器。
   */
  devIndicators: { position: "top-left" },

  /**
   * `sw.js` 与 manifest 一律 `no-store`（P6-D）。
   *
   * 它们是 `public/` 下的静态文件，默认会拿到长缓存——而 Service Worker
   * 恰恰是**唯一能把用户永久锁在旧版本上**的东西：新版 sw.js 推不下去，
   * 就再也没有机会修好。这与 §10.2 那条「HTML 被缓存导致白屏」是同族问题，
   * 只是后果更长久。（注册时的 `updateViaCache: "none"` 是同一件事的另一半。）
   */
  async headers() {
    return [
      {
        source: "/:file(sw.js|manifest.webmanifest)",
        headers: [{ key: "Cache-Control", value: "no-store, must-revalidate" }],
      },
    ];
  },

  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API_ORIGIN}/:path*` },
      // 宣传页随站点部署：`/landing` 是对外给人看的地址，
      // 实体是 public/landing.html（生成物，`bun run landing` 产出）
      { source: "/landing", destination: "/landing.html" },
    ];
  },
};

export default nextConfig;
