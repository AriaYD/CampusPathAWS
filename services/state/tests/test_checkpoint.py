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


class _FakeResponse:
    def __init__(self, status: int, body: dict):
        self.status_code = status; self._body = body; self.text = json.dumps(body)

    def json(self):
        return self._body


class _FakeSession:
    """记录请求；listDocuments 返回上次 commit 写进去的文档。"""

    def __init__(self):
        self.posts: list[tuple[str, dict]] = []
        self.gets: list[tuple[str, dict]] = []
        self.store: dict[str, dict] = {}

    def post(self, url, json, timeout):
        self.posts.append((url, json))
        for w in json["writes"]:
            if "update" in w:
                self.store[w["update"]["name"]] = w["update"]["fields"]
            else:
                self.store.pop(w["delete"], None)
        return _FakeResponse(200, {})

    def get(self, url, params, timeout):
        self.gets.append((url, params))
        docs = [{"name": n, "fields": f} for n, f in self.store.items()]
        return _FakeResponse(200, {"documents": docs})


def _rest(session):
    from campuspath_state.checkpoint import FirestoreCheckpoint

    return FirestoreCheckpoint(project="p", collection="ckpt", session=session)


def test_firestore_rest_urls_keep_default_database_literal():
    """gRPC 客户端在容器里把 (default) 编成 %28default%29 → 400；REST 路径里必须是字面量。"""
    session = _FakeSession()
    _rest(session).save("s1", {"a": "1"})
    url, body = session.posts[0]
    assert url == "https://firestore.googleapis.com/v1/projects/p/databases/(default)/documents:commit"
    assert body["writes"][0]["update"]["name"] == "projects/p/databases/(default)/documents/ckpt/a"
    assert body["writes"][-1]["update"]["name"].endswith("/ckpt/_meta")


def test_firestore_rest_roundtrip_with_chunks(monkeypatch):
    import campuspath_state.checkpoint as ck

    monkeypatch.setattr(ck, "CHUNK_LIMIT", 8)
    session = _FakeSession()
    backend = _rest(session)
    big = "é" * 20
    backend.save("s1", {"big": big, "small": "x"})
    fresh = _rest(session)                    # 新进程：没有内存布局，只能靠 _meta
    assert fresh.load() == ("s1", {"big": big, "small": "x"})
    assert any(n.endswith("/ckpt/big__0") for n in session.store)


def test_firestore_rest_changed_only_writes_a_subset_and_prunes_old_chunks(monkeypatch):
    import campuspath_state.checkpoint as ck

    monkeypatch.setattr(ck, "CHUNK_LIMIT", 8)
    session = _FakeSession()
    backend = _rest(session)
    backend.save("s1", {"big": "é" * 20, "small": "x"})
    backend.save("s1", {"big": "y", "small": "x"}, changed={"big"})     # big 从 5 块缩成 1 个文档
    _, body = session.posts[-1]
    names = [w.get("update", {}).get("name") or w.get("delete") for w in body["writes"]]
    assert not any(n.endswith("/ckpt/small") for n in names), "未变字段不该重写"
    assert any(w.get("delete", "").endswith("/ckpt/big__1") for w in body["writes"]), "多余旧块要删"
    assert _rest(session).load() == ("s1", {"big": "y", "small": "x"})


def test_firestore_rest_reports_http_errors_loudly():
    class Failing(_FakeSession):
        def post(self, url, json, timeout):
            return _FakeResponse(400, {"error": "Invalid database id %28default%29"})

    with pytest.raises(RuntimeError, match="400"):
        _rest(Failing()).save("s", {"a": "1"})
