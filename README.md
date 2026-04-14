# tac-sandbox

Greenfield workspace for tactical scenario engine experiments.

`AGENTS.md` is the authoritative guide for repo intent, working style, and decision-making.
`CLAUDE.md` exists only as a pointer to `AGENTS.md`.

Run the current spike with:

```bash
uv run python -m tac_sandbox.cli scenarios/ship_duel.toml
```

Managed browser host:

```bash
./scripts/start.sh
./scripts/stop.sh
```

Windows PowerShell:

```powershell
./scripts/start.ps1
./scripts/stop.ps1
```

The managed host defaults to `scenarios/ship_duel.toml` on `127.0.0.1:8000`.
It tracks state and logs under `.run/`.
