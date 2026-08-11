"use client";

/**
 * 全站共用的视觉原语。
 *
 * 两个"签名元素"在这里定义，全站复用，别处不再自造：
 *
 * * :func:`TriState` —— 三值指示器。UNKNOWN 用**斜纹**，既不是绿也不是红。
 *   产品的整个论证建立在"解析不出来 ≠ 你不合格"上，配色必须承认第三种状态。
 * * :func:`CredentialChip` —— 凭据票根。任何来自 Rules 的结论都挂着它，
 *   带真实的 validation_id。看得见的审计链比一句"我们很严谨"有用。
 */

import { motion, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useI18n, type MessageKey } from "@/i18n";

/* ------------------------------------------------------------------ */
/* 布局                                                                */
/* ------------------------------------------------------------------ */

export function PageHeader({
  titleKey,
  leadKey,
  children,
}: {
  titleKey: MessageKey;
  leadKey?: MessageKey;
  children?: ReactNode;
}) {
  const { t } = useI18n();
  return (
    <header className="mb-8">
      <h1 className="t-display text-fg">{t(titleKey)}</h1>
      {leadKey && (
        <p className="t-body mt-3 max-w-[60ch] text-fg-muted">{t(leadKey)}</p>
      )}
      {children && <div className="mt-5">{children}</div>}
    </header>
  );
}

/**
 * ``...rest`` 是有意的：不透传的话 `<Card data-x="…">` 会**静默丢掉**那个属性，
 * 而浏览器实测正是靠 `data-*` 断言的——一条断言查不到东西，
 * 分不清是"页面坏了"还是"属性被组件吃了"。实测里踩过一次。
 */
export function Card({
  children,
  className = "",
  as: Tag = "section",
  ...rest
}: {
  children: ReactNode;
  className?: string;
  as?: "section" | "article" | "div" | "li";
} & Record<string, unknown>) {
  return (
    <Tag
      {...rest}
      className={`rounded-lg border border-line bg-card p-5 ${className}`}
      style={{ boxShadow: "var(--shadow-card)" }}
    >
      {children}
    </Tag>
  );
}

export function SectionTitle({ children }: { children: ReactNode }) {
  return <h2 className="t-section mb-3 text-fg">{children}</h2>;
}

export function Grid({
  children,
  min = 260,
}: {
  children: ReactNode;
  min?: number;
}) {
  return (
    <div
      className="grid gap-4"
      style={{ gridTemplateColumns: `repeat(auto-fill, minmax(${min}px, 1fr))` }}
    >
      {children}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 签名元素 1：三值状态                                                 */
/* ------------------------------------------------------------------ */

export type TriValue = "met" | "not_met" | "unknown";

const TRI_KEY: Record<TriValue, MessageKey> = {
  met: "state.met",
  not_met: "state.notMet",
  unknown: "state.unknown",
};

export function TriState({ value, label }: { value: TriValue; label?: string }) {
  const { t } = useI18n();
  const text = label ?? t(TRI_KEY[value]);
  const shared =
    "inline-flex items-center gap-1.5 rounded-sm border px-2 py-1 t-meta font-medium";

  if (value === "unknown") {
    return (
      <span
        className={`${shared} hatch-unknown`}
        style={{ borderColor: "var(--hatch)", color: "var(--hatch-ink)" }}
        title={t("state.unknown.explain")}
        data-tri="unknown"
      >
        <span
          aria-hidden
          className="h-2 w-2 rounded-full border-[1.5px]"
          style={{ borderColor: "var(--hatch)" }}
        />
        {text}
      </span>
    );
  }
  const met = value === "met";
  return (
    <span
      className={shared}
      data-tri={value}
      style={{
        borderColor: met ? "var(--color-moss-500)" : "var(--color-clay-500)",
        color: met ? "var(--color-moss-600)" : "var(--color-clay-600)",
        background: met ? "var(--color-moss-100)" : "var(--color-clay-100)",
      }}
    >
      <span
        aria-hidden
        className="h-2 w-2 rounded-full"
        style={{
          background: met ? "var(--color-moss-500)" : "var(--color-clay-500)",
        }}
      />
      {text}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/* 签名元素 2：凭据票根                                                 */
/* ------------------------------------------------------------------ */

export function CredentialChip({ validationId }: { validationId?: string | null }) {
  const { t } = useI18n();
  if (!validationId) {
    return (
      <span className="t-mono text-fg-faint" data-credential="none">
        {t("credential.none")}
      </span>
    );
  }
  return (
    <span
      className="credential-chip inline-flex items-center gap-1.5 rounded-sm px-2 py-[3px]"
      style={{
        border: "1px dashed var(--hatch)",
        color: "var(--hatch-ink)",
        background: "color-mix(in srgb, var(--hatch) 8%, transparent)",
      }}
      title={t("credential.explain")}
      data-credential={validationId}
    >
      <span className="t-micro" style={{ letterSpacing: "0.08em" }}>
        {t("credential.label")}
      </span>
      <code className="t-mono">{validationId.slice(0, 12)}…</code>
    </span>
  );
}

/* ------------------------------------------------------------------ */
/* 状态                                                                */
/* ------------------------------------------------------------------ */

export function Loading() {
  const { t } = useI18n();
  return (
    <p className="t-meta text-fg-faint" role="status" data-state="loading">
      {t("app.loading")}
    </p>
  );
}

export function Empty({ messageKey }: { messageKey?: MessageKey }) {
  const { t } = useI18n();
  return (
    <p className="t-meta text-fg-faint" data-state="empty">
      {t(messageKey ?? "app.empty")}
    </p>
  );
}

/**
 * 错误态。**503 与 404 分开说**：
 * 503 = 这条路做完了但依赖不可用；404 = 这个学生现在真的没有这个东西。
 * 都写成"加载失败"会让人以为前端坏了。
 */
export function Failure({
  error,
  emptyKey,
  onRetry,
}: {
  error: Error & { isUnavailable?: boolean; isMissing?: boolean; status?: number };
  emptyKey?: MessageKey;
  onRetry?: () => void;
}) {
  const { t } = useI18n();
  if (error.isMissing) return <Empty messageKey={emptyKey} />;
  return (
    <div
      className="rounded-md border border-line bg-bg-sunk p-4"
      role="alert"
      data-state={error.isUnavailable ? "unavailable" : "error"}
    >
      <p className="t-meta text-fg-muted">
        {error.isUnavailable ? t("app.offline") : t("app.error")}
      </p>
      <p className="t-mono mt-1 text-fg-faint">{error.message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="pressable btn btn-secondary t-meta mt-3"
        >
          {t("app.retry")}
        </button>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 数据条与数值                                                         */
/* ------------------------------------------------------------------ */

export function Metric({
  label,
  value,
  unit,
  tone = "default",
}: {
  label: string;
  value: string | number;
  unit?: string;
  tone?: "default" | "warn" | "good";
}) {
  const color =
    tone === "warn"
      ? "var(--color-clay-600)"
      : tone === "good"
        ? "var(--color-moss-600)"
        : "var(--fg)";
  return (
    // min-w-0：不加它，flex 子项的最小宽度是内容宽度，父容器再怎么收缩都没用——
    // 2026-08-10 用户报障的英文档案卡溢出就是这条（"DEVELOPMENT MODE /
    // Exploration" 比中文的"发展模式/探索中"宽得多，卡片被顶穿）。
    <div className="min-w-0">
      <div className="t-micro text-fg-faint">{label}</div>
      <div className="mt-1 flex items-baseline gap-1">
        <span
          className="tabular-nums break-words"
          style={{ color, fontSize: "1.5rem", fontWeight: 700, letterSpacing: "-0.02em", fontFamily: "var(--font-display, ui-sans-serif), var(--font-sans)" }}
        >
          {value}
        </span>
        {unit && <span className="t-meta text-fg-faint">{unit}</span>}
      </div>
    </div>
  );
}

/** 水平占比条。宽度用 spring 过渡，可被随时打断（ui-ux-pro-max interruptible）。 */
export function Bar({
  ratio,
  tone = "accent",
}: {
  ratio: number;
  tone?: "accent" | "warn" | "hatch";
}) {
  const reduce = useReducedMotion();
  const clamped = Math.max(0, Math.min(1, ratio));
  const background =
    tone === "warn"
      ? "var(--color-clay-500)"
      : tone === "hatch"
        ? "var(--hatch)"
        : "var(--accent)";
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-bg-sunk">
      <motion.div
        className="h-full rounded-full"
        style={{ background }}
        initial={{ width: 0 }}
        animate={{ width: `${clamped * 100}%` }}
        transition={
          reduce
            ? { duration: 0.12 }
            : { type: "spring", bounce: 0, duration: 0.4 }
        }
      />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 开关与分段控件                                                       */
/* ------------------------------------------------------------------ */

export function Toggle({
  checked,
  onChange,
  labelledBy,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  labelledBy?: string;
}) {
  const reduce = useReducedMotion();
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-labelledby={labelledBy}
      onClick={() => onChange(!checked)}
      // 26px 的药丸是设计尺寸，撑到 44 就不是这个开关了；命中区改由
      // `[data-toggle-switch]::after` 向外扩（globals.css 的 coarse 段）。
      data-tap-exempt
      data-toggle-switch
      className="pressable relative h-[26px] w-[46px] shrink-0 rounded-full border"
      style={{
        background: checked ? "var(--accent)" : "var(--bg-sunk)",
        borderColor: checked ? "var(--accent)" : "var(--line-strong)",
      }}
    >
      <motion.span
        className="absolute top-[2px] block h-[20px] w-[20px] rounded-full bg-white"
        style={{ boxShadow: "0 1px 3px rgb(0 0 0 / 0.3)" }}
        animate={{ x: checked ? 22 : 2 }}
        transition={
          reduce ? { duration: 0.12 } : { type: "spring", bounce: 0.2, duration: 0.3 }
        }
      />
    </button>
  );
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  ariaLabel,
}: {
  options: readonly { value: T; label: string }[];
  value: T;
  onChange: (next: T) => void;
  ariaLabel: string;
}) {
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className="inline-flex gap-0.5 rounded-md border border-line bg-bg-sunk p-0.5"
    >
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(option.value)}
            className="pressable t-meta relative rounded-sm px-3 py-1.5"
            style={{
              color: active ? "var(--accent-fg)" : "var(--fg-muted)",
              background: active ? "var(--accent-deep)" : "transparent",
              fontWeight: active ? 600 : 500,
            }}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 抽屉                                                                */
/* ------------------------------------------------------------------ */

/**
 * 窄屏判定。**必须是状态而不是一次性读取**：视口会转向、会被开发者工具改，
 * 读一次就永远停在那一档。SSR 首帧当作宽屏（桌面是既有形态，
 * 手机上多一次 effect 后的切换比服务端猜错要安全）。
 */
export function useIsNarrow(query = "(max-width: 1023px)") {
  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const sync = () => setNarrow(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, [query]);
  return narrow;
}

/**
 * 侧滑面板。进出**走同一条路径**（ui-ux-pro-max continuity/modal-motion），
 * 材质是 blur + scale 一起动，读起来像一层真的玻璃到位，而不是简单淡入。
 *
 * **窄屏改底部工作表**（2026-08-11 P6）。理由不是"手机流行这样"：
 * 440px 的右侧抽屉在 390px 视口里等于整屏覆盖，而它从右侧滑入、
 * 顶到 `inset-y-0`——顶栏的人设徽标会压住抽屉标题的一角（实测），
 * 且拇指够不到顶部的关闭区。底部工作表从拇指所在的一侧升起，
 * 留出顶部 15% 让人看得见"下面还有原来的页面"（§7 modal-motion 的空间连续性）。
 */
export function Drawer({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}) {
  const reduce = useReducedMotion();
  const narrow = useIsNarrow();
  const panelRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    panelRef.current?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50" data-drawer="open">
      <motion.button
        type="button"
        aria-label={title}
        onClick={onClose}
        className="absolute inset-0 bg-black/45"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: reduce ? 0.12 : 0.22 }}
      />
      <motion.div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        data-drawer-form={narrow ? "sheet" : "side"}
        className={
          narrow
            ? "material-modal absolute inset-x-0 bottom-0 max-h-[85dvh] overflow-y-auto rounded-t-lg border-t border-line px-5 pt-3"
            : "material-modal absolute inset-y-0 right-0 w-full max-w-[440px] overflow-y-auto rounded-l-lg border-l border-line p-6"
        }
        // 底部工作表要给home indicator留位，否则最后一个按钮压在手势条下面
        style={narrow
          ? { paddingBottom: "calc(1.25rem + env(safe-area-inset-bottom))" }
          : undefined}
        initial={reduce ? { opacity: 0 }
          : narrow ? { y: 40, opacity: 0 } : { x: 32, opacity: 0, scale: 0.99 }}
        animate={reduce ? { opacity: 1 }
          : narrow ? { y: 0, opacity: 1 } : { x: 0, opacity: 1, scale: 1 }}
        transition={
          reduce ? { duration: 0.12 } : { type: "spring", bounce: 0, duration: 0.34 }
        }
      >
        {/* 抓手：告诉人这层是可以被推下去的（也顺带把标题从屏幕最上沿挪开）。
            纯视觉，交互仍靠背景点击与 Esc——手势关闭在 iOS Safari 上会与
            页面回弹打架，不值当为它引一套拖拽状态机。 */}
        {narrow && (
          <div aria-hidden className="mx-auto mb-3 h-1 w-10 rounded-full"
               style={{ background: "var(--line-strong)" }} />
        )}
        {children}
      </motion.div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 合成数据标记（D1 要求全站可见）                                       */
/* ------------------------------------------------------------------ */

export function SyntheticBadge({ full = false }: { full?: boolean }) {
  const { t } = useI18n();
  const [expanded, setExpanded] = useState(false);
  return (
    <div data-synthetic-badge className={full ? "block w-full" : "inline-block"}>
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        className="pressable t-micro inline-flex items-center gap-1.5 rounded-full px-2.5 py-1"
        style={{
          border: "1px solid var(--hatch)",
          color: "var(--hatch-ink)",
          background: "color-mix(in srgb, var(--hatch) 10%, transparent)",
        }}
      >
        <span aria-hidden className="hatch-unknown h-2.5 w-2.5 rounded-[2px] border" />
        {t("app.synthetic")}
      </button>
      {(expanded || full) && (
        /* 用户裁定 2026-08-02：说明分行排版、宽度与下方模块自适应对齐
           （不再截 46ch；父容器改 block 让宽度跟随页面栏宽）；
           真实源逐条编号，尾注单独一行 */
        <div className="t-meta mt-2 w-full text-fg-faint" data-synthetic-detail>
          <p>{t("app.syntheticFull")}</p>
          <ol className="mt-1.5 flex list-none flex-col gap-1 ps-0">
            {(["1", "2", "3", "4"] as const).map((n) => (
              <li key={n} className="flex gap-1.5">
                <span aria-hidden>
                  {{ "1": "①", "2": "②", "3": "③", "4": "④" }[n]}
                </span>
                <span className="min-w-0">
                  {t(`app.realSource.${n}` as Parameters<typeof t>[0])}
                </span>
              </li>
            ))}
          </ol>
          <p className="mt-1.5">{t("app.realSourceNote")}</p>
        </div>
      )}
    </div>
  );
}

/**
 * 样本不足的占位。**这是一个组件而不是一个字符串**，因为它绝不能被渲染成
 * 0、`—` 或一个灰掉的数字——那三种写法都会被读成"这个群体的表现是零/很差"，
 * 而真相是"人太少，说了就等于点名"（B9）。
 */
export function InsufficientEvidence({ n }: { n?: number }) {
  const { t } = useI18n();
  return (
    <span
      data-insufficient-evidence
      title={n === undefined ? undefined
        : t("insights.insufficient.why").replace("{n}", String(n))}
      className="t-micro inline-flex items-center gap-1.5 rounded-full px-2.5 py-1"
      style={{
        border: "1px solid var(--hatch)",
        color: "var(--hatch-ink)",
        background:
          "repeating-linear-gradient(45deg, transparent, transparent 4px," +
          " color-mix(in srgb, var(--hatch) 16%, transparent) 4px," +
          " color-mix(in srgb, var(--hatch) 16%, transparent) 8px)",
      }}
    >
      {t("insights.insufficient")}
    </span>
  );
}

/**
 * 极简折线。手写内联 SVG——不引图表库：Clay 令牌要贯通，线上有包体约束，
 * 而成长跟踪页的逐月柱早就是同样的路子（有先例可复用）。
 *
 * 被抑制的点**画成空心**并跳过连线：把它当 0 连进去，趋势线就会假装
 * "那一期掉到了谷底"。
 */
export function Sparkline({
  points,
}: {
  points: { label: string; value: number; suppressed?: boolean }[];
}) {
  if (!points.length) return null;
  const w = 100;
  const h = 28;
  const max = Math.max(...points.map((p) => p.value), 0.0001);
  const at = (i: number) => (points.length === 1 ? w / 2 : (i / (points.length - 1)) * w);
  const y = (v: number) => h - (v / max) * (h - 4) - 2;
  const solid = points.map((p, i) => ({ ...p, x: at(i), y: y(p.value) }));
  const path = solid
    .filter((p) => !p.suppressed)
    .map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`)
    .join(" ");
  return (
    <div data-sparkline className="w-full">
      <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none"
           className="h-8 w-full" role="img" aria-hidden>
        <path d={path} fill="none" stroke="var(--accent-deep)" strokeWidth={1.5}
              vectorEffect="non-scaling-stroke" />
        {solid.map((p) => (
          <circle key={p.label} cx={p.x} cy={p.y} r={2}
                  fill={p.suppressed ? "var(--bg)" : "var(--accent-deep)"}
                  stroke="var(--accent-deep)" strokeWidth={1}
                  vectorEffect="non-scaling-stroke" />
        ))}
      </svg>
      <div className="t-micro mt-1 flex justify-between text-fg-faint">
        {points.map((p) => <span key={p.label}>{p.label}</span>)}
      </div>
    </div>
  );
}

/**
 * 横向条：标签 + 条 + 数值。给排行榜用。
 *
 * `suppressed` 的那一行画**斜纹**而不是短条——短条会被读成"这项很少"，
 * 而真相是"人太少不能说"。两者在校方的处置上完全相反。
 */
export function BarRow({
  label,
  value,
  max,
  suffix,
  suppressed = false,
  tone = "accent",
}: {
  label: string;
  value: number;
  max: number;
  suffix?: string;
  suppressed?: boolean;
  tone?: "accent" | "muted";
}) {
  const ratio = max > 0 ? Math.max(0, Math.min(1, value / max)) : 0;
  return (
    <div className="flex items-center gap-3" data-bar-row={label}>
      {/* 宽度自适应：写死 9.5rem 在学院小卡里会把条挤成一小截。
          min-w-0 + basis 让它在宽容器里舒展、在窄容器里让位。 */}
      <span className="t-micro min-w-0 shrink basis-[9.5rem] truncate text-fg-muted"
            title={label}>
        {label}
      </span>
      <div className="h-3 flex-1 overflow-hidden rounded-full bg-bg-sunk">
        <div
          className="h-full rounded-full"
          style={
            suppressed
              ? {
                  width: "100%",
                  background:
                    "repeating-linear-gradient(45deg, transparent, transparent 4px," +
                    " color-mix(in srgb, var(--hatch) 24%, transparent) 4px," +
                    " color-mix(in srgb, var(--hatch) 24%, transparent) 8px)",
                }
              : {
                  width: `${ratio * 100}%`,
                  background:
                    tone === "muted" ? "var(--color-mist-400, var(--line-strong))" : "var(--accent)",
                }
          }
        />
      </div>
      <span className="t-micro w-14 shrink-0 text-end tabular-nums text-fg-muted">
        {suppressed ? "—" : `${value}${suffix ?? ""}`}
      </span>
    </div>
  );
}

/**
 * 漏斗：一层比一层窄。用**面积**而不是长度表达衰减，因为漏斗的重点是
 * "掉了多少"，长度条已经有 BarRow 在做了。
 */
export function Funnel({
  steps,
}: {
  steps: { label: string; value: number }[];
}) {
  const top = steps[0]?.value ?? 0;
  return (
    <div data-funnel className="flex flex-col gap-1.5">
      {steps.map((step, i) => {
        const ratio = top > 0 ? step.value / top : 0;
        return (
          <div key={step.label} className="flex items-center gap-3">
            <span className="t-micro w-[7.5rem] shrink-0 text-fg-muted">{step.label}</span>
            <div className="flex-1">
              <div
                className="h-7 rounded-md"
                style={{
                  width: `${Math.max(ratio * 100, 2)}%`,
                  background: `color-mix(in srgb, var(--accent) ${
                    Math.round(70 - i * 14)
                  }%, var(--bg-sunk))`,
                }}
              />
            </div>
            <span className="t-micro w-24 shrink-0 text-end tabular-nums text-fg-muted">
              {step.value.toLocaleString()}
              {i > 0 && top > 0 && (
                <span className="ms-1 text-fg-faint">
                  {Math.round(ratio * 100)}%
                </span>
              )}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/**
 * 带置信区间须线的分数条（1–5）。
 *
 * **须线不是装饰**：样本少的时候区间会很宽，那正是"别太当真"的可视化说法。
 * 只画点不画须，5 个人的 4.6 分和 200 个人的 4.6 分看起来一模一样。
 */
export function WhiskerBar({
  label,
  score,
  low,
  high,
}: {
  label: string;
  score: number;
  low: number;
  high: number;
}) {
  const pos = (v: number) => ((v - 1) / 4) * 100;
  return (
    <div className="flex items-center gap-3" data-whisker={label}>
      <span className="t-micro w-[6.5rem] shrink-0 leading-tight text-fg-muted">{label}</span>
      <div className="relative h-6 flex-1">
        <div className="absolute inset-x-0 top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-bg-sunk" />
        <div
          className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full"
          style={{
            left: `${pos(low)}%`,
            width: `${Math.max(pos(high) - pos(low), 1)}%`,
            background: "color-mix(in srgb, var(--accent) 34%, transparent)",
          }}
        />
        <div
          className="absolute top-1/2 h-3.5 w-[3px] -translate-x-1/2 -translate-y-1/2 rounded-sm"
          style={{ left: `${pos(score)}%`, background: "var(--accent-deep)" }}
        />
      </div>
      <span className="t-micro w-16 shrink-0 text-end tabular-nums text-fg-muted">
        {score.toFixed(2)}
      </span>
    </div>
  );
}
