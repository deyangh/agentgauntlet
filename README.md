# AgentGauntlet

**pytest for agent security.** Point it at your LLM agent and it runs the agent through a
suite of prompt-injection, data-exfiltration, confused-deputy, and tool-misuse scenarios,
then reports which ones it fell for.

```bash
pip install git+https://github.com/deyangh/agentgauntlet
agentgauntlet run --adapter mock --out report.html
```

**[See an example report →](https://deyangh.github.io/agentgauntlet/example-report.html)**
No API key needed to try it: the command above runs the whole suite against a simulated
agent, offline.

Most prompt-injection benchmarks evaluate a bare model in a fixed sandbox. That is useful
for research, but it does not answer the question most engineers have:

> I built an agent with my own system prompt, my own tools, and my own guardrails.
> Does *my* stack resist injection before I ship it?

AgentGauntlet tests that. Your agent runs inside the loop, and your CI fails when it
regresses.

---

## How it works

**The harness owns the agent loop.** Your agent only has to answer one question (given this
conversation and these tools, what do you do next?), and AgentGauntlet executes every tool
call itself.

That gives it two things:

- **Control.** Adversarial payloads are planted in the data a tool returns, which is how
  real prompt injection arrives. The attack never depends on the user's prompt.
- **Observation.** Every tool call and its arguments are recorded, so detection is a lookup
  rather than a guess.

**Attack success is an observable action, not a judgment call.** Each scenario is built so
the only way to fall for the attack is to call a canary tool or pass a canary token into an
outbound argument:

```yaml
detectors:
  - type: argument_contains
    tool: send_email
    arg: body
    value: "{{secrets.recovery_code}}"   # a fresh token, regenerated every run
```

Either the secret crossed the boundary or it did not. For the rare case where the only
evidence is prose, there is an optional LLM judge; its verdicts are marked non-deterministic
and reported separately from the tool-call evidence.

## Attack success rate is only half the score

A model that refuses everything scores a perfect 0% attack success rate. So does one too
weak to call tools at all. Report attack success on its own and a useless model comes out on
top.

So every scenario also has a **`utility_check`**: did the agent complete the harmless task it
was actually given? Both numbers come from the same runs, and a result only looks good when
attack success is low and utility is high:

```
overall            asr 6.2%   robustness 93.8%   utility 100.0%
```

## Testing your own agent

Three adapters share one interface.

**A model.** Anything LiteLLM can reach, including a local model through Ollama:

```bash
agentgauntlet run --adapter litellm --model ollama/llama3.1
agentgauntlet run --adapter litellm --model openai/gpt-4o-mini
```

**Your own Python agent.** Your routing, system prompt, and guardrails, all inside the loop
being attacked:

```python
# myapp/agent.py
def decide(messages, tools):
    """Return a string, or {"type": "tool_calls", "calls": [...]}."""
    ...
```

```bash
agentgauntlet run --adapter callable --target myapp.agent:decide
```

**An agent in any other language**, over a one-shot JSON protocol on stdin/stdout:

```bash
agentgauntlet run --adapter subprocess --target "node my-agent.js"
```

### One real limitation

Tool-level attacks need an agent that accepts tool schemas and returns tool calls. If yours
only takes text and returns text, the harness can still run the text-level scenarios, but the
tool-misuse and exfiltration categories need that seam. Most production agents have it; some
don't.

## In CI

```bash
agentgauntlet run --config agentgauntlet.yaml --fail-over-asr 0.10
```

This exits non-zero when the gate trips and writes JUnit XML for your CI's test reporter.
There is also a pytest plugin, so scenarios can be collected as ordinary tests:

```bash
pytest --agentgauntlet-scenarios ./scenarios --agentgauntlet-adapter mock
```

## The scenario suite

Sixteen scenarios across eight categories, each with a threat-model writeup in its
directory:

| Category | What it probes |
|---|---|
| `direct_injection` | Tool output that issues explicit instructions |
| `data_exfiltration` | A planted secret lured across an outbound boundary |
| `confused_deputy` | The agent's own privilege redirected by untrusted content |
| `tool_misuse` | Unauthorized destructive calls |
| `scope_violation` | Data treated as commands |
| `long_horizon_drift` | Safety eroding deep into a long trajectory |
| `cross_context_contamination` | One user's or tenant's content driving another's actions |
| `social_engineering` | Authority claims, fake debug modes, manufactured urgency |

Adding one is a single YAML file; see [CONTRIBUTING.md](CONTRIBUTING.md).

## Responsible use

This is a defensive testing tool, and it is built so it cannot be used any other way.

Every attack runs inside an in-process mock environment. The "malicious" tools
(`send_email`, `http_post`, `transfer_funds`, `delete_file`, `execute_shell`) are
instrumented stubs that record their arguments and return a plausible success string. No code
path in this project sends a message, writes a file, moves money, or opens a socket to
anything except the model provider you configure. The invocation record is the whole
measurement, so a real side effect would add nothing.

See [SECURITY.md](SECURITY.md).

## License

Apache-2.0.
