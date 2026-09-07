import sys

from hazzel import agent
from hazzel import safety
from hazzel import ui
from hazzel import config
from rich.console import Console

console = Console()

messages = [{"role": "system", "content": agent.SYSTEM_PROMPT}]

_last_summary = None
_last_trace = []


def handle_model_command():
    catalog = config.get_catalog()
    current = config.get_current_model()
    selected = ui.select_model(catalog, current)
    if selected is None:
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
        return "0.1.0"


VERSION = _version()


def main(argv=None):
    global _last_summary, _last_trace
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
    ui.show_welcome(config.get_current_display_name(), config.PROJECT_ROOT)
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
        if user_input.strip() == "/model":
            handle_model_command()
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
        if user_input.strip().lower() in ["/help", "/h", "help"]:
            ui.show_help()
            continue
        if user_input.strip().lower() in ["/logout", "/signout", "logout"]:
            config.clear_api_keys()
            _last_summary = None
            _last_trace = []
            ui.show_logout()
            continue
        if user_input.strip().lower() in ["/summary", "/s", "summary"]:
            ui.show_summary(_last_summary, _last_trace)
            continue
        if user_input.strip().lower() in ["/usage", "/u", "usage"]:
            ui.show_usage(agent.get_session_usage(), agent.get_last_turn_usage())
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
            try:
                sys.stdout.write("\x1b[2J\x1b[3J\x1b[H")
                sys.stdout.flush()
            except OSError:
                pass
            ui.show_welcome(config.get_current_display_name(), config.PROJECT_ROOT)
            continue
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
        ui.show_hazzel_message(response)


if __name__ == "__main__":
    main()
