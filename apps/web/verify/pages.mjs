/**
 * D1「页面完整性」的机器化点检清单。
 *
 * 为什么不写成 `expect(page).toHaveText(...)`：这份清单要被
 * **chrome-devtools 的 evaluate_script 直接吃**，所以它只是数据，
 * 断言在浏览器里跑。判定依据一律是 `data-*` 属性——
 * 用文案做断言会在切到另一种语言时全线失败，那样双语实测就变成了摆设。
 */

export const PAGES = [
  {
    path: "/onboarding",
    // 四项授权逐项独立。「outreach 默认关闭」是**状态断言**，不放在
    // 浏览器门禁里——用户合法授权一次它就永远红（2026-08-04 实发：
    // 用户测身心链路点过授权，门禁误报）。该不变量钉在
    // services/api/tests/test_wellbeing_balance.py::
    // test_outreach_consent_defaults_off_for_every_student
    // （fresh seed 全学生遍历），浏览器只断言控件在场。
    must: [
      "[data-consent='academic']",
      "[data-consent='calendar']",
      "[data-consent='wellbeing']",
      "[data-consent='outreach']",
      "[data-onboarding-finish]",
    ],
  },
  {
    path: "/profile",
    must: ["[data-tab-panel='overview']", "[data-proposal]"],
  },
  { path: "/reflections", must: ["[data-note]", "[data-reflection-boundary]"] },
  { path: "/memory", must: ["[data-memory]", "[data-memory-export]"] },
  { path: "/goals", must: ["[data-goal-role='primary']", "[data-goal-role='candidate']"] },
  { path: "/gaps", must: ["[data-unknowns]"] },
  {
    path: "/timeline",
    // 三个时间视图与 G4 成长曲线。
    //
    // 2026-08-10（P3-G）：计划条目**不再无条件存在**——规划要学生批准才落盘，
    // 所以新学生进来看到的是「开始规划」空态。把 `[data-plan-item]` 留作硬性
    // MUST 会让这道门禁的绿取决于跑之前有没有人手动批准过一版（本轮实测就
    // 撞上了：P3 收尾时它是绿的，只因为我刚在浏览器里批准过）——那是假绿。
    //
    // 改成或选：**要么有计划、要么有开始规划的入口**。空白页仍然是失败，
    // 断言的力度没有被削弱，只是不再依赖会话状态。
    must: [
      "[data-trajectory]",
      "[data-trajectory-chart]",
      "[data-plan-item],[data-never-planned]",
    ],
  },
  {
    path: "/planner",
    must: ["[data-prereq-counts]", "[data-course]", "[data-course-search]"],
  },
  {
    path: "/calendar",
    must: ["[data-capacity-snapshot]", "[data-availability-grid]", "[data-calendar-legend]"],
  },
  {
    path: "/wellbeing",
    // 2026-08-02 睡眠-负荷平衡批：容量超载信号卡 → 平衡卡；其余四信号
    // 数据链未接入时列表为空（诚实空态），故断言平衡卡而非 [data-signal]
    must: ["[data-zero-llm]", "[data-balance-card]", "[data-wellbeing-disclaimer]", "[data-outreach-request]"],
  },
  { path: "/actions", must: ["[data-schedule-proposal],[data-action-item],[data-state='empty']"] },
  { path: "/for-you", must: ["[data-match],[data-state='unavailable']"] },
  {
    path: "/square",
    must: ["[data-square-filters]", "[data-opportunity]", "[data-why-not]", "[data-square-count]"],
  },
  {
    path: "/insights",
    // 校方页：门禁默认以学生身份跑，这里显式声明身份。
    // 不声明的话六个断言会全部"缺失"——而那是**跑错了身份**，
    // 不是页面坏了；把它当页面坏了去改页面，才是真的坏。
    session: { portal: "institution", role: "career_center_admin" },
    // 五个视图各自的容器。**抑制格必须看得见**——这一页的价值一半在于
    // 让评委看到 `Insufficient evidence` 真的会出现，而不是一片漂亮数字。
    must: [
      "[data-view='utilisation']",
      "[data-view='unmet']",
      "[data-unmet-by-school]",
      "[data-view='cohort']",
      "[data-view='conversion']",
      "[data-provenance-note]",
    ],
  },
  {
    path: "/settings",
    must: ["[data-consent-scope]", "[data-delete-data]", "[data-synthetic-badge]"],
  },
  // 签到页：四种状态互斥，任一在场即算渲染成功（无票根时是 invalid 态）。
  {
    path: "/checkin",
    must: ["[data-checkin-invalid],[data-checkin-go],[data-checkin-done],[data-checkin-dup]"],
  },

  /* ── 校方端七页（2026-08-11 P6 补入）──────────────────────────────
     此前门禁只覆盖 15 页，校方端除 `/insights` 外**零覆盖**——手机档全站
     体检当场量到 `/plaza-admin` 横向溢出 51px，而门禁一次都没报过。
     缺的不是断言的力度，是**断言的覆盖面**：没被跑过的页面，绿是没有意义的。
     每页各自声明身份，MUST 一律取结构性选择器（不取"要先有数据才出现"的）。 */
  {
    path: "/publisher",
    session: { portal: "institution", role: "publisher" },
    must: ["[data-active-role]", "textarea"],
  },
  {
    path: "/console",
    session: { portal: "institution", role: "career_center_admin" },
    must: ["[data-active-role]", "[data-registered-source]", "[data-source-health]", "[data-probe]"],
  },
  {
    path: "/review",
    session: { portal: "institution", role: "career_center_admin" },
    // 队列可能为空（诚实空态），所以判**队列容器**在场而非「有条目」。
    must: ["[data-active-role]", "[data-review-queue]"],
  },
  {
    path: "/plaza-admin",
    session: { portal: "institution", role: "career_center_admin" },
    must: ["[data-active-role]", "[data-plaza-item]", "[data-plaza-quality]"],
  },
  {
    path: "/quality-reports",
    session: { portal: "institution", role: "career_center_admin" },
    must: ["[data-active-role]", "[data-report]", "[data-report-toggle]"],
  },
  {
    path: "/wellbeing-desk",
    session: { portal: "institution", role: "wellbeing_coordinator" },
    must: ["[data-active-role]", "[data-hours-row]"],
  },
  {
    path: "/advisor-desk",
    session: { portal: "institution", role: "advisor" },
    must: ["[data-desk-tab]", "[data-occupancy]"],
  },
];

/** 每一页都要成立的全站不变量。 */
export const GLOBAL_MUST = [
  "[data-synthetic-badge]", // D1：全站 Synthetic / Demo Data 标记
  "[data-sidebar]",
  "nav [data-nav-link]",
];

/**
 * 手机档专属不变量（390×844）。
 *
 * 底部标签栏是手机上**唯一**的主导航，它不在就等于导航没了。
 */
export const MOBILE_MUST = [
  "[data-mobile-tabbar]",
  "[data-mobile-tabbar] [data-nav-link]",
];

/**
 * 手机档**不许可见**的选择器。
 *
 * 注意这是「可见性」而不是「存在性」：侧栏在窄屏是 `display:none` 却
 * **仍在 DOM 里**，所以 `GLOBAL_MUST` 里的 `[data-sidebar]` 拿
 * `querySelector` 判会假绿。手机档把它从 MUST 里摘掉，改到这里判可见。
 */
export const MOBILE_MUST_HIDDEN = ["[data-sidebar]"];
