#!/usr/bin/env python3
"""
adk_eval_report.py

Genera un reporte legible a partir de archivos .evalset_result.json de ADK.

Uso:
  python adk_eval_report.py .adk/eval_history/*.evalset_result.json
  python adk_eval_report.py result.json --show-rationales --max-rationale 240 --show-final
  python adk_eval_report.py result.json --format md > report.md
"""

from __future__ import annotations

import argparse
import glob
import json
import os
from typing import Any, Dict, List, Optional, Tuple


def _as_list(x: Any) -> List[Any]:
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def _shorten(s: str, n: int) -> str:
    s = (s or "").strip()
    if n <= 0 or len(s) <= n:
        return s
    return s[: max(0, n - 1)].rstrip() + "…"


def _status_label(code: Any) -> str:
    # En tu JSON: 1 = pass. Otros valores pueden variar.
    return "PASS" if code == 1 else "FAIL"


def _get_final_response_text(eval_case: Dict[str, Any]) -> str:
    # ADK guarda respuestas por invocación en eval_metric_result_per_invocation[].actual_invocation.final_response.parts[].text
    per_inv = _as_list(eval_case.get("eval_metric_result_per_invocation"))
    if not per_inv:
        return ""
    actual = per_inv[0].get("actual_invocation") or {}
    final_resp = actual.get("final_response") or {}
    parts = _as_list(final_resp.get("parts"))
    # Concatenamos todos los textos no vacíos
    texts = []
    for p in parts:
        t = p.get("text")
        if isinstance(t, str) and t.strip():
            texts.append(t.strip())
    return "\n".join(texts).strip()


def _collect_metric_scores(eval_case: Dict[str, Any]) -> List[Tuple[str, Optional[float], Any]]:
    out = []
    metrics = _as_list(eval_case.get("overall_eval_metric_results"))
    for m in metrics:
        name = m.get("metric_name", "unknown_metric")
        score = m.get("score", None)
        status = m.get("eval_status", None)
        out.append((name, score, status))
    return out


def _collect_rubrics(eval_case: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Devuelve una lista plana de rúbricas evaluadas, si existen, con:
      metric_name, rubric_id, score, rationale
    """
    out: List[Dict[str, Any]] = []
    metrics = _as_list(eval_case.get("overall_eval_metric_results"))
    for m in metrics:
        metric_name = m.get("metric_name", "unknown_metric")
        details = m.get("details") or {}
        rubric_scores = _as_list(details.get("rubric_scores"))
        for r in rubric_scores:
            out.append(
                {
                    "metric_name": metric_name,
                    "rubric_id": r.get("rubric_id", "unknown_rubric"),
                    "score": r.get("score", None),
                    "rationale": r.get("rationale", ""),
                }
            )
    return out


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _expand_inputs(inputs: List[str]) -> List[str]:
    paths: List[str] = []
    for item in inputs:
        # Permite glob
        expanded = glob.glob(item)
        if expanded:
            paths.extend(expanded)
        else:
            paths.append(item)
    # Dedup preservando orden
    seen = set()
    uniq = []
    for p in paths:
        rp = os.path.abspath(p)
        if rp not in seen and os.path.exists(rp):
            seen.add(rp)
            uniq.append(rp)
    return uniq


def render_text(
    data_by_file: List[Tuple[str, Dict[str, Any]]],
    show_rationales: bool,
    max_rationale: int,
    show_final: bool,
    max_final: int,
) -> str:
    lines: List[str] = []
    for path, data in data_by_file:
        title = data.get("eval_set_result_name") or os.path.basename(path)
        eval_set_id = data.get("eval_set_id", "unknown_eval_set")
        lines.append(f"== {title} (eval_set_id={eval_set_id}) ==")

        cases = _as_list(data.get("eval_case_results"))
        lines.append(f"Casos: {len(cases)}")
        lines.append("")

        for c in cases:
            eval_id = c.get("eval_id", "unknown_eval_id")
            final_status = _status_label(c.get("final_eval_status"))
            lines.append(f"- {eval_id}: {final_status}")

            # Métricas (score)
            metric_scores = _collect_metric_scores(c)
            for name, score, status in metric_scores:
                s_label = _status_label(status) if status is not None else "?"
                score_str = f"{score:.3f}" if isinstance(score, (int, float)) else str(score)
                lines.append(f"    • {name}: {score_str} ({s_label})")

            if show_final:
                fr = _get_final_response_text(c)
                if fr:
                    lines.append(f"    • final_response: {_shorten(fr.replace('\\n', ' '), max_final)}")

            rubrics = _collect_rubrics(c)
            if rubrics:
                lines.append("    • rúbricas:")
                for r in rubrics:
                    rid = r["rubric_id"]
                    sc = r["score"]
                    sc_str = f"{sc:.3f}" if isinstance(sc, (int, float)) else str(sc)
                    lines.append(f"        - [{r['metric_name']}] {rid}: {sc_str}")
                    if show_rationales:
                        rat = _shorten(str(r.get("rationale", "")), max_rationale)
                        if rat:
                            lines.append(f"            rationale: {rat}")

            lines.append("")

        lines.append("")  # separación entre ficheros
    return "\n".join(lines).rstrip() + "\n"


def render_markdown(
    data_by_file: List[Tuple[str, Dict[str, Any]]],
    show_rationales: bool,
    max_rationale: int,
    show_final: bool,
    max_final: int,
) -> str:
    md: List[str] = []
    for path, data in data_by_file:
        title = data.get("eval_set_result_name") or os.path.basename(path)
        eval_set_id = data.get("eval_set_id", "unknown_eval_set")
        md.append(f"# {title}")
        md.append(f"- **eval_set_id:** `{eval_set_id}`")
        md.append(f"- **file:** `{path}`")
        md.append("")

        cases = _as_list(data.get("eval_case_results"))
        md.append(f"## Casos ({len(cases)})")
        md.append("")

        for c in cases:
            eval_id = c.get("eval_id", "unknown_eval_id")
            final_status = _status_label(c.get("final_eval_status"))
            md.append(f"### {eval_id} — {final_status}")
            md.append("")

            metric_scores = _collect_metric_scores(c)
            if metric_scores:
                md.append("| Métrica | Score | Status |")
                md.append("|---|---:|---|")
                for name, score, status in metric_scores:
                    s_label = _status_label(status) if status is not None else "?"
                    score_str = f"{score:.3f}" if isinstance(score, (int, float)) else str(score)
                    md.append(f"| `{name}` | {score_str} | {s_label} |")
                md.append("")

            if show_final:
                fr = _get_final_response_text(c)
                if fr:
                    md.append("**final_response (recortado):**")
                    md.append("")
                    md.append(f"> {_shorten(fr.replace('\\n', ' '), max_final)}")
                    md.append("")

            rubrics = _collect_rubrics(c)
            if rubrics:
                md.append("**Rúbricas:**")
                md.append("")
                for r in rubrics:
                    rid = r["rubric_id"]
                    sc = r["score"]
                    sc_str = f"{sc:.3f}" if isinstance(sc, (int, float)) else str(sc)
                    md.append(f"- `{r['metric_name']}` / `{rid}` → **{sc_str}**")
                    if show_rationales:
                        rat = _shorten(str(r.get("rationale", "")), max_rationale)
                        if rat:
                            md.append(f"  - rationale: {_shorten(rat, max_rationale)}")
                md.append("")

        md.append("\n---\n")
    return "\n".join(md).strip() + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", help="Archivos o globs hacia *.evalset_result.json")
    ap.add_argument("--format", choices=["text", "md"], default="text", help="Formato de salida")
    ap.add_argument("--show-rationales", action="store_true", help="Incluye rationales de las rúbricas")
    ap.add_argument("--max-rationale", type=int, default=240, help="Máximo de chars por rationale (0 = sin recortar)")
    ap.add_argument("--show-final", action="store_true", help="Incluye final_response (recortado)")
    ap.add_argument("--max-final", type=int, default=220, help="Máximo de chars del final_response (0 = sin recortar)")
    args = ap.parse_args()

    paths = _expand_inputs(args.inputs)
    if not paths:
        raise SystemExit("No se encontraron archivos de entrada.")

    data_by_file: List[Tuple[str, Dict[str, Any]]] = [(p, _load_json(p)) for p in paths]

    if args.format == "md":
        out = render_markdown(
            data_by_file=data_by_file,
            show_rationales=args.show_rationales,
            max_rationale=args.max_rationale,
            show_final=args.show_final,
            max_final=args.max_final,
        )
    else:
        out = render_text(
            data_by_file=data_by_file,
            show_rationales=args.show_rationales,
            max_rationale=args.max_rationale,
            show_final=args.show_final,
            max_final=args.max_final,
        )

    print(out, end="")


if __name__ == "__main__":
    main()