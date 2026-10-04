from odoo.tests import TransactionCase, tagged

from odoo.addons.azm_platform.models.azm_coding import (
    ARTIFACT_TYPES, CANONICAL, LIFECYCLE, MODULE_IDS)


@tagged('post_install', '-at_install')
class TestCoding(TransactionCase):
    """The coding of AZM Master Coding Registry v2.1, as the documents carry it."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env['res.company'].create({'name': 'AZM Coding Campus'})
        cls.env.user.company_ids = [(4, cls.company.id)]
        cls.entity = cls.company.azm_entity_ids
        cls.fin = cls.env['azm.fin.assessment'].create({'entity_id': cls.entity.id})
        cls.fin.action_fill_demo()
        cls.proc = cls.env['azm.assessment'].create({
            'entity_id': cls.entity.id, 'purchase_kind': 'subscriptions', 'scenario': 'petty_cash'})
        cls.proc.action_fill_demo()
        cls.Pub = cls.env['azm.doc.publication'].sudo()

    def test_the_modules_carry_the_registry_ids(self):
        """Taken from the registry, not derived: it orders INV before PUR and we do not."""
        modules = self.env['azm.fin.module'].search([])
        self.assertEqual({m.code: m.azm_code for m in modules if m.azm_code},
                         {code: canonical for code, canonical in MODULE_IDS.items()
                          if code in modules.mapped('code')})
        pur = modules.filtered(lambda m: m.code == 'PUR')
        self.assertEqual(pur.azm_code, 'AZM-FIN-MOD-000006')

    def test_every_document_is_coded_the_registry_way(self):
        """AZM-<DOMAIN>-<TYPE>-<SERIAL>, with entity, version and stage kept outside it."""
        module = self.env['azm.fin.module'].search([], limit=1)
        stage = self.env['azm.stage'].search([], limit=1)
        types = {code for code, _ar, _en in ARTIFACT_TYPES}
        stages = {code for code, _ar, _en in LIFECYCLE}
        cases = [
            self.Pub._get(self.company, 'module', module=module, tab='rules'),
            self.Pub._get(self.company, 'summary'),
            self.Pub._get(self.company, 'book'),
            self.Pub._get(self.company, 'stage', stage=stage, tab='pur_policy'),
            self.Pub._get(self.company, 'cycle'),
        ]
        for pub in cases:
            payload = pub._azm_payload()
            domain, atype, serial = payload['code'].split('-')[1:]
            self.assertIn(domain, ('FIN', 'PUR'))
            self.assertIn(atype, types)
            self.assertEqual(payload['code'],
                             CANONICAL.format(domain=domain, atype=atype, serial=int(serial)))
            self.assertIn(payload['stage'], stages)
            self.assertEqual(payload['scope'], self.company.name,
                             "the entity is the scope beside the code, never inside it")

    def test_a_requirement_keeps_the_id_the_registry_gave_it(self):
        requirement = self.env['azm.fin.requirement'].search([('req_id', '!=', False)], limit=1)
        pub = self.Pub._get(self.company, 'requirement', requirement=requirement)
        self.assertEqual(pub._azm_payload()['code'], requirement.req_id,
                         "the registry numbered the requirements; they are not renumbered here")

    def test_one_artifact_is_shared_by_every_entity(self):
        """Store once, map many: the same policy is one code for the whole group."""
        other = self.env['res.company'].create({'name': 'AZM Coding Elsewhere'})
        module = self.env['azm.fin.module'].search([], limit=1)
        mine = self.Pub._get(self.company, 'module', module=module, tab='rules')._artifact()
        theirs = self.Pub._get(other, 'module', module=module, tab='rules')._artifact()
        self.assertEqual(mine, theirs)
        self.assertEqual(mine.code, theirs.code)

    def test_the_serials_follow_the_model_not_the_reader(self):
        """The first module's policy is POL-000001, whichever document was opened first.

        A serial allocated on first sight follows whoever happened to read a document,
        so the policy of whatever module was opened first would be number one.
        """
        A = self.env['azm.artifact'].sudo()
        A._register_all()
        modules = self.env['azm.fin.module'].search([]).sorted(
            lambda m: (m.azm_code or 'ZZZ', m.id))
        for atype in ('POL', 'PRO', 'DOA', 'SRQ', 'GAP', 'DEC'):
            first = A.search([('domain', '=', 'FIN'), ('atype', '=', atype), ('serial', '=', 1)])
            self.assertIn(f"FIN.{modules[0].code}", first.node_name,
                          f"AZM-FIN-{atype}-000001 belongs to the first module")
        # and they follow the registry's order of modules, which is not ours: it puts
        # INV (MOD-000005) before PUR (MOD-000006) and the catalogue sequence does not
        fifth = A.search([('domain', '=', 'FIN'), ('atype', '=', 'POL'), ('serial', '=', 5)])
        self.assertIn(f"FIN.{modules[4].code}", fifth.node_name)

    def test_every_code_is_well_formed_unique_and_dense(self):
        import re
        from collections import Counter, defaultdict
        A = self.env['azm.artifact'].sudo()
        A._register_all()
        arts = A.search([])
        self.assertTrue(arts)
        for art in arts:
            self.assertRegex(art.code, r"^AZM-(FIN|PUR)-[A-Z]{2,4}-\d{6}$")
            self.assertEqual(art.code, f"AZM-{art.domain}-{art.atype}-{art.serial:06d}",
                             "a code says exactly what its own fields say")
        for field in ('code', 'ref'):
            dupes = [k for k, n in Counter(arts.mapped(field)).items() if n > 1]
            self.assertFalse(dupes, f"duplicate {field}: {dupes[:3]}")
        by = defaultdict(list)
        for art in arts:
            by[(art.domain, art.atype)].append(art.serial)
        for key, serials in by.items():
            self.assertEqual(sorted(serials), list(range(1, len(serials) + 1)),
                             f"{key} is numbered 1..N with no gaps")

    def test_a_requirement_is_numbered_as_the_registry_numbered_it(self):
        A = self.env['azm.artifact'].sudo()
        A._register_all()
        for req in self.env['azm.fin.requirement'].search([], limit=40):
            art = A.search([('ref', '=', f"azm.fin.requirement,{req.id}")], limit=1)
            self.assertEqual(art.code, req.req_id)

    def test_the_tree_reference_points_at_the_tree(self):
        """The identity is the canonical code; the tree reference is how to find the
        node again — not the shorthand the output used to be coded by."""
        module = self.env['azm.fin.module'].search([], limit=1)
        stage = self.env['azm.stage'].search([], limit=1)
        cases = [
            (self.Pub._get(self.company, 'module', module=module, tab='rules'), f"FIN.{module.code}"),
            (self.Pub._get(self.company, 'summary'), 'FIN'),
            (self.Pub._get(self.company, 'stage', stage=stage, tab='pur_policy'), f"PUR-{stage.code}"),
            (self.Pub._get(self.company, 'cycle'), 'PUR'),
        ]
        for pub, expected in cases:
            self.assertEqual(pub._azm_payload()['tree_ref'], expected)

    def test_a_serial_is_allocated_once_and_never_moves(self):
        module = self.env['azm.fin.module'].search([], limit=1)
        pub = self.Pub._get(self.company, 'module', module=module, tab='rules')
        first = pub._artifact().code
        self.env['azm.fin.module'].create({'code': 'ZZZ', 'name': 'AZM Coding Probe'})
        self.assertEqual(pub._artifact().code, first,
                         "approved history is immutable: a new module renumbers nothing")

    def test_a_document_names_itself_one_way(self):
        """The cover and the body of the same PDF print the same code."""
        import re
        stage = self.env['azm.stage'].search([], limit=1)
        pub = self.Pub._get(self.company, 'stage', stage=stage, tab='pur_policy')
        payload = pub._azm_payload()
        found = re.search(r'o_azm_doc_code">([^<]+)<', str(payload['html']))
        self.assertTrue(found, "the output prints a code of its own")
        self.assertEqual(found.group(1), payload['code'])

    def test_a_requirement_reference_cannot_be_given_to_two_of_them(self):
        from psycopg2 import IntegrityError
        from odoo.tools import mute_logger
        requirement = self.env['azm.fin.requirement'].search([('tree_ref', '!=', False)], limit=1)
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            with self.env.cr.savepoint():
                self.env.cr.execute(
                    "UPDATE azm_fin_requirement SET tree_ref = %s WHERE id = %s",
                    (requirement.tree_ref, self.env['azm.fin.requirement'].search(
                        [('id', '!=', requirement.id)], limit=1).id))

    def test_a_document_is_filed_under_a_name_a_file_system_can_hold(self):
        question = self.env['azm.question'].search([], limit=1)
        self.assertIn('/', question.code, "a question is coded with a slash")
        pub = self.Pub._get(self.company, 'question', question=question)
        pub._generate_safe()
        self.assertNotIn('/', pub.document_id.name,
                         "a slash in a file name is a path separator to whoever downloads it")
