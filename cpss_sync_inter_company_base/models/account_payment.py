# Copyright 2025 CPSS
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .cpss_sync_config import GROUPE_SYNC_ADMIN, verifier_groupe_sync

_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    partage = fields.Selection([
        ('not_shared', 'Non Partagé'),
        ('shared', 'Partagé'),
        ('error', 'Erreur de Partage'),
    ], string="État de Partage", default='not_shared', copy=False, readonly=True,
        index=True, tracking=True,
        help="Indique l'état de partage du paiement avec la société cible")

    paiement_societe_cible_id = fields.Many2one(
        'account.payment',
        string="Paiement Société Cible",
        copy=False,
        readonly=True,
        check_company=False,
        help="Le paiement correspondant dans la société cible"
    )

    paiement_origine_operationnelle_id = fields.Many2one(
        'account.payment',
        string="Paiement Origine",
        copy=False,
        readonly=True,
        index=True,
        check_company=False,
        help="Le paiement d'origine de la société opérationnelle"
    )

    is_operational_company = fields.Boolean(
        string="Est Société Opérationnelle",
        compute="_compute_is_operational_company",
        store=False,
        help="Détermine si ce paiement appartient à la société opérationnelle"
    )

    partage_error_message = fields.Text(
        string="Message d'erreur",
        readonly=True,
        copy=False,
        help="Détails de l'erreur lors du partage"
    )

    @api.depends('company_id')
    def _compute_is_operational_company(self):
        """Détermine si le paiement appartient à la société opérationnelle"""
        societe_operationnelle = self.env['cpss.sync.config']._get_societe_operationnelle()
        for payment in self:
            payment.is_operational_company = bool(societe_operationnelle) \
                and payment.company_id == societe_operationnelle

    def action_post(self):
        """Synchronise les paiements rapprochés avec une facture déjà partagée.

        Ce point d'entrée ne couvre que les paiements déjà rapprochés au
        moment de la validation. Les paiements rapprochés plus tard sont
        rattrapés lors du partage de la facture
        (`account.move._synchroniser_paiements_rapproches`).
        """
        res = super().action_post()

        for payment in self:
            if not payment.is_operational_company:
                continue
            if payment.partage in ('shared', 'error'):
                continue
            if not payment._doit_etre_partage():
                continue

            try:
                # Savepoint indispensable : sans lui, une erreur SQL laisserait
                # le curseur inutilisable et ferait échouer la validation du
                # paiement elle-même.
                with self.env.cr.savepoint():
                    payment._synchroniser_paiement_automatique()
            except Exception as error:
                _logger.exception("Échec du partage automatique du paiement %s",
                                  payment.name)
                payment.write({
                    'partage': 'error',
                    'partage_error_message': str(error),
                })

        return res

    def _doit_etre_partage(self):
        """Vérifie si le paiement doit être partagé"""
        self.ensure_one()
        if not self.reconciled_invoice_ids:
            return False
        return any(facture.partage == 'shared'
                   for facture in self.reconciled_invoice_ids)

    # ------------------------------------------------------------------
    # PARTAGE
    # ------------------------------------------------------------------
    def _partager_paiement(self, config, sync_type):
        """Crée le paiement correspondant dans la société cible.

        Cœur commun aux partages manuel et automatique.
        """
        self.ensure_one()

        ctx_fiscal = {
            'allowed_company_ids': [config.societe_cible_id.id],
            'check_move_validity': False,
        }
        self_sync = self.with_company(config.societe_cible_id) \
            .with_context(**ctx_fiscal).sudo()

        paiement_cible = self_sync._creer_paiement_cible(config)

        self.write({
            'partage': 'shared',
            'paiement_societe_cible_id': paiement_cible.id,
            'partage_error_message': False,
        })

        self.env['cpss.sync.log'].sudo()._log_sync_event(
            operation_name='Synchronisation Paiement',
            status='success',
            sync_type=sync_type,
            source_doc=self,
            target_doc=paiement_cible,
            config=config,
            details="Montant: %s %s" % (self.amount, self.currency_id.name),
        )
        self._message_log(body=_("✅ Paiement partagé avec la société cible : %s")
                          % paiement_cible.name)
        return paiement_cible

    def _synchroniser_paiement_automatique(self):
        """Synchronise automatiquement le paiement vers la société cible"""
        self.ensure_one()
        config = self.env['cpss.sync.config'].get_config()
        return self._partager_paiement(config, 'automatic')

    def _creer_paiement_cible(self, config):
        """Crée le paiement miroir dans la société cible.

        Le paiement n'est volontairement rapproché avec aucune facture : le
        lettrage dans la société cible reste à la charge du comptable.
        """
        self.ensure_one()

        existant = self.env['account.payment'].sudo().search([
            ('paiement_origine_operationnelle_id', '=', self.id),
            ('company_id', '=', config.societe_cible_id.id),
        ], limit=1)
        if existant:
            return existant

        journal_cible = self._obtenir_journal_paiement_cible(config)
        vals = {
            'payment_type': self.payment_type,
            'partner_type': self.partner_type,
            'partner_id': self.partner_id.id,
            'amount': self.amount,
            'currency_id': self.currency_id.id,
            'date': self.date,
            'ref': "SYNC-%s" % self.name,
            'journal_id': journal_cible.id,
            'company_id': config.societe_cible_id.id,
            'payment_method_line_id': self._obtenir_methode_paiement_cible(journal_cible).id,
            'paiement_origine_operationnelle_id': self.id,
        }

        paiement_cible = self.env['account.payment'].create(vals)
        paiement_cible.action_post()
        return paiement_cible

    def _obtenir_journal_paiement_cible(self, config):
        """Trouve le journal de paiement équivalent dans la société cible"""
        self.ensure_one()

        journal_cible = self.env['account.journal'].sudo().search([
            ('type', '=', self.journal_id.type),
            ('company_id', '=', config.societe_cible_id.id),
        ], limit=1)

        if not journal_cible:
            raise UserError(_(
                "Aucun journal de type « %(type)s » trouvé dans la société "
                "cible %(societe)s."
            ) % {'type': self.journal_id.type,
                 'societe': config.societe_cible_id.name})

        return journal_cible

    def _obtenir_methode_paiement_cible(self, journal_cible):
        """Trouve la méthode de paiement dans le journal de la société cible"""
        self.ensure_one()

        if self.payment_type == 'inbound':
            methode = journal_cible.inbound_payment_method_line_ids[:1]
        else:
            methode = journal_cible.outbound_payment_method_line_ids[:1]

        if not methode:
            raise UserError(_(
                "Aucune méthode de paiement trouvée pour le journal %s de la "
                "société cible."
            ) % journal_cible.name)

        return methode

    # ------------------------------------------------------------------
    # ACTIONS UI
    # ------------------------------------------------------------------
    def action_partager_paiement(self):
        """Partager manuellement un paiement vers la société cible"""
        self.ensure_one()
        verifier_groupe_sync(self.env, GROUPE_SYNC_ADMIN, _("partage de paiement"))

        if not self.is_operational_company:
            raise UserError(_("Cette action n'est disponible que dans la société opérationnelle."))
        if self.state != 'posted':
            raise UserError(_("Seuls les paiements validés peuvent être partagés."))
        if self.partage == 'shared':
            raise UserError(_("Ce paiement est déjà partagé avec la société cible."))

        config = self.env['cpss.sync.config'].get_config()

        try:
            paiement_cible = self._partager_paiement(config, 'manual')
        except UserError:
            raise
        except Exception as error:
            _logger.exception("Échec du partage manuel du paiement %s", self.name)
            self.env['cpss.sync.log'].sudo()._log_sync_event_isolated(
                operation_name='Synchronisation Paiement', status='error',
                sync_type='manual', error_msg=str(error), source_doc=self,
                config=config,
            )
            raise UserError(_("Échec du partage : %s") % error)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('✅ Partage Réussi'),
                'message': _(
                    'Paiement "%(source)s" partagé avec succès !\n\n'
                    '🏢 Société cible : %(societe)s\n'
                    '💰 Paiement cible : %(cible)s\n'
                    '💵 Montant : %(montant)s %(devise)s'
                ) % {
                    'source': self.name,
                    'societe': config.societe_cible_id.name,
                    'cible': paiement_cible.name,
                    'montant': self.amount,
                    'devise': self.currency_id.name,
                },
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }

    def action_retry_partage(self):
        """Réessayer le partage d'un paiement en erreur"""
        self.ensure_one()
        verifier_groupe_sync(self.env, GROUPE_SYNC_ADMIN, _("partage de paiement"))

        if self.partage != 'error':
            raise UserError(_("Seuls les paiements en erreur peuvent être re-synchronisés."))

        self.write({'partage': 'not_shared', 'partage_error_message': False})
        return self.action_partager_paiement()
