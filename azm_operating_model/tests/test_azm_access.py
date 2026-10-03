from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestAzmAccess(TransactionCase):
    """Each person only sees the data they are entitled to (role x entity x company)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Entity = cls.env["azm.entity"]
        cls.ent_a = Entity.create({"code": "ACA", "name": "كيان أ"})
        cls.ent_b = Entity.create({"code": "ACB", "name": "كيان ب"})
        cls.prep_1 = new_test_user(cls.env, "acc_prep1", groups="azm_operating_model.azm_group_user")
        cls.prep_2 = new_test_user(cls.env, "acc_prep2", groups="azm_operating_model.azm_group_user")
        cls.prep_b = new_test_user(cls.env, "acc_prepb", groups="azm_operating_model.azm_group_user")
        cls.reviewer = new_test_user(cls.env, "acc_rev", groups="azm_operating_model.azm_group_reviewer")
        cls.manager = new_test_user(cls.env, "acc_mgr", groups="azm_operating_model.azm_group_manager")
        cls.ent_a.user_ids = [(6, 0, [cls.prep_1.id, cls.prep_2.id, cls.reviewer.id])]
        cls.ent_b.user_ids = [(6, 0, [cls.prep_b.id])]
        Assessment = cls.env["azm.assessment"]
        cls.a1 = Assessment.with_user(cls.prep_1).create(
            {"entity_id": cls.ent_a.id, "purchase_kind": "goods", "scenario": "standard",
             "reviewer_id": cls.reviewer.id})
        cls.a2 = Assessment.with_user(cls.prep_2).create(
            {"entity_id": cls.ent_a.id, "purchase_kind": "services", "scenario": "standard"})
        cls.b1 = Assessment.with_user(cls.prep_b).create(
            {"entity_id": cls.ent_b.id, "purchase_kind": "goods", "scenario": "standard"})

    def _visible(self, user, model="azm.assessment"):
        return self.env[model].with_user(user).search([("id", "in", (self.a1 | self.a2 | self.b1).ids)]) \
            if model == "azm.assessment" else self.env[model].with_user(user).search([])

    def test_preparer_sees_only_own(self):
        self.assertEqual(self._visible(self.prep_1), self.a1)
        self.assertEqual(self._visible(self.prep_2), self.a2)
        self.assertEqual(self._visible(self.prep_b), self.b1)
        with self.assertRaises(AccessError):
            self.a2.with_user(self.prep_1).read(["name"])

    def test_entities_by_assignment(self):
        self.assertEqual(self.env["azm.entity"].with_user(self.prep_1).search([("code", "in", ("ACA", "ACB"))]),
                         self.ent_a)
        self.assertEqual(self.env["azm.entity"].with_user(self.prep_b).search([("code", "in", ("ACA", "ACB"))]),
                         self.ent_b)
        # cannot create an assessment on an entity they are not assigned to
        with self.assertRaises(AccessError):
            self.env["azm.assessment"].with_user(self.prep_b).create(
                {"entity_id": self.ent_a.id, "purchase_kind": "works", "scenario": "standard"})

    def test_reviewer_sees_assigned(self):
        self.assertEqual(self._visible(self.reviewer), self.a1)

    def test_removed_from_entity_loses_access(self):
        self.ent_a.user_ids = [(3, self.prep_1.id)]
        self.assertFalse(self._visible(self.prep_1))

    def test_manager_sees_all(self):
        self.assertEqual(self._visible(self.manager), self.a1 | self.a2 | self.b1)

    def test_children_follow_assessment(self):
        self.a1.action_fill_demo()
        self.a1.action_sync_findings()
        self.b1.action_fill_demo()
        self.b1.action_sync_findings()
        findings = self.env["azm.finding"].with_user(self.prep_1).search([])
        self.assertTrue(findings)
        self.assertEqual(findings.assessment_id, self.a1)
        answers = self.env["azm.answer"].with_user(self.prep_b).search([("assessment_id", "in", (self.a1 | self.b1).ids)])
        self.assertEqual(answers.assessment_id, self.b1)

    def test_company_follows_entity(self):
        company = self.env["res.company"].create({"name": "ACC Co"})
        # creating a company now creates its entity, and a company may only
        # have one, so the generated entity makes way for the one under test
        company.azm_entity_ids.unlink()
        self.ent_b.company_id = company
        a = self.env["azm.assessment"].create({"entity_id": self.ent_b.id, "purchase_kind": "works",
                                               "scenario": "direct"})
        self.assertEqual(a.company_id, company)
        self.assertNotEqual(a.name, "جديد")
        member = new_test_user(self.env, "acc_member", company_id=company.id, company_ids=[(6, 0, [company.id])],
                               groups="azm_operating_model.azm_group_user")
        self.ent_b.user_ids = [(4, member.id)]
        mine = self.env["azm.assessment"].with_user(member).create(
            {"entity_id": self.ent_b.id, "purchase_kind": "subscriptions", "scenario": "direct"})
        self.assertTrue(mine.name.startswith("AZM/"))
        # prep_b is not a member of that company: the entity and its assessments disappear for them
        self.assertFalse(self.env["azm.entity"].with_user(self.prep_b).search([("id", "=", self.ent_b.id)]))
