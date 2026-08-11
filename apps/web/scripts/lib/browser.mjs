/**
 * 浏览器门禁的共用样板。
 *
 * 抽这一层的原因很具体：六个门禁脚本逐字重复着同一段
 * `puppeteer.connect(...) + defaultViewport {1280,900}`，于是「全仓库
 * 零 `page.setViewport` 调用」——**手机上坏没坏，现有门禁一次都没机会发现**。
 * 视口成为参数之后，加一档手机才是改一行的事。
 */
import puppeteer from "puppeteer-core";

/** 门禁认可的视口档位。改这里等于改全部门禁的口径，所以只留两档。 */
export const VIEWPORTS = {
  /** 桌面基线。跨页对齐门禁逐像素比对的就是这一档，**数值不许动**。 */
  desktop: { width: 1280, height: 900 },
  /**
   * iPhone 14 档。390×844 是当前最常见的手机逻辑分辨率；
   * `isMobile`/`hasTouch` 让 `@media (pointer: coarse)` 与触摸事件真的生效——
   * 只改宽高的话，测的还是「窄窗口的桌面」，不是手机。
   */
  mobile: {
    width: 390, height: 844,
    deviceScaleFactor: 3, isMobile: true, hasTouch: true,
  },
};

/** `--viewport=mobile` → 档位名；缺省 desktop。未知档位直接报错，不静默回落。 */
export function viewportFromArgv(argv = process.argv) {
  const flag = argv.find((a) => a.startsWith("--viewport="));
  const name = flag ? flag.split("=")[1] : "desktop";
  if (!(name in VIEWPORTS)) {
    throw new Error(`未知视口档位 ${name}；可用：${Object.keys(VIEWPORTS).join(" / ")}`);
  }
  return name;
}

/** `--base <url>` → 基址；缺省本地 dev server。 */
export function baseFromArgv(argv = process.argv) {
  const i = argv.indexOf("--base");
  return i >= 0 ? argv[i + 1] : "http://127.0.0.1:3100";
}

/**
 * 连上已在跑的 Chrome（:9222）并开一页，按档位设视口。
 * 返回 `{ browser, page, viewport, viewportName }`；调用方负责 close/disconnect。
 */
export async function openPage(viewportName = "desktop") {
  const viewport = VIEWPORTS[viewportName];
  const browser = await puppeteer.connect({
    browserURL: "http://127.0.0.1:9222",
    defaultViewport: viewport,
  });
  const page = await browser.newPage();
  // connect 的 defaultViewport 只作用于 newPage 创建的那一刻；显式再设一次，
  // 保证 isMobile/hasTouch 这些非尺寸字段确实生效。
  await page.setViewport(viewport);
  return { browser, page, viewport, viewportName };
}

/**
 * 「页面 body 不许横向滚动」——本轮性价比最高的一条断言：
 * 一条就能兜住绝大多数「手机上崩了」。
 *
 * 容差 1px 是给亚像素布局的（`scrollbar-gutter: stable` 与 transform 都会
 * 产生零点几像素的余量）；再大就会放过真实溢出。
 * 返回 null 表示通过，否则返回一段可读的失败说明（含最宽的几个元素）。
 */
export async function checkNoHorizontalOverflow(page, tolerance = 1) {
  return page.evaluate((tol) => {
    const doc = document.documentElement;
    const over = doc.scrollWidth - doc.clientWidth;
    if (over <= tol) return null;
    // 报「谁把它撑宽的」，否则拿到 FAIL 也不知道去哪找。
    //
    // 两条排除规则，都是实测踩出来的：
    // ① `position: fixed` 的元素要跳过——手机模拟下页面一旦溢出，
    //    Chrome 会把**布局视口**撑到内容宽度，于是 `inset-x-0` 的底部标签栏
    //    跟着变宽。它是受害者不是元凶，排在 DOM 前面还会顶掉真正的元凶；
    // ② 祖先里有 `overflow-x: auto/scroll/hidden` 的跳过——那是**设计上**
    //    允许在自己容器里横滚的宽内容（日历周网格、宽表格），
    //    它不会把整页拽横。
    // 剩下的按「超出多少」降序，最宽的那个才是要去改的。
    // 注意排除的是**整棵 fixed 子树**，不只是那个 fixed 元素本身：
    // 底部标签栏的 `<ul>`/`<li>` 自己不是 fixed，却会跟着被撑宽的
    // 布局视口一起变宽，照样会顶掉真正的元凶。
    const inFixedSubtree = (el) => {
      for (let p = el; p && p !== document.body; p = p.parentElement) {
        if (getComputedStyle(p).position === "fixed") return true;
      }
      return false;
    };
    const scrolls = (el) => {
      for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
        const ox = getComputedStyle(p).overflowX;
        if (ox === "auto" || ox === "scroll" || ox === "hidden") return true;
      }
      return false;
    };
    const hits = [];
    for (const el of document.querySelectorAll("body *")) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      const excess = Math.max(r.right - doc.clientWidth, -r.left, 0);
      if (excess <= tol) continue;
      if (inFixedSubtree(el)) continue;
      if (scrolls(el)) continue;
      const id = el.tagName.toLowerCase()
        + (el.className && typeof el.className === "string"
          ? "." + el.className.trim().split(/\s+/).slice(0, 3).join(".")
          : "");
      hits.push({ id, excess, left: Math.round(r.left), right: Math.round(r.right) });
    }
    hits.sort((a, b) => b.excess - a.excess);
    const culprits = hits.slice(0, 4)
      .map((h) => `${h.id} [${h.left}→${h.right}] 超出 ${Math.round(h.excess)}px`);
    return `横向溢出 ${over}px（视口 ${doc.clientWidth}px）；元凶：${culprits.join(" ; ") || "未定位到（可能是某元素的负 margin 或 transform）"}`;
  }, tolerance);
}

/**
 * 元素是否**真的可见**（不只是在 DOM 里）。
 * 手机档要断言侧栏不可见——而侧栏在窄屏是 `display:none` 但**仍在 DOM 里**，
 * 用 `querySelector` 判存在会假绿。
 */
export async function isVisible(page, selector) {
  return page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (!el) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0
      && getComputedStyle(el).visibility !== "hidden";
  }, selector);
}
