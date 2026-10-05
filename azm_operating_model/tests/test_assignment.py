from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestAssignment(TransactionCase):
    """Who answers which part of a model.

    One person owning a whole assessment is the wrong shape for most entities: the
    financial model is 19 modules, and Treasury, HR and Procurement each know their own
    part. A part given to somebody is theirs — others read it and cannot write it.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.entity = cls.env["azm.entity"].create({"code": "ASN", "name": "كيان التوزيع"})
        cls.sara = new_test_user(cls.env, "asn_sara", groups="azm_operating_model.azm_group_user")
        cls.omar = new_test_user(cls.env, "asn_omar", groups="azm_operating_model.azm_group_user")
        cls.manager = new_test_user(cls.env, "asn_mgr", groups="azm_operating_model.azm_group_manager")
        cls.outsider = new_test_user(cls.env, "asn_out", groups="base.group_user")
        cls.entity.user_ids = [(6, 0, [cls.sara.id, cls.omar.id, cls.manager.id])]

        cls.fin = cls.env["azm.fin.assessment"].with_user(cls.sara).create(
            {"entity_id": cls.entity.id, "user_id": cls.sara.id})
        cls.gov = cls.env["azm.fin.module"].search([("code", "=", "GOV")], limit=1)
        cls.treasury = cls.env["azm.fin.module"].search([("code", "=", "TRY")], limit=1)
        cls.Assignment = cls.env["azm.assignment"]

    def _line(self, module):
        return self.fin.answer_ids.filtered(
            lambda a: a.module_id == module and a.applicable)[:1]

    def _answer(self, user, module):
        """Answer one question of this module as somebody, through the ORM they use."""
        line = self._line(module)
        self.assertTrue(line, f"FIN.{module.code} has an applicable requirement")
        return line.with_user(user).write({"na": False, "reason": "probe"})

    # ------------------------------------------------------------------ the lock
    def test_a_part_given_to_somebody_is_theirs(self):
        self.Assignment.create([
            {"fin_assessment_id": self.fin.id, "module_id": self.gov.id, "user_id": self.sara.id},
            {"fin_assessment_id": self.fin.id, "module_id": self.treasury.id, "user_id": self.omar.id},
        ])
        # each answers their own
        self._answer(self.sara, self.gov)
        self._answer(self.omar, self.treasury)
        # and neither answers the other's — not even the preparer of the assessment
        with self.assertRaises(UserError):
            self._answer(self.sara, self.treasury)
        with self.assertRaises(UserError):
            self._answer(self.omar, self.gov)

    def test_an_unassigned_part_stays_with_whoever_prepares_it(self):
        """Assigning nothing changes nothing: an entity that does not want to split the
        work does not have to."""
        self.assertFalse(self.fin.assignment_ids)
        self._answer(self.sara, self.gov)
        self._answer(self.sara, self.treasury)
        # and giving away one part does not take the rest away
        self.Assignment.create({"fin_assessment_id": self.fin.id,
                                "module_id": self.treasury.id, "user_id": self.omar.id})
        self._answer(self.sara, self.gov)
        with self.assertRaises(UserError):
            self._answer(self.sara, self.treasury)

    def test_a_manager_is_not_locked_out(self):
        self.Assignment.create({"fin_assessment_id": self.fin.id,
                                "module_id": self.treasury.id, "user_id": self.omar.id})
        self._answer(self.manager, self.treasury)

    def test_the_lock_holds_on_the_question_answers_too(self):
        """Answering is creating a question answer, not writing the requirement line,
        so the check has to be on that path as well or the lock is decoration."""
        self.Assignment.create({"fin_assessment_id": self.fin.id,
                                "module_id": self.treasury.id, "user_id": self.omar.id})
        line = self._line(self.treasury)
        question = line.requirement_id.question_ids[:1]
        self.assertTrue(question)
        with self.assertRaises(UserError):
            self.env["azm.fin.qanswer"].with_user(self.sara).create(
                {"line_id": line.id, "question_id": question.id})
        made = self.env["azm.fin.qanswer"].with_user(self.omar).create(
            {"line_id": line.id, "question_id": question.id})
        self.assertTrue(made)

    # ------------------------------------------------------------------ who may be given one
    def test_a_part_cannot_be_given_to_somebody_who_could_not_open_it(self):
        with self.assertRaises(ValidationError):
            self.Assignment.create({"fin_assessment_id": self.fin.id,
                                    "module_id": self.gov.id, "user_id": self.outsider.id})
        stranger = new_test_user(self.env, "asn_stranger",
                                 groups="azm_operating_model.azm_group_user")
        with self.assertRaises(ValidationError):
            self.Assignment.create({"fin_assessment_id": self.fin.id,
                                    "module_id": self.gov.id, "user_id": stranger.id})
        self.entity.user_ids = [(4, stranger.id)]
        self.assertTrue(self.Assignment.create(
            {"fin_assessment_id": self.fin.id, "module_id": self.gov.id,
             "user_id": stranger.id}), "on the entity, it is allowed")

    def test_a_part_is_given_to_one_person(self):
        from psycopg2 import IntegrityError
        from odoo.tools import mute_logger
        self.Assignment.create({"fin_assessment_id": self.fin.id,
                                "module_id": self.gov.id, "user_id": self.sara.id})
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            with self.cr.savepoint():
                self.Assignment.create({"fin_assessment_id": self.fin.id,
                                        "module_id": self.gov.id, "user_id": self.omar.id})

    def test_an_assignment_belongs_to_one_model_or_the_other(self):
        from psycopg2 import IntegrityError
        from odoo.tools import mute_logger
        proc = self.env["azm.assessment"].with_user(self.sara).create(
            {"entity_id": self.entity.id, "purchase_kind": "goods", "scenario": "standard"})
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            with self.cr.savepoint():
                self.Assignment.create({
                    "fin_assessment_id": self.fin.id, "module_id": self.gov.id,
                    "proc_assessment_id": proc.id, "user_id": self.sara.id})

    # ------------------------------------------------------------------ the cycle too
    def test_the_procurement_stages_work_the_same_way(self):
        proc = self.env["azm.assessment"].with_user(self.sara).create(
            {"entity_id": self.entity.id, "purchase_kind": "goods", "scenario": "standard",
             "user_id": self.sara.id})
        stage = self.env["azm.stage"].search([("is_governance", "=", False)], limit=1)
        self.Assignment.create({"proc_assessment_id": proc.id, "stage_id": stage.id,
                                "user_id": self.omar.id})
        line = proc.answer_ids.filtered(lambda a: a.stage_id == stage)[:1]
        option = line.question_id.option_ids[:1]
        self.assertTrue(option, "the question has something to pick")
        with self.assertRaises(UserError):
            line.with_user(self.sara).write({"option_id": option.id})
        line.with_user(self.omar).write({"option_id": option.id})
        self.assertEqual(line.option_id, option)

    # ------------------------------------------------------------------ tracking
    def test_an_administrator_can_see_how_far_each_person_has_got(self):
        both = self.Assignment.create([
            {"fin_assessment_id": self.fin.id, "module_id": self.gov.id, "user_id": self.sara.id},
            {"fin_assessment_id": self.fin.id, "module_id": self.treasury.id, "user_id": self.omar.id},
        ])
        for one in both:
            self.assertEqual(one.left, one.total - one.answered)
            self.assertEqual(one.entity_id, self.entity)
            self.assertEqual(one.model_key, 'financial')
            self.assertIn(f"FIN.{one.module_id.code}", one.part_name)
        self.assertTrue(all(one.total for one in both), 'each part has questions in it')
