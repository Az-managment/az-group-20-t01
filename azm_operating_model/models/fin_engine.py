"""Rendering of the unified financial model outputs.

Pure functions over plain dicts (no ORM) so the workspace, the form and the
approved snapshot all show the same document. HTML uses the same classes as
the procurement operating model (azm_output.scss) so both models look alike.

module = {"code", "name"}
item   = {"code", "req_id", "title", "question", "profile", "profile_name", "scope_name", "topic", "topic_code",
          "pack", "owner", "state", "impl", "rule", "target", "issues", "target_note", "reason", "done",
          "qa": [{"code", "key", "label", "qtype", "unit", "display", "columns", "rows", "names", "fallback"}],
          "missing": [labels], "q_total", "q_answered"}
"""

from html import escape

from .azm_svg import flow

STATE_LABELS = {
    "full": "مطبّق بالكامل",
    "partial": "مطبّق جزئيًا",
    "unavailable": "غير منفذ",
    "unknown": "لا أعرف",
    "na": "لا ينطبق",
}

OUTPUT_TABS = [
    ("book", "الوضع الحالي"),
    ("rules", "القواعد والسياسات"),
    ("workflow", "دورات العمل"),
    ("authority", "الصلاحيات والرقابة"),
    ("reports", "التقارير والمؤشرات"),
    ("integration", "التكامل والترحيل"),
    ("gaps", "الفجوات"),
    ("future", "النموذج المستهدف"),
    ("na", "لا ينطبق"),
    ("coverage", "تغطية المخرجات"),
]

TAB_PROFILES = {
    "rules": ("P", "C", "L"),
    "workflow": ("W",),
    "authority": ("A",),
    "reports": ("R",),
    "integration": ("I",),
}
DOC_CODES = {"book": "CS-FIN", "rules": "CS-POL", "workflow": "CS-SOP", "authority": "CS-AUTH",
             "reports": "CS-RPT", "integration": "CS-INT", "gaps": "CS-GAP", "future": "CS-TOM",
             "na": "CS-NA", "coverage": "CS-COV"}
# who creates / reviews / approves: a person in two of them is a segregation-of-duties warning
ROLE_WORDS = {
    "create": ("يُنشئ", "ينشئ", "يُعد", "يعد", "المنفذ", "يطلب", "يسجل"),
    "review": ("يراجع", "يراجعها", "يراجعه", "المراجع"),
    "approve": ("يعتمد", "يعتمده", "يعتمدها", "المعتمد", "يُعتمد"),
}
NOT_A_PERSON = {"لا يوجد", "لا أعرف", "غير مدرج", ""}
# A table whose first column names a step is a cycle, and is drawn as one. "بعد (يوم)"
# is here because an escalation ladder — after so many days, do this, and it is theirs —
# is an order of work like any other; what differs is that its first column is when the
# step happens rather than what it is, which is handled below.
STEP_COLUMNS = ("الخطوة", "المرحلة", "الحدث", "بعد (يوم)")


def step_rows(qa):
    """``[{"title", "sub"}]`` for a table that reads as a sequence.

    The step's name is the first column that reads as a name: where a table is ordered
    by a number — days elapsed, a level — that number says *when*, not *what*, so it
    moves into the line underneath and the next column gives the box its title.
    """
    columns, rows = qa["columns"], qa["rows"]
    if not columns or not rows:
        return []

    def numeric(index):
        seen = [row[index] for row in rows if index < len(row) and str(row[index]).strip()]
        if not seen:
            return False
        return all(str(value).strip().replace(".", "", 1).isdigit() for value in seen)

    lead = 1 if (numeric(0) and len(columns) > 1) else 0
    ordered = sorted(rows, key=lambda row: float(row[0])) if lead else rows
    steps = []
    for row in ordered:
        title = (row[lead] if lead < len(row) else "") or "[لم يُحدد]"
        detail = " · ".join(
            f"{columns[i]['label']}: {row[i]}"
            for i in range(len(columns))
            if i != lead and i < len(row) and str(row[i]).strip())
        steps.append({"title": title, "sub": detail})
    return steps


def _e(text):
    return escape(str(text or ""), quote=True)


def note(text, kind="info"):
    cls = "o_azm_note o_azm_note_warn" if kind == "warn" else "o_azm_note"
    return f'<div class="{cls}">{_e(text)}</div>'


# ---------------------------------------------------------------- visibility
def visible_keys(questions, values):
    """questions = [{"key", "condition"}] in order; values = {key: set(option names)}.

    A question is visible when it has no condition, or when the question it refers to is visible
    and answered with one of the listed options."""
    keys = set()
    for q in questions:
        cond = q.get("condition")
        if not cond or (cond["q"] in keys and values.get(cond["q"], set()) & set(cond["in"])):
            keys.add(q["key"])
    return keys


# ---------------------------------------------------------------- pieces
def module_header(module, tab):
    return (f'<div class="o_azm_stage_head"><span class="o_azm_code">FIN.{_e(module["code"])}</span>'
            f'<h3>{_e(module["name"])}</h3></div>'
            f'<div class="o_azm_doc_code">{DOC_CODES.get(tab, "CS")}-{_e(module["code"])}</div>')


def render_table(columns, rows):
    if not rows:
        return ""
    head = "".join(f"<th>{_e(c['label'])}</th>" for c in columns)
    body = "".join(
        "<tr>" + "".join(f"<td>{_e(row[i] if i < len(row) else '')}</td>" for i in range(len(columns))) + "</tr>"
        for row in rows)
    return f'<table class="o_azm_table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def _title(item):
    return (f'<h4>{_e(item["title"])} <span class="o_azm_code">{_e(item["code"])}</span></h4>'
            f'<p class="o_azm_fin_mainq">{_e(item["question"])}</p>')


def _source(item):
    return f'<span class="o_azm_source">مصدر الصياغة · {_e(item["req_id"] or item["code"])}</span>'


def _state_line(item):
    parts = [f"حالة التطبيق: {STATE_LABELS.get(item['state'], 'لم تتم الإجابة')}"]
    if item.get("impl"):
        parts.append(f"وسيلة التنفيذ: {'، '.join(item['impl'])}")
    if item.get("rule"):
        parts.append(f"القاعدة: {item['rule']}")
    if item.get("target"):
        parts.append(f"التوجه: {item['target']}")
    return f'<p class="o_azm_muted">{_e(" · ".join(parts))}</p>'


def _facts(item, tables=True):
    """Answers of the requirement-specific questions: one fact per question, tables in full."""
    facts, blocks = [], []
    for qa in item["qa"]:
        if qa["qtype"] == "table" and qa["rows"]:
            if tables:
                blocks.append(f'<p class="o_azm_fin_tablecap">{_e(qa["label"])}</p>' + render_table(qa["columns"], qa["rows"]))
            else:
                facts.append(f"<li><b>{_e(qa['label'])}:</b> {len(qa['rows'])} صف</li>")
        else:
            cls = ' class="o_azm_muted"' if qa["fallback"] else ""
            facts.append(f"<li{cls}><b>{_e(qa['label'])}:</b> {_e(qa['display'])}</li>")
    html = f'<ul class="o_azm_facts">{"".join(facts)}</ul>' if facts else ""
    return html + "".join(blocks)


def _missing(item):
    if not item["missing"]:
        return ""
    return f'<p class="o_azm_muted">لم تتم الإجابة: {_e("، ".join(item["missing"]))}</p>'


def _topic_groups(items):
    groups = []
    for item in items:
        if not groups or groups[-1][0] != item["topic_code"]:
            groups.append((item["topic_code"], item["topic"], []))
        groups[-1][2].append(item)
    return groups


def _topic_head(code, name):
    return f'<h4 class="o_azm_fin_topic"><span class="o_azm_code">{_e(code)}</span> {_e(name)}</h4>' if code else ""


# ---------------------------------------------------------------- per tab
def _book(module, items):
    html = [module_header(module, "book")]
    if not items:
        return html[0] + note("لا توجد متطلبات منطبقة في هذا الموديول.")
    open_items = []
    for code, name, group in _topic_groups(items):
        answered = [i for i in group if i["state"] or i["qa"]]
        open_items += [i for i in group if not (i["state"] or i["qa"])]
        if not answered:
            continue
        html.append(_topic_head(code, name))
        for item in answered:
            body = [_title(item), _state_line(item)]
            if item["state"] == "na":
                body.append(f"<p>سبب عدم الانطباق: {_e(item['reason'] or '[لم يُذكر]')}</p>")
            else:
                body.append(_facts(item))
                if item["issues"]:
                    body.append(f'<p class="o_azm_muted">تغطية النظام والمشاكل الحالية: {_e(item["issues"])}</p>')
                body.append(_missing(item))
            body.append(_source(item))
            html.append(f'<div class="o_azm_section">{"".join(body)}</div>')
    if open_items:
        html.append(f"<h4>لم تبدأ الإجابة ({len(open_items)})</h4><ul>")
        html += [f"<li>{_e(i['code'])} · {_e(i['title'])}</li>" for i in open_items]
        html.append("</ul>")
    return "".join(html)


def _people(item):
    """{role: set(person)} from the select answers and the table columns of the requirement."""
    found = {k: set() for k in ROLE_WORDS}

    def role_of(label):
        for role, words in ROLE_WORDS.items():
            if any(w in label for w in words):
                return role
        return None

    for qa in item["qa"]:
        if qa["qtype"] == "table":
            for idx, col in enumerate(qa["columns"]):
                role = role_of(col["label"])
                if role:
                    found[role] |= {row[idx] for row in qa["rows"] if idx < len(row) and row[idx] not in NOT_A_PERSON}
        elif qa["qtype"] == "select":
            role = role_of(qa["label"])
            if role:
                found[role] |= {n for n in qa["names"] if n not in NOT_A_PERSON}
    return found


def _sod_warning(item):
    people = _people(item)
    clash = (people["create"] & people["approve"]) | (people["review"] & people["approve"]) | \
            (people["create"] & people["review"])
    if clash:
        return note(f"«{'، '.join(sorted(clash))}» يظهر في أكثر من مهمة (إنشاء / مراجعة / اعتماد) — راجع الفصل بين المهام.",
                    "warn")
    return ""


def _steps(qa):
    """A work cycle, drawn as the flow it is.

    The answers arrive as a table — a row per step, the columns saying who does it and
    when — and a table makes the reader reconstruct the order for themselves. The same
    rows read top to bottom with an arrow between them say it outright, and match the
    procurement cycle, which has always been drawn this way.
    """
    return (f'<p class="o_azm_fin_tablecap">{_e(qa["label"])}</p>'
            + flow(step_rows(qa), label=qa["label"]))


def _by_profile(tab, module, items):
    profiles = TAB_PROFILES[tab]
    rel = [i for i in items if i["profile"] in profiles]
    html = [module_header(module, tab)]
    if not rel:
        return html[0] + note("لا توجد متطلبات من هذا النوع في الموديول.")
    for item in rel:
        if item["state"] not in ("full", "partial"):
            label = STATE_LABELS.get(item["state"], "لم تتم الإجابة")
            html.append(f'<div class="o_azm_section">{_title(item)}'
                        f'<p class="o_azm_muted">[{_e(label)}] — لا توجد قاعدة قائمة تُكتب في هذا المخرج.</p></div>')
            continue
        body = [_title(item), _state_line(item)]
        if tab == "workflow":
            for qa in item["qa"]:
                if qa["qtype"] == "table" and qa["rows"] and qa["columns"] and qa["columns"][0]["label"] in STEP_COLUMNS:
                    body.append(_steps(qa))
            body.append(_facts({**item, "qa": [q for q in item["qa"] if not (
                q["qtype"] == "table" and q["columns"] and q["columns"][0]["label"] in STEP_COLUMNS)]}))
        else:
            body.append(_facts(item))
        if tab == "authority":
            body.append(_sod_warning(item))
        if item["state"] == "partial" and item["issues"]:
            body.append(note(f"فجوة: {item['issues']}", "warn"))
        body.append(_source(item))
        html.append(f'<div class="o_azm_section">{"".join(body)}</div>')
    return "".join(html)


def _gaps(module, items):
    html = [module_header(module, "gaps")]
    rel = [i for i in items if i["state"] in ("partial", "unavailable")]
    if not rel:
        return html[0] + note("لا توجد فجوات مسجلة في هذا الموديول.")
    for item in rel:
        html.append(
            f'<div class="o_azm_risk"><span class="o_azm_code">{_e(item["code"])}</span>'
            f'<h4>{_e(item["title"])}</h4><div class="o_azm_chain">'
            f'<span><b>الحالة:</b> {_e(STATE_LABELS[item["state"]])}'
            f'{(" · " + _e("، ".join(item["impl"]))) if item["impl"] else ""}</span>'
            f'<span><b>التغطية والمشاكل الحالية:</b> {_e(item["issues"] or "[لم يُحدد]")}</span>'
            f'<span><b>حالة القاعدة:</b> {_e(item["rule"] or "[لم يُحدد]")}</span>'
            f'<span><b>التوجه المستهدف:</b> {_e(item["target"] or "[لم يُحدد]")}</span></div></div>')
    return "".join(html)


def _future(module, items):
    html = [module_header(module, "future")]
    rel = [i for i in items if i["state"] in ("unavailable", "partial", "unknown")
           or (i["target"] and i["target"] != "استمرار")]
    if not rel:
        return html[0] + note("لا توجد متطلبات تحتاج تصميمًا مستهدفًا في هذا الموديول.")
    for item in rel:
        html.append(f'<div class="o_azm_section">{_title(item)}'
                    f'<p class="o_azm_muted">{_e(STATE_LABELS.get(item["state"], "لم تتم الإجابة"))} · '
                    f'التوجه: {_e(item["target"] or "لم يُحدد")} · {_e(item["owner"])}</p>'
                    f'<p>{_e(item["target_note"] or item["issues"] or "[لا يوجد تصور بعد]")}</p></div>')
    return "".join(html)


def _na(module, items):
    html = [module_header(module, "na")]
    rel = [i for i in items if i["state"] == "na"]
    if not rel:
        return html[0] + note("لا توجد متطلبات معلنة «لا ينطبق».")
    html.append(note("كل متطلب «لا ينطبق» يُراجع ولا يُستبعد تلقائيًا."))
    html.append("<ul>")
    html += [f"<li><b>{_e(i['code'])} · {_e(i['title'])}</b> — {_e(i['reason'] or '[لم يُذكر سبب]')}</li>" for i in rel]
    html.append("</ul>")
    return "".join(html)


def stats(items):
    count = {k: sum(1 for i in items if i["state"] == k) for k in STATE_LABELS}
    return {"total": len(items), "done": sum(1 for i in items if i["done"]),
            "questions": sum(i["q_total"] for i in items), "answered": sum(i["q_answered"] for i in items),
            **count, "open": sum(1 for i in items if not i["state"])}


def _coverage(module, items):
    s = stats(items)
    html = [module_header(module, "coverage"),
            '<div class="o_azm_stats">'
            f'<div><b>{s["answered"]}/{s["questions"]}</b><span>سؤال مُجاب</span></div>'
            f'<div><b>{s["done"]}/{s["total"]}</b><span>متطلب مكتمل</span></div>'
            f'<div><b>{s["full"]}</b><span>مطبّق بالكامل</span></div>'
            f'<div><b>{s["partial"]}</b><span>مطبّق جزئيًا</span></div>'
            f'<div><b>{s["unavailable"]}</b><span>غير منفذ</span></div></div>']
    rows = []
    for tab, title in OUTPUT_TABS:
        if tab in TAB_PROFILES:
            rel = [i for i in items if i["profile"] in TAB_PROFILES[tab]]
            ready = [i for i in rel if i["state"] in ("full", "partial") and i["qa"]]
            rows.append(f"<tr><th>{_e(title)}</th><td>{len(ready)}/{len(rel)}</td></tr>")
    html.append('<table class="o_azm_table"><thead><tr><th>المخرج</th><th>متطلبات جاهزة للصياغة</th></tr></thead>'
                f'<tbody>{"".join(rows)}</tbody></table>')
    return "".join(html)


RENDERERS = {"book": _book, "gaps": _gaps, "future": _future, "na": _na, "coverage": _coverage}


def render_module(tab, module, items):
    if tab in TAB_PROFILES:
        return _by_profile(tab, module, items)
    return RENDERERS.get(tab, _book)(module, items)


def render_model(tab, data):
    """data = [(module, items)] for the whole model."""
    title = dict(OUTPUT_TABS).get(tab, "")
    html = [f'<h3>{_e(title)} · النموذج المالي الموحد</h3>']
    for module, items in data:
        if items:
            html.append(render_module(tab, module, items))
    return "".join(html)


def module_map(nav):
    """Overview of the modules (like the procurement cycle map)."""
    cards = []
    for m in nav:
        if m["applicable"] == 0:
            cls, label = "o_none", "غير منطبق"
        elif m["done"] == m["applicable"]:
            cls, label = "o_full", "مكتمل"
        elif m["answered"]:
            cls, label = "o_partial", "قيد الحصر"
        else:
            cls, label = "o_open", "لم يبدأ"
        gap = f'<span class="o_azm_fin_mapgap">{m["gaps"]}</span>' if m["gaps"] else ""
        cards.append(f'<div class="o_azm_fin_mapcard {cls}">{gap}<span class="o_azm_fin_mapcode">FIN.{_e(m["code"])}</span>'
                     f'<b>{_e(m["name"])}</b><span class="o_azm_muted">{m["answered"]}/{m["questions"]} سؤال · '
                     f'{m["done"]}/{m["applicable"]} متطلب · {label}</span></div>')
    return ('<h3>خريطة النموذج المالي الموحد</h3>'
            f'<p class="o_azm_muted">{len(nav)} موديولًا · الرقم الأحمر = فجوات (جزئي أو غير منفذ)</p>'
            f'<div class="o_azm_fin_map">{"".join(cards)}</div>')
