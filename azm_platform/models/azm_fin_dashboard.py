from collections import Counter

from odoo import api, models

from odoo.addons.azm_operating_model.models.azm_fin_catalogue import PROFILES, SCOPES, STATES

STATE_COLORS = {'full': '#16a34a', 'partial': '#f59e0b', 'unavailable': '#64748b', 'na': '#cbd5e1',
                'open': '#e2e8f0'}
ASSESSMENT_COLORS = {'draft': '#94a3b8', 'review': '#f59e0b', 'approved': '#16a34a'}
PROFILE_COLORS = {'L': '#5b7fa6', 'C': '#c08a1e', 'W': '#1f9d92', 'A': '#c0504d', 'R': '#7c5cd6',
                  'I': '#1f8ec7', 'P': '#3a9a5f'}


def _pct(part, whole):
    return round(100.0 * part / whole, 1) if whole else None


def _figures(answers):
    """Counts over a recordset of azm.fin.answer (only applicable lines are passed in)."""
    states = Counter(a.state or 'open' for a in answers)
    answered = len(answers) - states['open']
    done = len(answers.filtered('is_done'))
    implemented = states['full'] + states['partial'] + states['unavailable']
    return {
        'applicable': len(answers),
        'done': done,
        'answered': answered,
        'full': states['full'], 'partial': states['partial'],
        'unavailable': states['unavailable'], 'na': states['na'], 'open': states['open'],
        'gaps': states['partial'] + states['unavailable'],
        'completion': _pct(done, len(answers)),
        # maturity: share of the requirements that exist (not N/A) which are fully applied
        'maturity': _pct(states['full'], implemented),
    }


class AzmDashboard(models.AbstractModel):
    _inherit = 'azm.dashboard'

    @api.model
    def _fin_available(self):
        return 'azm.fin.assessment' in self.env and self.env['azm.fin.assessment'].has_access('read')

    @api.model
    def get_financial_model_data(self, entity_id=None, assessment_id=None, company_id=None, source=None,
                                 profile=None):
        """Unified financial model page: KPIs, one card per module, charts, entities, gaps.

        Every figure follows the user's access rights and the company switcher.
        source = 'FIN' / 'HRF' narrows to finance or HR-finance requirements, profile to one answer template.
        """
        if not self._fin_available():
            return {'available': False}
        env = self._env_all_companies()
        entity_domain = ([('company_id', '=', company_id)] if company_id else
                         ['|', ('company_id', '=', False), ('company_id', 'in', env.companies.ids)])
        entities = env['azm.entity'].search(entity_domain)
        Assessment = env['azm.fin.assessment']
        scope = [('state', '!=', 'archived'), ('entity_id', 'in', entities.ids)]
        if entity_id:
            scope.append(('entity_id', '=', entity_id))
        in_scope = Assessment.search(scope)
        assessments = in_scope.filtered(lambda a: a.id == assessment_id) if assessment_id else in_scope
        if not assessments and assessment_id:
            assessments, assessment_id = in_scope, None

        req_domain = []
        if source:
            req_domain.append(('source', '=', source))
        if profile:
            req_domain.append(('profile', '=', profile))
        requirements = env['azm.fin.requirement'].search(req_domain)
        all_answers = env['azm.fin.answer'].search([('assessment_id', 'in', assessments.ids),
                                                    ('requirement_id', 'in', requirements.ids)])
        answers = all_answers.filtered('applicable')

        # ---------------- one card per module
        modules = env['azm.fin.module'].search([])
        cards = []
        for module in modules:
            reqs = requirements.filtered(lambda r, m=module: r.module_id == m)
            lines = answers.filtered(lambda a, m=module: a.module_id == m)
            fig = _figures(lines)
            profiles = Counter(reqs.mapped('profile'))
            scopes = Counter(reqs.mapped('scope_code'))
            cards.append({
                'code': module.code, 'name': module.name,
                'requirements': len(reqs),
                'fin': len(reqs.filtered(lambda r: r.source == 'FIN')),
                'hrf': len(reqs.filtered(lambda r: r.source == 'HRF')),
                'profiles': [{'key': k, 'count': profiles[k], 'color': PROFILE_COLORS[k]} for k in PROFILES if profiles[k]],
                'scopes': [{'key': k, 'name': SCOPES[k], 'count': scopes[k]} for k in SCOPES if scopes[k]],
                **fig,
                'status': ('not_applicable' if not fig['applicable'] and assessments else
                           'complete' if fig['applicable'] and fig['done'] == fig['applicable'] else
                           'in_progress' if fig['answered'] else 'not_started'),
            })

        # ---------------- KPIs
        total = _figures(answers)
        states = Counter(assessments.mapped('state'))
        kpis = {
            'assessments': len(assessments),
            'draft': states['draft'], 'review': states['review'], 'approved': states['approved'],
            'modules': len([c for c in cards if c['requirements']]),
            'requirements': len(requirements),
            'fin_requirements': len(requirements.filtered(lambda r: r.source == 'FIN')),
            'hrf_requirements': len(requirements.filtered(lambda r: r.source == 'HRF')),
            'entities': len(entities),
            'entities_covered': len(assessments.entity_id),
            'entities_approved': len(assessments.filtered(lambda a: a.state == 'approved').entity_id),
            'evidence': len(answers.filtered('attachment_ids')),
            **total,
        }

        # ---------------- charts
        state_labels = dict(STATES)
        state_chart = [{'id': k, 'name': state_labels.get(k, 'لم تتم الإجابة'), 'color': STATE_COLORS[k],
                        'count': total[k]} for k in ('full', 'partial', 'unavailable', 'na', 'open')]
        a_labels = dict(Assessment._fields['state']._description_selection(env))
        assessment_chart = [{'id': s, 'name': a_labels.get(s, s), 'color': c, 'count': states[s]}
                            for s, c in ASSESSMENT_COLORS.items()]
        prof_req = Counter(requirements.mapped('profile'))
        prof_gap = Counter(answers.filtered(lambda a: a.state in ('partial', 'unavailable')).mapped('profile'))
        profile_rows = [{'key': k, 'name': PROFILES[k][0], 'en': PROFILES[k][1], 'color': PROFILE_COLORS[k],
                         'requirements': prof_req[k], 'gaps': prof_gap[k]} for k in PROFILES]
        scope_req = Counter(requirements.mapped('scope_code'))
        scope_rows = [{'key': k, 'name': SCOPES[k], 'requirements': scope_req[k]} for k in SCOPES if scope_req[k]]

        # ---------------- per assessment / entity
        a_rows = []
        for a in assessments:
            fig = _figures(answers.filtered(lambda x, a=a: x.assessment_id == a))
            a_rows.append({'id': a.id, 'name': a.name, 'entity': a.entity_id.name, 'entity_id': a.entity_id.id,
                           'state': a.state, 'state_label': a_labels.get(a.state, a.state), 'version': a.version,
                           'is_demo': a.is_demo, 'scopes': a.scope_ids.mapped('name'), **fig})
        e_rows = []
        for entity in entities.filtered(lambda e: not entity_id or e.id == entity_id):
            rows = [r for r in a_rows if r['entity_id'] == entity.id]
            fig = _figures(answers.filtered(lambda x, e=entity: x.assessment_id.entity_id == e))
            e_rows.append({
                'id': entity.id, 'code': entity.code, 'name': entity.name,
                'company': self._om_company(entity.company_id),
                'scopes': entity.fin_scope_ids.mapped('name'),
                'assessments': len(rows), 'assessment_id': rows[0]['id'] if len(rows) == 1 else False,
                'approved': len([r for r in rows if r['state'] == 'approved']),
                'status': ('approved' if any(r['state'] == 'approved' for r in rows) else
                           'in_progress' if rows else 'not_started'),
                **fig,
            })

        gaps = answers.filtered(lambda a: a.state == 'partial' and a.gap).sorted(
            lambda a: (a.module_sequence, a.requirement_sequence))[:8]
        top_gaps = [{'id': a.id, 'code': a.code, 'title': a.requirement_id.title, 'module': a.module_id.name,
                     'module_code': a.module_id.code, 'entity': a.entity_id.name, 'gap': a.gap,
                     'assessment_id': a.assessment_id.id} for a in gaps]

        return {
            'available': True,
            'filters': {'entity_id': entity_id or False, 'assessment_id': assessment_id or False,
                        'company_id': company_id or False, 'source': source or False, 'profile': profile or False},
            'kpis': kpis,
            'modules': cards,
            'profiles': profile_rows,
            'scopes': scope_rows,
            'charts': {'states': state_chart, 'assessments': assessment_chart},
            'entities': e_rows,
            'assessments': a_rows,
            'top_gaps': top_gaps,
            'entity_options': [{'id': e.id, 'name': e.name} for e in entities],
            'assessment_options': [{'id': a.id, 'name': f'{a.name} · {a.entity_id.name}'} for a in in_scope],
            'is_manager': self.env.user.has_group('azm_operating_model.azm_group_manager'),
        }

    @api.model
    def _fin_summary(self, company_id=None):
        data = self.get_financial_model_data(company_id=company_id)
        if not data.get('available'):
            return False
        return {
            'kpis': data['kpis'],
            'modules': [{k: m[k] for k in ('code', 'name', 'requirements', 'applicable', 'done', 'completion',
                                           'gaps', 'status')} for m in data['modules']],
            'assessments': data['assessments'][:6],
            'top_gaps': data['top_gaps'][:4],
            'states_chart': data['charts']['states'],
        }

    @api.model
    def get_dashboard_data(self):
        result = super().get_dashboard_data()
        result['fin'] = self._fin_summary()
        return result

    @api.model
    def get_company_overview(self, company_id):
        result = super().get_company_overview(company_id)
        if result:
            result['fin'] = self._fin_summary(company_id=company_id)
        return result
