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
            {"fin_assessment_id": self.fin.id, "module_id": self.gov.id, "user_ids": [(6, 0, [self.sara.id])]},
            {"fin_assessment_id": self.fin.id, "module_id": self.treasury.id, "user_ids": [(6, 0, [self.omar.id])]},
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
                                "module_id": self.treasury.id, "user_ids": [(6, 0, [self.omar.id])]})
        self._answer(self.sara, self.gov)
        with self.assertRaises(UserError):
            self._answer(self.sara, self.treasury)

    def test_a_manager_is_not_locked_out(self):
        self.Assignment.create({"fin_assessment_id": self.fin.id,
                                "module_id": self.treasury.id, "user_ids": [(6, 0, [self.omar.id])]})
        self._answer(self.manager, self.treasury)

    def test_the_lock_holds_on_the_question_answers_too(self):
        """Answering is creating a question answer, not writing the requirement line,
        so the check has to be on that path as well or the lock is decoration."""
        self.Assignment.create({"fin_assessment_id": self.fin.id,
                                "module_id": self.treasury.id, "user_ids": [(6, 0, [self.omar.id])]})
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
                                    "module_id": self.gov.id, "user_ids": [(6, 0, [self.outsider.id])]})
        stranger = new_test_user(self.env, "asn_stranger",
                                 groups="azm_operating_model.azm_group_user")
        with self.assertRaises(ValidationError):
            self.Assignment.create({"fin_assessment_id": self.fin.id,
                                    "module_id": self.gov.id, "user_ids": [(6, 0, [stranger.id])]})
        self.entity.user_ids = [(4, stranger.id)]
        self.assertTrue(self.Assignment.create(
            {"fin_assessment_id": self.fin.id, "module_id": self.gov.id,
             "user_ids": [(6, 0, [stranger.id])]}), "on the entity, it is allowed")

    def test_a_part_is_handed_out_once_however_many_people_are_on_it(self):
        """A part may be shared, but it is one row: two rows for the same part would be
        two answers to "who holds FIN.GOV" with nothing to say which is right."""
        from psycopg2 import IntegrityError
        from odoo.tools import mute_logger
        shared = self.Assignment.create({
            "fin_assessment_id": self.fin.id, "module_id": self.gov.id,
            "user_ids": [(6, 0, [self.sara.id, self.omar.id])]})
        self.assertEqual(len(shared.user_ids), 2, "a part can be given to several people")
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            with self.cr.savepoint():
                self.Assignment.create({"fin_assessment_id": self.fin.id,
                                        "module_id": self.gov.id,
                                        "user_ids": [(6, 0, [self.omar.id])]})

    def test_a_topic_may_be_carved_out_of_a_module(self):
        """A module given to one person, a topic of it to another: the module keeps the
        requirements the topic did not take, so nobody owes the same one twice."""
        topics = self.fin.answer_ids.filtered(lambda a: a.module_id == self.gov).topic_id
        self.assertTrue(topics, "the module has topics to carve")
        module = self.Assignment.create({
            "fin_assessment_id": self.fin.id, "module_id": self.gov.id,
            "user_ids": [(6, 0, [self.sara.id])]})
        whole = len(module._lines())
        carved = self.Assignment.create({
            "fin_assessment_id": self.fin.id, "topic_id": topics[0].id,
            "user_ids": [(6, 0, [self.omar.id])]})
        self.assertTrue(carved._lines(), "the topic holds its own requirements")
        module.invalidate_recordset()
        self.assertEqual(len(module._lines()) + len(carved._lines()), whole,
                         "between them they still cover the module exactly once")
        self.assertFalse(set(module._lines().ids) & set(carved._lines().ids))

    def test_a_carved_out_topic_is_actually_somebody_elses_to_answer(self):
        """The carve-out above only checked the accounting -- which lines each part
        covers -- and that was always right. What was never checked is whether the
        hand-out is enforced, and it was not: the gate read the module key alone, so a
        topic given to Omar was recorded, shown on both their pages, and protected from
        nobody."""
        topics = self.fin.answer_ids.filtered(lambda a: a.module_id == self.gov).topic_id
        self.assertTrue(topics, "the module has topics to carve")
        carved = topics[0]
        self.Assignment.create({
            "fin_assessment_id": self.fin.id, "topic_id": carved.id,
            "user_ids": [(6, 0, [self.omar.id])]})
        line = self.fin.answer_ids.filtered(
            lambda a: a.topic_id == carved and a.applicable)[:1]
        self.assertTrue(line, "the topic has an applicable requirement")

        with self.assertRaises(UserError):
            line.with_user(self.sara).write({"na": False, "reason": "not mine"})
        line.with_user(self.omar).write({"na": False, "reason": "mine"})

    def test_carving_a_topic_out_leaves_the_rest_of_the_module_alone(self):
        """Giving one topic away must not lock the module it came from."""
        topics = self.fin.answer_ids.filtered(lambda a: a.module_id == self.gov).topic_id
        if len(topics) < 2:
            self.skipTest("the module has only one topic")
        self.Assignment.create({
            "fin_assessment_id": self.fin.id, "topic_id": topics[0].id,
            "user_ids": [(6, 0, [self.omar.id])]})
        elsewhere = self.fin.answer_ids.filtered(
            lambda a: a.module_id == self.gov and a.topic_id == topics[1]
            and a.applicable)[:1]
        self.assertTrue(elsewhere)
        # nobody was given this one, so it stays with whoever prepares the assessment
        elsewhere.with_user(self.sara).write({"na": False, "reason": "still open"})

    def test_the_refusal_names_the_part_that_was_handed_out(self):
        """Being told "FIN.GOV is somebody else's" when one topic of it was given away
        sends the reader looking for a module that is mostly still theirs."""
        topics = self.fin.answer_ids.filtered(lambda a: a.module_id == self.gov).topic_id
        carved = topics[0]
        self.Assignment.create({
            "fin_assessment_id": self.fin.id, "topic_id": carved.id,
            "user_ids": [(6, 0, [self.omar.id])]})
        line = self.fin.answer_ids.filtered(
            lambda a: a.topic_id == carved and a.applicable)[:1]
        with self.assertRaises(UserError) as caught:
            line.with_user(self.sara).write({"na": False, "reason": "no"})
        said = str(caught.exception)
        self.assertIn(carved.code or carved.name, said, said)

    def test_a_part_cannot_be_given_to_somebody_barred_from_the_company(self):
        """Three things make an entity visible, and ir.access spells out all three: the
        AZM group, being on the entity, and having its company among your own. Missing
        the third is the quiet one -- the assignment saves, and their page stays empty.
        """
        # The class entity is built without a company, and an entity with no company
        # cannot be barred from one. A new company gets its own entity automatically
        # (azm.entity._azm_sync_companies, one entity per company), so that one is used
        # rather than moving the class entity onto it.
        company = self.env["res.company"].sudo().create({"name": "شركة التوزيع"})
        entity = self.env["azm.entity"].sudo().search([("company_id", "=", company.id)])
        self.assertTrue(entity, "a company gets an entity of its own")
        owner = new_test_user(
            self.env, "asn_owner", groups="azm_operating_model.azm_group_user",
            company_id=company.id, company_ids=[(6, 0, [company.id])])
        stranger = new_test_user(
            self.env, "asn_nocompany", groups="azm_operating_model.azm_group_user")
        entity.user_ids = [(6, 0, [owner.id, stranger.id])]
        self.assertNotIn(company, stranger.sudo().company_ids,
                         "the point of the test is that they may not work in it")
        assessment = self.env["azm.fin.assessment"].sudo().create(
            {"entity_id": entity.id, "user_id": owner.id})
        with self.assertRaises(ValidationError) as caught:
            self.Assignment.sudo().create({
                "fin_assessment_id": assessment.id, "module_id": self.gov.id,
                "user_ids": [(6, 0, [stranger.id])]})
        self.assertIn(company.name, str(caught.exception))
        # and somebody who may work there is accepted, so the rule refuses the right thing
        self.Assignment.sudo().create({
            "fin_assessment_id": assessment.id, "module_id": self.gov.id,
            "user_ids": [(6, 0, [owner.id])]})

    def test_an_assignment_belongs_to_one_model_or_the_other(self):
        from psycopg2 import IntegrityError
        from odoo.tools import mute_logger
        proc = self.env["azm.assessment"].with_user(self.sara).create(
            {"entity_id": self.entity.id, "purchase_kind": "goods", "scenario": "standard"})
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            with self.cr.savepoint():
                self.Assignment.create({
                    "fin_assessment_id": self.fin.id, "module_id": self.gov.id,
                    "proc_assessment_id": proc.id, "user_ids": [(6, 0, [self.sara.id])]})

    # ------------------------------------------------------------------ the cycle too
    def test_the_procurement_stages_work_the_same_way(self):
        proc = self.env["azm.assessment"].with_user(self.sara).create(
            {"entity_id": self.entity.id, "purchase_kind": "goods", "scenario": "standard",
             "user_id": self.sara.id})
        stage = self.env["azm.stage"].search([("is_governance", "=", False)], limit=1)
        self.Assignment.create({"proc_assessment_id": proc.id, "stage_id": stage.id,
                                "user_ids": [(6, 0, [self.omar.id])]})
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
            {"fin_assessment_id": self.fin.id, "module_id": self.gov.id, "user_ids": [(6, 0, [self.sara.id])]},
            {"fin_assessment_id": self.fin.id, "module_id": self.treasury.id, "user_ids": [(6, 0, [self.omar.id])]},
        ])
        for one in both:
            self.assertEqual(one.left, one.total - one.answered)
            self.assertEqual(one.entity_id, self.entity)
            self.assertEqual(one.model_key, 'financial')
            self.assertIn(f"FIN.{one.module_id.code}", one.part_name)
        self.assertTrue(all(one.total for one in both), 'each part has questions in it')
