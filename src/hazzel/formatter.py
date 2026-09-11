from __future__ import annotations

import re
from dataclasses import dataclass

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from rich import box


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_CODE_THEME = "github-dark"

ACCENT_STYLE = "bold white"
HEADING_STYLE = "bold white"
BOLD_STYLE = "bold white"
ITALIC_STYLE = "italic"
STRIKE_STYLE = "strike"
INLINE_CODE_STYLE = "bold cyan"
LINK_STYLE = "underline cyan"
LINK_URL_STYLE = "dim"
MENTION_STYLE = "bold #8ab4f8"

BULLET_STYLE = "dim"
BULLET_MARKER_STYLE = "dim"
BLOCKQUOTE_STYLE = "dim italic"

TABLE_PADDING = (0, 1)

LEAD_SEPARATORS = (" — ", " – ", " - ", ": ")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CodeBlock:
    language: str
    code: str


@dataclass
class ParsedBlock:
    kind: str
    content: object


# ---------------------------------------------------------------------------
# Inline Markdown
# ---------------------------------------------------------------------------

INLINE_PATTERN = re.compile(
    r"""
    (?P<code>`(?P<code_text>[^`\n]+)`)
    |
    (?P<bold>\*\*(?P<bold_text>.+?)\*\*|__(?P<bold_text2>.+?)__)
    |
    (?P<strike>~~(?P<strike_text>.+?)~~)
    |
    (?P<link>\[(?P<link_text>[^\]]+)\]\((?P<link_url>[^)]+)\))
    |
    (?P<mention>(?<![\w@])@(?P<mention_text>[A-Za-z0-9_~][A-Za-z0-9_~./+-]*))
    |
    (?P<italic>(?<!\*)\*(?P<italic_text>[^*\n]+)\*(?!\*)|(?<!_)_(?P<italic_text2>[^_\n]+)_(?!_))
    """,
    re.VERBOSE,
)

BR_PATTERN = re.compile(r"<br\s*/?>", re.IGNORECASE)


def render_inline(value: str) -> Text:
    value = BR_PATTERN.sub("\n", value or "")
    result = Text()
    position = 0

    for match in INLINE_PATTERN.finditer(value):
        if match.start() > position:
            result.append(value[position:match.start()])

        code_text = match.group("code_text")
        bold_text = match.group("bold_text") or match.group("bold_text2")
        strike_text = match.group("strike_text")
        link_text = match.group("link_text")
        mention_text = match.group("mention_text")
        italic_text = match.group("italic_text") or match.group("italic_text2")

        if code_text is not None:
            result.append(code_text, style=INLINE_CODE_STYLE)
        elif mention_text is not None:
            stripped = mention_text.rstrip(".,!?;:)]")
            tail = mention_text[len(stripped):]
            result.append("@" + stripped, style=MENTION_STYLE)
            if tail:
                result.append(tail)
        elif bold_text is not None:
            result.append(bold_text, style=BOLD_STYLE)
        elif strike_text is not None:
            result.append(strike_text, style=STRIKE_STYLE)
        elif link_text is not None:
            result.append(link_text, style=LINK_STYLE)
            url = match.group("link_url")
            if url:
                result.append(f" ({url})", style=LINK_URL_STYLE)
        elif italic_text is not None:
            result.append(italic_text, style=ITALIC_STYLE)
        else:
            result.append(match.group(0))

        position = match.end()

    if position < len(value):
        result.append(value[position:])

    return result


def split_lead(content: str):
    for separator in LEAD_SEPARATORS:
        index = content.find(separator)
        if 0 < index <= 64:
            head, rest = content[:index], content[index + len(separator):]
            if head.strip() and rest.strip() and "`" not in head:
                return head.strip(), separator.strip(), rest.strip()
    return None

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def is_blank(line: str) -> bool:
    return not line.strip()


def is_horizontal_rule(line: str) -> bool:
    return bool(
        re.match(
            r"^\s*(\*{3,}|-{3,}|_{3,})\s*$",
            line,
        )
    )


def is_heading(line: str) -> bool:
    return bool(
        re.match(
            r"^\s*#{1,6}\s+",
            line,
        )
    )


def is_bullet(line: str) -> bool:
    return bool(
        re.match(
            r"^\s*[-*+•]\s+",
            line,
        )
    )


def is_numbered_list(line: str) -> bool:
    return bool(
        re.match(
            r"^\s*\d+[.)]\s+",
            line,
        )
    )


def is_task(line: str) -> bool:
    return bool(
        re.match(
            r"^\s*[-*+]\s+\[[ xX]\]\s+",
            line,
        )
    )


def is_table_separator(line: str) -> bool:
    """
    Detect:

    | --- | --- |
    |:---|---:|
    """

    cells = split_table_row(line)

    if len(cells) < 2:
        return False

    for cell in cells:
        if not re.match(
            r"^\s*:?-{1,}:?\s*$",
            cell,
        ):
            return False

    return True


def looks_like_table(lines: list[str], index: int) -> bool:
    if index + 1 >= len(lines):
        return False

    first = lines[index]
    second = lines[index + 1]

    if "|" not in first:
        return False

    return is_table_separator(second)


def split_table_row(line: str) -> list[str]:
    line = line.strip()

    if line.startswith("|"):
        line = line[1:]

    if line.endswith("|"):
        line = line[:-1]

    return [
        cell.strip()
        for cell in line.split("|")
    ]


def strip_heading(line: str) -> str:
    return re.sub(
        r"^\s*#{1,6}\s+",
        "",
        line,
    ).strip()


def normalize_language(language: str) -> str:
    aliases = {
        "py": "python",
        "js": "javascript",
        "ts": "typescript",
        "sh": "bash",
        "shell": "bash",
        "yml": "yaml",
        "md": "markdown",
        "text": "text",
        "txt": "text",
    }

    language = language.strip().lower()

    return aliases.get(
        language,
        language or "text",
    )


# ---------------------------------------------------------------------------
# Code blocks
# ---------------------------------------------------------------------------

def render_code_block(
    code: str,
    language: str = "",
) -> Panel:

    language = normalize_language(
        language
    )

    clean = "\n".join(
        line.rstrip() for line in code.splitlines()
    ).strip("\n")

    return Panel(
        Syntax(
            clean,
            language,
            theme=DEFAULT_CODE_THEME,
            line_numbers=False,
            word_wrap=True,
            indent_guides=False,
        ),
        title=language,
        title_align="left",
        border_style="dim",
        box=box.ROUNDED,
        expand=False,
        padding=(0, 1),
    )


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

def parse_table(lines: list[str]) -> tuple[list[str], list[list[str]]]:
    headers = split_table_row(lines[0])

    rows = [
        split_table_row(line)
        for line in lines[2:]
        if not is_blank(line)
    ]

    return headers, rows


def render_table(
    headers: list[str],
    rows: list[list[str]],
) -> Table:

    table = Table(
        show_header=True,
        header_style="bold white",
        border_style="dim",
        box=box.ROUNDED,
        show_lines=False,
        show_edge=True,
        expand=False,
        padding=TABLE_PADDING,
        pad_edge=False,
    )

    column_count = len(headers)

    for idx, header in enumerate(headers):
        if idx == 0:
            table.add_column(
                str(header),
                overflow="fold",
                no_wrap=False,
                max_width=32,
                style="bold",
            )
        else:
            table.add_column(
                str(header),
                overflow="fold",
                no_wrap=False,
                min_width=20,
            )

    for row in rows:

        row = list(row)

        if len(row) < column_count:
            row.extend(
                [""] * (column_count - len(row))
            )

        if len(row) > column_count:
            row = row[:column_count]

        table.add_row(
            *[
                render_inline(cell)
                for cell in row
            ]
        )

    return table


# ---------------------------------------------------------------------------
# Lists
# ---------------------------------------------------------------------------

def append_item_content(result: Text, content: str) -> None:
    lead = split_lead(content)
    if lead is None:
        result.append_text(render_inline(content))
        return
    head, separator, rest = lead
    headed = render_inline(head)
    headed.stylize(BOLD_STYLE)
    result.append_text(headed)
    result.append(f" {separator} ", style=BULLET_STYLE)
    result.append_text(render_inline(rest))


def render_list_item(
    line: str,
) -> Text:

    # Task item
    task_match = re.match(
        r"^(\s*)[-*+]\s+\[([ xX])\]\s+(.+)$",
        line,
    )

    if task_match:

        indentation = task_match.group(1)
        checked = task_match.group(2).lower() == "x"
        content = task_match.group(3)

        symbol = "✓" if checked else "□"

        result = Text(
            indentation
        )

        result.append(
            f"{symbol} ",
            style=BULLET_MARKER_STYLE,
        )

        append_item_content(result, content)

        return result

    # Numbered item
    numbered = re.match(
        r"^(\s*)(\d+)[.)]\s+(.+)$",
        line,
    )

    if numbered:

        indentation = numbered.group(1)
        number = numbered.group(2)
        content = numbered.group(3)

        result = Text(
            indentation
        )

        result.append(
            f"{number}. ",
            style=BULLET_MARKER_STYLE,
        )

        append_item_content(result, content)

        return result

    # Bullet item
    bullet = re.match(
        r"^(\s*)[-*+•]\s+(.+)$",
        line,
    )

    if bullet:

        indentation = bullet.group(1)
        content = bullet.group(2)

        result = Text(
            indentation
        )

        result.append(
            "• ",
            style=BULLET_MARKER_STYLE,
        )

        append_item_content(result, content)

        return result

    return render_inline(line)


# ---------------------------------------------------------------------------
# Block parser
# ---------------------------------------------------------------------------

def parse_blocks(message: str) -> list[ParsedBlock]:

    lines = message.replace(
        "\r\n",
        "\n",
    ).replace(
        "\r",
        "\n",
    ).split("\n")

    blocks: list[ParsedBlock] = []

    i = 0

    while i < len(lines):

        line = lines[i]

        # ---------------------------------------------------------------
        # Blank lines
        # ---------------------------------------------------------------

        if is_blank(line):
            i += 1
            continue

        # ---------------------------------------------------------------
        # Fenced code block
        # ---------------------------------------------------------------

        fence = re.match(
            r"^\s*```([A-Za-z0-9_+#.-]*)\s*$",
            line,
        )

        if fence:

            language = fence.group(1)

            code_lines = []

            i += 1

            while i < len(lines):

                if re.match(
                    r"^\s*```\s*$",
                    lines[i],
                ):
                    break

                code_lines.append(
                    lines[i]
                )

                i += 1

            blocks.append(
                ParsedBlock(
                    "code",
                    CodeBlock(
                        language=language,
                        code="\n".join(
                            code_lines
                        ),
                    ),
                )
            )

            i += 1

            continue

        # ---------------------------------------------------------------
        # Heading
        # ---------------------------------------------------------------

        if is_heading(line):

            blocks.append(
                ParsedBlock(
                    "heading",
                    strip_heading(line),
                )
            )

            i += 1

            continue

        # ---------------------------------------------------------------
        # Horizontal rule
        # ---------------------------------------------------------------

        if is_horizontal_rule(line):

            blocks.append(
                ParsedBlock(
                    "rule",
                    None,
                )
            )

            i += 1

            continue

        # ---------------------------------------------------------------
        # Table
        # ---------------------------------------------------------------

        if looks_like_table(
            lines,
            i,
        ):

            table_lines = [
                lines[i],
                lines[i + 1],
            ]

            i += 2

            while (
                i < len(lines)
                and "|" in lines[i]
                and not is_blank(lines[i])
            ):

                table_lines.append(
                    lines[i]
                )

                i += 1

            headers, rows = parse_table(
                table_lines
            )

            blocks.append(
                ParsedBlock(
                    "table",
                    (
                        headers,
                        rows,
                    ),
                )
            )

            continue

        # ---------------------------------------------------------------
        # Blockquote
        # ---------------------------------------------------------------

        if line.lstrip().startswith(">"):

            quote_lines = []

            while (
                i < len(lines)
                and lines[i].lstrip().startswith(">")
            ):

                quote = re.sub(
                    r"^\s*>\s?",
                    "",
                    lines[i],
                )

                quote_lines.append(
                    quote
                )

                i += 1

            blocks.append(
                ParsedBlock(
                    "blockquote",
                    "\n".join(
                        quote_lines
                    ),
                )
            )

            continue

        # ---------------------------------------------------------------
        # Lists
        # ---------------------------------------------------------------

        if (
            is_bullet(line)
            or is_numbered_list(line)
        ):

            list_lines = []

            while i < len(lines):

                current = lines[i]

                if (
                    is_bullet(current)
                    or is_numbered_list(current)
                    or (
                        current.startswith("  ")
                        and current.strip()
                    )
                ):

                    list_lines.append(
                        current
                    )

                    i += 1

                else:
                    break

            blocks.append(
                ParsedBlock(
                    "list",
                    list_lines,
                )
            )

            continue

        # ---------------------------------------------------------------
        # Indented code block
        # ---------------------------------------------------------------

        if line.startswith("    "):

            code_lines = []

            while (
                i < len(lines)
                and (
                    lines[i].startswith("    ")
                    or is_blank(lines[i])
                )
            ):

                if lines[i].startswith("    "):
                    code_lines.append(
                        lines[i][4:]
                    )
                else:
                    code_lines.append("")

                i += 1

            blocks.append(
                ParsedBlock(
                    "code",
                    CodeBlock(
                        language="text",
                        code="\n".join(
                            code_lines
                        ),
                    ),
                )
            )

            continue

        # ---------------------------------------------------------------
        # Paragraph
        # ---------------------------------------------------------------

        paragraph = [line]

        i += 1

        while i < len(lines):

            next_line = lines[i]

            if is_blank(next_line):
                break

            if (
                is_heading(next_line)
                or is_horizontal_rule(next_line)
                or is_bullet(next_line)
                or is_numbered_list(next_line)
                or next_line.lstrip().startswith(">")
                or next_line.startswith("    ")
                or re.match(
                    r"^\s*```",
                    next_line,
                )
                or looks_like_table(
                    lines,
                    i,
                )
            ):
                break

            paragraph.append(
                next_line
            )

            i += 1

        blocks.append(
            ParsedBlock(
                "paragraph",
                "\n".join(
                    paragraph
                ),
            )
        )

    return blocks


# ---------------------------------------------------------------------------
# Block rendering
# ---------------------------------------------------------------------------

def render_block(
    block: ParsedBlock,
):
    kind = block.kind

    # Paragraph
    if kind == "paragraph":
        text = re.sub(r"[ \t]+", " ", str(block.content).replace("\n", " ")).strip()
        result = render_inline(text)
        result.justify = "left"
        return result

    # Heading
    if kind == "heading":

        heading = Text()
        heading.append("▸ ", style=ACCENT_STYLE)
        start = len(heading)
        heading.append_text(
            render_inline(
                str(block.content)
            )
        )
        heading.stylize(
            HEADING_STYLE,
            start,
            len(heading),
        )

        return heading

    # Code
    if kind == "code":

        code_block: CodeBlock = block.content

        return render_code_block(
            code_block.code,
            code_block.language,
        )

    # Table
    if kind == "table":

        headers, rows = block.content

        return render_table(
            headers,
            rows,
        )

    # List
    if kind == "list":

        items = []

        for line in block.content:
            items.append(
                render_list_item(line)
            )

        return Text(
            "\n"
        ).join(items)

    # Blockquote
    if kind == "blockquote":

        content = Text()

        for index, line in enumerate(
            str(block.content).splitlines()
        ):

            if index:
                content.append("\n")

            content.append(
                "│ ",
                style=BLOCKQUOTE_STYLE,
            )

            content.append_text(
                render_inline(line)
            )

        return content

    # Horizontal rule
    if kind == "rule":
        return Rule(
            style="dim"
        )

    return Text(
        str(block.content)
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def format_response(
    message: str,
):
    """
    Convert an LLM response into terminal-native Rich renderables.

    The returned value can be passed directly to:

        console.print(format_response(message))
    """

    if not message or not message.strip():
        return Text()

    blocks = parse_blocks(
        message
    )

    rendered = []

    for block in blocks:

        rendered.append(
            (
                block.kind,
                render_block(block),
            )
        )

    return _group_blocks(
        rendered
    )


def _group_blocks(
    rendered: list,
):
    """
    Add controlled spacing between blocks.

    One blank line between every top-level block so headings,
    paragraphs, lists, tables and code stay scannable and never
    run into each other.
    """

    group = []

    for kind, renderable in rendered:
        if group:
            group.append(
                Text("")
            )

        group.append(
            renderable
        )

    return group


def print_response(
    console: Console,
    message: str,
) -> None:

    for renderable in format_response(
        message
    ):
        console.print(
            renderable,
            soft_wrap=False,
        )