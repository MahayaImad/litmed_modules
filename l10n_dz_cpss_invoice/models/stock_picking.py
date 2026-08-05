# Dans votre fichier Python (models/stock_picking.py)
from odoo import models, api
from num2words import num2words  # Installer: pip install num2words


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def custom_amount_to_text(self, amount):
        """Convertit le montant en lettres"""
        currency_id = self.currency_id or self.env.ref('base.DZD')
        if not amount:
            return "ZÉRO"

        try:
            # Convertir en français
            amount_text = currency_id.amount_to_text(amount)
            if round(amount % 1, 2) == 0.0:
                amount_text += " et zéro centime"
            if amount > 1.0:
                amount_text = amount_text.replace('Dinar', 'Dinars')
            return amount_text.lower().capitalize()
        except:
            return f"{amount:.2f} {currency_id}"


