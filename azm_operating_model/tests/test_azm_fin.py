import json

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.azm_operating_model.models import fin_engine


@tagged("post_install", "-at_install")
class TestAzmFinancialModel(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Scope = cls.env["azm.fin.scope"]
        cls.edu, cls.work, cls.prj = (Scope.search([("code", "=", c)]) for c in ("EDU", "WORK", "PRJ"))
        cls.entity = cls.env["azm.entity"].create({"code": "FTA", "name": "كيان مالي أ",
                                                   "fin_scope_ids": [(6, 0, (cls.edu | cls.work).ids)]})
        cls.other = cls.env["azm.entity"].create({"code": "FTB", "name": "كيان مالي ب"})
        cls.preparer = new_test_user(cls.env, "fin_prep", groups="azm_operating_model.azm_group_user")
        cls.preparer_b = new_test_user(cls.env, "fin_prep_b", groups="azm_operating_model.azm_group_user")
        cls.reviewer = new_test_user(cls.env, "fin_rev", groups="azm_operating_model.azm_group_reviewer")
        cls.manager = new_test_user(cls.env, "fin_mgr", groups="azm_operating_model.azm_group_manager")
        cls.entity.user_ids = [(6, 0, [cls.preparer.id, cls.reviewer.id])]
        cls.other.user_ids = [(6, 0, [cls.preparer_b.id])]
        cls.assessment = cls.env["azm.fin.assessment"].with_user(cls.preparer).create(
            {"entity_id": cls.entity.id, "reviewer_id": cls.reviewer.id})

    def _line(self, code, assessment=None):
        return (assessment or self.assessment).answer_ids.filtered(lambda a: a.code == code)

    def _q(self, line, key):
        return line.requirement_id.question_ids.filtered(lambda q: q.key == key)

    def _opt(self, question, name):
        return question.option_ids.filtered(lambda o: o.name == name)

    def test_catalogue_matches_workbook(self):
        env = self.env
        self.assertEqual(env["azm.fin.module"].search_count([]), 19)
        self.assertEqual(env["azm.fin.topic"].search_count([]), 215)
        self.assertEqual(env["azm.fin.requirement"].search_count([]), 167)
        self.assertEqual(env["azm.fin.requirement"].search_count([("source", "=", "HRF")]), 60)
        self.assertEqual(env["azm.fin.prompt"].search_count([]), 3655)
        Question = env["azm.fin.question"]
        self.assertEqual(Question.search_count([]), 1136)
        counts = {t: Question.search_count([("qtype", "=", t)]) for t in ("select", "multi", "table", "number")}
        self.assertEqual(counts, {"select": 791, "multi": 244, "table": 53, "number": 48})
        self.assertEqual(Question.search_count([("role", "=", "status")]), 167)
        # every question carries its own answer data
        for q in Question.search([]):
            if q.qtype in ("select", "multi"):
                self.assertTrue(q.option_ids, q.code)
            if q.qtype == "table":
                self.assertTrue(q._columns(), q.code)
            if q.qtype == "number":
                self.assertTrue(q.unit, q.code)
            cond = q._condition()
            if cond:
                ref = q.requirement_id.question_ids.filtered(lambda x, k=cond["q"]: x.key == k)
                self.assertTrue(ref and ref.sequence < q.sequence, q.code)
                self.assertLessEqual(set(cond["in"]), set(ref.option_ids.mapped("name")), q.code)
        self.assertEqual(Question.search_count([("condition_json", "!=", False)]), 519)
        self.assertEqual(len(self.assessment.answer_ids), 167)
        # reloading is idempotent
        before = env["azm.fin.option"].search_count([])
        env["azm.fin.module"]._load_catalogue()
        self.assertEqual(env["azm.fin.option"].search_count([]), before)

    def test_applicability_follows_activities(self):
        self.assertEqual(self.assessment.scope_ids, self.edu | self.work)
        self.assertTrue(self._line("FIN-024").applicable)     # EDU
        self.assertTrue(self._line("HRF-006").applicable)     # WORK
        self.assertFalse(self._line("FIN-062").applicable)    # PRJ
        self.assessment.scope_ids = [(4, self.prj.id)]
        self.assertTrue(self._line("FIN-062").applicable)
        data = self.assessment.workspace_data("PRJ")
        reqs = [r for t in data["topics"] for r in t["requirements"]]
        self.assertEqual(len(reqs), len(self.assessment.answer_ids.filtered(
            lambda a: a.module_id.code == "PRJ" and a.applicable)))
        self.assertTrue(all(t["prompts"] for t in data["topics"]))

    def test_questions_conditions_and_outputs(self):
        a = self.assessment.with_user(self.preparer)
        line = self._line("FIN-004")
        main, table, status, impl, rule, target = (self._q(line, k) for k in ("Q001", "Q002", "Q003", "Q004", "Q005", "Q006"))
        # only the requirement questions and the status question show before the status is answered
        self.assertEqual(set(line._visible().mapped("key")), {"Q001", "Q002", "Q003"})
        a.workspace_answer(line.id, main.id, {"option_id": self._opt(main, "مصفوفة تفويض معتمدة").id})
        res = a.workspace_answer(line.id, status.id, {"option_id": self._opt(status, "مطبق جزئيًا").id,
                                                      "note": "المصفوفة لا تغطي الرواتب"})
        visible = {q["key"] for q in res["requirement"]["questions"] if q["visible"]}
        self.assertEqual(visible, {"Q001", "Q002", "Q003", "Q004", "Q005", "Q006"})
        self.assertEqual((line.state, line.gap), ("partial", "المصفوفة لا تغطي الرواتب"))
        self.assertFalse(line.is_done)
        a.workspace_answer(line.id, table.id, {"table": [["قيد يومية", "محاسب", "رئيس الحسابات", "محاسب", "50000"]]})
        a.workspace_answer(line.id, impl.id, {"option_ids": self._opt(impl, "SAP").ids})
        a.workspace_answer(line.id, rule.id, {"option_id": self._opt(rule, "مطبقة دون توثيق").id})
        res = a.workspace_answer(line.id, target.id, {"option_id": self._opt(target, "تحسين").id,
                                                      "note": "تحديث المصفوفة"}, module_code="GOV", tab="authority")
        self.assertTrue(res["requirement"]["done"])
        self.assertEqual((line.q_answered, line.q_total, line.impl, line.target), (6, 6, "SAP", "تحسين"))
        self.assertIn("محاسب", res["output"])
        self.assertIn("الفصل بين المهام", res["output"])   # creator == approver
        # the text boxes are answered from lists (+ priority); unknown items are ignored
        a.workspace_answer(line.id, target.id, {"note_tags": ["أتمتة العملية في النظام", "قيمة غير موجودة"],
                                                "priority": "high"})
        self.assertEqual(line.target_note, "أتمتة العملية في النظام — الأولوية: مرتفعة")
        a.workspace_answer(line.id, status.id, {"note_tags": ["إدخال يدوي متكرر", "أخرى"], "note": "مراجعة يدوية"})
        self.assertEqual(line.gap, "إدخال يدوي متكرر، مراجعة يدوية")
        table_q = line.requirement_id.question_ids.filtered(lambda x: x.key == "Q002")
        self.assertEqual([c.get("type") for c in table_q._columns()], ["list", "list", "list", "list", "number"])
        # changing the status hides the dependent questions again
        a.workspace_answer(line.id, status.id, {"option_id": self._opt(status, "لا أعرف").id})
        self.assertEqual((line.state, line.q_total), ("unknown", 3))
        # a number with its unit, a table cleared by «لا يوجد»
        cash = self._line("FIN-042")
        days = self._q(cash, "Q005")
        a.workspace_answer(cash.id, days.id, {"number": 3})
        self.assertEqual(cash.qanswer_ids.filtered(lambda x: x.question_id == days)._display(), "3 يوم")
        a.workspace_answer(line.id, table.id, {"option_id": self._opt(table, "لا يوجد").id})
        self.assertFalse(line.qanswer_ids.filtered(lambda x: x.question_id == table).table_json)
        with self.assertRaises(UserError):
            a.workspace_answer(line.id, main.id, {"option_id": self._opt(status, "غير منفذ").id})
        # «لا ينطبق» needs a reason
        a.workspace_requirement(line.id, {"na": True})
        self.assertEqual((line.state, line.is_done), ("na", False))
        a.workspace_requirement(line.id, {"reason": "لا يوجد نشاط"})
        self.assertTrue(line.is_done)
        for tab, _title in fin_engine.OUTPUT_TABS:
            self.assertTrue(a.workspace_output("GOV", tab, "module"))
            self.assertTrue(a.workspace_output("GOV", tab, "model"))

    def test_lifecycle_and_lock(self):
        a = self.assessment
        a.with_user(self.preparer).action_fill_demo()
        self.assertEqual(a.done_count, a.applicable_count)
        self.assertEqual(a.answered_count, a.question_count)
        self.assertTrue(a.partial_count and a.full_count and a.unavailable_count)
        a.with_user(self.preparer).action_submit()
        self.assertEqual(a.state, "review")
        self.assertTrue(a.activity_ids.filtered(lambda act: act.user_id == self.reviewer))
        with self.assertRaises(UserError):
            a.with_user(self.preparer).action_approve()
        a.with_user(self.manager).action_approve()
        self.assertEqual((a.state, len(a.version_ids)), ("approved", 1))
        # the point of an approved snapshot is that it records what was approved and
        # does not move afterwards — truthiness proved neither
        snapshot = json.loads(a.version_ids.answers_json)
        line = self._line("FIN-004")
        self.assertEqual(snapshot["FIN-004"]["state"], line.state)
        self.assertEqual(snapshot["FIN-004"]["answers"], line._snapshot()["answers"])
        frozen = dict(snapshot["FIN-004"])
        line = self._line("FIN-001")
        with self.assertRaises((UserError, AccessError)):
            a.with_user(self.preparer).workspace_answer(line.id, line.requirement_id.question_ids[:1].id, {"option_id": False})
        new = self.env["azm.fin.assessment"].browse(a.with_user(self.manager).action_new_version()["res_id"])
        self.assertEqual((new.version, new.state, a.state), (2, "draft", "archived"))
        self.assertEqual((new.done_count, new.answered_count), (a.done_count, a.answered_count))
        # the approved history is immutable: answering again in the new version must not
        # reach back into what was approved
        moved = new.answer_ids.filtered(lambda x: x.code == "FIN-004")[:1]
        if moved and moved.qanswer_ids:
            moved.qanswer_ids[:1].option_id = False
        self.assertEqual(json.loads(a.version_ids.answers_json)["FIN-004"], frozen,
                         "the snapshot still says what was approved")

    def test_each_user_sees_own_data(self):
        theirs = self.env["azm.fin.assessment"].with_user(self.preparer_b).create({"entity_id": self.other.id})
        Assessment = self.env["azm.fin.assessment"]
        ids = (self.assessment | theirs).ids
        self.assertEqual(Assessment.with_user(self.preparer).search([("id", "in", ids)]), self.assessment)
        self.assertEqual(Assessment.with_user(self.preparer_b).search([("id", "in", ids)]), theirs)
        self.assertEqual(Assessment.with_user(self.reviewer).search([("id", "in", ids)]), self.assessment)
        self.assertEqual(Assessment.with_user(self.manager).search([("id", "in", ids)]), self.assessment | theirs)
        unassigned = self.env["azm.entity"].create({"code": "FTC", "name": "كيان غير مسند"})
        with self.assertRaises(AccessError):
            Assessment.with_user(self.preparer_b).create({"entity_id": unassigned.id})
        answers = self.env["azm.fin.answer"].with_user(self.preparer_b).search([("assessment_id", "in", ids)])
        self.assertEqual(answers.assessment_id, theirs)
        self.assessment.with_user(self.preparer).action_fill_demo()
        QA = self.env["azm.fin.qanswer"]
        self.assertFalse(QA.with_user(self.preparer_b).search([("assessment_id", "=", self.assessment.id)]))
        self.assertTrue(QA.with_user(self.preparer).search([("assessment_id", "=", self.assessment.id)]))


@tagged("post_install", "-at_install")
class TestTheFilterOnlyFilters(TransactionCase):
    """DEV01 · U02 — «مرشّح العرض لا يكتب في قرار الانطباق».

    مساحة العمل كانت تطبع طول القائمة المعروضة تحت اسم «منطبق». وما دام المرشّح
    مُطفأ فالرقمان متساويان ولا يظهر الخطأ؛ وحين يُشغَّل «إظهار غير المنطبق» تتسع
    القائمة وحدها، فقرأ موديول المخزون — وفيه ثلاثة متطلبات لا ينطبق منها شيء —
    «3 متطلب منطبق من 3».

    المعروض والمنطبق رقمان مختلفان، وتشغيل المرشّك لا يغيّر إجابة ولا حالة ولا نسبة.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.entity = cls.env["azm.entity"].create({"code": "FLT", "name": "كيان المرشّح"})
        cls.preparer = new_test_user(cls.env, "flt_prep",
                                     groups="azm_operating_model.azm_group_user")
        cls.entity.user_ids = [(6, 0, [cls.preparer.id])]
        cls.assessment = cls.env["azm.fin.assessment"].with_user(cls.preparer).create(
            {"entity_id": cls.entity.id})

    def _a_module_with_something_inapplicable(self):
        """كود موديول فيه متطلب واحد على الأقل غير منطبق على هذا الكيان."""
        for module in self.assessment.answer_ids.module_id:
            lines = self.assessment.answer_ids.filtered(lambda a, m=module: a.module_id == m)
            if lines and not all(lines.mapped("applicable")):
                return module.code
        self.skipTest("كل المتطلبات منطبقة على هذا الكيان")

    def test_the_count_says_applicable_and_means_applicable(self):
        code = self._a_module_with_something_inapplicable()
        data = self.assessment.workspace_data(module_code=code, show_all=True)
        module = data["module"]
        shown = sum(len(topic["requirements"]) for topic in data["topics"])

        lines = self.assessment.answer_ids.filtered(lambda a: a.module_id.code == code)
        really = len(lines.filtered("applicable"))

        self.assertEqual(module["applicable"], really,
                         "«منطبق» يُحسب من البيانات، لا من طول القائمة المعروضة")
        self.assertEqual(module["shown"], shown, "«معروض» هو ما عُرض فعلًا")
        self.assertEqual(module["total"], len(lines))
        self.assertNotEqual(module["applicable"], module["shown"],
                            "هذا الموديول يحوي غير منطبق، فلا بد أن يختلف الرقمان")

    def test_turning_the_filter_on_shows_more_without_making_them_applicable(self):
        code = self._a_module_with_something_inapplicable()
        closed = self.assessment.workspace_data(module_code=code, show_all=False)
        opened = self.assessment.workspace_data(module_code=code, show_all=True)
        self.assertGreater(opened["module"]["shown"], closed["module"]["shown"],
                           "المرشّح يوسّع المعروض")
        self.assertEqual(opened["module"]["applicable"], closed["module"]["applicable"],
                         "ولا يغيّر عدد المنطبق")

    def test_the_filter_writes_nothing_at_all(self):
        """معيار القبول: تشغيله وإيقافه لا يغيّر أي إجابة أو حالة أو نسبة إنجاز."""
        code = self._a_module_with_something_inapplicable()

        def snapshot():
            header = self.assessment._header()
            lines = self.assessment.answer_ids.filtered(lambda a: a.module_id.code == code)
            return (header.get("answered"), header.get("progress"),
                    sorted((l.id, l.applicable, l.state, l.is_done) for l in lines))

        before = snapshot()
        for show_all in (True, False, True):
            self.assessment.workspace_data(module_code=code, show_all=show_all)
        self.assertEqual(snapshot(), before,
                         "العرض قراءة، ولا يكتب في الانطباق ولا في الإنجاز")
