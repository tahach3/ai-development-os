# Project Boundaries

> Formalized under [`docs/CONSTITUTION.md`](CONSTITUTION.md) (Articles VIII / XV — Engineering Law and Business Separation). This file remains the operational boundary ruleset; the Constitution does not replace it.

## Registry rule

Work is allowed **only** for projects present in `config/projects.yaml` (created via `ai-dev-os init` / `register-project`).

- Unregistered project IDs → refused
- Tasks referencing missing projects → refused
- Paths matching project `prohibited_path_prefixes` → refused

## Equitify

- **Not registered** in the example or default registry.
- Sentinels such as `equitify`, `equitify-machine` are rejected at registration time.
- Do not open, inspect, modify, copy from, test, or integrate `C:\Users\Taha\equitify-machine` until the user explicitly commands connection.

## Path discipline

- Prefer paths under the registered `root_path`.
- Task `allowed_paths` / `prohibited_paths` are validated for emptiness and conflicts.
- Context packets list capped paths only — **no full repo dump**.

## Workspace isolation

Runtime artifacts live under `workspace/` inside **this** repository (`ai-development-os`), not inside target project trees unless a handoff intentionally references them.
