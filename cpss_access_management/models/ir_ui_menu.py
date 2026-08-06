# -*- coding: utf-8 -*-
from odoo import api, models


class IrUiMenu(models.Model):
    """Removes the menus hidden by an access rule.

    Two entry points are needed. ``_load_menus_blacklist`` is the hook Odoo
    provides for exactly this purpose and is called from ``load_menus``, which
    is cached per user. ``_visible_menu_ids`` is cached on the *group set* of
    the user instead, so it is wrapped from the outside: filtering inside it
    would leak the restrictions to every user sharing the same groups.
    """
    _inherit = 'ir.ui.menu'

    def _load_menus_blacklist(self):
        return super()._load_menus_blacklist() + list(self._cpss_hidden_menu_ids())

    @api.model
    def _visible_menu_ids(self, debug=False):
        visible = super()._visible_menu_ids(debug)
        hidden = self._cpss_hidden_menu_ids()
        return visible - set(hidden) if hidden else visible

    @api.model
    def _cpss_hidden_menu_ids(self):
        return self.env['cpss.access.resolver']._get_user_restrictions()['menus']
