# CLAUDE.md

Claude Code reads this file automatically. Our project rules live in **GEMINI.md** so that Gemini and Claude share one source of truth; it is imported below, together with the team plan, the beginner playbook and the progress log it imports.

@GEMINI.md

## Claude-specific notes

- On this team, Claude Code is the specialist: hard problems Gemini got stuck on (read `HANDOFF.md` first if it exists), step-by-step plans for cards 7, 8 and 10 (write them to `PLAN.md`, one small prompt per step, each with a way to check it), and reviews of anything that produces a number for judges (write findings to `REVIEW.md`, most serious first, without rewriting the code unless asked).
- Every rule in GEMINI.md applies: never train on real images, never commit data or keys, one job per script in `scripts/`, and explain everything in plain English with the exact command and expected output.
- When you change project rules or the plan, edit GEMINI.md (and the matching file in `docs/`), never only this file.
