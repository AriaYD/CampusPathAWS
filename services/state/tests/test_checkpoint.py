"""检查点（P3，2026-08-24）：编解码器与后端。

进程内状态在 Cloud Run 冷启动即丢，是评审「状态管理」一项最大的短板。
这里不改任何容器的形态——只保证**任何**一份进程内状态都能原样落盘、原样回来。
"""

from __future__ import annotations

import dataclasses
import json
import threading
from datetime import date, datetime, timezone
from enum import Enum

import pytest

from campuspath_contracts.memory import MemoryEntry
from campuspath_contracts.profile import StudentProfile
from campuspath_state.checkpoint import (
    Checkpoint,
    FileCheckpoint,
    MemoryCheckpoint,
    chunk_text,
    unchunk_text,
)
from campuspath_state.codec import Codec, decode, encode
from campuspath_state.exposure import ExposureEvent, ExposureStore
from campuspath_state.store import InMemoryMemoryProvider, StudentStateStore


class Colour(Enum):
    RED = "red"


def _memory(memory_id: str) -> MemoryEntry:
    return MemoryEntry(
        memory_id=memory_id, student_id="STU-A", type="preference",
        origin="student_statement", content="prefers evening study",
        source_event_id="EVT-1", valid_from=datetime(2026, 8, 1, tzinfo=timezone.utc))


def _roundtrip(value):
    text = json.dumps(encode(value), ensure_ascii=False)
    return decode(json.loads(text))


def test_scalars_dates_and_containers_roundtrip():
    value = {
        "when": date(2026, 8, 24),
        "at": datetime(2026, 8, 24, 3, 55, tzinfo=timezone.utc),
        "tags": {"a", "b"},
        "pair": (1, "x"),
        "nested": [{"deep": (date(2026, 1, 1),)}],
        "colour": Colour.RED,
        "none": None,
    }
    back = _roundtrip(value)
    assert back == value
    assert isinstance(back["tags"], set) and isinstance(back["pair"], tuple)
    assert isinstance(back["colour"], Colour)


def test_dict_with_tuple_keys_roundtrips():
    """Deps 里大量 ``dict[tuple[str, date], int]``——JSON 的键只能是字符串。"""
    value = {("STU-A", date(2026, 8, 24)): 3, ("STU-B", date(2026, 8, 25)): 1}
    assert _roundtrip(value) == value


def test_pydantic_models_roundtrip_by_reference():
    entry = _memory("MEM-1")
    back = _roundtrip({"x": [entry]})
    assert back["x"][0] == entry and type(back["x"][0]) is MemoryEntry


def test_dataclass_containers_roundtrip_including_private_fields():
    from campuspath_seed.build import build_seed

    profile = StudentProfile(**build_seed("tiny")["students"][0])
    store = StudentStateStore(profile=profile)
    back = _roundtrip(store)
    assert isinstance(back, StudentStateStore)
    assert back.profile == profile
    assert back.events == ()


def test_memory_provider_skips_its_lock_and_keeps_sequence():
    provider = InMemoryMemoryProvider()
    provider.write(_memory("MEM-1"))
    provider.next_sequence(); provider.next_sequence()
    back = _roundtrip(provider)
    assert isinstance(back, InMemoryMemoryProvider)
    assert set(back.entries) == {"MEM-1"}
    assert back.next_sequence() == 3           # 序号不回退，否则会撞号
    assert isinstance(back._mutex, type(threading.RLock()))


def test_exposure_store_keeps_dedup_keys():
    store = ExposureStore()
    event = ExposureEvent(
        event_id="EXP-1", student_id="STU-A", subject_id="OPP-1", surface="for_you",
        depth="detail", occurred_at=datetime(2026, 8, 24, 10, tzinfo=timezone.utc),
        period="2026-27_FALL")
    store.log_for("STU-A").record((event,))
    back = _roundtrip(store)
    accepted, deduplicated = back.log_for("STU-A").record((event,))
    assert (accepted, deduplicated) == (0, 1), "去重键没回来，同一条曝光会被记两次"


def test_unknown_type_is_a_loud_error_not_a_string():
    class Opaque:
        pass

    with pytest.raises(TypeError):
        encode({"x": Opaque()})


def test_custom_codec_registration():
    class Counter:
        def __init__(self, n: int) -> None:
            self.n = n

    codec = Codec()
    codec.register(Counter, lambda c: {"n": c.n}, lambda d: Counter(d["n"]))
    back = codec.decode(json.loads(json.dumps(codec.encode({"c": Counter(7)}))))
    assert isinstance(back["c"], Counter) and back["c"].n == 7


# ── 后端 ────────────────────────────────────────────────────────────

def test_memory_and_file_checkpoint_roundtrip(tmp_path):
    for backend in (MemoryCheckpoint(), FileCheckpoint(tmp_path / "ckpt.json")):
        assert backend.load() is None
        backend.save("stamp-1", {"a": "[1, 2]", "b": "{}"})
        assert backend.load() == ("stamp-1", {"a": "[1, 2]", "b": "{}"})
        assert isinstance(backend, Checkpoint)


def test_chunking_splits_and_rejoins_large_strings():
    text = "é" * 10_000
    chunks = chunk_text(text, limit=4096)
    assert len(chunks) > 1 and all(len(c.encode("utf-8")) <= 4096 for c in chunks)
    assert unchunk_text(chunks) == text


def test_file_checkpoint_survives_partial_write(tmp_path):
    """写一半崩掉不能把上一份也毁了：先写临时文件再原子替换。"""
    path = tmp_path / "ckpt.json"
    backend = FileCheckpoint(path)
    backend.save("s", {"a": "1"})
    (tmp_path / "ckpt.json.tmp").write_text("{garbage")
    assert backend.load() == ("s", {"a": "1"})
