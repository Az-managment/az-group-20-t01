from odoo import api, models


class AzmDashboard(models.AbstractModel):
    _inherit = 'azm.dashboard'

    @api.model
    def get_operating_models_hub(self, company_id=None):
        """Landing page of the operating models: one 'file' per model with its KPIs,
        group totals and an entity x model comparison. Follows the user's access rights."""
        proc = self.get_operating_model_data(company_id=company_id)
        fin = self.get_financial_model_data(company_id=company_id) if 'azm.fin.assessment' in self.env else {}
        cards = []
        if proc.get('available'):
            k = proc['kpis']
            cards.append({
                'key': 'procurement', 'icon': 'shopping_cart', 'tone': 'blue',
                'name': 'Procurement cycle', 'name_ar': 'دورة المشتريات',
                'description': 'From the purchase request to closing: policy, procedure, authority and risks.',
                'units': len(proc['stages']), 'unit_label': 'stages', 'items': k['questions'], 'item_label': 'questions',
                'assessments': k['assessments'], 'approved': k['approved'], 'review': k['review'], 'draft': k['draft'],
                'completion': k['completion'], 'quality': k['certainty'], 'quality_label': 'Answer certainty',
                'issues': k['findings_open'], 'issues_label': 'Open findings', 'issues_sub': k['findings_high'],
                'issues_sub_label': 'high', 'entities_covered': k['entities_covered'], 'entities': k['entities'],
                'parts': [{'code': d['key'], 'label': d['label'], 'completion': d['completion'], 'count': d['stages']}
                          for d in proc['domains']],
                'action': 'azm_platform.action_azm_om_dashboard',
            })
        if fin.get('available'):
            k = fin['kpis']
            cards.append({
                'key': 'financial', 'icon': 'payments', 'tone': 'green',
                'name': 'Unified financial model', 'name_ar': 'النموذج المالي الموحد',
                'description': 'Inventory of the financial requirements of each entity and design of the target model.',
                'units': k['modules'], 'unit_label': 'modules', 'items': k['requirements'], 'item_label': 'requirements',
                'assessments': k['assessments'], 'approved': k['approved'], 'review': k['review'], 'draft': k['draft'],
                'completion': k['completion'], 'quality': k['maturity'], 'quality_label': 'Maturity',
                'issues': k['gaps'], 'issues_label': 'Gaps', 'issues_sub': k['na'], 'issues_sub_label': 'not applicable',
                'entities_covered': k['entities_covered'], 'entities': k['entities'],
                'parts': [{'code': 'FIN', 'label': 'Finance', 'count': k['fin_requirements'], 'completion': None},
                          {'code': 'HRF', 'label': 'HR finance', 'count': k['hrf_requirements'], 'completion': None}],
                'action': 'azm_platform.action_azm_fin_dashboard',
            })

        # entity x model comparison
        rows = {}
        for e in proc.get('entities', []):
            rows[e['id']] = {'id': e['id'], 'code': e['code'], 'name': e['name'], 'company': e['company'],
                             'procurement': {'assessments': e['assessments'], 'completion': e['completion'],
                                             'issues': e['findings_open'], 'status': e['status']},
                             'financial': False}
        for e in fin.get('entities', []):
            row = rows.setdefault(e['id'], {'id': e['id'], 'code': e['code'], 'name': e['name'], 'company': e['company'],
                                            'procurement': False})
            row['financial'] = {'assessments': e['assessments'], 'completion': e['completion'],
                                'issues': e['gaps'], 'status': e['status']}

        def weighted(key):
            parts = [(c[key], c['assessments']) for c in cards if c[key] is not None and c['assessments']]
            total = sum(w for _v, w in parts)
            return round(sum(v * w for v, w in parts) / total, 1) if total else None

        totals = {
            'models': len(cards),
            'assessments': sum(c['assessments'] for c in cards),
            'approved': sum(c['approved'] for c in cards),
            'items': sum(c['items'] for c in cards),
            'units': sum(c['units'] for c in cards),
            'completion': weighted('completion'),
            'issues': sum(c['issues'] for c in cards),
            'entities': max([c['entities'] for c in cards] or [0]),
            'entities_covered': len({r['id'] for r in rows.values()
                                     if (r['procurement'] and r['procurement']['assessments'])
                                     or (r['financial'] and r['financial']['assessments'])}),
        }
        return {'available': bool(cards), 'models': cards, 'totals': totals, 'entities': list(rows.values())}
