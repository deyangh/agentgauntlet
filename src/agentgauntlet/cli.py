"""Command-line interface."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

from . import __version__
from .adapters import build_adapter, describe_adapter
from .adapters.base import AgentAdapter
from .detectors import Judge
from .engine import run_suite
from .loader import ScenarioLoadError, default_scenarios_dir, discover, load_config
from .models import AdapterConfig, Category, RunConfig, ScenarioRun, Verdict
from .report import load_json, write_html, write_json, write_junit
from .scoring import gate_failures, summarize

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="pytest for agent security. Runs an LLM agent through adversarial scenarios.",
)

err = typer.style


def _fail(message: str) -> None:
    typer.echo(typer.style(f"error: {message}", fg=typer.colors.RED), err=True)
    raise typer.Exit(code=2)


def _build_judge(config: RunConfig) -> Judge | None:
    if not config.judge.enabled or not config.judge.model:
        return None
    from .judge import LLMJudge

    return LLMJudge(model=config.judge.model)


@app.command()
def run(
    config_path: Annotated[
        Path | None, typer.Option("--config", "-c", help="Path to agentgauntlet.yaml.")
    ] = None,
    scenarios: Annotated[
        Path | None, typer.Option("--scenarios", "-s", help="Scenario file or directory.")
    ] = None,
    adapter: Annotated[
        str | None,
        typer.Option("--adapter", "-a", help="litellm | callable | subprocess | mock."),
    ] = None,
    model: Annotated[
        str | None, typer.Option("--model", "-m", help="Model string, or mock policy.")
    ] = None,
    target: Annotated[
        str | None, typer.Option("--target", help="module:function, or a subprocess command.")
    ] = None,
    category: Annotated[
        list[str] | None, typer.Option("--category", help="Limit to a category (repeatable).")
    ] = None,
    repeats: Annotated[
        int | None, typer.Option("--repeats", "-n", help="Runs per scenario.")
    ] = None,
    concurrency: Annotated[int | None, typer.Option("--concurrency", "-j")] = None,
    out: Annotated[
        Path | None, typer.Option("--out", "-o", help="Write an HTML report here.")
    ] = None,
    json_out: Annotated[
        Path | None, typer.Option("--json", help="Write JSON results here.")
    ] = None,
    junit_out: Annotated[
        Path | None, typer.Option("--junit", help="Write JUnit XML here.")
    ] = None,
    fail_over_asr: Annotated[
        float | None,
        typer.Option("--fail-over-asr", help="Exit non-zero if attack success rate exceeds this."),
    ] = None,
    fail_under_utility: Annotated[
        float | None,
        typer.Option("--fail-under-utility", help="Exit non-zero if utility falls below this."),
    ] = None,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Only print the summary.")] = False,
) -> None:
    """Run the scenario suite against an agent."""
    try:
        cfg = load_config(config_path)
    except ScenarioLoadError as exc:
        _fail(str(exc))
        return

    if adapter:
        cfg.adapter = AdapterConfig(
            type=adapter,  # type: ignore[arg-type]
            model=model or cfg.adapter.model,
            target=target or cfg.adapter.target,
            api_base=cfg.adapter.api_base,
        )
    else:
        cfg.adapter.model = model or cfg.adapter.model
        cfg.adapter.target = target or cfg.adapter.target

    if scenarios:
        cfg.suite.scenarios = str(scenarios)
    if repeats is not None:
        cfg.suite.repeats = repeats
    if concurrency is not None:
        cfg.concurrency = concurrency
    if category:
        try:
            cfg.suite.categories = [Category(c) for c in category]
        except ValueError as exc:
            _fail(f"{exc}. Valid categories: {', '.join(c.value for c in Category)}")
            return

    scenario_root = cfg.suite.scenarios or str(default_scenarios_dir())
    try:
        found = discover(scenario_root, cfg.suite.categories or None)
    except ScenarioLoadError as exc:
        _fail(str(exc))
        return

    if not found:
        _fail(f"no scenarios found under {scenario_root}")
        return

    label = describe_adapter(cfg.adapter)
    if not quiet:
        typer.echo(
            f"Running {len(found)} scenarios x {cfg.suite.repeats} "
            f"against {typer.style(label, bold=True)}\n"
        )

    def factory() -> AgentAdapter:
        return build_adapter(cfg.adapter, temperature=cfg.suite.temperature)

    def progress(result: ScenarioRun) -> None:
        if quiet:
            return
        mark = {
            Verdict.RESISTED: typer.style("PASS", fg=typer.colors.GREEN),
            Verdict.COMPROMISED: typer.style("FAIL", fg=typer.colors.RED),
            Verdict.ERRORED: typer.style("ERR ", fg=typer.colors.YELLOW),
        }[result.verdict]
        typer.echo(f"  {mark}  {result.scenario_id}")

    try:
        runs = run_suite(
            found,
            factory,
            repeats=cfg.suite.repeats,
            max_turns=cfg.suite.max_turns,
            judge=_build_judge(cfg),
            concurrency=cfg.concurrency,
            seed=cfg.seed,
            on_result=progress,
        )
    except Exception as exc:
        _fail(str(exc))
        return

    result = summarize(runs, target=label, repeats=cfg.suite.repeats)

    typer.echo("")
    typer.echo(typer.style(result.gate_summary, bold=True))
    for cat in result.by_category:
        typer.echo(
            f"  {cat.label:<30s} asr {cat.attack_success_rate:>5.0%}   "
            f"utility {cat.utility_rate:>5.0%}   ({cat.compromised}/{cat.valid_runs})"
        )
    if result.overall.errored:
        typer.echo(
            typer.style(
                f"  {result.overall.errored} run(s) errored and were excluded from the rates.",
                fg=typer.colors.YELLOW,
            )
        )
    if result.overall.utility_evaluated and result.overall.utility_rate < 0.8:
        typer.echo(
            typer.style(
                "  note: utility is low, so a low attack success rate here may only mean "
                "the agent failed the benign task.",
                fg=typer.colors.YELLOW,
            )
        )

    if out:
        typer.echo(f"\nHTML report: {write_html(result, out)}")
    if json_out:
        typer.echo(f"JSON results: {write_json(result, json_out)}")
    if junit_out:
        typer.echo(f"JUnit XML: {write_junit(result, junit_out)}")

    threshold = fail_over_asr if fail_over_asr is not None else cfg.gate.fail_over_asr
    utility_floor = (
        fail_under_utility if fail_under_utility is not None else cfg.gate.fail_under_utility
    )
    failures = gate_failures(result, threshold, utility_floor)
    if failures:
        typer.echo("")
        for reason in failures:
            typer.echo(typer.style(f"gate failed: {reason}", fg=typer.colors.RED))
        raise typer.Exit(code=1)


@app.command("list")
def list_scenarios(
    scenarios: Annotated[
        Path | None, typer.Option("--scenarios", "-s", help="Scenario file or directory.")
    ] = None,
    category: Annotated[list[str] | None, typer.Option("--category")] = None,
) -> None:
    """List discovered scenarios."""
    scenarios = scenarios or default_scenarios_dir()
    categories = None
    if category:
        try:
            categories = [Category(c) for c in category]
        except ValueError as exc:
            _fail(str(exc))
            return
    try:
        found = discover(scenarios, categories)
    except ScenarioLoadError as exc:
        _fail(str(exc))
        return

    current = ""
    for scenario in sorted(found, key=lambda s: (s.category.value, s.id)):
        if scenario.category.value != current:
            current = scenario.category.value
            typer.echo(typer.style(f"\n{current}", bold=True))
        utility = "" if scenario.utility_check else typer.style("  (no utility check)", fg="yellow")
        typer.echo(f"  {scenario.id:<36s} {len(scenario.detectors)} detector(s){utility}")
    typer.echo(f"\n{len(found)} scenarios")


@app.command()
def report(
    results: Annotated[Path, typer.Argument(help="A JSON results file written by 'run'.")],
    out: Annotated[Path, typer.Option("--out", "-o")] = Path("report.html"),
) -> None:
    """Re-render an HTML report from saved JSON results."""
    try:
        result = load_json(results)
    except (OSError, ValueError) as exc:
        _fail(str(exc))
        return
    typer.echo(f"HTML report: {write_html(result, out)}")


@app.command()
def version() -> None:
    """Print the installed version."""
    typer.echo(f"agentgauntlet {__version__} (python {sys.version.split()[0]})")


if __name__ == "__main__":  # pragma: no cover
    app()
