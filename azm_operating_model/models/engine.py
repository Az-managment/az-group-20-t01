"""Deterministic rendering engine for AZM assessments.

Pure functions only: they receive plain Python structures (no ORM records)
and return HTML/SVG strings. This keeps the logic testable and lets the
same engine feed the OWL workspace, the form view and the PDF report.

Input shapes
------------
stage   = {"id", "code", "name", "input", "output", "owner", "governance"}
question= {"id", "key", "code", "label", "qtype", "group", "clause",
           "condition", "raci"}
answers = {key: value}   value = str | list[str] | float | None
rule    = {"code", "stage", "key", "trigger", "fact", "risk", "control", "owner"}
"""

from html import escape

from .azm_svg import DEFS as SVG_DEFS, arrow as _arrow, box as _svg_box

UNKNOWN = "لا أعرف"
NOT_LISTED = "غير مدرج"
NONE = "لا يوجد"
NA = "لا ينطبق"
APPLIED = ("مطبقة بالكامل", "مطبقة جزئيًا")
OUTSIDE = ("خارج النظام", "جزء داخل وجزء خارج")

GROUP_TITLES = {
    "0": "واقع المرحلة",
    "1": "المسؤوليات والمسار",
    "2": "النظام والإثبات",
}

OUTPUT_TABS = [
    ("book", "الوضع الحالي"),
    ("policy", "السياسة"),
    ("procedure", "الإجراء"),
    ("workflow", "رسم الدورة"),
    ("authority", "الصلاحيات"),
    ("gaps", "النواقص"),
    ("risks", "المخاطر"),
    ("controls", "الضوابط المقترحة"),
    ("system", "متطلبات النظام واختبارها"),
    ("kpi", "مؤشرات المتابعة"),
    ("coverage", "تغطية المخرجات"),
]


# ---------------------------------------------------------------- values
def exists(value):
    if value is None or value == "" or value is False:
        return False
    if isinstance(value, (list, tuple)):
        return bool(value)
    return True


def known(value):
    if not exists(value):
        return False
    if isinstance(value, (list, tuple)):
        return UNKNOWN not in value and NOT_LISTED not in value
    return value not in (UNKNOWN, NOT_LISTED)


def show(value, unit=""):
    if isinstance(value, (list, tuple)):
        return "، ".join(value)
    if isinstance(value, float):
        value = int(value) if value.is_integer() else value
        return f"{value} {unit}".strip()
    return str(value)


def condition(cond, answers):
    """Same grammar as the prototype: eq / not / in / all / any."""
    if not cond:
        return True
    if "all" in cond:
        return all(condition(c, answers) for c in cond["all"])
    if "any" in cond:
        return any(condition(c, answers) for c in cond["any"])
    value = answers.get(cond.get("field"))
    if not known(value):
        return False
    if "eq" in cond:
        return value == cond["eq"]
    if "not" in cond:
        return value != cond["not"]
    if "in" in cond:
        return value in cond["in"]
    return False


def is_applied(stage, answers):
    return stage["governance"] or answers.get("presence") in APPLIED


def visible_questions(stage, questions, answers):
    out = []
    for q in questions:
        if not stage["governance"] and q["key"] not in ("presence", "na_reason"):
            if not is_applied(stage, answers):
                continue
        if condition(q["condition"], answers):
            out.append(q)
    return out


def stage_stats(stage, questions, answers):
    vis = visible_questions(stage, questions, answers)
    return {
        "total": len(vis),
        "answered": sum(1 for q in vis if exists(answers.get(q["key"]))),
        "known": sum(1 for q in vis if known(answers.get(q["key"]))),
    }


# ---------------------------------------------------------------- html bits
def _e(text):
    return escape(str(text or ""), quote=True)


def note(text, kind="info"):
    return f'<div class="o_azm_note o_azm_note_{kind}">{_e(text)}</div>'


def source_tag(stage, keys):
    codes = " · ".join(f"PUR-{stage['code']}/{k}" for k in keys)
    label = f"مصدر الصياغة · {len(keys)} سؤال" if len(keys) > 1 else f"مصدر الصياغة · PUR-{stage['code']}/{keys[0]}"
    if len(keys) == 1:
        return f'<span class="o_azm_source">{_e(label)}</span>'
    return f'<details class="o_azm_source"><summary>{_e(label)}</summary>{_e(codes)}</details>'


def doc_code(stage, default):
    """The code printed inside an output.

    A published document carries the code its cover carries — the caller passes it in —
    so one PDF never names itself two different things. The workspace, which previews an
    output that has not been published, keeps the catalogue's own shorthand.
    """
    return _e(stage.get("doc_code") or f"{default}-{stage['code']}")


def stage_header(stage):
    return (
        f'<div class="o_azm_stage_head"><span class="o_azm_code">PUR-{_e(stage["code"])}</span>'
        f'<h3>{_e(stage["name"])}</h3></div>'
    )


def sentence(q, answers):
    value = answers.get(q["key"])
    if not known(value):
        return ""
    unit = ""
    if q["qtype"] == "number":
        unit = answers.get("duration_unit", "") if q["key"] == "duration" else ""
    return f"{q['clause']}: {show(value, unit if known(unit) else '')}."


# ---------------------------------------------------------------- outputs
def render_book(stage, questions, answers):
    vis = visible_questions(stage, questions, answers)
    parts = [stage_header(stage)]
    if not stage["governance"] and not is_applied(stage, answers):
        presence = answers.get("presence")
        if known(presence):
            reason = answers.get("na_reason")
            txt = f"حالة تطبيق المرحلة: {presence}."
            if known(reason):
                txt += f" السبب: {reason}."
            parts.append(f'<p class="o_azm_clause">{_e(txt)}</p>')
        else:
            parts.append(note("ابدأ بتحديد هل المرحلة مطبقة عندكم أم لا.", "warn"))
        return "".join(parts)
    for group in ("0", "1", "2"):
        lines = [(q, sentence(q, answers)) for q in vis if q["group"] == group]
        lines = [(q, s) for q, s in lines if s]
        if not lines:
            continue
        if not stage["governance"]:
            parts.append(f'<h4 class="o_azm_group">{GROUP_TITLES[group]}</h4>')
        items = "".join(f"<li>{_e(s)}</li>" for _q, s in lines)
        parts.append(
            f'<ul class="o_azm_facts">{items}</ul>{source_tag(stage, [q["key"] for q, _s in lines])}'
        )
    if len(parts) == 1:
        parts.append(note("لا توجد إجابات محددة بعد في هذه المرحلة."))
    return "".join(parts)


def render_policy(stage, questions, answers):
    vis = visible_questions(stage, questions, answers)
    if not stage["governance"] and not is_applied(stage, answers):
        return stage_header(stage) + note("لا تُكتب سياسة لمرحلة غير مطبقة أو غير محسومة.")
    by_key = {q["key"]: q for q in vis}

    def clauses(keys):
        return [sentence(by_key[k], answers) for k in keys if k in by_key and sentence(by_key[k], answers)]

    specific = [q["key"] for q in vis if not q.get("is_common")]
    sections = [
        ("نطاق التطبيق", clauses(["presence"]) + clauses(specific)),
        ("المسؤوليات", clauses(["owner", "reviewer", "consulted", "informed"])),
        ("الاعتماد والصلاحيات", clauses(["approval_mode", "approver", "quorum", "currency"])),
        ("المسار بعد القرار", clauses(["accept_route", "reject_route", "duration"])),
        ("التنفيذ والإثبات", clauses(["boundary", "system", "inside", "channel", "record",
                                      "recorder", "input_doc", "output_doc", "proof_doc"])),
        ("العلاقة بالوثائق المكتوبة", clauses(["evidence"])),
    ]
    if stage["governance"]:
        sections = [("حوكمة الدورة", clauses(specific))]
    html = [stage_header(stage), f'<div class="o_azm_doc_code">{doc_code(stage, "CS-POL")}</div>']
    n = 0
    for title, lines in sections:
        if not lines:
            continue
        n += 1
        html.append(
            f'<div class="o_azm_section"><span class="o_azm_num">{n}</span>'
            f'<h4>{_e(title)}</h4><p>{_e(" ".join(lines))}</p></div>'
        )
    if n == 0:
        html.append(note("لا توجد إجابات كافية لصياغة السياسة."))
    html.append(note("المسودة توثّق ما تم الإبلاغ عنه ولا تمنحه صفة الاعتماد."))
    return "".join(html)


def render_procedure(stage, questions, answers):
    if stage["governance"]:
        return stage_header(stage) + note("الحوكمة لا تُكتب كإجراء تشغيلي؛ راجع تبويب السياسة.")
    if not is_applied(stage, answers):
        return stage_header(stage) + note("لا يُكتب إجراء لمرحلة غير مطبقة.")
    a = answers
    k = known

    def val(key, missing="[لم يُحدد]"):
        return show(a[key]) if k(a.get(key)) else missing

    steps = [
        ("بدء المرحلة", f"تبدأ المرحلة بمستند: {val('input_doc')}. المدخل المتوقع: {stage['input']}."),
        ("التنفيذ", f"ينفذ {val('owner')} أعمال المرحلة وفق القواعد المبلّغ عنها."),
        ("المراجعة", f"يراجع {val('reviewer')} نتيجة التنفيذ."
         + (f" يُستشار {val('consulted')} قبل القرار." if k(a.get("consulted")) and a.get("consulted") != NONE else "")),
    ]
    mode = a.get("approval_mode")
    if k(mode) and mode != "لا يوجد اعتماد":
        txt = f"طريقة الاعتماد: {mode}."
        if k(a.get("approver")):
            txt += f" صاحب الاعتماد: {a['approver']}."
        if k(a.get("quorum")):
            txt += f" قاعدة الاكتمال: {a['quorum']}."
        steps.append(("الاعتماد", txt))
    else:
        steps.append(("الاعتماد", "لا يوجد اعتماد مبلّغ عنه لهذه المرحلة." if mode == "لا يوجد اعتماد"
                      else "طريقة الاعتماد لم تُحدد."))
    steps.append(("توجيه الطلب", f"عند القبول: {val('accept_route')}. عند الرفض أو النقص: {val('reject_route')}."))
    doc = f"تُنفذ الخطوة {val('boundary')}"
    if k(a.get("system")):
        doc += f" على نظام {a['system']}"
    if k(a.get("channel")):
        doc += f"، والجزء الخارجي عبر {a['channel']}"
    doc += "."
    if k(a.get("record")):
        doc += f" تسجيل النتيجة لاحقًا: {a['record']}."
    doc += f" مستند النتيجة: {val('output_doc')}. إثبات القرار: {val('proof_doc')}."
    if k(a.get("informed")) and a.get("informed") != NONE:
        doc += f" يُبلّغ {a['informed']} بالنتيجة."
    steps.append(("التوثيق والإبلاغ", doc))
    vis = visible_questions(stage, questions, answers)
    rules = [sentence(q, answers) for q in vis if not q.get("is_common") and sentence(q, answers)]
    html = [stage_header(stage), f'<div class="o_azm_doc_code">{doc_code(stage, "CS-SOP")}</div><ol class="o_azm_steps">']
    for title, body in steps:
        html.append(f"<li><b>{_e(title)}</b><p>{_e(body)}</p></li>")
    html.append("</ol>")
    if rules:
        html.append('<h4 class="o_azm_group">قواعد خاصة بالمرحلة</h4><ul class="o_azm_rules">')
        html.extend(f"<li>{_e(r)}</li>" for r in rules)
        html.append("</ul>")
    if k(a.get("duration")):
        unit = a.get("duration_unit") if k(a.get("duration_unit")) else ""
        html.append(note(f"المدة المعتادة بحسب الإفادة: {show(a['duration'])} {unit}".strip()))
    html.append(note("القيم بين [ ] لم تُحدد في الإفادة ولم تُفترض."))
    return "".join(html)


# ---------------------------------------------------------------- svg
# the drawing primitives live apart, because the financial engine draws with them too


def render_workflow(stage, questions, answers):
    if stage["governance"]:
        return stage_header(stage) + note("رسم الدورة الكاملة يظهر عند اختيار نطاق «الدورة بالكامل».")
    if not is_applied(stage, answers):
        return stage_header(stage) + note("لا يُرسم مسار لمرحلة غير مطبقة.")
    a = answers

    def v(key, missing="لم يُحدد"):
        return show(a[key]) if known(a.get(key)) else missing

    def route(key):
        text = v(key)
        return text.split(" · ", 1)[1] if " · " in text else text

    has_approval = known(a.get("approval_mode")) and a.get("approval_mode") != "لا يوجد اعتماد"
    W = 680
    svg = [f'<svg viewBox="0 0 {W} 430" class="o_azm_svg" direction="ltr" style="direction:ltr" role="img" '
           f'aria-label="مسار {_e(stage["name"])}">', SVG_DEFS]
    cx = W / 2
    svg.append(_svg_box(cx - 130, 16, 260, 52, f"بدء · {v('input_doc')}", stage["input"]))
    svg.append(_arrow(cx, 68, cx, 92))
    svg.append(_svg_box(cx - 130, 92, 260, 52, "تنفيذ المرحلة", v("owner"), accent=True))
    svg.append(_arrow(cx, 144, cx, 168))
    svg.append(_svg_box(cx - 130, 168, 260, 52, "مراجعة النتيجة", v("reviewer")))
    svg.append(_arrow(cx, 220, cx, 246))
    # decision diamond
    dy = 246
    label = v("approval_mode") if has_approval else "قرار المرحلة"
    svg.append(f'<polygon points="{cx},{dy} {cx + 120},{dy + 40} {cx},{dy + 80} {cx - 120},{dy + 40}" '
               f'fill="#fff8e6" stroke="#c08a1e" stroke-width="1.3"/>')
    svg.append(f'<text x="{cx}" y="{dy + 38}" text-anchor="middle" font-size="12.5" font-weight="600" fill="#17323d">{_e(label)}</text>')
    if has_approval and known(a.get("approver")):
        svg.append(f'<text x="{cx}" y="{dy + 56}" text-anchor="middle" font-size="11" fill="#5b7380">{_e(a["approver"])}</text>')
    # accept (right in RTL reading = start) / reject
    svg.append(_arrow(cx + 120, dy + 40, W - 120, dy + 40, "قبول"))
    svg.append(_arrow(W - 120 + 0, dy + 40, W - 120, dy + 100))
    svg.append(_svg_box(W - 230, dy + 100, 210, 56, route("accept_route"), "وجهة القبول", accent=True))
    svg.append(_arrow(cx - 120, dy + 40, 120, dy + 40, "رفض / نقص"))
    svg.append(_arrow(120, dy + 40, 120, dy + 100))
    svg.append(_svg_box(20, dy + 100, 210, 56, route("reject_route"), "وجهة الرفض", dashed=True))
    svg.append("</svg>")
    html = [stage_header(stage), f'<div class="o_azm_doc_code">{doc_code(stage, "CS-WF")}</div>', "".join(svg)]
    if known(a.get("boundary")) and a.get("boundary") in OUTSIDE:
        html.append(note(f"جزء من الخطوة يتم خارج النظام عبر: {v('channel')}. تسجيل النتيجة: {v('record')}.", "warn"))
    return "".join(html)


def render_cycle_map(stages_data):
    """Global map of the 12 operational stages with status and risk badges.

    stages_data = [{"stage", "status", "risks", "known", "total"}]
    """
    ops = [s for s in stages_data if not s["stage"]["governance"]]
    cols, bw, bh, gx, gy = 4, 150, 74, 22, 40
    W = cols * bw + (cols - 1) * gx + 40
    rows = (len(ops) + cols - 1) // cols
    H = rows * bh + (rows - 1) * gy + 90
    colors = {
        "full": ("#e8f5ec", "#2f8a4c"),
        "partial": ("#fff8e6", "#c08a1e"),
        "none": ("#f3f4f6", "#9aa3ab"),
        "unknown": ("#ffffff", "#8aa1ad"),
    }
    svg = [f'<svg viewBox="0 0 {W} {H}" class="o_azm_svg" direction="ltr" style="direction:ltr" role="img" aria-label="خريطة دورة المشتريات">', SVG_DEFS]
    svg.append(f'<text x="{W - 20}" y="28" text-anchor="end" font-size="15" font-weight="600" fill="#17323d">'
               'دورة المشتريات من الطلب إلى الإقفال</text>')
    pos = []
    for i, s in enumerate(ops):
        r, c = divmod(i, cols)
        if r % 2 == 1:  # snake layout keeps arrows short
            c = cols - 1 - c
        x = W - 20 - (c + 1) * bw - c * gx  # RTL: first stage on the right
        y = 50 + r * (bh + gy)
        pos.append((x, y))
        fill, stroke = colors[s["status"]]
        svg.append(f'<rect x="{x}" y="{y}" width="{bw}" height="{bh}" rx="10" fill="{fill}" stroke="{stroke}" stroke-width="1.4"/>')
        svg.append(f'<text x="{x + bw - 10}" y="{y + 20}" text-anchor="end" font-size="10.5" fill="#5b7380">{i + 1:02d} · {_e(s["stage"]["code"])}</text>')
        name = s["stage"]["name"]
        words = name.split()
        line1, line2 = name, ""
        if len(name) > 18:
            half = (len(words) + 1) // 2
            line1, line2 = " ".join(words[:half]), " ".join(words[half:])
        svg.append(f'<text x="{x + bw / 2}" y="{y + 42}" text-anchor="middle" font-size="12" font-weight="600" fill="#17323d">{_e(line1)}</text>')
        if line2:
            svg.append(f'<text x="{x + bw / 2}" y="{y + 58}" text-anchor="middle" font-size="12" font-weight="600" fill="#17323d">{_e(line2)}</text>')
        if s["risks"]:
            svg.append(f'<circle cx="{x + 16}" cy="{y + 16}" r="10" fill="#c0392b"/>'
                       f'<text x="{x + 16}" y="{y + 20}" text-anchor="middle" font-size="11" font-weight="700" fill="#fff">{s["risks"]}</text>')
    for i in range(len(pos) - 1):
        (x1, y1), (x2, y2) = pos[i], pos[i + 1]
        if y1 == y2:
            if x2 < x1:
                svg.append(_arrow(x1, y1 + bh / 2, x2 + bw, y2 + bh / 2))
            else:
                svg.append(_arrow(x1 + bw, y1 + bh / 2, x2, y2 + bh / 2))
        else:
            svg.append(_arrow(x1 + bw / 2, y1 + bh, x2 + bw / 2, y2))
    # legend: fixed slots from the right edge
    ly = H - 18
    legend = [("full", "مطبقة بالكامل"), ("partial", "مطبقة جزئيًا"), ("none", "لا تتم / لا ينطبق"),
              ("unknown", "لم تُحسم")]
    for i, (key, label) in enumerate(legend):
        fill, stroke = colors[key]
        lx = W - 20 - i * 130
        svg.append(f'<rect x="{lx - 14}" y="{ly - 11}" width="14" height="14" rx="3" fill="{fill}" stroke="{stroke}"/>')
        svg.append(f'<text x="{lx - 20}" y="{ly}" text-anchor="end" font-size="11" fill="#5b7380">{label}</text>')
    lx = W - 20 - len(legend) * 130
    svg.append(f'<circle cx="{lx - 7}" cy="{ly - 4}" r="7" fill="#c0392b"/>'
               f'<text x="{lx - 20}" y="{ly}" text-anchor="end" font-size="11" fill="#5b7380">مؤشرات خطر</text>')
    svg.append("</svg>")
    return "".join(svg)


# ---------------------------------------------------------------- authority
RACI_COLS = [("owner", "ينفذ"), ("reviewer", "يراجع"), ("approver", "يعتمد"),
             ("consulted", "يُستشار"), ("informed", "يُبلّغ")]


def render_authority(stage, questions, answers):
    vis = visible_questions(stage, questions, answers)
    roles = [q for q in vis if q.get("is_role") and known(answers.get(q["key"]))]
    html = [stage_header(stage), f'<div class="o_azm_doc_code">{doc_code(stage, "CS-AUTH")}</div>']
    if not roles:
        return "".join(html) + note("لا توجد أدوار محددة بعد.")
    html.append('<div class="o_azm_cards">')
    for q in roles:
        html.append(f'<div class="o_azm_card"><span class="o_azm_badge">{_e(q["label"])}</span>'
                    f'<b>{_e(answers[q["key"]])}</b>{source_tag(stage, [q["key"]])}</div>')
    html.append("</div>")
    # segregation of duties signals
    sod = []
    for k1, k2, label in (("owner", "reviewer", "التنفيذ والمراجعة"), ("owner", "approver", "التنفيذ والاعتماد"),
                          ("reviewer", "approver", "المراجعة والاعتماد")):
        v1, v2 = answers.get(k1), answers.get(k2)
        if known(v1) and v1 == v2 and v1 != NONE:
            sod.append(f"نفس الدور ({v1}) يجمع بين {label}.")
    for s in sod:
        html.append(note(s, "warn"))
    return "".join(html)


def render_raci_matrix(stages_data):
    rows = []
    for s in stages_data:
        if s["stage"]["governance"]:
            continue
        a = s["answers"]
        if not is_applied(s["stage"], a):
            cells = '<td colspan="5" class="o_azm_muted">غير مطبقة أو لم تُحسم</td>'
        else:
            def cell(k):
                if known(a.get(k)):
                    return _e(show(a[k]))
                if k == "approver" and known(a.get("approval_mode")):
                    return f'<span class="o_azm_muted">{_e(a["approval_mode"])}</span>'
                return '<span class="o_azm_muted">—</span>'
            cells = "".join(f"<td>{cell(k)}</td>" for k, _l in RACI_COLS)
        rows.append(f"<tr><th>{_e(s['stage']['name'])}</th>{cells}</tr>")
    head = "".join(f"<th>{label}</th>" for _k, label in RACI_COLS)
    return (f'<h3>مصفوفة المسؤوليات للدورة</h3><table class="o_azm_table"><thead><tr><th>المرحلة</th>{head}</tr>'
            f'</thead><tbody>{"".join(rows)}</tbody></table>')


# ---------------------------------------------------------------- findings
def findings(stage, questions, answers, rules):
    if not stage["governance"] and not is_applied(stage, answers):
        return []
    active = {q["key"] for q in visible_questions(stage, questions, answers)}
    out = []
    for r in rules:
        if r["stage"] != stage["code"] or r["key"] not in active:
            continue
        value = answers.get(r["key"])
        hit = value == r["trigger"] or (isinstance(value, list) and r["trigger"] in value)
        if hit:
            out.append({**r, "keys": [r["key"]]})
    if not stage["governance"]:
        a = answers
        if a.get("boundary") in OUTSIDE and a.get("record") in ("جزئيًا", "لا يتم التسجيل"):
            out.append({"code": f"R-{stage['code']}-record", "keys": ["boundary", "record"],
                        "fact": "نتيجة التنفيذ الخارجي لا تُسجل بالكامل",
                        "risk": "فقد أثر القرار أو اختلاف بيانات المتابعة",
                        "control": "تحديد الحد الأدنى لبيانات القرار وإلزام تسجيلها وربط دليلها",
                        "owner": "مالك العملية"})
        if a.get("proof_doc") == NONE:
            out.append({"code": f"R-{stage['code']}-proof", "keys": ["proof_doc"],
                        "fact": "لا يوجد إثبات قرار بحسب الإفادة",
                        "risk": "تعذر تتبع المراجعة والاعتماد",
                        "control": "إلزام مرجع إثبات القرار ومسؤول وتاريخ قبل إقفال المرحلة",
                        "owner": "مالك العملية"})
        for k1, k2 in (("owner", "reviewer"), ("owner", "approver")):
            v1 = a.get(k1)
            if known(v1) and v1 != NONE and v1 == a.get(k2):
                out.append({"code": f"R-{stage['code']}-sod-{k2}", "keys": [k1, k2],
                            "fact": f"نفس الدور ({v1}) ينفذ و{'يراجع' if k2 == 'reviewer' else 'يعتمد'}",
                            "risk": "غياب فحص مستقل للقرار",
                            "control": "فصل الأدوار أو إضافة مراجعة مستقلة موثقة",
                            "owner": "مالك العملية"})
        if a.get("approval_mode") == "لا يوجد اعتماد":
            out.append({"code": f"R-{stage['code']}-noapproval", "keys": ["approval_mode"],
                        "fact": "المرحلة تتم دون أي اعتماد",
                        "risk": "قرارات تشغيلية دون تفويض أو مساءلة",
                        "control": "تحديد صاحب اعتماد أو توثيق مبرر عدم الحاجة للاعتماد",
                        "owner": "مالك العملية"})
    return out


def render_risks(stage, items, controls=False):
    html = [stage_header(stage)]
    if not items:
        html.append(note("لم تُفعّل الإجابات الحالية قاعدة خطر؛ هذا ليس تأكيدًا لغياب المخاطر."))
        return "".join(html)
    for r in items:
        title = r["control"] if controls else r["fact"]
        body = [f"<div>الممارسة المبلّغ عنها: {_e(r['fact'])}</div>",
                f"<div>الأثر المحتمل: {_e(r['risk'])}</div>"]
        if controls:
            body.append(f"<div>الضابط المقترح: {_e(r['control'])}</div>")
            tail = (f"<p>مسؤول مقترح للمراجعة: {_e(r['owner'])} — لم يُكلف فعليًا.</p>"
                    "<p>اختبار التطبيق: عينة تشمل حالة عادية واستثناء، مع التحقق من دليل تطبيق الضابط.</p>")
        else:
            tail = "<p>الاحتمال والأثر: لم يُقيّما؛ يلزم حجم وتكرار وقيمة العمليات وأدلتها.</p>"
        html.append(f'<article class="o_azm_risk"><span class="o_azm_code">{_e(r["code"])}</span>'
                    f'<h4>{_e(title)}</h4><div class="o_azm_chain">{"".join(body)}</div>{tail}'
                    f'{source_tag(stage, r["keys"])}</article>')
    return "".join(html)


def gaps(stage, questions, answers):
    vis = visible_questions(stage, questions, answers)
    missing = [q for q in vis if not exists(answers.get(q["key"]))]
    unknown = [q for q in vis if exists(answers.get(q["key"])) and not known(answers.get(q["key"]))]
    return missing, unknown


def render_gaps(stage, questions, answers):
    missing, unknown = gaps(stage, questions, answers)
    html = [stage_header(stage)]
    if not missing and not unknown:
        html.append(note("لا توجد إجابات ناقصة في الحقول الظاهرة. ده لا يثبت صحة الإفادة."))
        return "".join(html)
    if missing:
        html.append(f"<h4>لم تتم الإجابة ({len(missing)})</h4><ul>")
        html.extend(f"<li><span class='o_azm_code'>{_e(q['code'])}</span> {_e(q['label'])}</li>" for q in missing)
        html.append("</ul>")
    if unknown:
        html.append(f"<h4>«لا أعرف» أو «غير مدرج» ({len(unknown)}) — تحتاج صاحب معلومة</h4><ul>")
        html.extend(f"<li><span class='o_azm_code'>{_e(q['code'])}</span> {_e(q['label'])}</li>" for q in unknown)
        html.append("</ul>")
    return "".join(html)


def render_system(stage, questions, answers, items):
    if stage["governance"]:
        return stage_header(stage) + note(
            "متطلبات مقترحة: إدارة إصدارات السياسة، ومصفوفة التفويض، وسجل القرارات والاستثناءات، "
            "وصلاحيات فصل المسؤوليات.") + (
            '<div class="o_azm_section"><h4>اختبار قبول مقترح</h4><p>أنشئ نسخة مسودة، وعدّل صاحب اعتمادها، '
            'ثم تحقق أن النسخة السابقة محفوظة، وأن مستخدمًا دون صلاحية لا يستطيع نشر التعديل.</p></div>')
    if not is_applied(stage, answers):
        return stage_header(stage) + note("لا تُستنتج أتمتة لمرحلة غير مؤكدة التطبيق.")
    a = answers
    reqs = [
        ("النطاق والمرجع", "احفظ كل عملية بالكيان ونوع الشراء والمسار ورقم مرجعي يربط المراحل.",
         "أنشئ مسارين لنفس الكيان وتأكد من عدم انتقال بيانات أحدهما للآخر."),
        ("المسؤوليات", "اضبط منفذ المرحلة ومراجعها وجهات اعتمادها بعد تأكيد الأدوار والأشخاص.",
         "جرّب مستخدمًا مخولًا وآخر غير مخول؛ تحقق من السماح والمنع وسجل الأثر."),
        ("مسار القرار", f"وجهة القبول: {show(a.get('accept_route') or '[لم يُحدد]')}. "
                         f"وجهة الرفض: {show(a.get('reject_route') or '[لم يُحدد]')}.",
         "نفذ حالة قبول وحالة رفض، وتحقق من الوجهة وحفظ السبب والتاريخ والفاعل."),
        ("الأدلة", "اربط مستند البدء والنتيجة وإثبات القرار بالمرجع.",
         "حاول إغلاق خطوة تتطلب إثباتًا دون الدليل، ثم أضفه وأعد المحاولة."),
    ]
    if a.get("approval_mode") == "حسب شرائح القيمة":
        reqs.append(("شرائح الصلاحية", "طبّق الحدود المعتمدة بعد علاج الفجوات والتداخل وتحديد العملة.",
                     "اختبر قبل الحد مباشرة، وعنده، وبعده، ثم بعملة مختلفة."))
    if a.get("boundary") in OUTSIDE:
        reqs.append(("التنفيذ الخارجي", "وفر تسجيل نتيجة التنفيذ الخارجي مع مرجع الدليل ومسؤول الإدخال.",
                     "أدخل قرارًا خارجيًا وتحقق من ظهوره في المتابعة دون اعتباره اعتمادًا آليًا."))
    for r in items:
        reqs.append((r["fact"], r["control"], "اختبر حالة تتحقق فيها الممارسة وتأكد من المنع أو التنبيه وتوثيق الاستثناء."))
    html = [stage_header(stage), note("متطلبات واختبارات مقترحة لم تُنفذ على نظام فعلي.")]
    for i, (title, req, test) in enumerate(reqs, 1):
        html.append(f'<div class="o_azm_section"><span class="o_azm_code">SYS-{_e(stage["code"])}-{i} / '
                    f'UAT-{_e(stage["code"])}-{i}</span><h4>{_e(title)}</h4><p>{_e(req)}</p>'
                    f'<p><b>اختبار القبول:</b> {_e(test)}</p></div>')
    return "".join(html)


def render_kpi(stage, items):
    name = stage["name"]
    kpis = [
        (f"زمن {name}", "المدة بين بدء المرحلة وقرارها النهائي لكل عملية مكتملة؛ يُعرض الوسيط والقيم المتأخرة.",
         "وقت البدء، وقت القرار، سجل التعليق والاستئناف."),
        ("نسبة الاستثناءات", "عمليات ذات استثناء معتمد ÷ إجمالي العمليات المنطبقة × 100.", "سجل الاستثناءات."),
        ("اكتمال دليل القرار", "عمليات اكتمل دليلها ÷ العمليات التي يلزمها دليل × 100.", "مرفقات القرار ومراجعها."),
    ]
    html = [stage_header(stage), note("تعريفات مقترحة؛ لا قياسات فعلية أو أهداف معتمدة.")]
    for i, (t, d, src) in enumerate(kpis, 1):
        html.append(f'<div class="o_azm_section"><span class="o_azm_code">KPI-{_e(stage["code"])}-{i}</span>'
                    f'<h4>{_e(t)}</h4><p>{_e(d)}</p><p class="o_azm_muted">المصدر المطلوب: {_e(src)}</p></div>')
    for i, r in enumerate(items, 1):
        html.append(f'<div class="o_azm_section"><span class="o_azm_code">KRI-{_e(stage["code"])}-{i}</span>'
                    f'<h4>تكرار: {_e(r["fact"])}</h4><p>عدد العمليات التي ظهرت فيها الممارسة ÷ إجمالي العمليات × 100. '
                    f'حد الإنذار: [لم يُعتمد].</p></div>')
    return "".join(html)


def render_coverage(stage, questions, answers, items):
    st = stage_stats(stage, questions, answers)
    return (stage_header(stage) +
            f'<div class="o_azm_stats"><div><b>{st["total"]}</b><span>سؤال ظاهر</span></div>'
            f'<div><b>{st["answered"]}</b><span>إجابة مسجلة</span></div>'
            f'<div><b>{st["known"]}</b><span>إجابة محددة</span></div>'
            f'<div><b>{len(items)}</b><span>مؤشر خطر</span></div></div>' +
            note("التغطية للحقول الظاهرة فقط؛ لا تعني اعتماد السياسة أو التحقق من الأدلة."))


def render_stage(tab, stage, questions, answers, rules):
    items = findings(stage, questions, answers, rules)
    if tab == "book":
        return render_book(stage, questions, answers)
    if tab == "policy":
        return render_policy(stage, questions, answers)
    if tab == "procedure":
        return render_procedure(stage, questions, answers)
    if tab == "workflow":
        return render_workflow(stage, questions, answers)
    if tab == "authority":
        return render_authority(stage, questions, answers)
    if tab == "gaps":
        return render_gaps(stage, questions, answers)
    if tab == "risks":
        return render_risks(stage, items)
    if tab == "controls":
        return render_risks(stage, items, controls=True)
    if tab == "system":
        return render_system(stage, questions, answers, items)
    if tab == "kpi":
        return render_kpi(stage, items)
    if tab == "coverage":
        return render_coverage(stage, questions, answers, items)
    return ""


def stage_status(stage, answers):
    p = answers.get("presence")
    if stage["governance"]:
        return "full"
    if p == "مطبقة بالكامل":
        return "full"
    if p == "مطبقة جزئيًا":
        return "partial"
    if p in ("لا تتم", NA):
        return "none"
    return "unknown"


def render_cycle(tab, stages_data, rules):
    """Whole-cycle output. stages_data = [{"stage", "questions", "answers"}]."""
    enriched = []
    for s in stages_data:
        items = findings(s["stage"], s["questions"], s["answers"], rules)
        st = stage_stats(s["stage"], s["questions"], s["answers"])
        enriched.append({**s, "risks": len(items), "status": stage_status(s["stage"], s["answers"]),
                         "known": st["known"], "total": st["total"]})
    head = ""
    if tab == "workflow":
        return render_cycle_map(enriched)
    if tab == "authority":
        head = render_raci_matrix(enriched)
    if tab == "coverage":
        total = sum(e["total"] for e in enriched)
        known_n = sum(e["known"] for e in enriched)
        risks = sum(e["risks"] for e in enriched)
        head = (f'<div class="o_azm_stats"><div><b>{len(enriched)}</b><span>مرحلة</span></div>'
                f'<div><b>{total}</b><span>سؤال ظاهر</span></div><div><b>{known_n}</b><span>إجابة محددة</span></div>'
                f'<div><b>{risks}</b><span>مؤشر خطر</span></div></div>')
        rows = "".join(
            f"<tr><th>{_e(e['stage']['name'])}</th><td>{e['known']} / {e['total']}</td><td>{e['risks']}</td></tr>"
            for e in enriched)
        return head + (f'<table class="o_azm_table"><thead><tr><th>المرحلة</th><th>إجابات محددة</th>'
                       f'<th>مؤشرات خطر</th></tr></thead><tbody>{rows}</tbody></table>')
    body = "".join(render_stage(tab, s["stage"], s["questions"], s["answers"], rules) for s in stages_data)
    return head + body
