/**
 * 底部标签栏用的线性图标。
 *
 * 为什么不用 emoji：emoji 依字体而变、跨平台不一致、无法被设计令牌控制颜色，
 * 也没法跟随选中态（ui-ux-pro-max §4 `no-emoji-icons`）。为什么不引图标库：
 * 全站只需要这几个，一个依赖换十来行内联 SVG 不划算，且线上有包体约束。
 *
 * 统一规格：24×24 视框、`stroke-width: 1.75`、`currentColor` 取色、
 * 圆头圆角接线——一套笔画语言，不混填充与描边（§4 `icon-style-consistent`）。
 */
type IconProps = { className?: string };

function Svg({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75}
      strokeLinecap="round" strokeLinejoin="round" aria-hidden focusable="false"
      className={className} width={24} height={24}
    >
      {children}
    </svg>
  );
}

/** 成长档案：人 + 底座 */
const Profile = (p: IconProps) => (
  <Svg {...p}><circle cx="12" cy="8" r="3.5" /><path d="M4.5 20a7.5 7.5 0 0 1 15 0" /></Svg>
);
/** 为你推荐：指南针——「往哪走」而不是「有什么」 */
const Discover = (p: IconProps) => (
  <Svg {...p}><circle cx="12" cy="12" r="8.5" /><path d="M15.5 8.5 13.7 13.7 8.5 15.5l1.8-5.2z" /></Svg>
);
/** 规划与行动：勾选清单 */
const Plan = (p: IconProps) => (
  <Svg {...p}><path d="m3.5 7 2 2 3-3.5" /><path d="m3.5 16.5 2 2 3-3.5" /><path d="M12 7.5h8.5M12 17h8.5" /></Svg>
);
/** 日历与容量 */
const Calendar = (p: IconProps) => (
  <Svg {...p}>
    <rect x="3.5" y="5" width="17" height="15.5" rx="2.5" />
    <path d="M3.5 9.5h17M8 3.5v3M16 3.5v3" />
  </Svg>
);
/** 更多：不用「三个点」而用网格——它拉起的是一张清单，不是一个菜单条 */
const More = (p: IconProps) => (
  <Svg {...p}>
    <rect x="4" y="4" width="6.5" height="6.5" rx="1.8" />
    <rect x="13.5" y="4" width="6.5" height="6.5" rx="1.8" />
    <rect x="4" y="13.5" width="6.5" height="6.5" rx="1.8" />
    <rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.8" />
  </Svg>
);
/** 资讯广场：叠放的卡片 */
const Square = (p: IconProps) => (
  <Svg {...p}>
    <rect x="3.5" y="6.5" width="17" height="12" rx="2.5" />
    <path d="M7 3.5h10M7.5 11h6M7.5 14.5h9" />
  </Svg>
);
/** 校方通用工作台：面板 */
const Desk = (p: IconProps) => (
  <Svg {...p}>
    <rect x="3.5" y="4.5" width="17" height="15" rx="2.5" />
    <path d="M3.5 9.5h17M9 9.5v10" />
  </Svg>
);

/**
 * href → 图标。没有专属图标的一律走 `Desk`——**给一个中性图标，
 * 而不是不给图标**：底部导航的每一格都必须图标 + 文字，
 * 只有文字会显著伤害可发现性（§9 `nav-label-icon`）。
 */
const BY_HREF: Record<string, (p: IconProps) => React.ReactElement> = {
  "/profile": Profile,
  "/for-you": Discover,
  "/actions": Plan,
  "/calendar": Calendar,
  "/square": Square,
  "/gaps": Profile,
  "/goals": Discover,
};

export function NavIcon({ href, className }: { href: string; className?: string }) {
  const Icon = BY_HREF[href] ?? Desk;
  return <Icon className={className} />;
}

export const MoreIcon = More;
