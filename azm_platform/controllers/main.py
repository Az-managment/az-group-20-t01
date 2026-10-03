from odoo import http
from odoo.http import request

from odoo.addons.web.controllers.home import Home


class AzmHome(Home):
    """Login page language: ?lang=xx is remembered; Arabic is the default when installed."""

    def _azm_login_lang(self):
        installed = dict(request.env['res.lang'].sudo().get_installed())
        lang = request.params.get('lang')
        if lang and lang in installed:
            request.session['azm_login_lang'] = lang
        lang = request.session.get('azm_login_lang')
        if not lang:
            lang = next((code for code in installed if code.startswith('ar')), None)
        if lang and lang in installed:
            request.update_context(lang=lang)

    @http.route()
    def web_login(self, redirect=None, **kw):
        if request.db:
            self._azm_login_lang()
        return super().web_login(redirect=redirect, **kw)

    @http.route('/azm/language', type='jsonrpc', auth='user', methods=['POST'])
    def azm_set_language(self, lang):
        """Put the current user, and the running session, on that language.

        res.users.lang is writeable by its own user, but writing it is not
        enough on its own: the session keeps the context it built when the user
        logged in, and the language the pages and the assets are rendered in is
        read from there. Written alone, the preference would only take effect
        at the next login. The caller reloads once this returns.
        """
        if lang not in dict(request.env['res.lang'].sudo().get_installed()):
            return False
        request.env.user.write({'lang': lang})
        # Assign the key: the session only notices a change through __setitem__,
        # so mutating the context dictionary in place would never be persisted.
        request.session['context'] = {**request.session.context, 'lang': lang}
        return True
