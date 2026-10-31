"""Export JSON Schemas and a generated field reference from the Pydantic models.

``docs/schemas/*.json`` and ``docs/PROTOCOL_REFERENCE.md`` are build artefacts: a test
checks they match the models, so the documentation cannot drift from the code.
"""

from __future__ import annotations

import json
import types
import typing
from enum import Enum
from pathlib import Path
from typing import Any, get_args, get_origin

from pydantic import BaseModel, TypeAdapter
from pydantic.fields import FieldInfo

from netcoop.protocol.capability import CapabilityCard
from netcoop.protocol.common import PROTOCOL_VERSION
from netcoop.protocol.messages import MESSAGE_CLASSES, Envelope, Message
from netcoop.protocol.report import Report
from netcoop.protocol.vocabulary import get_vocabulary

DOCS = Path(__file__).resolve().parents[2] / "docs"
SCHEMA_DIR = DOCS / "schemas"
REFERENCE = DOCS / "PROTOCOL_REFERENCE.md"


def build_schemas() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {
        "message.json": TypeAdapter(Message).json_schema(),
        "capability_card.json": CapabilityCard.model_json_schema(),
        "report.json": Report.model_json_schema(),
    }
    for t, cls in MESSAGE_CLASSES.items():
        out[f"messages/{t.value.lower()}.json"] = cls.model_json_schema()
    for name, schema in out.items():
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["$id"] = f"netcoop/{PROTOCOL_VERSION}/{name}"
    return out


# ----------------------------------------------------------------------------- reference
def _type_str(tp: Any) -> str:
    origin = get_origin(tp)
    if origin is typing.Literal:
        return "const"
    if origin in (typing.Union, types.UnionType):
        return " | ".join(_type_str(a) for a in get_args(tp))
    if origin is tuple:
        args = [a for a in get_args(tp) if a is not Ellipsis]
        return f"list[{_type_str(args[0])}]" if args else "list"
    if origin is dict:
        k, v = get_args(tp)
        return f"map[{_type_str(k)}, {_type_str(v)}]"
    if tp is type(None):
        return "null"
    if isinstance(tp, type) and issubclass(tp, Enum):
        return "enum"
    if isinstance(tp, type) and issubclass(tp, BaseModel):
        return f"[{tp.__name__}](#{tp.__name__.lower()})"
    names = {str: "string", float: "number", int: "integer", bool: "boolean"}
    if tp in names:
        return names[tp]
    return getattr(tp, "__name__", str(tp)).replace("AwareDatetime", "datetime (ISO-8601, tz)")


def _allowed(tp: Any, info: FieldInfo) -> str:
    parts: list[str] = []
    stack = [tp]
    while stack:
        cur = stack.pop()
        if get_origin(cur) is typing.Literal:
            parts += [f"`{getattr(a, 'value', a)}`" for a in get_args(cur)]
        elif isinstance(cur, type) and issubclass(cur, Enum):
            parts += [f"`{m.value}`" for m in cur]
        else:
            stack += list(get_args(cur))
    for m in info.metadata:
        for attr, sym in (
            ("ge", ">="),
            ("le", "<="),
            ("min_length", "min len "),
            ("pattern", "pattern "),
        ):
            val = getattr(m, attr, None)
            if val is not None:
                parts.append(f"{sym}{val}" if attr != "pattern" else f"pattern `{val}`")
    return ", ".join(dict.fromkeys(parts))


def _nested_models(tp: Any) -> list[type[BaseModel]]:
    if isinstance(tp, type) and issubclass(tp, BaseModel):
        return [tp]
    return [m for a in get_args(tp) for m in _nested_models(a)]


def _model_table(model: type[BaseModel]) -> list[str]:
    lines = [
        f"### {model.__name__}",
        "",
        (model.__doc__ or "").strip().splitlines()[0] if model.__doc__ else "",
        "",
        "| field | type | required | unit | allowed values / constraints | meaning |",
        "|---|---|---|---|---|---|",
    ]
    for name, info in model.model_fields.items():
        extra = info.json_schema_extra if isinstance(info.json_schema_extra, dict) else {}
        unit = extra.get("x-unit", "") if extra else ""
        req = "yes" if info.is_required() else f"no (default `{info.default!r}`)"
        desc = (info.description or "").replace("|", "\\|")
        allowed = _allowed(info.annotation, info).replace("|", "\\|")
        typ = _type_str(info.annotation).replace(" | ", " or ")
        lines.append(f"| `{name}` | {typ} | {req} | {unit} | {allowed} | {desc} |")
    return [*lines, ""]


def build_reference() -> str:
    vocab = get_vocabulary()
    lines = [
        "# Protocol field reference",
        "",
        f"Generated from the Pydantic models by `netcoop schemas` (protocol {PROTOCOL_VERSION}, "
        f"vocabulary {vocab.version}). Do not edit by hand. Rules and semantics: PROTOCOL.md.",
        "",
        "## Envelope and messages",
        "",
    ]
    seen: set[type[BaseModel]] = set()
    queue: list[type[BaseModel]] = [Envelope]
    for cls in MESSAGE_CLASSES.values():
        queue += _nested_models(cls.model_fields["payload"].annotation)
    queue += [CapabilityCard, Report]
    while queue:
        model = queue.pop(0)
        if model in seen:
            continue
        seen.add(model)
        lines += _model_table(model)
        for info in model.model_fields.values():
            queue += [m for m in _nested_models(info.annotation) if m not in seen]
    lines += ["## Message types", "", "| type | payload | purpose |", "|---|---|---|"]
    for t, cls in MESSAGE_CLASSES.items():
        p = cls.model_fields["payload"].annotation
        lines.append(
            f"| `{t.value}` | {_type_str(p)} | {(MESSAGE_CLASSES[t].__doc__ or '').strip()} |"
        )
    lines += [
        "",
        "## Controlled vocabulary",
        "",
        "### Metrics",
        "",
        "| metric | unit | kind | applies to | worse when | physical range | meaning |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, m in vocab.metrics.items():
        rng = "" if m.range is None else f"[{m.range[0]}, {m.range[1]}]".replace("None", "-")
        vals = f" values: {', '.join(m.values)}" if m.values else ""
        lines.append(
            f"| `{name}` | {m.unit} | {m.kind}{vals} | {', '.join(m.applies_to)} | {m.worse_when} "
            f"| {rng} | {m.description} |"
        )
    lines += [
        "",
        "### Units",
        "",
        "| dimension | canonical | unit | factor to canonical | aliases |",
        "|---|---|---|---|---|",
    ]
    for dim, d in vocab.dimensions.items():
        for u, ud in d.units.items():
            lines.append(
                f"| {dim} | {d.canonical} | {u} | {ud.factor:g} | {', '.join(ud.aliases)} |"
            )
    lines += ["", "### Entity types", "", "| type | category | meaning |", "|---|---|---|"]
    for name, e in vocab.entity_types.items():
        lines.append(f"| `{name}` | {e.category} | {e.description} |")
    lines += [
        "",
        "### Hypothesis types",
        "",
        "| type | kind | scenario family | meaning |",
        "|---|---|---|---|",
    ]
    for name, h in vocab.hypothesis_types.items():
        lines.append(f"| `{name}` | {h.kind} | {h.family or '-'} | {h.description} |")
    return "\n".join(lines) + "\n"


def write_all(schema_dir: Path = SCHEMA_DIR, reference: Path = REFERENCE) -> list[Path]:
    written: list[Path] = []
    for name, schema in build_schemas().items():
        path = schema_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.append(path)
    reference.write_text(build_reference(), encoding="utf-8")
    written.append(reference)
    return written
