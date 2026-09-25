import difflib
import json
from pathlib import Path

# Undo event: (resolved path, prior content, agent content).
# prior None means the file did not exist at checkpoint time.
# post None means unknown (legacy checkpoints + shell commands) -> blind restore.
_events: list[tuple[str, bytes | None, bytes | None]] = []

# Redo event: (path, prior, post, undo_result, pre_undo_content).
# undo_result None means undo left the file deleted; pre_undo None means missing.
_redo: list[tuple[str, bytes | None, bytes | None, bytes | None, bytes | None]] = []

MAX_EVENTS = 200
MAX_DEPTH_PER_FILE = 20
MAX_DIFF_LINES = 80
MAX_PERSIST_BYTES = 2_000_000

# Merge guards: bigger than this -> no per-hunk attempt, keep user content.
MERGE_MAX_BYTES = 500_000
MERGE_MAX_LINES = 20000


def _undo_dir():
    from . import config as _cfg

    return Path(_cfg.CONFIG_DIR) / "undo"


def _index_path():
    return _undo_dir() / "index.json"


def _backups_dir():
    return _undo_dir() / "backups"


def _coerce_blob(value):
    if value is None:
        return None
    if isinstance(value, bytes):
        return value
    return str(value).encode("utf-8")


def _coerce_event(ev):
    """Tolerate legacy 2-tuples appended by older code/tests."""
    try:
        if len(ev) == 2:
            return (str(ev[0]), ev[1], None)
        return (str(ev[0]), ev[1], ev[2])
    except (TypeError, IndexError):
        return None


def _persist_save():
    try:
        undo_dir = _undo_dir()
        backups = _backups_dir()
        undo_dir.mkdir(parents=True, exist_ok=True)
        backups.mkdir(parents=True, exist_ok=True)
        try:
            undo_dir.chmod(0o700)
        except OSError:
            pass

        def _store(blob, tag, idx):
            if blob is None:
                return None
            if len(blob) > MAX_PERSIST_BYTES:
                return None
            name = f"{tag}{idx:04d}-{abs(hash(str(idx))) % 10_000_000:07d}.bak"
            try:
                dest = backups / name
                dest.write_bytes(blob)
                try:
                    dest.chmod(0o600)
                except OSError:
                    pass
                return name
            except OSError:
                return None

        items = []
        for i, ev in enumerate(_events):
            coerced = _coerce_event(ev)
            if coerced is None:
                continue
            key, prior, post = coerced
            items.append({
                "path": key,
                "prior": _store(prior, "up", i),
                "post": _store(post, "uo", i),
                "post_missing": post is None,
            })
        redo_items = []
        for i, ev in enumerate(_redo):
            try:
                key, prior, post, restored, displaced = ev
            except (TypeError, ValueError):
                continue
            redo_items.append({
                "path": str(key),
                "prior": _store(prior, "rp", i),
                "post": _store(post, "ro", i),
                "restored": _store(restored, "rr", i),
                "displaced": _store(displaced, "rd", i),
            })
        try:
            tmp = _index_path().with_suffix(".tmp")
            tmp.write_text(json.dumps({"v": 2, "items": items, "redo": redo_items}),
                           encoding="utf-8")
            tmp.replace(_index_path())
        except OSError:
            pass
        try:
            valid = set()
            for it in items + redo_items:
                for k in ("prior", "post", "restored", "displaced", "backup"):
                    if it.get(k):
                        valid.add(it[k])
            for blob in backups.glob("*.bak"):
                if blob.name not in valid:
                    try:
                        blob.unlink()
                    except OSError:
                        pass
        except OSError:
            pass
    except Exception:
        pass


def _load_blob(backups, name):
    if not name:
        return None
    try:
        blob = backups / str(name)
        if not blob.exists() or blob.stat().st_size > MAX_PERSIST_BYTES:
            return None
        return blob.read_bytes()
    except OSError:
        return None


def _persist_load():
    global _events, _redo
    try:
        index = _index_path()
        if not index.exists():
            return
        data = json.loads(index.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return
        backups = _backups_dir()
        raw_items = data.get("items")
        if not isinstance(raw_items, list):
            return
        loaded = []
        for it in raw_items[-MAX_EVENTS:]:
            if not isinstance(it, dict) or not it.get("path"):
                continue
            if "backup" in it and "prior" not in it:
                # v1 index: prior only, post unknown.
                name = it.get("backup")
                prior = _load_blob(backups, name) if name else None
                loaded.append((it["path"], prior, None))
                continue
            prior = _load_blob(backups, it.get("prior"))
            post = _load_blob(backups, it.get("post"))
            if it.get("prior") and prior is None and not it.get("post_missing", True):
                pass
            loaded.append((it["path"], prior, post))
        if loaded:
            _events = loaded
        raw_redo = data.get("redo")
        if isinstance(raw_redo, list):
            redo_loaded = []
            for it in raw_redo[-MAX_EVENTS:]:
                if not isinstance(it, dict) or not it.get("path"):
                    continue
                redo_loaded.append((
                    it["path"],
                    _load_blob(backups, it.get("prior")),
                    _load_blob(backups, it.get("post")),
                    _load_blob(backups, it.get("restored")),
                    _load_blob(backups, it.get("displaced")),
                ))
            if redo_loaded:
                _redo = redo_loaded
    except Exception:
        pass


def clear_undo_log():
    global _events, _redo
    _events = []
    _redo = []
    try:
        index = _index_path()
        if index.exists():
            index.unlink()
        backups = _backups_dir()
        if backups.exists():
            for blob in backups.glob("*.bak"):
                try:
                    blob.unlink()
                except OSError:
                    pass
    except OSError:
        pass


def checkpoint(path, updated=None):
    """Snapshot prior bytes before a write. Pass what will be written as
    `updated` so /undo can tell agent edits apart from later user edits."""
    global _redo
    path = Path(path)
    key = str(path)
    try:
        prior = path.read_bytes() if path.exists() and path.is_file() else None
    except OSError:
        return
    post = _coerce_blob(updated)
    _events.append((key, prior, post))
    while len([1 for ev in _events if _coerce_event(ev) and _coerce_event(ev)[0] == key]) > MAX_DEPTH_PER_FILE:
        for i, ev in enumerate(_events):
            coerced = _coerce_event(ev)
            if coerced is not None and coerced[0] == key:
                del _events[i]
                break
    del _events[: max(0, len(_events) - MAX_EVENTS)]
    _redo = []
    _persist_save()


def _read_current(path):
    try:
        p = Path(path)
        if not p.exists() or not p.is_file():
            return None
        return p.read_bytes()
    except OSError:
        return None


def _decode_lines(blob):
    return blob.decode("utf-8").splitlines()


def _locate_equal(equal_blocks, p1, p2):
    """Map source interval [p1,p2) to dest via equal blocks. None if touched."""
    if p1 == p2:
        cands = [b for b in equal_blocks if b[0] <= p1 <= b[1]]
        if not cands:
            return None
        if len(cands) > 1:
            # Insertion point inside a user-edited gap: ambiguous, keep user.
            first_end = cands[0][2] + (p1 - cands[0][0])
            for b in cands[1:]:
                if b[2] + (p1 - b[0]) != first_end:
                    return None
            return (first_end, first_end)
        b = cands[0]
        pos = b[2] + (p1 - b[0])
        return (pos, pos)
    for b in equal_blocks:
        if b[0] <= p1 and p2 <= b[1]:
            off = b[2] - b[0]
            return (p1 + off, p2 + off)
    return None


def _revert_agent_hunks(base_lines, agent_lines, current_lines):
    """Reverse base->agent hunks found verbatim in current. Returns
    (merged, reverted, skipped)."""
    import difflib as _d

    sm_ba = _d.SequenceMatcher(None, base_lines, agent_lines, autojunk=False)
    hunks = [h for h in sm_ba.get_opcodes() if h[0] != "equal"]
    if not hunks:
        return (list(current_lines), 0, 0)
    sm_ac = _d.SequenceMatcher(None, agent_lines, current_lines, autojunk=False)
    equal_ac = [(a1, a2, b1, b2) for t, a1, a2, b1, b2 in sm_ac.get_opcodes()
                if t == "equal" and a1 != a2]
    merged = list(current_lines)
    reverted = 0
    skipped = 0
    for tag, a1, a2, b1, b2 in sorted(hunks, key=lambda h: h[3], reverse=True):
        loc = _locate_equal(equal_ac, b1, b2)
        if loc is None:
            skipped += 1
            continue
        c1, c2 = loc
        if merged[c1:c2] != agent_lines[b1:b2]:
            skipped += 1
            continue
        merged[c1:c2] = base_lines[a1:a2]
        reverted += 1
    return (merged, reverted, skipped)


def _apply_target_hunks(base_lines, target_lines, current_lines):
    """Apply base->target hunks found at base positions in current. For redo."""
    import difflib as _d

    sm_bt = _d.SequenceMatcher(None, base_lines, target_lines, autojunk=False)
    hunks = [h for h in sm_bt.get_opcodes() if h[0] != "equal"]
    if not hunks:
        return (list(current_lines), 0, 0)
    sm_bc = _d.SequenceMatcher(None, base_lines, current_lines, autojunk=False)
    equal_bc = [(a1, a2, b1, b2) for t, a1, a2, b1, b2 in sm_bc.get_opcodes()
                if t == "equal" and a1 != a2]
    merged = list(current_lines)
    applied = 0
    skipped = 0
    for tag, a1, a2, b1, b2 in sorted(hunks, key=lambda h: h[1], reverse=True):
        loc = _locate_equal(equal_bc, a1, a2)
        if loc is None:
            skipped += 1
            continue
        c1, c2 = loc
        if merged[c1:c2] != base_lines[a1:a2]:
            skipped += 1
            continue
        merged[c1:c2] = target_lines[b1:b2]
        applied += 1
    return (merged, applied, skipped)


def _mergeable(prior, post, current):
    if post is None:
        return False
    try:
        total = len(prior or b"") + len(post) + len(current or b"")
    except TypeError:
        return False
    if total > MERGE_MAX_BYTES:
        return False
    try:
        for blob in (prior, post, current):
            if blob is not None:
                blob.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _match_paths(key, filters):
    if not filters:
        return True
    for f in filters:
        f = str(f)
        if key == f or key.endswith("/" + f.lstrip("/")) or key.endswith(f):
            return True
    return False


def _normalize_filters(paths):
    if not paths:
        return None
    if isinstance(paths, str):
        return [paths]
    return [str(p) for p in paths]


def _select_indices(count, paths):
    filt = _normalize_filters(paths)
    idxs = []
    for i in range(len(_events) - 1, -1, -1):
        coerced = _coerce_event(_events[i])
        if coerced is None:
            continue
        if _match_paths(coerced[0], filt):
            idxs.append(i)
            if len(idxs) >= max(1, count):
                break
    return idxs


def _blind_apply(key, prior):
    path = Path(key)
    try:
        if prior is None:
            if not path.exists():
                return (False, "skipped")
            if path.is_dir():
                return (False, "skipped")
            path.unlink()
            return (True, "removed")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(prior)
        return (True, "restored")
    except OSError:
        return (False, "skipped")


def undo(count=1, force=False, paths=None):
    """Smart undo: reverts agent hunks, keeps later user edits. Legacy blind
    restore when post was never recorded (shell commands) or with force."""
    restored = []
    if force:
        idxs = _select_indices(count, paths)
        for i in sorted(idxs, reverse=True):
            coerced = _coerce_event(_events[i])
            if coerced is None:
                del _events[i]
                continue
            key, prior, post = coerced
            cur = _read_current(key)
            if prior is None and cur is None:
                del _events[i]
                continue
            if Path(key).is_dir():
                del _events[i]
                continue
            ok, action = _blind_apply(key, prior)
            del _events[i]
            if ok:
                _redo.append((key, prior, post, prior, cur))
                restored.append((key, action))
        if restored:
            _persist_save()
        return restored

    remaining = max(1, count)
    guard = 0
    while remaining > 0 and _events and guard < MAX_EVENTS + 5:
        guard += 1
        idx = -1
        filt = _normalize_filters(paths)
        if filt:
            found = _select_indices(1, paths)
            if not found:
                break
            idx = found[0]
        coerced = _coerce_event(_events[idx])
        if coerced is None:
            del _events[idx]
            continue
        key, prior, post = coerced
        if Path(key).is_dir():
            del _events[idx]
            remaining -= 1
            continue
        cur = _read_current(key)
        if post is None:
            # Unknown agent result: legacy blind restore.
            if prior is None and cur is None:
                del _events[idx]
                remaining -= 1
                continue
            ok, action = _blind_apply(key, prior)
            del _events[idx]
            remaining -= 1
            if ok:
                _redo.append((key, prior, post, prior, cur))
                restored.append((key, action))
            continue
        if prior is None:
            # Agent created the file.
            if cur is None:
                del _events[idx]
                remaining -= 1
                continue
            if cur == post:
                try:
                    Path(key).unlink()
                except OSError:
                    remaining -= 1
                    continue
                del _events[idx]
                remaining -= 1
                _redo.append((key, prior, post, None, cur))
                restored.append((key, "removed"))
                continue
            restored.append((key, "kept (your edits preserved; /undo --force discards)"))
            break
        # prior exists.
        if cur is None:
            restored.append((key, "kept (file deleted after checkpoint; /undo --force restores)"))
            break
        if cur == post:
            try:
                Path(key).parent.mkdir(parents=True, exist_ok=True)
                Path(key).write_bytes(prior)
            except OSError:
                remaining -= 1
                continue
            del _events[idx]
            remaining -= 1
            _redo.append((key, prior, post, prior, cur))
            restored.append((key, "restored"))
            continue
        if cur == prior:
            del _events[idx]
            remaining -= 1
            restored.append((key, "skipped (already matches checkpoint)"))
            continue
        if not _mergeable(prior, post, cur):
            restored.append((key, "kept (overlaps your edits; /undo --force discards)"))
            break
        try:
            base_lines = _decode_lines(prior)
            agent_lines = _decode_lines(post)
            cur_lines = _decode_lines(cur)
        except UnicodeDecodeError:
            restored.append((key, "kept (overlaps your edits; /undo --force discards)"))
            break
        if len(base_lines) + len(agent_lines) + len(cur_lines) > MERGE_MAX_LINES:
            restored.append((key, "kept (overlaps your edits; /undo --force discards)"))
            break
        merged, reverted, skipped = _revert_agent_hunks(base_lines, agent_lines, cur_lines)
        if reverted == 0:
            restored.append((key, "kept (overlaps your edits; /undo --force discards)"))
            break
        try:
            Path(key).write_text("\n".join(merged) + ("\n" if merged else ""),
                                 encoding="utf-8")
        except OSError:
            remaining -= 1
            continue
        del _events[idx]
        remaining -= 1
        _redo.append((key, prior, post, "\n".join(merged).encode() +
                      (b"\n" if merged else b""), cur))
        if skipped == 0:
            restored.append((key, "merged (kept your edits)"))
        else:
            restored.append((key, f"partial (reverted {reverted}, kept yours in {skipped})"))
    if restored and any(a not in ("kept (your edits preserved; /undo --force discards)",
                                  "kept (overlaps your edits; /undo --force discards)",
                                  "kept (file deleted after checkpoint; /undo --force restores)")
                        for _, a in restored):
        _persist_save()
    elif any(idx is not None for idx in []):
        pass
    else:
        # Persist when the stack itself changed (pops without file mutation).
        try:
            _persist_save()
        except Exception:
            pass
    return restored


def redo(count=1, force=False, paths=None):
    """Reapply what undo took away, preserving edits made after the undo."""
    redone = []
    if not _redo:
        return redone
    remaining = max(1, count)
    filt = _normalize_filters(paths)
    guard = 0
    while remaining > 0 and _redo and guard < MAX_EVENTS + 5:
        guard += 1
        idx = -1
        if filt:
            found = None
            for i in range(len(_redo) - 1, -1, -1):
                try:
                    if _match_paths(str(_redo[i][0]), filt):
                        found = i
                        break
                except (TypeError, IndexError):
                    continue
            if found is None:
                break
            idx = found
        try:
            key, prior, post, restored, displaced = _redo[idx]
        except (TypeError, ValueError):
            del _redo[idx]
            continue
        key = str(key)
        if Path(key).is_dir():
            del _redo[idx]
            continue
        cur = _read_current(key)
        if force:
            if displaced is None and cur is None:
                del _redo[idx]
                _events.append((key, prior, post))
                remaining -= 1
                continue
            ok, _ = _blind_apply(key, displaced)
            del _redo[idx]
            remaining -= 1
            if ok:
                _events.append((key, prior, post))
                action = "removed" if displaced is None else "redone"
                redone.append((key, action))
            continue
        if cur == restored or (cur is None and restored is None):
            if displaced is None:
                if cur is not None:
                    try:
                        Path(key).unlink()
                    except OSError:
                        remaining -= 1
                        continue
                action = "removed"
            else:
                try:
                    Path(key).parent.mkdir(parents=True, exist_ok=True)
                    Path(key).write_bytes(displaced)
                except OSError:
                    remaining -= 1
                    continue
                action = "recreated" if restored is None else "redone"
            del _redo[idx]
            remaining -= 1
            _events.append((key, prior, post))
            redone.append((key, action))
            continue
        if cur == displaced or (cur is None and displaced is None):
            del _redo[idx]
            remaining -= 1
            _events.append((key, prior, post))
            redone.append((key, "skipped (already redone)"))
            continue
        base = restored
        target = displaced
        if base is None or target is None:
            redone.append((key, "kept (overlaps newer edits; /redo --force overwrites)"))
            break
        if not _mergeable(base, target, cur):
            redone.append((key, "kept (overlaps newer edits; /redo --force overwrites)"))
            break
        try:
            base_lines = _decode_lines(base)
            target_lines = _decode_lines(target)
            cur_lines = _decode_lines(cur)
        except UnicodeDecodeError:
            redone.append((key, "kept (overlaps newer edits; /redo --force overwrites)"))
            break
        if len(base_lines) + len(target_lines) + len(cur_lines) > MERGE_MAX_LINES:
            redone.append((key, "kept (overlaps newer edits; /redo --force overwrites)"))
            break
        merged, applied, skipped = _apply_target_hunks(base_lines, target_lines, cur_lines)
        if applied == 0:
            redone.append((key, "kept (overlaps newer edits; /redo --force overwrites)"))
            break
        try:
            Path(key).write_text("\n".join(merged) + ("\n" if merged else ""),
                                 encoding="utf-8")
        except OSError:
            remaining -= 1
            continue
        del _redo[idx]
        remaining -= 1
        _events.append((key, prior, post))
        if skipped == 0:
            redone.append((key, "reapplied (kept your newer edits)"))
        else:
            redone.append((key, f"partial (reapplied {applied}, kept yours in {skipped})"))
    if redone:
        _persist_save()
    return redone


def _would_be_for_event(key, prior, post, cur):
    """Compute undo result without writing. Returns (would_be, action)."""
    if Path(key).is_dir():
        return (cur, "skipped (is a directory)")
    if post is None:
        return (prior, "restores" if prior != cur else "no change")
    if prior is None:
        if cur is None:
            return (None, "no change")
        if cur == post:
            return (None, "removes")
        return (cur, "keeps (your edits preserved)")
    if cur is None:
        return (cur, "keeps (file deleted after checkpoint)")
    if cur == post:
        return (prior, "restores")
    if cur == prior:
        return (cur, "no change")
    if not _mergeable(prior, post, cur):
        return (cur, "keeps (overlaps your edits)")
    try:
        base_lines = _decode_lines(prior)
        agent_lines = _decode_lines(post)
        cur_lines = _decode_lines(cur)
    except UnicodeDecodeError:
        return (cur, "keeps (overlaps your edits)")
    if len(base_lines) + len(agent_lines) + len(cur_lines) > MERGE_MAX_LINES:
        return (cur, "keeps (overlaps your edits)")
    merged, reverted, skipped = _revert_agent_hunks(base_lines, agent_lines, cur_lines)
    if reverted == 0:
        return (cur, "keeps (overlaps your edits)")
    blob = ("\n".join(merged) + ("\n" if merged else "")).encode()
    if skipped == 0:
        return (blob, "merges (keeps your edits)")
    return (blob, f"partial (reverts {reverted}, keeps yours in {skipped})")


def preview_undo(count=1, paths=None):
    """Show what undo would do, changing nothing."""
    out = []
    for i in _select_indices(count, paths):
        coerced = _coerce_event(_events[i])
        if coerced is None:
            continue
        key, prior, post = coerced
        cur = _read_current(key)
        would_be, action = _would_be_for_event(key, prior, post, cur)
        out.append((key, action, diff_text(key, cur, would_be)))
    return out


def preview_redo(count=1, paths=None):
    out = []
    filt = _normalize_filters(paths)
    idxs = []
    for i in range(len(_redo) - 1, -1, -1):
        try:
            if _match_paths(str(_redo[i][0]), filt):
                idxs.append(i)
                if len(idxs) >= max(1, count):
                    break
        except (TypeError, IndexError):
            continue
    for i in idxs:
        try:
            key, _, _, restored, displaced = _redo[i]
        except (TypeError, ValueError):
            continue
        key = str(key)
        cur = _read_current(key)
        out.append((key, "reapplies" if cur == restored else "reapplies" if cur != displaced else "no change",
                    diff_text(key, cur, displaced)))
    return out


def redo_count():
    return len(_redo)


def pending_count():
    return len(_events)


def diff_text(display_path, original, updated):
    def _lines(data):
        if data is None:
            return []
        if isinstance(data, bytes):
            data = data.decode("utf-8", errors="replace")
        return str(data).splitlines()

    diff = difflib.unified_diff(
        _lines(original),
        _lines(updated),
        fromfile=f"a/{display_path}",
        tofile=f"b/{display_path}",
        lineterm="",
    )
    lines = list(diff)
    if not lines:
        return "(no changes)"
    if len(lines) > MAX_DIFF_LINES:
        lines = lines[:MAX_DIFF_LINES] + ["[…diff truncated…]"]
    return "\n".join(lines)


try:
    _persist_load()
except Exception:
    pass
