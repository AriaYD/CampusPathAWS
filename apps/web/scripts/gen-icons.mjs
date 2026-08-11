#!/usr/bin/env node
/**
 * PWA 图标生成（P6-D）。
 *
 * **不引新依赖**是硬要求：sharp / canvas 都要编原生模块，而这个仓库的
 * `package.json` 已经把 sharp 列进 `ignoreScripts`。这里复用**已有的**
 * `puppeteer-core`——把一张内联 SVG 字标渲染成 PNG，产物入库、可复现。
 *
 * 产物（`public/`）：
 *   icon-192.png / icon-512.png —— Android 与 manifest 的常规档
 *   icon-512-maskable.png       —— 安全区内缩 20%，圆形裁切不会切掉字
 *   apple-touch-icon.png(180)   —— iOS 主屏（iOS 不读 manifest 的 icons）
 *
 * 用法：Chrome 带 :9222 起着，然后 `node scripts/gen-icons.mjs`。
 * 图标不常改，所以**不进构建**——改了字标才需要手动重跑一次。
 */
import { writeFileSync } from "node:fs";
import { openPage } from "./lib/browser.mjs";

const OUT = new URL("../public/", import.meta.url).pathname;

/** clay 令牌里的强调深色 + 纯白字。与 manifest 的 theme_color 同源。 */
const BG = "#a04a2a";
const FG = "#ffffff";

/**
 * 字标：一个 "C" 加一条向上的路径折线——"CampusPath" 的两个词各出一半。
 * `safe` 是 maskable 档的内缩比例：圆形裁切最多切掉 10%，留 20% 才稳。
 */
const markup = (size, safe) => {
  const pad = Math.round(size * safe);
  const box = size - pad * 2;
  return `<!doctype html><meta charset="utf-8">
<style>
  html,body{margin:0;padding:0}
  body{width:${size}px;height:${size}px;background:${BG};
       display:flex;align-items:center;justify-content:center}
  svg{width:${box}px;height:${box}px;display:block}
</style>
<svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M72 27a30 30 0 1 0 0 46" stroke="${FG}" stroke-width="11"
        stroke-linecap="round"/>
  <path d="M45 63 L58 50 L68 57 L84 34" stroke="${FG}" stroke-width="9"
        stroke-linecap="round" stroke-linejoin="round" opacity="0.92"/>
  <circle cx="84" cy="34" r="7" fill="${FG}"/>
</svg>`;
};

const TARGETS = [
  { file: "icon-192.png", size: 192, safe: 0.16 },
  { file: "icon-512.png", size: 512, safe: 0.16 },
  { file: "icon-512-maskable.png", size: 512, safe: 0.2 },
  { file: "apple-touch-icon.png", size: 180, safe: 0.14 },
];

const { browser, page } = await openPage("desktop");
try {
  for (const { file, size, safe } of TARGETS) {
    await page.setViewport({ width: size, height: size, deviceScaleFactor: 1 });
    await page.setContent(markup(size, safe), { waitUntil: "load" });
    const buf = await page.screenshot({ type: "png", omitBackground: false });
    writeFileSync(OUT + file, buf);
    console.log(`  写出 ${file}  ${size}×${size}`);
  }
} finally {
  await page.close();
  browser.disconnect();
}
console.log(`gen-icons: ${TARGETS.length} 个图标已生成`);
