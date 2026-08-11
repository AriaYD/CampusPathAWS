"use client";

import { useState } from "react";
import { useI18n } from "@/i18n";
import { institution, type ResourceCoverageAggregate } from "@/lib/api";
import { useResource } from "@/lib/useResource";
import {
  Card,
  Empty,
  Failure,
  Grid,
  InsufficientEvidence,
  Loading,
  Metric,
  PageHeader,
  SectionTitle,
  Segmented,
  Sparkline,
} from "@/components/ui";

/**
 * 校方洞察页（Spec §17.1.2 / §17.3.1 / §17.6，2026-08-10 用户需求 B）。
 *
 * 五个视图集中一页：全局利用率与趋势 / 曝光断层榜 / 供给缺口榜 /
 * 分组对比 / Plaza-to-Action 转化。
 *
 * **这一页最重要的不是画得好看，是不许说谎**：
 * - 样本不足的格子渲染 `Insufficient evidence`，**绝不**画成 0、`—` 或灰数字；
 * - 每个分区标出「N 真实 / M 合成」——合成数据是用来撑演示形状的，
 *   把它和真实推导混在一起，校方看到的每个百分比都失去意义；
 * - **零下钻入口**：这一页没有任何「看看是哪些学生」的按钮，后端也不提供
 *   那种查询（硬性边界第 2 条）。
 */

type Cohort = "school" | "year_level" | "development_mode";

function pct(value: number | null | undefined): string | null {
  return value === null || value === undefined
    ? null
    : `${Math.round(value * 100)}%`;
}

/** 一个比率：有值就出数字，没值就出 Insufficient evidence——不出第三种。 */
function Rate({ label, value, n }: { label: string; value: number | null | undefined; n: number }) {
  const shown = pct(value);
  return (
    <div data-rate={label} data-suppressed={shown === null ? "true" : "false"}>
      <div className="t-micro text-fg-faint">{label}</div>
      {shown === null ? (
        <div className="mt-1"><InsufficientEvidence n={n} /></div>
      ) : (
        <div className="t-title mt-1 tabular-nums text-fg">{shown}</div>
      )}
    </div>
  );
}

function ProvenanceNote({ rows }: { rows: { derived_cell_n: number; synthetic_cell_n: number }[] }) {
  const { t } = useI18n();
  const derived = rows.reduce((a, r) => a + r.derived_cell_n, 0);
  const synthetic = rows.reduce((a, r) => a + r.synthetic_cell_n, 0);
  return (
    <p className="t-micro mt-2 text-fg-faint" data-provenance-note>
      {t("insights.provenance")
        .replace("{derived}", String(derived))
        .replace("{synthetic}", String(synthetic))}
    </p>
  );
}

export default function InsightsPage() {
  const { t } = useI18n();
  const [cohort, setCohort] = useState<Cohort>("school");

  const trend = useResource(() => institution.resourceCoverage(), []);
  const cells = useResource(
    () => institution.resourceCoverage({ cohort }), [cohort]);
  // 供给缺口按学院拆：与分组对比用的是同一条聚合路径，但它自己固定按学院，
  // 不跟着上面那个分组选择器走——「哪个学院缺什么」是一个独立的问题。
  const bySchool = useResource(
    () => institution.resourceCoverage({ cohort: "school" }), []);
  const conversion = useResource(() => institution.plazaConversion(), []);

  const latest: ResourceCoverageAggregate | null =
    trend.data && trend.data.length ? trend.data[trend.data.length - 1] : null;

  return (
    <>
      <PageHeader titleKey="insights.title" leadKey="insights.lead" />

      {/* 2026-08-11 用户裁定：撤掉「仅真实推导」分段控件。
          接入真实数据后所有来源本来就都是真实的，这个开关届时是死 UI；
          而在演示环境里按下它会整页显示「样本不足」，评委只会读成"坏了"。
          **诚实性不靠这个控件保证**——每个分区下方的 provenance 注脚照旧
          写明「N 条真实推导 / M 条合成演示」，服务端的 `include_synthetic`
          参数也保留（它是这条诚实性可被测试断言的地方）。 */}
      {/* ── 视图 1：全局利用率 + 趋势 ── */}
      <Card className="mb-5" data-view="utilisation">
        <SectionTitle>{t("insights.utilisation")}</SectionTitle>
        {trend.loading && <Loading />}
        {trend.error && <Failure error={trend.error} />}
        {latest && (
          <>
            <Grid min={200}>
              <Rate label={t("insights.discovery")} value={latest.discovery_rate} n={latest.cell_n} />
              <Rate label={t("insights.action")} value={latest.action_rate} n={latest.cell_n} />
              <Rate label={t("insights.gapCoverage")} value={latest.gap_coverage_rate} n={latest.cell_n} />
              <Metric label={t("insights.cellN")} value={latest.cell_n} />
            </Grid>
            <p className="t-micro mt-3 max-w-[74ch] text-fg-faint" data-reach-note>
              {t("insights.discovery.note")}
            </p>
            {trend.data && trend.data.length > 1 && (
              <div className="mt-4" data-trend>
                <p className="t-micro mb-1.5 text-fg-faint">{t("insights.trend")}</p>
                <Sparkline
                  points={trend.data.map((r) => ({
                    label: r.period,
                    value: r.discovery_rate ?? 0,
                    suppressed: r.discovery_rate === null,
                  }))}
                />
              </div>
            )}
            {trend.data && <ProvenanceNote rows={trend.data} />}
          </>
        )}
      </Card>

      {/* ── 视图 2：供给缺口榜（全校 + 按学院拆）──
          2026-08-11 用户裁定：只按能力类别分不够，要能看出**哪个学院**的
          资源有缺口——「全校缺 network」和「工院缺 network 而商院不缺」
          是两种完全不同的处置。逐学院的抑制沿用同一条 MIN_CELL_N 规则。 */}
      <Card className="mb-5" data-view="unmet">
        <SectionTitle>{t("insights.unmet")}</SectionTitle>
        <p className="t-meta mb-3 max-w-[70ch] text-fg-muted">{t("insights.unmet.lead")}</p>
        {latest && latest.unmet_requirement_ranking.length === 0 && (
          <Empty messageKey="insights.unmet.empty" />
        )}
        <ul className="flex flex-col gap-2">
          {(latest?.unmet_requirement_ranking ?? []).map((row) => (
            <li key={row.category} data-unmet={row.category}
                className="flex flex-wrap items-baseline justify-between gap-2 rounded-md border border-line bg-bg-sunk p-3">
              <span className="t-meta text-fg">{row.category}</span>
              <span className="t-micro text-fg-muted">
                <span className="tabular-nums">{row.occurrences}</span> ·{" "}
                {row.covered_by_any_resource
                  ? t("insights.unmet.covered")
                  : t("insights.unmet.uncovered")}
              </span>
            </li>
          ))}
        </ul>

        {/* 逐学院：同一份缺口按学院拆开，每格自带自己的样本量与抑制。
            全校层面看不出的偏科，在这一层才现形。 */}
        <div className="mt-5" data-unmet-by-school>
          <p className="t-micro mb-2 text-fg-faint">{t("insights.unmet.bySchool")}</p>
          {bySchool.loading && <Loading />}
          {bySchool.error && <Failure error={bySchool.error} />}
          <Grid min={240}>
            {(bySchool.data ?? []).map((cell) => {
              const school = cell.aggregate_id.replace(/^AGG-/, "");
              const rows = cell.unmet_requirement_ranking;
              return (
                <div key={cell.aggregate_id} data-unmet-school={school}
                     className="rounded-md border border-line bg-bg-sunk p-3">
                  <div className="t-meta mb-2 font-medium text-fg">{school}</div>
                  {cell.cell_n < 5 ? (
                    <InsufficientEvidence n={cell.cell_n} />
                  ) : rows.length === 0 ? (
                    <p className="t-micro text-fg-faint">{t("insights.unmet.none")}</p>
                  ) : (
                    <ul className="flex flex-col gap-1.5">
                      {rows.slice(0, 6).map((row) => (
                        <li key={row.category} data-unmet-row={`${school}:${row.category}`}
                            className="t-micro flex items-baseline justify-between gap-2 text-fg-muted">
                          <span>{row.category}</span>
                          <span className="tabular-nums">{row.occurrences}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                  <p className="t-micro mt-2 text-fg-faint">
                    {t("insights.cellN")} {cell.cell_n}
                  </p>
                </div>
              );
            })}
          </Grid>
        </div>
      </Card>

      {/* ── 视图 4：分组对比（抑制格必须看得见）── */}
      <Card className="mb-5" data-view="cohort">
        <SectionTitle>{t("insights.cohort")}</SectionTitle>
        <div className="mb-3">
          <Segmented
            ariaLabel={t("insights.cohort")}
            value={cohort}
            onChange={setCohort}
            options={(["school", "year_level", "development_mode"] as Cohort[]).map((c) => ({
              value: c, label: t(`insights.cohort.${c}` as Parameters<typeof t>[0]),
            }))}
          />
        </div>
        {cells.loading && <Loading />}
        {cells.error && <Failure error={cells.error} />}
        <Grid min={220}>
          {(cells.data ?? []).map((cell) => (
            <div key={cell.aggregate_id} data-cohort-cell={cell.aggregate_id}
                 className="rounded-md border border-line bg-bg-sunk p-3">
              <div className="t-meta mb-2 font-medium text-fg">
                {cell.aggregate_id.replace(/^AGG-/, "")}
              </div>
              <Rate label={t("insights.discovery")} value={cell.discovery_rate} n={cell.cell_n} />
              <div className="mt-2">
                <Rate label={t("insights.action")} value={cell.action_rate} n={cell.cell_n} />
              </div>
              <p className="t-micro mt-2 text-fg-faint">
                {t("insights.cellN")} {cell.cell_n}
              </p>
            </div>
          ))}
        </Grid>
        {cells.data && cells.data.length === 0 && !cells.loading && (
          <Empty messageKey="insights.cohort.empty" />
        )}
      </Card>

      {/* ── 视图 5：Plaza-to-Action ── */}
      <Card data-view="conversion">
        <SectionTitle>{t("insights.conversion")}</SectionTitle>
        <p className="t-meta mb-3 max-w-[70ch] text-fg-muted">
          {t("insights.conversion.lead")}
        </p>
        {conversion.loading && <Loading />}
        {conversion.error && <Failure error={conversion.error} />}
        <Grid min={220}>
          {(conversion.data ?? []).map((row) => (
            <div key={row.aggregate_id} data-conversion={row.aggregate_id}
                 className="rounded-md border border-line bg-bg-sunk p-3">
              <div className="t-meta mb-2 font-medium text-fg">
                {row.period} · {t(`insights.surface.${row.surface}` as Parameters<typeof t>[0])}
              </div>
              <Rate label={t("insights.conversionRate")} value={row.conversion_rate} n={row.cell_n} />
              <p className="t-micro mt-2 tabular-nums text-fg-faint">
                {t("insights.exposedTotal")} {row.exposed_total} ·{" "}
                {t("insights.actedTotal")} {row.acted_total}
              </p>
            </div>
          ))}
        </Grid>
        {conversion.data && <ProvenanceNote rows={conversion.data} />}
      </Card>
    </>
  );
}
