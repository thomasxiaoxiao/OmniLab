# Replit integration checkpoint

Started October 3, 2026, 19:39 PDT. Production launch correction verified through
the Replit Agent result and running preview at 20:11 PDT. Private publication
remains incomplete.

The user confirmed the signed-in Replit Core account, a new private app for this
repository, and spending limited to included credits. The initial browser check
showed $20 remaining, no top-ups and auto-reload off. No purchase, upgrade,
auto-reload enablement is authorized. The user subsequently requested correction
of the failed deployment and successful publication of this existing app, without
rebuilding the project unnecessarily. Private access remains required.

App: https://replit.com/replid/c50d44bc-1f3e-4bcd-b5f5-9cc19bbf59cb

Replit app ID: `c50d44bc-1f3e-4bcd-b5f5-9cc19bbf59cb`. Reuse this app; do not
create another to retry setup. The Replit connector is connected. Initial
publication inspection returned `found: false`. A later publication failed:
deployment `35530e18-7120-4a61-8996-a271a61406fe`, build
`3c168332-790d-484b-af5a-04e5fa3e17c3`. At 02:49:11 UTC on October 4, its log
reported that the production run command contained a potentially vulnerable
`dev` configuration. The actual artifact configuration pointed production to
`pnpm --filter @workspace/omnigent-lab run dev`.

The Replit Agent was stopped and the queued deployment-debug request removed.
No further Agent question/update was submitted during that revalidation. User-reported
spend is three charges of $0.20; a billing breakdown has not been independently
verified. Agent questions can incur usage even when they request read-only work.

Private source visibility still needs an authenticated settings check. The
deployment form initially selected Public; Invite only was then selected, but
publication under that setting has not yet been verified.

## Intended integration

Import https://github.com/thomasxiaoxiao/OmniLab and preserve the
existing Python/Streamlit scientific application and Omnigent orchestration.
The local checkout had uncommitted work during setup. Importing GitHub does not
copy those changes. Record and compare the actual imported commit before claiming
that Replit contains the latest local implementation.

| Tier | Required route | Verified local state |
| --- | --- | --- |
| Complex reasoning | Codex through Omnigent by default | Local configuration uses Codex, `gpt-6-astra`, medium effort; login status confirms ChatGPT authentication |
| Quick closed decisions | Local Qwen plus AnyJev | Pinned Qwen3-4B-Instruct-2507 MLX model; 11 manifest files passed hash/size verification |
| Optional alternative reasoning | Explicitly selected Claude through managed Replit integration | Replit Agent reports provisioned; authentication/inference not tested |

Replit-managed OpenAI and Anthropic access was requested. It is distinct from
Codex subscription authentication. No personal credential files or API key values
were copied. The existing MLX adapter requires Apple Silicon; Replit Linux cannot
run it unchanged. A secure connection to the local worker or a separately verified
compatible implementation is still required. Do not silently use a hosted Qwen,
another paid provider, mock, or replay when the required tier is unavailable.

The older adaptive workflow has a hybrid Codex-assessment/AnyJev-action path.
At inspection, the uncommitted new repository workflow uses Omnigent for every
role and its UI forces the Codex decision setting. Do not represent that path as
an already functioning two-tier implementation. The older hybrid still requests
a complex assessment before each local action; no call reduction is established.

## Requested guards, not yet verified enforcement

- Six complex requests per run and 20 per UTC day, shared across providers.
- One concurrent request, zero automatic retries and a 120-second timeout.
- Two research rounds and 16 local decisions per run.
- Explicit input/output bounds and a persistent daily ledger checked before calls.
- Live model requests disabled until guards, authentication and routing pass.
- Included Replit credits only; auto-reload remains off.

An application call/token cap is not an account dollar shutdown limit. Replit
Agent setup costs are separate from scientific-model requests and have not yet
been measured. Account-wide shutdown configuration beyond the observed disabled
auto-reload has not been verified. A prompt is not cost enforcement.

## Setup attempts and local validation

The initial creation request returned a new app. A subsequent read-only Replit
Agent check reported only a starter application: no repository import, managed
OpenAI/Anthropic provisioning or usage guards. Its workspace commit
`0c05d76b9e518521a819bcdca13cfdf07cc61818` was not established as a source-repository
commit. A correction request to the same app then requested the actual import,
provider provisioning and offline guard verification. Its visible conversation
reports the actual import at `d525e91fac65aa1f764c42f4d707917910b4e237`, both
managed providers provisioned, 37 offline checks passing, a disabled start-run
button, and zero application-ledger calls. These are Agent-reported checks, not
independent live provider or routing validation. The remote host has no Codex
executable/authentication, configured Omnigent endpoint, or working Qwen bridge.

Direct configuration inspection confirmed the existing Streamlit launcher uses
headless mode, an explicit port/address, no file watcher, and disabled static
file serving. A production `start` script referencing that same launcher has
been saved directly in the Replit editor. The intended correction was to point the
artifact's production command at `start`, then verify startup and publish. No
scientific application code was rewritten for this correction. Browser work
paused when Chrome switched to unrelated email; automatic approval review
blocked reading that window. The user was asked to leave Replit selected.

At 20:05 PDT another publication reported the same development-command error.
The user explicitly requested fixing the configuration and retrying. At 20:07
PDT one narrowly scoped Replit update requested only the production launch
correction and a bounded no-inference startup check. It must not regenerate or
reimport the project, upgrade dependencies, remove guards, or publish before
verification. This request can consume included credits; no paid diagnostic
question was submitted. Its final result reported a one-line production command
change from `dev` to `start`, validated saved configuration, and a bounded
startup health check returning HTTP 200 / `ok` before stopping its test process.
The preview independently loaded the original Streamlit interface, its disabled
run button, and managed provider provisioning indicators. No scientific-model
inference or application rewrite was performed.

Saved deployment visibility remained `public`; the earlier Invite only selection
was not persisted by publication. At 20:15 PDT a second narrowly scoped request
attempted to save private visibility and retry once. It stopped after 39 seconds:
its supported tools can read deployment visibility but cannot change it. No retry
was started. Native UI attempts repeatedly encountered inaccessible element frames
or unavailable windows. The user was asked to save Invite only in Publishing
settings and click Republish so the result can be checked through read-only
deployment metadata. Successful deployment and private access are not yet claimed.

Local checks during this integration task:

```bash
.venv/bin/pytest tests/test_decisions.py tests/test_omnigent_adapter.py -q
```

Result: 19 tests passed in 2.30 seconds. Qwen manifest verification passed and
Codex login status returned success with ChatGPT authentication. These are local
software/readiness checks, not new inference, Replit connectivity, scientific
results, or live two-tier orchestration evidence. No scientific-model inference
was run by this task during these checks.

## Provider documentation inspected

- [Replit AI integrations](https://docs.replit.com/features/integrations/replit-ai-integrations):
  managed OpenAI and Anthropic access consumes Replit credits; BYOK bills the
  provider separately.
- [Replit spending controls](https://docs.replit.com/billing/managing-spend):
  account usage limits and auto-reload are distinct controls; verify the controls
  offered by this account before treating any dollar cap as enforced.
- [Codex authentication](https://learn.chatgpt.com/docs/auth): ChatGPT sign-in and
  API-key authentication have different billing routes.

No scientific scope change, new result, deployment, or submission is claimed.
