# Copyright 2025 CPSS
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class CpssSyncTaxMapping(models.Model):
    _name = 'cpss.sync.tax.mapping'
    _description = 'Correspondance de Taxe Inter-Sociétés'
    _rec_name = 'taxe_source_id'

    config_id = fields.Many2one(
        'cpss.sync.config', string="Configuration",
        required=True, ondelete='cascade', index=True)
    taxe_source_id = fields.Many2one(
        'account.tax', string="Taxe (Société Opérationnelle)",
        required=True, ondelete='cascade', check_company=False)
    taxe_cible_id = fields.Many2one(
        'account.tax', string="Taxe (Société Cible)",
        required=True, ondelete='cascade', check_company=False)

    _sql_constraints = [
        ('taxe_source_unique',
         'unique(config_id, taxe_source_id)',
         "Une seule correspondance par taxe d'origine."),
    ]

    @api.constrains('taxe_source_id', 'taxe_cible_id')
    def _check_societes(self):
        for mapping in self:
            config = mapping.config_id
            if mapping.taxe_source_id.company_id != config.societe_operationnelle_id:
                raise ValidationError(_(
                    "La taxe d'origine « %(taxe)s » doit appartenir à la "
                    "société opérationnelle %(societe)s."
                ) % {'taxe': mapping.taxe_source_id.display_name,
                     'societe': config.societe_operationnelle_id.name})
            if mapping.taxe_cible_id.company_id != config.societe_cible_id:
                raise ValidationError(_(
                    "La taxe cible « %(taxe)s » doit appartenir à la société "
                    "cible %(societe)s."
                ) % {'taxe': mapping.taxe_cible_id.display_name,
                     'societe': config.societe_cible_id.name})


class CpssSyncAccountMapping(models.Model):
    _name = 'cpss.sync.account.mapping'
    _description = 'Correspondance de Compte Inter-Sociétés'
    _rec_name = 'compte_source_id'

    config_id = fields.Many2one(
        'cpss.sync.config', string="Configuration",
        required=True, ondelete='cascade', index=True)
    compte_source_id = fields.Many2one(
        'account.account', string="Compte (Société Opérationnelle)",
        required=True, ondelete='cascade', check_company=False)
    compte_cible_id = fields.Many2one(
        'account.account', string="Compte (Société Cible)",
        required=True, ondelete='cascade', check_company=False)

    _sql_constraints = [
        ('compte_source_unique',
         'unique(config_id, compte_source_id)',
         "Une seule correspondance par compte d'origine."),
    ]

    @api.constrains('compte_source_id', 'compte_cible_id')
    def _check_societes(self):
        for mapping in self:
            config = mapping.config_id
            if mapping.compte_source_id.company_id != config.societe_operationnelle_id:
                raise ValidationError(_(
                    "Le compte d'origine « %(compte)s » doit appartenir à la "
                    "société opérationnelle %(societe)s."
                ) % {'compte': mapping.compte_source_id.display_name,
                     'societe': config.societe_operationnelle_id.name})
            if mapping.compte_cible_id.company_id != config.societe_cible_id:
                raise ValidationError(_(
                    "Le compte cible « %(compte)s » doit appartenir à la "
                    "société cible %(societe)s."
                ) % {'compte': mapping.compte_cible_id.display_name,
                     'societe': config.societe_cible_id.name})
