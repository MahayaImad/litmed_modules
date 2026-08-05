from odoo import models
from odoo.tools.misc import format_date


class AccountMove(models.Model):
    _inherit = "account.move"

    def _get_invoiced_lot_values_with_expiry(self):
        result = self._get_invoiced_lot_values()

        lot_ids = [
            l['lot_id']
            for l in result
            if l.get('lot_id')
        ]

        lots = {
            lot.id: lot
            for lot in self.env['stock.lot'].browse(lot_ids)
        }

        for data in result:
            lot = lots.get(data.get('lot_id'))

            data['expiration_date'] = (
                lot.expiration_date if lot else False
            )

            data['use_expiration_date'] = (
                lot.use_expiration_date if lot else False
            )
            if lot and lot.expiration_date:
                data['expiration_date_display'] = lot.expiration_date.strftime('%m-%Y')
            else:
                data['expiration_date_display'] = ''

        return result