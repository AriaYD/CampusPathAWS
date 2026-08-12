"use client";

import { useCallback, useEffect, useState } from "react";
import { localized, pickLang, useI18n } from "@/i18n";
import { ApiError, api, type Schemas } from "@/lib/api";
import { useResource, type Resource } from "@/lib/useResource";
import { Card, Drawer, SectionTitle } from "@/components/ui";

/**
 * G（2026-08-10 用户裁定）：**规划要先问过学生才落盘**。
 *
 * 用户原话：「第一次规划直接落盘 很不对劲…… 应该是根据我的目标和我的档案，
 * 还有记忆中心的用户偏好去规划之后，弹窗询问我是否批准这个规划」。
 *
 * 服务端把「排」与「定」拆成了 `POST /pathway/draft` 与
 * `/draft/{id}/decision`，`GET /pathway` 只读已采纳版本。前端相应地分成
 * 两态：**没有已采纳版本 = 404 = 空态**（不是故障，所以不渲染 Failure），
 * 学生点「开始规划」才起草，起草完弹窗给他看清依据再决定。
 *
 * 抽成一个 hook + 一个组件，是因为行动中心与课外规划两页共用同一份规划——
 * 两处各写一遍审批流，迟早会漂移成两种批准语义。
 */

export type PathwayPlan = {
  pathway: Resource<Schemas["PathwayVersion"]>;
  draft: Schemas["PathwayDraft"] | null;
  state: "idle" | "drafting" | "deciding" | "error";
  /** 还没有任何已采纳版本——该显示"开始规划"，不是显示错误。 */
  neverPlanned: boolean;
  startPlanning: () => Promise<void>;
  progress: { percent: number; phase: string } | null;
  decide: (decision: "adopt" | "discard",
           acknowledgeConflicts?: boolean,
           keepPlanItemIds?: string[]) => Promise<void>;
  dismissDraft: () => void;
};

export function usePathwayPlan(studentId: string, intensity?: string): PathwayPlan {
  const pathway = useResource(
    () => api.pathway(studentId, intensity), [studentId, intensity]);
  const [draft, setDraft] = useState<Schemas["PathwayDraft"] | null>(null);
  const [state, setState] = useState<PathwayPlan["state"]>("idle");

  const [progress, setProgress] = useState<{ percent: number; phase: string } | null>(null);

  /** 轮询排程进度，直到跑完或失败。**回到页面也调它**——重点不是"我发起过"，
   *  而是"服务器现在做到哪了"。 */
  const followJob = useCallback(async function follow() {
    for (;;) {
      let job;
      try {
        job = await api.pathwayDraftStatus(studentId);
      } catch {
        setState("error");
        setProgress(null);
        return;
      }
      if (job.state === "running") {
        setState("drafting");
        setProgress({ percent: job.percent, phase: job.phase });
        await new Promise((r) => setTimeout(r, 1500));
        continue;
      }
      setProgress(null);
      if (job.state === "done" && job.draft_id) {
        try {
          setDraft(await api.pathwayDraftById(studentId, job.draft_id));
          setState("idle");
        } catch {
          setState("error");
        }
        return;
      }
      if (job.state === "failed") { setState("error"); return; }
      setState("idle");
      return;
    }
  }, [studentId]);

  // 切走再回来：问一次服务器。**做这件事的是服务器，不是这个页面**——
  // 所以页面卸载不该打断它，重新挂载也不该重新开始
  // （2026-08-11 用户要求 D）。
  useEffect(() => { void followJob(); }, [followJob]);

  async function startPlanning() {
    setState("drafting");
    setProgress({ percent: 0, phase: "collect" });
    try {
      await api.startPathwayDraft(studentId, intensity);
      await followJob();
    } catch {
      setState("error");
      setProgress(null);
    }
  }

  async function decide(decision: "adopt" | "discard",
                        acknowledgeConflicts = false,
                        keepPlanItemIds?: string[]) {
    if (!draft) return;
    setState("deciding");
    try {
      await api.decidePathwayDraft(studentId, draft.draft_id, decision,
                                   acknowledgeConflicts, keepPlanItemIds);
      setDraft(null);
      setState("idle");
      // 采纳后已采纳版本才存在——重读，让三个时间视图同时更新
      if (decision === "adopt") pathway.reload();
    } catch {
      setState("error");
    }
  }

  return {
    pathway,
    draft,
    state,
    progress,
    neverPlanned:
      pathway.error instanceof ApiError && pathway.error.isMissing,
    startPlanning,
    decide,
    dismissDraft: () => setDraft(null),
  };
}

/** 空态 + 审批弹窗。放在页面顶部，两页共用。 */
export function PathwayApprovalGate({ plan }: { plan: PathwayPlan }) {
  const { t, locale } = useI18n();
  // 分隔符也是文案：英文界面下写死「：」「、」会当场穿帮
  const colon = pickLang(locale, "：", ": ");
  const comma = pickLang(locale, "、", ", ");
  const semi = pickLang(locale, "；", "; ");
  const d = plan.draft;
  const busy = plan.state === "drafting" || plan.state === "deciding";
  // 「我知道有冲突」的勾选。**每来一份新草案都要重新勾**——
  // 上一版看过不等于这一版看过。
  const [ack, setAck] = useState(false);
  // 逐条取舍（2026-08-11 用户报障 A）。**默认全选**：这一版是系统排给你的，
  // 默认接受、逐条退出，比默认拒绝、逐条挑选更贴近"给你一版方案"的语义。
  // 存"被取消的那些"而不是"被选中的那些"——新草案来了直接清空即可，
  // 不必再去和新条目列表对账。
  const [dropped, setDropped] = useState<Set<string>>(new Set());
  const items = plan.draft?.pathway.plan_items ?? [];
  const keptIds = items.filter((i) => !dropped.has(i.plan_item_id))
                       .map((i) => i.plan_item_id);
  // 冲突只数**还留着的**：把撞车那条取消掉，就不该再拦着你批准
  const clashCount = items.filter(
    (i) => !dropped.has(i.plan_item_id) && (i.conflicts ?? []).length > 0).length;

  return (
    <>
      {plan.neverPlanned && (
        <Card className="mb-5" data-never-planned>
          <SectionTitle>{t("pathway.empty.title")}</SectionTitle>
          <p className="t-meta mb-3 max-w-[62ch] text-fg-muted">
            {t("pathway.empty.lead")}
          </p>
          <button
            type="button"
            data-start-planning
            disabled={busy}
            onClick={() => plan.startPlanning()}
            className="pressable btn btn-primary t-body disabled:opacity-60"
          >
            {plan.state === "drafting"
              ? t("pathway.empty.drafting")
              : t("pathway.empty.cta")}
          </button>
          {/* 进度条（2026-08-11 用户要求 D）。每一档对应一件真做完的事——
              取数 → 比对 → 拆解 → 校验；**不做插值动画**，假装匀速的进度条
              在慢的时候会卡在 99% 骗人，那比没有进度条更糟。
              刷新、切页、关页都不影响：进度存在服务端，回来一问就接上。 */}
          {plan.progress && (
            <div className="mt-3 max-w-[42ch]" data-draft-progress={plan.progress.percent}>
              <div className="t-micro mb-1 flex items-baseline justify-between text-fg-muted">
                <span>{t(`pathway.progress.${plan.progress.phase}` as Parameters<typeof t>[0])}</span>
                <span className="tabular-nums">{plan.progress.percent}%</span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full"
                   role="progressbar" aria-valuenow={plan.progress.percent}
                   aria-valuemin={0} aria-valuemax={100}
                   style={{ background: "var(--bg-sunk)" }}>
                <div className="h-full rounded-full"
                     style={{ width: `${plan.progress.percent}%`,
                              background: "var(--accent-deep)",
                              transition: "width .4s ease-out" }} />
              </div>
              <p className="t-micro mt-1.5 text-fg-faint">
                {t("pathway.progress.keepGoing")}
              </p>
            </div>
          )}
          {plan.state === "error" && (
            <p className="t-meta mt-2" style={{ color: "var(--color-clay-600)" }}>
              {t("pathway.draft.failed")}
            </p>
          )}
        </Card>
      )}

      {/* 已有规划时，重排入口也走同一条批准路——换档静默重排是这次要修掉的行为 */}
      {!plan.neverPlanned && plan.pathway.data && (
        <button
          type="button"
          data-replan
          disabled={busy}
          onClick={() => plan.startPlanning()}
          className="pressable btn btn-secondary t-meta mb-4 disabled:opacity-60"
        >
          {plan.state === "drafting"
            ? t("pathway.empty.drafting")
            : t("pathway.replan")}
        </button>
      )}

      <Drawer
        open={d !== null}
        onClose={() => plan.dismissDraft()}
        title={t("pathway.draft.title")}
      >
        {d && (
          <div data-pathway-draft={d.draft_id}>
            <SectionTitle>{t("pathway.draft.title")}</SectionTitle>
            <p className="t-meta mb-4 text-fg-muted">
              {d.diff.is_first_plan
                ? t("pathway.draft.leadFirst")
                : t("pathway.draft.leadReplan")}
            </p>

            {/* 依据行：目标 / 档案 / 记忆偏好。数据一直都在，只是从没上过屏——
                要学生批准一件事，先让他看见这件事凭什么来的。 */}
            <div className="mb-4 rounded-md border border-line bg-bg-sunk p-3"
                 data-draft-rationale>
              <p className="t-micro mb-2 text-fg-faint">
                {t("pathway.draft.grounds")}
              </p>
              <ul className="t-meta flex flex-col gap-1 text-fg-muted">
                {d.rationale_goals.length > 0 && (
                  <li data-ground="goals">
                    {t("pathway.draft.grounds.goals")}{colon}
                    {d.rationale_goals.join(comma)}
                  </li>
                )}
                {d.rationale_profile.length > 0 && (
                  <li data-ground="profile">
                    {t("pathway.draft.grounds.profile")}{colon}
                    {d.rationale_profile.join(comma)}
                  </li>
                )}
                {d.rationale_memory.length > 0 && (
                  <li data-ground="memory">
                    {t("pathway.draft.grounds.memory")}{colon}
                    {d.rationale_memory.join(semi)}
                  </li>
                )}
              </ul>
            </div>

            {/* 会变什么。第一次规划只报新增——契约层不允许它报出"移除" */}
            <div className="mb-4 flex flex-wrap gap-2" data-draft-diff>
              {([
                ["added", d.diff.added_count],
                ["carried", d.diff.carried_over_count],
                ["removed", d.diff.removed_count],
                ["rescheduled", d.diff.rescheduled_count],
              ] as const)
                .filter(([, n]) => n > 0)
                .map(([kind, n]) => (
                  <span key={kind} data-diff={kind}
                        className="chip t-micro text-fg-muted">
                    {t(`pathway.draft.diff.${kind}` as Parameters<typeof t>[0])} {n}
                  </span>
                ))}
            </div>

            <p className="t-micro mb-1.5 text-fg-faint">
              {t("pathway.draft.items")}{pickLang(locale, "（", " (")}{d.pathway.plan_items.length}{pickLang(locale, "）", ")")}
            </p>
            <ul className="mb-4 flex max-h-[40vh] flex-col gap-2 overflow-y-auto">
              {d.pathway.plan_items.slice(0, 40).map((item) => (
                <li key={item.plan_item_id} data-draft-item={item.plan_item_id}
                    data-draft-kept={!dropped.has(item.plan_item_id)}
                    className="rounded-md border border-line p-2.5"
                    style={{ background: dropped.has(item.plan_item_id)
                      ? "transparent" : "var(--bg-sunk)",
                      opacity: dropped.has(item.plan_item_id) ? 0.55 : 1 }}>
                  <label className="flex items-start gap-2">
                    <input type="checkbox"
                           data-draft-pick={item.plan_item_id}
                           checked={!dropped.has(item.plan_item_id)}
                           onChange={() => setDropped((prev) => {
                             const next = new Set(prev);
                             if (next.has(item.plan_item_id)) next.delete(item.plan_item_id);
                             else next.add(item.plan_item_id);
                             return next;
                           })} />
                    <span className="min-w-0 flex-1">
                  <span className="t-meta text-fg">{localized(item.title, locale)}</span>
                  <span className="t-micro ms-2 text-fg-faint">
                    {item.date_range.start}
                    {item.date_range.end ? ` → ${item.date_range.end}` : ""}
                  </span>
                  {/* 冲突事实由服务端（Capacity）算好随条目下发。这里只陈述
                      「与谁撞、撞多久」——**不写"建议放弃"**：课能不能翘是
                      学生的私人取舍，他知道那节课点不点名，系统不知道。 */}
                  {(item.conflicts ?? []).length > 0 && (
                    <ul className="mt-1.5 flex flex-col gap-1"
                        data-item-conflicts={item.conflicts.length}>
                      {item.conflicts.map((c) => (
                        <li key={c.with_id} className="t-micro flex flex-wrap items-baseline gap-1.5"
                            style={{ color: "var(--color-clay-600)" }}>
                          <span aria-hidden>▲</span>
                          <span>{t(`pathway.conflict.${c.kind}` as Parameters<typeof t>[0])}</span>
                          <span className="text-fg-muted">{localized(c.label, locale)}</span>
                          <span className="tabular-nums">
                            {t("pathway.conflict.minutes").replace("{n}", String(c.overlap_minutes))}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                    </span>
                  </label>
                </li>
              ))}
            </ul>
            {/* 取消掉的条目 = 拒绝，会进拒绝名单，下一版不再推荐它
                （用户报障 B）。这句要说出来——静默记住比不记住更吓人。 */}
            <p className="t-micro mb-3 text-fg-faint" data-drop-note>
              {t("pathway.draft.dropNote")
                .replace("{n}", String(dropped.size))}
            </p>

            {clashCount > 0 && (
              <label className="mb-3 flex items-start gap-2 rounded-md p-2.5"
                     data-conflict-ack
                     style={{ background: "var(--color-clay-100)",
                              border: "1px solid var(--color-clay-500)" }}>
                <input type="checkbox" checked={ack}
                       onChange={(e) => setAck(e.target.checked)} />
                <span className="t-meta" style={{ color: "var(--color-clay-600)" }}>
                  {t("pathway.draft.ackConflicts").replace("{n}", String(clashCount))}
                </span>
              </label>
            )}
            <div className="flex gap-2">
              <button
                type="button"
                data-adopt-draft
                // 有冲突就必须先勾——**不拦"要不要去"，只拦"你看见了吗"**。
                // 服务端同样会拦（409），因为前端拦不住直连 API 的人。
                disabled={busy || (clashCount > 0 && !ack) || keptIds.length === 0}
                onClick={() => plan.decide("adopt", ack, keptIds)}
                className="pressable btn btn-primary t-body flex-1 disabled:opacity-60"
              >
                {t("pathway.draft.adopt")}
              </button>
              <button
                type="button"
                data-discard-draft
                disabled={busy}
                onClick={() => plan.decide("discard")}
                className="pressable btn btn-secondary t-body flex-1 disabled:opacity-60"
              >
                {t("pathway.draft.discard")}
              </button>
            </div>
          </div>
        )}
      </Drawer>
    </>
  );
}
