import contextlib
from unittest.mock import Mock, patch

from odoo.exceptions import AccessError
from odoo.http import request_var
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

    # ------------------------------------------------------------ handing work over
    def test_submitting_reaches_somebody_who_can_open_it(self):
        """Work left the preparer and arrived in nobody's hands.

        Submitting wrote the state and scheduled an activity *if* a reviewer happened to
        be named on the record. Where none was, the assessment said "under review" and
        no human had been told — and the people who should review it could not read it
        either, because the rules only let through work they were named on.
        """
        Activity = self.env["mail.activity"]
        before = Activity.search_count([("user_id", "=", self.reviewer.id)])
        self.assertFalse(self.a2.reviewer_id, "nobody was named on it")

        self.a2.with_user(self.prep_2).action_submit()

        self.assertEqual(self.a2.state, "review")
        self.assertIn(self.reviewer, self.a2._reviewers(),
                      "the entity's own reviewer is who it goes to")
        self.assertGreater(Activity.search_count([("user_id", "=", self.reviewer.id)]), before,
                           "and they were told")
        # and they can actually open what they were told about
        self.env["azm.assessment"].with_user(self.reviewer).browse(self.a2.id).check_access("read")
        self.assertIn(self.a2, self._visible(self.reviewer))

    def test_a_preparer_does_not_review_their_own_work(self):
        self.a1.reviewer_id = False
        self.assertNotIn(self.prep_1, self.a1._reviewers(),
                         "the person who prepared it is never who it goes to")

    def test_work_is_not_sent_where_nobody_is_standing(self):
        """Better to refuse than to park it in a state nobody is watching."""
        from odoo.exceptions import UserError
        lonely = self.env["azm.entity"].create({"code": "LNE", "name": "بلا مراجع"})
        lonely.user_ids = [(6, 0, [self.prep_1.id])]
        orphan = self.env["azm.assessment"].with_user(self.prep_1).create(
            {"entity_id": lonely.id, "purchase_kind": "goods", "scenario": "standard"})
        # no reviewer named, nobody assigned who reviews — but the managers can always
        # be reached, so it goes to them rather than nowhere
        self.assertTrue(orphan._reviewers(), "the managers are the last resort")
        self.assertIn(self.manager, orphan._reviewers())
        # and with not even a manager to reach, it refuses rather than disappearing
        patched = self.env["azm.assessment"]
        with patch.object(type(patched), "_reviewers", lambda self: self.env["res.users"]):
            with self.assertRaises(UserError):
                orphan.with_user(self.prep_1).action_submit()
        self.assertEqual(orphan.state, "draft", "and it stayed where it was")

    def test_only_people_who_could_do_the_job_are_offered(self):
        """Assigning somebody who is not on the entity hands them work they cannot open."""
        # a record being filled in is a NewId one, so the lists are compared by origin
        def offered(entity, field):
            draft = self.env["azm.assessment"].new({"entity_id": entity.id})
            return draft[field]._origin

        self.assertIn(self.prep_1, offered(self.ent_a, "allowed_preparer_ids"))
        self.assertNotIn(self.prep_b, offered(self.ent_a, "allowed_preparer_ids"),
                         "somebody on another entity is not offered")
        self.assertIn(self.reviewer, offered(self.ent_a, "allowed_reviewer_ids"))
        self.assertNotIn(self.prep_1, offered(self.ent_a, "allowed_reviewer_ids"),
                         "a preparer is not offered as a reviewer")

        outsider = new_test_user(self.env, "acc_outsider", groups="base.group_user")
        self.ent_a.user_ids = [(4, outsider.id)]
        self.assertNotIn(outsider, offered(self.ent_a, "allowed_preparer_ids"),
                         "being on the entity is not enough without the role")

        # an entity nobody is on yet offers the role at large, rather than nothing
        bare = self.env["azm.entity"].create({"code": "BRE", "name": "بلا أحد"})
        self.assertIn(self.reviewer, offered(bare, "allowed_reviewer_ids"))
        self.assertNotIn(outsider, offered(bare, "allowed_preparer_ids"))

    def test_company_follows_entity(self):
        company = self.env["res.company"].create({"name": "كيان ب"})   # same name: the entity is linked to it
        self.assertEqual(self.ent_b.company_id, company)
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

    @contextlib.contextmanager
    def _bound_request(self, **cookies):
        """Bind a minimal request, which the theme is picked from.

        ir.http.color_scheme runs while serving a request: web_enterprise reads
        the color_scheme cookie and the preference of request.env.user from it,
        so calling it from a bare TransactionCase raises "request not bound".
        """
        token = request_var.set(Mock(env=self.env, httprequest=Mock(cookies=cookies)))
        try:
            yield
        finally:
            request_var.reset(token)

    def test_the_served_theme_follows_the_browser(self):
        """Regression: forcing the served theme reloaded the page for ever.

        web_enterprise settles the theme on both sides. The browser computes
        it in ColorSchemePlugin from the user's preference, falling back to the
        operating system when that preference reads "system", writes the answer
        into the color_scheme cookie and reloads if it had to change it. The
        server reads that same cookie back. Answering "light" whatever the
        cookie said made the two disagree on a machine set to dark: the browser
        wrote "dark" and reloaded, the next response set "light" again, and the
        page reloaded for as long as it was left open.
        """
        IrHttp = self.env["ir.http"]
        settings = self.env["res.users.settings"]._find_or_create_for_user(self.env.user)
        settings.color_scheme = "system"
        for asked in ("dark", "light"):
            with self._bound_request(color_scheme=asked):
                self.assertEqual(
                    IrHttp.color_scheme(), asked,
                    "the server has to agree with the theme the browser settled on",
                )

    def test_a_chosen_theme_is_served_whatever_the_cookie_says(self):
        """A real preference wins on both sides, so the two cannot disagree."""
        IrHttp = self.env["ir.http"]
        settings = self.env["res.users.settings"]._find_or_create_for_user(self.env.user)
        for preference in ("light", "dark"):
            settings.color_scheme = preference
            for stale_cookie in ("light", "dark"):
                with self._bound_request(color_scheme=stale_cookie):
                    self.assertEqual(IrHttp.color_scheme(), preference)

    def test_a_user_starts_on_the_light_theme(self):
        """AZM pages are designed light, so that is where a user starts."""
        Settings = self.env["res.users.settings"]
        ICP = self.env["ir.config_parameter"].sudo()
        ICP.set_bool("azm.allow_dark_theme", False)
        self.assertEqual(Settings._azm_default_color_scheme(), "light")
        # ... unless an administrator allows dark mode, and then Odoo decides.
        ICP.set_bool("azm.allow_dark_theme", True)
        self.assertEqual(Settings._azm_default_color_scheme(), "system")

    def test_existing_users_are_moved_off_the_system_theme(self):
        Settings = self.env["res.users.settings"]
        self.env["ir.config_parameter"].sudo().set_bool("azm.allow_dark_theme", False)
        settings = Settings._find_or_create_for_user(self.prep_1)
        settings.color_scheme = "system"
        Settings._azm_apply_light_theme()
        self.assertEqual(settings.color_scheme, "light")

    def test_a_deliberate_dark_choice_is_left_alone(self):
        Settings = self.env["res.users.settings"]
        self.env["ir.config_parameter"].sudo().set_bool("azm.allow_dark_theme", False)
        settings = Settings._find_or_create_for_user(self.prep_2)
        settings.color_scheme = "dark"
        Settings._azm_apply_light_theme()
        self.assertEqual(settings.color_scheme, "dark", "a user's own choice must survive")
