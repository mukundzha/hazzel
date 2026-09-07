from hazzel import ui


def test_format_elapsed():
    assert ui._format_elapsed(0.012) == "12ms"
    assert ui._format_elapsed(1.25) == "1.2s"
    assert ui._format_elapsed(None) == ""


def test_relativize_detail():
    assert ui._relativize_detail("/home/mukund/Code/Hazzel/hn.py") in ("hn.py", "/home/mukund/Code/Hazzel/hn.py")
    assert ui._relativize_detail("utcfromtimestamp") == "utcfromtimestamp"
    assert ui._relativize_detail("/etc/hostname") == "/etc/hostname"


def test_visible_len_strips_ansi():
    assert ui._visible_len("  \x1b[1m❯\x1b[0m hello") == 9
