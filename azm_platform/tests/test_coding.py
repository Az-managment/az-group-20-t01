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
        """<ENTITY>-<DOMAIN>-<NODE>-<TYPE>-<SERIAL>, broad to narrow.

        The version and the lifecycle stage stay outside the code, as the registry
        insists. The entity does not: one master deliverable belongs to the group and
        each entity's copy of it says whose copy it is, so the thing in Future
        University's folders is theirs and still plainly the same deliverable.
        """
        self.env['azm.artifact'].sudo()._register_all()
        module = self.env['azm.fin.module'].search([], limit=1)
        requirement = module.requirement_ids[:1]
        stage = self.env['azm.stage'].search([], limit=1)
        types = {code for code, _ar, _en in ARTIFACT_TYPES}
        stages = {code for code, _ar, _en in LIFECYCLE}
        entity = self.company.azm_entity_ids[:1]
        cases = [
            self.Pub._get(self.company, 'requirement', requirement=requirement),
            self.Pub._get(self.company, 'summary'),
            self.Pub._get(self.company, 'book'),
            self.Pub._get(self.company, 'stage', stage=stage, tab='pur_policy'),
            self.Pub._get(self.company, 'cycle'),
        ]
        for pub in cases:
            payload = pub._azm_payload()
            prefix, domain, node, atype, serial = payload['code'].split('-')
            self.assertEqual(prefix, entity.code, "this entity's own copy of it")
            self.assertIn(domain, ('FIN', 'PUR'))
            self.assertIn(atype, types)
            self.assertTrue(node, 'the module or stage it hangs on')
            self.assertEqual(payload['master_code'],
                             CANONICAL.format(domain=domain, node=node, atype=atype,
                                              serial=int(serial)),
                             "and the group's master code travels with it")
            self.assertIn(payload['stage'], stages)
            self.assertEqual(payload['scope'], self.company.name)
            self.assertNotIn('v', payload['code'],
                             "the version travels beside the code, not inside it")

    def test_a_requirement_is_coded_as_the_deliverable_it_is(self):
        """A requirement is not a page about a policy filed next to the policy — it *is*
        the policy, and it is coded as one.

        Which kind comes from the profile it is answered under, the module is the node
        it hangs on, and the serial counts inside that module. The registry's own
        requirement id stays on the record for anyone tracing back to the source
        document, but it is not what the deliverable is called.
        """
        from odoo.addons.azm_platform.models.azm_coding import PROFILE_OUTPUT
        from odoo.addons.azm_platform.models.azm_documents import FIN_ARTIFACTS
        A = self.env['azm.artifact'].sudo()
        A._register_all()
        requirement = self.env['azm.fin.requirement'].search(
            [('req_id', '!=', False), ('profile', 'in', list(PROFILE_OUTPUT))], limit=1)
        art = A.search([('ref', '=', f"azm.fin.requirement,{requirement.id}")], limit=1)
        self.assertTrue(art, 'a requirement is a deliverable of its own')
        self.assertEqual(art.atype,
                         FIN_ARTIFACTS[PROFILE_OUTPUT[requirement.profile]][0],
                         'typed by what it asks for')
        self.assertEqual(art.node, requirement.module_id.code, 'noded by its module')
        self.assertEqual(art.code,
                         f"AZM-FIN-{art.node}-{art.atype}-{art.serial:06d}")
        self.assertTrue(requirement.req_id,
                        'and the registry id it came in with is still on the record')

    def test_the_entity_s_copy_carries_the_entity_s_own_code(self):
        """One master deliverable for the group, and each entity's copy of it says whose
        it is: AZM-FIN-GOV-POL-000001 is the group's, FUI-FIN-GOV-POL-000001 is Future
        University's copy of that same one."""
        A = self.env['azm.artifact'].sudo()
        A._register_all()
        requirement = self.env['azm.fin.requirement'].search(
            [('req_id', '!=', False)], limit=1)
        pub = self.Pub._get(self.company, 'requirement', requirement=requirement)
        master = pub._artifact(create=False)
        self.assertTrue(master, 'the group numbered it once')
        scoped = pub._scoped_code()
        entity = self.company.azm_entity_ids[:1]
        self.assertTrue(entity.code)
        self.assertEqual(scoped, master.code.replace('AZM', entity.code, 1),
                         "the entity's code in place of the group's, nothing else moved")
        payload = pub._azm_payload()
        self.assertEqual(payload['code'], scoped, 'and that is what the document prints')
        self.assertEqual(payload['master_code'], master.code,
                         'with the master travelling beside it, so one reads back to the other')

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
        order = [f"FIN.{m.code}" for m in modules]
        tabs = {'POL': 'rules', 'PRO': 'workflow', 'DOA': 'authority',
                'SRQ': 'integration', 'GAP': 'gaps', 'DEC': 'future'}
        for atype in tabs:
            arts = A.search([('domain', '=', 'FIN'), ('atype', '=', atype)])
            self.assertTrue(arts, f"something is numbered AZM-FIN-…-{atype}-…")
            # every module that has one starts its own count at one
            for node in set(arts.mapped('node')):
                theirs = arts.filtered(lambda a, n=node: a.node == n).sorted('serial')
                self.assertEqual(theirs[0].serial, 1,
                                 f"FIN.{node}'s first {atype} is 000001")
                self.assertEqual([a.serial for a in theirs],
                                 list(range(1, len(theirs) + 1)),
                                 f"and FIN.{node}'s {atype}s run 1..N")
            # the modules themselves still fall in the registry's order, which is not
            # the catalogue's — read off the names rather than asked of the registry
            seen, got = set(), []
            for art in arts.sorted(lambda a: (order.index(f"FIN.{a.node}")
                                              if f"FIN.{a.node}" in order else 999,
                                              a.serial)):
                head = f"FIN.{art.node}"
                if head not in seen:
                    seen.add(head)
                    got.append(head)
            self.assertEqual(got, sorted(got, key=order.index),
                             f"AZM-FIN-…-{atype} follows the registry's order of modules")

    def test_every_code_is_well_formed_unique_and_dense(self):
        import re
        from collections import Counter, defaultdict
        A = self.env['azm.artifact'].sudo()
        A._register_all()
        arts = A.search([])
        self.assertTrue(arts)
        for art in arts:
            self.assertRegex(art.code, r"^AZM-(FIN|PUR)-[A-Z0-9]{2,8}-[A-Z]{2,4}-\d{6}$")
            self.assertEqual(
                art.code, f"AZM-{art.domain}-{art.node}-{art.atype}-{art.serial:06d}",
                "a code says exactly what its own fields say")
        for field in ('code', 'ref'):
            dupes = [k for k, n in Counter(arts.mapped(field)).items() if n > 1]
            self.assertFalse(dupes, f"duplicate {field}: {dupes[:3]}")
        # dense *inside the node*: FIN.GOV's policies are its first, second and third,
        # and FIN.BUD's begin again at one — which is the whole point of the node being
        # in the code
        by = defaultdict(list)
        for art in arts:
            by[(art.domain, art.node, art.atype)].append(art.serial)
        for key, serials in by.items():
            self.assertEqual(sorted(serials), list(range(1, len(serials) + 1)),
                             f"{key} is numbered 1..N with no gaps")

    def test_a_module_s_deliverables_are_its_own_and_counted_from_one(self):
        """FIN.GOV has three policies, not one. That was the whole complaint about
        AZM-FIN-POL-000001: it read as though a module had one of each kind."""
        from odoo.addons.azm_platform.models.azm_coding import PROFILE_OUTPUT
        A = self.env['azm.artifact'].sudo()
        A._register_all()
        gov = self.env['azm.fin.module'].search([('code', '=', 'GOV')], limit=1)
        policies = gov.requirement_ids.filtered(
            lambda r: PROFILE_OUTPUT.get(r.profile) == 'rules')
        self.assertGreater(len(policies), 1, 'GOV has more than one policy')
        coded = A.search([('domain', '=', 'FIN'), ('node', '=', 'GOV'),
                          ('atype', '=', 'POL')])
        self.assertEqual(len(coded), len(policies), 'and each of them is numbered')
        self.assertEqual(sorted(coded.mapped('serial')),
                         list(range(1, len(policies) + 1)), 'from one, inside GOV')
        # another module counts its own from one as well
        other = A.search([('domain', '=', 'FIN'), ('atype', '=', 'POL'),
                          ('node', '!=', 'GOV'), ('serial', '=', 1)], limit=1)
        self.assertTrue(other, 'every module that has a policy has a first one')

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

    def test_a_deliverable_added_after_the_others_does_not_disturb_them(self):
        """The registry is in the catalogue's order, so something that sorts last lands
        last and nothing before it moves. The probe module carries a requirement, or it
        would never enter the numbering at all."""
        A = self.env['azm.artifact'].sudo()
        A._register_all()
        before = {a.ref: a.code for a in A.search([])}

        module = self.env['azm.fin.module'].create({'code': 'ZZZ', 'name': 'AZM Coding Probe'})
        probe = self.env['azm.fin.requirement'].create({
            'module_id': module.id, 'code': 'ZZZ-001', 'req_id': 'AZM-FIN-REQ-900001',
            'title': 'متطلب تجريبي', 'question': 'سؤال تجريبي', 'profile': 'P'})
        A._register_all()

        after = {a.ref: a.code for a in A.search([])}
        self.assertEqual({r: c for r, c in after.items() if r in before}, before,
                         "nothing that was already numbered moved")
        new_ref = f"azm.fin.requirement,{probe.id}"
        self.assertIn(new_ref, after, "and the new module's policy was numbered")
        # a module counts its own, so a new one starts at one rather than carrying on
        # from whatever the last module reached
        self.assertEqual(after[new_ref], "AZM-FIN-ZZZ-POL-000001",
                         "in its own module, from one")

    def test_a_deliverable_that_becomes_real_is_numbered_without_moving_anyone(self):
        """An entity takes on an activity, so now there are deliverables for it.

        They are numbered inside their own module, from one — and nothing in any other
        module moves, which is what counting inside the node buys. Before the node was
        part of the code a new deliverable pushed every later one along, and every
        document carrying a moved code had to be reissued; now the disturbance stops at
        the module boundary.

        Built from scratch rather than leaned on an existing module: what any particular
        module is applicable to is the catalogue's business and changes, and this is
        about the numbering.
        """
        A = self.env['azm.artifact'].sudo()
        scope = self.env['azm.fin.scope'].sudo().search(
            [('code', 'not in', self.fin.scope_ids.mapped('code'))], limit=1)
        self.assertTrue(scope, 'an activity this entity does not have')
        module = self.env['azm.fin.module'].create(
            {'code': 'QQQ', 'name': 'AZM Numbering Probe'})
        requirement = self.env['azm.fin.requirement'].create({
            'module_id': module.id, 'code': 'QQQ-001', 'req_id': 'AZM-FIN-REQ-900002',
            'title': 'متطلب تجريبي', 'question': 'سؤال تجريبي', 'profile': 'P',
            'scope_code': scope.code})
        self.fin._ensure_answers()
        # filed, so it is judged: a ref nothing has been filed under anywhere is left
        # alone rather than assumed to be nothing
        doc = self.Pub._get(self.company, 'requirement', requirement=requirement)
        self.assertTrue(doc._is_empty(doc._assessment()),
                        'the entity does not do this, so there is nothing to issue')

        A._register_all()
        # the module's gap register and target direction are a different question —
        # nothing has been filed under them, so they are left alone rather than judged
        self.assertFalse(A.search_count([('domain', '=', 'FIN'), ('node', '=', 'QQQ'),
                                         ('atype', '=', 'POL')]),
                         'and the policy nobody needs is not numbered')
        before = {a.ref: a.code for a in A.search([('domain', '=', 'FIN')])}

        # The entity takes the activity on — and only that. Filling the whole demo
        # would hand it every activity there is, and half a dozen other modules would
        # gain deliverables at the same moment, which is not what is being measured.
        self.fin.scope_ids = [(4, scope.id)]
        self.assertFalse(doc._is_empty(doc._assessment()), 'now it has something to say')

        A._register_all()
        gained = A.search([('domain', '=', 'FIN'), ('node', '=', 'QQQ')])
        self.assertTrue(gained, 'the new deliverables are numbered')
        self.assertEqual(gained.filtered(lambda a: a.atype == 'POL').code,
                         'AZM-FIN-QQQ-POL-000001',
                         'in their own module, counted from one')
        now = {a.ref: a.code for a in A.search([('domain', '=', 'FIN')])}
        # outside the probe module: what happens inside it is the point of the test
        outside = {r: c for r, c in before.items() if not c.startswith('AZM-FIN-QQQ-')}
        moved = {r: (outside[r], now.get(r)) for r in outside if now.get(r) != outside[r]}
        self.assertFalse(moved,
                         f"not one code outside FIN.QQQ moved; {list(moved.items())[:3]}")

    def test_registering_twice_changes_nothing(self):
        A = self.env['azm.artifact'].sudo()
        A._register_all()
        before = {a.ref: a.code for a in A.search([])}
        A._register_all()
        self.assertEqual({a.ref: a.code for a in A.search([])}, before)

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
        """The check is deferred to commit so that reordering a topic — which passes
        through a moment where two rows share a reference — is allowed; what must never
        stand is the end state."""
        from psycopg2 import IntegrityError
        from odoo.tools import mute_logger
        requirement = self.env['azm.fin.requirement'].search([('tree_ref', '!=', False)], limit=1)
        other = self.env['azm.fin.requirement'].search([('id', '!=', requirement.id)], limit=1)
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            with self.env.cr.savepoint():
                self.env.cr.execute("UPDATE azm_fin_requirement SET tree_ref = %s WHERE id = %s",
                                    (requirement.tree_ref, other.id))
                self.env.cr.execute("SET CONSTRAINTS ALL IMMEDIATE")

    def test_a_topic_can_be_reordered_without_tripping_that(self):
        """The reference is computed from sibling rank, so moving one requirement
        renumbers its whole topic; that must not be refused."""
        Req = self.env['azm.fin.requirement']
        rows = Req._read_group([('topic_id', '!=', False)], ['topic_id'], ['__count'])
        topic = next((t for t, n in rows if n >= 3), None)
        self.assertTrue(topic, "the catalogue has a topic with several requirements")
        reqs = Req.search([('topic_id', '=', topic.id)], order='sequence, id')
        reqs[0].sequence = reqs[-1].sequence + 5
        self.env.flush_all()
        after = Req.search([('topic_id', '=', topic.id)], order='sequence, id')
        refs = after.mapped('tree_ref')
        self.assertEqual(len(set(refs)), len(refs), "no two requirements share a reference")
        self.assertEqual(refs, sorted(refs), "they are numbered in order down the topic")

    def test_a_document_is_filed_under_a_name_a_file_system_can_hold(self):
        question = self.env['azm.question'].search([], limit=1)
        self.assertIn('/', question.code, "a question is coded with a slash")
        pub = self.Pub._get(self.company, 'question', question=question)
        pub._generate_safe()
        self.assertNotIn('/', pub.document_id.name,
                         "a slash in a file name is a path separator to whoever downloads it")

    # ------------------------------------------------------------------ what exists
    def test_only_an_output_that_can_exist_is_numbered(self):
        """A module with no requirement of a kind has no document of that kind, so it
        takes no number: the first procedure is the first module that has procedures."""
        from odoo.addons.azm_platform.models.azm_documents import MODULE_OUTPUTS
        A = self.env['azm.artifact'].sudo()
        A._register_all()
        for module in self.env['azm.fin.module'].search([]):
            can = module._azm_outputs()
            self.assertTrue(set(can) <= set(MODULE_OUTPUTS))
            for tab in MODULE_OUTPUTS:
                if tab not in can:
                    self.assertFalse(
                        A.search_count([('ref', '=', f"azm.fin.module,{module.id},{tab}")]),
                        f"FIN.{module.code} can have no {tab}, so there is none to number")

    def test_a_deliverable_the_group_does_not_produce_is_not_numbered(self):
        """A module that could have a policy, that nobody in the group needs one for.

        Every entity marked investments not applicable — nobody does that work — so
        there is no investments policy anywhere. It was numbered all the same, and the
        number it held pushed every real policy after it up a place.
        """
        A = self.env['azm.artifact'].sudo()
        A._register_all()
        module = self.env['azm.fin.module'].search([('code', '=', 'INV')], limit=1)
        self.assertTrue(module, 'the catalogue has the module')
        self.assertIn('rules', module._azm_outputs(), 'and it could carry a policy')
        # read from the answers, not from the registry, which is what is on trial
        lines = self.env['azm.fin.answer'].sudo().search([('module_id', '=', module.id)])
        self.assertTrue(lines, 'every entity has been asked about it')
        self.assertFalse(lines.filtered('applicable'), 'and not one of them does this work')
        self.assertFalse(A.search_count([('ref', '=', f"azm.fin.module,{module.id},rules")]),
                         'so there is no investments policy to number')
        # and nothing else is numbered with nothing behind it either
        filed, produced = self.env['azm.doc.publication']._produced_refs()
        hollow = [a.code for a in A.search([]) if a.ref in filed and a.ref not in produced]
        self.assertFalse(hollow, f"numbered with nothing behind them: {hollow[:5]}")

    def test_a_governance_stage_has_no_procedure_and_no_workflow(self):
        """The engine says so itself: governance is not written as an operating
        procedure, and the cycle is drawn whole rather than per governance stage."""
        from odoo.addons.azm_platform.models.azm_proc_documents import (
            GOVERNANCE_HAS_NO, PROC_TAB_ORDER)
        A = self.env['azm.artifact'].sudo()
        A._register_all()
        governance = self.env['azm.stage'].search([('is_governance', '=', True)], limit=1)
        self.assertTrue(governance, "the cycle has a governance stage")
        self.assertEqual(set(governance._azm_outputs()), set(PROC_TAB_ORDER) - GOVERNANCE_HAS_NO)
        for tab in GOVERNANCE_HAS_NO:
            self.assertFalse(A.search_count([('ref', '=', f"azm.stage,{governance.id},{tab}")]),
                             f"PUR-{governance.code} has no {tab} to number")

    def test_the_tree_offers_only_the_outputs_that_exist(self):
        D = self.env['azm.dashboard'].with_company(self.company)
        tree = D.get_fin_tree(company_id=self.company.id)
        for node in tree['nodes']:
            module = self.env['azm.fin.module'].browse(node['id'])
            self.assertEqual([d['tab'] for d in node['docs']], module._azm_outputs())
        proc = D.get_proc_tree(company_id=self.company.id)
        for node in proc['nodes']:
            stage = self.env['azm.stage'].browse(node['id'])
            self.assertEqual([d['tab'] for d in node['docs']], stage._azm_outputs())

    def test_an_output_this_entity_has_nothing_in_is_not_offered(self):
        """Not restating the rule: an output is made genuinely empty for this entity and
        the chip has to disappear, while its neighbours stay."""
        D = self.env['azm.dashboard'].with_company(self.company)
        module = next(m for m in self.env['azm.fin.module'].search([])
                      if len(m._azm_outputs()) >= 2)
        tab, keep = module._azm_outputs()[0], module._azm_outputs()[1]

        def chips():
            tree = D.get_fin_tree(company_id=self.company.id)
            node = next(n for n in tree['nodes'] if n['id'] == module.id)
            return [d['tab'] for d in node['docs']], tree['outputs']

        before, outputs_before = chips()
        self.assertIn(tab, before)
        count_before = next(f['count'] for f in outputs_before['families'] if f['tab'] == tab)

        # the document itself is what knows an output came out empty
        self.Pub._get(self.company, 'module', module=module, tab=tab).write({'state': 'empty'})

        after, outputs_after = chips()
        self.assertNotIn(tab, after, "the empty output is no longer offered")
        self.assertIn(keep, after, "its neighbours still are")
        count_after = next((f['count'] for f in outputs_after['families'] if f['tab'] == tab), 0)
        self.assertEqual(count_after, count_before - 1, "and it stops being counted")

    def test_the_count_says_what_the_branches_show(self):
        """The tile and the chips are the same documents counted once."""
        D = self.env['azm.dashboard'].with_company(self.company)
        for tree in (D.get_fin_tree(company_id=self.company.id),
                     D.get_proc_tree(company_id=self.company.id)):
            from collections import Counter
            on_branches = Counter()
            for node in tree['nodes']:
                for doc in node['docs']:
                    on_branches[doc['tab']] += 1
            for family in tree['outputs']['families']:
                if family['tab'] in on_branches:
                    self.assertEqual(family['count'], on_branches[family['tab']],
                                     f"{family['tab']}: the tile and the branches disagree")

    # ------------------------------------------------------------------ the ground truth
    def test_which_outputs_a_module_has_is_pinned_to_the_catalogue(self):
        """Every other test builds its expectation by calling _azm_outputs() — the method
        under test. This one states the answer, read off the requirements themselves:
        FIN.GOV holds no requirement of the procedure kind, FIN.PUR none of the policy
        kind, and gaps and target direction belong to any module with requirements."""
        expected = {
            'GOV': ['rules', 'authority', 'reports', 'gaps', 'future'],
            'GLD': ['rules', 'gaps', 'future'],
            'PUR': ['workflow', 'authority', 'gaps', 'future'],
            'TRY': ['rules', 'workflow', 'reports', 'integration', 'gaps', 'future'],
        }
        for code, tabs in expected.items():
            module = self.env['azm.fin.module'].search([('code', '=', code)], limit=1)
            self.assertTrue(module, f"the catalogue has module {code}")
            self.assertEqual(module._azm_outputs(), tabs, f"FIN.{code}")

    def test_a_governance_stage_is_pinned_too(self):
        governance = self.env['azm.stage'].search([('is_governance', '=', True)])
        self.assertEqual(governance.mapped('code'), ['GOV'],
                         "the cycle has exactly one governance stage")
        self.assertNotIn('pur_procedure', governance._azm_outputs())
        self.assertNotIn('pur_workflow', governance._azm_outputs())
        operating = self.env['azm.stage'].search([('is_governance', '=', False)], limit=1)
        self.assertIn('pur_procedure', operating._azm_outputs())
        self.assertIn('pur_workflow', operating._azm_outputs())
