# Roadmap

## Round 1

Foundation: registry, tasks, lifecycle, routing, budgets, context, git inspect, manual adapters, reports, behavioral metrics, CLI, docs, tests.

## Round 2 (this release)

- Plan artifacts + approval gates (create/validate/submit/approve/reject/show)
- Fingerprints and approval invalidation
- Task/plan linkage; pre-approval handoff blocking
- Role-specific handoff packets
- Review verdicts: pass / pass_with_notes / changes_required / blocked
- Repair-round tracking with configurable max → blocked
- Synthetic `demo_projects/calculator-demo` lifecycle
- Open-source reference assessment (patterns only)
- Extended project-status

## Round 3+ (only with explicit approval)

- Equitify connection after the exact user command
- Git worktrees / sessions (Agent Orchestrator-inspired)
- Real provider CLI adapters (MCO-inspired), still no unpaid/unapproved network model spend without approval
- Any future automation beyond manual handoff

## Explicitly deferred

- LangChain / CrewAI / AutoGen
- Paid API adapters
- Browser automation
- Auto-merge / auto-push
- Self-modifying routing rules
- Copying third-party orchestrator code into this repo
