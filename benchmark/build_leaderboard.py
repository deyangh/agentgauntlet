#!/usr/bin/env python3
"""Build the static leaderboard page from the newest benchmark summary.

    python benchmark/build_leaderboard.py

Writes ``benchmark/leaderboard/index.html`` — a self-contained page suitable for
GitHub Pages. Robustness and utility are shown side by side deliberately: a model
that scores well on one and badly on the other has not passed.
"""

from __future__ import annotations

import json
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BENCH_DIR / "results"
OUT_DIR = BENCH_DIR / "leaderboard"

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
</style>
</head>
<body>
<div class="wrap">
  <h1>AgentGauntlet leaderboard</h1>
  <p class="sub">
    {scenario_count} adversarial scenarios × {repeats} repeats · run {date} ·
    lower attack success is better, higher utility is better
  </p>

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
    <p>Every attack ran inside an in-process mock environment — no messages were
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


def main() -> int:
    summaries = sorted(RESULTS_DIR.glob("*/summary.json"))
    if not summaries:
        print("no benchmark results yet — run benchmark/run_benchmark.py first")
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
            rows="\n".join(rows),
        )
    )
    print(f"Wrote {OUT_DIR / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
