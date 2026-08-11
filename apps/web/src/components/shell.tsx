"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { LOCALES, useI18n, type Locale } from "@/i18n";
import { useSession } from "@/app/providers";
import {
  NAV_GROUPS, NAV_ITEMS, homeFor, itemsFor, mobilePrimaryFor, visibleItemsFor,
} from "./nav";
import { MoreIcon, NavIcon } from "./nav-icons";
import { SyntheticBadge } from "./ui";

export function LocaleSwitch() {
  const { locale, setLocale, t } = useI18n();
  return (
    <div
      className="inline-flex gap-0.5 rounded-md border border-line bg-bg-sunk p-0.5"
      role="group"
      aria-label={t("chrome.language")}
    >
      {LOCALES.map((code: Locale) => {
        const active = code === locale;
        return (
          <button
            key={code}
            type="button"
            data-locale-option={code}
            aria-pressed={active}
            onClick={() => setLocale(code)}
            className="pressable t-meta rounded-sm px-2.5 py-1"
            style={{
              background: active ? "var(--accent-deep)" : "transparent",
              color: active ? "var(--accent-fg)" : "var(--fg-muted)",
              fontWeight: active ? 600 : 500,
            }}
          >
            {code === "zh-Hans" ? "简" : code === "zh-Hant" ? "繁" : "EN"}
          </button>
        );
      })}
    </div>
  );
}

/**
 * 登录学生的身份徽章。**只读，不能切换**——以谁登录就是谁，
 * 换学生必须退出登录重新验证（用户裁定 2026-07-31：切换器等于免验证看别人档案）。
 */
function PersonaBadge() {
  const { session } = useSession();
  const { t } = useI18n();
  if (session?.portal !== "student") return null;
  return (
    <span
      aria-label={t("chrome.persona")}
      data-persona-badge
      className="t-meta rounded-md border border-line bg-card px-2.5 py-1.5 text-fg-muted"
    >
      {session.studentId}
    </span>
  );
}

/**
 * R6-A：校方岗位徽章。**只读，不能切换**——以哪个岗位登录就是哪个岗位，
 * 换岗必须退出登录重新验证（与学生端同一裁定：切换器=免验证看别人的工作台）。
 */
function InstitutionRoleSwitch() {
  const { session } = useSession();
  const { t } = useI18n();
  if (session?.portal !== "institution") return null;
  return (
    <span
      aria-label={t("console.actingAs")}
      data-role-badge
      className="t-meta rounded-md border border-line bg-card px-2.5 py-1.5 text-fg-muted"
    >
      {t(`login.role.${session.role}` as Parameters<typeof t>[0])}
    </span>
  );
}

/** F1（2026-08-02 用户裁定）：demo 顶栏一键启停 Vertex Agent Engine。
 * 运行时按小时计费——这颗按钮的意义就是「演示前启动、演示完关闭」。
 * 任务在服务端跑（切页不中断）；环境不可控（云端容器无 adk）时按钮不出现。 */
function RuntimeToggle() {
  // 2026-08-04 用户裁定：**控制按钮整体撤除**——测试网站的用户不该有
  // 机会启停 Cloud Run 运行时；顶栏只留只读状态灯（GET 探测）。
  const { t } = useI18n();
  type Status = Awaited<ReturnType<typeof import("@/lib/api").api.agentRuntime>>;
  const [status, setStatus] = useState<Status | null>(null);
  useEffect(() => {
    let stop = false;
    async function poll() {
      try {
        const { api } = await import("@/lib/api");
        const next = await api.agentRuntime();
        if (!stop) setStatus(next);
      } catch {
        // 探测不可用就保持无灯——只读展示，无需向用户报错
      }
    }
    poll();
    const timer = setInterval(poll, 30000);
    return () => { stop = true; clearInterval(timer); };
  }, []);

  // unknown = 后端如实承认"本环境探测不到运行时"——灯不显示。
  // 2026-08-03 起云端探测走 Vertex REST 回退，线上通常能给出真值。
  if (!status || status.state === "unknown") return null;
  const running = status.state === "running";
  // 状态灯（2026-08-03 用户需求）：绿 = 引擎运行中 = 正在按小时计费；
  // 灰 = 已停止。
  return (
    <span
      data-runtime-light={status.state}
      title={t(running ? "runtime.light.running" : "runtime.light.stopped")}
      className="t-meta inline-flex items-center gap-1.5 text-fg-muted"
    >
      <span
        aria-hidden
        style={{
          width: 8, height: 8, borderRadius: 999,
          background: running ? "var(--color-moss-500)" : "var(--line-strong)",
          boxShadow: running ? "0 0 0 3px var(--color-moss-100)" : "none",
          animation: running ? "cp-pulse 1.6s ease-in-out infinite" : "none",
        }}
      />
      {t(running ? "runtime.light.on" : "runtime.light.off")}
    </span>
  );
}

/** 「睡眠-负荷平衡」预警弹窗（2026-08-02 用户裁定，全链零 LLM）。
 *
 * warning（14 天内 ≥10 个「睡眠<7h 且学习>11h」日）→ 温和提醒，可关闭
 * （按 qualifying 数记忆，不重复骚扰）；assessment（28 天内 ≥20 日）→
 * 引导完成 ISI+PSS-10，**完成后（last_assessment_at 落档）自动解除**；
 * 分流由既有 §16.8 链路接手（初级自动联系辅导员 / 高压引导预约咨询室）。
 * 在 /wellbeing 页不弹——学生正在那里填表。 */
function WellbeingNudge() {
  const { t } = useI18n();
  const { session } = useSession();
  const pathname = usePathname();
  type Esc = Awaited<ReturnType<typeof import("@/lib/api").api.wellbeingEscalation>>;
  const [esc, setEsc] = useState<Esc | null>(null);
  const [acked, setAcked] = useState(false);
  const studentId = session?.portal === "student" ? session.studentId : null;
  useEffect(() => {
    if (!studentId) return;
    let stop = false;
    import("@/lib/api").then(({ api }) =>
      api.wellbeingEscalation(studentId)
        .then((next) => { if (!stop) setEsc(next); })
        .catch(() => {}));
    return () => { stop = true; };
  }, [studentId, pathname]);

  if (!esc || esc.tier === "none" || pathname === "/wellbeing") return null;
  const ackKey = `campuspath.wellbeing.ack.${studentId}.${esc.qualifying_days_14}`;
  if (esc.tier === "warning") {
    if (acked || (typeof window !== "undefined" && localStorage.getItem(ackKey))) {
      return null;
    }
  }
  if (esc.tier === "assessment" && esc.last_assessment_at) return null;

  const assessment = esc.tier === "assessment";
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-5"
         data-wellbeing-nudge={esc.tier}
         style={{ background: "color-mix(in srgb, var(--fg) 30%, transparent)" }}>
      <div className="material-card w-full max-w-[460px] rounded-lg bg-card p-6">
        <div className="t-section text-fg">
          {t(assessment ? "wellbeing.nudge.assessTitle" : "wellbeing.nudge.title")}
        </div>
        <p className="t-body mt-2 text-fg-muted">
          {t(assessment ? "wellbeing.nudge.assessBody" : "wellbeing.nudge.body")
            .replace("{d14}", String(esc.qualifying_days_14))
            .replace("{d28}", String(esc.qualifying_days_28))}
        </p>
        <p className="t-micro mt-2 text-fg-faint">{t("wellbeing.nudge.basis")}</p>
        <div className="mt-4 flex items-center justify-end gap-2">
          {assessment ? (
            <Link href="/wellbeing" data-nudge-go
                  className="pressable btn btn-primary t-meta font-medium">
              {t("wellbeing.nudge.goAssess")}
            </Link>
          ) : (
            <>
              <Link href="/calendar" data-nudge-calendar
                    className="pressable btn btn-secondary t-meta">
                {t("wellbeing.nudge.goCalendar")}
              </Link>
              <button type="button" data-nudge-dismiss
                      className="pressable btn btn-primary t-meta font-medium"
                      onClick={() => {
                        localStorage.setItem(ackKey, "1");
                        setAcked(true);
                      }}>
                {t("wellbeing.nudge.dismiss")}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function LogoutButton() {
  const { session, logout } = useSession();
  const router = useRouter();
  const { t } = useI18n();
  if (!session) return null;
  return (
    <button
      type="button"
      data-logout
      onClick={() => {
        logout();
        router.replace("/login");
      }}
      className="pressable btn btn-ghost t-meta"
    >
      {t("auth.logout")}
    </button>
  );
}

function Sidebar() {
  const pathname = usePathname();
  const { t } = useI18n();
  const { session } = useSession();
  const reduce = useReducedMotion();

  if (!session) return null;
  const items = visibleItemsFor(session);

  return (
    <nav aria-label={t("nav.landmark.sidebar")} className="flex flex-col gap-6" data-sidebar>
      {NAV_GROUPS.map((groupKey) => {
        const groupItems = items.filter((i) => i.groupKey === groupKey);
        if (!groupItems.length) return null;
        return (
          <div key={groupKey}>
            <div className="t-micro mb-1.5 px-2 text-fg-faint">{t(groupKey)}</div>
            <ul className="flex flex-col gap-0.5">
              {groupItems.map((item) => {
                const active = pathname === item.href;
                return (
                  <li key={item.href} className="relative">
                    {active && (
                      // 选中态的位移用 layoutId 做共享过渡：切页时它是**滑过去**的，
                      // 不是在两处各自淡入淡出——位置关系因此始终连续。
                      <motion.span
                        layoutId="nav-active"
                        className="absolute inset-0 rounded-md"
                        style={{ background: "var(--accent-soft)" }}
                        transition={
                          reduce
                            ? { duration: 0.12 }
                            : { type: "spring", bounce: 0, duration: 0.35 }
                        }
                      />
                    )}
                    <Link
                      href={item.href}
                      data-nav-link={item.href}
                      aria-current={active ? "page" : undefined}
                      className="pressable relative flex items-center gap-2 rounded-md px-2 py-1.5"
                      style={{
                        color: active ? "var(--accent-deep)" : "var(--fg-muted)",
                        fontWeight: active ? 600 : 450,
                        fontSize: "0.875rem",
                      }}
                    >
                      <span
                        aria-hidden
                        className="h-1 w-1 shrink-0 rounded-full"
                        style={{
                          background: active ? "var(--accent)" : "var(--line-strong)",
                        }}
                      />
                      {t(item.labelKey)}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
    </nav>
  );
}

/**
 * 手机底部标签栏（<lg）。取代旧的「横向滚动文字药丸带」——那条带子把
 * 10+ 项全排一行，在 390px 视口里排到 858px，是用户点名的
 * 「按钮溢出界面外面」。
 *
 * 结构上不可能再溢出：**格子数固定**（`MOBILE_PRIMARY_SLOTS` 个主入口 + 「更多」，
 * 当前 5+1=6 格），每格 `flex-1 min-w-0` 均分视口宽度，标签用短名并 `truncate`。
 * 视口再窄只会让每格变窄，不会把某一格挤出屏幕——实测 390px 下每格 65px、
 * 简体与英文标签均不截断、命中区 56×65px。
 */
function MobileTabBar({ onMore, moreOpen }: { onMore: () => void; moreOpen: boolean }) {
  const pathname = usePathname();
  const { t } = useI18n();
  const { session } = useSession();
  if (!session) return null;
  const primary = mobilePrimaryFor(session);
  // 当前页不属于任何主入口时，「更多」代为点亮——否则深页里所有格子全灭，
  // 用户失去「我在哪」的锚点（§9 nav-state-active）
  const onPrimary = primary.some((i) => pathname === i.href);

  return (
    <nav
      aria-label={t("nav.landmark.primary")}
      data-mobile-tabbar
      className="material-chrome fixed inset-x-0 bottom-0 z-40 border-t border-line lg:hidden"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
    >
      <ul className="flex items-stretch">
        {primary.map((item) => {
          const active = pathname === item.href;
          return (
            <li key={item.href} className="min-w-0 flex-1">
              <Link
                href={item.href}
                data-nav-link={item.href}
                aria-current={active ? "page" : undefined}
                className="pressable flex min-h-[56px] flex-col items-center justify-center gap-0.5 px-1 py-1.5"
                style={{ color: active ? "var(--accent-deep)" : "var(--fg-muted)" }}
              >
                <NavIcon href={item.href} className="h-[22px] w-[22px] shrink-0" />
                <span
                  className="w-full truncate text-center"
                  style={{ fontSize: "0.6875rem", lineHeight: 1.2,
                           fontWeight: active ? 600 : 500 }}
                >
                  {t(item.mobileLabelKey ?? item.labelKey)}
                </span>
              </Link>
            </li>
          );
        })}
        <li className="min-w-0 flex-1">
          <button
            type="button"
            data-mobile-more
            aria-expanded={moreOpen}
            onClick={onMore}
            className="pressable flex min-h-[56px] w-full flex-col items-center justify-center gap-0.5 px-1 py-1.5"
            style={{ color: !onPrimary || moreOpen ? "var(--accent-deep)" : "var(--fg-muted)" }}
          >
            <MoreIcon className="h-[22px] w-[22px] shrink-0" />
            <span className="w-full truncate text-center"
                  style={{ fontSize: "0.6875rem", lineHeight: 1.2,
                           fontWeight: !onPrimary || moreOpen ? 600 : 500 }}>
              {t("nav.more")}
            </span>
          </button>
        </li>
      </ul>
    </nav>
  );
}

/**
 * 「更多」底部面板：该门户的**全部**导航项，按侧栏同一套分组。
 * 清单仍然只从 `nav.ts` 取——手机端不另维护一份，否则「少做了一页」
 * 会只在一端被发现。
 */
function MoreSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const pathname = usePathname();
  const { t } = useI18n();
  const { session } = useSession();
  const reduce = useReducedMotion();

  // 面板打开时锁背景滚动；Esc 关闭（§9 modal-escape）
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);

  if (!open || !session) return null;
  const items = visibleItemsFor(session);

  return (
    <div className="fixed inset-0 z-50 flex flex-col justify-end lg:hidden"
         data-more-sheet role="dialog" aria-modal="true"
         aria-label={t("nav.more")}>
      {/* 遮罩要足够暗才能把前景隔离出来（§Light/Dark scrim 40–60%） */}
      <button type="button" aria-label={t("chrome.close")} onClick={onClose}
              className="absolute inset-0" style={{ background: "rgb(0 0 0 / 0.45)" }} />
      <motion.div
        initial={reduce ? false : { y: 24, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={reduce ? { duration: 0.12 } : { type: "spring", bounce: 0, duration: 0.28 }}
        className="material-card relative max-h-[72dvh] overflow-y-auto rounded-t-lg bg-card px-4 pt-3"
        style={{ paddingBottom: "calc(1rem + env(safe-area-inset-bottom))" }}
      >
        {/* 抓握条：告诉用户这是可以往下推走的面板 */}
        <div aria-hidden className="mx-auto mb-3 h-1 w-10 rounded-full"
             style={{ background: "var(--line-strong)" }} />
        {NAV_GROUPS.map((groupKey) => {
          const groupItems = items.filter((i) => i.groupKey === groupKey);
          if (!groupItems.length) return null;
          return (
            <div key={groupKey} className="mb-3">
              <div className="t-micro mb-1.5 text-fg-faint">{t(groupKey)}</div>
              <ul className="flex flex-col gap-0.5">
                {groupItems.map((item) => {
                  const active = pathname === item.href;
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        data-nav-link={item.href}
                        data-more-link={item.href}
                        aria-current={active ? "page" : undefined}
                        onClick={onClose}
                        className="pressable flex min-h-[44px] items-center gap-2.5 rounded-md px-2"
                        style={{
                          background: active ? "var(--accent-soft)" : "transparent",
                          color: active ? "var(--accent-deep)" : "var(--fg)",
                          fontWeight: active ? 600 : 450,
                          fontSize: "0.9375rem",
                        }}
                      >
                        <NavIcon href={item.href} className="h-[20px] w-[20px] shrink-0 opacity-70" />
                        <span className="min-w-0 truncate">{t(item.labelKey)}</span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </motion.div>
    </div>
  );
}

/**
 * 门户守卫。三条规则，全部在跳转层面强制（服务端 RBAC 是第二道，独立成立）：
 *
 * 1. 未登录 → `/login`；
 * 2. 会话访问不属于自己的页面 → 送回**自己身份**的落地页。
 *    R7-A：这不只隔离两个门户，也隔离校方内部的岗位——advisor 直开
 *    /publisher 或 /console，对这个会话来说等于页面不存在；
 * 3. 已登录访问 `/login` → 送回自己身份的落地页。
 */
function usePortalGuard(): "checking" | "login" | "app" {
  const { session, ready } = useSession();
  const pathname = usePathname();
  const router = useRouter();

  const onLogin = pathname === "/login";
  const guarded = NAV_ITEMS.find(
    (item) => pathname === item.href || pathname.startsWith(`${item.href}/`),
  );
  const wrongDesk =
    session !== null &&
    guarded !== undefined &&
    !itemsFor(session).some((item) => item.href === guarded.href);

  useEffect(() => {
    if (!ready) return;
    if (session === null && !onLogin) router.replace("/login");
    else if (session !== null && (onLogin || wrongDesk)) {
      router.replace(homeFor(session));
    }
  }, [ready, session, onLogin, wrongDesk, router]);

  if (!ready) return "checking";
  if (onLogin) return session === null ? "login" : "checking";
  if (session === null || wrongDesk) return "checking";
  return "app";
}

export function Shell({ children }: { children: React.ReactNode }) {
  const { t } = useI18n();
  const { session } = useSession();
  const phase = usePortalGuard();
  const [moreOpen, setMoreOpen] = useState(false);
  const [chromeOpen, setChromeOpen] = useState(false);

  // 登录页不带导航壳——门户的导航只属于登录后的那个门户
  if (phase === "login") return <>{children}</>;
  if (phase === "checking") return <div className="min-h-dvh" data-guard-checking />;

  return (
    <div className="min-h-dvh">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-card focus:px-3 focus:py-2"
      >
        {t("chrome.skipToContent")}
      </a>

      <header
        className="material-chrome sticky top-0 z-40 border-b border-line"
        style={{ paddingTop: "env(safe-area-inset-top)" }}
      >
        <div className="mx-auto flex max-w-[1240px] items-center gap-3 px-4 py-2.5 sm:px-5 sm:py-3">
          <Link
            href={session ? homeFor(session) : "/login"}
            className="flex min-w-0 items-baseline gap-2"
          >
            <span
              className="t-title"
              style={{ color: "var(--accent)", letterSpacing: "-0.03em" }}
            >
              {t("app.name")}
            </span>
            <span className="t-meta hidden text-fg-faint sm:inline" data-portal-tag>
              {session?.portal === "institution"
                ? t("auth.portal.institution")
                : t("app.tagline")}
            </span>
          </Link>

          {/* 桌面：六个 chrome 控件平铺。
              窄屏：只留语言切换 + 一个「⋯」——六个控件靠 flex-wrap 硬挤
              会在手机上折成三四行、吃掉半屏（§9 overflow-menu）。 */}
          <div className="ms-auto hidden flex-wrap items-center gap-2 lg:flex">
            <SyntheticBadge />
            <InstitutionRoleSwitch />
            <PersonaBadge />
            <LocaleSwitch />
            <RuntimeToggle />
            <LogoutButton />
          </div>
          <div className="ms-auto flex items-center gap-1.5 lg:hidden">
            <LocaleSwitch />
            <button
              type="button"
              data-chrome-menu
              aria-expanded={chromeOpen}
              aria-label={t("chrome.more")}
              onClick={() => setChromeOpen((v) => !v)}
              className="pressable btn btn-secondary"
              style={{ minWidth: 44, minHeight: 44, padding: 0 }}
            >
              <span aria-hidden style={{ fontSize: "1.05rem", lineHeight: 1 }}>⋯</span>
            </button>
          </div>
        </div>

        {/* 窄屏的 chrome 抽屉：徽章与登出收在这里，默认不占首屏 */}
        {chromeOpen && (
          <div
            data-chrome-panel
            className="flex flex-wrap items-center gap-2 border-t border-line px-4 py-2.5 lg:hidden"
          >
            <SyntheticBadge />
            <InstitutionRoleSwitch />
            <PersonaBadge />
            <RuntimeToggle />
            <LogoutButton />
          </div>
        )}
      </header>

      <div className="mx-auto flex max-w-[1240px] gap-8 px-4 py-6 sm:px-5 sm:py-8">
        <aside className="sticky top-[74px] hidden h-fit w-[210px] shrink-0 lg:block">
          <Sidebar />
        </aside>
        {/* 底部标签栏是 fixed 的，主内容必须自己留出等高的下边距，
            否则最后一屏内容会被压在栏下面（§5 fixed-element-offset）。
            桌面无此栏，`lg:pb-0` 收回，跨页对齐门禁的基线因此不受影响。 */}
        <main
          id="main"
          className="min-w-0 flex-1 pb-[calc(56px+env(safe-area-inset-bottom)+0.5rem)] lg:pb-0"
        >
          {children}
        </main>
      </div>

      {session?.portal === "student" && <WellbeingNudge />}

      {/* 窄屏主导航：固定 5 格的底部标签栏 + 「更多」面板。
          清单仍然只从 nav.ts 取，手机端不另维护一份。 */}
      <MobileTabBar moreOpen={moreOpen} onMore={() => setMoreOpen((v) => !v)} />
      <MoreSheet open={moreOpen} onClose={() => setMoreOpen(false)} />
    </div>
  );
}
