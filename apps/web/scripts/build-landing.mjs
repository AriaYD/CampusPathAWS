/**
 * 生成三语产品宣传页 `docs/campuspath-landing.html`。
 *
 *   bun apps/web/scripts/build-landing.mjs           重新生成
 *   bun apps/web/scripts/build-landing.mjs --check   只校验不写盘（入库文件不一致则退出 1）
 *
 * 与 `i18n:hant` / `contracts-check` 同一守法：**生成物入库、检查器守一致性**。
 * 文案源在 `docs/landing/content.mjs`（简体 + 英文两份），繁体由 OpenCC(cn→hk)
 * 确定性转换——**禁止手写繁体，也禁止手改产出的 HTML**。
 *
 * 页面是**自包含**的：CSS/JS 全内联，不引外部字体与脚本。理由有两条——
 * 它要能直接丢给评委打开（可能没网），而且不引外部资源就没有 CSP 与追踪问题。
 */
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import * as OpenCC from "opencc-js";
import { APP_URL, PASSCODE, en, zhHans } from "../../../docs/landing/content.mjs";

const convert = OpenCC.Converter({ from: "cn", to: "hk" });

/** 递归转换字符串叶子；结构原样保留。 */
function toHant(value) {
  if (typeof value === "string") return convert(value);
  if (Array.isArray(value)) return value.map(toHant);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([k, v]) => [k, toHant(v)]),
    );
  }
  return value;
}

const zhHant = { ...toHant(zhHans), htmlLang: "zh-Hant" };
// nav 的 key 是锚点 id，不能被转换（"what" 不会变，但保险起见按源还原）
zhHant.nav = zhHans.nav.map(([id, label]) => [id, convert(label)]);
zhHant.sections = zhHant.sections.map((s, i) => ({
  ...s, id: zhHans.sections[i].id,
}));

const DICTS = { "zh-Hans": zhHans, "zh-Hant": zhHant, en };

const esc = (s) =>
  String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/* ------------------------------------------------------------------ */
/* 片段渲染                                                            */
/* ------------------------------------------------------------------ */

const table = (t) => !t ? "" : `
        <div class="table-wrap">
          <table>
            <thead><tr>${t.head.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead>
            <tbody>${t.rows.map((r) =>
              `<tr>${r.map((c, i) =>
                `<td${i === 0 ? ' class="first"' : ""}>${esc(c)}</td>`).join("")}</tr>`
            ).join("")}</tbody>
          </table>
        </div>`;

const cards = (list) => !list ? "" : `
        <div class="cards">${list.map((c) => `
          <article class="card">
            <h3>${esc(c.title)}</h3>
            <p>${esc(c.body)}</p>
          </article>`).join("")}
        </div>`;

const steps = (list) => !list ? "" : `
        <ol class="steps">${list.map((s, i) => `
          <li>
            <span class="step-n" aria-hidden="true">${String(i + 1).padStart(2, "0")}</span>
            <div>
              <h3>${esc(s.title)}</h3>
              <p>${esc(s.body)}</p>
            </div>
          </li>`).join("")}
        </ol>`;

const paras = (list) => !list ? "" :
  list.map((p) => `        <p class="lead">${esc(p)}</p>`).join("\n");

const section = (code) => (s) => `
      <section id="${code}-${s.id}" class="section">
        <div class="wrap">
          <p class="kicker">${esc(s.kicker)}</p>
          <h2>${esc(s.title)}</h2>
${paras(s.body)}${table(s.table)}${cards(s.cards)}${steps(s.steps)}${
  s.note ? `\n        <p class="note">${esc(s.note)}</p>` : ""}
        </div>
      </section>`;

/** 一份语言的完整 <div lang>。三份同时在 DOM 里，切换只改 hidden——
 *  这样锚点导航、Ctrl+F 与打印都不依赖 JS 先跑一遍。 */
const pane = (code, d) => `
    <div class="pane" data-lang-pane="${code}" lang="${d.htmlLang}"${
      code === "zh-Hans" ? "" : " hidden"}>
      <header class="hero">
        <div class="wrap">
          <p class="kicker">${esc(d.hero.kicker)}</p>
          <h1>${esc(d.hero.title)}</h1>
          <p class="hero-lead">${esc(d.hero.lead)}</p>
          <div class="hero-actions">
            <a class="btn btn-primary" href="${APP_URL}" target="_blank" rel="noopener"
               data-cta="hero">${esc(d.cta)} <span aria-hidden="true">→</span></a>
            <span class="passcode" data-passcode>
              <span class="passcode-label">${esc(d.ctaHint)}</span>
              <code>${esc(PASSCODE)}</code>
              <button type="button" class="copy" data-copy="${esc(PASSCODE)}"
                      aria-label="copy">⧉</button>
            </span>
          </div>
          <dl class="stats">${d.hero.stats.map(([n, label]) => `
            <div><dt>${esc(n)}</dt><dd>${esc(label)}</dd></div>`).join("")}
          </dl>
        </div>
      </header>
${d.sections.map(section(code)).join("\n")}

      <section class="cta-band">
        <div class="wrap">
          <div class="cta-inner">
            <div class="cta-mark" aria-hidden="true">◱</div>
            <div class="cta-text">
              <h2>${esc(d.ctaBand.title)}</h2>
              <p>${esc(d.ctaBand.body)}</p>
              <p class="cta-note">${esc(d.ctaBand.note)}</p>
            </div>
            <div class="cta-act">
              <a class="btn btn-primary" href="${APP_URL}" target="_blank" rel="noopener"
                 data-cta="band">${esc(d.cta)} <span aria-hidden="true">→</span></a>
              <span class="passcode" data-passcode>
                <span class="passcode-label">${esc(d.ctaHint)}</span>
                <code>${esc(PASSCODE)}</code>
                <button type="button" class="copy" data-copy="${esc(PASSCODE)}"
                        aria-label="copy">⧉</button>
              </span>
            </div>
          </div>
        </div>
      </section>

      <footer class="foot">
        <div class="wrap">
          <p class="synthetic">${esc(d.footer.synthetic)}</p>
          <p class="note">${esc(d.footer.note)}</p>
        </div>
      </footer>
    </div>`;

/* ------------------------------------------------------------------ */
/* 页面                                                                */
/* ------------------------------------------------------------------ */

/** 三个语言面板同时在 DOM 里，所以章节 id **必须**按语言加前缀——
 *  否则 `#how` 有三份，锚点会跳到当前隐藏的那个面板上（实测过，会跳错）。 */
const navFor = (code, d) => d.nav.map(([id, label]) =>
  `<a href="#${code}-${id}">${esc(label)}</a>`).join("");

const html = `<!doctype html>
<html lang="zh-Hans" data-landing>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#faf9f5">
<title>CampusPath · 一个目标 → 一条今天就能走的路</title>
<meta name="description" content="以学生目标为中心的成长规划系统，与校方资源效能分析构成双闭环。港科大 Google 黑客松项目。">
<style>
:root{
  /* Clay 令牌 v2.0，取自 apps/web/src/app/globals.css——宣传页与产品同一套色 */
  --bg:#faf9f5; --bg-sunk:#f0eee6; --bg-card:#fffefb;
  --fg:#29261b; --fg-muted:#5c5648; --fg-faint:#6b6455;
  --line:#e0dbcd; --line-strong:#cdc6b4;
  --accent:#d3714e; --accent-deep:#a04a2a; --accent-soft:#f6e3d8; --accent-fg:#fff;
  --radius:12px; --radius-sm:8px;
  --nav-h:60px;
  --shadow:0 1px 2px rgb(41 38 27/.05), 0 4px 14px rgb(41 38 27/.05);
  --wrap:1120px;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%; scroll-behavior:smooth; scroll-padding-top:calc(var(--nav-h) + 12px)}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
body{
  margin:0; background:var(--bg); color:var(--fg);
  font-family:ui-sans-serif,-apple-system,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",
    "Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
  font-size:16px; line-height:1.7; letter-spacing:.005em;
  overflow-wrap:anywhere;
}
.wrap{max-width:var(--wrap); margin:0 auto; padding:0 24px}
a{color:var(--accent-deep)}
:focus-visible{outline:2px solid var(--accent); outline-offset:2px; border-radius:6px}

/* ── 顶栏：品牌 / 章节锚点 / 语言 / 常驻 CTA（Consilium 的引导形状）── */
.topbar{
  position:sticky; top:0; z-index:50; height:var(--nav-h);
  background:color-mix(in srgb,var(--bg) 88%,transparent);
  backdrop-filter:saturate(1.6) blur(12px);
  border-bottom:1px solid var(--line);
}
.topbar .wrap{display:flex; align-items:center; gap:12px; height:100%}
.brand{display:flex; align-items:center; gap:10px; text-decoration:none; color:var(--fg); flex:0 0 auto}
.brand-mark{
  width:30px; height:30px; border-radius:9px; flex:0 0 auto;
  background:linear-gradient(150deg,var(--accent) 0%,var(--accent-deep) 100%);
  display:grid; place-items:center; color:#fff; font-size:15px; font-weight:700;
}
.brand-name{font-weight:650; font-size:16px; line-height:1.15; letter-spacing:-.01em}
.brand-sub{display:block; font-size:11px; color:var(--fg-muted); font-weight:450}
.navlinks{display:flex; gap:2px; margin-inline:auto; overflow-x:auto; scrollbar-width:none}
.navlinks::-webkit-scrollbar{display:none}
.navlinks a{
  padding:7px 8px; border-radius:8px; text-decoration:none; color:var(--fg-muted);
  font-size:13px; white-space:nowrap; transition:background .15s,color .15s;
}
.navlinks a:hover{background:var(--bg-sunk); color:var(--fg)}
.topbar-end{display:flex; align-items:center; gap:10px; flex:0 0 auto}
.langsel{
  appearance:none; border:1px solid var(--line-strong); background:var(--bg-card);
  color:var(--fg); border-radius:8px; padding:6px 26px 6px 10px; font-size:13px;
  font-family:inherit; cursor:pointer;
  background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='6'><path d='M1 1l4 4 4-4' fill='none' stroke='%235c5648' stroke-width='1.5'/></svg>");
  background-repeat:no-repeat; background-position:right 9px center;
}
.btn{
  display:inline-flex; align-items:center; gap:7px; border-radius:10px;
  padding:9px 16px; font-size:14px; font-weight:550; text-decoration:none;
  border:1px solid transparent; cursor:pointer; font-family:inherit;
  transition:transform .12s ease, box-shadow .15s ease, background .15s ease;
}
.btn:active{transform:translateY(1px)}
.btn-primary{background:var(--accent-deep); color:var(--accent-fg); box-shadow:var(--shadow)}
.btn-primary:hover{background:#8f4125}
.topbar .btn-primary{border-color:var(--accent-deep)}
/* 窄屏顶栏只放得下短标签：全称在 390px 上实测右缘 437px，整块按钮伸到视口外
   （body 不横向滚动，所以「无溢出」断言看不见它——按钮自己被切掉了）。 */
[data-cta-short]{display:none}
@media (max-width:640px){
  [data-cta-full]{display:none}
  [data-cta-short]{display:inline}
  .topbar .btn{padding:9px 12px}
  .langsel{padding:6px 22px 6px 8px; font-size:12px; max-width:104px}
}

/* ── Hero ── */
.kicker{
  font-size:12px; letter-spacing:.09em; text-transform:uppercase;
  color:var(--fg-muted); font-weight:600; margin:0 0 10px;
}
.hero{padding:76px 0 56px; border-bottom:1px solid var(--line)}
.hero h1{
  font-size:clamp(30px,5.4vw,52px); line-height:1.18; letter-spacing:-.02em;
  font-weight:700; margin:0 0 20px; max-width:19ch;
}
.hero-lead{font-size:clamp(15px,1.9vw,18px); color:var(--fg-muted); max-width:66ch; margin:0 0 28px}
.hero-actions{display:flex; flex-wrap:wrap; align-items:center; gap:14px}
.stats{display:flex; flex-wrap:wrap; gap:36px; margin:44px 0 0}
.stats div{margin:0}
.stats dt{font-size:clamp(24px,3.4vw,32px); font-weight:700; letter-spacing:-.02em; font-variant-numeric:tabular-nums}
.stats dd{margin:2px 0 0; font-size:13px; color:var(--fg-muted)}

/* ── 口令：用户 2026-08-10 要求印在 CTA 旁边 ── */
.passcode{
  display:inline-flex; align-items:center; gap:8px;
  border:1px dashed var(--line-strong); border-radius:10px;
  padding:6px 10px; background:var(--bg-card);
}
.passcode-label{font-size:12px; color:var(--fg-muted)}
.passcode code{
  font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  font-size:13px; color:var(--accent-deep); font-weight:600; letter-spacing:.01em;
}
.copy{
  border:none; background:transparent; cursor:pointer; color:var(--fg-muted);
  font-size:14px; line-height:1; padding:4px; border-radius:6px;
}
.copy:hover{background:var(--bg-sunk); color:var(--fg)}
.copy[data-copied]{color:#3a6b4e}

/* ── 章节 ── */
.section{padding:64px 0; border-bottom:1px solid var(--line)}
.section:nth-of-type(even){background:var(--bg-sunk)}
.section h2{
  font-size:clamp(22px,3.2vw,32px); line-height:1.28; letter-spacing:-.015em;
  font-weight:680; margin:0 0 18px; max-width:26ch;
}
.lead{color:var(--fg-muted); max-width:74ch; margin:0 0 14px; font-size:15.5px}
.note{
  color:var(--fg-faint); max-width:76ch; font-size:14px; margin:22px 0 0;
  padding-left:14px; border-left:3px solid var(--accent-soft);
}

.cards{display:grid; grid-template-columns:repeat(auto-fit,minmax(258px,1fr)); gap:14px; margin-top:26px}
.card{
  background:var(--bg-card); border:1px solid var(--line); border-radius:var(--radius);
  padding:18px 18px 16px; box-shadow:var(--shadow); margin:0;
}
.card h3{font-size:15px; font-weight:640; margin:0 0 8px; letter-spacing:-.005em}
.card p{margin:0; font-size:14px; color:var(--fg-muted); line-height:1.65}

.table-wrap{
  margin-top:24px; overflow-x:auto; border:1px solid var(--line);
  border-radius:var(--radius); background:var(--bg-card);
}
table{border-collapse:collapse; width:100%; min-width:520px; font-size:14px}
th,td{text-align:start; padding:11px 14px; border-bottom:1px solid var(--line); vertical-align:top}
th{background:var(--bg-sunk); font-weight:620; font-size:13px; color:var(--fg); white-space:nowrap}
tbody tr:last-child td{border-bottom:none}
td.first{font-weight:600; color:var(--fg); white-space:nowrap}
.section:nth-of-type(even) .table-wrap{background:var(--bg)}
.section:nth-of-type(even) th{background:var(--bg-sunk)}

.steps{list-style:none; counter-reset:none; margin:28px 0 0; padding:0; display:grid; gap:2px}
.steps li{display:flex; gap:18px; padding:18px 0; border-top:1px solid var(--line)}
.steps li:last-child{border-bottom:1px solid var(--line)}
.step-n{
  flex:0 0 auto; width:38px; font-variant-numeric:tabular-nums;
  font-size:13px; font-weight:700; color:var(--accent-deep); padding-top:2px;
}
.steps h3{font-size:16px; font-weight:640; margin:0 0 6px}
.steps p{margin:0; color:var(--fg-muted); font-size:14.5px; max-width:76ch}

/* ── 页尾 CTA band：Consilium 的收口形状 ── */
.cta-band{padding:56px 0; background:var(--bg)}
.cta-inner{
  display:flex; align-items:center; gap:26px; flex-wrap:wrap;
  border:1px solid var(--line-strong); border-radius:16px;
  background:linear-gradient(180deg,var(--bg-card) 0%,var(--accent-soft) 260%);
  padding:26px 28px; box-shadow:var(--shadow);
}
.cta-mark{
  flex:0 0 auto; width:44px; height:44px; border-radius:12px;
  background:var(--accent-soft); color:var(--accent-deep);
  display:grid; place-items:center; font-size:20px;
}
.cta-text{flex:1 1 320px}
.cta-text h2{font-size:clamp(19px,2.4vw,24px); margin:0 0 6px; font-weight:680}
.cta-text p{margin:0; color:var(--fg-muted); font-size:14.5px; max-width:62ch}
.cta-note{margin-top:6px !important; font-size:13px !important; color:var(--fg-faint) !important}
.cta-act{display:flex; flex-direction:column; align-items:flex-start; gap:10px; flex:0 0 auto}

.foot{padding:34px 0 46px; border-top:1px solid var(--line); background:var(--bg-sunk)}
.synthetic{
  display:inline-block; font-size:12px; color:var(--fg-faint);
  border:1px solid var(--line-strong); border-radius:999px; padding:4px 12px; margin:0 0 12px;
}
.foot .note{border:none; padding:0; margin:0; font-size:13px}

/* ── 窄屏 ── */
@media (max-width:1120px){
  .navlinks{display:none}
  .brand-sub{display:none}
  .topbar .wrap{gap:10px}
  .topbar-end{margin-inline-start:auto}
}
@media (max-width:640px){
  .wrap{padding:0 18px}
  .hero{padding:44px 0 36px}
  .section{padding:44px 0}
  .stats{gap:24px}
  .cta-inner{padding:20px}
  .cta-act{width:100%}
  .cta-act .btn{width:100%; justify-content:center}
  .passcode{width:100%; justify-content:space-between}
  .hero-actions .btn{flex:1 1 auto; justify-content:center}
}
/* 触摸设备：命中区 ≥44px（iOS HIG / Material），桌面密度不动 */
@media (pointer:coarse){
  .btn{min-height:44px}
  .langsel{min-height:44px}
  .copy{min-width:44px; min-height:44px}
  .navlinks a{min-height:44px; display:flex; align-items:center}
}
@media print{.topbar{display:none} .section{break-inside:avoid}}
</style>
</head>
<body>
<nav class="topbar">
  <div class="wrap">
    <a class="brand" href="#top">
      <span class="brand-mark" aria-hidden="true">C</span>
      <span>
        <span class="brand-name">CampusPath</span>
        <span class="brand-sub" data-brand-sub>${esc(zhHans.brandSub)}</span>
      </span>
    </a>
    <div class="navlinks" data-navlinks>${navFor("zh-Hans", zhHans)}</div>
    <div class="topbar-end">
      <select class="langsel" data-lang-select aria-label="Language">
        <option value="zh-Hans">简体中文</option>
        <option value="zh-Hant">繁體中文</option>
        <option value="en">English</option>
      </select>
      <a class="btn btn-primary" href="${APP_URL}" target="_blank" rel="noopener"
         data-cta="topbar" data-cta-label>
        <span data-cta-full>${esc(zhHans.cta)}</span
        ><span data-cta-short>${esc(zhHans.ctaShort)}</span>
        <span aria-hidden="true">→</span></a>
    </div>
  </div>
</nav>

<main id="top">
${Object.entries(DICTS).map(([code, d]) => pane(code, d)).join("\n")}
</main>

<script>
(function () {
  var KEY = "campuspath.landing.locale";
  var NAV = ${JSON.stringify(
    Object.fromEntries(Object.entries(DICTS).map(([c, d]) =>
      [c, { nav: d.nav, cta: d.cta, short: d.ctaShort, sub: d.brandSub,
         lang: d.htmlLang }])))};
  var sel = document.querySelector("[data-lang-select]");
  var links = document.querySelector("[data-navlinks]");
  var ctaLabel = document.querySelector("[data-cta-label]");
  var sub = document.querySelector("[data-brand-sub]");

  function apply(code) {
    if (!NAV[code]) code = "zh-Hans";
    document.querySelectorAll("[data-lang-pane]").forEach(function (p) {
      p.hidden = p.getAttribute("data-lang-pane") !== code;
    });
    document.documentElement.lang = NAV[code].lang;
    links.innerHTML = NAV[code].nav.map(function (n) {
      return '<a href="#' + code + "-" + n[0] + '">' + n[1] + "</a>";
    }).join("");
    ctaLabel.querySelector("[data-cta-full]").textContent = NAV[code].cta;
    ctaLabel.querySelector("[data-cta-short]").textContent = NAV[code].short;
    sub.textContent = NAV[code].sub;
    sel.value = code;
    try { localStorage.setItem(KEY, code); } catch (e) {}
  }

  var stored = null;
  try { stored = localStorage.getItem(KEY); } catch (e) {}
  // 没存过就跟随浏览器语言：繁体地区给繁体，非中文给英文
  if (!stored) {
    var l = (navigator.language || "").toLowerCase();
    stored = l.indexOf("zh") === 0
      ? (/hant|tw|hk|mo/.test(l) ? "zh-Hant" : "zh-Hans")
      : (l.indexOf("zh") === -1 && l ? "en" : "zh-Hans");
  }
  apply(stored);
  sel.addEventListener("change", function () { apply(sel.value); });

  document.addEventListener("click", function (e) {
    var b = e.target.closest("[data-copy]");
    if (!b) return;
    var done = function () {
      b.setAttribute("data-copied", "1");
      b.textContent = "✓";
      setTimeout(function () {
        b.removeAttribute("data-copied");
        b.textContent = "⧉";
      }, 1600);
    };
    if (navigator.clipboard) {
      navigator.clipboard.writeText(b.getAttribute("data-copy")).then(done, function () {});
    }
  });
})();
</script>
</body>
</html>
`;

const target = fileURLToPath(new URL("../../../docs/campuspath-landing.html", import.meta.url));

/** Artifact 发布用的变体：宿主自带 doctype/html/head/body 外壳，
 *  所以这里只留 <title> + <style> + 页面内容。同一份内容，两个出口。 */
const fragment = html
  .replace(/^[\s\S]*?<title>/, "<title>")
  .replace(/<\/head>\n<body>\n/, "")
  .replace(/<\/body>\n<\/html>\n$/, "");
const fragmentTarget = fileURLToPath(
  new URL("../../../docs/landing/artifact.html", import.meta.url));

/** 第三个出口：随站点部署的那一份（Cloud Run 上 `/landing`）。
 *  与 docs/ 那份**逐字节相同**——两处内容会漂移的唯一原因是有人手改了其中一份，
 *  所以 `--check` 三份一起校验。 */
const publicTarget = fileURLToPath(
  new URL("../public/landing.html", import.meta.url));

if (process.argv.includes("--check")) {
  let current = "";
  try {
    current = readFileSync(target, "utf-8");
  } catch {
    console.error("campuspath-landing.html 不存在——先跑 bun apps/web/scripts/build-landing.mjs");
    process.exit(1);
  }
  if (current !== html) {
    console.error("campuspath-landing.html 与 docs/landing/content.mjs 不一致——重新生成，别手改 HTML");
    process.exit(1);
  }
  let frag = "";
  try { frag = readFileSync(fragmentTarget, "utf-8"); } catch {}
  if (frag !== fragment) {
    console.error("landing/artifact.html 与内容源不一致——重新生成");
    process.exit(1);
  }
  let pub = "";
  try { pub = readFileSync(publicTarget, "utf-8"); } catch {}
  if (pub !== html) {
    console.error("apps/web/public/landing.html 与 docs/ 那份不一致——重新生成，"
      + "别只改一处（线上发出去的是 public/ 这份）");
    process.exit(1);
  }
  console.log("campuspath-landing.html 一致（docs / artifact / public 三份）");
} else {
  writeFileSync(target, html, "utf-8");
  writeFileSync(fragmentTarget, fragment, "utf-8");
  writeFileSync(publicTarget, html, "utf-8");
  console.log(`已生成 campuspath-landing.html（三语，${html.length.toLocaleString()} 字节）`
    + ` + landing/artifact.html + apps/web/public/landing.html`);
}
