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
            holder, domain, atype, serial = payload['code'].split('-')
            self.assertEqual(holder, entity.code, 'the copy says whose it is')
            self.assertIn(domain, ('FIN', 'PUR'))
            self.assertIn(atype, types)
            # the serial is the master's: the group numbers the artifact once, and the
            # entity's copy of it keeps that number rather than starting a count of
            # its own, so the same deliverable is the same number everywhere
            self.assertEqual(payload['master_code'],
                             CANONICAL.format(domain=domain, atype=atype,
                                              serial=int(serial)))
            self.assertEqual(payload['code'],
                             f"{entity.code}-{domain}-{atype}-{serial}")
            # the node, the version and the stage still sit beside it
            self.assertTrue(payload['azm_node'], 'the module or stage it hangs on')
            self.assertIn(payload['stage'], stages)
            self.assertEqual(payload['scope'], self.company.name)
            self.assertNotIn(payload['azm_node'], payload['code'])

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
        tab = PROFILE_OUTPUT[requirement.profile]
        art = A.search([('ref', '=', f"azm.fin.requirement,{requirement.id},{tab}")],
                       limit=1)
        self.assertTrue(art, 'a requirement is a deliverable of its own')
        self.assertEqual(art.atype, FIN_ARTIFACTS[tab][0], 'typed by what it asks for')
        self.assertEqual(art.node, requirement.module_id.code,
                         'with its module beside the code, not inside it')
        self.assertEqual(art.code, f"AZM-FIN-{art.atype}-{art.serial:06d}")
        self.assertTrue(requirement.req_id,
                        'and the registry id it came in with is still on the record')

    def test_the_entity_names_the_copy_and_not_the_artifact(self):
        """One artifact, held by every entity it applies to — "store once, map many".

        The register holds one entry, numbered once, with no entity in it. What each
        entity holds is a copy of that entry, and a copy has to say whose it is, so the
        document leads with the entity and prints the master beside it. The module is
        never in either: an artifact may map to many nodes without copies, which a code
        naming one node forbids.
        """
        A = self.env['azm.artifact'].sudo()
        A._register_all()
        requirement = self.env['azm.fin.requirement'].search(
            [('req_id', '!=', False)], limit=1)
        pub = self.Pub._get(self.company, 'requirement', requirement=requirement)
        artifact = pub._artifact(create=False)
        self.assertTrue(artifact, 'the group numbered it once')
        entity = self.company.azm_entity_ids[:1]
        self.assertTrue(entity.code)

        payload = pub._azm_payload()
        self.assertNotIn(entity.code, artifact.code, 'the register entry names no entity')
        self.assertEqual(payload['master_code'], artifact.code)
        self.assertEqual(payload['code'], f"{entity.code}-{artifact.code.split('-', 1)[1]}",
                         "the copy is the master under this entity's name")
        self.assertNotIn(artifact.node, payload['code'], 'the module is in neither')
        self.assertEqual(payload['azm_node'], artifact.node, 'it is printed beside them')
        self.assertEqual(payload['scope'], self.company.name)
        # and the next entity's copy of it is the same deliverable, not another one
        other = self.env['res.company'].create({'name': 'AZM Coding Campus Two'})
        self.env.user.company_ids = [(4, other.id)]
        theirs = self.Pub._get(other, 'requirement', requirement=requirement)
        self.assertEqual(theirs._artifact(create=False), artifact,
                         'stored once, mapped to many')
        # the two copies are plainly the same deliverable and plainly not the same copy
        self.assertNotEqual(theirs._scoped_code(), pub._scoped_code())
        self.assertEqual(theirs._scoped_code().split('-')[1:], pub._scoped_code().split('-')[1:],
                         'one serial behind both, so the two entities can be compared')
        self.assertTrue(theirs._scoped_code().startswith(other.azm_entity_ids[:1].code + '-'))

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
            # one running count for the model, 1..N with no holes
            self.assertEqual(sorted(arts.mapped('serial')),
                             list(range(1, len(arts) + 1)),
                             f"AZM-FIN-{atype} runs 1..N")
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
            self.assertRegex(art.code, r"^AZM-(FIN|PUR)-[A-Z]{2,4}-\d{6}$")
            self.assertEqual(art.code, f"AZM-{art.domain}-{art.atype}-{art.serial:06d}",
                             "a code says exactly what its own fields say")
            self.assertTrue(art.node, "and the node travels beside it, as a field")
        for field in ('code', 'ref'):
            dupes = [k for k, n in Counter(arts.mapped(field)).items() if n > 1]
            self.assertFalse(dupes, f"duplicate {field}: {dupes[:3]}")
        # One running serial per model and type, as the registry numbers them. This
        # asked for 1..N with no gaps, which held only because every run renumbered
        # from one — and renumbering is what moved an issued code onto a different
        # deliverable. Retirement now leaves its serial behind rather than closing the
        # rank up, so the promise is that a serial is issued once and never moves,
        # which is the one the registry actually makes.
        by = defaultdict(list)
        for art in arts:
            by[(art.domain, art.atype)].append(art.serial)
        for key, serials in by.items():
            self.assertEqual(len(set(serials)), len(serials),
                             f"{key} issued a serial twice")
            self.assertTrue(all(n >= 1 for n in serials), f"{key} has a serial below one")
            self.assertGreaterEqual(max(serials), len(serials),
                                    f"{key} has more rows than serials issued")

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
        self.assertEqual(len(coded), len(policies),
                         'and each of them is a deliverable of its own')
        self.assertEqual(len(set(coded.mapped('code'))), len(policies),
                         'each under its own code')
        # the serial runs through the model, so another module's policies carry on
        # rather than starting again — the module is a field, not part of the number
        everything = A.search([('domain', '=', 'FIN'), ('atype', '=', 'POL')])
        serials = everything.mapped('serial')
        self.assertEqual(len(set(serials)), len(serials), 'each under its own serial')
        self.assertEqual(min(serials), 1, 'and the model is counted from one')

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
        new_ref = f"azm.fin.requirement,{probe.id},rules"
        self.assertIn(new_ref, after, "and the new module's policy was numbered")
        # a module counts its own, so a new one starts at one rather than carrying on
        # from whatever the last module reached
        self.assertTrue(after[new_ref].startswith("AZM-FIN-POL-"),
                        "numbered among the model's policies")

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
        policy = gained.filtered(lambda a: a.atype == 'POL')
        self.assertTrue(policy.code.startswith('AZM-FIN-POL-'),
                        'numbered among the model\'s policies')
        self.assertEqual(policy.node, 'QQQ', 'with its module beside the code')
        now = {a.ref: a.code for a in A.search([('domain', '=', 'FIN')])}
        # The serial runs through the model, so a deliverable appearing in the middle of
        # it does move the ones after — that is the price of the registry's flat
        # numbering, and the reason a document prints its code into its own fingerprint:
        # the ones affected age by themselves rather than keeping a number that moved.
        moved = {r: (before[r], now[r]) for r in before if r in now and before[r] != now[r]}
        for ref, (was, is_now) in moved.items():
            self.assertGreater(is_now, was, 'down the list, never up')
        self.assertFalse([r for r in before if r not in now],
                         'and nothing already numbered was dropped')

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


@tagged('post_install', '-at_install')
class TestACodeIsIssuedOnce(TransactionCase):
    """Approved history is immutable, which is a promise about codes.

    The register used to renumber on every run so that each type read 000001..N with
    no holes. Retiring one policy from FIN.GOV then moved 108 codes onto different
    deliverables: AZM-FIN-POL-000003 stopped meaning "حالات إضافية" and started
    meaning the policy after it, while every PDF already issued went on carrying the
    old number. These are the four things that must hold instead.
    """

    def setUp(self):
        super().setUp()
        self.A = self.env['azm.artifact'].sudo().with_context(active_test=False)
        self.Pub = self.env['azm.doc.publication']

    def _retire(self, ref):
        """Run the real registration with one deliverable no longer produced."""
        original = type(self.Pub)._produced_refs

        def produced_without_it(pub):
            filed, produced = original(pub)
            return set(filed) | {ref}, set(produced) - {ref}

        type(self.Pub)._produced_refs = produced_without_it
        try:
            self.env['azm.artifact'].sudo()._register_all()
        finally:
            type(self.Pub)._produced_refs = original

    def _a_policy(self):
        art = self.A.search([('domain', '=', 'FIN'), ('atype', '=', 'POL')],
                            order='serial', limit=1)
        if not art:
            self.skipTest('no financial policy is registered')
        return art

    def test_retiring_one_deliverable_moves_no_other_code(self):
        """ما يُقارَن هو ref لا node_name.

        ref هو ما يشير إليه الكود — العقدة ومخرجها — وهو الهوية. و node_name
        اسمٌ يُعرض، يتغيّر حين يُعاد تسمية متطلب دون أن ينتقل الكود إلى شيء آخر.
        مقارنته كانت تقرأ إعادة التسمية انتقالًا، فيسقط الاختبار على تغيير
        لا علاقة له بما يحرسه.
        """
        victim = self._a_policy()
        before = {a.code: a.ref for a in self.A.search([])}
        self._retire(victim.ref)
        after = {a.code: a.ref for a in self.A.search([])}
        moved = [c for c in sorted(set(before) & set(after)) if before[c] != after[c]]
        self.assertFalse(moved, f"{len(moved)} codes changed meaning: {moved[:3]}")

    def test_a_retired_deliverable_keeps_its_code_and_leaves_the_catalogue(self):
        victim = self._a_policy()
        code, name = victim.code, victim.node_name
        self._retire(victim.ref)
        still = self.A.search([('code', '=', code)], limit=1)
        self.assertTrue(still, 'the row stays, so the code stays spoken for')
        self.assertEqual(still.node_name, name, 'and goes on meaning what it meant')
        self.assertFalse(still.active, 'but it is no longer produced')
        self.assertFalse(self.env['azm.artifact'].sudo().search([('code', '=', code)]),
                         'so it is out of the catalogue every reader sees')

    def test_a_new_deliverable_never_takes_a_retired_code(self):
        victim = self._a_policy()
        hole = victim.code
        top = max(self.A.search([('domain', '=', 'FIN'),
                                 ('atype', '=', 'POL')]).mapped('serial'))
        self._retire(victim.ref)
        fresh = self.env['azm.artifact'].sudo()._of(
            'azm.test,brand.new,rules', 'FIN', 'POL', node='GOV', name='a new policy')
        self.assertNotEqual(fresh.code, hole, 'a retired code is never handed out again')
        self.assertGreater(fresh.serial, top,
                           'the next serial goes above the highest ever issued, '
                           'not into the gap retirement left')

    def test_producing_it_again_revives_the_code_it_already_had(self):
        victim = self._a_policy()
        code, ref = victim.code, victim.ref
        self._retire(ref)
        back = self.env['azm.artifact'].sudo()._of(ref, 'FIN', 'POL', node='GOV',
                                                   name='revived')
        self.assertEqual(back.code, code, 'it is the same deliverable, so the same code')
        self.assertTrue(back.active)

    def test_registering_twice_issues_nothing_new(self):
        """The register is derived, so a second run with nothing changed is a no-op."""
        before = {a.code: a.ref for a in self.A.search([])}
        self.env['azm.artifact'].sudo()._register_all()
        self.assertEqual({a.code: a.ref for a in self.A.search([])}, before)

    def test_the_same_code_cannot_be_issued_to_two_rows(self):
        from psycopg2 import IntegrityError
        from odoo.tools.misc import mute_logger
        art = self._a_policy()
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            with self.env.cr.savepoint():
                self.A.create({
                    'code': art.code, 'ref': 'azm.test,duplicate,rules',
                    'domain': 'FIN', 'atype': 'POL', 'node': 'GOV', 'serial': 999999,
                })

    def test_the_same_serial_cannot_be_issued_twice_for_a_type(self):
        from psycopg2 import IntegrityError
        from odoo.tools.misc import mute_logger
        art = self._a_policy()
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            with self.env.cr.savepoint():
                self.A.create({
                    'code': 'AZM-FIN-POL-999999', 'ref': 'azm.test,same.serial,rules',
                    'domain': 'FIN', 'atype': 'POL', 'node': 'GOV',
                    'serial': art.serial,
                })

    def test_one_node_is_registered_once_while_it_is_produced(self):
        from psycopg2 import IntegrityError
        from odoo.tools.misc import mute_logger
        art = self._a_policy()
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            with self.env.cr.savepoint():
                self.A.create({
                    'code': 'AZM-FIN-POL-999998', 'ref': art.ref,
                    'domain': 'FIN', 'atype': 'POL', 'node': 'GOV', 'serial': 999998,
                })


@tagged('post_install', '-at_install')
class TestTheFilenameConvention(TransactionCase):
    """<MasterID>__<Entity-or-Shared>__v<Version>__<Lang>__<ShortTitle>.pdf

    The parts are the registry's first rule written into a file name: the identity is
    the master ID, and the entity, the version and the language sit beside it rather
    than inside it. A file used to be named for the entity's copy code, which buried
    the master and left the version and the language unsaid.
    """

    def setUp(self):
        super().setUp()
        self.Pub = self.env['azm.doc.publication'].sudo()

    def _published(self, limit=200):
        pubs = self.Pub.search([('document_id', '!=', False)], limit=limit)
        if not pubs:
            self.skipTest('nothing has been published')
        return pubs

    def test_a_name_has_the_five_parts_in_the_right_order(self):
        from odoo.addons.azm_platform.models.azm_documents import DOC_LANG
        for pub in self._published(50):
            stem = pub._file_stem()
            parts = stem.split('__')
            self.assertEqual(len(parts), 5, f"not five parts: {stem}")
            master, scope, version, lang, title = parts
            self.assertTrue(master, 'it leads with what identifies it')
            self.assertTrue(scope, 'and says whose copy it is')
            self.assertRegex(version, r"^v\d+$", f"version reads oddly: {version}")
            self.assertEqual(lang, DOC_LANG)
            self.assertTrue(title.strip(), 'and what it is about')

    def test_the_master_leads_and_the_entity_sits_beside_it(self):
        """Every entity's copy of a policy is the same artifact, so they sort together."""
        from odoo.addons.azm_platform.models.azm_coding import HOLDER, copy_code
        # an entity that is not the register holder, so its copy code genuinely differs
        # from the master and there is something to tell apart
        pubs = self.Pub.search([('document_id', '!=', False),
                                ('artifact_id', '!=', False)], limit=400)
        pub = next((p for p in pubs
                    if (p._entity().code or '').upper() != HOLDER
                    and p._artifact(create=False).code), None)
        if not pub:
            self.skipTest('nothing published for an entity other than the holder')
        master = pub._artifact(create=False).code
        entity = pub._entity().code
        stem = pub._file_stem()
        self.assertTrue(stem.startswith(f"{master}__{entity}__"), stem)
        # the copy code is what the cover prints; it is not what the file is named
        copy = copy_code(master, entity)
        self.assertNotEqual(copy, master, 'this entity really does hold a copy code')
        self.assertNotIn(copy, stem,
                         f"the file is named for the master, not the copy: {stem}")

    def test_a_name_carries_nothing_a_file_system_refuses(self):
        for pub in self._published(200):
            stem = pub._file_stem()
            for bad in '\\/:*?"<>|':
                self.assertNotIn(bad, stem, f"{bad!r} is not safe in {stem}")
            self.assertNotIn('\n', stem)
            self.assertLessEqual(len(stem), 160, f"too long to survive a zip: {stem}")

    def test_a_long_title_is_cut_to_the_budget(self):
        from odoo.addons.azm_platform.models.azm_documents import SHORT_TITLE
        from unittest.mock import patch
        pub = self._published(1)
        long_title = 'ref · ' + ('سياسة الاعتماد والتفويض المالي للكيانات التابعة ' * 5)
        with patch.object(type(pub), 'name', long_title):
            title = pub._short_title()
        self.assertLessEqual(len(title), SHORT_TITLE)
        self.assertTrue(title.strip())
        self.assertNotIn('__', title, 'or the parts cannot be told apart again')

    def test_a_binding_leads_with_where_it_sits(self):
        """It is a collection of deliverables that each carry their own number."""
        binding = self.Pub.search([('kind', '=', 'module'), ('document_id', '!=', False)],
                                  limit=1)
        if not binding:
            self.skipTest('no binding is published')
        self.assertEqual(binding._file_stem().split('__')[0], binding._tree_ref())

    def test_a_document_ages_when_its_own_name_would_change(self):
        """Otherwise a naming change leaves files behind under a dead convention."""
        from unittest.mock import patch
        pub = self._published(1)
        before = pub._current_stamp()
        with patch.object(type(pub), '_file_stem', lambda self, assessment=None: 'OTHER'):
            after = pub._current_stamp()
        self.assertNotEqual(before, after, 'the name is part of what the document is')
