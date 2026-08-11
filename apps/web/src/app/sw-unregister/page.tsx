"use client";

import { useEffect, useState } from "react";
import { Card, PageHeader } from "@/components/ui";

/**
 * Service Worker 卸载后门（P6-D）。
 *
 * **为什么值得单独一页**：SW 是整个前端里唯一能把用户**永久**锁在旧版本上
 * 的东西——它拦在页面和网络之间，用户刷新多少次都没用，清缓存也未必够。
 * 出事时需要一个能用一句话说出口的地址：「打开 /sw-unregister」。
 *
 * 页面是**自动执行**的：走到这里的人已经出问题了，不该再让他去点按钮。
 * 三件事一起做：注销全部注册、删掉全部缓存、如实报告删了几个。
 */
export default function SwUnregisterPage() {
  const [state, setState] = useState<"working" | "done" | "unsupported">("working");
  const [detail, setDetail] = useState("");

  useEffect(() => {
    if (!("serviceWorker" in navigator)) {
      setState("unsupported");
      return;
    }
    (async () => {
      const regs = await navigator.serviceWorker.getRegistrations();
      await Promise.all(regs.map((r) => r.unregister()));
      let cacheCount = 0;
      if (typeof caches !== "undefined") {
        const names = await caches.keys();
        cacheCount = names.length;
        await Promise.all(names.map((n) => caches.delete(n)));
      }
      setDetail(`service worker: ${regs.length} · caches: ${cacheCount}`);
      setState("done");
    })();
  }, []);

  return (
    <>
      <PageHeader titleKey="sw.unregister.title" leadKey="sw.unregister.lead" />
      <Card>
        <p className="t-body text-fg" data-sw-unregister-state={state}>
          {state === "working" && "正在清理… / Cleaning up…"}
          {state === "done" && "已清理干净。回到任意页面刷新即可。 / Done. Reload any page."}
          {state === "unsupported"
            && "这个浏览器没有 Service Worker，无需清理。 / No service worker here."}
        </p>
        {detail && (
          <p className="t-mono t-micro mt-2 text-fg-faint" data-sw-unregister-detail>
            {detail}
          </p>
        )}
      </Card>
    </>
  );
}
