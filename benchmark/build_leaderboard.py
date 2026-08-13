#!/usr/bin/env python3
"""Build the static leaderboard page from the newest benchmark summary.

    python benchmark/build_leaderboard.py

Writes ``benchmark/leaderboard/index.html``, a self-contained page suitable for
GitHub Pages. Robustness and utility are shown side by side deliberately: a model
that scores well on one and badly on the other has not passed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BENCH_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BENCH_DIR / "results"
# Published under docs/ so GitHub Pages serves it at /agentgauntlet/leaderboard/.
OUT_DIR = BENCH_DIR.parent / "docs" / "leaderboard"

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AgentGauntlet leaderboard</title>
<style>
  :root {{
    --bg:#fbfbfd; --panel:#fff; --ink:#16181d; --muted:#62677a; --line:#e3e5ec;
    --good:#2b8a3e; --bad:#c92a2a;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg:#14161b; --panel:#1c1f26; --ink:#e8eaf0; --muted:#9aa1b4; --line:#2c313b;
      --good:#8ce99a; --bad:#ff8787;
    }}
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; padding:3rem 1.25rem 5rem; background:var(--bg); color:var(--ink);
    font:15px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, sans-serif; }}
  .wrap {{ max-width:900px; margin:0 auto; }}
  h1 {{ font-size:1.7rem; margin:0 0 .3rem; letter-spacing:-.02em; }}
  p.sub {{ color:var(--muted); margin:0 0 2rem; }}
  .scroll {{ overflow-x:auto; }}
  table {{ border-collapse:collapse; width:100%; min-width:640px; background:var(--panel);
    border:1px solid var(--line); border-radius:10px; overflow:hidden; }}
  th,td {{ text-align:left; padding:.65rem .8rem; border-bottom:1px solid var(--line); }}
  th {{ font-size:.72rem; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); }}
  td.num, th.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  .good {{ color:var(--good); font-weight:600; }}
  .bad {{ color:var(--bad); font-weight:600; }}
  .note {{ color:var(--muted); font-size:.8rem; }}
  footer {{ margin-top:2.5rem; padding-top:1rem; border-top:1px solid var(--line);
    color:var(--muted); font-size:.85rem; }}
  code {{ background:var(--line); padding:.1rem .35rem; border-radius:4px; }}
  .chart {{ margin:1rem 0 .4rem; }}
  .chart svg {{ width:100%; height:auto; max-width:640px; display:block; }}
  .cap {{ color:var(--muted); font-size:.82rem; margin:0 0 2rem; max-width:640px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>AgentGauntlet leaderboard</h1>
  <p class="sub">
    {scenario_count} adversarial scenarios × {repeats} repeats · run {date} ·
    lower attack success is better, higher utility is better
  </p>

  <div class="chart">
{chart}
  </div>
  <p class="cap">Each dot is a model. Up and to the right is better: it resists attacks while
  still completing the task. Two models at the same height are equally hard to attack, yet
  can sit far apart on whether they actually did the work.</p>

  <div class="scroll">
  <table>
    <thead><tr>
      <th>Model</th>
      <th class="num">Robustness</th>
      <th class="num">Attack success</th>
      <th class="num">Utility</th>
      <th class="num">Runs</th>
    </tr></thead>
    <tbody>
{rows}
    </tbody>
  </table>
  </div>

  <footer>
    <p><strong>Reading this table.</strong> Robustness is 1 − attack success rate.
    Utility is the share of runs where the agent completed the benign task it was
    given. They must be read together: a model that refuses everything scores
    100% robustness and 0% utility, and has not passed anything.</p>
    <p>Every attack ran inside an in-process mock environment. No messages were
    sent and no requests left the machine. Reproduce with
    <code>python benchmark/run_benchmark.py</code>.</p>
  </footer>
</div>
</body>
</html>
"""


def _cell(value: float, good_when_low: bool) -> str:
    good = value < 0.15 if good_when_low else value > 0.85
    return f'<td class="num {"good" if good else "bad"}">{value * 100:.0f}%</td>'


def build_chart_svg(rows: list[dict[str, Any]]) -> str:
    """Robustness-vs-utility scatter as inline, theme-aware SVG.

    One dot per model. This is the figure that carries the argument: models can
    tie on robustness (same x) yet split on utility (different y), which the table
    keeps in separate columns. Colors are CSS variables defined on the page, so
    the chart follows light/dark like everything else, and there is no chart
    library or external asset.
    """
    w, h = 640, 400
    left, right, top, bottom = 66, 132, 30, 54
    pw, ph = w - left - right, h - top - bottom

    def px(v: float) -> float:  # robustness/utility percent -> pixels
        return left + (v / 100) * pw

    def py(v: float) -> float:
        return top + ph - (v / 100) * ph

    s: list[str] = [
        f'<svg viewBox="0 0 {w} {h}" role="img" '
        f'aria-label="Robustness versus utility, one point per model" '
        f'xmlns="http://www.w3.org/2000/svg" font-family="-apple-system,BlinkMacSystemFont,'
        f'Segoe UI,Inter,sans-serif">'
    ]

    # "safe + useful" target region: robustness >= 75 and utility >= 75.
    gx = px(75)
    s.append(
        f'<rect x="{gx:.0f}" y="{top}" width="{px(100) - gx:.0f}" height="{py(75) - top:.0f}" '
        f'fill="var(--good)" opacity="0.10"/>'
    )
    s.append(
        f'<text x="{gx + 6:.0f}" y="{top + 16}" text-anchor="start" font-size="11" '
        f'font-weight="600" fill="var(--good)">safe + useful</text>'
    )

    # gridlines and axis ticks every 20%
    for t in (0, 20, 40, 60, 80, 100):
        gxp, gyp = px(t), py(t)
        s.append(
            f'<line x1="{gxp:.0f}" y1="{top}" x2="{gxp:.0f}" y2="{top + ph}" '
            f'stroke="var(--line)" stroke-width="1"/>'
        )
        s.append(
            f'<line x1="{left}" y1="{gyp:.0f}" x2="{left + pw}" y2="{gyp:.0f}" '
            f'stroke="var(--line)" stroke-width="1"/>'
        )
        s.append(
            f'<text x="{gxp:.0f}" y="{top + ph + 18}" text-anchor="middle" font-size="11" '
            f'fill="var(--muted)">{t}%</text>'
        )
        s.append(
            f'<text x="{left - 8}" y="{gyp + 4:.0f}" text-anchor="end" font-size="11" '
            f'fill="var(--muted)">{t}%</text>'
        )

    # axis titles
    s.append(
        f'<text x="{left + pw / 2:.0f}" y="{h - 12}" text-anchor="middle" font-size="12" '
        f'fill="var(--muted)">Robustness  (1 minus attack success)</text>'
    )
    s.append(
        f'<text transform="translate(16,{top + ph / 2:.0f}) rotate(-90)" text-anchor="middle" '
        f'font-size="12" fill="var(--muted)">Utility  (benign task completed)</text>'
    )

    # One point per model. Real leaderboards cluster in the top-right (high
    # robustness), so labels are placed toward the open interior of the plot
    # rather than off the right edge: points on the right half get left-aligned
    # labels, points on the left half get right-aligned ones.
    for r in rows:
        cx, cy = px(r["robustness"] * 100), py(r["utility"] * 100)
        name = str(r["label"]).replace(" (local)", "")
        left_side = r["robustness"] * 100 >= 55
        lx = cx - 11 if left_side else cx + 11
        anchor = "end" if left_side else "start"
        values = f'R {r["robustness"] * 100:.0f}% · U {r["utility"] * 100:.0f}%'
        s.append(
            f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="6" fill="var(--ink)" '
            f'stroke="var(--panel)" stroke-width="2"/>'
        )
        s.append(
            f'<text x="{lx:.0f}" y="{cy - 2:.0f}" text-anchor="{anchor}" font-size="12.5" '
            f'font-weight="600" fill="var(--ink)">{name}</text>'
        )
        s.append(
            f'<text x="{lx:.0f}" y="{cy + 12:.0f}" text-anchor="{anchor}" font-size="10.5" '
            f'fill="var(--muted)">{values}</text>'
        )

    s.append("</svg>")
    return "".join(s)


def main() -> int:
    summaries = sorted(RESULTS_DIR.glob("*/summary.json"))
    if not summaries:
        print("no benchmark results yet; run benchmark/run_benchmark.py first")
        return 1

    summary = json.loads(summaries[-1].read_text())

    rows = []
    for row in summary["rows"]:
        note = f'<div class="note">{row["notes"]}</div>' if row.get("notes") else ""
        rows.append(
            "      <tr>"
            f'<td>{row["label"]}{note}</td>'
            f'<td class="num">{row["robustness"] * 100:.0f}%</td>'
            f"{_cell(row['asr'], good_when_low=True)}"
            f"{_cell(row['utility'], good_when_low=False)}"
            f'<td class="num">{row["valid_runs"]}</td>'
            "</tr>"
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "index.html").write_text(
        PAGE.format(
            scenario_count=summary["scenario_count"],
            repeats=summary["repeats"],
            date=summary["date"],
            chart=build_chart_svg(summary["rows"]),
            rows="\n".join(rows),
        )
    )
    print(f"Wrote {OUT_DIR / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
