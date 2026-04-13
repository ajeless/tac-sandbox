# AGENTS.md

This file is the primary guide for coding agents working in this repo.

If `CLAUDE.md` or another agent-oriented file exists, it should point here.
If there is a conflict, follow `AGENTS.md`.

## What this repo is

This repo is for building **a domain-specific engine for authored turn-based tactical scenarios on flexible play surfaces**.

It is a tool for crafting and testing a specific family of experiences.
The exact product shape is expected to emerge through implementation and manual testing.

## Workflow

Use discussion to frame the next question, especially for structural or hard-to-reverse choices.
Answer it with the smallest runnable experiment that preserves flexibility and avoids premature assumptions.

Build in small, manually testable slices.

Preferred loop:
1. Discuss the next question
2. Build a small working piece
3. Test it manually
4. Revise from actual use
5. Repeat

Prefer short-lived, descriptively named branches for ideas, comparisons, and spikes.
Name branches for the question or capability they explore, not by phase or sequence.

Keep `main` as the current best known runnable baseline.
Do not merge into `main` until something has been manually tested and shown useful.

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
- `DECISIONS.md` when needed for settled constraints

Do not create planning or process docs until the work earns them.

## Runtime behavior

Development workflows should be predictable and non-obtrusive.

When scripts launch processes, they should:
- track what was started
- stop what they started
- free known ports on teardown

The project should play nice on Linux, macOS, and Windows.
