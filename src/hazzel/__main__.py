import sys

from hazzel import agent
from hazzel import safety
from hazzel import session
from hazzel import ui
from hazzel import config
from hazzel import usage_store
from hazzel import wincompat
console = ui.console

messages = [{"role": "system", "content": agent.build_system_prompt(config.PROJECT_ROOT)}]

_last_summary = None
_last_trace = []
_last_response = None
_last_user_input = None
_pending_prefill = ""

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
            return "1.4.3"


VERSION = _version()


def main(argv=None):
    global _last_summary, _last_trace, _last_response, _last_user_input, _pending_prefill
    from hazzel import print_mode as _print_mode

    parser = _print_mode.build_parser()
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    if args.version:
        console.print(f"Hazzel {VERSION}")
        return
    if args.prompt is not None:
        piped = _print_mode.read_piped_stdin()
        final = _print_mode.combine_prompt(args.prompt, piped)
        if not (final or "").strip():
            parser.error("no prompt: pass TEXT to -p/--print or pipe stdin (e.g. `git diff | hazzel -p`).")
        raise SystemExit(_print_mode.run_print(final, approve=args.approve, output_format=args.output_format))
    wincompat.enable_ansi()
    ui.show_welcome(config.get_current_display_name(), config.PROJECT_ROOT)
    if not config.has_any_key():
        console.print("  No API key yet — run /model to add one (takes ~10s).", style="dim")
        console.print()
    def _persist():
        try:
            session.save(messages, _last_summary, _last_trace, _last_user_input, _last_response)
        except Exception:
            pass
    def _apply_restored(restored):
        global _last_summary, _last_trace, _last_response, _last_user_input
        messages.extend(restored["messages"])
        _last_summary = restored["summary"] or None
        _last_trace = restored["trace"] or []
        _last_response = restored["response"] or None
        _last_user_input = restored["user_input"] or None
        return len(restored["messages"])
    while True:
        try:
            prefill, _pending_prefill = _pending_prefill, ""
            user_input = ui.get_input(messages, prefill=prefill)
        except KeyboardInterrupt:
            continue
        except EOFError:
            _persist()
            break
        except Exception as error:
            ui.show_error(f"Input failed ({error}). Try again.")
            continue
        if user_input.strip().lower() in ["exit", "quit", "/exit", "/q", ":q", ":quit"]:
            _persist()
            break
        if not user_input.strip():
            continue
        if user_input.strip().startswith("!"):
            cmd = user_input.strip()[1:].strip()
            if not cmd:
                ui.show_error("Empty command — try `!ls`.")
                continue
            from hazzel.jobs import split_background_marker as _split_bg
            cmd, _bg = _split_bg(cmd)
            if not cmd:
                ui.show_error("Empty command — try `!ls`.")
                continue
            _last_user_input = user_input
            try:
                if _bg:
                    result = agent.run_tool("run_command", {"command": cmd, "background": True})
                else:
                    result = agent.run_tool("run_command", {"command": cmd})
            except KeyboardInterrupt:
                ui.show_hazzel_message("Cancelled.")
                continue
            except Exception as error:
                ui.show_error(f"Command failed ({error}).")
                continue
            _last_response = result
            _last_trace = []
            _last_summary = None
            ui.show_hazzel_message(result)
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
            ui.show_git_file_list(files, staged, branch)
            sel = ui.prompt_diff_selection(len(files))
            if sel is None or sel == "invalid":
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
            ui.show_git_log(out, _git.branch_current())
            continue
        if low_in.startswith("/review") or low_in == "review":
            staged = "--staged" in low_in or "staged" in low_in.split()
            from hazzel import review as _review
            _last_user_input = user_input
            ui.show_loader("Reviewing diff…")
            try:
                files, markdown, fallback, err = _review.review_working_tree(staged=staged)
            except KeyboardInterrupt:
                ui.hide_loader()
                ui.show_hazzel_message("Cancelled.")
                continue
            ui.hide_loader()
            if err:
                ui.show_error(err)
                continue
            if not files:
                message = (
                    "Nothing staged — `git add` first, or drop --staged."
                    if staged
                    else "Nothing to review — working tree is clean."
                )
                console.print(f"  {message}", style="dim")
                console.print()
                continue
            _last_response = markdown
            ui.show_review(markdown, files, staged=staged, fallback=fallback)
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
        parts_think = user_input.strip().lower().split()
        if parts_think and parts_think[0] == "/think":
            arg = parts_think[1] if len(parts_think) > 1 else ""
            if arg in ("on", "enable", "true", "1"):
                config.set_think_enabled(True)
            elif arg in ("off", "disable", "false", "0"):
                config.set_think_enabled(False)
            elif arg in ("toggle", ""):
                config.set_think_enabled(not config.is_think_enabled())
            elif arg in ("status", "show"):
                pass
            else:
                ui.show_error("Usage: /think on|off|toggle")
                console.print()
                continue
            state = "on" if config.is_think_enabled() else "off"
            console.print(f"  Think mode: {state} — model reasons step-by-step before answering; costs more tokens.", style="dim")
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
                ui.set_quiet(True)
                try:
                    result = agent.run(messages, task)
                except KeyboardInterrupt:
                    ui.set_quiet(False)
                    ui.end_turn()
                    ui.show_hazzel_message("Cancelled.")
                    continue
                except Exception as error:
                    ui.set_quiet(False)
                    ui.end_turn()
                    ui.show_error(f"Turn failed ({error}). Nothing was changed; try again.")
                    continue
                ui.set_quiet(False)
                if isinstance(result, tuple) and len(result) == 3:
                    response, trace, summary = result
                    _last_trace = trace
                    _last_summary = summary
                else:
                    response = result
                    _last_trace = []
                    _last_summary = None
                _last_response = response
                ui.show_reasoning(agent.get_last_reasoning())
                ui.show_hazzel_message(response)
                _persist()
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
        if low_in in ["/usage", "/u", "usage", "u"] or low_in.startswith("/usage ") or low_in.startswith("usage "):
            raw = user_input.strip()
            if raw.startswith("/"):
                cmd, _, arg = raw[1:].partition(" ")
            else:
                cmd, _, arg = raw.partition(" ")
            arg = (arg or "").strip().lower()
            if not arg:
                ui.show_usage(agent.get_session_usage(), agent.get_last_turn_usage(), agent.context_usage(messages))
            elif arg in ("today", "week", "month"):
                ui.show_usage_range(arg, usage_store.range_totals(arg))
            elif arg in ("--by-model", "by-model", "models"):
                ui.show_by_model(usage_store.by_model(usage_store.query()))
            elif arg.startswith("export"):
                parts = arg.split()
                fmt = parts[1] if len(parts) > 1 else "json"
                if fmt not in ("csv", "json"):
                    ui.show_error("Usage: /usage export [csv|json] [file]")
                else:
                    from datetime import datetime
                    name = parts[2] if len(parts) > 2 else datetime.now().strftime(f"hazzel-usage-%Y%m%d.{fmt}")
                    try:
                        dest = config.resolve_project_path(name)
                    except ValueError as error:
                        ui.show_error(str(error))
                        continue
                    if fmt == "csv":
                        ok, err = usage_store.export_csv(dest)
                    else:
                        ok, err = usage_store.export_json(dest)
                    if ok:
                        ui.show_export(str(dest))
                    else:
                        ui.show_error(f"Export failed ({err}).")
            elif arg in ("clear", "wipe"):
                count = usage_store.clear()
                console.print(f"  Cleared {count} logged requests.", style="dim")
                console.print()
            else:
                ui.show_error("Usage: /usage [today|week|month|--by-model|export|clear]")
            continue
        if low_in in ["/budget", "budget"] or low_in.startswith("/budget ") or low_in.startswith("budget "):
            raw = user_input.strip()
            arg = (raw[7:].strip() if raw.startswith("/") else raw[6:].strip())
            parts = arg.split()
            if not parts:
                budget = config.get_budget()
                try:
                    daily = usage_store.range_totals("today")["cost"]
                except Exception:
                    daily = 0.0
                sess = agent.get_session_usage().get("cost") or 0.0
                console.print()
                console.print(f"  session budget: {budget['session_usd'] or 'off'} · spent ${sess:,.2f}", style="dim")
                console.print(f"  daily budget: {budget['daily_usd'] or 'off'} · spent ${daily:,.2f}", style="dim")
                console.print(f"  warn at: {budget['warn_at_pct']:.0f}% — warnings only, never blocks", style="dim")
                console.print()
            elif parts[0] in ("off", "clear"):
                config.clear_budget()
                console.print("  Budgets cleared.", style="dim")
                console.print()
            elif len(parts) == 2 and parts[0] in ("session", "daily", "warn"):
                try:
                    value = float(parts[1])
                except ValueError:
                    ui.show_error("Usage: /budget [session|daily] <usd> | /budget warn <pct> | /budget off")
                    continue
                if parts[0] == "session":
                    config.set_budget(session_usd=value)
                elif parts[0] == "daily":
                    config.set_budget(daily_usd=value)
                else:
                    config.set_budget(warn_at_pct=value)
                console.print("  Budget updated — warnings only, Hazzel never stops itself.", style="dim")
                console.print()
            else:
                ui.show_error("Usage: /budget [session|daily] <usd> | /budget warn <pct> | /budget off")
            continue
        if low_in == "retry" or low_in.startswith("/retry"):
            if not (_last_user_input or "").strip():
                ui.show_error("No previous message — ask something first.")
                continue
            ui.set_quiet(True)
            try:
                result = agent.run(messages, _last_user_input)
            except KeyboardInterrupt:
                ui.set_quiet(False)
                ui.end_turn()
                ui.show_hazzel_message("Cancelled.")
                continue
            except Exception as error:
                ui.set_quiet(False)
                ui.end_turn()
                ui.show_error(f"Turn failed ({error}). Nothing was changed; try again.")
                continue
            ui.set_quiet(False)
            if isinstance(result, tuple) and len(result) == 3:
                response, trace, summary = result
                _last_trace = trace
                _last_summary = summary
            else:
                response = result
                _last_trace = []
                _last_summary = None
            _last_response = response
            ui.show_reasoning(agent.get_last_reasoning())
            ui.show_hazzel_message(response)
            _persist()
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
        if low_in == "skills" or low_in == "/skills" or low_in.startswith("/skills ") or low_in.startswith("skills "):
            raw = user_input.strip()
            arg = (raw[7:].strip() if raw.startswith("/") else raw[6:].strip()).strip("\"'")
            from hazzel import skills as _skills
            if not arg or arg.lower() in ("list", "ls"):
                picked = ui.select_skill(_skills.discover_skills())
                if picked is not None:
                    _pending_prefill = "@" + picked.get("name", "") + " "
            else:
                name = arg.split()[0]
                _last_response = agent.run_tool("skill", {"name": name})
                ui.show_skill_detail(name, _last_response)
            continue
        if low_in == "mcp" or low_in == "/mcp" or low_in.startswith("/mcp ") or low_in.startswith("mcp "):
            raw = user_input.strip()
            arg = (raw[4:].strip() if raw.startswith("/") else raw[3:].strip()).strip("\"'")
            if not arg or arg.lower() in ("list", "ls", "servers"):
                _last_response = agent.run_tool("mcp", {"action": "list"})
            else:
                parts = arg.split()
                server = parts[0]
                tool = parts[1] if len(parts) > 1 else ""
                if not tool:
                    _last_response = agent.run_tool("mcp", {"action": "list", "server": server})
                else:
                    _last_response = agent.run_tool("mcp", {"action": "call", "server": server, "tool": tool, "arguments": {}})
            ui.show_hazzel_message(_last_response)
            continue
        if low_in == "jobs" or low_in == "/jobs" or low_in.startswith("/jobs ") or low_in.startswith("jobs "):
            raw = user_input.strip()
            arg = (raw[5:].strip() if raw.startswith("/") else raw[4:].strip()).strip("\"'")
            if not arg or arg.lower() in ("list", "ls"):
                _last_response = agent.run_tool("jobs", {"action": "list"})
            else:
                parts = arg.split()
                if parts[0].lower() in ("clear", "clean"):
                    _last_response = agent.run_tool("jobs", {"action": "clear"})
                elif parts[0].lower() in ("wait", "watch") and len(parts) > 1:
                    timeout = 30
                    if len(parts) > 2:
                        try:
                            timeout = float(parts[2])
                        except ValueError:
                            timeout = 30
                    _last_response = agent.run_tool("jobs", {"action": "wait", "job_id": parts[1], "timeout": timeout})
                elif parts[0].lower() in ("kill", "stop", "cancel") and len(parts) > 1:
                    _last_response = agent.run_tool("jobs", {"action": "kill", "job_id": parts[1]})
                elif parts[0].lower() in ("poll", "log", "tail", "show") and len(parts) > 1:
                    _last_response = agent.run_tool("jobs", {"action": "poll", "job_id": parts[1]})
                else:
                    _last_response = agent.run_tool("jobs", {"action": "poll", "job_id": parts[0]})
            ui.show_hazzel_message(_last_response)
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
            messages.append({"role": "system", "content": agent.build_system_prompt(config.PROJECT_ROOT)})
            agent.reset_conversation_state()
            session.backup()
            session.clear()
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
        if low_in == "session" or low_in.startswith("/session"):
            raw = user_input.strip()
            arg = (raw[8:].strip() if raw.startswith("/") else raw[7:].strip()).lower()
            if arg in ("restore", "reload", "back"):
                try:
                    previous = session.load_backup()
                except Exception:
                    previous = None
                from_backup = previous is not None
                if not previous:
                    try:
                        previous = session.load()
                    except Exception:
                        previous = None
                if not previous:
                    ui.show_error("No saved session — nothing to restore.")
                    continue
                messages.clear()
                messages.append({"role": "system", "content": agent.build_system_prompt(config.PROJECT_ROOT)})
                agent.reset_conversation_state()
                count = _apply_restored(previous)
                if from_backup:
                    session.clear_backup()
                _persist()
                try:
                    sys.stdout.write("\x1b[2J\x1b[3J\x1b[H")
                    sys.stdout.flush()
                except OSError:
                    pass
                ui.show_welcome(config.get_current_display_name(), config.PROJECT_ROOT)
                try:
                    ui.show_history(messages)
                except Exception:
                    pass
                continue
            console.print("  Usage: /session restore — reload the last saved session.", style="dim")
            console.print()
            continue
        _last_user_input = user_input
        ui.set_quiet(True)
        try:
            result = agent.run(messages, user_input)
        except KeyboardInterrupt:
            ui.set_quiet(False)
            ui.end_turn()
            ui.show_hazzel_message("Cancelled.")
            continue
        except Exception as error:
            ui.set_quiet(False)
            ui.end_turn()
            ui.show_error(f"Turn failed ({error}). Nothing was changed; try again.")
            continue
        ui.set_quiet(False)
        if isinstance(result, tuple) and len(result) == 3:
            response, trace, summary = result
            _last_trace = trace
            _last_summary = summary
        else:
            response = result
            _last_trace = []
            _last_summary = None
        _last_response = response
        ui.show_reasoning(agent.get_last_reasoning())
        ui.show_hazzel_message(response)
        try:
            sess_usage = agent.get_session_usage()
            try:
                daily = usage_store.range_totals("today")["cost"]
            except Exception:
                daily = 0.0
            ui.show_budget_warning(usage_store.budget_warnings(sess_usage.get("cost") or 0.0, daily))
        except Exception:
            pass
        _persist()


if __name__ == "__main__":
    main()
