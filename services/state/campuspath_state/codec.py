"""通用编解码：把进程内状态变成 JSON 能装的东西，再原样变回来。

设计原则只有一条：**类型信息随数据走**。Pydantic 模型记 ``module:Class``，
dataclass 同理，日期、集合、元组、枚举各有标记——解码时不需要知道
"这个字段本来是什么"，所以 Deps 上的容器可以整体登记、不必逐字段写 schema。

不认识的类型**抛异常**而不是 ``str()``：静默降级成字符串的话，
下次冷启动时那个字段会以字符串身份回来，错在离出错点很远的地方。

**解码只认白名单**：类型引用串查 :attr:`Codec._types`，不做动态 import。
检查点是外部输入（Firestore 文档谁都可能改），让它指定"请实例化哪个类"
等于把反序列化交给数据；零 LLM 扫描的第四层（动态导入）也因此干净。
"""

from __future__ import annotations

import dataclasses
import enum
import sys
from datetime import date, datetime
from typing import Any, Callable

from pydantic import BaseModel

_TYPE = "__t__"      # 标记键：值是类型标签
_VALUE = "__v__"


def _ref(cls: type) -> str:
    return f"{cls.__module__}:{cls.__qualname__}"


class Codec:
    """可注册自定义类型的编解码器。模块级 :func:`encode` / :func:`decode` 用默认实例。"""

    def __init__(self) -> None:
        self._custom: dict[type, tuple[Callable[[Any], Any], Callable[[Any], Any]]] = {}
        #: 解码按注册时的引用串查表——本地类/闭包类 import 不回来，注册表回得来。
        self._custom_by_ref: dict[str, tuple[Callable[[Any], Any], Callable[[Any], Any]]] = {}
        #: dataclass 字段跳过表：锁、线程等不可序列化且可重建的字段。
        self._skip_fields: dict[type, frozenset[str]] = {}
        #: 解码白名单：引用串 → 类。编码时登记，冷启动前由 install_* 预填。
        self._types: dict[str, type] = {}

    def allow(self, *classes: type) -> None:
        for cls in classes:
            self._types[_ref(cls)] = cls

    def allow_from_modules(self, prefix: str) -> int:
        """把已导入的、模块名以 ``prefix`` 开头的 Pydantic 模型与枚举全部列入白名单。
        只看 ``sys.modules``，不导入任何东西。"""
        count = 0
        for name, module in list(sys.modules.items()):
            if not (name == prefix or name.startswith(prefix + ".")) or module is None:
                continue
            for attr in vars(module).values():
                if isinstance(attr, type) and attr.__module__ == name and (
                    issubclass(attr, BaseModel) or issubclass(attr, enum.Enum)
                ):
                    self._types[_ref(attr)] = attr
                    count += 1
        return count

    def _resolve(self, ref: str) -> type:
        try:
            return self._types[ref]
        except KeyError:
            raise TypeError(f"codec 白名单里没有 {ref}；先 allow() 它") from None

    def _remember(self, cls: type) -> str:
        ref = _ref(cls)
        self._types.setdefault(ref, cls)
        return ref

    def register(self, cls: type, encode_fn: Callable[[Any], Any],
                 decode_fn: Callable[[Any], Any]) -> None:
        self._custom[cls] = (encode_fn, decode_fn)
        self._custom_by_ref[_ref(cls)] = (encode_fn, decode_fn)

    def skip_dataclass_fields(self, cls: type, *names: str) -> None:
        self._skip_fields[cls] = frozenset(names)

    # ── encode ──────────────────────────────────────────────────────

    def encode(self, value: Any) -> Any:
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        for cls, (encode_fn, _) in self._custom.items():
            if isinstance(value, cls):
                return {_TYPE: "custom", "cls": _ref(cls), _VALUE: self.encode(encode_fn(value))}
        if isinstance(value, enum.Enum):
            return {_TYPE: "enum", "cls": self._remember(type(value)), _VALUE: value.value}
        if isinstance(value, datetime):
            return {_TYPE: "datetime", _VALUE: value.isoformat()}
        if isinstance(value, date):
            return {_TYPE: "date", _VALUE: value.isoformat()}
        if isinstance(value, BaseModel):
            return {_TYPE: "model", "cls": self._remember(type(value)),
                    _VALUE: value.model_dump(mode="json")}
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            skip = self._skip_fields.get(type(value), frozenset())
            fields = {f.name: self.encode(getattr(value, f.name))
                      for f in dataclasses.fields(value) if f.name not in skip}
            return {_TYPE: "dataclass", "cls": self._remember(type(value)), _VALUE: fields}
        if isinstance(value, tuple):
            return {_TYPE: "tuple", _VALUE: [self.encode(v) for v in value]}
        if isinstance(value, (set, frozenset)):
            return {_TYPE: "set", _VALUE: [self.encode(v) for v in value]}
        if isinstance(value, list):
            return [self.encode(v) for v in value]
        if isinstance(value, dict):
            if all(isinstance(k, str) for k in value) and _TYPE not in value:
                return {k: self.encode(v) for k, v in value.items()}
            return {_TYPE: "dict", _VALUE: [[self.encode(k), self.encode(v)] for k, v in value.items()]}
        raise TypeError(f"codec 不认识 {type(value).__qualname__}；请 register() 或登记跳过")

    # ── decode ──────────────────────────────────────────────────────

    def decode(self, value: Any) -> Any:
        if isinstance(value, list):
            return [self.decode(v) for v in value]
        if not isinstance(value, dict):
            return value
        tag = value.get(_TYPE)
        if tag is None:
            return {k: self.decode(v) for k, v in value.items()}
        payload = value.get(_VALUE)
        if tag == "custom":
            try:
                _, decode_fn = self._custom_by_ref[value["cls"]]
            except KeyError:
                raise TypeError(f"codec 没有 {value['cls']} 的解码器；先 register()") from None
            return decode_fn(self.decode(payload))
        if tag == "enum":
            return self._resolve(value["cls"])(payload)
        if tag == "datetime":
            return datetime.fromisoformat(payload)
        if tag == "date":
            return date.fromisoformat(payload)
        if tag == "model":
            return self._resolve(value["cls"]).model_validate(payload)
        if tag == "dataclass":
            cls = self._resolve(value["cls"])
            fields = {k: self.decode(v) for k, v in payload.items()}
            return cls(**fields)
        if tag == "tuple":
            return tuple(self.decode(v) for v in payload)
        if tag == "set":
            return {self.decode(v) for v in payload}
        if tag == "dict":
            return {self.decode(k): self.decode(v) for k, v in payload}
        raise TypeError(f"codec 不认识标记 {tag!r}")


DEFAULT = Codec()


def encode(value: Any) -> Any:
    return DEFAULT.encode(value)


def decode(value: Any) -> Any:
    return DEFAULT.decode(value)


# ── 本包自己的容器 ────────────────────────────────────────────────
from .exposure import ExposureLog as _ExposureLog, ExposureStore as _ExposureStore  # noqa: E402
from .store import (  # noqa: E402
    InMemoryMemoryProvider as _InMemoryMemoryProvider,
    StudentStateStore as _StudentStateStore,
)


def _encode_exposure_store(store: _ExposureStore) -> Any:
    return dict(store._logs)


def _decode_exposure_store(logs: dict) -> _ExposureStore:
    store = _ExposureStore()
    store._logs.update(logs)
    return store


def install_defaults(codec: Codec) -> Codec:
    """冷启动前必须调用：契约模型与本包容器进白名单。``DEFAULT`` 已装好。"""
    import campuspath_contracts  # noqa: F401,PLC0415 —— 字面量导入；其 __init__ 会把全部子模块带进来

    codec.allow_from_modules("campuspath_contracts")
    codec.allow(_StudentStateStore, _ExposureLog, _InMemoryMemoryProvider)
    # 锁不可序列化且可重建：跳过后由 dataclass 默认工厂重新造一把。
    codec.skip_dataclass_fields(_InMemoryMemoryProvider, "_mutex")
    codec.register(_ExposureStore, _encode_exposure_store, _decode_exposure_store)
    return codec


install_defaults(DEFAULT)
