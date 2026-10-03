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

    def test_catalogue(self):
        self.assertEqual(self.env["azm.fin.module"].search_count([]), 17)
        self.assertEqual(self.env["azm.fin.requirement"].search_count([]), 167)
        self.assertEqual(self.env["azm.fin.requirement"].search_count([("source", "=", "HRF")]), 60)
        self.assertEqual(len(self.env["azm.fin.module"].search([("code", "=", "ADV")])._details()), 22)
        self.assertEqual(len(self.assessment.answer_ids), 167)

    def test_applicability_follows_activities(self):
        self.assertEqual(self.assessment.scope_ids, self.edu | self.work)
        self.assertTrue(self._line("FIN-024").applicable)     # EDU
        self.assertTrue(self._line("HRF-006").applicable)     # WORK
        self.assertFalse(self._line("FIN-062").applicable)    # PRJ
        self.assessment.scope_ids = [(4, self.prj.id)]
        self.assertTrue(self._line("FIN-062").applicable)
        data = self.assessment.workspace_data("PRJ")
        self.assertEqual(len(data["requirements"]), 7)

    def test_done_rule_and_outputs(self):
        a = self.assessment.with_user(self.preparer)
        line = self._line("FIN-004")
        res = a.workspace_save(line.id, {"state": "partial"})
        self.assertFalse(res["answer"]["done"])  # the gap is mandatory for «partial»
        res = a.workspace_save(line.id, {"gap": "لا توجد مصفوفة صلاحيات مكتوبة", "current": "اعتماد شفهي",
                                         "table": [["الصرف", "موظف", "مراجع", "موظف", "", "", "", ""]]},
                               module_code="GOV", tab="authority")
        self.assertTrue(res["answer"]["done"])
        self.assertIn("نفس الدور", res["output"])        # creator == approver -> segregation warning
        for tab, _title in fin_engine.OUTPUT_TABS:
            self.assertTrue(a.workspace_output("GOV", tab, "module"))
            self.assertTrue(a.workspace_output("GOV", tab, "model"))
        self.assertIn("FIN-004", a.workspace_output("GOV", "gaps", "module"))

    def test_lifecycle_and_lock(self):
        a = self.assessment
        a.with_user(self.preparer).action_fill_demo()
        self.assertEqual(a.done_count, a.applicable_count)
        a.with_user(self.preparer).action_submit()
        self.assertEqual(a.state, "review")
        self.assertTrue(a.activity_ids.filtered(lambda act: act.user_id == self.reviewer))
        with self.assertRaises(UserError):
            a.with_user(self.preparer).action_approve()
        a.with_user(self.manager).action_approve()
        self.assertEqual((a.state, len(a.version_ids)), ("approved", 1))
        with self.assertRaises((UserError, AccessError)):
            a.with_user(self.preparer).workspace_save(self._line("FIN-001").id, {"state": "na"})
        new = self.env["azm.fin.assessment"].browse(a.with_user(self.manager).action_new_version()["res_id"])
        self.assertEqual((new.version, new.state, a.state), (2, "draft", "archived"))
        self.assertEqual(new.done_count, a.done_count)

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
