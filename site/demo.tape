# Hazzel demo — one message, one bug fix.
# Re-record with: vhs site/demo.tape   (requires vhs + ffmpeg + ttyd)
# Output matches the embeds in README.md (assets/demo.gif) and
# site/index.html (site/demo.gif): 980x596, ~100 cols, <1MB, <30s.
#
# What it shows (in order):
#   1. zero-install launch via `uvx hazzel`
#   2. one user message: fix the failing test in test.py
#   3. read -> diff + y approval (ask-once) -> pytest green
#   4. ends on the summary output (no footer on the end frame)
#
# The hidden setup builds a tiny deterministic fixture so the tape
# re-records offline: test.py ships with an off-by-one bug, pytest
# passes after the one-line fix.

Output site/demo.gif

Set Shell "bash"
Set FontSize 15
Set Width 980
Set Height 596
Set Padding 12
Set TypingSpeed 50ms
Set Framerate 12
Set CursorBlink false

Hide
Type "rm -rf /tmp/hazzel-demo && mkdir -p /tmp/hazzel-demo && cd /tmp/hazzel-demo && printf 'def add(a, b):\n    return a + b + 1\n\ndef test_add():\n    assert add(1, 2) == 3\n' > test.py && clear"
Enter
Sleep 1s
Show

Type "uvx hazzel"
Enter
Sleep 2s

Type "Fix the failing test in test.py"
Enter
Sleep 4s

Type "y"
Enter
Sleep 2s

Sleep 3s
