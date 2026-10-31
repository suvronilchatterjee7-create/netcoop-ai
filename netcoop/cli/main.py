"""``netcoop`` command-line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from netcoop import __version__
from netcoop.config import ConfigError, get_value, load_config
from netcoop.generation import DEFAULT_OUT, GeneratorUnavailable, run_sweep
from netcoop.profiling import profile_directory, render_markdown

REPO_ROOT = Path(__file__).resolve().parents[2]


def _cmd_generate(args: argparse.Namespace) -> int:
    run_dirs = run_sweep(out_dir=args.out, scenarios=args.scenario, seeds=args.seed)
    print(f"generated {len(run_dirs)} runs under {args.out}")
    return 0


def _cmd_profile(args: argparse.Namespace) -> int:
    cfg = load_config("profiling")
    profile = profile_directory(
        args.input, get_value(cfg, "max_examples"), get_value(cfg, "max_files_per_group")
    )
    if not profile:
        print(f"error: no CSV/JSON/JSONL files found under {args.input}", file=sys.stderr)
        return 2
    notes_path = args.out.with_name(args.out.stem + "_NOTES.md")
    notes = notes_path.read_text(encoding="utf-8") if notes_path.is_file() else None
    args.out.write_text(render_markdown(profile, args.input, notes), encoding="utf-8")
    print(f"wrote {args.out} ({len(profile)} file groups)")
    return 0


def _cmd_schemas(_args: argparse.Namespace) -> int:
    from netcoop.protocol.schema_export import write_all

    written = write_all()
    print(f"wrote {len(written)} files (JSON Schemas + docs/PROTOCOL_REFERENCE.md)")
    return 0


def _cmd_translate(args: argparse.Namespace) -> int:
    import json

    from netcoop.protocol.messages import dump_message
    from netcoop.translator.translator import Translator

    result = Translator().translate(args.input, args.incident or args.input.name)
    print(f"dialects: {result.dialects}")
    print(f"stats:    {result.stats}")
    for e in result.errors:
        field = f" [{e.source.raw_field}]" if e.source and e.source.raw_field else ""
        src = e.source.source if e.source else "-"
        print(f"  {e.severity.value:11s} {e.code.value:22s} {src}{field}: {e.message}")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8") as fh:
            for m in result.messages:
                fh.write(json.dumps(dump_message(m)) + "\n")
        print(f"wrote {len(result.messages)} messages to {args.out}")
    return 0


def _cmd_interop_eval(args: argparse.Namespace) -> int:
    import tempfile

    from netcoop.mutation import render_corpus, run_corpus, select_runs
    from netcoop.translator.translator import Translator

    n = args.runs_per_family or get_value(load_config("evaluation"), "interop.runs_per_family")
    runs = select_runs(args.input, int(n))
    if not runs:
        print(
            f"error: no generated runs under {args.input}; run `netcoop generate` first",
            file=sys.stderr,
        )
        return 2
    with tempfile.TemporaryDirectory() as tmp:
        rows = run_corpus(runs, Path(tmp), Translator())
    args.out.write_text(render_corpus(rows), encoding="utf-8")
    bad = [r for r in rows if r.outcome in ("fail", "crash")]
    print(
        f"{len(rows)} mutation cases, {len(runs)} runs: {len(bad)} failures/crashes -> {args.out}"
    )
    return 1 if bad else 0


def _not_yet(phase: str) -> int:
    print(f"error: this command is implemented in {phase}", file=sys.stderr)
    return 3


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="netcoop", description=__doc__)
    p.add_argument("--version", action="version", version=f"netcoop {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="generate the labelled synthetic dataset")
    g.add_argument("--out", type=Path, default=DEFAULT_OUT)
    g.add_argument("--scenario", action="append", help="limit to scenario family (repeatable)")
    g.add_argument("--seed", type=int, action="append", help="limit to seed (repeatable)")
    g.set_defaults(func=_cmd_generate)

    pr = sub.add_parser("profile", help="profile generator output into docs/DATA_PROFILE.md")
    pr.add_argument("--input", type=Path, default=DEFAULT_OUT)
    pr.add_argument("--out", type=Path, default=REPO_ROOT / "docs" / "DATA_PROFILE.md")
    pr.set_defaults(func=_cmd_profile)

    sc = sub.add_parser("schemas", help="export JSON Schemas and the protocol field reference")
    sc.set_defaults(func=_cmd_schemas)

    tr = sub.add_parser("translate", help="run the Translator on a run directory or files")
    tr.add_argument("input", type=Path)
    tr.add_argument("--incident", help="incident id (default: input directory name)")
    tr.add_argument("--out", type=Path, help="write the canonical messages as JSONL")
    tr.set_defaults(func=_cmd_translate)

    ie = sub.add_parser("interop-eval", help="mutated-corpus robustness check of the Translator")
    ie.add_argument("--input", type=Path, default=DEFAULT_OUT)
    ie.add_argument("--runs-per-family", type=int)
    ie.add_argument("--out", type=Path, default=REPO_ROOT / "docs" / "INTEROP_RESULTS.md")
    ie.set_defaults(func=_cmd_interop_eval)

    for name, phase in [
        ("run", "Phase 3"),
        ("replay", "Phase 3"),
        ("calibrate", "Phase 4/5"),
        ("eval", "Phase 8"),
    ]:
        sp = sub.add_parser(name, help=f"(coming in {phase})")
        sp.add_argument("rest", nargs="*")
        sp.set_defaults(func=lambda _a, ph=phase: _not_yet(ph))
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (GeneratorUnavailable, ConfigError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
