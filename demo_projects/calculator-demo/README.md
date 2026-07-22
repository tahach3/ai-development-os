# Calculator Demo

Synthetic project under `ai-development-os/demo_projects/calculator-demo` for proving the
manual AI Development OS lifecycle. **Not connected to Equitify.**

## Module

- `calculator/ops.py` — `add`, `subtract` (multiplication added via Round 2 demo task)

## Git for Round 3A sessions

`create-session` requires this directory to be a Git repository. If needed:

```bash
cd demo_projects/calculator-demo
git init -b main
git add -A
git -c user.email=demo@ai-dev-os.local -c user.name=Demo commit -m "init calculator-demo"
```

## Tests

```bash
cd demo_projects/calculator-demo
python -m pytest -q
```
