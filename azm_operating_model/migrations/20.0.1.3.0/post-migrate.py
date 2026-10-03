from odoo import SUPERUSER_ID, api

STATUS = {"full": "مطبق بالكامل", "partial": "مطبق جزئيًا", "unavailable": "غير منفذ"}
IMPL = {"نظام": ["النظام الحالي"], "يدوي": ["يدوي أو ورقي"], "Excel": ["Excel"], "مختلط": ["النظام الحالي", "Excel"]}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {"azm_skip_lock": True, "tracking_disable": True})
    env["azm.fin.module"]._load_catalogue()
    env["azm.fin.assessment"].search([])._ensure_answers()

    cr.execute("SELECT to_regclass('azm_fin_answer_legacy')")
    if not cr.fetchone()[0]:
        return
    cr.execute("SELECT id, state, impl, current, gap, future, reason FROM azm_fin_answer_legacy")
    rows = cr.fetchall()
    Line = env["azm.fin.answer"]
    QA = env["azm.fin.qanswer"]
    creates = []
    for line_id, state, impl, current, gap, future, reason in rows:
        line = Line.browse(line_id).exists()
        if not line or line.qanswer_ids:
            continue
        if state == "na":
            line.write({"na": True, "reason": reason or "لا ينطبق (منقول من الإصدار السابق)."})
            continue
        questions = {q.role: q for q in line.requirement_id.question_ids if q.role in ("status", "impl", "target")}
        status = questions.get("status")
        if not status or state not in STATUS:
            continue
        option = status.option_ids.filtered(lambda o: o.name == STATUS[state])[:1]
        note = "\n".join(x for x in (current, f"الفجوة: {gap}" if gap else "") if x)
        creates.append({"line_id": line.id, "question_id": status.id, "option_id": option.id, "note": note or False})
        if impl and "impl" in questions and state in ("full", "partial"):
            names = {n for part in impl.split(",") for n in IMPL.get(part.strip(), [])}
            opts = questions["impl"].option_ids.filtered(lambda o: o.name in names)
            if opts:
                creates.append({"line_id": line.id, "question_id": questions["impl"].id, "option_ids": [(6, 0, opts.ids)]})
        if future and "target" in questions:
            creates.append({"line_id": line.id, "question_id": questions["target"].id, "note": future})
    QA.create(creates)
    lines = Line.search([])
    lines._compute_from_questions()
    lines.flush_recordset()
    cr.execute("DROP TABLE azm_fin_answer_legacy")
