from odoo import models
import logging

_logger = logging.getLogger(__name__)


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    def load_menus(self, debug):
        menus = super().load_menus(debug)

        config = self.env['cpss.sync.config'].search([], limit=1)

        _logger.warning(
            "LOAD MENUS company: %s (%s)",
            self.env.company.name,
            self.env.company.id
        )

        if config and self.env.company.id == config.societe_cible_id.id:

            menu = self.env.ref(
                'cpss_sync_inter_company_base.menu_sync_main',
                raise_if_not_found=False
            )

            if menu:
                _logger.warning("Removing menu: %s", menu.name)

                # remove from loaded menu dictionary
                menus['root'].pop(menu.id, None)

        return menus