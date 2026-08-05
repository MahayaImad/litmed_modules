# Copyright 2025 CPSS
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models, _


class CpssSyncLog(models.Model):
    _name = 'cpss.sync.log'
    _description = 'Synchronization Log'
    _order = 'create_date desc'

    # Informations de base
    operation_name = fields.Char(string="Operation", required=True)
    status = fields.Selection([
        ('success', 'Success'),
        ('error', 'Error'),
        ('warning', 'Warning'),
    ], string="Status", required=True, default='success')

    sync_type = fields.Selection([
        ('manual', 'Manual'),
        ('automatic', 'Automatic'),
    ], string="Sync Type", default='manual')

    # Messages d'erreur
    error_message = fields.Text(string="Error Message")
    operation_details = fields.Text(string="Operation Details")

    # Documents liés
    source_document_model = fields.Char(string="Source Model")
    source_document_id = fields.Integer(string="Source ID")
    source_document_name = fields.Char(string="Source Name")
    source_document_ref = fields.Reference(
        string="Source Document",
        selection='_get_models_selection'
    )

    target_document_model = fields.Char(string="Target Model")
    target_document_id = fields.Integer(string="Target ID")
    target_document_name = fields.Char(string="Target Name")
    target_document_ref = fields.Reference(
        string="Target Document",
        selection='_get_models_selection'
    )

    # Sociétés
    societe_operationnelle_id = fields.Many2one('res.company', string="Operational Company")
    societe_cible_id = fields.Many2one('res.company', string="Fiscal Company")

    # Dates
    start_time = fields.Datetime(string="Start Time", default=fields.Datetime.now)
    end_time = fields.Datetime(string="End Time")

    @api.model
    def _get_models_selection(self):
        """Modèles disponibles pour les références"""
        return [
            ('account.move', 'Invoice'),
            ('account.payment', 'Payment'),
        ]

    @api.model
    def _log_sync_event(self, operation_name, status, sync_type='manual',
                        error_msg=None, details=None, traceback=None,
                        source_doc=None, target_doc=None, config=None):
        """
        Méthode utilitaire pour enregistrer un événement de synchronisation
        """
        vals = {
            'operation_name': operation_name,
            'status': status,
            'sync_type': sync_type,
            'error_message': error_msg,
            'operation_details': details,
            'end_time': fields.Datetime.now(),
        }

        # Informations du document source
        if source_doc:
            vals.update({
                'source_document_model': source_doc._name,
                'source_document_id': source_doc.id,
                'source_document_name': source_doc.display_name,
                'source_document_ref': f"{source_doc._name},{source_doc.id}",
            })

        # Informations du document cible
        if target_doc:
            vals.update({
                'target_document_model': target_doc._name,
                'target_document_id': target_doc.id,
                'target_document_name': target_doc.display_name,
                'target_document_ref': f"{target_doc._name},{target_doc.id}",
            })

        # Sociétés impliquées
        if config:
            vals.update({
                'societe_operationnelle_id': config.societe_operationnelle_id.id,
                'societe_cible_id': config.societe_cible_id.id,
            })

        return self.create(vals)