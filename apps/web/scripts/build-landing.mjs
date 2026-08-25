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

/**
 * 正文用的转义 + **行内加粗**。
 *
 * 产品介绍文档里那些 `**…**` 是作者标出来的重点，压平成普通文字就把
 * "哪一句是要点"这件事丢了。**顺序不能反**：先转义再认 `**`——
 * 反过来的话正文里的 `<` 会先被当成标签。
 *
 * 这也是 §10.2 那条 i18n 坑的正解：值里写了 `**粗体**` 却没人解析，
 * 界面上就会原样出现两个星号。要么解析它，要么别写它。
 */
const rich = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

/* ------------------------------------------------------------------ */
/* 片段渲染                                                            */
/* ------------------------------------------------------------------ */

/**
 * 表格。`ours`（列序号，从 0 数）把**我们自己这一列**标出来。
 *
 * 对比表里三列长得一模一样时，"它们的重心"与"CampusPath 的区别"很容易被
 * 顺着读成同一件事——用户 2026-08-11 指出这正是会看错的地方。
 * 给那一列上底色是**区分立场**，不是装饰：读者一眼就知道哪一列是我们说的话。
 * 不做成"永远高亮最后一列"：痛点成本表、四层记忆表的最后一列并不是我们的立场。
 */
const table = (t) => !t ? "" : `
        <div class="table-wrap">
          <table>
            <thead><tr>${t.head.map((h, i) =>
              `<th${i === t.ours ? ' class="ours"' : ""}>${esc(h)}</th>`).join("")}</tr></thead>
            <tbody>${t.rows.map((r) =>
              `<tr>${r.map((c, i) =>
                `<td class="${i === 0 ? "first" : ""}${i === t.ours ? " ours" : ""}">${rich(c)}</td>`
              ).join("")}</tr>`
            ).join("")}</tbody>
          </table>
        </div>`;

const cards = (list) => !list ? "" : `
        <div class="cards">${list.map((c) => `
          <article class="card">
            <h3>${esc(c.title)}</h3>
            <p>${rich(c.body)}</p>
          </article>`).join("")}
        </div>`;

/**
 * 流程步骤。除 `body` 外还认 `bullets`（分列小点）与 `tail`（小点之后的收束句）——
 * 加这两个是因为产品介绍文档里这一节本来就是**分点写的**，把它压成一段话
 * 会让「拆解分三层」「学校拿到哪几组数据」这类**逐条的事实**读起来像一句概括。
 */
const steps = (list) => !list ? "" : `
        <ol class="steps">${list.map((s, i) => `
          <li>
            <span class="step-n" aria-hidden="true">${String(i + 1).padStart(2, "0")}</span>
            <div>
              <h3>${esc(s.title)}</h3>${s.body ? `
              <p>${rich(s.body)}</p>` : ""}${!s.bullets ? "" : `
              <ul class="step-points">${s.bullets.map((b) =>
                `\n                <li>${rich(b)}</li>`).join("")}
              </ul>`}${s.tail ? `
              <p>${rich(s.tail)}</p>` : ""}
            </div>
          </li>`).join("")}
        </ol>`;

const paras = (list) => !list ? "" :
  list.map((p) => `        <p class="lead">${rich(p)}</p>`).join("\n");

/** 架构图（Hackathon 2026-08-25）：`docs/hackathon/architecture.svg` 内联进单文件——
 *  三份产物都可能离线打开，外链图片在 file:// 下会断。SVG 本身是英文技术图，
 *  三语只换 figcaption。窄屏横向滚动（min-width 1100px），别把 11px 的图文缩成噪点。 */
const ARCH_SVG = readFileSync(
  new URL("../../../docs/hackathon/architecture.svg", import.meta.url), "utf-8")
  .replace(/^<\?xml[^>]*>\s*/, "")
  .replace(/<svg /, '<svg role="img" ');
const figure = (f) => !f ? "" : `
        <figure class="figure">
          <div class="figure-scroll">${ARCH_SVG}</div>
          <figcaption>${rich(f.caption)}</figcaption>
        </figure>`;

/** 前置条件块。比 `note` 重一档：它不是补充说明，是**读者会追问的那件事**
 *  （"这套东西要接进学校的什么系统才成立"），所以给它边框与标题，别混进脚注。 */
const callout = (c) => !c ? "" : `
        <aside class="callout">
          <p class="callout-title"><span aria-hidden="true">▲</span> ${esc(c.title)}</p>
          <p>${rich(c.body)}</p>
        </aside>`;

const section = (code) => (s) => `
      <section id="${code}-${s.id}" class="section">
        <div class="wrap">
          <p class="kicker">${esc(s.kicker)}</p>
          <h2>${esc(s.title)}</h2>
${paras(s.body)}${figure(s.figure)}${table(s.table)}${cards(s.cards)}${steps(s.steps)}${callout(s.callout)}${
  s.note ? `\n        <p class="note">${rich(s.note)}</p>` : ""}
        </div>
      </section>`;

/**
 * 顶栏与两处 CTA 的链接属性。
 *
 * **两份产物走两种链接**（2026-08-11 用户裁定）：
 * · `standalone` —— docs/ 与 Artifact 那两份，可能被离线双击打开、也可能挂在
 *   别的域名上，所以必须是**绝对地址 + 新标签页**；相对路径在 `file://` 下直接失效。
 * · `site` —— 随 web app 一起部署的那一份（同一个 Cloud Run 服务、同一个域名），
 *   宣传页与产品本来就是一个站，跳自己家的 `/login` 用**同标签页相对路径**：
 *   不新开标签、不写死域名（换自定义域名时不用重新生成）。
 */
const ctaLink = (mode) => mode === "site"
  ? 'href="/login"'
  : `href="${APP_URL}" target="_blank" rel="noopener"`;

/**
 * 导航七项 → 各自的分页面装哪些章节。
 *
 * 用户 2026-08-11 裁定：导航要**切分页面**，不是在同一张长页上来回跳。
 * 十个章节里有三个不在导航上，必须各自有归宿——**内容一条都不许因为
 * 改成分页而丢掉**：
 * · `compare`（与竞品对比）跟着「能得到什么」——两者回答的是同一个问题的正反面；
 * · `control`（谁说了算）与 `numbers`（数字与还没做的）跟着「技术」——
 *   红线与"不宣称没有基线的事"都是"这东西是怎么造的"的一部分。
 */
const VIEW_GROUPS = {
  what: ["what"],
  pain: ["pain"],
  who: ["who"],
  value: ["value", "compare"],
  memory: ["memory"],
  how: ["how"],
  tech: ["tech", "control", "numbers"],
};

/** 一份语言的完整 <div lang>。三份同时在 DOM 里，切换只改 hidden。
 *
 *  分页面同理：**十个章节全部留在 DOM 里**，切换只改 `hidden`。
 *  这样没有 JS 时整页照旧是一张长页（渐进增强），Ctrl+F 与打印也仍然
 *  搜得到、印得全——把内容真的删掉才是不可接受的那一种"分页"。 */
const pane = (code, d, mode) => {
  const byId = Object.fromEntries(d.sections.map((s) => [s.id, s]));
  // 导航之外的章节若漏了归宿，构建期当场报错——不许静默丢内容
  const placed = new Set(Object.values(VIEW_GROUPS).flat());
  const orphans = d.sections.map((s) => s.id).filter((id) => !placed.has(id));
  if (orphans.length) {
    throw new Error(`章节没有归宿，会在分页模式下消失：${orphans.join(", ")}`
      + "——把它加进 VIEW_GROUPS 或加进 nav");
  }

  // Hero 只属于**第一个分页面**。它是这一页的开场白，跟着每个标签重复出现
  // 就不再是开场白了；而常驻的 CTA 与口令仍由顶栏和底部 CTA 带栏承担，
  // 所以切到任何一页都还找得到入口。
  const hero = `
        <header class="hero">
          <div class="wrap">
            <p class="kicker">${esc(d.hero.kicker)}</p>
            <h1>${esc(d.hero.title)}</h1>
            <p class="hero-lead">${rich(d.hero.lead)}</p>
            <div class="hero-actions">
              <a class="btn btn-primary" ${ctaLink(mode)}
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
        </header>`;

  const views = d.nav.map(([navId], i) => `
      <div class="view" data-view="${code}-${navId}">${i === 0 ? hero : ""}
${(VIEW_GROUPS[navId] ?? [navId]).filter((id) => byId[id])
  .map((id) => section(code)(byId[id])).join("\n")}
      </div>`).join("\n");

  return `
    <div class="pane" data-lang-pane="${code}" lang="${d.htmlLang}"${
      code === "zh-Hans" ? "" : " hidden"}>
${views}

      <section class="cta-band">
        <div class="wrap">
          <div class="cta-inner">
            <div class="cta-mark" aria-hidden="true">◱</div>
            <div class="cta-text">
              <h2>${esc(d.ctaBand.title)}</h2>
              <p>${rich(d.ctaBand.body)}</p>
              <p class="cta-note">${esc(d.ctaBand.note)}</p>
            </div>
            <div class="cta-act">
              <a class="btn btn-primary" ${ctaLink(mode)}
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
};

/* ------------------------------------------------------------------ */
/* 页面                                                                */
/* ------------------------------------------------------------------ */

/** 三个语言面板同时在 DOM 里，所以章节 id **必须**按语言加前缀——
 *  否则 `#how` 有三份，锚点会跳到当前隐藏的那个面板上（实测过，会跳错）。 */
const navFor = (code, d) => d.nav.map(([id, label], i) =>
  `<a href="#${code}-${id}" data-view-link="${code}-${id}"${
    i === 0 ? ' aria-current="page"' : ""}>${esc(label)}</a>`).join("");

/** 整页。`mode` 决定 CTA 走绝对地址新标签页（standalone）还是站内相对路径（site）。 */
const renderPage = (mode) => `<!doctype html>
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
/* 当前分页面。导航现在是标签而不是锚点，"我在哪一页"必须一眼看得出
   （ui-ux-pro-max §9 nav-state-active）。没有 JS 时全部页面都显示，
   这时高亮第一项也不会误导——那页确实就在最上面。 */
.navlinks a[aria-current="page"]{
  background:var(--accent-soft); color:var(--accent-deep); font-weight:640;
}
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
/* 章节小标（kicker）。它对应产品介绍文档里的 ## 一级章节名，不是装饰性
   的眉批——所以用强调色 + 浅底药丸把"这是一章的名字"标出来，
   而不是继续用灰色小字（用户 2026-08-11 指出：灰得读不出它是标题）。 */
.kicker{
  display:inline-block;
  font-size:12px; letter-spacing:.06em; font-weight:680; margin:0 0 12px;
  color:var(--accent-deep); background:var(--accent-soft);
  border-radius:999px; padding:3px 11px;
}
/* hero 的 kicker 是受众说明（"面向在校本科生 · 由大学部署"），不是章节名，
   保持素净——同一个类两种角色时，把差异写清楚比再造一个类省事。 */
.hero .kicker{
  background:none; color:var(--fg-muted); font-weight:600; padding:0;
  letter-spacing:.09em; text-transform:uppercase;
}

/* 行内加粗：只加重量、不换颜色。正文里已经有强调色在用（链接、kicker），
   再给 strong 上色会让一段话出现三种"重要"。 */
strong{font-weight:680; color:var(--fg)}
.note strong,.step-points strong,.card strong,.callout strong{color:var(--fg)}
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

/* 前置条件块：比 .note 重一档但不抢章节标题的位置——陶土浅底 + 左侧实线，
   与产品里的 .ai-note 同一语汇（"这句是系统在说明前提"）。 */
.callout{
  margin:26px 0 0; max-width:76ch; padding:14px 16px;
  background:var(--accent-soft); border-left:3px solid var(--accent-deep);
  border-radius:0 var(--radius-sm) var(--radius-sm) 0;
}
.callout p{margin:0; color:var(--fg-muted); font-size:14.5px; line-height:1.62}
.callout-title{
  font-weight:680; color:var(--accent-deep) !important; font-size:13px !important;
  letter-spacing:.02em; margin:0 0 6px !important;
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
/* 架构图跳出正文栏：1600×960 的图塞进 ~1000px 栏里文字只剩 7px。宽屏按视口铺开
   （上限 1600），窄屏仍在图内横向滚动——body 永不横向滚动，门禁量的就是这一条。 */
.figure{
  margin:26px 0 0; border:1px solid var(--line); border-radius:var(--radius); background:#fff; overflow:hidden;
  width:min(1600px, calc(100vw - 48px)); position:relative; left:50%; transform:translateX(-50%);
}
.figure-scroll{overflow-x:auto; -webkit-overflow-scrolling:touch}
.figure svg{display:block; width:100%; min-width:1100px; height:auto}
.figure figcaption{padding:12px 16px; font-size:13.5px; color:var(--fg-muted); border-top:1px solid var(--line); background:var(--bg-sunk)}
.section:nth-of-type(even) .figure{background:#fff}
table{border-collapse:collapse; width:100%; min-width:520px; font-size:14px}
th,td{text-align:start; padding:11px 14px; border-bottom:1px solid var(--line); vertical-align:top}
th{background:var(--bg-sunk); font-weight:620; font-size:13px; color:var(--fg); white-space:nowrap}
tbody tr:last-child td{border-bottom:none}
td.first{font-weight:600; color:var(--fg); white-space:nowrap}
.section:nth-of-type(even) .table-wrap{background:var(--bg)}
.section:nth-of-type(even) th{background:var(--bg-sunk)}
/* 我们自己那一列。底色 + 左侧一道强调线把它与"它们的重心"分开；
   表头再加重一档，让"这一列是谁在说话"从第一行就成立。
   .section:nth-of-type(even) th 也会命中这一格，所以 th.ours 要写在它后面。 */
td.ours{background:var(--accent-soft)}
th.ours,
.section:nth-of-type(even) th.ours{
  /* 表头**不再加深**：加深到 accent-soft 78% + accent 时，13px 粗体的
     accent-deep 只有 3.93:1，够不上 AA 的 4.5（13px 也不算"大字"）。
     与单元格同底、靠左侧强调线与字重区分，实测 4.82:1。 */
  background:var(--accent-soft);
  color:var(--accent-deep);
}
td.ours,th.ours{border-inline-start:2px solid var(--accent)}

.steps{list-style:none; counter-reset:none; margin:28px 0 0; padding:0; display:grid; gap:2px}
/* 直接子级选择器是**必须的**：.steps li 会连步骤里的分列小点一起选中，
   而 .steps li:last-child（0,2,1）比 .step-points li（0,1,1）特异性更高，
   于是每组小点的最后一条会自己长出一条分割线——步骤之间该有的线，
   跑到步骤**内部**去了（用户 2026-08-11 截图指出）。 */
.steps > li{display:flex; gap:18px; padding:18px 0; border-top:1px solid var(--line)}
.steps > li:last-child{border-bottom:1px solid var(--line)}
.step-n{
  flex:0 0 auto; width:38px; font-variant-numeric:tabular-nums;
  font-size:13px; font-weight:700; color:var(--accent-deep); padding-top:2px;
}
.steps h3{font-size:16px; font-weight:640; margin:0 0 6px}
.steps p{margin:0; color:var(--fg-muted); font-size:14.5px; max-width:76ch}
.steps p + p{margin-top:8px}
/* 步骤里的分列小点：跟正文同色同字号，只靠一个小方块把"这是逐条的事实"
   与"这是一段说明"分开——加大字重或换色会把它抬到和步骤标题打架。 */
.step-points{
  margin:8px 0 0; padding:0; list-style:none; max-width:76ch;
  display:grid; gap:5px;
}
.step-points li{
  display:block; padding:0 0 0 15px; border:0; position:relative;
  color:var(--fg-muted); font-size:14.5px;
}
.step-points li::before{
  content:""; position:absolute; left:2px; top:.72em;
  width:5px; height:5px; border-radius:1px; background:var(--accent);
}
.step-points + p{margin-top:10px}

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
  /* 导航**不能再隐藏**：它从"页内锚点"变成了"分页面标签"，藏起来等于
     手机上除了第一页哪都去不了。改成折到第二行的可横滚标签条，
     顶栏因此改为自适应高度。 */
  .topbar{height:auto; min-height:var(--nav-h)}
  .topbar .wrap{flex-wrap:wrap; gap:10px; padding-block:8px; row-gap:4px}
  .navlinks{order:3; width:100%; margin-inline:0; padding-bottom:2px}
  .brand-sub{display:none}
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
/* 打印与「没有 JS」这两种情况下，分页必须自己让开：
   .view 默认就是显示的，是脚本给非当前页加上 hidden；打印时把它掀回来，
   一份 PDF 仍然是完整的十章，不是当前那一页。 */
@media print{
  .topbar{display:none}
  .section{break-inside:avoid}
  .view[hidden]{display:block !important}
}
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
      <a class="btn btn-primary" ${ctaLink(mode)}
         data-cta="topbar" data-cta-label>
        <span data-cta-full>${esc(zhHans.cta)}</span
        ><span data-cta-short>${esc(zhHans.ctaShort)}</span>
        <span aria-hidden="true">→</span></a>
    </div>
  </div>
</nav>

<main id="top">
${Object.entries(DICTS).map(([code, d]) => pane(code, d, mode)).join("\n")}
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
  var current = { code: "zh-Hans", view: NAV["zh-Hans"].nav[0][0] };

  /** 显示某个分页面：只在**当前语言**的面板里切，其余语言整块本来就 hidden。
   *  语言切换时按同一个 view id 复位，读者不会因为换语言被丢回第一页。 */
  function showView(viewId, scroll) {
    current.view = viewId;
    document.querySelectorAll("[data-view]").forEach(function (v) {
      v.hidden = v.getAttribute("data-view") !== current.code + "-" + viewId;
    });
    links.querySelectorAll("a").forEach(function (a) {
      if (a.getAttribute("data-view-link") === current.code + "-" + viewId) {
        a.setAttribute("aria-current", "page");
      } else {
        a.removeAttribute("aria-current");
      }
    });
    if (scroll) window.scrollTo(0, 0);
  }

  function apply(code) {
    if (!NAV[code]) code = "zh-Hans";
    current.code = code;
    document.querySelectorAll("[data-lang-pane]").forEach(function (p) {
      p.hidden = p.getAttribute("data-lang-pane") !== code;
    });
    document.documentElement.lang = NAV[code].lang;
    links.innerHTML = NAV[code].nav.map(function (n) {
      return '<a href="#' + code + "-" + n[0] + '" data-view-link="'
        + code + "-" + n[0] + '">' + n[1] + "</a>";
    }).join("");
    ctaLabel.querySelector("[data-cta-full]").textContent = NAV[code].cta;
    ctaLabel.querySelector("[data-cta-short]").textContent = NAV[code].short;
    sub.textContent = NAV[code].sub;
    sel.value = code;
    // 换语言不改当前在看哪一页；那一页在新语言里若不存在（不会发生，
    // 三份 nav 同构）则回到第一页
    var ids = NAV[code].nav.map(function (n) { return n[0]; });
    showView(ids.indexOf(current.view) >= 0 ? current.view : ids[0], false);
    try { localStorage.setItem(KEY, code); } catch (e) {}
  }

  /** 导航点击 = 换页，不是页内滚动。hash 仍然写进去，所以链接可以直接分享
   *  到某一页；#zh-Hans-compare 这类**藏在某页里的章节 id** 也认，
   *  它会打开包含它的那一页。 */
  function viewOfHash(hash) {
    var h = (hash || "").replace(/^#/, "");
    if (!h) return null;
    var box = null;
    var all = document.querySelectorAll("[data-view]");
    for (var i = 0; i < all.length && !box; i++) {
      if (all[i].getAttribute("data-view") === h) box = all[i];
    }
    if (!box) {
      var sec = document.getElementById(h);
      box = sec && sec.closest ? sec.closest("[data-view]") : null;
    }
    if (!box) return null;
    // 前缀是语言码，而 "zh-Hans" 自己带连字符——**不能按 "-" 切**，
    // 只能按已知的语言码长度裁。（第一版就是这么错的。）
    var paneEl = box.closest("[data-lang-pane]");
    var code = paneEl ? paneEl.getAttribute("data-lang-pane") : current.code;
    return box.getAttribute("data-view").slice(code.length + 1);
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
  // 进来时如果 URL 带 hash，直接开到那一页（分享链接能落到具体一页）
  var fromHash = viewOfHash(location.hash);
  if (fromHash) showView(fromHash, false);
  sel.addEventListener("change", function () { apply(sel.value); });

  // 导航 = 换页。用委托绑在容器上——apply() 会重建这几个 a，
  // 逐个绑事件会在换一次语言后全部失效。
  links.addEventListener("click", function (e) {
    var a = e.target.closest("[data-view-link]");
    if (!a) return;
    e.preventDefault();
    var id = a.getAttribute("data-view-link");
    showView(id.slice(current.code.length + 1), true);
    if (history.replaceState) history.replaceState(null, "", "#" + id);
    else location.hash = id;
  });
  // 浏览器前进/后退
  window.addEventListener("hashchange", function () {
    var v = viewOfHash(location.hash);
    if (v) showView(v, true);
  });
  // 站标回到第一页
  var brand = document.querySelector(".brand");
  if (brand) brand.addEventListener("click", function (e) {
    e.preventDefault();
    showView(NAV[current.code].nav[0][0], true);
  });

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

/** 离线 / 外链那一档：CTA 是绝对地址 + 新标签页。 */
const html = renderPage("standalone");

/** 随站点部署那一档：CTA 是站内 `/login`，同标签页。
 *  两份**只差链接**——正文若开始漂移，说明有人手改了 HTML。 */
const siteHtml = renderPage("site");

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
 *  它与 docs/ 那份**只应该差 CTA 的链接**，正文逐字节相同；
 *  `--check` 用「把它的站内链接换回绝对地址后必须等于 docs 那份」来守这一点，
 *  比放着不校验强——只校验其中一份，另一份被手改就永远发现不了。 */
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
  if (pub !== siteHtml) {
    console.error("apps/web/public/landing.html 与 docs/ 那份不一致——重新生成，"
      + "别只改一处（线上发出去的是 public/ 这份）");
    process.exit(1);
  }
  console.log("campuspath-landing.html 一致（docs / artifact / public 三份）");
} else {
  writeFileSync(target, html, "utf-8");
  writeFileSync(fragmentTarget, fragment, "utf-8");
  writeFileSync(publicTarget, siteHtml, "utf-8");
  console.log(`已生成 campuspath-landing.html（三语，${html.length.toLocaleString()} 字节）`
    + ` + landing/artifact.html + apps/web/public/landing.html`);
}
