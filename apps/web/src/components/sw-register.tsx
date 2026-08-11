"use client";

import { useEffect } from "react";

/**
 * Service Worker 注册（P6-D）。渲染 null——它只有副作用。
 *
 * **本地开发默认不注册**：改一行代码却看到上一版页面，是最耗时间的一类
 * 假故障。要在本地验证 SW，在控制台执行
 * `localStorage.setItem("campuspath.sw", "on")` 后刷新——这个开关是
 * **给验证留的口子**，不是功能：没有它，「只在生产注册」这条规则本身
 * 就没法被实测，只能靠读代码相信。
 *
 * `updateViaCache: "none"` 是必须的：否则浏览器会按 HTTP 缓存复用
 * 旧的 `sw.js`，新版 SW 推不下去（同族问题见 sw.js 顶部第 3 条）。
 */
export function ServiceWorkerRegistrar() {
  useEffect(() => {
    if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return;
    // `?sw=off` = 紧急卸载后门的快捷方式（另有 /sw-unregister 页面）
    if (new URLSearchParams(window.location.search).get("sw") === "off") {
      navigator.serviceWorker.getRegistrations().then((rs) => {
        for (const r of rs) r.unregister();
      });
      caches?.keys?.().then((ns) => ns.forEach((n) => caches.delete(n)));
      return;
    }
    const enabled = process.env.NODE_ENV === "production"
      || (() => {
        try { return localStorage.getItem("campuspath.sw") === "on"; }
        catch { return false; }
      })();
    if (!enabled) return;
    navigator.serviceWorker
      .register("/sw.js", { scope: "/", updateViaCache: "none" })
      .catch(() => { /* 注册失败不该影响任何功能——PWA 是增益不是前提 */ });
  }, []);
  return null;
}
