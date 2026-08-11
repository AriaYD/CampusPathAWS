import type { MessageKey } from "@/i18n";

/**
 * D1 的 14 个页面。**这份数组是唯一出处**——导航、面包屑、
 * 以及"页面完整性"的浏览器实测脚本都从这里取，
 * 所以"少做了一页"不可能只在某一处被发现。
 *
 * 导航项按其**内容**命名（"Pathway Timeline"、"Memory Center"），
 * 不用 "Home" 这类伞状词：具体的名字才能让人预判点进去看到什么。
 */
export type NavItem = {
  href: string;
  labelKey: MessageKey;
  groupKey: MessageKey;
  /** 归属门户。学生端只见学生项，校方端只见校方项——**互不可见**。 */
  portal: "student" | "institution";
  /** 不出现在导航里，但门户守卫仍认它（并入他页后保留深链接）。 */
  hidden?: boolean;
  /**
   * R7-A：校方项只属于列出的岗位。以哪个岗位登录就只见（也只进得去）
   * 自己职责的工作台——advisor 连 Publisher 投稿台的导航项都看不到。
   * 未列出 = 该门户所有身份可见（学生项不用填）。
   */
  roles?: readonly string[];
  /**
   * 手机底部标签栏的主入口位次（1–5）。最后一格固定是「更多」。
   *
   * **上限是硬的**：`MOBILE_PRIMARY_SLOTS` 决定最多几个主入口，
   * 多标了也只取前 N 个。这是「按钮不许溢出界面」在数据层的保证——
   * 旧实现把 10+ 项全排一行靠横向滚动，在 390px 视口里排到了 858px，
   * 正是用户点名的那个毛病。格子数一旦固定，布局再怎么变也排不出第 7 格。
   *
   * 未标注的项只在「更多」面板与桌面侧栏出现；**清单仍然只有这一份**。
   */
  mobilePrimary?: 1 | 2 | 3 | 4 | 5;
  /**
   * 底部标签栏专用短名。**必须两到三个字**。
   *
   * 侧栏的名字是按「点进去看到什么」起的（"我的成长档案"、"顾问预约/规划与行动"），
   * 那是对的——侧栏有 210px。但标签栏一格只有约 78px（390÷5），
   * 长名会被截成「我的成长…」，等于没有标签。
   * 截断不是解法，换一个短名才是（§6 truncation-strategy）。
   */
  mobileLabelKey?: MessageKey;
};

export const NAV_ITEMS: readonly NavItem[] = [
  { href: "/onboarding", labelKey: "page.onboarding", groupKey: "nav.group.start", portal: "student" },

  { href: "/profile", labelKey: "page.profile", groupKey: "nav.group.me", portal: "student", mobilePrimary: 1, mobileLabelKey: "nav.tab.profile" },
  // 用户裁定（2026-08-01）：成长动态跟踪讲的是"我"的证据链，归「我」分组，
  // 紧跟成长档案——档案是存量、跟踪是增量，读序自然
  { href: "/gaps", labelKey: "page.gaps", groupKey: "nav.group.me", portal: "student" },
  { href: "/reflections", labelKey: "page.reflections", groupKey: "nav.group.me", portal: "student" },
  { href: "/memory", labelKey: "page.memory", groupKey: "nav.group.me", portal: "student" },

  // 第三轮调整（2026-07-31 用户裁定 I）：
  // 选课与学位规划 + 课外活动规划（原路径时间线）合并为 /planner 的同页分页；
  // 行动中心恢复为独立导航项（从时间线分页拎出）；身心容量仍并入日历。
  // /timeline 与 /wellbeing 的路由保留（深链接不断），只是不出现在导航里。
  { href: "/goals", labelKey: "page.goals", groupKey: "nav.group.direction", portal: "student", mobilePrimary: 2, mobileLabelKey: "nav.tab.goals" },
  // 导航名点明双重身份（用户裁定 2026-08-01）；页内分页标签仍各自用
  // page.calendar / page.wellbeing，不动
  { href: "/calendar", labelKey: "nav.calendarWellbeing", groupKey: "nav.group.direction", portal: "student", mobilePrimary: 5, mobileLabelKey: "nav.tab.calendar" },
  { href: "/actions", labelKey: "page.actions", groupKey: "nav.group.direction", portal: "student", mobilePrimary: 4, mobileLabelKey: "nav.tab.actions" },
  { href: "/planner", labelKey: "page.planner", groupKey: "nav.group.direction", portal: "student", hidden: true },
  { href: "/timeline", labelKey: "page.timeline", groupKey: "nav.group.direction", portal: "student", hidden: true },
  { href: "/wellbeing", labelKey: "page.wellbeing", groupKey: "nav.group.direction", portal: "student", hidden: true },

  { href: "/for-you", labelKey: "page.forYou", groupKey: "nav.group.discover", portal: "student", mobilePrimary: 3, mobileLabelKey: "nav.tab.forYou" },
  { href: "/checkin", labelKey: "checkin.title", groupKey: "nav.group.discover", portal: "student", hidden: true },
  { href: "/square", labelKey: "page.square", groupKey: "nav.group.discover", portal: "student" },

  { href: "/settings", labelKey: "page.settings", groupKey: "nav.group.system", portal: "student" },

  // 校方门户。曾与学生端同一份导航"按角色路由"（Plan §165 的旧决定）——
  // 用户裁定推翻：两端必须各自登录、界面互不混排。D5 的隔离验证不受影响：
  // /console 里仍以校方身份对学生禁区端点做主动探测，全部 403 才算通过。
  // R7-A：一岗一台。旧的细分角色（reviewer/curator/connector_admin）
  // 归并到 Career Center 控制台；wellbeing_coordinator 是心理咨询室部门，
  // 有自己的工作台（outreach 队列），不与 Career Center 混排。
  { href: "/publisher", labelKey: "publisher.title", groupKey: "nav.group.institution", portal: "institution",
    roles: ["publisher"] },
  { href: "/console", labelKey: "console.title", groupKey: "nav.group.institution", portal: "institution",
    roles: ["career_center_admin", "reviewer", "curator", "connector_admin"] },
  // 用户裁定（2026-08-01）：审核队列独立成页；广场总览给管理端只读监看
  { href: "/review", labelKey: "console.reviewQueue", groupKey: "nav.group.institution", portal: "institution",
    roles: ["career_center_admin", "reviewer"] },
  { href: "/plaza-admin", labelKey: "console.plaza.title", groupKey: "nav.group.institution", portal: "institution",
    roles: ["career_center_admin", "curator"] },
  { href: "/insights", labelKey: "insights.title", groupKey: "nav.group.institution", portal: "institution",
    roles: ["career_center_admin", "curator"] },
  { href: "/quality-reports", labelKey: "reports.title", groupKey: "nav.group.institution", portal: "institution",
    roles: ["career_center_admin"] },
  { href: "/wellbeing-desk", labelKey: "wellbeingDesk.title", groupKey: "nav.group.institution", portal: "institution",
    roles: ["wellbeing_coordinator"] },
  { href: "/advisor-desk", labelKey: "advisor.deskTitle", groupKey: "nav.group.institution", portal: "institution",
    roles: ["advisor"] },
] as const;

export type NavSession =
  | { portal: "student" }
  | { portal: "institution"; role: string };

export function itemsFor(session: NavSession): NavItem[] {
  return NAV_ITEMS.filter(
    (item) =>
      item.portal === session.portal &&
      (item.roles === undefined ||
        session.portal !== "institution" ||
        item.roles.includes(session.role)),
  );
}

/** 导航栏显示用：过滤掉并入他页的隐藏项。守卫请用 itemsFor（含隐藏项）。 */
export function visibleItemsFor(session: NavSession): NavItem[] {
  return itemsFor(session).filter((item) => !item.hidden);
}

/**
 * 底部标签栏的主入口格数上限。加上固定的「更多」格，总格数 = 本值 + 1。
 *
 * 5 是**用户 2026-08-10 的产品裁定**：目标工作室是核心页，必须常驻第 2 格，
 * 且不牺牲其余四个。通用建议是底部导航 ≤5 项（ui-ux-pro-max §9
 * `bottom-nav-limit`），这里是 6 格——**取的是实测而不是教条**：
 * 390px 视口下 6 格各 65px，两种语言的标签都能整词放下、无截断、
 * 命中区仍 ≥56px 高。若将来再加第 7 格，65→56px，英文标签开始截断，
 * 那时必须改成把低频项挪进「更多」，而不是继续加格。
 */
export const MOBILE_PRIMARY_SLOTS = 5;

/**
 * 手机底部标签栏的主入口。**最多 `MOBILE_PRIMARY_SLOTS` 个，超出的进「更多」面板**。
 *
 * 学生端按 `mobilePrimary` 显式排序（档案 / 目标 / 推荐 / 规划 / 日历）；
 * 校方端各岗位可见项本就少（多数 1–4 个），按侧栏顺序取前几个即可。
 */
export function mobilePrimaryFor(session: NavSession): NavItem[] {
  const visible = visibleItemsFor(session);
  const tagged = visible
    .filter((i) => i.mobilePrimary !== undefined)
    .sort((a, b) => (a.mobilePrimary ?? 9) - (b.mobilePrimary ?? 9));
  return (tagged.length ? tagged : visible).slice(0, MOBILE_PRIMARY_SLOTS);
}

/**
 * 落地页跟着身份走：学生进档案；校方进自己岗位的第一个（通常唯一的）
 * 工作台。没有任何可见项的身份回登录页——不该发生，发生了也别死循环。
 */
export function homeFor(session: NavSession): string {
  if (session.portal === "student") return "/profile";
  return visibleItemsFor(session)[0]?.href ?? "/login";
}

export const NAV_GROUPS: readonly MessageKey[] = [
  "nav.group.start",
  "nav.group.me",
  "nav.group.direction",
  "nav.group.plan",
  "nav.group.discover",
  "nav.group.system",
  "nav.group.institution",
] as const;
