# AGENTS.md

This file is the primary guide for coding agents working in this repo.

If `CLAUDE.md` or another agent-oriented file exists, it should point here.
If there is a conflict, follow `AGENTS.md`.

## What this repo is

This repo is for building **a domain-specific engine for authored turn-based tactical scenarios on flexible play surfaces**.

It is a tool for crafting and testing a specific family of experiences.
The exact product shape is expected to emerge through implementation and manual testing.

## How to work here

Build in small, manually testable slices.

Preferred loop:
1. Build a small working piece
2. Test it manually
3. Revise from actual use
4. Repeat

Optimize for discovering what works.

Keep a **portable core** and a **replaceable host**.
Treat the first host runtime or engine as a convenience, not the product architecture.

Prefer:
- readable authored data
- reversible decisions
- adapters over hard coupling
- quick startup, reload, reset, and inspection
- simple creator-facing loops over broad infrastructure

## What to optimize for

Choose changes that make the repo more:
- runnable
- testable
- readable
- adaptable
- useful to the next creator-facing loop

Text-first authoring is acceptable and preferred early on.

## What to avoid

Avoid **premature generalization**:
building large abstractions or systems before they are needed.

Avoid **premature lock-in**:
binding the core too tightly to one host, board model, or future target.

Avoid **premature sprawl**:
broadening scope, adding heavy docs, or creating complexity before the current loop works.

## Docs

Keep docs light.

Early repo docs should usually be limited to:
- `README.md`
- `AGENTS.md`
- `CLAUDE.md`
- `DECISIONS.md` when needed

## Runtime behavior

Development workflows should be predictable and non-obtrusive.

When scripts launch processes, they should:
- track what was started
- stop what they started
- free known ports on teardown

The project should play nice on Linux, macOS, and Windows.

## Decision rule

When direction is unclear, choose the smallest runnable path that preserves flexibility, can be tested manually, and avoids premature assumptions.
