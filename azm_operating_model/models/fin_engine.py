"""Rendering of the unified financial model outputs.

Pure functions over plain dicts (no ORM) so the workspace, the form and the
approved snapshot all show the same document. HTML uses the same classes as
the procurement operating model (azm_output.scss) so both models look alike.

module = {"code", "name"}
item   = {"code", "title", "question", "profile", "profile_name", "scope_name", "state",
          "impl", "current", "gap", "future", "reason", "table", "branches",
          "columns", "branch_defs", "done"}
"""

import re
from html import escape

STATE_LABELS = {
    "full": "مطبّق بالكامل",
    "partial": "مطبّق جزئيًا",
    "unavailable": "غير متاح حاليًا",
    "na": "لا ينطبق",
}

# One output per answer template, so nothing is answered into a document that
# never shows it. «حصر مرجعي» used to have no tab at all, and «قاعدة حساب» and
# «سياسة وتوقيت» shared one even though they are different templates.
OUTPUT_TABS = [
    ("book", "الوضع الحالي"),
    ("lists", "القوائم المرجعية"),
    ("calc", "قواعد الاحتساب"),
    ("policies", "السياسات والتوقيت"),
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
    "lists": ("L",),
    "calc": ("C",),
    "policies": ("P",),
    "workflow": ("W",),
    "authority": ("A",),
    "reports": ("R",),
    "integration": ("I",),
}
DOC_CODES = {"book": "CS-FIN", "lists": "CS-LST", "calc": "CS-CALC", "policies": "CS-POL",
             "workflow": "CS-WF", "authority": "CS-AUTH",
             "reports": "CS-RPT", "integration": "CS-INT", "gaps": "CS-GAP", "future": "CS-TOM",
             "na": "CS-NA", "coverage": "CS-COV"}
ROLE_COLUMNS = ("المنشئ", "المنفّذ", "المراجع", "المعتمد")
# The value of «التعارض» that means the conflict is still open. The other
# values («لا يوجد», «يوجد ومقبول برقابة بديلة») need no warning.
CONFLICT_UNRESOLVED = "يوجد ويحتاج معالجة"


# A grid cell is typed from its column: a listed column is a dropdown, a date
# column gets a date picker, everything else stays free text. «التاريخ/الفترة»
# deliberately stays text, because it also accepts a period such as "الربع الأول",
# which a date picker could not express.
DATE_LABEL_RE = re.compile(r"تاريخ|موعد|مهلة")
PERIOD_LABEL_RE = re.compile(r"فترة")


def column_type(label, options):
    if options:
        return "select"
    label = label or ""
    if DATE_LABEL_RE.search(label) and not PERIOD_LABEL_RE.search(label):
        return "date"
    return "text"


# Columns the catalogue leaves as free text although they answer with a known
# vocabulary. Applied only when the column does not already carry its own list.
# «الوحدة» is drawn from the units the questionnaire itself uses (يوم، يوم عمل،
# شهر، سنة، درجة، مستوى، قسط، راتب شهري، موظف، %) plus the الوحدة الزمنية list
# already in the catalogue. Currency is deliberately absent: the calculation
# grid carries a separate العملة column.
COLUMN_VOCABULARY = {
    "الوحدة": [
        "نسبة مئوية", "مبلغ", "يوم", "يوم عمل", "أسبوع", "شهر", "ربع سنة", "سنة",
        "موظف", "درجة", "مستوى", "قسط", "راتب شهري", "أخرى",
    ],
}


# Columns that answer with a recognisable vocabulary but must stay open, because
# the cell holds real content a fixed list could not express: a formula, a named
# source, the wording of an exception. These render as a text box WITH a
# dropdown of suggestions, so the list is offered and anything else is still
# typeable.
COLUMN_SUGGESTIONS = {
    # the shape is already a list in «أساس الحساب»; this cell holds the formula
    "المعادلة أو الشرائح": [
        "نسبة ثابتة", "شرائح تصاعدية", "شرائح تنازلية", "معادلة مركّبة",
        "مبلغ مقطوع", "جدول مرجعي",
    ],
    # the generic parts a calculation is built from; a rule-specific name is
    # still typeable, because every rule computes something different
    "المكوّن": [
        "المبلغ الأساسي", "النسبة", "الحد الأدنى", "الحد الأقصى", "الشريحة",
        "معامل التعديل", "البدل", "الخصم", "الضريبة", "الرسوم", "العمولة",
        "الفائدة", "القسط",
    ],
    "المصدر": ["النظام", "ملف Excel", "إدخال يدوي", "تكامل مع نظام آخر", "جهة خارجية"],
    # Workflow grid. The steps of a cycle are specific to it — the sheet gives
    # each requirement its own list — so these are the generic verbs and
    # artifacts a step is built from, offered and still typeable.
    "الخطوة/الحدث": [
        "طلب", "مراجعة", "اعتماد", "تنفيذ", "تسجيل", "مطابقة", "إشعار",
        "تسوية", "أرشفة", "إقفال",
    ],
    "المدخل": [
        "طلب", "نموذج معتمد", "مستند مؤيد", "عقد", "فاتورة", "أمر شراء",
        "كشف حساب", "بيانات من نظام آخر",
    ],
    "المخرج": [
        "موافقة", "أمر شراء", "قيد محاسبي", "سند صرف", "سند قبض", "تقرير",
        "إشعار", "ملف مرحّل", "مستند مؤرشف",
    ],
    "المدة": [
        "فوري", "نفس اليوم", "يوم عمل", "يوما عمل", "٣ أيام عمل", "أسبوع",
        "أسبوعان", "شهر",
    ],
    "الاستثناء": ["لا يوجد", "بموافقة المدير المالي", "بموافقة الإدارة العليا", "حسب السياسة"],
    "التفويض": ["مسموح", "غير مسموح", "مسموح بحدود"],
    "التعارض": ["لا يوجد", "يوجد ومقبول برقابة بديلة", "يوجد ويحتاج معالجة"],
    # حصر مرجعي
    "الاستخدام": ["تقارير داخلية", "تقارير قانونية", "الموازنة", "التحليل",
                  "الإقفال", "الرقابة", "التسعير"],
    # سياسة وتوقيت — the cell takes a date OR a period, so both are offered
    "التاريخ/الفترة": ["بداية السنة المالية", "نهاية الشهر", "نهاية الربع",
                        "نهاية السنة", "شهري", "ربع سنوي", "سنوي", "تاريخ محدد"],
    "الأثر على التشغيل والتسجيل": ["يوقف العملية", "يؤخر التسجيل",
                                     "يتطلب موافقة إضافية", "يتطلب قيد تسوية", "لا أثر"],
    # تقرير أو مؤشر — the dimensions are the reporting levels the model names
    # in FIN-001 (الكيان، الفرع، الكلية، البرنامج، الإدارة، المشروع، النشاط)
    "الغرض": ["متابعة تشغيلية", "رقابة داخلية", "إفصاح قانوني", "دعم قرار",
               "تحليل أداء", "متابعة موازنة"],
    "الأبعاد": ["الكيان", "الفرع", "الكلية", "البرنامج", "الإدارة", "المشروع",
                 "النشاط", "مركز التكلفة", "الفترة"],
    "الفلاتر": ["الفترة", "الكيان", "الحالة", "النوع", "المسؤول", "مركز التكلفة"],
    # تكامل أو ترحيل
    "الوجهة": ["النظام المالي", "نظام الرواتب", "نظام المخزون", "نظام الطلاب",
                "نظام الأصول", "جهة خارجية", "ملف"],
    "الحدث": ["إنشاء", "تعديل", "اعتماد", "إلغاء", "ترحيل دوري", "عند الطلب"],
    "قاعدة المطابقة": ["مطابقة بالمعرف", "مطابقة بالرقم المرجعي",
                        "مطابقة بالمبلغ والتاريخ", "مطابقة يدوية"],
    # صلاحيات ورقابة — «العملية» reuses the نوع العملية list the sheet already
    # gives on FIN-004, rather than a parallel invention
    "العملية": ["قيد يومية", "طلب شراء", "أمر شراء", "فاتورة مورد", "سند صرف",
                 "سند قبض", "تسوية بنكية", "تعديل موازنة", "إضافة أصل", "كشف رواتب"],
    "النطاق/الشريحة": ["كل المبالغ", "حتى حد معين", "أعلى من حد معين",
                        "حسب النوع", "حسب الكيان"],
    "دليل الرقابة": ["سجل النظام", "توقيع إلكتروني", "مستند ورقي",
                      "تقرير دوري", "مراجعة لاحقة"],
    "الجهة المستفيدة": [
        "الإدارة المالية", "الإدارة العليا", "مجلس الإدارة", "جهة رقابية",
        "جهة حكومية", "المراجع الخارجي",
    ],
}


def typed_columns(columns):
    """Return the columns with the widget each one should use."""
    typed = []
    for column in columns or []:
        label = (column.get("label") or "").strip()
        options = column.get("options") or COLUMN_VOCABULARY.get(label)
        kind = column_type(label, options)
        suggestions = None
        if kind == "text" and label in COLUMN_SUGGESTIONS:
            kind, suggestions = "suggest", COLUMN_SUGGESTIONS[label]
        typed.append(dict(column, options=options, suggestions=suggestions, type=kind))
    return typed


def _e(text):
    return escape(str(text or ""), quote=True)


def note(text, kind="info"):
    cls = "o_azm_note o_azm_note_warn" if kind == "warn" else "o_azm_note"
    return f'<div class="{cls}">{_e(text)}</div>'


def module_header(module, tab):
    return (f'<div class="o_azm_stage_head"><span class="o_azm_code">FIN-{_e(module["code"])}</span>'
            f'<h3>{_e(module["name"])}</h3></div>'
            f'<div class="o_azm_doc_code">{DOC_CODES.get(tab, "CS")}-{_e(module["code"])}</div>')


def _rows(item):
    """Non-empty rows of the answer table."""
    return [row for row in item.get("table") or [] if any((c or "").strip() for c in row)]


def render_table(columns, rows):
    if not rows:
        return ""
    head = "".join(f"<th>{_e(c['label'])}</th>" for c in columns)
    body = "".join(
        "<tr>" + "".join(f"<td>{_e(row[i] if i < len(row) else '')}</td>" for i in range(len(columns))) + "</tr>"
        for row in rows)
    return f'<table class="o_azm_table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def _branches(item):
    out = []
    for i, b in enumerate(item.get("branch_defs") or []):
        values = item.get("branches") or []
        value = values[i] if i < len(values) else ""
        if value:
            out.append(f"<li>{_e(b['title'])}: {_e(value)}"
                       + (f" — يتطلب: {_e('، '.join(b.get('reveals') or []))}" if b.get("reveals") else "") + "</li>")
    return f'<ul class="o_azm_facts">{"".join(out)}</ul>' if out else ""


def _source(item):
    return f'<span class="o_azm_source">مصدر الصياغة · {_e(item["code"])}</span>'


def _state_line(item):
    impl = "، ".join(item.get("impl") or [])
    parts = [f"حالة التطبيق: {STATE_LABELS.get(item['state'], 'لم تتم الإجابة')}"]
    if impl:
        parts.append(f"طريقة التنفيذ: {impl}")
    return f'<p class="o_azm_muted">{_e(" · ".join(parts))}</p>'


# ---------------------------------------------------------------- per tab
def _book(module, items):
    html = [module_header(module, "book")]
    answered = [i for i in items if i["state"]]
    missing = [i for i in items if not i["state"]]
    for item in answered:
        body = [f'<h4>{_e(item["title"])} <span class="o_azm_code">{_e(item["code"])}</span></h4>', _state_line(item)]
        text = {"full": item["current"], "partial": item["current"], "unavailable": item["future"],
                "na": item["reason"]}[item["state"]]
        if text:
            body.append(f"<p>{_e(text)}</p>")
        if item["state"] == "partial" and item["gap"]:
            body.append(f'<p class="o_azm_muted">الفجوة: {_e(item["gap"])}</p>')
        if item["state"] in ("full", "partial"):
            body.append(render_table(item["columns"], _rows(item)))
        body.append(_branches(item))
        body.append(_source(item))
        html.append(f'<div class="o_azm_section">{"".join(body)}</div>')
    if missing:
        html.append(f"<h4>لم تتم الإجابة ({len(missing)})</h4><ul>")
        html += [f"<li>{_e(i['code'])} · {_e(i['title'])}</li>" for i in missing]
        html.append("</ul>")
    if not items:
        html.append(note("لا توجد متطلبات منطبقة في هذا الموديول."))
    return "".join(html)


def _by_profile(tab, module, items):
    profiles = TAB_PROFILES[tab]
    rel = [i for i in items if i["profile"] in profiles]
    html = [module_header(module, tab)]
    if not rel:
        return html[0] + note("لا توجد متطلبات من هذا النوع في الموديول.")
    for item in rel:
        if item["state"] not in ("full", "partial"):
            label = STATE_LABELS.get(item["state"], "لم تتم الإجابة")
            html.append(f'<div class="o_azm_section"><h4>{_e(item["title"])} <span class="o_azm_code">{_e(item["code"])}</span></h4>'
                        f'<p class="o_azm_muted">[{_e(label)}] — لا توجد قاعدة قائمة تُكتب في هذا المخرج.</p></div>')
            continue
        rows = _rows(item)
        body = [f'<h4>{_e(item["title"])} <span class="o_azm_code">{_e(item["code"])}</span></h4>']
        if item["current"]:
            body.append(f"<p>{_e(item['current'])}</p>")
        if tab == "workflow" and rows:
            cols = item["columns"]
            steps = []
            for row in rows:
                head = row[0] if row else ""
                rest = " · ".join(f"{cols[i]['label']}: {row[i]}" for i in range(1, min(len(cols), len(row))) if row[i])
                steps.append(f"<li><b>{_e(head or '[لم يُحدد]')}</b><br/><span class='o_azm_muted'>{_e(rest)}</span></li>")
            body.append(f'<ol class="o_azm_steps">{"".join(steps)}</ol>')
        else:
            body.append(render_table(item["columns"], rows))
        if tab == "authority":
            idx = {c["label"]: n for n, c in enumerate(item["columns"])}

            def cell(row, label):
                position = idx.get(label)
                return row[position] if position is not None and position < len(row) else ""

            for row in rows:
                roles = [cell(row, name) for name in ROLE_COLUMNS if cell(row, name)]
                where = row[0] or item["title"]
                if len(roles) != len(set(roles)):
                    body.append(note(f"نفس الدور يظهر في أكثر من مهمة في «{where}» — راجع الفصل بين المهام.", "warn"))
                # a conflict the entity declared itself, which the duplication
                # check above cannot see: the roles may all differ and the
                # conflict still be real
                if cell(row, "التعارض") == CONFLICT_UNRESOLVED:
                    body.append(note(f"تعارض معلن لم يُعالج في «{where}».", "warn"))
                # an authority with no evidence behind it is an authority
                # nobody can audit
                if not cell(row, "دليل الرقابة"):
                    body.append(note(f"لا يوجد دليل رقابة مسجّل لـ «{where}».", "info"))
        if item["state"] == "partial" and item["gap"]:
            body.append(note(f"فجوة: {item['gap']}", "warn"))
        body.append(_branches(item))
        body.append(_source(item))
        html.append(f'<div class="o_azm_section">{"".join(body)}</div>')
    return "".join(html)


def _gaps(module, items):
    html = [module_header(module, "gaps")]
    rel = [i for i in items if i["state"] == "partial"]
    if not rel:
        return html[0] + note("لا توجد فجوات مسجلة في هذا الموديول.")
    for item in rel:
        html.append(
            f'<div class="o_azm_risk"><span class="o_azm_code">{_e(item["code"])}</span>'
            f'<h4>{_e(item["title"])}</h4><div class="o_azm_chain">'
            f'<span><b>المطبّق حاليًا:</b> {_e(item["current"] or "[لم يُحدد]")}</span>'
            f'<span><b>الفجوة وأثرها:</b> {_e(item["gap"] or "[لم يُحدد]")}</span>'
            f'<span><b>قالب الإجابة:</b> {_e(item["profile_name"])}</span></div></div>')
    return "".join(html)


def _future(module, items):
    html = [module_header(module, "future")]
    rel = [i for i in items if i["state"] in ("unavailable", "partial")]
    if not rel:
        return html[0] + note("لا توجد متطلبات تحتاج تصميمًا مستهدفًا في هذا الموديول.")
    for item in rel:
        text = item["future"] if item["state"] == "unavailable" else f"معالجة الفجوة: {item['gap']}"
        html.append(f'<div class="o_azm_section"><h4>{_e(item["title"])} <span class="o_azm_code">{_e(item["code"])}</span></h4>'
                    f'<p class="o_azm_muted">{_e(STATE_LABELS[item["state"]])} · {_e(item["profile_name"])}</p>'
                    f'<p>{_e(text or "[لا يوجد تصور بعد]")}</p></div>')
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
    total = len(items)
    count = {k: sum(1 for i in items if i["state"] == k) for k in STATE_LABELS}
    done = sum(1 for i in items if i["done"])
    return {"total": total, "done": done, **count, "open": sum(1 for i in items if not i["state"])}


def _coverage(module, items):
    s = stats(items)
    html = [module_header(module, "coverage"),
            '<div class="o_azm_stats">'
            f'<div><b>{s["done"]}/{s["total"]}</b><span>متطلب مكتمل الإجابة</span></div>'
            f'<div><b>{s["full"]}</b><span>مطبّق بالكامل</span></div>'
            f'<div><b>{s["partial"]}</b><span>مطبّق جزئيًا</span></div>'
            f'<div><b>{s["unavailable"]}</b><span>غير متاح حاليًا</span></div></div>']
    rows = []
    for tab, title in OUTPUT_TABS:
        if tab in TAB_PROFILES:
            rel = [i for i in items if i["profile"] in TAB_PROFILES[tab]]
            ready = [i for i in rel if i["state"] in ("full", "partial") and (i["current"] or _rows(i))]
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
    """Overview of the 17 modules (like the procurement cycle map)."""
    cards = []
    for m in nav:
        if m["applicable"] == 0:
            cls, label = "o_none", "غير منطبق"
        elif m["done"] == m["applicable"]:
            cls, label = "o_full", "مكتمل"
        elif m["done"]:
            cls, label = "o_partial", "قيد الحصر"
        else:
            cls, label = "o_open", "لم يبدأ"
        gap = f'<span class="o_azm_fin_mapgap">{m["gaps"]}</span>' if m["gaps"] else ""
        cards.append(f'<div class="o_azm_fin_mapcard {cls}">{gap}<span class="o_azm_fin_mapcode">FIN-{_e(m["code"])}</span>'
                     f'<b>{_e(m["name"])}</b><span class="o_azm_muted">{m["done"]}/{m["applicable"]} · {label}</span></div>')
    return ('<h3>خريطة النموذج المالي الموحد</h3>'
            '<p class="o_azm_muted">17 موديولًا · الرقم الأحمر = فجوات (جزئي أو غير متاح)</p>'
            f'<div class="o_azm_fin_map">{"".join(cards)}</div>')
