# -*- coding: utf-8 -*-
from odoo import api, models


class IrUiMenu(models.Model):
    """Removes the menus hidden by an access rule.

    Two entry points are needed, and both are wrapped from the *outside* of
    the native caches:

    * ``_visible_menu_ids`` is the hook every menu search goes through, but it
      is cached on the group set of the user. Filtering inside it would leak
      one user's restrictions to every user sharing the same groups.
    * ``load_menus`` builds the menu tree of the web client and is cached on
      the group set too — and, unlike our restrictions, not on the company.
      Its cached result is therefore filtered here, on a copy: mutating the
      dictionary returned by the cache would corrupt it for everybody.
    """
    _inherit = 'ir.ui.menu'

    @api.model
    def _visible_menu_ids(self, debug=False):
        visible = super()._visible_menu_ids(debug)
        hidden = self._cpss_hidden_menu_ids()
        return visible - set(hidden) if hidden else visible

    @api.model
    def load_menus(self, debug):
        menus = super().load_menus(debug)
        hidden = self._cpss_hidden_menu_ids()
        if not hidden:
            return menus
        return self._cpss_filter_loaded_menus(menus, hidden)

    @api.model
    def _cpss_filter_loaded_menus(self, menus, hidden):
        """Return a copy of ``menus`` without the hidden entries.

        ``load_menus`` returns ``{'root': {...}, menu_id: {...}}`` where every
        entry lists its children by id. Both the entries and the children
        lists have to be rebuilt, otherwise a hidden menu would still be
        referenced by its parent and the client would fail to resolve it.
        """
        filtered = {}
        for key, menu in menus.items():
            if key != 'root' and key in hidden:
                continue
            menu = dict(menu)
            children = menu.get('children')
            if children:
                menu['children'] = [
                    child for child in children if child not in hidden]
            filtered[key] = menu
        return filtered

    @api.model
    def _cpss_hidden_menu_ids(self):
        return self.env['cpss.access.resolver']._get_user_restrictions()['menus']
