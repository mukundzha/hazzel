# Copy-paste sessions

These short sessions show representative terminal output. Model wording, commit
suggestions, job IDs, and elapsed times can vary by provider and run.

## 1. Review a staged change

```text
$ git add src/auth.py
$ hazzel
> /review --staged
Staged diff: src/auth.py adds `console.log("token", token)`.
Diff review · 1 file · +1 −0 · staged · offline heuristics
Summary — 1 file(s), +1 −0 (offline heuristics; no model reachable).
Risks — added line contains `console.log(`.
Missing — no test file changed; `CHANGELOG.md` not updated.
Before commit — run the test suite; skim the diff above; then `/commit`.
Read-only — nothing changed. /commit when ready.
```

Why it matters: review the staged diff before recording it; `/review` does not edit files.

## 2. Draft a Conventional Commit

```text
$ hazzel
> /commit
Suggested message · offline draft
❯ chore(auth): update src/auth.py
[y] commit · [e] edit · [n] cancel
Accept? [y/e/n]: e
Message [chore(auth): update src/auth.py]: fix(auth): reject empty token
Diff preview: src/auth.py · +2 −0 (representative)
Accept? [y/N]: y
Committed as <hash> fix(auth): reject empty token
```

The draft, preview, and commit hash vary by diff and run. The `e` choice opens an editable message prompt; approve the diff to create the commit.

Why it matters: get a Conventional Commit draft while choosing the final wording and approving the commit.

## 3. Give a vision model a screenshot

```text
$ hazzel
> @screenshot.png make the nav match this
[Hazzel attaches screenshot.png to this request]
[A vision-capable model examines the screenshot and current project files]
Representative response:
The reference has a centered logo and evenly spaced navigation links.
The current header uses a left-aligned logo and a tighter link gap.
I can update the header styles to match those positions and spacing.
I’ll show the proposed diff before applying any file changes.
> /review
Summary — header styles adjust logo alignment and navigation spacing.
```

Use a vision-capable model and keep `screenshot.png` in the project directory. Generated analysis varies by image and model.

Why it matters: attach visual context directly instead of describing every detail in text.

## 4. Keep a dev server in the background

```text
$ hazzel
> !npm run dev &
Started background job 1: npm run dev
Poll with jobs(action=poll, job_id=1) (or /jobs 1); kill with jobs(action=kill, job_id=1).
> /jobs
Background jobs (1):
- 1 · running 2s · npm run dev
Poll with jobs(action=poll, job_id=…) or /jobs <id>.
> /jobs 1
Job 1 · running 4s · npm run dev
VITE v6.0.0 ready in 240 ms
Local: http://localhost:5173/
Full log: <temporary job log path>
```

The job ID and elapsed time are examples; Hazzel assigns them at runtime.

Why it matters: leave a server running while continuing the conversation, then inspect or stop it by ID.

## 5. Summarize a diff in a pipeline

```text
$ git diff | hazzel -p "summarize this diff"
This diff updates token validation before authentication.
It rejects empty tokens instead of passing them to the verifier.
The change also adds a regression test for an empty token.
No unrelated files appear in the supplied diff.
Suggested next step: run the authentication test suite.
The summary is printed to stdout for a script or shell pipeline.
The command exits after this single response.
No interactive REPL is opened for the pipeline.
$ 
```

`-p` prints one turn and exits. Without `-y`, Hazzel blocks requested writes and commands; this read-only summary needs no approval.

Why it matters: use Hazzel from a shell pipeline or script without entering the interactive REPL.
