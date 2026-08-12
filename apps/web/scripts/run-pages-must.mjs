#!/usr/bin/env node
/**
 * run-pages-must.mjs — 吃 verify/pages.mjs 的 PAGES/GLOBAL_MUST 清单，
 * 以学生会话逐页断言 data-* 选择器存在。任何缺失 exit 1。
 *
 * 断言全部基于 data-*，对纯视觉重构免疫——重构批次跑它守"结构没被改坏"。
 * 前置：Chrome :9222 + dev server :3100。
 *
 * 视口两档（2026-08-10）：
 *   node scripts/run-pages-must.mjs                     # 桌面 1280×900
 *   node scripts/run-pages-must.mjs --viewport=mobile   # 手机 390×844
 * 手机档多两项断言：**body 不许横向滚动**（本轮最值钱的一条）、
 * 底部标签栏在场且侧栏不可见。
 *
 * H5 自证（检查器本身要被检查）：
 *   --probe            首页塞一个不可能存在的选择器 → 必须 FAIL
 *   --probe-overflow   页面塞一个 1200px 宽的元素 → 溢出断言必须 FAIL
 *   --probe-sidebar    手机档强开侧栏 → 可见性断言必须 FAIL
 */
import { PAGES, GLOBAL_MUST, MOBILE_MUST, MOBILE_MUST_HIDDEN } from "../verify/pages.mjs";
import {
  openPage, baseFromArgv, viewportFromArgv,
  checkNoHorizontalOverflow, isVisible,
} from "./lib/browser.mjs";

const base = baseFromArgv();
const viewportName = viewportFromArgv();
const isMobile = viewportName === "mobile";

/**
 * 状态依赖基线（2026-08-01 实测，main ae36b05 与 ui/clay-restyle 完全同集）：
 * 这些选择器在**新鲜种子态**下本就不出现（要有 pending 提案 / 已写笔记 /
 * unknown 缺口 / 交互后的课程搜索 / 日历授权层级），不是重构破坏的。
 * 命中基线记 warn 不判死；基线**之外**的缺失才是回归。
 * 属性被整体删除的风险由每批 `git diff | grep -c data-` 比对兜底。
 */
const KNOWN_STATE_DEPENDENT = new Set([
  "[data-onboarding-finish]",
  "[data-proposal]",
  "[data-note]",
  "[data-unknowns]",
  "[data-prereq-counts]",
  "[data-availability-grid]",
]);

/**
 * `--wide-controls`：把原生表单控件强撑到 **Android 的真实宽度**再量溢出。
 *
 * 2026-08-11 用户手机实测报障：日历页「日常作息」的时间选择器溢出卡片，
 * 连带把固定标签栏撑宽、第 6 格滑出屏幕。桌面 Chrome **复现不出来**——
 * 它的 `<input type="time">` 约 90px，而那台 vivo 上实测 **160px**。
 * 门禁跑在桌面 Chrome 里，于是这一整类缺陷天生看不见。
 *
 * 160 不是拍脑袋：它就是真机量出来的数。
 */
const wideControls = process.argv.includes("--wide-controls");
const NATIVE_WIDE_CSS =
  'input[type="time"],input[type="date"],input[type="datetime-local"],'
  + 'input[type="month"],input[type="week"]{min-width:160px !important}';

const probe = process.argv.includes("--probe");
const probeOverflow = process.argv.includes("--probe-overflow");
const probeSidebar = process.argv.includes("--probe-sidebar");

const { browser, page } = await openPage(viewportName);
let failures = 0;

/** 手机档不该出现的选择器：侧栏在窄屏是 display:none 但仍在 DOM 里，
 *  所以 GLOBAL_MUST 的 [data-sidebar] 在手机档会**假绿**——改判可见性。 */
const globalMust = isMobile
  ? [...GLOBAL_MUST.filter((s) => !MOBILE_MUST_HIDDEN.includes(s)), ...MOBILE_MUST]
  : GLOBAL_MUST;

try {
  await page.goto(`${base}/login`, { waitUntil: "domcontentloaded" });
  const STUDENT_SESSION = { portal: "student", studentId: "STU-A" };
  const setSession = (session) => page.evaluate((s) => {
    localStorage.setItem("campuspath.session", JSON.stringify(s));
  }, session);
  await setSession(STUDENT_SESSION);

  // H5 探针（审查 M7）：--probe 给首页多塞一个不可能存在的选择器，
  // 必须报 FAIL（exit 1），否则断言循环本身坏了
  if (probe && PAGES.length) {
    // 只跑首页 + 注入不可能选择器；短超时、不重试——探针要快
    PAGES.length = 1;
    PAGES[0] = { ...PAGES[0], must: ["[data-definitely-not-here]"] };
  }
  // 溢出/侧栏探针同样只跑首页，快进快出
  if ((probeOverflow || probeSidebar) && PAGES.length) PAGES.length = 1;

  for (const spec of PAGES) {
    // 每页可声明自己的身份；没声明就是学生。切身份要在导航**之前**，
    // 否则页面守卫会先把你踢回登录页。
    await setSession(spec.session ?? STUDENT_SESSION);
    await page.goto(`${base}${spec.path}`, { waitUntil: "domcontentloaded" });
    let pageFailed = false;
    try {
      try {
        await page.waitForFunction(
          (sels) => sels.every((s) => document.querySelector(s)),
          { timeout: probe ? 5000 : 30000 },
          [...spec.must, ...globalMust],
        );
      } catch (firstErr) {
        if (probe) throw firstErr;
        // dev 首访编译抖动：重载一次再断言，仍失败才算真缺失
        await page.reload({ waitUntil: "domcontentloaded" });
        await page.waitForFunction(
          (sels) => sels.every((s) => document.querySelector(s)),
          { timeout: 30000 },
          [...spec.must, ...globalMust],
        );
      }
    } catch {
      const missing = await page.evaluate(
        (sels) => sels.filter((s) => !document.querySelector(s)),
        [...spec.must, ...globalMust],
      );
      const real = missing.filter((s) => !KNOWN_STATE_DEPENDENT.has(s));
      const warned = missing.filter((s) => KNOWN_STATE_DEPENDENT.has(s));
      if (warned.length) console.log(`warn ${spec.path}  状态依赖缺席: ${warned.join(" , ")}`);
      if (real.length) {
        failures++; pageFailed = true;
        console.log(`FAIL ${spec.path}  缺失: ${real.join(" , ")}`);
      }
    }

    // 已知失败样例：塞一个撑破视口的元素，证明溢出断言真的会响
    if (probeOverflow) {
      await page.evaluate(() => {
        const d = document.createElement("div");
        d.style.cssText = "width:1200px;height:8px";
        d.dataset.overflowProbe = "1";
        document.body.appendChild(d);
      });
    }
    // 已知失败样例：强行让侧栏可见，证明「手机上侧栏必须收起」真的会响。
    //
    // 第一版探针写错了，而且是 H5 自证抓出来的：它只给 `<nav data-sidebar>`
    // 设 display:block，可真正带 `hidden lg:block` 的是**外层 `<aside>`**——
    // 父级 display:none 时改子级毫无作用，于是注入了坏样例断言却全绿。
    // 探针必须掀开**祖先链上所有被隐藏的那一层**。
    if (probeSidebar && isMobile) {
      await page.evaluate(() => {
        const el = document.querySelector("[data-sidebar]");
        if (!el) return;
        for (let p = el; p && p !== document.body; p = p.parentElement) {
          if (getComputedStyle(p).display === "none") p.style.display = "block";
        }
        el.style.width = "210px";
        el.style.height = "40px";
      });
    }

    if (wideControls) {
      await page.addStyleTag({ content: NATIVE_WIDE_CSS });
      await new Promise((r) => setTimeout(r, 250));
    }

    if (isMobile) {
      const overflow = await checkNoHorizontalOverflow(page);
      if (overflow) {
        failures++; pageFailed = true;
        console.log(`FAIL ${spec.path}  ${overflow}`);
      }
      for (const sel of MOBILE_MUST_HIDDEN) {
        if (await isVisible(page, sel)) {
          failures++; pageFailed = true;
          console.log(`FAIL ${spec.path}  ${sel} 在手机档仍然可见（应折进底部导航）`);
        }
      }
    }

    if (!pageFailed) console.log(`  ok  ${spec.path}`);
  }
} finally {
  await page.close();
  browser.disconnect();
}

const label = `run-pages-must[${viewportName}]`;
console.log(`\n${label}: ${PAGES.length} pages, ${failures} failures`);

// 探针的成功判据是**反过来的**：它必须失败。没失败说明断言没约束力。
if (probe || probeOverflow || probeSidebar) {
  if (failures > 0) {
    console.log(`✓ H5 自证通过：探针如期触发 ${failures} 条失败`);
    process.exit(0);
  }
  console.log("✗ H5 自证失败：探针注入了已知的坏样例，断言却全绿——断言没有约束力");
  process.exit(1);
}
process.exit(failures > 0 ? 1 : 0);
