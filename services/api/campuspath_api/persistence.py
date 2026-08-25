"""Deps 的检查点（P3，2026-08-24）：可变状态整体落盘、冷启动回读。

**为什么是快照而不是逐容器改 Firestore**：Deps 上有 70+ 个容器、几百个写入点，
逐个换后端等于重写 api；而 12 名合成学生的全部状态只有几百 KB。
所以：后台线程按固定间隔把 :data:`MANIFEST` 列出的属性编码成 JSON，
**内容哈希变了才写**；启动时若后端有一份且版本戳匹配，就整体覆盖回来。

它解决的是**持久性**（重启不丢），不是多实例一致性——`max-instances=1`
的理由仍在（后台任务与锁都是进程态），README 如实写。

清单是**穷举**的：Deps 的每个属性要么在 MANIFEST，要么在 SKIPPED，
否则 `test_persistence` 红——新加一个容器忘了登记，不会静默丢。
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import os
import threading
import time
from typing import TYPE_CHECKING, Any

from campuspath_contracts.common import CONTRACTS_VERSION
from campuspath_contracts.validation import InMemoryValidationRegistry
from campuspath_seed.config import SEED_VERSION
from campuspath_state.checkpoint import (
    Checkpoint,
    FileCheckpoint,
    FirestoreCheckpoint,
    MemoryCheckpoint,
)
from campuspath_publishing.workflow import PublishingService
from campuspath_state.codec import DEFAULT as CODEC, Codec, install_defaults

if TYPE_CHECKING:  # pragma: no cover
    from .app import Deps

log = logging.getLogger("campuspath.persistence")

#: 环境变量：``firestore`` / ``firestore:<collection>`` / ``file:<path>`` / 未设=关闭。
CHECKPOINT_ENV = "CAMPUSPATH_CHECKPOINT"

#: 会被学生、校方或后台任务**改动**的状态。顺序无关。
MANIFEST: tuple[str, ...] = (
    # 学生私有域
    "students", "stores", "memory", "reflections", "applied_changes", "applied_undo",
    "declined", "goals", "pathways", "pathway_drafts", "schedule_proposals",
    "approval_receipts", "actions", "exposures", "gap_changes", "gap_snapshots",
    "personal_protected_ids", "proposals", "evidence", "experiences", "notes",
    "availability", "snapshots", "records", "profile_extras", "contacts",
    "match_cache", "match_refreshes", "course_rec_cache", "a5_failed",
    "research_daily", "research_target", "agent_traces", "last_assessment",
    "emergency_uses", "reminders", "consents", "outreach_queue",
    "tutor_interventions", "counseling_hours", "counseling_bookings",
    "advisor_bookings", "advisor_seq",
    # 机构域
    "opportunities", "expired_opportunities", "withdrawn_opportunities",
    "opportunity_drafts", "submissions", "publishing", "attendance",
    "registered_sources", "source_fetch_status", "metric_tuples", "quality_feedback",
    "metrics_version",
    # 凭据注册表：回来的 PlanItem 仍要过 B8，凭据不在就全被拒
    "validations",
)

#: 不落盘，且有明确理由。
SKIPPED: tuple[str, ...] = (
    "model",                      # 模型客户端：按环境重建
    "catalog", "requirements", "future_offerings",   # 只读目录：seed 派生
    "current_term", "today", "as_of",                # 演示时钟：seed manifest
    "advisors",                   # 按日期确定性生成的名录
    "jobs_lock", "probe_fn", "research_fetch_fn", "runtime_rest_fn",
    "runtime_script_path", "runtime_job", "runtime_status_cache", "runtime_refreshing",
    "draft_jobs", "report_jobs", "sweep_job", "research_jobs",   # 线程态任务
    "derived_metrics_cache",      # 派生缓存：按 metrics_version 重算
    "checkin_secret",             # 密钥：只从环境来
)


def _encode_registry(registry: InMemoryValidationRegistry) -> Any:
    return dict(registry._store)


def _decode_registry(data: dict) -> InMemoryValidationRegistry:
    registry = InMemoryValidationRegistry()
    registry._store.update(data)
    return registry


def install_api_types(codec: Codec) -> Codec:
    """api 层自己的容器进白名单。冷启动解码只认这里与 install_defaults 登记过的类型。"""
    codec.register(InMemoryValidationRegistry, _encode_registry, _decode_registry)
    codec.allow(PublishingService)
    return codec


def fresh_codec() -> Codec:
    """一个"冷"编解码器：只有预填的白名单，没有本进程编码时顺手记住的类型。"""
    return install_api_types(install_defaults(Codec()))


install_api_types(CODEC)


def stamp() -> str:
    """契约或 seed 一变，旧快照就不再可信——宁可冷启动，不把旧形状硬塞进新代码。"""
    return f"contracts/{CONTRACTS_VERSION}+{SEED_VERSION}"


def snapshot(deps: "Deps") -> dict[str, str]:
    with deps.jobs_lock:
        return {
            name: json.dumps(CODEC.encode(getattr(deps, name)), ensure_ascii=False,
                             sort_keys=True)
            for name in MANIFEST
        }


def restore(deps: "Deps", fields: dict[str, str]) -> int:
    """整体覆盖 MANIFEST 里的属性。快照缺的字段保留 seed 初值（向前兼容新容器）。"""
    restored = 0
    with deps.jobs_lock:
        for name in MANIFEST:
            if name not in fields:
                continue
            setattr(deps, name, CODEC.decode(json.loads(fields[name])))
            restored += 1
    return restored


@dataclasses.dataclass(frozen=True)
class RestoreOutcome:
    restored: bool
    reason: str
    fields: int = 0


def restore_from(deps: "Deps", backend: Checkpoint) -> RestoreOutcome:
    loaded = backend.load()
    if loaded is None:
        return RestoreOutcome(False, "empty backend")
    found_stamp, fields = loaded
    if found_stamp != stamp():
        return RestoreOutcome(False, f"stamp mismatch: checkpoint {found_stamp!r} vs code {stamp()!r}")
    return RestoreOutcome(True, "restored", restore(deps, fields))


class Persister:
    """后台写入：每 ``interval`` 秒编码一次，哈希变了才写。"""

    def __init__(self, deps: "Deps", backend: Checkpoint, *, interval: float = 10.0) -> None:
        self.deps = deps
        self.backend = backend
        self.interval = interval
        self.last_digest: str | None = None
        #: 逐字段摘要：只把变了的字段告诉后端（Firestore 据此少写）。
        self.field_digests: dict[str, str] = {}
        self.last_saved_at: float | None = None
        self.saves = 0
        self.last_error: str | None = None
        self.restore_outcome: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def tick(self) -> bool:
        fields = snapshot(self.deps)
        digests = {k: hashlib.sha256(v.encode("utf-8")).hexdigest() for k, v in fields.items()}
        changed = {k for k, d in digests.items() if self.field_digests.get(k) != d}
        if not changed and self.last_digest is not None:
            return False
        self.backend.save(stamp(), fields,
                          changed=None if self.last_digest is None else changed)
        self.field_digests = digests
        self.last_digest = hashlib.sha256("".join(sorted(digests.values())).encode()).hexdigest()
        self.last_saved_at = time.time()
        self.saves += 1
        return True

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                self.tick()
                self.last_error = None
            except Exception as exc:  # noqa: BLE001 —— 后台线程不许死，下一轮再试
                self.last_error = f"save: {type(exc).__name__}: {exc}"[:300]
                log.exception("checkpoint save failed")

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="checkpoint", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            self.tick()                      # 关机前最后一次
        except Exception:  # noqa: BLE001
            log.exception("final checkpoint save failed")


def backend_from_env(env: dict[str, str] | None = None) -> Checkpoint | None:
    env = os.environ if env is None else env
    spec = (env.get(CHECKPOINT_ENV) or "").strip()
    if not spec:
        return None
    if spec.startswith("file:"):
        return FileCheckpoint(spec[len("file:"):])
    if spec == "memory":
        return MemoryCheckpoint()
    if spec.startswith("firestore"):
        _, _, collection = spec.partition(":")
        return FirestoreCheckpoint(
            project=env.get("GOOGLE_CLOUD_PROJECT") or None,
            database=env.get("FIRESTORE_DATABASE") or "(default)",
            collection=collection or "campuspath_checkpoint",
        )
    raise ValueError(f"{CHECKPOINT_ENV}={spec!r} 不认识；用 firestore[:collection] / file:<path> / memory")


def install(app: Any, deps: "Deps") -> Persister | None:
    """按环境接上检查点：启动时回读，之后后台按需写。未配置即 no-op。"""
    backend = backend_from_env()
    if backend is None:
        return None
    persister = Persister(deps, backend)
    # 回读失败**不许**把整个 api 拖死（线上 rev 00020 就是这么启动即崩的）：
    # 记下错误、继续用 seed 起，错误在 GET /v1/ops/agents 的 checkpoint.error 里如实可见。
    try:
        outcome = restore_from(deps, backend)
        log.info("checkpoint %s: %s (%d fields)", backend.describe(), outcome.reason, outcome.fields)
        persister.restore_outcome = outcome.reason
    except Exception as exc:  # noqa: BLE001
        log.exception("checkpoint restore failed; starting from seed")
        persister.last_error = f"restore: {type(exc).__name__}: {exc}"[:300]
        persister.restore_outcome = "failed"
    deps.checkpoint = persister

    @app.on_event("startup")
    def _start() -> None:
        persister.start()

    @app.on_event("shutdown")
    def _stop() -> None:
        persister.stop()

    return persister
