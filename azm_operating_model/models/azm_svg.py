"""The drawing primitives both engines share.

Pure functions over plain values, like the engines that use them: they return SVG
strings and know nothing about the ORM. They live apart from either engine because a
flowchart of a financial work cycle is not a procurement thing, and neither engine
should have to import the other to draw one.
"""
from html import escape

# One arrow head, defined once per drawing and pointed at by every line in it.
DEFS = ('<defs><marker id="azm-arrow" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M0 0L10 5L0 10z" fill="#8aa1ad"/></marker></defs>')

INK = "#17323d"
MUTED = "#5b7380"
LINE = "#8aa1ad"
ACCENT = "#1f5f73"

# How much text fits on one line inside a box, at the sizes below. Arabic runs a little
# wider than Latin per character, so this is deliberately conservative.
_PER_LINE = 44


def _e(value):
    return escape(str(value if value is not None else ""))


def wrap(text, per_line=_PER_LINE, max_lines=2):
    """Break ``text`` into at most ``max_lines`` lines, marking anything dropped.

    Words are kept whole where they fit; a word longer than a line is cut, because a
    box that grows to fit one long word would throw the whole drawing out.
    """
    if not text:
        return []
    words, lines, current = str(text).split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= per_line:
            current = candidate
            continue
        if current:
            lines.append(current)
        if len(lines) == max_lines:
            lines[-1] = lines[-1][: per_line - 1].rstrip() + "…"
            return lines
        current = word if len(word) <= per_line else word[: per_line - 1] + "…"
    if current:
        lines.append(current)
    return lines[:max_lines]


def box(x, y, w, h, title, sub="", accent=False, dashed=False):
    """A rounded box with a title and, under it, one or more quieter lines."""
    stroke = ACCENT if accent else LINE
    fill = "#e6f1f4" if accent else "#ffffff"
    dash = ' stroke-dasharray="5 4"' if dashed else ""
    subs = sub if isinstance(sub, (list, tuple)) else ([sub] if sub else [])
    out = (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}" '
           f'stroke="{stroke}" stroke-width="{2 if accent else 1.2}"{dash}/>')
    # the title sits in the middle when it is alone, and rides up when lines follow it
    cy = y + (h / 2 if not subs else h / 2 - 6 * len(subs))
    out += (f'<text x="{x + w / 2}" y="{cy + 5}" text-anchor="middle" font-size="13" '
            f'font-weight="600" fill="{INK}">{_e(title)}</text>')
    for index, line in enumerate(subs):
        out += (f'<text x="{x + w / 2}" y="{cy + 23 + index * 15}" text-anchor="middle" '
                f'font-size="11" fill="{MUTED}">{_e(line)}</text>')
    return out


def arrow(x1, y1, x2, y2, label=""):
    out = (f'<path d="M{x1} {y1} L{x2} {y2}" stroke="{LINE}" stroke-width="1.3" '
           f'fill="none" marker-end="url(#azm-arrow)"/>')
    if label:
        out += (f'<text x="{(x1 + x2) / 2}" y="{(y1 + y2) / 2 - 6}" text-anchor="middle" '
                f'font-size="11" fill="{MUTED}">{_e(label)}</text>')
    return out


def flow(steps, label="مسار العمل", width=680, box_width=440):
    """A flowchart of ``steps`` read top to bottom, one box each, arrows between.

    ``steps`` is a list of ``{"title", "sub"}``. The drawing sizes itself to what it is
    given rather than to a fixed canvas, so a cycle of three steps is not three boxes
    adrift in the space twelve would need.
    """
    if not steps:
        return ""
    gap, top = 30, 14
    laid, y = [], top
    for step in steps:
        lines = wrap(step.get("sub") or "")
        height = 44 + 15 * len(lines)
        laid.append((y, height, step.get("title") or "", lines))
        y += height + gap
    total = y - gap + top

    x = (width - box_width) / 2
    out = [f'<svg viewBox="0 0 {width} {total}" class="o_azm_svg" direction="ltr" '
           f'style="direction:ltr" role="img" aria-label="{_e(label)}">', DEFS]
    for index, (top_y, height, title, lines) in enumerate(laid):
        # the first box is the way in, so it is the one drawn as the accent
        out.append(box(x, top_y, box_width, height, title, lines, accent=index == 0))
        if index + 1 < len(laid):
            out.append(arrow(width / 2, top_y + height, width / 2, top_y + height + gap))
    out.append("</svg>")
    return "".join(out)
