from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'

    company_stamp = fields.Binary(
        string="Cachet de la Société",
        help="Télécharger le cachet de la société à afficher sur les factures"
    )

    second_logo = fields.Binary(
        string="Deuxième Logo",
        help="Deuxième logo à afficher au centre de l'en-tête de la facture"
    )