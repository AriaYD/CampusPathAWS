"""P3（2026-08-24）：Deps 的可变状态能整体落检查点、冷启动后原样回来。

验收的本质是一句话：**重启 api 之后，学生刚才批准的规划还在。**
此前它不在——`Deps.__init__` 每次从 seed 重建，Cloud Run 冷启动即清零。

不测后端（Firestore 在 test_checkpoint 与线上实测），这里只测：
1. 快照覆盖 Deps 的可变状态（清单是显式的，新加容器忘了登记会红）；
2. 回来的状态通过既有闸门（B8：pathway 的 validation_id 仍可查验）；
3. 版本戳不匹配时**拒绝**恢复，而不是把旧形状硬塞进新代码。
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from campuspath_api import persistence
from campuspath_api.app import Deps, create_app
from campuspath_state.checkpoint import MemoryCheckpoint
from pathway_flow import adopt_pathway

ROLE = {"X-CampusPath-Role": "student"}


@pytest.fixture
def deps():
    return Deps("full", model=None)


def _mutate(client: TestClient) -> dict:
    """做几件学生会做的事，返回之后要核对的把手。"""
    got = adopt_pathway(client, "STU-A")
    assert got.status_code == 200, got.text
    pathway = got.json()
    item = next(i for i in pathway["plan_items"] if i["kind"] == "opportunity")
    declined = client.delete(
        f"/v1/students/STU-A/pathway/items/{item["plan_item_id"]}", headers=ROLE)
    assert declined.status_code == 200, declined.text
    reflection = client.post("/v1/students/STU-A/reflections", headers=ROLE, json={
        "reflection_id": "REFL-CHECKPOINT", "student_id": "STU-A",
        "subject_id": item["subject_id"], "created_at": "2026-08-24T10:00:00Z",
        "private_text": "checkpoint-probe: private text never leaves the vault",
    })
    assert reflection.status_code == 200, reflection.text
    return {"pathway_id": pathway["pathway_id"], "declined_subject": item["subject_id"]}


def test_manifest_names_only_real_attributes(deps):
    missing = [name for name in persistence.MANIFEST if not hasattr(deps, name)]
    assert missing == [], f"清单里有 Deps 没有的属性：{missing}"


def test_every_mutable_container_is_either_persisted_or_explicitly_skipped(deps):
    """新加一个 `self.xxx = {}` 忘了登记 → 这里红。清单必须是**穷举**的。"""
    attrs = {k for k, v in vars(deps).items()}
    unaccounted = attrs - set(persistence.MANIFEST) - set(persistence.SKIPPED)
    assert unaccounted == set(), (
        f"Deps 属性既不在 MANIFEST 也不在 SKIPPED：{sorted(unaccounted)}")
    assert not set(persistence.MANIFEST) & set(persistence.SKIPPED)


def test_roundtrip_restores_student_decisions(deps):
    client = TestClient(create_app(deps))
    handles = _mutate(client)
    fields = persistence.snapshot(deps)
    assert set(fields) == set(persistence.MANIFEST)
    for value in fields.values():
        json.loads(value)                       # 每个字段都是合法 JSON 文本

    fresh = Deps("full", model=None)
    assert "STU-A" not in fresh.pathways        # 冷启动：seed 里没有已采纳规划
    persistence.restore(fresh, fields)
    client2 = TestClient(create_app(fresh))

    got = client2.get("/v1/students/STU-A/pathway", headers=ROLE)
    assert got.status_code == 200, got.text
    assert got.json()["pathway_id"] == handles["pathway_id"]
    assert all(i["subject_id"] != handles["declined_subject"] for i in got.json()["plan_items"])
    assert any(r.reflection_id == "REFL-CHECKPOINT" for r in fresh.reflections["STU-A"])
    # B8：回来的每一项凭据仍能被查验（validations 也在快照里）
    for item in got.json()["plan_items"]:
        assert fresh.validations.get(item["validation_id"]) is not None


def test_persister_saves_only_when_state_changed(deps):
    backend = MemoryCheckpoint()
    persister = persistence.Persister(deps, backend, interval=999)
    assert persister.tick() is True             # 第一次：有东西就存
    assert persister.tick() is False            # 没变：不写
    client = TestClient(create_app(deps))
    _mutate(client)
    assert persister.tick() is True
    stamp, fields = backend.load()
    assert stamp == persistence.stamp()
    assert "pathways" in fields


def test_restore_refuses_mismatched_stamp(deps):
    backend = MemoryCheckpoint()
    backend.save("contracts/0.0.0+seed/0.0.0", persistence.snapshot(deps))
    outcome = persistence.restore_from(deps, backend)
    assert outcome.restored is False and "stamp" in outcome.reason


def test_restore_from_backend_reports_what_it_did(deps):
    backend = MemoryCheckpoint()
    assert persistence.restore_from(deps, backend).restored is False   # 空后端
    client = TestClient(create_app(deps))
    handles = _mutate(client)
    persistence.Persister(deps, backend, interval=999).tick()
    fresh = Deps("full", model=None)
    outcome = persistence.restore_from(fresh, backend)
    assert outcome.restored is True and outcome.fields == len(persistence.MANIFEST)
    assert fresh.pathways["STU-A"].pathway_id == handles["pathway_id"]


def test_install_is_a_noop_without_configuration(deps, monkeypatch):
    monkeypatch.delenv(persistence.CHECKPOINT_ENV, raising=False)
    assert persistence.backend_from_env() is None


def test_file_backend_from_env(deps, monkeypatch, tmp_path):
    monkeypatch.setenv(persistence.CHECKPOINT_ENV, f"file:{tmp_path / 'c.json'}")
    backend = persistence.backend_from_env()
    assert type(backend).__name__ == "FileCheckpoint"


def test_lifespan_restores_on_boot_and_flushes_on_shutdown(monkeypatch, tmp_path):
    """真正接线的那条路：环境变量 → create_app 回读 → 关机最后一次落盘 → 下次启动回来。"""
    monkeypatch.setenv(persistence.CHECKPOINT_ENV, f"file:{tmp_path / 'ckpt.json'}")
    first = Deps("full", model=None)
    with TestClient(create_app(first)) as client:      # 进入 = startup，退出 = shutdown
        handles = _mutate(client)
    assert (tmp_path / "ckpt.json").exists(), "关机时没有落盘"

    second = Deps("full", model=None)
    assert "STU-A" not in second.pathways
    with TestClient(create_app(second)) as client:
        got = client.get("/v1/students/STU-A/pathway", headers=ROLE)
    assert got.status_code == 200 and got.json()["pathway_id"] == handles["pathway_id"]
    assert second.checkpoint.saves >= 0 and second.checkpoint.backend.describe().startswith("file:")


def test_persister_tells_backend_which_fields_changed(deps):
    class Spy(MemoryCheckpoint):
        calls: list = []

        def save(self, stamp, fields, *, changed=None):
            self.calls.append(changed)
            super().save(stamp, fields, changed=changed)

    spy = Spy()
    persister = persistence.Persister(deps, spy, interval=999)
    persister.tick()
    assert spy.calls == [None]                       # 首次：全写
    client = TestClient(create_app(deps))
    _mutate(client)
    persister.tick()
    changed = spy.calls[1]
    assert changed and changed < set(persistence.MANIFEST)      # 只有一部分字段
    assert {"pathways", "declined", "reflections"} <= changed


def test_cold_process_can_decode_every_field(deps):
    """冷启动的进程没编码过任何东西——白名单必须**预先**齐全，而不是靠编码时顺手登记。"""
    client = TestClient(create_app(deps))
    _mutate(client)
    fields = persistence.snapshot(deps)
    cold = persistence.fresh_codec()
    for name, text in fields.items():
        cold.decode(json.loads(text))          # 任一字段缺白名单即 TypeError


def test_decode_refuses_types_outside_the_allowlist():
    from campuspath_state.codec import Codec

    hostile = {"__t__": "dataclass", "cls": "os:system", "__v__": {}}
    with pytest.raises(TypeError):
        Codec().decode(hostile)


def test_restore_failure_does_not_kill_the_app(monkeypatch, tmp_path):
    """线上 rev 00020 的教训：回读抛异常曾让 uvicorn 在 import 时就退出。现在：起来、记错、如实报。"""
    path = tmp_path / "broken.json"
    path.write_text("{not json")
    monkeypatch.setenv(persistence.CHECKPOINT_ENV, f"file:{path}")
    deps = Deps("full", model=None)
    client = TestClient(create_app(deps))                 # 不抛
    assert deps.checkpoint.restore_outcome == "failed"
    assert deps.checkpoint.last_error and "restore:" in deps.checkpoint.last_error
    body = client.get("/v1/ops/agents", headers={"X-CampusPath-Role": "career_center_admin"}).json()
    assert body["checkpoint"]["enabled"] is True and body["checkpoint"]["error"].startswith("restore:")
    assert body["checkpoint"]["restore_outcome"] == "failed"


def test_mutating_requests_checkpoint_inline(monkeypatch, tmp_path):
    """Cloud Run 请求间掐 CPU：不能指望后台线程，写请求返回前就得落盘。"""
    path = tmp_path / "ckpt.json"
    monkeypatch.setenv(persistence.CHECKPOINT_ENV, f"file:{path}")
    deps = Deps("full", model=None)
    client = TestClient(create_app(deps))            # 不进 with：startup 不跑，后台线程不起
    assert not path.exists()
    client.get("/v1/students/STU-A/profile", headers=ROLE)
    assert not path.exists(), "GET 不该触发落盘"
    _mutate(client)
    assert path.exists() and deps.checkpoint.saves >= 1
    assert deps.checkpoint.tick_if_due(min_interval=60) is False   # 刚存过：合并
