"use client";

import { useState } from "react";
import { useI18n } from "@/i18n";
import { institution, type ResourceCoverageAggregate } from "@/lib/api";
import { useResource } from "@/lib/useResource";
import {
  BarRow,
  Card,
  Empty,
  Funnel,
  Grid,
  Loading,
  Failure,
  InsufficientEvidence,
  SectionTitle,
  Sparkline,
  SyntheticBadge,
} from "@/components/ui";

/**
 * 完整数据报告（2026-08-10 用户需求 C）。
 *
 * **就地展开，不跳页不下载**——报告要能在同一屏里和上面的四个视图对照着看，
 * 跳出去就断了。
 *
 * 图表一律**手写内联 SVG / CSS**，不引图表库：Clay 令牌要贯通、线上有包体与
 * CSP 约束，而且成长跟踪页的逐月柱早就是同样的路子（有先例可复用）。
 *
 * 三条诚实性红线（与 `/insights` 主体同源）：
 * 1. 被抑制的格画**斜纹**并写 `Insufficient evidence`，**绝不画成 0 或空白**；
 * 2. 合成数据来源的分区带 `Synthetic / Demo Data` 角标；
 * 3. 零下钻——报告里没有任何"看看是哪些学生"的入口。
 */

const MIN_CELL_N = 5;

function pct(v: number | null | undefined): string | null {
  return v === null || v === undefined ? null : `${Math.round(v * 100)}%`;
}

/** 小倍数网格的一格：一个学院 × 三项指标。抑制格画斜纹。 */
function CellCard({ cell }: { cell: ResourceCoverageAggregate }) {
  const { t } = useI18n();
  const thin = cell.cell_n < MIN_CELL_N;
  const rows: [string, number | null][] = [
    [t("insights.discovery"), cell.discovery_rate],
    [t("insights.action"), cell.action_rate],
    [t("insights.gapCoverage"), cell.gap_coverage_rate],
  ];
  return (
    <div
      data-report-cell={cell.aggregate_id}
      className="rounded-md border border-line bg-bg-sunk p-3"
    >
      <div className="t-meta mb-2 font-medium text-fg">
        {/* 代码换成人话：SENG 这种缩写只有内部人看得懂 */}
        {t(`school.${cell.aggregate_id.replace(/^AGG-/, "")}` as Parameters<typeof t>[0])}
      </div>
      {thin ? (
        <InsufficientEvidence n={cell.cell_n} />
      ) : (
        <div className="flex flex-col gap-2">
          {rows.map(([label, value]) => (
            <BarRow
              key={label}
              label={label}
              value={Math.round((value ?? 0) * 100)}
              max={100}
              suffix="%"
              suppressed={value === null}
            />
          ))}
        </div>
      )}
      <p className="t-micro mt-2 text-fg-faint">
        {t("insights.cellN")} {cell.cell_n}
      </p>
    </div>
  );
}

export function InsightReport() {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  // 2026-08-11 用户裁定：报告并入「活动反馈数据报告」页，与周期报告合成
  // **一份**报告，不再拆成两份。所以数据由组件自取——它已经不在 /insights 上，
  // 没有上游可以传给它了。展开才拉：没人点开就不该付这三次请求的代价。
  const trendRes = useResource(
    () => (open ? institution.resourceCoverage() : Promise.resolve([])), [open]);
  const schoolRes = useResource(
    () => (open ? institution.resourceCoverage({ cohort: "school" })
                : Promise.resolve([])), [open]);
  const conversionRes = useResource(
    () => (open ? institution.plazaConversion() : Promise.resolve([])), [open]);
  const trend = trendRes.data ?? [];
  const bySchool = schoolRes.data ?? [];
  const conversion = conversionRes.data ?? [];
  const loading = trendRes.loading || schoolRes.loading || conversionRes.loading;
  const failure = trendRes.error ?? schoolRes.error ?? conversionRes.error;

  const latest = trend.length ? trend[trend.length - 1] : null;
  const plaza = conversion.filter((c) => c.surface === "plaza");
  const latestPlaza = plaza.length ? plaza[plaza.length - 1] : null;

  return (
    <Card className="mt-5" data-report>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SectionTitle>{t("report.title")}</SectionTitle>
        <button
          type="button"
          data-report-toggle
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
          className="pressable btn btn-secondary t-meta"
        >
          {open ? t("report.collapse") : t("report.expand")}
        </button>
      </div>
      <p className="t-meta mb-1 max-w-[74ch] text-fg-muted">{t("report.lead")}</p>

      {open && (
        <div className="mt-4 flex flex-col gap-6" data-report-body>
          <div>
            <SyntheticBadge />
          </div>
          {loading && <Loading />}
          {failure && <Failure error={failure} />}

          {/* ── 一、三项利用率与趋势 ── */}
          <section data-report-section="utilisation">
            <p className="t-micro mb-2 font-medium text-fg">{t("report.section.utilisation")}</p>
            {latest && (
              <div className="flex flex-col gap-2">
                <BarRow label={t("insights.discovery")}
                        value={Math.round((latest.discovery_rate ?? 0) * 100)}
                        max={100} suffix="%" suppressed={latest.discovery_rate === null} />
                <BarRow label={t("insights.action")}
                        value={Math.round((latest.action_rate ?? 0) * 100)}
                        max={100} suffix="%" suppressed={latest.action_rate === null} />
                <BarRow label={t("insights.gapCoverage")}
                        value={Math.round((latest.gap_coverage_rate ?? 0) * 100)}
                        max={100} suffix="%" suppressed={latest.gap_coverage_rate === null} />
              </div>
            )}
            {trend.length > 1 && (
              <div className="mt-3">
                <Sparkline
                  points={trend.map((r) => ({
                    label: r.period,
                    value: r.discovery_rate ?? 0,
                    suppressed: r.discovery_rate === null,
                  }))}
                />
              </div>
            )}
          </section>

          {/* ── 二、供给缺口（全校 + 按学院小倍数）── */}
          <section data-report-section="supply">
            <p className="t-micro mb-2 font-medium text-fg">{t("report.section.supply")}</p>
            {latest && latest.unmet_requirement_ranking.length > 0 ? (
              <div className="flex flex-col gap-2">
                {latest.unmet_requirement_ranking.map((row) => (
                  <BarRow
                    key={row.category}
                    label={t(`category.${row.category}` as Parameters<typeof t>[0])}
                    value={row.occurrences}
                    max={Math.max(...latest.unmet_requirement_ranking.map((r) => r.occurrences))}
                    tone={row.covered_by_any_resource ? "muted" : "accent"}
                  />
                ))}
                <p className="t-micro mt-1 text-fg-faint">{t("report.supply.legend")}</p>
              </div>
            ) : (
              <Empty messageKey="insights.unmet.empty" />
            )}
          </section>

          {/* ── 三、分组对比小倍数网格 ── */}
          <section data-report-section="cohort">
            <p className="t-micro mb-2 font-medium text-fg">{t("report.section.cohort")}</p>
            <Grid min={240}>
              {bySchool.map((cell) => <CellCard key={cell.aggregate_id} cell={cell} />)}
            </Grid>
          </section>

          {/* ── 四、广场转化漏斗 ── */}
          <section data-report-section="funnel">
            <p className="t-micro mb-2 font-medium text-fg">{t("report.section.funnel")}</p>
            {latestPlaza ? (
              latestPlaza.cell_n < MIN_CELL_N ? (
                <InsufficientEvidence n={latestPlaza.cell_n} />
              ) : (
                <>
                  <Funnel
                    steps={[
                      { label: t("insights.exposedTotal"), value: latestPlaza.exposed_total },
                      { label: t("insights.actedTotal"), value: latestPlaza.acted_total },
                    ]}
                  />
                  <p className="t-micro mt-2 text-fg-faint">
                    {t("insights.conversionRate")}: {pct(latestPlaza.conversion_rate) ?? "—"}
                  </p>
                </>
              )
            ) : (
              <Empty messageKey="insights.cohort.empty" />
            )}
          </section>

          {/* 五、四维活动质量——**已撤下**（2026-08-11 用户裁定）。
              那是**逐活动**的评分，早就在「资讯广场总览」逐行显示（含 k-匿名
              阈值与契合分布）。在这份**跨活动的聚合报告**里再列一遍每个活动，
              既重复又串了层级：这份报告回答的是"全校资源效能"，不是"这场活动办得好不好"。
              实测佐证：模拟 7 份已验证反馈后，广场总览该行立刻出
              内容深度 4.6 / 组织流程 2.6 / 实用收获 4.4 / 预期兑现 4.0，
              周围各行仍是「样本不足」——那一页已经把这件事说清楚了。 */}

          <p className="t-micro border-l-2 border-line ps-3 text-fg-faint" data-report-notes>
            {t("report.notes")}
          </p>
        </div>
      )}
    </Card>
  );
}
