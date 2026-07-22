# Roadmap

## Round 1

Foundation: registry, tasks, lifecycle, routing, budgets, context, git inspect, manual adapters, reports, behavioral metrics, CLI, docs, tests.

## Round 2

- Plan artifacts + approval gates (create/validate/submit/approve/reject/show)
- Fingerprints and approval invalidation
- Task/plan linkage; pre-approval handoff blocking
- Role-specific handoff packets
- Review verdicts: pass / pass_with_notes / changes_required / blocked
- Repair-round tracking with configurable max → blocked
- Synthetic `demo_projects/calculator-demo` lifecycle
- Open-source reference assessment (patterns only)
- Extended project-status

## Round 3A (this release)

Safe execution foundation (no provider CLI spawn yet):

- Isolated session + worktree lifecycle for registered synthetic projects
- Allowlisted subprocess (`shell=False`, pytest profile only)
- Path confinement + symlink-escape checks
- Env filtering, timeouts, output-size limits
- Normalized execution envelopes + audit JSON
- CLI: `create-session`, `show-session`, `list-sessions`, `cleanup-session`, `run-tests`, `show-execution`
- Design: `docs/ROUND_3A_SAFE_EXECUTION_DESIGN.md`

## Round 3B+ (only with explicit approval)

- Real provider CLI adapters (Claude / Cursor / Codex), still no unpaid/unapproved network model spend without approval
- Broader command profiles beyond pytest
- Equitify connection after the exact user command
- Any future automation beyond manual handoff + local allowlisted exec

## Explicitly deferred

- LangChain / CrewAI / AutoGen
- Paid API adapters
- Browser automation
- Auto-merge / auto-push
- Self-modifying routing / safety rules
- Copying third-party orchestrator code into this repo
