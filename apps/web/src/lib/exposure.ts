"use client";

import { useCallback, useEffect, useRef } from "react";
import { api, type Schemas } from "@/lib/api";
import { usePersona } from "@/app/providers";

/**
 * 曝光记录器（Spec §17.6）。
 *
 * **「看到」必须是「真的进过视口」**，不是「在 JSON 里」。后端返回 200 条机会
 * 而学生只滚到第 8 条，把 200 条都记成曝光会让「曝光断层榜」彻底失去意义——
 * 那张榜的全部价值就在于分辨「发出去了」和「被看见了」。
 *
 * 所以用 IntersectionObserver：阈值 0.5（半个卡片进入视口）+ 停留 ≥300ms
 * （飞速滚过不算看见）。会话级去重集合避免重复上报；满 25 条 / 空闲 5s /
 * `pagehide` 时 flush，用 `keepalive` 让离开页面那一批也发得出去。
 */
const BATCH_SIZE = 25;
const IDLE_FLUSH_MS = 5000;
const DWELL_MS = 300;
const VISIBLE_RATIO = 0.5;

type Surface = "plaza" | "for_you";
type Depth = "impression" | "detail";

let sequence = 0;

export function useExposureRecorder(surface: Surface, period: string) {
  const { studentId } = usePersona();
  const queue = useRef<Schemas["ExposureEvent"][]>([]);
  const reported = useRef<Set<string>>(new Set());
  const timers = useRef<Map<Element, number>>(new Map());
  const idle = useRef<number | null>(null);
  const observer = useRef<IntersectionObserver | null>(null);

  const flush = useCallback(() => {
    if (idle.current !== null) {
      window.clearTimeout(idle.current);
      idle.current = null;
    }
    const events = queue.current;
    if (!events.length || !studentId) return;
    queue.current = [];
    // 失败就算了：曝光是尽力而为的遥测，丢一批不该让学生看到错误。
    // 但**不重试也不静默补回**——补回来的曝光时间戳是假的。
    api.recordExposures(studentId, { student_id: studentId, events })
      .catch(() => undefined);
  }, [studentId]);

  const enqueue = useCallback((subjectId: string, depth: Depth) => {
    const key = `${subjectId}|${surface}|${depth}`;
    if (reported.current.has(key)) return;
    reported.current.add(key);
    sequence += 1;
    queue.current.push({
      event_id: `EX-${studentId}-${sequence}-${Date.now().toString(36)}`,
      student_id: studentId,
      subject_id: subjectId,
      surface,
      depth,
      occurred_at: new Date().toISOString(),
      period,
    });
    if (queue.current.length >= BATCH_SIZE) {
      flush();
      return;
    }
    if (idle.current !== null) window.clearTimeout(idle.current);
    idle.current = window.setTimeout(flush, IDLE_FLUSH_MS);
  }, [studentId, surface, period, flush]);

  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return;
    observer.current = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        const el = entry.target;
        const subjectId = el.getAttribute("data-exposure-subject");
        if (!subjectId) continue;
        if (entry.isIntersecting) {
          // 停留够久才算看见——飞速滚过不算
          const timer = window.setTimeout(
            () => enqueue(subjectId, "impression"), DWELL_MS);
          timers.current.set(el, timer);
        } else {
          const timer = timers.current.get(el);
          if (timer !== undefined) {
            window.clearTimeout(timer);
            timers.current.delete(el);
          }
        }
      }
    }, { threshold: VISIBLE_RATIO });

    const onLeave = () => flush();
    window.addEventListener("pagehide", onLeave);
    return () => {
      window.removeEventListener("pagehide", onLeave);
      observer.current?.disconnect();
      timers.current.forEach((t) => window.clearTimeout(t));
      timers.current.clear();
      flush();
    };
  }, [enqueue, flush]);

  /** 挂在卡片根节点上：`ref={observe}` + `data-exposure-subject={id}`。 */
  const observe = useCallback((el: HTMLElement | null) => {
    if (el) observer.current?.observe(el);
  }, []);

  /** 抽屉展开 = 真的点开看了，深度记为 detail。 */
  const markDetail = useCallback(
    (subjectId: string) => enqueue(subjectId, "detail"), [enqueue]);

  return { observe, markDetail, flush };
}
