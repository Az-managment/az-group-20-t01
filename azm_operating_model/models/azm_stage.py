import json

from odoo import api, fields, models
from odoo.tools import file_open

KIND_BY_NAME = {"لا أعرف": "unknown", "غير مدرج": "not_listed", "لا يوجد": "none", "لا ينطبق": "na"}


class AzmStage(models.Model):
    _name = "azm.stage"
    _description = "AZM Cycle Stage"
    _order = "sequence, id"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    sequence = fields.Integer(default=10)
    input_desc = fields.Char("المدخل", translate=True)
    output_desc = fields.Char("المخرج", translate=True)
    default_owner = fields.Char("المالك المعتاد", translate=True)
    is_governance = fields.Boolean("مرحلة حوكمة")
    question_ids = fields.One2many("azm.question", "stage_id", string="الأسئلة")
    question_count = fields.Integer(compute="_compute_question_count")
    risk_rule_ids = fields.One2many("azm.risk.rule", "stage_id", string="قواعد المخاطر")
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint("UNIQUE(code)", "كود المرحلة لازم يكون فريد.")

    def _compute_question_count(self):
        counts = dict(self.env["azm.question"]._read_group(
            [("stage_id", "in", self.ids)], ["stage_id"], ["__count"]))
        for stage in self:
            stage.question_count = counts.get(stage, 0)

    def _engine_dict(self):
        self.ensure_one()
        return {
            "id": self.id, "code": self.code, "name": self.name, "input": self.input_desc or "",
            "output": self.output_desc or "", "owner": self.default_owner or "",
            "governance": self.is_governance,
        }

    # ------------------------------------------------------------ catalogue
    @api.model
    def _load_catalogue(self):
        """Create or update stages, questions, options and risk rules from
        data/catalogue.json. Idempotent: existing records are matched by code/key,
        records edited in the UI keep their id, and nothing answered is deleted."""
        with file_open("azm_operating_model/data/catalogue.json", "rb") as f:
            cat = json.load(f)
        unknown, not_listed = cat["unknown"], cat["not_listed"]
        ops = [s for s in cat["stages"] if not s.get("governance")]
        routes = [f"{s['id']} · {s['name']}" for s in ops] + cat["route_extra"] + [unknown, not_listed]
        lists = {"@R": cat["roles"], "@D": cat["docs"], "@T": routes}

        # entities are the companies of Odoo (azm.entity._azm_sync_companies), not part of the catalogue
        Question = self.env["azm.question"].with_context(active_test=False)
        Option = self.env["azm.option"].with_context(active_test=False)
        stages = {}
        for seq, s in enumerate(cat["stages"], 1):
            vals = {
                "name": s["name"], "sequence": seq * 10, "input_desc": s["input"],
                "output_desc": s["output"], "default_owner": s["owner"],
                "is_governance": bool(s.get("governance")),
            }
            stage = self.with_context(active_test=False).search([("code", "=", s["id"])])
            if stage:
                stage.write(vals)
            else:
                stage = self.create({"code": s["id"], **vals})
            stages[s["id"]] = stage
            fields_def = list(s["fields"]) if s.get("governance") else (
                [{**c, "is_common": True} for c in cat["common"]]
                + [{**f, "group": 0} for f in s["fields"]])
            for qseq, fd in enumerate(fields_def, 1):
                options = fd.get("options")
                is_role = options == "@R"
                if isinstance(options, str):
                    options = lists[options]
                elif options and fd.get("um"):
                    options = options + [unknown, not_listed]
                qvals = {
                    "label": fd["label"], "clause": fd["clause"],
                    "qtype": fd.get("type", "select"), "group": str(fd.get("group", 0)),
                    "sequence": qseq, "is_common": bool(fd.get("is_common")),
                    "is_role": is_role, "raci": fd.get("raci") or False,
                    "condition": json.dumps(fd["when"], ensure_ascii=False) if fd.get("when") else False,
                }
                question = Question.search([("stage_id", "=", stage.id), ("key", "=", fd["id"])])
                if question:
                    question.write(qvals)
                else:
                    question = Question.create({"stage_id": stage.id, "key": fd["id"], **qvals})
                existing = {o.name: o for o in question.option_ids}
                for oseq, name in enumerate(options or [], 1):
                    ovals = {"sequence": oseq, "kind": KIND_BY_NAME.get(name, "normal"), "active": True}
                    if name in existing:
                        existing[name].write(ovals)
                    else:
                        Option.create({"question_id": question.id, "name": name, **ovals})
                stale = [o for n, o in existing.items() if n not in (options or [])]
                if stale:
                    Option.browse([o.id for o in stale]).write({"active": False})

        Rule = self.env["azm.risk.rule"].with_context(active_test=False)
        counter = {}
        for stage_code, key, trigger, fact, risk, control, owner in cat["rules"]:
            counter[(stage_code, key)] = counter.get((stage_code, key), 0) + 1
            code = f"R-{stage_code}-{key}" + (f"-{counter[(stage_code, key)]}" if counter[(stage_code, key)] > 1 else "")
            stage = stages[stage_code]
            question = Question.search([("stage_id", "=", stage.id), ("key", "=", key)])
            option = question.option_ids.filtered(lambda o, t=trigger: o.name == t)[:1]
            if not option:
                continue
            vals = {"stage_id": stage.id, "question_id": question.id, "trigger_option_id": option.id,
                    "fact": fact, "risk": risk, "control": control, "owner_hint": owner}
            rule = Rule.search([("code", "=", code)])
            if rule:
                rule.write(vals)
            else:
                Rule.create({"code": code, **vals})
        return True

    def action_reload_catalogue(self):
        self._load_catalogue()
        return {"type": "ir.actions.client", "tag": "display_notification",
                "params": {"type": "success", "message": "تم تحديث كتالوج الأسئلة."}}
