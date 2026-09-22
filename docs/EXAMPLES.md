# Examples

Five short sessions that show what diff-first feels like. Each block is the command you type, what Hazzel typically prints, and why it matters. Commands match the table in the [README](../README.md#commands-at-a-glance).

Start from a project root after `pip install hazzel` and `hazzel`.

## 1. `/review --staged` catches a risky change

```text
❯ /review --staged

  ● /review --staged
    3 files · +84 / −12

  Summary
  Staged changes drop the CSRF check on POST /login and widen a SQL query.

  Risks
  - auth/views.py: csrf_exempt on the login view
  - db.py: string-interpolated WHERE clause

  Missing
  - tests for the new query path

  Before commit
  Restore the CSRF decorator or document why it is gone.
```

Why it matters: `/review` is read-only git. It never writes files or runs shell. You see the risk before `/commit`.

## 2. `/commit` auto-drafts a Conventional message

```text
❯ /commit

  staged:
    M  src/hazzel/safety.py
    M  tests/test_safety.py

  proposed message:
    fix(safety): reject git reset --hard outside the project root

  Apply this commit? [y/N]
```

Why it matters: `/commit` drafts a Conventional Commit from the staged diff and still stops for approval. Raw `git commit` is steered here so the preview is not skipped.

## 3. `@screenshot.png` make the nav match this

Needs a vision-capable model (`/model`). Attach the image with `@`.

```text
❯ @docs/nav-mock.png make the nav match this

  ● read_file   docs/nav-mock.png   (image)
  ● read_file   src/components/Nav.tsx

  edit_file  src/components/Nav.tsx
  @@ -12,7 +12,11 @@
  -      <nav className="flex gap-2">
  +      <nav className="flex items-center justify-between px-4">

  Apply this edit? [y/N]
```

Why it matters: `@path` pins the file into context. Writes still stop at a diff. Without a vision model the image is ignored and `/model` is the switch.

## 4. Background job: `!npm run dev &` plus `/jobs`

```text
❯ !npm run dev &

  job 3 started   log /tmp/hazzel-job-3.log
  Local:   http://127.0.0.1:5173/

❯ /jobs

  3  running  npm run dev   12s

❯ /jobs 3

  [12:04:01] VITE v5 ready in 184 ms
```

Block instead of polling with `jobs(action=wait, job_id=3)` (or `/jobs wait 3`
— optional timeout in seconds), and drop finished jobs with `/jobs clear`.

Why it matters: `!cmd &` detaches long-running processes. `/jobs` lists, tails, or kills them. Jobs are cleaned up when Hazzel exits.

## 5. `hazzel -p` for pipes and CI

```bash
git diff HEAD~1 | hazzel -p "summarize this diff" --output-format json
```

```text
{
  "ok": true,
  "text": "Adds /review --staged. No write-path changes.",
  "exit_code": 0
}
```

Why it matters: `-p` is one turn and exit. JSON plus real exit codes fit scripts. The agent does not stay in a REPL.
