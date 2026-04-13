# tac-sandbox

Greenfield workspace for tactical scenario engine experiments.

`AGENTS.md` is the authoritative guide for repo intent, working style, and decision-making.
`CLAUDE.md` exists only as a pointer to `AGENTS.md`.

Run the current spike with:

```bash
uv run python -m tac_sandbox.cli scenarios/ship_duel.toml
```

Minimal browser host:

```bash
uv run python -m tac_sandbox.web_host scenarios/ship_duel.toml --port 8000
```
