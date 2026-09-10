from .. import github
from .. import git
from .. import ui


def github_pr(action="list", number="", title="", body="", method="squash"):
    action = (action or "list").strip().lower()
    if action in ("ls", "show"):
        action = "list"
    if action == "list":
        ok, out = github.pr_list()
        return out
    if action == "view":
        if not str(number or "").strip():
            return "Tool error: PR number is required for view. Use e.g. view 12."
        ok, out = github.pr_view(number)
        return out
    if action == "diff":
        if not str(number or "").strip():
            return "Tool error: PR number is required for diff. Use e.g. diff 12."
        ok, out = github.pr_diff(number)
        return out
    if action == "checks":
        ok, out = github.pr_checks(number or None)
        return out
    if action == "comment":
        if not str(number or "").strip() or not str(body or "").strip():
            return "Tool error: number and body are required for comment."
        preview = str(body).strip()[:300]
        if not ui.confirm(f"Comment on PR #{str(number).lstrip('#')} with: {preview!r}?"):
            return "PR cancelled by user"
        ok, out = github.pr_comment(number, body)
        return out
    if action == "create":
        ok, status_out, _ = git.status_porcelain()
        if not ok:
            return status_out
        if status_out.strip() not in ("(clean)", "") and "##" not in status_out:
            pass
        ok_d, diff = git.diff_text(False, ".")
        if not ok_d:
            return diff
        title = (title or "").strip()
        body = body or ""
        if not title or title.lower() in ("suggest", "auto"):
            ok_s, status_body, _ = git.status_porcelain()
            draft_title, draft_body = github.suggest_pr_draft(diff, status_body)
            fallback = True
            try:
                ui.show_loader("Drafting PR title…")
                from ..git_suggest import suggest_message

                suggestion, fallback = suggest_message(diff, status_body)
                if suggestion:
                    draft_title = suggestion.replace("chore:", "feat:", 1)[:100]
            except Exception:
                fallback = True
            finally:
                try:
                    ui.end_turn()
                except Exception:
                    pass
            ui.show_pr_suggest(draft_title, draft_body, fallback)
            picked = ui.prompt_suggest_action()
            if picked == "n":
                return "PR cancelled by user"
            if picked == "e":
                edited = ui.prompt_suggest_edit(draft_title)
                if edited is None or not edited.strip():
                    return "PR cancelled by user"
                title = edited.strip()[:200]
            else:
                title = draft_title
            if not body.strip():
                body = draft_body
        branch = git.branch_current()
        if not ui.confirm(f"Open PR from '{branch or 'current branch'}' with title: {title!r}?"):
            return "PR cancelled by user"
        ok, out = github.pr_create(title, body)
        return out
    if action == "merge":
        label = f"#{str(number).lstrip('#')}" if str(number or "").strip() else "current branch PR"
        if not ui.confirm(f"Squash-merge {label} ({method or 'squash'})?"):
            return "PR cancelled by user"
        ok, out = github.pr_merge(number or None, method or "squash")
        return out
    if action == "close":
        if not str(number or "").strip():
            return "Tool error: PR number is required for close. Use e.g. close 12."
        if not ui.confirm(f"Close PR #{str(number).lstrip('#')} without merging?"):
            return "PR cancelled by user"
        ok, out = github.pr_close(number)
        return out
    return "Tool error: unknown PR action. Use list, view, diff, checks, comment, create, merge, close."
