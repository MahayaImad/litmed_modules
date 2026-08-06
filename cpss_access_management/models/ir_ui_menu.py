# -*- coding: utf-8 -*-
from odoo import api, models


class IrUiMenu(models.Model):
    """Removes the menus hidden by an access rule.

    Odoo caches the menu tree twice, and both caches are keyed on the *group
    set* of the user, never on the user. Everything below exists to filter
    around those caches instead of inside them.
    """
    _inherit = 'ir.ui.menu'

    @api.model
    def _visible_menu_ids(self, debug=False):
        """Filter the menus a search may return, for the current user.

        ``super()`` is cached on the group set, so the subtraction is done
        here, outside that cache. It is skipped entirely while ``load_menus``
        runs: that method is cached on the group set too, and it calls this
        one internally, so filtering there would bake the first user's
        restrictions into a tree served to everybody sharing their groups.
        """
        visible = super()._visible_menu_ids(debug)
        if self.env.context.get('cpss_menu_no_filter'):
            return visible
        hidden = self._cpss_hidden_menu_ids()
        return visible - set(hidden) if hidden else visible

    @api.model
    def load_menus(self, debug):
        # The tree is built unfiltered, so what lands in the shared cache is
        # the same for every user of the group set, then filtered per user.
        menus = super(
            IrUiMenu, self.with_context(cpss_menu_no_filter=True)
        ).load_menus(debug)
        hidden = self._cpss_hidden_menu_ids()
        if not hidden:
            return menus
        return self._cpss_filter_loaded_menus(menus, hidden)

    @api.model
    def _cpss_filter_loaded_menus(self, menus, hidden):
        """Return a copy of ``menus`` without the hidden entries.

        ``load_menus`` returns ``{'root': {...}, menu_id: {...}}`` where every
        entry lists its children by id. The entries, the children lists and
        the flat index of the root all have to be rebuilt — a hidden menu
        still referenced by its parent would leave a dead entry in the tree.

        A menu emptied by the filtering is dropped in turn: hiding the only
        sub-menu of an application would otherwise leave the application in
        place, opening on nothing. The pass is repeated until nothing moves,
        so that a whole emptied branch collapses.

        The dictionary is copied and never mutated: it comes straight from a
        cache shared by every user of the group set.
        """
        filtered = {
            key: dict(menu) for key, menu in menus.items()
            if self._cpss_identifiant_menu(key) not in hidden
        }
        supprimes = set(hidden)
        while True:
            for menu in filtered.values():
                for cle in ('children', 'all_menu_ids'):
                    identifiants = menu.get(cle)
                    if identifiants:
                        menu[cle] = [
                            identifiant for identifiant in identifiants
                            if identifiant not in supprimes]
            vides = {
                key for key, menu in filtered.items()
                if self._cpss_identifiant_menu(key) is not None
                and not menu.get('action')
                and not menu.get('children')
            }
            if not vides:
                return filtered
            for key in vides:
                del filtered[key]
                supprimes.add(self._cpss_identifiant_menu(key))

    @api.model
    def _cpss_identifiant_menu(self, cle):
        """Identifiant de menu porté par une clé de l'arbre.

        Les clés sont des identifiants, sauf ``'root'``. Elles sont converties
        plutôt que comparées telles quelles : la structure vient d'Odoo et le
        type exact des clés n'est pas garanti d'une version à l'autre, alors
        que les identifiants masqués sont toujours des entiers.
        """
        try:
            return int(cle)
        except (TypeError, ValueError):
            return None

    @api.model
    def _cpss_hidden_menu_ids(self):
        return self.env['cpss.access.resolver']._get_user_restrictions()['menus']
