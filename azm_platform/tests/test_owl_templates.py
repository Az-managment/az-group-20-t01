"""Names an Owl template reads that nothing ever defines.

Owl 3 renders a template against `{this: component, __owl__: node}` and nothing
else, so a bare `foo` in an expression compiles to `ctx['foo']` and is `undefined`
at render time unless a `t-set` or a `t-foreach` put it there. Reaching the
component is `this.foo`.

That is a silent fault: the template compiles, the page builds, the data loads,
every server-side test passes, and the first person to open it gets
"Cannot read properties of undefined". It happened to مساحتي للمراجعة, which was
written with a bare `d` next to a `get d()` on the component — the one other page
here that writes `d` declares it with `t-set` first, and that difference is
invisible when reading either file alone.

There is no browser in this container to catch it the usual way, so it is caught
by reading: every expression in every template of ours, against every name in
scope. It is a close enough reading of Owl's own rule to have caught that bug and
quiet enough to report nothing else across all of our templates.
"""
import os
import re

from lxml import etree

from odoo.tests import TransactionCase, tagged

# Names that are not the component's: JavaScript's own, and the words QWeb spells
# out. `this` is here because `this.x` is how the component is reached at all.
GLOBALS = {
    "this", "__owl__", "true", "false", "null", "undefined", "void", "typeof",
    "new", "in", "of", "instanceof", "return", "function", "const", "let", "var",
    "if", "else", "await", "async", "delete", "yield",
    "and", "or", "not",
    "Math", "JSON", "Object", "Array", "String", "Number", "Boolean", "Date",
    "Set", "Map", "Promise", "RegExp", "Error", "Infinity", "NaN",
    "parseInt", "parseFloat", "isNaN", "console", "window", "document",
    "encodeURIComponent", "decodeURIComponent", "luxon", "owl", "odoo",
}

# attributes that carry a name or a template, not an expression to evaluate
NOT_EXPRESSIONS = {
    "t-name", "t-ref", "t-else", "t-tag", "t-portal", "t-component",
    "t-set-slot", "t-slot", "t-inherit", "t-inherit-mode",
    "t-translation", "t-no-translation", "t-debug", "t-log",
}
EXPRESSION_PREFIXES = ("t-att-", "t-on-", "t-model")

TOKEN = re.compile(r"""
   (?P<str>'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*"|`(?:\\.|[^`\\])*`)
 | (?P<num>\b\d[\w.]*)
 | (?P<dot>\.\s*[A-Za-z_$][\w$]*)
 | (?P<name>[A-Za-z_$][\w$]*)
""", re.X)
ARROW_PARAMS = re.compile(r"\(([^()]*)\)\s*=>|([A-Za-z_$][\w$]*)\s*=>")
INTERPOLATED = re.compile(r"\{\{(.*?)\}\}|#\{(.*?)\}")


def free_names(expression):
    """Root identifiers an expression reads — what Owl turns into ctx['name']."""
    expression = expression or ""
    local = set()
    for in_parens, bare in ARROW_PARAMS.findall(expression):
        for part in (in_parens or "").split(","):
            part = part.strip().strip("{}[]").strip()
            if re.fullmatch(r"[A-Za-z_$][\w$]*", part):
                local.add(part)
        if bare:
            local.add(bare)
    names = set()
    for match in TOKEN.finditer(expression):
        if match.lastgroup != "name":
            continue           # a string, a number, or a .property
        name = match.group("name")
        after = expression[match.end():].lstrip()
        if after.startswith(":") and not after.startswith("::"):
            continue           # a key of an object literal
        if name not in GLOBALS and name not in local:
            names.add(name)
    return names


def _read(element, defined, used, called):
    for key, value in element.attrib.items():
        if key == "t-set":
            defined.add(value)
        elif key == "t-as":
            defined.update({value, f"{value}_index", f"{value}_value",
                            f"{value}_first", f"{value}_last", f"{value}_all"})
        elif key == "t-call":
            called.add(value)
        elif key in NOT_EXPRESSIONS:
            continue
        elif key.startswith("t-attf-"):
            for a, b in INTERPOLATED.findall(value):
                used.update(free_names(a or b))
        elif key.startswith("t-") or key.startswith(EXPRESSION_PREFIXES):
            used.update(free_names(value))
    for child in element:
        if isinstance(child.tag, str):
            _read(child, defined, used, called)


def undefined_names(path):
    """[(template, name)] — every name read in this file that nothing defines."""
    per_template, callers_of = {}, {}
    for node in etree.parse(path).getroot().iter():
        name = node.get("t-name")
        if not name:
            continue
        defined, used, called = set(), set(), set()
        _read(node, defined, used, called)
        per_template[name] = (defined, used)
        for target in called:
            callers_of.setdefault(target, set()).add(name)
    found = []
    for name, (defined, used) in per_template.items():
        # a t-called template renders in its caller's scope, so its names count
        for caller in callers_of.get(name, ()):
            defined |= per_template.get(caller, (set(), set()))[0]
        found += [(name, free) for free in sorted(used - defined)]
    return found


@tagged('post_install', '-at_install')
class TestOwlTemplatesSayWhereTheirNamesComeFrom(TransactionCase):

    def test_every_name_is_defined(self):
        source = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
        complaints = []
        for module in sorted(os.listdir(source)):
            static = os.path.join(source, module, "static", "src")
            for folder, _subs, files in os.walk(static):
                for f in files:
                    if not f.endswith(".xml"):
                        continue
                    path = os.path.join(folder, f)
                    for template, name in undefined_names(path):
                        complaints.append(
                            f"{os.path.relpath(path, source)} · {template} reads "
                            f"`{name}`, which nothing defines — did you mean "
                            f"`this.{name}`?")
        self.assertFalse(complaints, "\n" + "\n".join(complaints))
