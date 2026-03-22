---
name: openspec
description: Use OpenSpec CLI for spec-driven software planning, change proposals, acceptance criteria, task breakdown, and artifact validation before delegating implementation.
metadata: {"openclaw":{"requires":{"bins":["openspec"]}}}
user-invocable: false
---

# OpenSpec

Use this skill when you are the `spec` agent and need to turn a software request into a structured OpenSpec plan before delegating work.

## Goals

- capture scope, non-goals, constraints, and acceptance criteria
- create or refine OpenSpec change/spec artifacts for the current task
- produce implementation-ready instructions before handing work to `coder`, `qa`, `docs`, `release`, or `deploy`
- validate OpenSpec artifacts before downstream execution when practical

## Command Workflow

Use the installed `openspec` CLI rather than improvising a freeform plan when the task is non-trivial.
Common commands:

- `openspec list`
- `openspec status`
- `openspec show <item-name>`
- `openspec new`
- `openspec change`
- `openspec spec`
- `openspec instructions`
- `openspec validate <item-name>`

If command syntax is unclear, check `openspec --help` or `openspec help <command>` first.

## Required Behavior

- Use OpenSpec to frame the work before delegating implementation for non-trivial software tasks.
- Treat OpenSpec artifacts as planning and coordination assets, not as a substitute for implementation.
- After creating or updating OpenSpec artifacts, summarize the current scope, acceptance criteria, blocker, and next handoff in `TASK_STATUS.md`.
- When delegating to another agent, reference the relevant OpenSpec artifact names or instructions so downstream work is grounded in the same plan.
