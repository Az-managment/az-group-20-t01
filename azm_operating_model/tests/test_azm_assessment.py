from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestAzmAssessment(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.entity = cls.env.company.azm_entity_ids   # the entities are the companies
        cls.preparer = new_test_user(cls.env, "azm_preparer", groups="azm_operating_model.azm_group_user")
        cls.manager = new_test_user(cls.env, "azm_manager", groups="azm_operating_model.azm_group_manager")
        cls.entity.user_ids = [(4, cls.preparer.id)]
        cls.assessment = cls.env["azm.assessment"].with_user(cls.preparer).create({
            "entity_id": cls.entity.id, "purchase_kind": "services", "scenario": "urgent",
        })
        cls.bud = cls.env["azm.stage"].search([("code", "=", "BUD")])

    def _answer(self, stage, key, option_name, user=None):
        q = self.env["azm.question"].search([("stage_id", "=", stage.id), ("key", "=", key)])
        opt = q.option_ids.filtered(lambda o: o.name == option_name)
        rec = self.assessment.with_user(user or self.preparer)
        return rec.workspace_answer(q.id, option_id=opt.id, stage_id=stage.id)

    def test_catalogue_loaded(self):
        self.assertEqual(self.env["azm.stage"].search_count([]), 13)
        self.assertGreater(self.env["azm.question"].search_count([]), 380)
        self.assertEqual(len(self.assessment.answer_ids), self.env["azm.question"].search_count([]))

    def test_visibility_follows_conditions(self):
        data = self.assessment.workspace_data(stage_id=self.bud.id)
        self.assertEqual([q["code"] for q in data["questions"]], ["PUR-BUD/presence"])
        data = self._answer(self.bud, "presence", "مطبقة بالكامل")
        self.assertGreater(len(data["questions"]), 15)
        codes = {q["code"] for q in data["questions"]}
        self.assertNotIn("PUR-BUD/exception_approver", codes)
        data = self._answer(self.bud, "shortage", "اعتماد استثنائي")
        codes = {q["code"] for q in data["questions"]}
        self.assertIn("PUR-BUD/exception_approver", codes)

    def test_risk_rule_and_document(self):
        self._answer(self.bud, "presence", "مطبقة بالكامل")
        data = self._answer(self.bud, "shortage", "استمرار الشراء")
        bud = next(s for s in data["stages"] if s["code"] == "BUD")
        self.assertEqual(bud["risks"], 1)
        policy = self.assessment.workspace_output(stage_id=self.bud.id, tab="policy")
        self.assertIn("عند عدم كفاية المخصص يتم: استمرار الشراء", policy)
        self.assessment.action_sync_findings()
        self.assertIn("R-BUD-shortage", self.assessment.finding_ids.mapped("code"))

    def test_approval_flow_and_lock(self):
        self.assessment.with_user(self.preparer).action_fill_demo()
        self.assessment.with_user(self.preparer).action_submit()
        self.assertEqual(self.assessment.state, "review")
        with self.assertRaises(UserError):
            self.assessment.with_user(self.preparer).action_approve()
        self.assessment.with_user(self.manager).action_approve()
        self.assertEqual(self.assessment.state, "approved")
        self.assertEqual(len(self.assessment.version_ids), 1)
        with self.assertRaises((UserError, AccessError)):
            self._answer(self.bud, "shortage", "إيقاف الطلب")
        new = self.env["azm.assessment"].browse(
            self.assessment.with_user(self.manager).action_new_version()["res_id"])
        self.assertEqual((new.version, new.state, self.assessment.state), (2, "draft", "archived"))
        self.assertEqual(len(new.answer_ids), len(self.assessment.answer_ids))

    def test_every_tab_renders(self):
        self.assessment.action_fill_demo()
        for tab in ("book", "policy", "procedure", "workflow", "authority", "gaps", "risks",
                    "controls", "system", "kpi", "coverage"):
            self.assertTrue(self.assessment.workspace_output(tab=tab, scope="cycle"))
            self.assertTrue(self.assessment.workspace_output(stage_id=self.bud.id, tab=tab))

    def test_entities_are_the_companies(self):
        Entity = self.env["azm.entity"].with_context(active_test=False)
        companies = self.env["res.company"].with_context(active_test=False).search([])
        self.assertEqual(Entity.search([("company_id", "!=", False)]).company_id, companies)
        company = self.env["res.company"].create({"name": "Zeta Training Center"})
        entity = company.azm_entity_ids
        self.assertEqual((len(entity), entity.name, entity.code), (1, "Zeta Training Center", "ZTC"))
        company.name = "Zeta Academy"
        self.assertEqual(entity.name, "Zeta Academy")
        other = self.env["res.company"].create({"name": "Zeta Tech Center"})
        self.assertEqual(other.azm_entity_ids.code, "ZTC2")
        # an entity typed by hand earlier is linked instead of duplicated
        manual = Entity.create({"code": "OMG", "name": "Omega Group"})
        omega = self.env["res.company"].create({"name": "Omega Group"})
        self.assertEqual(omega.azm_entity_ids, manual)
        orphan = Entity.create({"code": "ORP", "name": "بدون شركة"})
        Entity._azm_sync_companies()
        self.assertFalse(orphan.active)
