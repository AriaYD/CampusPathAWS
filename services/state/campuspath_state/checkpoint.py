"""检查点后端：一份带版本戳的「字段名 → JSON 文本」。

三个实现同一个协议：
* :class:`MemoryCheckpoint` —— 测试；
* :class:`FileCheckpoint` —— 本地开发（临时文件 + 原子替换，写一半崩掉不毁上一份）；
* :class:`FirestoreCheckpoint` —— 线上（Cloud Run 服务账号 ADC）。
  Firestore 单文档 1 MiB 上限，所以每个字段独立成文档，超限的字段切块。

**零 LLM**：本模块只 import ``google.cloud.firestore``（延迟），不碰任何模型 SDK。
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


def chunk_text(text: str, *, limit: int = CHUNK_LIMIT) -> list[str]:
    """按 UTF-8 字节数切块，不切开多字节字符。"""
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
    """``<collection>/_meta`` 存版本戳与字段布局；``<collection>/<field>`` 存文本，
    超限字段存为 ``<field>#<n>`` 若干文档。

    **少写**：``changed`` 给了就只写那些字段（外加 ``_meta``），一次 batch 提交；
    12 名学生的全部状态约 1 MB / 56 字段，一次典型操作只动 2–5 个字段。
    **少读**：``load`` 用一条查询流式取整个集合，而不是逐文档 get。
    先写字段再写 ``_meta``（同一 batch 原子提交），读侧以 ``_meta`` 的布局为准。
    """

    META = "_meta"

    def __init__(self, *, project: str | None = None, database: str = "(default)",
                 collection: str = "campuspath_checkpoint") -> None:
        self.project = project
        self.database = database
        self.collection = collection
        self._client: Any | None = None
        #: 上次已知布局（字段 → 块数）。changed 模式下未动的字段沿用它。
        self._layout: dict[str, int] | None = None

    def _col(self) -> Any:
        if self._client is None:
            from google.cloud import firestore  # noqa: PLC0415  # 延迟：本地/测试不需要

            self._client = firestore.Client(project=self.project, database=self.database)
        return self._client.collection(self.collection)

    def save(self, stamp: str, fields: Fields, *, changed: set[str] | None = None) -> None:
        col = self._col()
        if changed is None or self._layout is None:
            to_write = dict(fields)
            layout: dict[str, int] = {}
        else:
            to_write = {k: v for k, v in fields.items() if k in changed}
            layout = {k: n for k, n in self._layout.items() if k in fields}
        batch = self._client.batch()
        ops = 0
        for name, text in to_write.items():
            chunks = chunk_text(text)
            previous = layout.get(name, 0)
            layout[name] = len(chunks)
            if len(chunks) == 1:
                batch.set(col.document(name), {"text": text}); ops += 1
            else:
                for index, chunk in enumerate(chunks):
                    batch.set(col.document(f"{name}#{index}"), {"text": chunk}); ops += 1
            # 块数变少时清掉多余的旧块，免得下次布局对不上
            for index in range(len(chunks), previous):
                batch.delete(col.document(f"{name}#{index}")); ops += 1
            if ops >= 400:                      # Firestore 单 batch 上限 500
                batch.commit(); batch = self._client.batch(); ops = 0
        batch.set(col.document(self.META), {"stamp": stamp, "layout": layout})
        batch.commit()
        self._layout = layout

    def load(self) -> tuple[str, Fields] | None:
        col = self._col()
        docs = {doc.id: (doc.to_dict() or {}) for doc in col.stream()}
        meta = docs.get(self.META)
        if meta is None:
            return None
        layout = dict(meta.get("layout", {}))
        fields: Fields = {}
        for name, count in layout.items():
            if count == 1:
                fields[name] = docs[name]["text"]
            else:
                fields[name] = unchunk_text([docs[f"{name}#{i}"]["text"] for i in range(count)])
        self._layout = layout
        return meta["stamp"], fields

    def describe(self) -> str:
        return f"firestore:{self.database}/{self.collection}"
