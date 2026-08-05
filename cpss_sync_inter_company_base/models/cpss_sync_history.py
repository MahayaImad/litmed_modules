# Copyright 2025 CPSS
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models, _


class CpssSyncHistory(models.Model):
    _name = 'cpss.sync.history'
    _description = 'Synchronization History'
    _order = 'create_date desc'

    # Informations de base
    operation_type = fields.Selection([
        ('invoice_sync', 'Invoice Synchronization'),
    ], string="Operation Type", required=True)

    status = fields.Selection([
        ('success', 'Success'),
        ('error', 'Error'),
    ], string="Status", required=True)

    # Documents impliqués
    source_move_id = fields.Many2one('account.move', string="Source Invoice")
    fiscal_move_id = fields.Many2one('account.move', string="Fiscal Invoice")

    # Détails
    sync_details = fields.Text(string="Sync Details")
    error_message = fields.Text(string="Error Message")

    # Utilisateur et dates
    sync_user_id = fields.Many2one('res.users', string="Sync User", default=lambda self: self.env.user)
    sync_date = fields.Datetime(string="Sync Date", default=fields.Datetime.now)
