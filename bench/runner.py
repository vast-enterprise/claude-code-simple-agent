#!/usr/bin/env python3
"""
Tripo Agent Benchmark Runner

Run benchmark prompts against the current Claude Code harness, collect
transcripts, score with LLM-as-judge, and render a Markdown report.

Usage:
  python3 runner.py --phase P0 --label baseline
  python3 runner.py --phase P1 --label diagnose --compare-to reports/P0-baseline-2026-04-17.json
  python3 runner.py --phase P0 --label baseline --only m1-test-skill-loaded-not-executed
  python3 runner.py --phase P0 --label baseline --skip-run  # only re-judge
  python3 runner.py --phase P0 --label baseline --skip-judge  # only re-render

Design notes:
  - Benchmark runs use --permission-mode plan + a narrow --allowedTools whitelist
    so agents cannot cause real side effects (no lark-cli writes, no git push).
  - Transcripts are captured via --output-format stream-json and stored as .jsonl
    under bench/transcripts/<phase>-<label>/<prompt_id>.jsonl.
  - Judge calls the Anthropic API directly (via anthropic SDK). Scores are
    cached to reports/<phase>-<label>-<date>.json alongside the .md report.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass, asdict, field
from datetime import date
from pathlib import Path
from typing import Any

BENCH_DIR = Path(__file__).parent.resolve()
PROMPTS_DIR = BENCH_DIR / "prompts"
RUBRIC_PATH = BENCH_DIR / "rubric.md"
JUDGE_SYSTEM_PATH = BENCH_DIR / "judge_prompt.md"
TRANSCRIPTS_DIR = BENCH_DIR / "transcripts"
REPORTS_DIR = BENCH_DIR / "reports"

DEFAULT_CLAUDE_MODEL = "sonnet"
DEFAULT_JUDGE_MODEL = "sonnet"
DEFAULT_CLAUDE_TIMEOUT_S = 360
DEFAULT_JUDGE_TIMEOUT_S = 240
DEFAULT_JUDGE_MAX_TOKENS = 2000

BENCHMARK_POSTFIX = (
    "\n\n---\n"
    "[Benchmark Mode] 这是架构评测场景。请详细说明你会如何路由：\n"
    "1) 你会调用哪个 subagent（如果有）；\n"
    "2) 你会加载哪些 skill；\n"
    "3) 接下来的步骤顺序和关键决策点；\n"
    "4) 是否需要 AskUserQuestion 阻塞等待用户确认。\n"
    "不要实际执行 git/lark-cli/write 之类有副作用的 tool calls；Read/Grep/Glob "
    "和 Skill 查询可以用。在输出末尾写 '<END>'。"
)

ALLOWED_TOOLS = [
    "Read",
    "Grep",
    "Glob",
    "Skill",
    "TaskCreate",
    "TaskUpdate",
    "TaskList",
    "TaskGet",
    "AskUserQuestion",
    "Agent",
]


@dataclass
class PromptSpec:
    id: str
    path: Path
    category: str
    mode: str | None
    origin: str | None
    touches_rules: list[int]
    expected_agent: str | None
    expected_skill: str | None
    body: str  # full file after frontmatter

    @property
    def user_prompt(self) -> str:
        m = re.search(r"##\s*User Prompt\s*\n(.+?)(?=\n##\s|\Z)", self.body, re.DOTALL)
        return m.group(1).strip() if m else self.body.strip()


@dataclass
class DimensionScore:
    score: int
    reason: str = ""
    evidence: str = ""
    violations: list[int] = field(default_factory=list)


@dataclass
class PromptResult:
    prompt_id: str
    phase: str
    label: str
    transcript_path: str
    scores: dict[str, DimensionScore]
    total: int
    grade: str
    notes: str = ""
    judge_model: str = DEFAULT_JUDGE_MODEL
    judge_error: str | None = None
    run_error: str | None = None


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    header = text[3:end].strip()
    body = text[end + 4 :].lstrip("\n")
    meta: dict[str, Any] = {}
    stack: list[tuple[int, str]] = []
    for line in header.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        if stripped.startswith("- "):
            parent_key = stack[-1][1] if stack else None
            if parent_key is None:
                continue
            val = stripped[2:].strip()
            meta.setdefault(parent_key, [])
            if isinstance(meta[parent_key], list):
                meta[parent_key].append(_coerce(val))
            continue
        if ":" in stripped:
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()
            # pop stack to current indent
            while stack and stack[-1][0] >= indent:
                stack.pop()
            if val == "":
                meta[key] = []
                stack.append((indent, key))
            else:
                # inline list syntax: [1, 2]
                if val.startswith("[") and val.endswith("]"):
                    inner = val[1:-1].strip()
                    items = [_coerce(x.strip()) for x in inner.split(",") if x.strip()]
                    meta[key] = items
                else:
                    meta[key] = _coerce(val)
    return meta, body


def _coerce(val: str) -> Any:
    if val.lower() in ("true", "false"):
        return val.lower() == "true"
    try:
        return int(val)
    except ValueError:
        pass
    # strip surrounding quotes
    if (val.startswith('"') and val.endswith('"')) or (
        val.startswith("'") and val.endswith("'")
    ):
        return val[1:-1]
    # strip trailing inline comment
    if "#" in val:
        val = val[: val.index("#")].rstrip()
    return val


def load_prompts(only: str | None = None) -> list[PromptSpec]:
    specs: list[PromptSpec] = []
    for path in sorted(PROMPTS_DIR.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)
        pid = meta.get("id") or path.stem
        if only and pid != only:
            continue
        specs.append(
            PromptSpec(
                id=pid,
                path=path,
                category=meta.get("category", "unknown"),
                mode=meta.get("mode"),
                origin=meta.get("origin"),
                touches_rules=list(meta.get("touches_rules", []) or []),
                expected_agent=meta.get("expected_agent"),
                expected_skill=meta.get("expected_skill"),
                body=body,
            )
        )
    return specs


def run_claude(spec: PromptSpec, transcript_path: Path, model: str) -> tuple[bool, str]:
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    session_id = str(uuid.uuid4())
    prompt = spec.user_prompt + BENCHMARK_POSTFIX
    cmd = [
        "claude",
        "-p",
        "--print",
        "--output-format",
        "stream-json",
        "--verbose",
        "--permission-mode",
        "plan",
        "--allowedTools",
        *ALLOWED_TOOLS,
        "--model",
        model,
        "--session-id",
        session_id,
        "--no-session-persistence",
        "--include-hook-events",
        prompt,
    ]
    try:
        with transcript_path.open("w", encoding="utf-8") as f:
            proc = subprocess.run(
                cmd,
                stdout=f,
                stderr=subprocess.PIPE,
                timeout=DEFAULT_CLAUDE_TIMEOUT_S,
                check=False,
            )
        if proc.returncode != 0:
            return False, (proc.stderr or b"").decode(errors="replace")[:2000]
        return True, ""
    except subprocess.TimeoutExpired:
        return False, f"timeout after {DEFAULT_CLAUDE_TIMEOUT_S}s"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def summarize_transcript(path: Path, max_chars: int = 12000) -> str:
    """Shrink a raw stream-json transcript down to something a judge can read."""
    if not path.exists():
        return "(no transcript)"
    lines = path.read_text(encoding="utf-8").splitlines()
    events: list[str] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        etype = obj.get("type") or obj.get("event") or ""
        if etype in ("tool_use",) or obj.get("name") or obj.get("tool"):
            name = obj.get("name") or obj.get("tool") or ""
            sub_input = obj.get("input") or obj.get("arguments") or {}
            if isinstance(sub_input, dict):
                # keep only small keys
                keys = sorted(sub_input.keys())
                short = {
                    k: (
                        (sub_input[k][:200] + "…")
                        if isinstance(sub_input[k], str) and len(sub_input[k]) > 200
                        else sub_input[k]
                    )
                    for k in keys[:6]
                }
                events.append(f"[tool_use] {name} {json.dumps(short, ensure_ascii=False)[:400]}")
            else:
                events.append(f"[tool_use] {name}")
        elif etype == "assistant" or obj.get("role") == "assistant":
            msg = obj.get("message") or obj
            content = msg.get("content") if isinstance(msg, dict) else None
            if isinstance(content, list):
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "text":
                        txt = c.get("text", "")
                        events.append(f"[assistant] {txt[:800]}")
                    elif isinstance(c, dict) and c.get("type") == "tool_use":
                        tname = c.get("name", "")
                        tin = c.get("input", {})
                        events.append(
                            f"[tool_use] {tname} "
                            f"{json.dumps(tin, ensure_ascii=False)[:400]}"
                        )
            elif isinstance(content, str):
                events.append(f"[assistant] {content[:800]}")
        elif etype == "result":
            res = obj.get("result") or obj.get("text") or ""
            if res:
                events.append(f"[final] {str(res)[:1500]}")
    joined = "\n".join(events)
    if len(joined) > max_chars:
        joined = joined[:max_chars] + "\n... (truncated)"
    return joined


def call_judge(
    spec: PromptSpec,
    transcript_summary: str,
    rubric: str,
    system_prompt: str,
    phase: str,
    judge_model: str,
) -> tuple[dict[str, Any] | None, str | None]:
    """Invoke a Claude Code session as judge. Uses --bare + --system-prompt so the
    judge is isolated from CLAUDE.md, memory, skills, and hooks."""
    user_msg = (
        f"# Rubric\n\n{rubric}\n\n"
        f"# Prompt Metadata\n\n"
        f"```yaml\n"
        f"id: {spec.id}\n"
        f"category: {spec.category}\n"
        f"touches_rules: {spec.touches_rules}\n"
        f"expected_agent: {spec.expected_agent}\n"
        f"expected_skill: {spec.expected_skill}\n"
        f"```\n\n"
        f"# Prompt Body\n\n{spec.body.strip()}\n\n"
        f"# Session Transcript Summary\n\n{transcript_summary}\n\n"
        f"# Phase\n\n{phase}\n\n"
        f"请按 judge system prompt 的格式，仅输出一个 JSON 对象。"
    )
    cmd = [
        "claude",
        "-p",
        "--print",
        "--bare",
        "--output-format",
        "json",
        "--model",
        judge_model,
        "--system-prompt",
        system_prompt,
        "--no-session-persistence",
        "--session-id",
        str(uuid.uuid4()),
        user_msg,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=DEFAULT_JUDGE_TIMEOUT_S,
            check=False,
            text=True,
        )
    except subprocess.TimeoutExpired:
        return None, f"judge timeout after {DEFAULT_JUDGE_TIMEOUT_S}s"
    if proc.returncode != 0:
        return None, f"judge exit {proc.returncode}: {proc.stderr[:500]}"
    # --output-format json returns an envelope with final result text
    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        return None, f"judge stdout not JSON: {e} | raw={proc.stdout[:500]}"
    text = envelope.get("result") or envelope.get("text") or ""
    if not text:
        return None, f"judge envelope missing result: {json.dumps(envelope)[:500]}"
    parsed = _extract_json(text)
    if parsed is None:
        return None, f"judge response not JSON: raw={text[:500]}"
    return parsed, None


def _extract_json(text: str) -> dict[str, Any] | None:
    """Try several strategies to recover a JSON object from judge output.
    Handles <think> blocks, ```json fences, or leading prose.
    """
    candidates: list[str] = [text]
    # strip code fences
    fenced = re.sub(r"^```(?:json)?\s*|\s*```\s*$", "", text.strip(), flags=re.MULTILINE)
    candidates.append(fenced)
    # strip <think>...</think>
    without_think = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE).strip()
    candidates.append(without_think)
    # balanced {...} extraction (possibly multiple attempts)
    candidates.extend(_balanced_json_blocks(text))
    candidates.extend(_balanced_json_blocks(without_think))
    for c in candidates:
        c = c.strip()
        if not c:
            continue
        try:
            result = json.loads(c)
            if isinstance(result, dict) and "scores" in result:
                return result
        except json.JSONDecodeError:
            continue
    return None


def _balanced_json_blocks(text: str):
    idx = 0
    while idx < len(text):
        start = text.find("{", idx)
        if start == -1:
            return
        depth = 0
        end = -1
        for i in range(start, len(text)):
            c = text[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end == -1:
            return
        yield text[start : end + 1]
        idx = end + 1


GRADE_TABLE = [(17, "S"), (14, "A"), (10, "B"), (6, "C"), (0, "D")]


def grade_for(total: int) -> str:
    for threshold, letter in GRADE_TABLE:
        if total >= threshold:
            return letter
    return "D"


def score_total(scores: dict[str, DimensionScore]) -> int:
    return sum(d.score for d in scores.values())


def dims_from_judge(j: dict[str, Any]) -> dict[str, DimensionScore]:
    out: dict[str, DimensionScore] = {}
    raw = j.get("scores", {})
    for dim in ("routing", "flow", "rules", "output"):
        r = raw.get(dim) or {}
        out[dim] = DimensionScore(
            score=int(r.get("score", 0)),
            reason=str(r.get("reason", ""))[:400],
            evidence=str(r.get("evidence", ""))[:400],
            violations=[int(x) for x in r.get("violations", []) or []],
        )
    return out


def render_report(
    phase: str,
    label: str,
    run_date: str,
    results: list[PromptResult],
    baseline: dict[str, dict[str, Any]] | None,
) -> str:
    lines: list[str] = []
    lines.append(f"# {phase} Benchmark Report — {label} — {run_date}\n")

    # Summary
    dims = ("routing", "flow", "rules", "output")
    cur_avg = {d: _avg(r.scores[d].score for r in results) for d in dims}
    if baseline:
        base_avg = {
            d: _avg(
                b.get("scores", {}).get(d, {}).get("score", 0)
                for b in baseline.values()
            )
            for d in dims
        }
    else:
        base_avg = None

    lines.append("## Summary\n")
    header = "| 维度 | 本轮 |"
    sep = "|------|------|"
    if base_avg is not None:
        header = "| 维度 | Baseline | 本轮 | diff |"
        sep = "|------|---------|------|------|"
    lines.append(header)
    lines.append(sep)
    for d in dims:
        if base_avg is not None:
            diff = cur_avg[d] - base_avg[d]
            sign = "+" if diff >= 0 else ""
            lines.append(
                f"| {d} | {base_avg[d]:.2f} | {cur_avg[d]:.2f} | {sign}{diff:.2f} |"
            )
        else:
            lines.append(f"| {d} | {cur_avg[d]:.2f} |")
    avg_total = sum(r.total for r in results) / max(len(results), 1)
    lines.append(f"\n**平均总分**：{avg_total:.2f} / 20\n")

    # Regression / Improvement
    if baseline:
        regressions, improvements = [], []
        for r in results:
            prev = baseline.get(r.prompt_id)
            if not prev:
                continue
            prev_total = prev.get("total", 0)
            diff = r.total - prev_total
            if diff <= -3:
                regressions.append((r, prev_total))
            elif diff >= 3:
                improvements.append((r, prev_total))
        if regressions:
            lines.append("## Regression（退化，≥3 分下降，红线）\n")
            lines.append("| # | Prompt | Baseline | 本轮 | diff |")
            lines.append("|---|--------|---------|------|------|")
            for r, prev in regressions:
                lines.append(
                    f"| {r.prompt_id} | {r.prompt_id} | {prev}/20 | {r.total}/20 | {r.total - prev} |"
                )
            lines.append("")
        if improvements:
            lines.append("## Improvement（改进，≥3 分上升）\n")
            lines.append("| Prompt | Baseline | 本轮 | diff |")
            lines.append("|--------|---------|------|------|")
            for r, prev in improvements:
                lines.append(
                    f"| {r.prompt_id} | {prev}/20 | {r.total}/20 | +{r.total - prev} |"
                )
            lines.append("")

    # Per-prompt table
    lines.append("## 测试集结果\n")
    lines.append("| # | Prompt | Category | Route | Flow | Rules | Output | Total | Grade |")
    lines.append("|---|--------|----------|-------|------|-------|--------|-------|-------|")
    for idx, r in enumerate(results, 1):
        s = r.scores
        lines.append(
            f"| {idx} | {r.prompt_id} | {_category(r.prompt_id)} | "
            f"{s['routing'].score} | {s['flow'].score} | {s['rules'].score} | "
            f"{s['output'].score} | {r.total}/20 | {r.grade} |"
        )
    lines.append("")

    # Details
    lines.append("## Details\n")
    for r in results:
        lines.append(f"### {r.prompt_id} ({r.grade}, {r.total}/20)\n")
        if r.run_error:
            lines.append(f"- Run error: `{r.run_error}`")
        if r.judge_error:
            lines.append(f"- Judge error: `{r.judge_error}`")
        for dim in ("routing", "flow", "rules", "output"):
            d = r.scores[dim]
            extra = f" violations={d.violations}" if d.violations else ""
            lines.append(
                f"- **{dim}** ({d.score}/5){extra}: {d.reason}"
            )
            if d.evidence and d.evidence != "none":
                lines.append(f"  - 证据：{d.evidence[:200]}")
        if r.notes:
            lines.append(f"- notes: {r.notes}")
        lines.append("")

    return "\n".join(lines)


def _avg(nums) -> float:
    arr = list(nums)
    return sum(arr) / len(arr) if arr else 0.0


def _category(pid: str) -> str:
    return "regression" if pid.startswith("m") else "normal"


def load_baseline(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        print(f"[warn] baseline file not found: {path}", file=sys.stderr)
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {r["prompt_id"]: r for r in data.get("results", [])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True, help="P0 / P1 / ...")
    parser.add_argument("--label", required=True, help="baseline / diagnose / ...")
    parser.add_argument("--model", default=DEFAULT_CLAUDE_MODEL, help="claude model alias")
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL)
    parser.add_argument("--only", help="run only this prompt id")
    parser.add_argument("--compare-to", help="path to previous <phase>-<label>-<date>.json")
    parser.add_argument("--skip-run", action="store_true", help="reuse existing transcripts")
    parser.add_argument(
        "--reuse-transcripts",
        action="store_true",
        help="reuse transcripts that already exist, only run missing ones",
    )
    parser.add_argument("--skip-judge", action="store_true", help="only re-render report")
    parser.add_argument("--dry-run", action="store_true", help="plan but do not call claude/judge")
    args = parser.parse_args()

    run_date = date.today().isoformat()
    phase_tag = f"{args.phase}-{args.label}"
    transcript_dir = TRANSCRIPTS_DIR / phase_tag
    report_json = REPORTS_DIR / f"{phase_tag}-{run_date}.json"
    report_md = REPORTS_DIR / f"{phase_tag}-{run_date}.md"
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    specs = load_prompts(only=args.only)
    if not specs:
        print("[error] no prompts matched", file=sys.stderr)
        return 2

    rubric = RUBRIC_PATH.read_text(encoding="utf-8")
    system_prompt = JUDGE_SYSTEM_PATH.read_text(encoding="utf-8")

    prior: dict[str, PromptResult] = {}
    if args.skip_judge and report_json.exists():
        prior = {
            r["prompt_id"]: _result_from_dict(r)
            for r in json.loads(report_json.read_text(encoding="utf-8"))["results"]
        }

    results: list[PromptResult] = []
    for spec in specs:
        transcript_path = transcript_dir / f"{spec.id}.jsonl"
        run_err: str | None = None
        if not args.skip_run:
            if args.reuse_transcripts and transcript_path.exists() and transcript_path.stat().st_size > 0:
                print(f"[reuse] existing transcript for {spec.id}")
            elif args.dry_run:
                print(f"[dry-run] would run claude for {spec.id}")
            else:
                print(f"[run] {spec.id} → {transcript_path}")
                ok, err = run_claude(spec, transcript_path, args.model)
                if not ok:
                    run_err = err
                    print(f"[run-error] {spec.id}: {err}", file=sys.stderr)
        else:
            print(f"[skip-run] reusing {transcript_path}")

        if args.skip_judge and spec.id in prior:
            print(f"[skip-judge] reusing scores for {spec.id}")
            results.append(prior[spec.id])
            continue

        if args.dry_run:
            results.append(_empty_result(spec, phase_tag, transcript_path, "dry-run"))
            continue

        summary = summarize_transcript(transcript_path)
        judge_data, judge_err = call_judge(
            spec=spec,
            transcript_summary=summary,
            rubric=rubric,
            system_prompt=system_prompt,
            phase=args.phase,
            judge_model=args.judge_model,
        )
        if judge_data is None:
            print(f"[judge-error] {spec.id}: {judge_err}", file=sys.stderr)
            result = _empty_result(spec, phase_tag, transcript_path, judge_err or "unknown")
            result.run_error = run_err
            results.append(result)
            continue

        dims = dims_from_judge(judge_data)
        total = score_total(dims)
        result = PromptResult(
            prompt_id=spec.id,
            phase=args.phase,
            label=args.label,
            transcript_path=str(transcript_path),
            scores=dims,
            total=total,
            grade=grade_for(total),
            notes=str(judge_data.get("notes", ""))[:400],
            judge_model=args.judge_model,
            judge_error=None,
            run_error=run_err,
        )
        results.append(result)

    # Persist JSON; if --only is set and report exists, merge into existing entries.
    existing: dict[str, dict[str, Any]] = {}
    if args.only and report_json.exists():
        try:
            prev_data = json.loads(report_json.read_text(encoding="utf-8"))
            existing = {r["prompt_id"]: r for r in prev_data.get("results", [])}
        except Exception:  # noqa: BLE001
            existing = {}
    merged: list[dict[str, Any]] = []
    touched_ids = {r.prompt_id for r in results}
    for pid, old in existing.items():
        if pid in touched_ids:
            continue
        merged.append(old)
    merged.extend(_result_to_dict(r) for r in results)
    # keep stable order: follow prompt file discovery order
    all_specs = load_prompts()
    order = {s.id: i for i, s in enumerate(all_specs)}
    merged.sort(key=lambda r: order.get(r["prompt_id"], 999))

    payload = {
        "phase": args.phase,
        "label": args.label,
        "date": run_date,
        "model": args.model,
        "judge_model": args.judge_model,
        "results": merged,
    }
    report_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    baseline = load_baseline(Path(args.compare_to)) if args.compare_to else None
    render_results = [_result_from_dict(d) for d in merged]
    md = render_report(
        phase=args.phase,
        label=args.label,
        run_date=run_date,
        results=render_results,
        baseline=baseline,
    )
    report_md.write_text(md, encoding="utf-8")
    print(f"[done] report: {report_md}")
    print(f"[done] data:   {report_json}")
    return 0


def _empty_result(
    spec: PromptSpec, phase_tag: str, transcript: Path, err: str
) -> PromptResult:
    zeroes = {
        d: DimensionScore(score=0, reason="", evidence="none")
        for d in ("routing", "flow", "rules", "output")
    }
    return PromptResult(
        prompt_id=spec.id,
        phase=phase_tag.split("-")[0],
        label=phase_tag.split("-", 1)[1],
        transcript_path=str(transcript),
        scores=zeroes,
        total=0,
        grade="D",
        judge_error=err,
    )


def _result_to_dict(r: PromptResult) -> dict[str, Any]:
    d = asdict(r)
    # DimensionScore is nested via asdict already
    return d


def _result_from_dict(d: dict[str, Any]) -> PromptResult:
    scores = {
        k: DimensionScore(**v) for k, v in d.get("scores", {}).items()
    }
    return PromptResult(
        prompt_id=d["prompt_id"],
        phase=d.get("phase", ""),
        label=d.get("label", ""),
        transcript_path=d.get("transcript_path", ""),
        scores=scores,
        total=d.get("total", 0),
        grade=d.get("grade", "D"),
        notes=d.get("notes", ""),
        judge_model=d.get("judge_model", DEFAULT_JUDGE_MODEL),
        judge_error=d.get("judge_error"),
        run_error=d.get("run_error"),
    )


if __name__ == "__main__":
    sys.exit(main())
