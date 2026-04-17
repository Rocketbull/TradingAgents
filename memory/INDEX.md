# Project Memory Index

This folder holds durable project knowledge for agents. Read this file first, then open only the files relevant to the task.

## Files
- `PROJECT.md`: repository purpose, priorities, environment, and skills.
- `ENGINEERING_PRINCIPLES.md`: first-principles engineering rules and overengineering guardrails.
- `ARCHITECTURE.md`: stable module boundaries and data/I/O expectations.
- `WORKFLOWS.md`: common commands and validation routines.
- `DECISIONS.md`: durable project decisions with rationale.
- `REFLECTIONS.md`: short lessons learned from completed work.
- `PITFALLS.md`: recurring traps agents should avoid.
- `FEEDBACK.md`: durable user or reviewer feedback.
- `WORKLOG.md`: compact task history for recent context.

## Update Rules
- Keep `AGENTS.md` as operating guidance, not a project encyclopedia.
- Add memory only when it is likely to help future work.
- Prefer updating an existing memory file over adding a new one.
- Use `scripts/reflect.py` for short lessons.
- Run `scripts/memory_guard.py` after memory changes.
