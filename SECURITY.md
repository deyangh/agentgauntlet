# Security and responsible use

## What this project is

AgentGauntlet is a **defensive** testing tool. It measures whether an LLM agent can be
talked into doing something it should not, so that the people building that agent can fix
it before shipping.

## What it cannot do

The scenarios describe attacks, but nothing in this repository executes one against a real
system. That is a property of the design, not a policy we ask contributors to remember:

- Every tool the agent under test can reach is a **mock defined in a scenario file**. The
  agent has no route to the network, the filesystem, or a subprocess.
- The sink tools (`send_email`, `http_post`, `post_message`, `share_document`,
  `transfer_funds`, `delete_file`, `execute_shell`, `revoke_access`, `update_permissions`)
  are implemented in [`stdlib_tools.py`](src/agentgauntlet/stdlib_tools.py) as dataclasses
  holding a description and a response string. They record their arguments and return a
  plausible success message. There is no I/O in that module at all.
- Recording the invocation is the whole measurement, so a real side effect would add nothing
  to the result.

The only outbound network traffic the tool generates is model inference: calls to whichever
provider you configured, using your own credentials, plus the optional LLM judge.

The `subprocess` adapter runs a command **you supply on your own command line** in order to
test your own agent. It is the same trust level as any other CLI flag that takes a command.

## Scope for contributions

Scenarios are welcome. Anything that gives the harness a real capability is not:

- No scenario may perform real network requests, filesystem writes, or process execution.
- No scenario may target a real third-party service, account, or person.
- Payloads must be synthetic. Do not contribute working exploits for real systems,
  credentials, or content harvested from a real user's data.

Pull requests adding real side effects to the mock environment will be declined.

## Reporting a vulnerability

If you find a way to make AgentGauntlet itself do something harmful (escape the mock
environment, execute unintended code from a scenario file, leak credentials from the host),
please open a GitHub security advisory rather than a public issue.
