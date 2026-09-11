import sys

from hazzel import agent
from hazzel import safety
from hazzel import ui
from hazzel import config
from hazzel import wincompat
from rich.console import Console

console = Console()

messages = [{"role": "system", "content": agent.SYSTEM_PROMPT}]

_last_summary = None
_last_trace = []
_last_response = None
_last_user_input = None


def _show_goal(goal):
    console.print(f"  Goal: {goal['objective']}", style="bold white")
    if (goal.get("criteria") or "").strip():
        console.print(f"  Accept: {goal['criteria']}", style="dim")
    console.print()


def handle_model_command():
    catalog = config.get_catalog()
    current = config.get_current_model()
    selected = ui.select_model(catalog, current)
    if selected is None:
        return
    if selected["provider"] in config.KEYLESS_PROVIDERS:
        config.set_model(selected["provider"], selected["id"], selected["display_name"])
        ui.show_model_selected(selected["display_name"], selected.get("provider_display", selected["provider"]))
        return
    existing = config.get_api_key(selected["provider"])
    if existing and existing.strip():
        config.set_model(selected["provider"], selected["id"], selected["display_name"])
        ui.show_model_selected(selected["display_name"], selected.get("provider_display", selected["provider"]))
        return
    key = ui.prompt_api_key(existing)
    if key is None:
        return
    if not key.strip():
        ui.show_error("API key is required")
        console.print()
        console.print("  Check your API key and try again.", style="dim")
        console.print()
        return
    key = key.strip()
    config.set_api_key(selected["provider"], key)
    config.set_model(selected["provider"], selected["id"], selected["display_name"])
    ui.show_model_selected(selected["display_name"], selected.get("provider_display", selected["provider"]))


def _version():
    try:
        from importlib.metadata import version
        return version("hazzel")
    except Exception:
        try:
            from hazzel import __version__
            return __version__
        except Exception:
            return "1.3.2"


VERSION = _version()


def main(argv=None):
    global _last_summary, _last_trace, _last_response, _last_user_input
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("--version", "-V"):
        console.print(f"Hazzel {VERSION}")
        return
    if args and args[0] in ("--help", "-h"):
        console.print("Hazzel — terminal coding agent. Usage: python -m hazzel [--version|--help]")
        return
    if args:
        ui.show_error(f"Unknown option: {args[0]}. Try --help.")
        return
    wincompat.enable_ansi()
    ui.show_welcome(config.get_current_display_name(), config.PROJECT_ROOT)
    if config.should_show_star_nudge():
        ui.show_star_nudge()
        config.mark_star_nudged()
    if not config.has_any_key():
        console.print("  No API key yet — run /model to add one (takes ~10s).", style="dim")
        console.print()
    while True:
        try:
            user_input = ui.get_input(messages)
        except KeyboardInterrupt:
            continue
        except EOFError:
            break
        except Exception as error:
            ui.show_error(f"Input failed ({error}). Try again.")
            continue
        if user_input.strip().lower() in ["exit", "quit", "/exit", "/q", ":q", ":quit"]:
            break
        if not user_input.strip():
            continue
        if user_input.strip().startswith("/"):
            ui.show_user_command(user_input)
        if user_input.strip() == "/model":
            handle_model_command()
            continue
        low_in = user_input.strip().lower()
        if low_in in ("/status", "status"):
            from hazzel import git as _git
            ok, out, branch = _git.status_porcelain()
            if not ok:
                ui.show_error(out)
                continue
            ui.show_git_status(branch, out)
            continue
        if low_in.startswith("/diff") or low_in == "diff":
            staged = "--staged" in low_in or "staged" in low_in.split()
            from hazzel import git as _git
            ok, files, err = _git.changed_files(staged)
            if not ok:
                ui.show_error(err)
                continue
            branch = _git.branch_current()
            if not files:
                ui.show_git_file_list(files, staged, branch)
                continue
            if not sys.stdin.isatty():
                ui.show_git_file_list(files, staged, branch)
                for i, f in enumerate(files):
                    dok, body = _git.diff_file(f["key"], staged)
                    ui.show_git_file_diff(f["path"], body if dok else f"Diff failed: {body}", staged, f"{i + 1}/{len(files)} ")
                continue
            while True:
                ui.show_git_file_list(files, staged, branch)
                sel = ui.prompt_diff_selection(len(files))
                if sel is None:
                    break
                if sel == "invalid":
                    continue
                f = files[sel]
                dok, body = _git.diff_file(f["key"], staged)
                ui.show_git_file_diff(f["path"], body if dok else f"Diff failed: {body}", staged, f"{sel + 1}/{len(files)} ")
            continue
        if low_in.startswith("/commit"):
            msg = user_input.strip()[len("/commit"):].strip().strip("\"'")
            from hazzel.tools.git_commit import git_commit as _gc
            ui.show_git_commit(_gc(msg or None))
            continue
        if low_in.startswith("/branch") or low_in == "branch":
            parts_b = user_input.strip().split()
            from hazzel.tools.git_branch import git_branch as _gb
            from hazzel import git as _git
            if len(parts_b) == 1:
                ok, out, cur = _git.branch_list()
                if not ok:
                    ui.show_error(out)
                    continue
                ui.show_git_branches(cur, out)
            elif len(parts_b) >= 3 and parts_b[1].lower() in ("create", "new", "switch", "checkout"):
                ui.show_git_commit(_gb(parts_b[1].lower() == "create" and "create" or "switch", " ".join(parts_b[2:])))
            else:
                ok, out, cur = _git.branch_list()
                if not ok:
                    ui.show_error(out)
                    continue
                ui.show_git_branches(cur, out)
            continue
        if low_in.startswith("/log") or low_in == "log":
            parts_l = user_input.strip().split()
            n = 10
            if len(parts_l) > 1:
                try:
                    n = max(1, min(20, int(parts_l[1])))
                except ValueError:
                    n = 10
            from hazzel import git as _git
            ok, out = _git.log_entries(n)
            if not ok:
                ui.show_error(out)
                continue
            ui.show_git_log(out)
            continue
        if low_in == "review" or low_in.startswith("/review"):
            raw = user_input.strip()
            rest = (raw[7:].strip() if raw.startswith("/") else raw[6:].strip())
            from hazzel.git_review import parse_review_args as _parse_review_args
            staged, path, codebase = _parse_review_args(rest)
            result = agent.run_tool("review_diff", {"staged": staged, "path": path, "codebase": codebase})
            _last_response = result
            if codebase:
                scope = "whole codebase"
            elif path != ".":
                scope = path
            else:
                scope = "staged" if staged else "unstaged"
            ui.show_review(result, scope)
            continue
        if low_in in ("/push", "push"):
            from hazzel.tools.git_branch import git_branch as _gb
            ui.show_git_commit(_gb("push"))
            continue
        if low_in in ("/pull", "pull"):
            from hazzel.tools.git_branch import git_branch as _gb
            ui.show_git_commit(_gb("pull"))
            continue
        if low_in in ("/sync", "sync"):
            from hazzel.tools.git_branch import git_branch as _gb
            ui.show_git_commit(_gb("sync"))
            continue
        if low_in == "/pr" or low_in.startswith("/pr ") or low_in == "pr":
            from hazzel.tools.github_pr import github_pr as _pr
            raw = user_input.strip()
            rest = (raw[3:].strip() if raw.startswith("/") else raw[2:].strip())
            parts = rest.split()
            if not parts:
                ui.show_pr_list(_pr("list"))
                continue
            sub = parts[0].lower()
            if sub in ("list", "ls"):
                ui.show_pr_list(_pr("list"))
            elif sub in ("view", "show"):
                ui.show_pr_view(_pr("view", parts[1] if len(parts) > 1 else ""))
            elif sub == "diff":
                ui.show_pr_view(_pr("diff", parts[1] if len(parts) > 1 else ""))
            elif sub in ("checks", "check", "ci"):
                ui.show_pr_checks(_pr("checks", parts[1] if len(parts) > 1 else ""))
            elif sub == "create":
                title = rest[len(parts[0]):].strip().strip("\"'")
                ui.show_pr_result(_pr("create", title=title))
            elif sub == "merge":
                num = parts[1] if len(parts) > 1 and parts[1].lstrip("#").isdigit() else ""
                ui.show_pr_result(_pr("merge", number=num))
            elif sub == "close":
                ui.show_pr_result(_pr("close", number=parts[1] if len(parts) > 1 else ""))
            elif sub == "comment":
                num = parts[1] if len(parts) > 1 else ""
                cbody = rest.split(num, 1)[1].strip().strip("\"'") if num else ""
                ui.show_pr_result(_pr("comment", number=num, body=cbody))
            elif parts[0].lstrip("#").isdigit():
                ui.show_pr_view(_pr("view", parts[0]))
            else:
                ui.show_pr_result(_pr("create", title=rest.strip().strip("\"'")))
            continue
        parts_prove = user_input.strip().lower().split()
        if parts_prove and parts_prove[0] == "/prove":
            arg = parts_prove[1] if len(parts_prove) > 1 else ""
            if arg in ("on", "enable", "true", "1"):
                config.set_prove_enabled(True)
            elif arg in ("off", "disable", "false", "0"):
                config.set_prove_enabled(False)
            elif arg in ("status", "show", ""):
                pass
            else:
                ui.show_error("Usage: /prove on|off")
                console.print()
                continue
            state = "on" if config.is_prove_enabled() else "off"
            console.print(f"  Prove mode: {state} — ephemeral smoke check in /tmp after edits.", style="dim")
            console.print()
            continue
        parts_plan = user_input.strip().lower().split()
        if parts_plan and parts_plan[0] == "/plan":
            arg = parts_plan[1] if len(parts_plan) > 1 else ""
            if arg in ("on", "enable", "true", "1"):
                config.set_plan_enabled(True)
            elif arg in ("off", "disable", "false", "0"):
                config.set_plan_enabled(False)
            elif arg in ("status", "show", ""):
                pass
            else:
                ui.show_error("Usage: /plan on|off")
                console.print()
                continue
            state = "on" if config.is_plan_enabled() else "off"
            console.print(f"  Plan mode: {state} — read-only exploration; Hazzel proposes, you approve with /plan off.", style="dim")
            console.print()
            continue
        if low_in == "goal" or low_in.startswith("/goal"):
            raw = user_input.strip()
            rest = (raw[5:].strip() if raw.startswith("/") else raw[4:].strip())
            head, _, arg = rest.partition(" ")
            head = head.lower()
            arg = arg.strip().strip("\"'")
            if head in ("done", "clear", "reset", "off", "unset"):
                config.clear_goal()
                console.print("  Goal cleared.", style="dim")
                console.print()
                continue
            if head in ("run", "go", "start"):
                task = agent.goal_run_task()
                if not task:
                    ui.show_error("No goal set — /goal <objective> first.")
                    continue
                _last_user_input = task
                try:
                    result = agent.run(messages, task)
                except KeyboardInterrupt:
                    ui.end_turn()
                    ui.show_hazzel_message("Cancelled.")
                    continue
                except Exception as error:
                    ui.end_turn()
                    ui.show_error(f"Turn failed ({error}). Nothing was committed; try again.")
                    continue
                if isinstance(result, tuple) and len(result) == 3:
                    response, trace, summary = result
                    _last_trace = trace
                    _last_summary = summary
                else:
                    response = result
                    _last_trace = []
                    _last_summary = None
                _last_response = response
                ui.show_hazzel_message(response)
                ui.show_reasoning(agent.get_last_reasoning())
                continue
            if head in ("accept", "criteria", "ok"):
                current = config.get_goal() or {}
                if not (current.get("objective") or "").strip():
                    ui.show_error("No goal set — /goal <objective> first.")
                    continue
                config.set_goal(current["objective"], arg)
                _show_goal(config.get_goal())
                continue
            if not rest:
                current = config.get_goal()
                if current:
                    _show_goal(current)
                else:
                    console.print("  No goal set — /goal <objective> to pin one.", style="dim")
                    console.print()
                continue
            objective, _, inline = rest.partition("|")
            objective = objective.strip().strip("\"'")
            inline = inline.strip().strip("\"'")
            if not objective:
                ui.show_error("Usage: /goal <objective> [| <acceptance>].")
                continue
            if inline:
                config.set_goal(objective, inline)
            else:
                config.set_goal(objective)
                criteria = ui.prompt_goal_criteria()
                if criteria:
                    config.set_goal(objective, criteria)
            _show_goal(config.get_goal())
            console.print("  ✓ Goal live — I'll steer here and flag when it looks done.", style="dim")
            console.print()
            continue
        if user_input.strip().lower() in ["/help", "/h", "help"]:
            ui.show_help()
            continue
        if user_input.strip().lower() in ["/docs", "/doc", "/guide", "docs"]:
            ui.show_docs()
            continue
        if user_input.strip().lower() in ["/logout", "/signout", "logout"]:
            config.clear_api_keys()
            _last_summary = None
            _last_trace = []
            _last_response = None
            _last_user_input = None
            ui.show_logout()
            continue
        if user_input.strip().lower() in ["/summary", "/s", "summary"]:
            ui.show_summary(_last_summary, _last_trace)
            continue
        if low_in == "export" or low_in.startswith("/export"):
            raw = user_input.strip()
            arg = raw[7:].strip() if raw.startswith("/") else raw[6:].strip()
            from hazzel.export import export_transcript as _export
            ok, out = _export(
                messages, _last_summary, _last_trace, agent.get_session_usage(),
                config.get_current_display_name(), arg or None,
            )
            if ok:
                ui.show_export(out)
            else:
                ui.show_error(out)
            continue
        if user_input.strip().lower() in ["/usage", "/u", "usage"]:
            ui.show_usage(agent.get_session_usage(), agent.get_last_turn_usage())
            continue
        if low_in == "retry" or low_in.startswith("/retry"):
            if not (_last_user_input or "").strip():
                ui.show_error("No previous message — ask something first.")
                continue
            try:
                result = agent.run(messages, _last_user_input)
            except KeyboardInterrupt:
                ui.end_turn()
                ui.show_hazzel_message("Cancelled.")
                continue
            except Exception as error:
                ui.end_turn()
                ui.show_error(f"Turn failed ({error}). Nothing was committed; try again.")
                continue
            if isinstance(result, tuple) and len(result) == 3:
                response, trace, summary = result
                _last_trace = trace
                _last_summary = summary
            else:
                response = result
                _last_trace = []
                _last_summary = None
            _last_response = response
            ui.show_hazzel_message(response)
            ui.show_reasoning(agent.get_last_reasoning())
            continue
        if low_in == "init" or low_in.startswith("/init"):
            raw = user_input.strip()
            arg = (raw[5:].strip() if raw.startswith("/") else raw[4:].strip()).strip("\"'") or "AGENTS.md"
            from hazzel.init_map import build_map
            content = build_map(config.PROJECT_ROOT)
            result = agent.run_tool("write_file", {"path": arg, "content": content})
            _last_response = result
            ui.show_hazzel_message(result)
            continue
        if low_in == "copy" or low_in.startswith("/copy"):
            raw = user_input.strip()
            arg = (raw[5:].strip() if raw.startswith("/") else raw[4:].strip()).lower()
            from hazzel.clipboard import copy_text, extract_last_code_block
            text = _last_response or ""
            if arg in ("code", "block"):
                code = extract_last_code_block(text)
                if not code:
                    ui.show_error("No code block in the last reply — copying everything instead.")
                else:
                    text = code
            ok, out = copy_text(text)
            if ok:
                ui.show_copied(out)
            else:
                ui.show_error(out)
            continue
        parts = user_input.strip().lower().split()
        if parts and parts[0] in ["/undo", "undo"]:
            count = 1
            if len(parts) > 1:
                try:
                    count = max(1, int(parts[1]))
                except ValueError:
                    count = 1
            ui.show_undo(safety.undo(count))
            continue
        if user_input.strip().lower() in ["/clear", "/c", "clear"]:
            messages.clear()
            messages.append({"role": "system", "content": agent.SYSTEM_PROMPT})
            agent.reset_conversation_state()
            _last_summary = None
            _last_trace = []
            _last_response = None
            _last_user_input = None
            try:
                sys.stdout.write("\x1b[2J\x1b[3J\x1b[H")
                sys.stdout.flush()
            except OSError:
                pass
            ui.show_welcome(config.get_current_display_name(), config.PROJECT_ROOT)
            continue
        _last_user_input = user_input
        try:
            result = agent.run(messages, user_input)
        except KeyboardInterrupt:
            ui.end_turn()
            ui.show_hazzel_message("Cancelled.")
            continue
        except Exception as error:
            ui.end_turn()
            ui.show_error(f"Turn failed ({error}). Nothing was committed; try again.")
            continue
        if isinstance(result, tuple) and len(result) == 3:
            response, trace, summary = result
            _last_trace = trace
            _last_summary = summary
        else:
            response = result
            _last_trace = []
            _last_summary = None
        _last_response = response
        ui.show_hazzel_message(response)
        ui.show_reasoning(agent.get_last_reasoning())


if __name__ == "__main__":
    main()
