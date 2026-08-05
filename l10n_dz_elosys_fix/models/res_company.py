# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ResCompany(models.Model):
    _inherit = 'res.company'

    # Correction du champ transfer_tax_journal - Suppression du default problématique
    transfer_tax_journal = fields.Many2one(
        "account.journal",
        string="Journal de transfert de taxe",
        help="Journal utilisé pour les transferts de taxes"
    )

    # Ajout d'une méthode pour définir un journal par défaut si nécessaire
    @api.model
    def _get_default_transfer_tax_journal(self, company_id):
        """Retourne un journal général par défaut pour la société donnée"""
        journal = self.env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', company_id)
        ], limit=1)
        return journal.id if journal else False


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    @api.model
    def get_values(self):
        """Correction : conversion des recordsets en IDs"""
        res = super(ResConfigSettings, self).get_values()
        company = self.env.company

        if company:
            res.update(
                transfer_tax_journal=company.transfer_tax_journal.id if company.transfer_tax_journal else False,
                temporary_tax_account=company.temporary_tax_account.id if company.temporary_tax_account else False,
                based_on=company.based_on,
                industry_id_in_invoice=company.industry_id_in_invoice,
                activity_code_in_invoice=company.activity_code_in_invoice,
                industry_id_in_quotation=company.industry_id_in_quotation,
                activity_code_in_quotation=company.activity_code_in_quotation,
            )
        return res

    def set_values(self):
        """Correction : conversion des recordsets en IDs avant écriture"""
        res = super(ResConfigSettings, self).set_values()
        company = self.env.company

        if company:
            vals = {
                'based_on': self.based_on,
                'industry_id_in_invoice': self.industry_id_in_invoice,
                'activity_code_in_invoice': self.activity_code_in_invoice,
                'industry_id_in_quotation': self.industry_id_in_quotation,
                'activity_code_in_quotation': self.activity_code_in_quotation,
            }

            # Gestion sécurisée des champs Many2one
            if self.transfer_tax_journal:
                vals['transfer_tax_journal'] = self.transfer_tax_journal.id
            else:
                vals['transfer_tax_journal'] = False

            if self.temporary_tax_account:
                vals['temporary_tax_account'] = self.temporary_tax_account.id
            else:
                vals['temporary_tax_account'] = False

            company.write(vals)

        return res

    @api.onchange('company_id')
    def _onchange_company_set_default_journal(self):
        """Définir automatiquement un journal par défaut si non défini"""
        if self.company_id and not self.company_id.transfer_tax_journal:
            default_journal_id = self.company_id._get_default_transfer_tax_journal(self.company_id.id)
            if default_journal_id:
                self.transfer_tax_journal = default_journal_id