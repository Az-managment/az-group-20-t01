from odoo import api, models

from odoo.addons.azm_operating_model.models import engine
from odoo.addons.azm_operating_model.models.azm_assessment import PURCHASE_KINDS, SCENARIOS

from .azm_om_catalogue import MODEL_DOMAINS

OPEN_FINDING_STATES = ('candidate', 'confirmed', 'treatment')
HIGH_SCORE = 15  # likelihood x impact (1..25)
STAGE_STATUSES = ('full', 'partial', 'none', 'unknown')
DOMAIN_TONES = {'governance': 'purple', 'procurement': 'blue', 'financial': 'green'}
DOMAIN_ICONS = {'governance': 'account_balance', 'procurement': 'shopping_cart', 'financial': 'payments'}
FINDING_COLORS = {'candidate': '#f59e0b', 'confirmed': '#ef4444', 'treatment': '#3b82f6',
                  'closed': '#16a34a', 'dismissed': '#94a3b8'}
ASSESSMENT_COLORS = {'draft': '#94a3b8', 'review': '#f59e0b', 'approved': '#16a34a'}


def _pct(part, whole):
    return round(100.0 * part / whole, 1) if whole else None


def _empty():
    return {'visible': 0, 'answered': 0, 'known': 0, 'risks': 0,
            'status': dict.fromkeys(STAGE_STATUSES, 0)}


def _add(total, item):
    for key in ('visible', 'answered', 'known', 'risks'):
        total[key] += item[key]
    if item.get('status') in total['status'] and 'status_counts' not in item:
        total['status'][item['status']] += 1
    return total


class AzmDashboard(models.AbstractModel):
    _inherit = 'azm.dashboard'

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    @api.model
    def _om_available(self):
        return 'azm.assessment' in self.env and self.env['azm.assessment'].has_access('read')

    @api.model
    def _om_scan(self, assessments, stages):
        """Run the Operating Model engine once per assessment x stage.

        Returns {(assessment_id, stage_id): {visible, answered, known, risks, status}}.
        The engine is the same one that drives the answer workspace, so the figures
        always match what the preparer sees.
        """
        rules = [r._engine_dict() for r in self.env['azm.risk.rule'].search([])]
        result = {}
        for assessment in assessments:
            for stage in stages:
                sdict, qdicts, answers, _by_q = assessment._stage_payload(stage)
                stats = engine.stage_stats(sdict, qdicts, answers)
                result[assessment.id, stage.id] = {
                    'visible': stats['total'],
                    'answered': stats['answered'],
                    'known': stats['known'],
                    'risks': len(engine.findings(sdict, qdicts, answers, rules)),
                    'status': engine.stage_status(sdict, answers),
                }
        return result

    @api.model
    def _om_rates(self, agg):
        return {
            **{k: agg[k] for k in ('visible', 'answered', 'known', 'risks')},
            'completion': _pct(agg['answered'], agg['visible']),
            'certainty': _pct(agg['known'], agg['answered']),
        }

    @api.model
    def _om_company(self, company):
        if not company:
            return False
        company = company.sudo()  # presentation only (name / logo)
        return {
            'id': company.id,
            'name': company.name,
            'has_logo': bool(company.logo) and not company.uses_default_logo,
            'unique': str(company.write_date or ''),
        }

    @api.model
    def _om_finding_row(self, finding, labels):
        return {
            'id': finding.id,
            'code': finding.code,
            'fact': finding.fact,
            'risk': finding.risk or '',
            'control': finding.control or '',
            'stage': finding.stage_id.name,
            'stage_code': finding.stage_id.code,
            'domain': finding.azm_domain,
            'entity': finding.entity_id.name,
            'assessment': finding.assessment_id.name,
            'state': finding.state,
            'state_label': labels.get(finding.state, finding.state),
            'score': finding.score,
            'owner': finding.user_id.name or finding.owner_hint or '',
            'due_date': str(finding.due_date or ''),
        }

    # ------------------------------------------------------------------
    # Operating Model page
    # ------------------------------------------------------------------
    @api.model
    def get_operating_model_data(self, entity_id=None, assessment_id=None, domain=None, company_id=None):
        """Everything the Operating Model page needs, in one call.

        entity_id / company_id narrow the assessments, assessment_id picks a single one,
        domain (governance / procurement / financial) narrows the question areas.
        """
        if not self._om_available():
            return {'available': False}
        env = self._env_all_companies()
        all_stages = env['azm.stage'].search([])
        Assessment = env['azm.assessment']

        # entities of the companies selected in the company switcher (or not linked to any company)
        entity_domain = ([('company_id', '=', company_id)] if company_id else
                         ['|', ('company_id', '=', False), ('company_id', 'in', env.companies.ids)])
        entities = env['azm.entity'].search(entity_domain)
        scope = [('state', '!=', 'archived'), ('entity_id', 'in', entities.ids)]
        if entity_id:
            scope.append(('entity_id', '=', entity_id))
        in_scope = Assessment.search(scope)
        assessments = in_scope.filtered(lambda a: a.id == assessment_id) if assessment_id else in_scope
        if not assessments and assessment_id:
            assessments, assessment_id = in_scope, None

        scan = self._om_scan(assessments, all_stages)
        stages = all_stages.filtered(lambda s: not domain or s.azm_domain == domain)
        domain_labels = dict(MODEL_DOMAINS)

        # ---------------- catalogue figures (per stage)
        Question = env['azm.question']
        q_by_type = Question._read_group([('stage_id', 'in', all_stages.ids)], ['stage_id', 'qtype'], ['__count'])
        q_by_group = Question._read_group([('stage_id', 'in', all_stages.ids)], ['stage_id', 'group'], ['__count'])
        q_common = dict(Question._read_group([('stage_id', 'in', all_stages.ids), ('is_common', '=', True)],
                                             ['stage_id'], ['__count']))
        rules = dict(env['azm.risk.rule']._read_group([('stage_id', 'in', all_stages.ids)],
                                                       ['stage_id'], ['__count']))
        catalogue = {st.id: {'questions': 0, 'types': {'select': 0, 'multi': 0, 'number': 0},
                             'groups': {'0': 0, '1': 0, '2': 0}} for st in all_stages}
        for stage, qtype, count in q_by_type:
            catalogue[stage.id]['types'][qtype] = count
            catalogue[stage.id]['questions'] += count
        for stage, group, count in q_by_group:
            catalogue[stage.id]['groups'][group] = count

        # ---------------- findings (tracked risk register)
        Finding = env['azm.finding']
        state_labels = dict(Finding._fields['state']._description_selection(env))
        findings = Finding.search([('assessment_id', 'in', assessments.ids)])
        live = findings.filtered(lambda f: f.triggered or f.state in ('closed', 'dismissed'))
        open_findings = live.filtered(lambda f: f.state in OPEN_FINDING_STATES)

        def finding_figures(subset):
            opened = subset.filtered(lambda f: f.state in OPEN_FINDING_STATES)
            handled = subset.filtered(lambda f: f.state != 'dismissed')
            return {
                'findings': len(subset),
                'findings_open': len(opened),
                'findings_high': len(opened.filtered(lambda f: f.score >= HIGH_SCORE)),
                'findings_closed': len(subset.filtered(lambda f: f.state == 'closed')),
                'treatment_rate': _pct(len(subset.filtered(lambda f: f.state == 'closed')), len(handled)),
            }

        # ---------------- one card per question area (stage)
        stage_cards = []
        for st in stages:
            agg = _empty()
            for a in assessments:
                _add(agg, scan[a.id, st.id])
            cat = catalogue[st.id]
            single = scan[assessments.id, st.id] if len(assessments) == 1 else None
            stage_cards.append({
                'id': st.id,
                'code': st.code,
                'name': st.name,
                'domain': st.azm_domain,
                'domain_label': domain_labels.get(st.azm_domain, ''),
                'tone': DOMAIN_TONES.get(st.azm_domain, 'slate'),
                'owner': st.default_owner or '',
                'input': st.input_desc or '',
                'output': st.output_desc or '',
                'governance': st.is_governance,
                'questions': cat['questions'],
                'types': cat['types'],
                'groups': cat['groups'],
                'common': q_common.get(st, 0),
                'rules': rules.get(st, 0),
                'status_counts': agg['status'],
                'status': single['status'] if single else False,
                **self._om_rates(agg),
                **finding_figures(live.filtered(lambda f, s=st: f.stage_id == s)),
            })

        # ---------------- domain summaries (always the three domains)
        domains = []
        for key, label in MODEL_DOMAINS:
            dstages = all_stages.filtered(lambda s, k=key: s.azm_domain == k)
            agg = _empty()
            for a in assessments:
                for st in dstages:
                    _add(agg, scan[a.id, st.id])
            domains.append({
                'key': key, 'label': label, 'tone': DOMAIN_TONES[key], 'icon': DOMAIN_ICONS[key],
                'stages': len(dstages),
                'questions': sum(catalogue[s.id]['questions'] for s in dstages),
                'rules': sum(rules.get(s, 0) for s in dstages),
                'codes': dstages.mapped('code'),
                **self._om_rates(agg),
                **finding_figures(live.filtered(lambda f, ds=dstages: f.stage_id in ds)),
            })

        # ---------------- per assessment (domain filtered)
        kind_labels, scenario_labels = dict(PURCHASE_KINDS), dict(SCENARIOS)
        a_state_labels = dict(Assessment._fields['state']._description_selection(env))
        assessment_rows = []
        for a in assessments:
            agg = _empty()
            for st in stages:
                _add(agg, scan[a.id, st.id])
            assessment_rows.append({
                'id': a.id, 'name': a.name, 'entity': a.entity_id.name, 'entity_id': a.entity_id.id,
                'kind': kind_labels.get(a.purchase_kind, ''), 'scenario': scenario_labels.get(a.scenario, ''),
                'state': a.state, 'state_label': a_state_labels.get(a.state, a.state),
                'version': a.version, 'is_demo': a.is_demo,
                **self._om_rates(agg),
                'findings_open': len(open_findings.filtered(
                    lambda f, x=a: f.assessment_id == x and (not domain or f.azm_domain == domain))),
            })

        # ---------------- per entity
        entity_rows = []
        for entity in entities.filtered(lambda e: not entity_id or e.id == entity_id):
            rows = [r for r in assessment_rows if r['entity_id'] == entity.id]
            agg = _empty()
            for row in rows:
                _add(agg, row)
            approved = [r for r in rows if r['state'] == 'approved']
            entity_rows.append({
                'id': entity.id, 'code': entity.code, 'name': entity.name,
                'company': self._om_company(entity.company_id),
                'assessments': len(rows), 'approved': len(approved),
                'in_review': len([r for r in rows if r['state'] == 'review']),
                'assessment_id': rows[0]['id'] if len(rows) == 1 else False,
                **self._om_rates(agg),
                'findings_open': sum(r['findings_open'] for r in rows),
                'status': 'approved' if approved else ('in_progress' if rows else 'not_started'),
            })

        # ---------------- KPIs (domain filtered)
        total = _empty()
        for card in stage_cards:
            _add(total, card)
        scoped = live.filtered(lambda f: not domain or f.azm_domain == domain)
        states = {s: len(assessments.filtered(lambda a, s=s: a.state == s)) for s in ('draft', 'review', 'approved')}
        kpis = {
            'entities': len(entities),
            'entities_linked': len(entities.filtered('company_id')),
            'entities_covered': len({r['entity_id'] for r in assessment_rows}),
            'entities_approved': len([e for e in entity_rows if e['approved']]),
            'assessments': len(assessments),
            'draft': states['draft'], 'review': states['review'], 'approved': states['approved'],
            'versions': env['azm.assessment.version'].search_count([('assessment_id', 'in', in_scope.ids)]),
            'stages': len(stages),
            'questions': sum(c['questions'] for c in stage_cards),
            'rules': sum(c['rules'] for c in stage_cards),
            'common_questions': sum(c['common'] for c in stage_cards),
            **self._om_rates(total),
            **finding_figures(scoped),
        }

        # ---------------- charts
        findings_chart = [
            {'id': s, 'name': state_labels.get(s, s), 'color': FINDING_COLORS[s],
             'count': len(scoped.filtered(lambda f, s=s: f.state == s))}
            for s in FINDING_COLORS
        ]
        assessments_chart = [
            {'id': s, 'name': a_state_labels.get(s, s), 'color': ASSESSMENT_COLORS[s], 'count': states[s]}
            for s in ASSESSMENT_COLORS
        ]
        status_mix = dict.fromkeys(STAGE_STATUSES, 0)
        for card in stage_cards:
            if not card['governance']:
                for s in STAGE_STATUSES:
                    status_mix[s] += card['status_counts'][s]
        types_mix = {t: sum(c['types'][t] for c in stage_cards) for t in ('select', 'multi', 'number')}
        groups_mix = {g: sum(c['groups'][g] for c in stage_cards) for g in ('0', '1', '2')}

        top = scoped.filtered(lambda f: f.state in OPEN_FINDING_STATES).sorted(
            lambda f: (-f.score, f.stage_sequence, f.code))[:8]

        return {
            'available': True,
            'filters': {'entity_id': entity_id or False, 'assessment_id': assessment_id or False,
                        'domain': domain or False, 'company_id': company_id or False},
            'kpis': kpis,
            'domains': domains,
            'stages': stage_cards,
            'entities': entity_rows,
            'assessments': assessment_rows,
            'entity_options': [{'id': e.id, 'name': e.name} for e in entities],
            'assessment_options': [{'id': a.id, 'name': '%s · %s · %s' % (a.name, a.entity_id.name,
                                                                         kind_labels.get(a.purchase_kind, ''))}
                                   for a in in_scope],
            'charts': {
                'findings': findings_chart,
                'assessments': assessments_chart,
                'status': status_mix,
                'types': types_mix,
                'groups': {engine.GROUP_TITLES[g]: n for g, n in groups_mix.items()},
            },
            'top_findings': [self._om_finding_row(f, state_labels) for f in top],
            'is_manager': self.env.user.has_group('azm_operating_model.azm_group_manager'),
        }

    # ------------------------------------------------------------------
    # Home dashboard + entity page
    # ------------------------------------------------------------------
    @api.model
    def _om_summary(self, company_id=None):
        data = self.get_operating_model_data(company_id=company_id)
        if not data.get('available'):
            return False
        return {
            'kpis': data['kpis'],
            'domains': data['domains'],
            'entities': data['entities'],
            'assessments': data['assessments'][:6],
            'top_findings': data['top_findings'][:4],
            'findings_chart': data['charts']['findings'],
        }

    @api.model
    def get_dashboard_data(self):
        result = super().get_dashboard_data()
        result['om'] = self._om_summary()
        return result

    @api.model
    def get_company_overview(self, company_id):
        result = super().get_company_overview(company_id)
        if result:
            result['om'] = self._om_summary(company_id=company_id)
        return result
