from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestOutputsLibrary(TransactionCase):
    """The library reads one deliverable across every entity — the other way round
    from the trees, which read one model for one entity."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env['res.company'].create({'name': 'AZM Library Campus'})
        cls.other = cls.env['res.company'].create({'name': 'AZM Library Elsewhere'})
        cls.env.user.company_ids = [(4, cls.company.id), (4, cls.other.id)]
        cls.entity = cls.company.azm_entity_ids
        # two entities that have both started, so coverage is a real figure and the
        # books have something to bind
        for company in (cls.company, cls.other):
            entity = company.azm_entity_ids
            cls.env['azm.fin.assessment'].create({'entity_id': entity.id}).action_fill_demo()
            cls.env['azm.assessment'].create({
                'entity_id': entity.id, 'purchase_kind': 'subscriptions',
                'scenario': 'petty_cash'}).action_fill_demo()
        cls.D = cls.env['azm.dashboard'].with_context(
            allowed_company_ids=[cls.env.company.id, cls.company.id, cls.other.id])
        cls.env['azm.doc.publication'].sudo()._enqueue(cls.company | cls.other)

    # ------------------------------------------------------------------ the shelf
    def test_every_deliverable_appears_once_however_many_entities_hold_it(self):
        """Store once, map many: one row per master artifact, not per copy."""
        # a deliverable this entity holds ready, built here: what the database happens
        # to have published already is not this test's subject
        self.env['azm.doc.publication'].sudo().search(
            [('company_id', '=', self.company.id), ('kind', '=', 'requirement')], limit=1)._generate()
        library = self.D.get_outputs_library()
        self.assertTrue(library['available'])
        codes = [r['code'] for r in library['rows']]
        self.assertEqual(len(codes), len(set(codes)), "a deliverable is listed once")
        row = next(r for r in library['rows'] if r['ready'])
        self.assertLessEqual(row['ready'], row['entities'],
                             "no more entities hold it ready than exist")
        shared = [r for r in library['rows'] if r['held'] > 1]
        self.assertTrue(shared, "a deliverable held by several entities is still one row")
        self.assertEqual(len([r for r in library['rows'] if r['code'] == shared[0]['code']]), 1)

    def test_the_sheets_are_left_out_until_asked_for(self):
        """The four hundred per-question pages of the cycle would bury the outputs people
        actually file; the tree is where those are read.

        A financial requirement is no longer one of them — it *is* the policy or the
        procedure it asks about, so it belongs on the shelf under that name. What is
        left as a sheet is the cycle's questions.
        """
        without = self.D.get_outputs_library()
        with_them = self.D.get_outputs_library(sheets=True)
        self.assertGreater(with_them['total'], without['total'])
        self.assertFalse([r for r in without['rows'] if r['atype'] == 'REQ'])
        # asked for by kind rather than looked for in the first page: there are four
        # hundred of them and the page stops at three hundred
        sheets = self.D.get_outputs_library(sheets=True, atype='REQ')
        self.assertTrue(sheets['total'], 'the sheets are there when asked for')
        self.assertEqual({r['domain'] for r in sheets['rows']}, {'PUR'},
                         'and the sheets that remain are the cycle\'s questions')
        self.assertTrue(self.D.get_outputs_library(atype='POL')['total'],
                        'while the policies are on the shelf in their own right')

    # ------------------------------------------------------------------ the filters
    def test_each_filter_narrows_to_what_it_names(self):
        policies = self.D.get_outputs_library(atype='POL')
        self.assertTrue(policies['rows'])
        self.assertEqual({r['atype'] for r in policies['rows']}, {'POL'})

        cycle = self.D.get_outputs_library(domain='PUR')
        self.assertEqual({r['domain'] for r in cycle['rows']}, {'PUR'})

        gaps = self.D.get_outputs_library(stage='GR')
        self.assertEqual({r['stage'] for r in gaps['rows']}, {'GR'})

        node = self.D.get_outputs_library(node='FIN.GOV')
        self.assertTrue(node['rows'])
        self.assertEqual({r['node'] for r in node['rows']}, {'FIN.GOV'})

        # the node sits between the model and the kind now, so a search by code says so
        found = self.D.get_outputs_library(query='AZM-FIN-POL')
        self.assertTrue(found['rows'])
        self.assertTrue(all('AZM-FIN-POL' in r['code'] for r in found['rows']))

    def test_the_facets_count_what_the_filter_then_returns(self):
        library = self.D.get_outputs_library()
        for facet in library['types']:
            narrowed = self.D.get_outputs_library(atype=facet['key'])
            self.assertEqual(narrowed['total'], facet['count'],
                             f"the {facet['key']} chip promises what filtering by it gives")

    def test_a_chip_counts_under_the_filters_already_on(self):
        """A chip is a promise about what clicking it returns, and it is read with the
        other chips still lit — so it has to count under them, not over the whole shelf.
        It counts under every filter but its own, or picking it could never widen."""
        cycle = self.D.get_outputs_library(domain='PUR')
        for facet in cycle['types']:
            both = self.D.get_outputs_library(domain='PUR', atype=facet['key'])
            self.assertEqual(both['total'], facet['count'],
                             f"with the cycle showing, {facet['key']} promises its own count")
        for facet in cycle['stages']:
            both = self.D.get_outputs_library(domain='PUR', stage=facet['key'])
            self.assertEqual(both['total'], facet['count'])
        for branch in cycle['nodes']:
            both = self.D.get_outputs_library(domain='PUR', node=branch['key'])
            self.assertEqual(both['total'], branch['count'])
        # its own dimension is the exception: the model chips still offer the other
        # model, or picking PUR would leave no way back to FIN
        self.assertEqual({m['key'] for m in cycle['domains']}, {'FIN', 'PUR'})

        # and a search narrows the chips too
        found = self.D.get_outputs_library(query='AZM-FIN-POL')
        for facet in found['types']:
            both = self.D.get_outputs_library(query='AZM-FIN-POL', atype=facet['key'])
            self.assertEqual(both['total'], facet['count'])

    def test_the_shelf_counts_do_not_move_when_a_chip_is_picked(self):
        """The KPIs say what the group produces; that is a property of the group, not
        of what is being looked at, so filtering must not rewrite it."""
        whole = self.D.get_outputs_library()['totals']
        filtered = self.D.get_outputs_library(atype='POL', domain='FIN')['totals']
        self.assertEqual(filtered['deliverables'], whole['deliverables'])
        self.assertEqual(filtered['types'], whole['types'])

    # ------------------------------------------------------------------ issued or not
    def _build_some(self, limit=8):
        """Build a few documents for real.

        A document records which assessment it was built from as it is built, so until
        something is built nothing has been issued from anything — which is correct, and
        is why these tests cannot just queue them.
        """
        Pub = self.env['azm.doc.publication'].sudo()
        # The kinds the shelf lists. A requirement is one of them now — it *is* the
        # policy or the procedure — while the cycle's question sheets are not, and the
        # module-level documents are bindings of the deliverables under them rather than
        # deliverables, so building either of those proves nothing about what it shows.
        pubs = Pub.search([('company_id', '=', self.company.id),
                           ('kind', '=', 'requirement')]
                          + Pub._due_domain(), limit=limit)
        self.assertTrue(pubs, 'there was something queued to build')
        for pub in pubs:
            pub._generate_safe()
        sourced = pubs.filtered(lambda p: p.assessment_id or p.proc_assessment_id)
        self.assertTrue(sourced, f"nothing recorded a source; states={pubs.mapped('state')}")
        return pubs

    def test_a_ready_file_and_an_approved_one_are_not_the_same_thing(self):
        """A deliverable built from a draft is a draft deliverable however finished the
        file looks. What counts as issued is the state of the answers behind it."""
        self.assertFalse(self.D.get_outputs_library()['approvals'],
                         'nothing built yet, so nothing has been issued from anything')
        self._build_some()

        library = self.D.get_outputs_library()
        by_state = {a['key']: a['count'] for a in library['approvals']}
        self.assertTrue(by_state, 'now the copies are in some state or other')
        self.assertEqual(by_state.get('approved', 0), library['totals']['approved'])
        self.assertGreater(by_state.get('draft', 0), 0,
                           'and they are draft, because that is what they came from')
        self.assertEqual(self.D.get_outputs_library(approval='approved')['total'], 0,
                         'nothing has been approved, so nothing is listed as such')
        self.assertGreater(library['totals']['unissued'], 0)

    def test_approving_an_assessment_issues_its_deliverables(self):
        built = self._build_some()
        fin = built.mapped('assessment_id')
        proc = built.mapped('proc_assessment_id')
        self.assertTrue(fin or proc, 'the documents know what they were built from')
        before = self.D.get_outputs_library(approval='approved')['total']

        for sources in (fin, proc):
            if sources:
                sources.sudo()._workflow().write({'state': 'approved'})

        after = self.D.get_outputs_library(approval='approved')
        self.assertGreater(after['total'], before,
                           'the deliverables built from it now read as approved')
        self.assertTrue(all(r['held'] for r in after['rows']),
                        'and only the ones somebody actually holds in that state')
        # each entity's own copy says where it stands
        entities = self.D.get_output_entities(after['rows'][0]['id'])['rows']
        self.assertTrue([e for e in entities if e['approval'] == 'approved'])
        self.assertTrue(all(e['approval_label'] for e in entities if e['approval']))

    def test_filtering_by_approval_counts_only_those_copies(self):
        """The coverage bar should answer "how many have it approved", not "how many
        have a file", once the question is about approval."""
        self._build_some()
        whole = self.D.get_outputs_library()
        drafts = self.D.get_outputs_library(approval='draft')
        self.assertGreater(drafts['total'], 0)
        self.assertLess(drafts['totals']['copies'], whole['totals']['copies'],
                        'only the copies issued from a draft are counted')
        self.assertEqual(drafts['filters']['approval'], 'draft')
        for row in drafts['rows']:
            self.assertTrue(row['held'], 'a deliverable nobody holds in that state is out')

    # ------------------------------------------------------------------ the entities
    def test_the_coverage_counts_only_the_entities_asked_for(self):
        everywhere = self.D.get_outputs_library()
        here = self.D.get_outputs_library(company_ids=[self.company.id])
        self.assertEqual(here['totals']['entities'], 1)
        self.assertGreater(everywhere['totals']['entities'], 1)
        self.assertLessEqual(here['totals']['copies'], everywhere['totals']['copies'])

    def test_an_entity_the_user_does_not_work_in_is_not_reachable(self):
        """Filtering by entity can only ever narrow: asking for one the user was never
        given falls back to the ones they work in rather than widening."""
        outsider = self.env['res.company'].create({'name': 'AZM Library Outside'})
        user = new_test_user(
            self.env, 'azm_library_insider', company_id=self.company.id,
            company_ids=[(6, 0, [self.company.id])],
            groups='azm_platform.group_azm_user,azm_operating_model.azm_group_user')
        D = self.env['azm.dashboard'].with_user(user).with_company(self.company)
        library = D.get_outputs_library(company_ids=[outsider.id])
        self.assertEqual([e['id'] for e in library['entity_options']], [self.company.id])
        self.assertEqual(library['filters']['company_ids'], [self.company.id])

        # opening a row is the other way in, and it names entities: it must narrow too,
        # or the row would list an entity the filter was refused
        row = library['rows'][0]
        found = D.get_output_entities(row['id'], company_ids=[outsider.id])
        self.assertEqual([e['company_id'] for e in found['rows']], [self.company.id])
        self.assertNotIn(outsider.name, [e['name'] for e in found['rows']])

    def test_a_model_the_reader_cannot_open_is_not_listed(self):
        """The library lists both models, so it has to ask about both.

        The gate used to be "either model is readable", and then the page listed them
        both: a reader allowed the procurement cycle but not the financial model got
        every financial deliverable's code, node and coverage because one of the two
        answered yes.
        """
        cls = type(self.env['azm.dashboard'])
        with patch.object(cls, '_fin_available', lambda self: False):
            library = self.D.get_outputs_library()
            self.assertEqual({r['domain'] for r in library['rows']}, {'PUR'})
            self.assertEqual({m['key'] for m in library['domains']}, {'PUR'})
            # and it cannot be reached by id through the other way in either
            fin = self.env['azm.artifact'].sudo().search([('domain', '=', 'FIN')], limit=1)
            self.assertTrue(fin)
            self.assertFalse(self.D.get_output_entities(fin.id)['available'])

        with patch.object(cls, '_om_available', lambda self: False):
            self.assertEqual({r['domain'] for r in self.D.get_outputs_library()['rows']},
                             {'FIN'})

        with patch.object(cls, '_fin_available', lambda self: False), \
                patch.object(cls, '_om_available', lambda self: False):
            self.assertFalse(self.D.get_outputs_library()['available'])
            self.assertFalse(self.D.get_output_entities(1)['available'])

    def test_opening_a_deliverable_names_the_entities_and_how_each_is_doing(self):
        library = self.D.get_outputs_library(atype='POL')
        row = library['rows'][0]
        found = self.D.get_output_entities(row['id'])
        self.assertTrue(found['available'])
        self.assertEqual(found['code'], row['code'])
        self.assertEqual({e['company_id'] for e in found['rows']},
                         set(self.D._companies().ids))
        for entity in found['rows']:
            self.assertIn(entity['state'], ('done', 'pending', 'empty', 'error'))
            self.assertTrue(entity['doc']['kind'])
            self.assertEqual(entity['doc']['company_id'], entity['company_id'])
        # Every row says which copy it is. The card above carries the master code that
        # all of them share, so a panel that named only the entity left the reader
        # opening nine documents that all looked like the one code on the card.
        from odoo.addons.azm_platform.models.azm_coding import copy_code
        codes = self.env['azm.entity'].sudo().with_context(active_test=False).search(
            [('company_id', 'in', [e['company_id'] for e in found['rows']])])
        by_company = {e.company_id.id: e.code or '' for e in codes}
        for entity in found['rows']:
            self.assertEqual(entity['code'],
                             copy_code(found['code'], by_company.get(entity['company_id'], '')),
                             f"{entity['name']} is not told which copy it holds")
        # and they differ from one another, or the panel is nine rows of one code
        holders = [e for e in found['rows'] if by_company.get(e['company_id'])]
        self.assertEqual(len({e['code'] for e in holders}), len(holders),
                         'two entities are shown the same copy code')

    # ------------------------------------------------------------------ reading it
    def test_every_kind_the_library_offers_can_be_read_and_downloaded(self):
        """A row is only worth listing if it leads to the document.

        The library offers six kinds of deliverable — a branch output of either model,
        each model's own summary, and each model's whole book. They are read through one
        pair of methods, so a kind added to the shelf without a path to the file would
        show up here rather than as a dead button.
        """
        # Every kind, asked for rather than taken off the first page — the shelf stops
        # at three hundred rows and the model-wide volumes sort last.
        rows_by_kind = {}
        for atype in (None, 'MAN', 'RPT'):
            library = self.D.get_outputs_library(company_ids=[self.company.id],
                                                 atype=atype)
            for row in library['rows']:
                rows_by_kind.setdefault(row['doc']['kind'], []).append(row)
        # a module-level document is a binding of the deliverables under it, so it is
        # not one of them and is not on the shelf
        self.assertEqual(set(rows_by_kind), {'requirement', 'stage', 'summary',
                                             'cycle', 'book', 'cycle_book'},
                         'every kind of deliverable is on the shelf')

        for kind, rows in rows_by_kind.items():
            # One that this entity actually holds something for. A module's gap register
            # with no gaps in it is on the shelf for the group and empty for an entity
            # that has none, and "open the first row of this kind" would land on one.
            opened = None
            for row in rows[:12]:
                doc = next(e['doc'] for e in self.D.get_output_entities(row['id'])['rows']
                           if e['company_id'] == self.company.id)
                # exactly the arguments doc_preview.js sends
                args = {'kind': doc['kind'], 'node_id': doc.get('id'),
                        'tab': doc.get('tab'), 'company_id': doc['company_id']}
                try:
                    read = self.D.preview_tree_document(**args)
                except UserError:
                    continue   # nothing in this one for this entity
                self.assertTrue(read['url'].startswith('/web/content/'),
                                f'{kind} ({row["code"]}) can be read in place')
                download = self.D.open_tree_document(**args, download=True)
                self.assertIn('download=true', download['url'],
                              f'{kind} ({row["code"]}) comes down as a file')
                opened = row
                break
            self.assertTrue(opened, f'at least one {kind} this entity holds can be read')

    def test_a_row_can_be_found_again_on_the_tree(self):
        """"Show it on the tree" has to show it, on somebody's tree.

        The button hands the tree a branch and an output as well as an entity. If the
        row carried neither — as it did — the tree opened the model at the top and left
        the reader to find the branch by hand, which is the search they had just done.
        """
        # each model asked for in turn: the shelf stops at three hundred rows and the
        # financial requirements fill it, so the cycle's would never be reached
        rows = []
        for domain in ('FIN', 'PUR'):
            rows += self.D.get_outputs_library(company_ids=[self.company.id],
                                               domain=domain)['rows']
        checked = set()
        for row in rows:
            doc = row['doc']
            if doc['kind'] not in ('requirement', 'stage') or doc['kind'] in checked:
                continue
            checked.add(doc['kind'])
            branch = row['tree']
            self.assertTrue(doc.get('id'), f"{row['code']} names what to open")
            self.assertTrue(branch.get('node_id'),
                            f"{row['code']} names the branch it hangs on")
            tree = (self.D.get_proc_tree(company_id=self.company.id) if row['domain'] == 'PUR'
                    else self.D.get_fin_tree(company_id=self.company.id))
            node = next((n for n in tree['nodes'] if n['id'] == branch['node_id']), None)
            self.assertTrue(node, f"{row['code']} points at a branch the tree has")
        self.assertEqual(checked, {'requirement', 'stage'}, 'both models were checked')

    def test_each_entity_has_its_own_way_onto_the_tree(self):
        """A tree is one entity's model, so the row's entities each carry their own.

        One button for nine entities opened whichever the filter happened to leave.
        """
        library = self.D.get_outputs_library()
        row = next(r for r in library['rows']
                   if r['doc']['kind'] in ('requirement', 'stage'))
        rows = self.D.get_output_entities(row['id'])['rows']
        self.assertGreater(len(rows), 1, 'this deliverable is held by several entities')
        named = [e['doc']['company_id'] for e in rows]
        self.assertEqual(named, [e['company_id'] for e in rows],
                         'each entity carries itself, not the one in focus')
        self.assertEqual(len(set(named)), len(named), 'and each one is its own')

    # ------------------------------------------------------------------ one volume
    def test_all_of_one_kind_binds_into_one_document(self):
        """"Give me our policies" is not "give me our financial model".

        The entity book binds one model whole, in tree order. This binds one kind across
        the branches and across both models, which is the shape a policy manual has.
        """
        Pub = self.env['azm.doc.publication'].sudo()
        book = Pub._get_type_book(self.company, 'POL')
        parts = book._book_parts()
        self.assertTrue(parts, 'the entity has policies to bind')
        self.assertEqual({p.artifact_id.atype for p in parts}, {'POL'},
                         'and only policies went in')
        self.assertEqual({p.company_id for p in parts}, {self.company},
                         'all of them this entity\'s own')
        self.assertEqual([p.artifact_id.serial for p in parts
                          if p.artifact_id.domain == 'FIN'],
                         sorted(p.artifact_id.serial for p in parts
                                if p.artifact_id.domain == 'FIN'),
                         'in the registry\'s order, not whatever the search returned')
        self.assertEqual({p.artifact_id.domain for p in parts}, {'FIN', 'PUR'},
                         'a policy manual crosses both models')
        # the report prints the volume's own cover first, then every part
        self.assertEqual(book._report_ids(), [book.id] + [p.id for p in parts])

        # narrowing to one model gives that model's manual alone
        cycle = Pub._get_type_book(self.company, 'POL', 'PUR')
        self.assertEqual({p.artifact_id.domain for p in cycle._book_parts()}, {'PUR'})
        self.assertLess(len(cycle._book_parts()), len(parts))

    def test_a_manual_of_something_the_entity_has_none_of_says_so(self):
        """Rather than handing over a cover with nothing behind it."""
        Pub = self.env['azm.doc.publication'].sudo()
        bare = self.env['res.company'].create({'name': 'AZM Library Bare'})
        self.env.user.company_ids = [(4, bare.id)]
        book = Pub._get_type_book(bare, 'POL')
        self.assertFalse(book._book_parts())
        self.assertTrue(book._is_empty(None))
        with self.assertRaises(UserError):
            self.D.open_outputs_book(atype='POL', company_id=bare.id)

    def test_a_manual_is_only_offered_for_what_is_worth_binding(self):
        """The per-requirement and per-question sheets are the tree's business, and
        there are nine hundred of them."""
        with self.assertRaises(UserError):
            self.D.open_outputs_book(atype='REQ', company_id=self.company.id)
        with self.assertRaises(UserError):
            self.D.open_outputs_book(atype='NOPE', company_id=self.company.id)

    def test_a_manual_cannot_be_bound_for_an_entity_the_reader_does_not_work_in(self):
        """The entity is checked, not clamped: binding a different entity's manual than
        the one asked for would be worse than refusing."""
        outsider = self.env['res.company'].create({'name': 'AZM Library Outsider'})
        user = new_test_user(
            self.env, 'azm_library_binder', company_id=self.company.id,
            company_ids=[(6, 0, [self.company.id])],
            groups='azm_platform.group_azm_user,azm_operating_model.azm_group_user')
        D = self.env['azm.dashboard'].with_user(user).with_company(self.company)
        with self.assertRaises(UserError):
            D.open_outputs_book(atype='POL', company_id=outsider.id)

    def test_a_manual_is_a_binding_not_a_deliverable(self):
        """Its parts each carry a registry code; the volume takes none.

        Numbering it would put something in the registry the registry does not define,
        and the next pass over the catalogue would take it straight back out.
        """
        Pub = self.env['azm.doc.publication'].sudo()
        book = Pub._get_type_book(self.company, 'POL')
        self.assertFalse(book._artifact_ref())
        self.assertFalse(book._artifact())
        self.assertFalse(book.artifact_id)
        self.assertTrue(all(p.artifact_id for p in book._book_parts()),
                        'while every part of it is numbered')
        before = self.env['azm.artifact'].sudo().search_count([])
        self.env['azm.artifact']._register_all()
        self.assertEqual(self.env['azm.artifact'].sudo().search_count([]), before,
                         'and binding one did not add anything to the registry')

    def test_the_whole_book_can_be_downloaded(self):
        for kind in ('book', 'cycle_book'):
            action = self.D.open_tree_document(kind=kind, company_id=self.company.id,
                                               download=True)
            self.assertIn('download=true', action['url'],
                          f"{kind} comes down as one file")


@tagged('post_install', '-at_install')
class TestOutputsLibraryTour(HttpCase):

    def test_the_library_renders_and_opens_a_deliverable(self):
        self.start_tour('/odoo/action-azm_platform.action_azm_outputs_library',
                        'azm_library_tour', login='admin')


@tagged('post_install', '-at_install')
class TestLibrarySearchesWhatItShows(TransactionCase):
    """A code the product prints has to be a code the product finds."""

    def _library(self, query, user=None, company=None):
        model = self.env['azm.dashboard']
        if user:
            model = model.with_user(user)
        if company:
            model = model.with_company(company)
        return model.get_outputs_library(query=query)

    def test_a_copy_code_finds_the_master_it_names(self):
        artifact = self.env['azm.artifact'].sudo().search([], limit=1)
        if not artifact:
            self.skipTest('no artifacts registered')
        master = artifact.code
        tail = master.split('-', 1)[1]
        entity = self.env['azm.entity'].sudo().search([('code', '!=', False)], limit=1)
        copy = f'{entity.code}-{tail}'

        self.assertTrue(self._library(master)['rows'], 'the master is findable')
        self.assertTrue(self._library(copy)['rows'],
                        f'{copy} is printed on the page, so it must be searchable')
        # case and stray spacing are not part of a code
        self.assertTrue(self._library(copy.lower())['rows'])
        self.assertTrue(self._library(f'   {master}  ')['rows'])

    def test_search_reaches_titles_and_tree_references(self):
        artifact = self.env['azm.artifact'].sudo().search([('node_name', '!=', False)], limit=1)
        if not artifact:
            self.skipTest('no artifact carries a node name')
        # the tree reference is the leading token of the node name: "FIN.GOV · ..."
        ref = (artifact.node_name or '').split(' ')[0]
        self.assertTrue(self._library(ref)['rows'],
                        f'{ref} names a branch, and a reader types what they see')

    def test_a_copy_code_outside_your_entities_finds_nothing(self):
        """Searching is not a way to learn that another entity holds a copy."""
        # AZ Management holds the master register, so its entity code is the master's
        # own prefix and its "copy" code is the master code — which every reader is
        # meant to resolve. It cannot stand for somebody else's copy here.
        from odoo.addons.azm_platform.models.azm_coding import HOLDER
        entities = self.env['azm.entity'].sudo().search([('code', '!=', False)])
        others = entities.filtered(lambda e: (e.code or '').upper() != HOLDER)
        if len(entities) < 2 or not others:
            self.skipTest('needs two entities, one of them not the register holder')
        mine, theirs = entities[0], others[0]
        if mine == theirs:
            mine = (entities - theirs)[0]
        user = new_test_user(
            self.env, 'azm_lib_scope', company_id=mine.company_id.id,
            company_ids=[(6, 0, [mine.company_id.id])],
            groups='azm_platform.group_azm_user,azm_operating_model.azm_group_user')
        artifact = self.env['azm.artifact'].sudo().search([], limit=1)
        tail = artifact.code.split('-', 1)[1]

        self.assertTrue(
            self._library(f'{mine.code}-{tail}', user, mine.company_id)['rows'],
            'their own copy is theirs to find')
        self.assertFalse(
            self._library(f'{theirs.code}-{tail}', user, mine.company_id)['rows'],
            'another entity\'s copy code must not resolve for them')


@tagged('post_install', '-at_install')
class TestTheCardHeadingIsATitle(TransactionCase):
    """A card is headed by what the deliverable is called, not by its number.

    A registry code reads the same down a whole shelf -- AZM-FIN-POL-000001,
    000002, 000003 -- so leading with it pushed the one thing that tells two
    policies apart into second place. The code is an identity and it is kept
    everywhere it identifies something: on the opened card, on the document, in
    the file name, in the payload and in search. It is only the heading it leaves.

    The tours that would normally cover this cannot start a browser in this
    container, so the template is read directly.
    """

    def _template(self):
        import os
        from odoo.modules.module import get_module_path
        path = os.path.join(get_module_path('azm_platform'),
                            'static/src/library/outputs_library.xml')
        with open(path, encoding='utf-8') as handle:
            body = handle.read()
        head, _, rest = body.partition('o_azm_output_entities')
        return head.rpartition('o_azm_output_head')[2], rest

    def test_the_heading_carries_the_title_and_not_the_code(self):
        head, _panel = self._template()
        self.assertIn('t-out="row.label"', head, 'the heading is what it is called')
        self.assertNotIn('t-out="row.code"', head,
                         'the registry code is an identity, not a title')

    def test_opening_the_card_still_shows_the_whole_code(self):
        """Opened, each row carries a complete code -- the copy that row holds.

        The master code is not repeated above them. Every copy code contains it:
        FUE-FIN-POL-000001 is AZM-FIN-POL-000001 held by FUE, so a reader who has
        opened the card can read the whole identity off any row.
        """
        _head, panel = self._template()
        self.assertIn('t-out="e.code"', panel,
                      'each row says which copy it holds')

    def test_no_screen_prints_the_master_code(self):
        """The master code identifies the artifact; it does not label a screen.

        What a reader is looking at is always one entity's copy, and the copy code
        contains the master anyway -- FUE-FIN-POL-000001 is AZM-FIN-POL-000001 held
        by FUE. So no template renders the master: not as a card heading, not as a
        panel header, and not as the tooltip the preview used to carry.
        """
        import os
        from odoo.modules.module import get_module_path
        offenders = []
        for module in ('azm_platform', 'azm_operating_model'):
            root = os.path.join(get_module_path(module), 'static')
            for base, _dirs, files in os.walk(root):
                for name in files:
                    if not name.endswith(('.xml', '.js')):
                        continue
                    path = os.path.join(base, name)
                    with open(path, encoding='utf-8') as handle:
                        body = handle.read()
                    if 'master_code' in body:
                        offenders.append(os.path.relpath(path, root))
        self.assertFalse(offenders, f"these still print the master code: {offenders}")

    def test_a_document_is_labelled_with_the_copy_it_opens(self):
        """The label becomes the preview's heading and the opened tab's title."""
        from odoo.addons.azm_platform.models.azm_coding import copy_code
        D = self.env['azm.dashboard']
        library = D.get_outputs_library(atype='POL')
        if not library['rows']:
            self.skipTest('no policy is registered')
        opened = D.get_output_entities(library['rows'][0]['id'])
        entities = self.env['azm.entity'].sudo().with_context(active_test=False).search(
            [('company_id', 'in', [r['company_id'] for r in opened['rows']])])
        by_company = {e.company_id.id: e.code or '' for e in entities}
        for row in opened['rows']:
            self.assertEqual(
                row['doc'].get('label'),
                copy_code(opened['code'], by_company.get(row['company_id'], '')),
                f"{row['name']} opens a document labelled with somebody else's code")

    def test_the_code_is_still_in_the_payload_and_still_searchable(self):
        """Nothing about the identity moved -- only where it is printed."""
        D = self.env['azm.dashboard']
        library = D.get_outputs_library(atype='POL')
        if not library['rows']:
            self.skipTest('no policy is registered')
        row = library['rows'][0]
        self.assertRegex(row['code'], r"^AZM-(FIN|PUR)-[A-Z]{2,4}-\d{6}$")
        self.assertTrue(row['label'], 'and it still has a title to be headed by')
        # the code it no longer prints is still the code it is found by
        self.assertTrue(D.get_outputs_library(query=row['code'])['rows'],
                        'searching the code still resolves it')
        opened = D.get_output_entities(row['id'])
        self.assertEqual(opened['code'], row['code'])
