"""Helpers shared by the financial-model tests.

Answering is done the way the workspace does it — one question at a time through
``azm.fin.answer._set_answer`` — because answering a trigger may reveal a
follow-up, and only the server knows which.
"""

from odoo.addons.azm_operating_model.models.azm_fin_catalogue import FALLBACK_KINDS

FULL = "مطبق بالكامل"


def real_options(question):
    """The options that answer the question, excluding «لا أعرف» and friends."""
    return question.option_ids.filtered(lambda o: o.kind not in FALLBACK_KINDS)


def cell_value(column, token):
    """A value a grid cell will accept, honouring what the column says it holds."""
    if column.get("options"):
        return column["options"][0]
    return {"date": "2026-01-01", "number": "10"}.get(column.get("type"), token)


def answer_for(question, token):
    """A plausible answer for one question, in ``_set_answer`` form."""
    options = real_options(question)
    if question.qtype == "number":
        return {"number": 1}
    if question.qtype == "table":
        return {"table": [[cell_value(c, token) for c in question._columns()]]}
    if question.qtype == "multi":
        return {"option_ids": options[:1].ids}
    if question.role == "status":
        return {"option_id": (options.filtered(lambda o: o.name == FULL) or options)[:1].id}
    return {"option_id": options[:1].id}


def fill(line, token="قيمة"):
    """Answer every visible question of a requirement, following the reveals.

    Loops because answering the status question uncovers the three standard
    scales, which were not visible when the walk started.
    """
    for _ in range(8):
        answered = {qa.question_id.id for qa in line.qanswer_ids if qa.is_answered}
        todo = line._visible().filtered(lambda q: q.id not in answered)
        if not todo:
            break
        for question in todo:
            line._set_answer(question.id, answer_for(question, token))
    return line


def table_question(line):
    """The requirement's grid, i.e. the one the output documents render."""
    return line.requirement_id.question_ids.filtered(lambda q: q.qtype == "table")[:1]


def columns_of(line):
    question = table_question(line)
    return question._columns() if question else []
