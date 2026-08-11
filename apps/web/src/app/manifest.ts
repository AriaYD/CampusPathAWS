import type { MetadataRoute } from "next";

/**
 * Web App Manifest（P6-D）。
 *
 * 走 Next 的 `app/manifest.ts` 约定而不是手写 `public/manifest.webmanifest`：
 * 产物路径与 `<link rel="manifest">` 由框架保证一致，少一处能漂移的地方
 * （`node_modules/next/dist/docs/…/01-metadata/manifest.md`）。
 *
 * `start_url: "/"` 会落到门户守卫上：未登录 → 登录页，已登录 → 各自的主页。
 * **不写成 `/profile`**——校方身份从主屏进来会撞上学生页的守卫。
 *
 * `theme_color` 与 `layout.tsx` 的 `viewport.themeColor` 必须同一个值：
 * 一个管 standalone 的系统色，一个管浏览器状态栏，不一致时从主屏启动
 * 会看到状态栏先奶油后陶土地闪一下。
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "CampusPath — 有据可查的成长路径",
    short_name: "CampusPath",
    description:
      "把校园里散落的机会、你的目标与你的时间连成一条能落地的成长路径。合成 / 演示数据。",
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#faf9f5",
    theme_color: "#faf9f5",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      // maskable 单列一档：Android 会把 any 档直接圆形裁切，字标边缘会被切掉
      { src: "/icon-512-maskable.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
