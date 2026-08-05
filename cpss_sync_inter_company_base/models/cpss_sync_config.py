# Copyright 2025 CPSS
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class CpssSyncConfig(models.Model):
    _name = 'cpss.sync.config'
    _description = 'Configuration Synchronisation Inter-Sociétés'
    _rec_name = 'societe_operationnelle_id'

    # Configuration de base
    societe_operationnelle_id = fields.Many2one(
        'res.company',
        string="Société Opérationnelle",
        required=True,
        help="Société qui gère toutes les opérations (déclarées et non-déclarées)"
    )
    societe_cible_id = fields.Many2one(
        'res.company',
        string="Société Cible",
        required=True,
        help="Société qui reçoit les opérations synchronisées"
    )

    # Journal par défaut
    journal_fiscal_defaut_id = fields.Many2one(
        'account.journal',
        string="Journal par Défaut (Cible)",
        help="Journal par défaut pour les factures dans la société cible"
    )

    # Champs informatifs (lecture seule)
    nb_contacts_partages = fields.Integer(
        string="Contacts Partagés",
        compute="_compute_donnees_partagees",
        help="Nombre de contacts partagés entre sociétés"
    )
    nb_produits_partages = fields.Integer(
        string="Produits Partagés",
        compute="_compute_donnees_partagees",
        help="Nombre de produits partagés entre sociétés"
    )

    @api.depends()
    def _compute_donnees_partagees(self):
        """Calcule le nombre d'éléments partagés"""
        for config in self:
            config.nb_contacts_partages = self.env['res.partner'].search_count([
                ('company_id', '=', False),
                ('is_company', '=', True)
            ])
            config.nb_produits_partages = self.env['product.product'].search_count([
                ('company_id', '=', False)
            ])

    @api.model
    def action_open(self):
        """Ouvre la fiche singleton existante ou un formulaire vide."""
        config = self.search([], limit=1)
        return {
            'type': 'ir.actions.act_window',
            'name': 'Configuration Synchronisation',
            'res_model': 'cpss.sync.config',
            'view_mode': 'form',
            'res_id': config.id if config else False,
            'target': 'current',
        }

    @api.model
    def get_config(self):
        """Récupère la configuration active"""
        config = self.search([], limit=1)
        if not config:
            raise ValidationError(_(
                "Aucune configuration de synchronisation trouvée. "
                "Veuillez créer une configuration dans le menu Technique."
            ))
        return config

    @api.constrains('societe_operationnelle_id', 'societe_cible_id')
    def _check_societes_differentes(self):
        """Les deux sociétés doivent être différentes"""
        for config in self:
            if config.societe_operationnelle_id == config.societe_cible_id:
                raise ValidationError(_(
                    "La société opérationnelle et la société cible doivent être différentes."
                ))

    def action_configurer_donnees_partagees(self):
        """Action manuelle pour reconfigurer les données partagées"""
        self.configurer_donnees_partagees()
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    @api.model
    def configurer_donnees_partagees(self):
        """
        Configure les données pour qu'elles soient partagées
        entre les sociétés (company_id = False)
        """
        try:
            # 1. Partners partagés (sauf les sociétés elles-mêmes)
            partners = self.env['res.partner'].search([
                ('company_id', '!=', False),
                ('is_company', '=', False)  # Ne pas partager les sociétés
            ])
            if partners:
                partners.write({'company_id': False})
                _logger.info(f"✅ {len(partners)} contacts configurés comme partagés")

            # 2. Produits partagés
            produits = self.env['product.product'].search([('company_id', '!=', False)])
            if produits:
                produits.write({'company_id': False})
                _logger.info(f"✅ {len(produits)} produits configurés comme partagés")

            # 3. IMPORTANT : Ne PAS partager les comptes et taxes
            # Ils doivent rester spécifiques à chaque société pour la conformité comptable
            # Le mapping sera fait automatiquement lors de la synchronisation

            _logger.info("🎯 Configuration des données partagées terminée avec succès")
            _logger.info("⚠️  Les comptes et taxes restent spécifiques par société (mapping automatique)")
            return True

        except Exception as e:
            _logger.error(f"❌ Erreur lors de la configuration des données partagées : {str(e)}")
            return False

    def action_test_synchronisation(self):
        """Test de la configuration de synchronisation"""
        try:
            if not self.journal_fiscal_defaut_id:
                raise ValidationError(_("Journal par défaut non défini"))

            # Test d'accès aux sociétés
            self.env['account.move'].check_access_rights('read')

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Test Réussi"),
                    'message': _("La configuration de synchronisation est fonctionnelle !"),
                    'type': 'success',
                }
            }

        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Test Échoué"),
                    'message': _("Erreur de configuration : %s") % str(e),
                    'type': 'danger',
                }
            }