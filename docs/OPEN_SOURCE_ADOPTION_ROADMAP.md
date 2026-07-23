# Open-Source Adoption Roadmap

**Version:** `1.0`  
**Status:** Persisted architecture decision (Round 4D1.3)  
**Authority:** AI Development OS remains the workflow authority

---

## Architecture decision

AI Development OS remains the authority for:

- project registration;
- path restrictions;
- tasks;
- plans;
- approvals;
- fingerprints;
- worktrees;
- safe execution;
- repair limits;
- testing;
- review;
- reporting;
- audit history;
- merge and deployment gates.

External open-source components must be **replaceable adapters** or **reference implementations**. They must not become competing workflow authorities.

Related references (patterns only unless a later round authorizes installation):

- `docs/OPEN_SOURCE_REFERENCE_ASSESSMENT.md`
- `docs/AI_OS_OPEN_SOURCE_INTEGRATION_MASTER_BLUEPRINT.md`

---

## NOW — PROVIDER PATH

| Component | Role |
| --- | --- |
| **OpenAI Codex CLI** | Official first headless **implementer** candidate (Round 4D1.3 readiness; Round 4D2 separately gated). |
| **Claude Code** | Later candidate for planning, implementation, or separate review. |
| **Cursor** | Interactive editor only unless a genuine supported headless agent CLI is discovered later. |

Round 4D1.3 installs and authenticates Codex for readiness only — **zero** model prompts.

---

## NEXT — PROTOCOL STANDARDIZATION

- **Agent Client Protocol (ACP):** evaluate as an optional provider transport and capability-negotiation layer.
- ACP must **not** own task state, approvals, repair policy, or report truth.
- **Not installed** in Round 4D1.3.

---

## SECURITY ADAPTERS

Future independent checks (results remain separate — never one vague “security passed”):

| Tool | Purpose |
| --- | --- |
| **zizmor** | GitHub Actions security |
| **pip-audit** | Known Python dependency vulnerabilities |
| **Gitleaks** | Secret detection in files and, where explicitly enabled, Git history |

**Not installed** in Round 4D1.3.

---

## EVALUATION

Use **Inspect AI** and **mini-swe-agent** as design references for:

- reproducible tasks;
- append-only trajectories;
- scorer separation;
- environment isolation;
- wall-clock limits;
- benchmark comparisons.

Do **not** replace the existing orchestration engine.

---

## SANDBOX EVALUATION

Evaluate **SWE-ReX** and **OpenShell** later against the existing worktree and safe runner.

Adopt only when measured safety or reliability gains justify the dependency.

---

## REPORTING EXTENSIONS

Round 4C canonical JSON remains the reporting source of truth.

**Ghostwriter** may be studied for:

- template organization;
- document export;
- reusable report sections;
- sanitized one-way export.

Do **not** embed Ghostwriter’s complete application, database, authentication, or workflow system.

**PwnDoc**, **Dradis**, and similar full reporting platforms remain reference-only unless a separate architecture and licensing review approves them.

---

## DO NOT ADOPT AS THE CORE

Do not replace the OS with:

- OpenHands;
- LangGraph;
- CrewAI;
- AutoGen;
- SWE-agent;
- another lifecycle or multi-agent framework.

(Blueprint documents may discuss optional peripheral roles; they do not override this roadmap.)

---

## DEPENDENCY GATES

Before any external component is installed into the product:

1. confirm the problem it solves;
2. inspect license;
3. inspect transitive dependencies;
4. inspect network behavior;
5. inspect data-retention behavior;
6. inspect Windows support;
7. define an adapter boundary;
8. define removal and fallback behavior;
9. add synthetic tests;
10. receive explicit authorization.

Round 4D1.3 authorization covers **official OpenAI Codex CLI only** among external provider tools.
