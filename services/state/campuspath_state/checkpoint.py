"""检查点后端：一份带版本戳的「字段名 → JSON 文本」。

三个实现同一个协议：
* :class:`MemoryCheckpoint` —— 测试；
* :class:`FileCheckpoint` —— 本地开发（临时文件 + 原子替换，写一半崩掉不毁上一份）；
* :class:`FirestoreCheckpoint` —— 线上（Cloud Run 服务账号 ADC，**REST**）。
  Firestore 单文档 1 MiB 上限，所以每个字段独立成文档，超限的字段切块。

**零 LLM**：本模块只 import ``google.auth``（延迟），不碰任何模型 SDK。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

Fields = dict[str, str]

#: Firestore 字符串字段的安全上限（文档上限 1 MiB，留出键与开销）。
CHUNK_LIMIT = 900_000


@runtime_checkable
class Checkpoint(Protocol):
    def save(self, stamp: str, fields: Fields, *, changed: set[str] | None = None) -> None:
        """``changed`` 是提示：只有这些字段与上次不同。后端可据此少写；
        传 None 表示全写。语义上 ``fields`` 永远是完整的一份。"""
        ...

    def load(self) -> tuple[str, Fields] | None: ...

    def describe(self) -> str: ...


def chunk_text(text: str, *, limit: int | None = None) -> list[str]:
    """按 UTF-8 字节数切块，不切开多字节字符。``limit`` 缺省读模块常量（调用时求值，测试可改）。"""
    limit = CHUNK_LIMIT if limit is None else limit
    data = text.encode("utf-8")
    if len(data) <= limit:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(data):
        end = min(start + limit, len(data))
        # 退到字符边界：UTF-8 续字节以 10xxxxxx 开头
        while end < len(data) and (data[end] & 0xC0) == 0x80:
            end -= 1
        chunks.append(data[start:end].decode("utf-8"))
        start = end
    return chunks


def unchunk_text(chunks: list[str]) -> str:
    return "".join(chunks)


class MemoryCheckpoint:
    def __init__(self) -> None:
        self._state: tuple[str, Fields] | None = None

    def save(self, stamp: str, fields: Fields, *, changed: set[str] | None = None) -> None:
        self._state = (stamp, dict(fields))

    def load(self) -> tuple[str, Fields] | None:
        return None if self._state is None else (self._state[0], dict(self._state[1]))

    def describe(self) -> str:
        return "memory"


class FileCheckpoint:
    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)

    def save(self, stamp: str, fields: Fields, *, changed: set[str] | None = None) -> None:
        tmp = self.path.with_name(self.path.name + ".tmp")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps({"stamp": stamp, "fields": fields}, ensure_ascii=False))
        os.replace(tmp, self.path)

    def load(self) -> tuple[str, Fields] | None:
        if not self.path.exists():
            return None
        data = json.loads(self.path.read_text())
        return data["stamp"], dict(data["fields"])

    def describe(self) -> str:
        return f"file:{self.path}"


class FirestoreCheckpoint:
    """Firestore **REST** 后端（`documents:commit` / `listDocuments`）。

    为什么不用 ``google-cloud-firestore`` 的 gRPC 客户端：同一版本在本机正常、在 Cloud Run
    容器里把路由头的 ``(default)`` 编成 ``%28default%29`` → 400（rev 00020–00022 实测，
    钉 api-core 版本也没用）。REST 路径里的括号没有歧义，依赖只剩 google-auth + requests
    （二者本来就随 google-genai 装着）。

    布局：``<collection>/_meta`` 存版本戳与「字段 → 块数」；``<collection>/<field>`` 存文本，
    超限字段存为 ``<field>__<n>``。**少写**：``changed`` 给了就只写那些字段（外加 ``_meta``），
    一次 commit（≤ 500 写）原子提交；**少读**：``listDocuments`` 分页取整个集合。
    """

    META = "_meta"
    SCOPE = "https://www.googleapis.com/auth/datastore"
    MAX_WRITES = 450          # Firestore 单次 commit 上限 500，留余量

    def __init__(self, *, project: str | None = None, database: str = "(default)",
                 collection: str = "campuspath_checkpoint", session: Any | None = None) -> None:
        self.project = project
        self.database = database or "(default)"
        self.collection = collection
        self._session = session
        self._layout: dict[str, int] | None = None

    # ── 连接 ────────────────────────────────────────────────────────

    def _http(self) -> Any:
        if self._session is None:
            import google.auth  # noqa: PLC0415  # 延迟：本地/测试不需要
            from google.auth.transport.requests import AuthorizedSession  # noqa: PLC0415

            credentials, detected = google.auth.default(scopes=[self.SCOPE])
            if not self.project:
                self.project = detected
            self._session = AuthorizedSession(credentials)
        return self._session

    @property
    def _parent(self) -> str:
        return f"projects/{self.project}/databases/{self.database}/documents"

    def _url(self, suffix: str) -> str:
        return f"https://firestore.googleapis.com/v1/{self._parent}{suffix}"

    def _doc_name(self, doc_id: str) -> str:
        return f"{self._parent}/{self.collection}/{doc_id}"

    # ── 写 ──────────────────────────────────────────────────────────

    def save(self, stamp: str, fields: Fields, *, changed: set[str] | None = None) -> None:
        http = self._http()
        if changed is None or self._layout is None:
            to_write = dict(fields)
            layout: dict[str, int] = {}
        else:
            to_write = {k: v for k, v in fields.items() if k in changed}
            layout = {k: n for k, n in self._layout.items() if k in fields}
        writes: list[dict[str, Any]] = []
        for name, text in to_write.items():
            chunks = chunk_text(text)
            previous = layout.get(name, 0)
            layout[name] = len(chunks)
            if len(chunks) == 1:
                writes.append(self._update(name, {"text": text}))
            else:
                for index, chunk in enumerate(chunks):
                    writes.append(self._update(f"{name}__{index}", {"text": chunk}))
            for index in range(max(len(chunks), 1), previous):
                writes.append({"delete": self._doc_name(f"{name}__{index}")})
        writes.append(self._update(self.META, {"stamp": stamp, "layout_json": json.dumps(layout)}))
        # 分批提交；_meta 在最后一批——读侧以它为准，前面批次失败不会留下"指向不存在字段"的布局
        for start in range(0, len(writes), self.MAX_WRITES):
            self._commit(http, writes[start:start + self.MAX_WRITES])
        self._layout = layout

    def _update(self, doc_id: str, values: dict[str, str]) -> dict[str, Any]:
        return {"update": {"name": self._doc_name(doc_id),
                           "fields": {k: {"stringValue": v} for k, v in values.items()}}}

    def _commit(self, http: Any, writes: list[dict[str, Any]]) -> None:
        response = http.post(self._url(":commit"), json={"writes": writes}, timeout=60)
        if response.status_code >= 300:
            raise RuntimeError(f"firestore commit {response.status_code}: {response.text[:300]}")

    # ── 读 ──────────────────────────────────────────────────────────

    def load(self) -> tuple[str, Fields] | None:
        http = self._http()
        docs: dict[str, dict[str, str]] = {}
        token: str | None = None
        while True:
            params: dict[str, Any] = {"pageSize": 300}
            if token:
                params["pageToken"] = token
            response = http.get(self._url(f"/{self.collection}"), params=params, timeout=60)
            if response.status_code >= 300:
                raise RuntimeError(f"firestore list {response.status_code}: {response.text[:300]}")
            body = response.json()
            for doc in body.get("documents", []):
                doc_id = doc["name"].rsplit("/", 1)[-1]
                docs[doc_id] = {k: v.get("stringValue", "") for k, v in doc.get("fields", {}).items()}
            token = body.get("nextPageToken")
            if not token:
                break
        meta = docs.get(self.META)
        if meta is None:
            return None
        layout = json.loads(meta.get("layout_json") or "{}")
        fields: Fields = {}
        for name, count in layout.items():
            if count == 1:
                fields[name] = docs[name]["text"]
            else:
                fields[name] = unchunk_text([docs[f"{name}__{i}"]["text"] for i in range(count)])
        self._layout = layout
        return meta["stamp"], fields

    def describe(self) -> str:
        return f"firestore:{self.database}/{self.collection}"
