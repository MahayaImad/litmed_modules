from odoo import models, fields

class StockLot(models.Model):
    _inherit = 'stock.lot'

    manufacturing_date = fields.Date(
        string='Date de Fabrication',
        help="Date de fabrication du lot"
    )