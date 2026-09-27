import json

from hazzel import config
from hazzel import ui
from hazzel import skills as _skills
from hazzel import mcp as _mcp
from hazzel.mentions import (
    build_user_content,
    collect_mention_images,
    expand_mentions,
    parse_mentions,
    strip_mentions,
)
from hazzel.providers import get_provider
from hazzel.tools.approvals import reset_approvals as _reset_turn_approvals

from .dispatch import (
    _active_tools,
    _coerce_tool_args,
    _extract_bad_tool,
    _finalize_result,
    _format_contact_error,
    _is_parallel_safe,
    _is_tool_validation_error,
    _normalize_tool_name,
    _run_one_tool,
    _tool_cache_key,
    _tool_detail,
    is_print_readonly,
)
from .fastpath import _fast_reply, _plan_defers, try_fast_path
from .history import (
    _build_summary,
    _commit_history,
    _enforce_turn_budget,
    _session_goal_note,
)
from .state import (
    _last_turn_usage,
    _note_reasoning,
    _note_target,
    _record_usage,
    _turn_reasoning,
    _update_last_target,
)
from .toolspec import (
    MAX_ITERATIONS,
    PARALLEL_MAX_WORKERS,
    PARALLEL_TOOL_TIMEOUT,
    PLAN_ADDENDUM,
    PRINT_ADDENDUM,
    TOOL_NAMES,
)


def _safe_chat(provider, task_messages, tools, retries=1, think=False):
    try:
        response = provider.chat(task_messages, tools, think=think)
    except Exception as error:
        if retries <= 0 or not _is_tool_validation_error(error):
            raise
        bad = _extract_bad_tool(str(error))
        valid = ", ".join(sorted(TOOL_NAMES))
        task_messages.append({
            "role": "user",
            "content": f"System correction: '{bad or 'that tool'}' does not exist. Valid tools are exactly: {valid}. Retry using only those (list trees with list_files), or answer directly with no tool call.",
        })
        try:
            response = provider.chat(task_messages, tools)
        except Exception as retry_error:
            if not _is_tool_validation_error(retry_error):
                raise
            task_messages.append({
                "role": "user",
                "content": f"Final correction: answer directly with NO tool calls. Plain text only, valid tools were: {valid}.",
            })
            response = provider.chat(task_messages, [], think=think)
        try:
            _record_usage(response, task_messages)
        except Exception:
            pass
        return response
    for tc in getattr(response, "tool_calls", None) or []:
        fixed = _normalize_tool_name(tc.name)
        if fixed is not None and fixed != tc.name:
            tc.name = fixed
            try:
                parsed = json.loads(tc.arguments) if tc.arguments else {}
            except (json.JSONDecodeError, TypeError, ValueError):
                parsed = {}
            tc.arguments = json.dumps(_coerce_tool_args(fixed, parsed))
    return response


def _normalize_response_tools(response):
    for tc in getattr(response, "tool_calls", None) or []:
        fixed = _normalize_tool_name(tc.name)
        if fixed is not None and fixed != tc.name:
            tc.name = fixed
            try:
                parsed = json.loads(tc.arguments) if tc.arguments else {}
            except (json.JSONDecodeError, TypeError, ValueError):
                parsed = {}
            tc.arguments = json.dumps(_coerce_tool_args(fixed, parsed))
    return response


# Errors that dropping `stream=True` can never fix. Retrying them without
# streaming just burns a second full request (and doubles the latency of an
# already-failing call), so they go straight back to the caller.
_HOPELESS_ERROR_MARKERS = (
    "401",
    "403",
    "invalid_api_key",
    "incorrect api key",
    "unauthorized",
    "authentication",
    "permission denied",
    "forbidden",
    "model_not_found",
    "does not exist or you do not have access",
    "404",
)


def _is_hopeless_stream_error(error):
    text = str(error).lower()
    if not any(marker in text for marker in _HOPELESS_ERROR_MARKERS):
        return False
    # A 4xx that explicitly blames streaming is still fixable by dropping it.
    return not any(marker in text for marker in ("stream", "sse", "event_source"))


def _safe_stream_chat(provider, task_messages, tools, think=False):
    try:
        ui.begin_stream()
        try:
            response = provider.stream(
                task_messages,
                tools,
                on_token=ui.push_stream_token,
                think=think,
                on_reason=ui.push_reasoning_token,
            )
        finally:
            try:
                ui.end_stream()
            except Exception:
                pass
    except KeyboardInterrupt:
        raise
    except Exception as error:
        if _is_hopeless_stream_error(error):
            raise
        return _safe_chat(provider, task_messages, tools, think=think)
    _normalize_response_tools(response)
    if ui.was_thinking_streamed():
        _note_reasoning(None)
    else:
        _note_reasoning(getattr(response, "reasoning", None))
    if getattr(response, "tool_calls", None):
        try:
            ui.show_loader("Working…")
        except Exception:
            pass
    return response


def run(messages, user_input):
    # `messages` holds the system prompt plus compact history from previous turns.
    # Tool traffic for this turn is added to a working copy and never persisted.
    task_messages = messages + [{"role": "user", "content": user_input}]
    if _plan_defers() and task_messages and task_messages[0].get("role") == "system":
        task_messages[0] = {"role": "system", "content": (task_messages[0].get("content") or "") + PLAN_ADDENDUM}
    try:
        readonly_print = is_print_readonly()
    except Exception:
        readonly_print = False
    if readonly_print and task_messages and task_messages[0].get("role") == "system":
        task_messages[0] = {"role": "system", "content": (task_messages[0].get("content") or "") + PRINT_ADDENDUM}
    try:
        skills_note = _skills.skills_prompt()
    except Exception:
        skills_note = ""
    if skills_note and task_messages and task_messages[0].get("role") == "system":
        task_messages[0] = {"role": "system", "content": (task_messages[0].get("content") or "") + skills_note}
    try:
        mcp_note = _mcp.mcp_prompt()
    except Exception:
        mcp_note = ""
    if mcp_note and task_messages and task_messages[0].get("role") == "system":
        task_messages[0] = {"role": "system", "content": (task_messages[0].get("content") or "") + mcp_note}

    trace = []
    seen_reads = set()
    _turn_reasoning.clear()
    _reset_turn_approvals()
    _last_turn_usage.update({"input": 0, "output": 0, "cached": 0, "calls": 0, "estimated": False})

    try:
        think = bool(config.is_think_enabled())
    except Exception:
        think = False

    ui.begin_turn()

    fast = try_fast_path(messages, user_input)
    if fast is not None:
        ui.end_turn()
        return fast

    mention_context, attached, _, mention_errors, attached_skills = expand_mentions(user_input)
    mention_images = []
    if attached:
        try:
            _targets = parse_mentions(user_input)
            _all_images = collect_mention_images(_targets)
            _attached_set = set(attached)
            mention_images = [img for img in _all_images if img.get("path") in _attached_set]
        except Exception:
            mention_images = []
    if mention_context:
        task_messages[-1]["content"] = user_input + "\n\n" + mention_context
        if attached:
            task_messages[-1]["content"] += "\n\nAnswer the user's instruction using the attached files; do not reprint them unless asked."
            if mention_images:
                task_messages[-1]["content"] += " Attached images are visible to you — describe what you see when relevant."
        if attached_skills:
            task_messages[-1]["content"] += "\n\nFollow the loaded skill instructions for this task."
        for path in attached:
            seen_reads.add(("read_file", str(path), "1", "60", ""))
            seen_reads.add(("read_file", str(path), "", "", ""))
            seen_reads.add(("list_files", str(path), "", "", ""))
            trace.append({"tool": "read_file", "args": {"path": path}, "detail": path, "result": "(attached via @mention)", "success": True, "exit_code": None})
            try:
                ui.show_tool("read_file", path, success=True, result="(attached via @mention)")
            except Exception:
                pass
        for name in attached_skills:
            seen_reads.add(("skill", str(name), "", "", ""))
            trace.append({"tool": "skill", "args": {"name": name}, "detail": name, "result": "(attached via @mention)", "success": True, "exit_code": None})
            try:
                ui.show_tool("skill", name, success=True, result="(attached via @mention)")
            except Exception:
                pass
        if attached:
            _note_target(attached[0])
        if not strip_mentions(user_input) and (attached or attached_skills) and not mention_errors:
            ui.end_turn()
            tagged = ", ".join(f"`@{p}`" for p in list(attached) + list(attached_skills))
            return _fast_reply(messages, user_input, f"Attached {tagged} — tell me what to do with it (explain, review, edit …).", trace)

    goal_note = _session_goal_note()
    if goal_note:
        try:
            _cur = task_messages[-1].get("content")
            if isinstance(_cur, str):
                task_messages[-1]["content"] = _cur + goal_note
            elif isinstance(_cur, list):
                for _part in task_messages[-1]["content"]:
                    if isinstance(_part, dict) and _part.get("type") == "text":
                        _part["text"] = (_part.get("text") or "") + goal_note
                        break
            else:
                task_messages[-1]["content"] = str(_cur or "") + goal_note
        except Exception:
            pass

    if mention_images:
        try:
            _cur = task_messages[-1].get("content")
            _text = _cur if isinstance(_cur, str) else user_input + ("\n\n" + mention_context if mention_context else "")
            task_messages[-1]["content"] = build_user_content(_text, mention_images)
        except Exception:
            pass

    try:
        provider = get_provider()
        response = _safe_stream_chat(provider, task_messages, _active_tools(), think=think)
        try:
            _record_usage(response, task_messages)
        except Exception:
            pass
    except KeyboardInterrupt:
        ui.end_turn()
        msg = "Cancelled."
        _commit_history(messages, user_input, msg)
        return msg, trace, _build_summary(trace, msg, user_input)
    except Exception as error:
        ui.end_turn()
        msg = _format_contact_error(error)
        summary = _build_summary([], msg, user_input)
        return msg, trace, summary

    prev_sig = None
    stall_count = 0
    nudged = False
    inspect_streak = 0

    for _ in range(MAX_ITERATIONS):
        if not response.tool_calls:
            break

        task_messages.append({
            "role": "assistant",
            "content": response.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": tc.arguments,
                    },
                }
                for tc in response.tool_calls
            ],
        })

        round_start = len(trace)
        jobs = []
        for tc in response.tool_calls:
            tool_name = tc.name
            try:
                if tc.arguments and len(tc.arguments) > 20000:
                    raise ValueError("tool arguments too large")
                arguments = json.loads(tc.arguments) if tc.arguments else {}
                if not isinstance(arguments, dict):
                    arguments = {}
            except (json.JSONDecodeError, ValueError):
                task_messages.append({"role": "tool", "content": "Invalid tool arguments.", "tool_call_id": tc.id})
                trace.append({"tool": tool_name, "args": {}, "detail": "", "result": "Invalid tool arguments.", "success": False, "exit_code": None})
                continue
            detail = _tool_detail(tool_name, arguments)
            cache_key = _tool_cache_key(tool_name, arguments, detail)
            cached = bool(cache_key and cache_key in seen_reads)
            if cache_key and not cached:
                seen_reads.add(cache_key)
            jobs.append({"tc": tc, "tool": tool_name, "args": arguments, "detail": detail, "cache_key": cache_key, "cached": cached})

        batch_keys = set()
        for job in jobs:
            if job["cached"] or not job["cache_key"]:
                continue
            if job["cache_key"] in batch_keys:
                job["cached"] = True
                job["result"] = "(already in context above; do not re-read)"
                job["elapsed"] = None
            else:
                batch_keys.add(job["cache_key"])

        parallel_ok = len(jobs) > 1 and all(_is_parallel_safe(j["tool"], j["args"]) for j in jobs)
        if parallel_ok:
            todo = [j for j in jobs if not j["cached"]]
            if todo:
                workers = min(PARALLEL_MAX_WORKERS, len(todo))
                try:
                    ui.show_loader(f"Working… · {len(todo)} parallel")
                except Exception:
                    pass
                # No `with` block: its __exit__ calls shutdown(wait=True), which
                # blocks on a hung tool long after we reported a timeout. wait()
                # bounds the batch, and shutdown(wait=False) returns immediately
                # so one stuck tool can't stall the whole turn.
                # Deferred: ~19ms of import that only parallel batches need.
                import concurrent.futures

                pool = concurrent.futures.ThreadPoolExecutor(
                    max_workers=workers, thread_name_prefix="hazzel-tool")
                future_map = {pool.submit(_run_one_tool, j["tool"], j["args"]): j for j in todo}
                timed_out = (
                    f"Tool timed out after {PARALLEL_TOOL_TIMEOUT:.0f} seconds. "
                    "Retry with a narrower scope."
                )
                try:
                    done, _pending = concurrent.futures.wait(
                        set(future_map), timeout=PARALLEL_TOOL_TIMEOUT)
                    # Walk `todo` order, not the done-set, so rows stay stable.
                    for fut in [f for f in future_map if f in done]:
                        job = future_map[fut]
                        raw, elapsed = fut.result()
                        job["result"] = raw
                        job["elapsed"] = elapsed
                    for fut in [f for f in future_map if f not in done]:
                        job = future_map[fut]
                        fut.cancel()
                        job["result"] = timed_out
                        job["elapsed"] = PARALLEL_TOOL_TIMEOUT
                    for job in todo:
                        result, success, exit_code = _finalize_result(job["result"])
                        job["_final"] = (result, success, exit_code)
                        try:
                            ui.show_tool(job["tool"], job["detail"], success=success,
                                         exit_code=exit_code, elapsed=job["elapsed"], result=result)
                        except Exception:
                            pass
                except KeyboardInterrupt:
                    for f in future_map:
                        f.cancel()
                    raise
                finally:
                    pool.shutdown(wait=False, cancel_futures=True)
            for job in jobs:
                if job["cached"] and "result" not in job:
                    job["result"] = "(already in context above; do not re-read)"
                    job["elapsed"] = None
                if "_final" in job:
                    result, success, exit_code = job.pop("_final")
                elif job["cached"]:
                    result, success, exit_code = job["result"], True, None
                else:
                    result, success, exit_code = _finalize_result(job["result"])
                    try:
                        ui.show_tool(job["tool"], job["detail"], success=success, exit_code=exit_code, elapsed=job.get("elapsed"), result=result)
                    except Exception:
                        pass
                job["elapsed"] = job.get("elapsed") if not job["cached"] else None
                task_messages.append({"role": "tool", "content": result, "tool_call_id": job["tc"].id})
                trace.append({"tool": job["tool"], "args": job["args"], "detail": job["detail"], "result": result, "success": success, "exit_code": exit_code, "cached": job["cached"]})
        else:
            for job in jobs:
                if job["cached"]:
                    result, success, exit_code, elapsed = job["result"] if "result" in job else "(already in context above; do not re-read)", True, None, None
                else:
                    try:
                        raw, elapsed = _run_one_tool(job["tool"], job["args"])
                    except KeyboardInterrupt:
                        raise
                    result, success, exit_code = _finalize_result(raw)
                try:
                    ui.show_tool(job["tool"], job["detail"], success=success, exit_code=exit_code, cached=job["cached"], elapsed=elapsed, result=result)
                except Exception:
                    pass
                task_messages.append({"role": "tool", "content": result, "tool_call_id": job["tc"].id})
                trace.append({"tool": job["tool"], "args": job["args"], "detail": job["detail"], "result": result, "success": success, "exit_code": exit_code, "cached": job["cached"]})

        round_entries = trace[round_start:]
        sig = tuple(sorted((t.get("tool"), str(t.get("detail"))) for t in round_entries))
        progressed = any(t.get("tool") in ("write_file", "edit_file", "apply_edits", "git_commit") and t.get("success") for t in round_entries)
        if sig and sig == prev_sig and not progressed:
            stall_count += 1
        else:
            stall_count = 0
        prev_sig = sig
        if stall_count >= 2:
            if not nudged:
                nudged = True
                stall_count = 0
                prev_sig = None
                task_messages.append({
                    "role": "user",
                    "content": "You are repeating the same tool calls without progress. Answer now using the context gathered so far, or make a clearly different call.",
                })
            else:
                task_messages.append({
                    "role": "user",
                    "content": "Stop calling tools. Answer now with NO tool calls, using only the context gathered so far.",
                })
                try:
                    final = _safe_stream_chat(provider, task_messages, [], think=think)
                    _record_usage(final, task_messages)
                    content = (final.content or "").strip() or "Done."
                except Exception:
                    ui.end_turn()
                    msg = "Stopped: repeating the same tool calls without progress. Try a smaller step or rephrase."
                    summary = _build_summary(trace, msg, user_input)
                    _update_last_target(trace)
                    _commit_history(messages, user_input, msg)
                    return msg, trace, summary
                ui.end_turn()
                _update_last_target(trace)
                _commit_history(messages, user_input, content)
                summary = _build_summary(trace, content, user_input)
                return content, trace, summary

        only_inspect = bool(round_entries) and all(t.get("tool") in ("list_files", "read_file", "search_files", "glob", "git_status", "git_diff") for t in round_entries)
        if only_inspect:
            inspect_streak += 1
        else:
            # Every fresh read-only spiral earns its own correction — a one-shot
            # latch let the model wander until the iteration cap.
            inspect_streak = 0
        if inspect_streak >= 4:
            inspect_streak = 0
            task_messages.append({
                "role": "user",
                "content": "You have explored enough. Take ONLY the requested action now (or answer) — no more listing, reading, or searching unless the request is genuinely ambiguous.",
            })

        try:
            ui.show_loader("Working…")
        except Exception:
            pass

        _enforce_turn_budget(task_messages)
        try:
            response = _safe_stream_chat(provider, task_messages, _active_tools(), think=think)
            try:
                _record_usage(response, task_messages)
            except Exception:
                pass
        except KeyboardInterrupt:
            ui.end_turn()
            msg = "Cancelled."
            _update_last_target(trace)
            _commit_history(messages, user_input, msg)
            return msg, trace, _build_summary(trace, msg, user_input)
        except Exception as error:
            ui.end_turn()

            msg = _format_contact_error(error)
            summary = _build_summary(trace, msg, user_input)

            return msg, trace, summary

    else:
        ui.end_turn()

        msg = f"Stopped: maximum tool iterations ({MAX_ITERATIONS}) reached. Try splitting the task into smaller steps."
        summary = _build_summary(trace, msg, user_input)
        _update_last_target(trace)
        _commit_history(messages, user_input, msg)

        return msg, trace, summary

    ui.end_turn()

    _update_last_target(trace)
    _commit_history(messages, user_input, response.content)

    summary = _build_summary(
        trace,
        response.content,
        user_input,
    )

    return response.content, trace, summary
