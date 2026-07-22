# Open-Source Reference Assessment (Round 2)

Review date: 2026-07-22.

Method: public GitHub metadata (`gh api`), README/docs pages, and published documentation. **No repositories were cloned into this product. No reference code was copied. No new dependencies were added from these projects.**

Adoption rule for Round 2: **architectural patterns and concepts only**, independently re-implemented in Python inside `ai-development-os`.

This document remains the record of the Round 2 reference review. Integration decisions and the future reuse strategy are extended or superseded by [`docs/AI_OS_OPEN_SOURCE_INTEGRATION_MASTER_BLUEPRINT.md`](AI_OS_OPEN_SOURCE_INTEGRATION_MASTER_BLUEPRINT.md).

---

## 1. AgentWrapper/agent-orchestrator

| Field | Finding |
| --- | --- |
| Purpose | Meta-harness / agent IDE for fleets of parallel coding agents with sessions, terminals, PRs, and feedback loops. |
| License | Apache-2.0 |
| Language / runtime | Go (+ TypeScript/Next.js dashboard and plugin ecosystem historically described as Node/plugin monorepo) |
| Supported agents | Claude Code, Codex, Cursor, Kimi Code, OpenCode, Aider, and similar terminal agents |

**Architecture / models / lifecycle**

- Plugin slots: Runtime, Agent, Workspace, Tracker, SCM, Notifier, Terminal; Lifecycle is core/non-pluggable.
- Session lifecycle with isolated **git worktrees** per session.
- Event bus, prompt assembly, activity detection, daemon supervision.
- Autonomous loops for CI fixes, merge conflicts, and reviews.

**Git isolation / review / outputs**

- Worktree-per-session isolation; SCM plugins for PR/CI.
- Dashboard + CLI status views; plugin-driven notifications.

**Windows / security**

- Process/ConPTY runtimes mentioned for Windows; tmux defaults are Unix-oriented.
- Security concerns: autonomous merge/CI loops, broad plugin surface, network integrations (GitHub/Slack), executing agent CLIs.

**Adopt / reject**

| Adopt (Round 3+) | Reject (Round 2) |
| --- | --- |
| Conceptual session + isolation boundaries | Worktrees, daemon, dashboard, auto CI/merge |
| Clear adapter/plugin *interfaces* as future design notes | Real agent spawning or paid/network providers |

**Adoption form:** architectural pattern only. **Not implemented in Round 2.**

---

## 2. mco-org/mco

| Field | Finding |
| --- | --- |
| Purpose | Multi-CLI Orchestrator: fan-out prompts to multiple agent CLIs; aggregate structured outputs. Successor effort noted as Hive. |
| License | MIT |
| Language / runtime | Python |
| Supported agents | Claude Code, Codex CLI, Gemini CLI, OpenCode, Qwen Code, Hermes/Pi (opt-in), OpenClaw callers |

**Architecture / models / lifecycle**

- Provider adapter concept: dispatch to named CLIs in parallel.
- Structured outputs: JSON, SARIF, Markdown.
- Self-describing CLI help for agent-driven discovery.

**Git isolation / review / outputs**

- Review fan-out (`mco review`) rather than durable task state machine.
- Aggregation/consensus oriented; not a full plan-approval OS.

**Windows / security**

- CLI-based; Windows depends on local agent CLI availability.
- Security concerns: spawning external agents, network via providers, consensus automation without human gates.

**Adopt / reject**

| Adopt (Round 3+) | Reject (Round 2) |
| --- | --- |
| Provider-adapter *concept* for future real CLI wiring | Real provider connections, parallel fan-out execution |
| Structured report shapes as inspiration | Dependency on MCO/Hive |

**Adoption form:** architectural pattern only. Round 2 keeps `automation_status: manual_handoff_required` placeholders.

---

## 3. gotalab/cc-sdd

| Field | Finding |
| --- | --- |
| Purpose | Spec-driven development harness: discovery → requirements → design → tasks → approved-spec implementation with independent review. |
| License | MIT |
| Language / runtime | TypeScript (Agent Skills / slash-command packaging) |
| Supported agents | Claude Code, Codex, Cursor, Copilot, Windsurf, OpenCode, Gemini CLI, Antigravity |

**Architecture / models / lifecycle**

- Durable artifacts: `brief.md`, requirements, design, `tasks.md`, steering docs.
- Phase gates with human review before implementation (`/kiro-impl` only after approved tasks).
- Independent reviewer pass; bounded remediation/debug loops; resumability via durable specs.
- Boundaries / steering for project rules.

**Git isolation / review / outputs**

- Spec files as source of truth; GO / NO-GO / MANUAL_VERIFY_REQUIRED style validation outcomes.
- Fresh implementer/reviewer contexts per task in autonomous mode.

**Windows / security**

- Skills install across IDEs; Windows generally supported where host agents run.
- Security concerns: autonomous `/kiro-impl`, optional auto-approval flags (`-y` / `--auto`) — incompatible with our Round 2 hard gates.

**Adopt / reject**

| Adopt (Round 2) | Reject (Round 2) |
| --- | --- |
| Approved-spec / approved-plan gate before implementation | Autonomous subagent execution |
| Durable plan/requirements-style artifact fields | Copying skills/templates or installing cc-sdd |
| Independent review + resumability mindset | Auto-approval bypass flags |

**Adoption form:** architectural pattern only (plan artifact + approval boundaries). Independent Python models/CLI.

---

## 4. liza-mas/liza

| Field | Finding |
| --- | --- |
| Purpose | Hardened multi-agent coding system: mechanical Go state machine + role-separated agents. |
| License | Apache-2.0 |
| Language / runtime | Go |
| Supported agents | Popular coding-agent CLIs wrapped by supervisors |

**Architecture / models / lifecycle**

- Explicit task state machine with many forbidden transitions.
- Planner/reviewer separation; no self-approval.
- Audit fields: `assigned_to`, `reviewing_by`, `approved_by`, `base_commit` / `review_commit`, merge traceability.
- Status concepts include blocked / rejected / superseded-style terminal and repair paths; `done_when`-style completion criteria in specs.
- Blackboard / structured state as source of truth.

**Git isolation / review / outputs**

- Isolated git worktrees; supervisor-enforced merges and TDD gates.
- Adversarial review protocol with structured findings.

**Windows / security**

- Worktree/supervisor model may be Unix-leaning; verify before any future port.
- Security concerns: autonomous merge authority, large surface of agent supervisors — we keep human approval and manual handoff.

**Adopt / reject**

| Adopt (Round 2) | Reject (Round 2) |
| --- | --- |
| State-machine discipline; planner ≠ approver for high-risk | Worktrees, Go supervisors, autonomous merge |
| `approved_by`, starting/base commit, blocked/rejected/superseded | Dependency on Liza |
| Role separation for plan vs implementation vs review | Self-clearing pre-execution checkpoints without human gate |

**Adoption form:** architectural pattern only. Independent Python enums/models/gates.

---

## 5. umputun/ralphex

| Field | Finding |
| --- | --- |
| Purpose | Extended “Ralph” loop for autonomous plan execution with review iterations. |
| License | MIT |
| Language / runtime | Go |
| Supported agents | Claude (+ external review tools such as Codex) |

**Architecture / models / lifecycle**

- Iteration loops with `max_iterations` / `max_external_iterations`.
- Fresh-context style re-runs; stalemate detection (`review_patience`) when HEAD/diff unchanged.
- Terminates on resolved issues, max rounds, stalemate, or manual break.

**Git isolation / review / outputs**

- HEAD hash / diff fingerprint checks for progress and stalemate.
- Plan file driven execution.

**Windows / security**

- Manual break via SIGQUIT noted as not available on Windows.
- Security concerns: autonomous execution loops and token spend — explicitly out of Round 2 scope.

**Adopt / reject**

| Adopt (Round 2) | Reject (Round 2) |
| --- | --- |
| Max repair-round limit → blocked / human review | Autonomous Ralph execution |
| Stalemate / no-progress as a *concept* for later | SIGQUIT control loops, live Claude spawning |
| Fingerprint/HEAD mismatch as gate inspiration | Dependency on ralphex |

**Adoption form:** architectural pattern only (repair-round tracking + configurable max).

---

## Round 2 decision summary

| Source | Round 2 action |
| --- | --- |
| CC-SDD | **Adopt patterns:** approved plan gate, durable plan fields, independent review mindset |
| Liza | **Adopt patterns:** lifecycle FSM, audit fields (`approved_by`, starting commit), blocked/rejected/superseded, planner≠approver |
| Ralphex | **Adopt patterns:** max repair rounds → blocked; stalemate concept documented for later |
| Agent Orchestrator | **Study only:** worktrees/sessions deferred to Round 3 |
| MCO | **Study only:** real provider CLI adapters deferred to Round 3 |

**Copied source code:** none.  
**New dependencies from these projects:** none.  
**Attribution:** conceptual inspiration only; see `docs/ARCHITECTURE.md` “Inspired by” notes. No `THIRD_PARTY_NOTICES` required unless/until code is copied (preferred: never).
