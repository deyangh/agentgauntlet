# Write-up template

Fill this in **after** the first benchmark run. This document is the highest-leverage
artifact in the repository: the code proves you can build, and the write-up proves you
understand what you built and what the numbers mean. It is also what gets a project
discussed rather than merely starred.

Publish it on your site and link it from the README.

---

## Suggested title

Something claim-shaped, not project-shaped. "I tested N agent configurations for prompt
injection — here's what broke" beats "Announcing AgentGauntlet."

## 1. The problem (≈200 words)

Open with the gap, not the tool. Agent security is not model safety: a model can refuse
every harmful request in a chat box and still hand over a credential when the request
arrives inside a tool result. Existing benchmarks measure bare models in fixed sandboxes;
engineers ship assembled stacks — a system prompt, a set of tools, an MCP server or two —
and have no way to test the thing they actually deployed.

## 2. Method (≈400 words)

The two decisions worth explaining in detail, because they are what make the numbers mean
anything:

- **The harness owns the agent loop.** Explain what this buys: control over where payloads
  appear, and observation of every tool call.
- **Attack success is an observable action.** Canary tools and per-run canary tokens. Show
  the `argument_contains` snippet. State plainly that a detector either fired or it did not.

Then the honest methodology notes:

- Utility baseline, and *why* — a refusing model scores a perfect ASR otherwise.
- Errored runs excluded from rates, not counted as resistance.
- Repeats and temperature; which scenarios were unstable across repeats.
- The LLM judge is secondary and its verdicts are segregated.

## 3. Findings (the part people quote)

Lead with one number. Fill these in from `benchmark/results/`:

> Across ___ agent configurations and ___ scenarios, ___% of runs executed instructions
> planted in tool output.

Then the structure behind it:

- Which **category** was hardest across the board? (Prediction worth checking: scope
  violation and long-horizon drift, since neither requires an adversary to be clever.)
- Which category was easiest, and does that suggest training coverage rather than genuine
  reasoning about trust boundaries?
- Did any model score low ASR **because** it had low utility? Name it. This is the finding
  a careless benchmark would have reported as a win.
- Did results move between repeats? Report the unstable scenarios rather than hiding them.
- Anything surprising in a transcript — quote it. One vivid trajectory is worth a table.

## 4. Limitations (do not skip — this section is why readers trust the rest)

- Mock environments are not production. Real tools have latency, errors, partial results.
- Sixteen scenarios is a starting suite, not coverage. Absence of a finding is not evidence.
- Scenario wording is itself a variable; a rephrased payload can move a model's score.
- Detectors measure the action, not the reasoning. An agent can do the right thing for the
  wrong reason and pass.
- Results are a snapshot of specific model versions on a specific date.

## 5. What's next

Keep it concrete: more scenarios, adapters for real deployed agents, defenses to measure
against (spotlighting, delimiters, tool-level allowlists) rather than only models.

---

### Publishing checklist

- [ ] Numbers match the committed JSON in `benchmark/results/` (auditable claims only)
- [ ] Leaderboard regenerated and linked
- [ ] Model versions and run date stated explicitly
- [ ] Responsible-use note carried over: every attack ran in a mock environment
- [ ] README links to the write-up; the write-up links to the repo
