# Copyright 2025 CPSS
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import SUPERUSER_ID, api, fields, models, registry

_logger = logging.getLogger(__name__)


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
    ], string="Status", required=True, default='success', index=True)

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
    def _prepare_sync_log_vals(self, operation_name, status, sync_type='manual',
                               error_msg=None, details=None,
                               source_doc=None, target_doc=None, config=None):
        """Construit les valeurs d'un log à partir des enregistrements liés."""
        vals = {
            'operation_name': operation_name,
            'status': status,
            'sync_type': sync_type,
            'error_message': error_msg,
            'operation_details': details,
            'end_time': fields.Datetime.now(),
        }

        for doc, prefixe in ((source_doc, 'source'), (target_doc, 'target')):
            if not doc:
                continue
            vals.update({
                '%s_document_model' % prefixe: doc._name,
                '%s_document_id' % prefixe: doc.id,
                '%s_document_name' % prefixe: doc.display_name,
                '%s_document_ref' % prefixe: "%s,%s" % (doc._name, doc.id),
            })

        if config:
            vals.update({
                'societe_operationnelle_id': config.societe_operationnelle_id.id,
                'societe_cible_id': config.societe_cible_id.id,
            })

        return vals

    @api.model
    def _log_sync_event(self, **kwargs):
        """Enregistre un événement dans la transaction courante.

        À réserver aux succès : en cas d'erreur la transaction est annulée et
        le log disparaîtrait avec elle (voir `_log_sync_event_isolated`).
        """
        return self.create(self._prepare_sync_log_vals(**kwargs))

    @api.model
    def _log_sync_event_isolated(self, **kwargs):
        """Enregistre un événement dans une transaction dédiée.

        Un `raise` annule toute la transaction Odoo : un log d'erreur écrit
        sur le curseur courant serait annulé en même temps que l'opération
        qui a échoué. On utilise donc un curseur séparé, validé indépendamment.
        """
        try:
            vals = self._prepare_sync_log_vals(**kwargs)
        except Exception:
            # Le curseur courant peut être inutilisable (erreur SQL en amont) :
            # on retombe sur les seules informations déjà disponibles.
            _logger.exception("Préparation du log de synchronisation impossible")
            vals = {
                'operation_name': kwargs.get('operation_name') or 'Synchronisation',
                'status': kwargs.get('status') or 'error',
                'sync_type': kwargs.get('sync_type') or 'manual',
                'error_message': kwargs.get('error_msg'),
            }

        try:
            with registry(self.env.cr.dbname).cursor() as cr:
                api.Environment(cr, SUPERUSER_ID, {})['cpss.sync.log'].create(vals)
        except Exception:
            # Le log ne doit jamais masquer l'erreur d'origine.
            _logger.exception(
                "Écriture du log de synchronisation impossible : %s",
                vals.get('error_message'))
            return False
        return True
