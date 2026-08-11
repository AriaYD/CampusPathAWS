#!/usr/bin/env node
/**
 * 真机调试（Android，adb + Chrome remote debugging）。
 *
 *   adb forward tcp:9333 localabstract:chrome_devtools_remote
 *   node apps/web/scripts/phone-debug.mjs [url]
 *
 * **只操作 CampusPath 的标签页**——手机上还开着用户自己的别的页面，不碰。
 * 抓的是真机上真实发生的事：页面异常、失败请求、body 到底有没有内容。
 */
import puppeteer from "puppeteer-core";

const TARGET = process.argv[2]
  ?? "https://campuspath-web-786160486093.asia-east2.run.app/login";
const HOST = "http://127.0.0.1:9333";

const browser = await puppeteer.connect({ browserURL: HOST, defaultViewport: null });
const pages = await browser.pages();
const page = pages.find((p) => p.url().includes("campuspath-web"))
  ?? await browser.newPage();

const logs = [], errors = [], failed = [];
page.on("console", (m) => logs.push(`${m.type()}: ${m.text().slice(0, 240)}`));
page.on("pageerror", (e) => errors.push(String(e).slice(0, 400)));
page.on("requestfailed", (r) => failed.push(`FAILED ${r.failure()?.errorText} ${r.url().slice(0, 130)}`));
page.on("response", (r) => { if (r.status() >= 400) failed.push(`${r.status()} ${r.url().slice(0, 130)}`); });

try {
  console.log("真机 UA:", (await browser.userAgent()).slice(0, 120));
  const resp = await page.goto(TARGET, { waitUntil: "domcontentloaded", timeout: 45000 })
    .catch((e) => ({ err: e.message }));
  await new Promise((r) => setTimeout(r, 4000));

  const info = await page.evaluate(() => {
    const bodyText = (document.body?.innerText || "").trim();
    return {
      url: location.href,
      title: document.title,
      viewport: `${window.innerWidth}×${window.innerHeight}`,
      bodyChars: bodyText.length,
      firstText: bodyText.slice(0, 100).replace(/\n/g, " | "),
      htmlLen: document.documentElement.outerHTML.length,
      bodyChildren: document.body?.children.length,
      guardChecking: !!document.querySelector("[data-guard-checking]"),
      inputs: document.querySelectorAll("input").length,
      // 常见"白屏"成因逐个点名
      localStorageOK: (() => {
        try { localStorage.setItem("__t", "1"); localStorage.removeItem("__t"); return true; }
        catch (e) { return String(e).slice(0, 80); }
      })(),
      swRegs: "pending",
      cssVarsLoaded: getComputedStyle(document.documentElement)
        .getPropertyValue("--accent").trim() || "(空=样式没加载)",
      bodyBg: getComputedStyle(document.body).backgroundColor,
      bodyHeight: document.body.getBoundingClientRect().height,
    };
  });
  info.swRegs = await page.evaluate(async () =>
    "serviceWorker" in navigator
      ? (await navigator.serviceWorker.getRegistrations()).length : "不支持");
  console.log(`\n=== ${TARGET} → status ${resp?.status?.() ?? resp?.err} ===`);
  console.log(JSON.stringify(info, null, 1));
  if (errors.length) console.log("\n页面异常:\n  " + errors.slice(0, 5).join("\n  "));
  if (failed.length) console.log("\n失败请求:\n  " + [...new Set(failed)].slice(0, 10).join("\n  "));
  const errLogs = logs.filter((l) => /^(error|warning)/.test(l));
  if (errLogs.length) console.log("\nconsole:\n  " + errLogs.slice(0, 8).join("\n  "));
  await page.screenshot({ path: process.env.SHOT
    ?? "/Users/aria_macmini/AllProjects/HKUST_CampusPath/docs/verification/phone-live.png" });
} finally {
  browser.disconnect();
}
