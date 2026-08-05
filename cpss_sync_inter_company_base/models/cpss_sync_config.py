# Copyright 2025 CPSS
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import _, api, fields, models, tools
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)

GROUPE_SYNC_USER = 'cpss_sync_inter_company_base.group_sync_user'
GROUPE_SYNC_ADMIN = 'cpss_sync_inter_company_base.group_sync_admin'


def verifier_groupe_sync(env, groupe, operation):
    """Contrôle d'accès côté serveur.

    Les attributs ``groups`` des boutons ne masquent que l'interface : une
    méthode reste appelable en RPC. Toutes les actions de synchronisation
    doivent donc revérifier le groupe explicitement.
    """
    if not env.user.has_group(groupe):
        raise AccessError(_(
            "Vous n'avez pas les droits nécessaires pour effectuer cette "
            "opération (%s)."
        ) % operation)


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
        domain="[('company_id', '=', societe_cible_id)]",
        help="Journal utilisé pour les factures créées dans la société cible "
             "lorsque son type correspond au type de la facture d'origine"
    )

    # Correspondances explicites (prioritaires sur la recherche automatique)
    mapping_taxe_ids = fields.One2many(
        'cpss.sync.tax.mapping', 'config_id',
        string="Correspondances de Taxes",
        help="Correspondances forcées, utilisées en priorité lorsque la "
             "recherche automatique est ambiguë ou infructueuse"
    )
    mapping_compte_ids = fields.One2many(
        'cpss.sync.account.mapping', 'config_id',
        string="Correspondances de Comptes",
        help="Correspondances forcées, utilisées en priorité lorsque la "
             "recherche automatique est infructueuse"
    )

    # Champs informatifs (lecture seule)
    nb_contacts_partages = fields.Integer(
        string="Contacts Partagés",
        compute="_compute_donnees_partagees",
        help="Nombre de contacts accessibles depuis les deux sociétés"
    )
    nb_produits_partages = fields.Integer(
        string="Produits Partagés",
        compute="_compute_donnees_partagees",
        help="Nombre de produits accessibles depuis les deux sociétés"
    )
    nb_contacts_a_partager = fields.Integer(
        string="Contacts à Partager",
        compute="_compute_donnees_partagees",
        help="Contacts rattachés à l'une des deux sociétés et donc invisibles "
             "depuis l'autre"
    )
    nb_produits_a_partager = fields.Integer(
        string="Produits à Partager",
        compute="_compute_donnees_partagees",
        help="Produits rattachés à l'une des deux sociétés et donc invisibles "
             "depuis l'autre"
    )

    # ------------------------------------------------------------------
    # CACHE / ACCES A LA CONFIGURATION
    # ------------------------------------------------------------------
    # La configuration est lue à chaque calcul de `is_operational_company`,
    # c'est-à-dire une fois par ligne de liste de factures. Sans cache, cela
    # génère une requête par enregistrement affiché.
    @api.model
    @tools.ormcache()
    def _get_config_id(self):
        return self.sudo().search([], limit=1, order='id').id

    def _invalider_cache_config(self):
        self.clear_caches()

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self._invalider_cache_config()
        return records

    def write(self, vals):
        res = super().write(vals)
        self._invalider_cache_config()
        return res

    def unlink(self):
        res = super().unlink()
        self._invalider_cache_config()
        return res

    @api.model
    def _get_config_ou_vide(self):
        """Retourne la configuration active, ou un recordset vide."""
        config_id = self._get_config_id()
        if not config_id:
            return self.browse()
        return self.sudo().browse(config_id).exists()

    @api.model
    def _get_societe_operationnelle(self):
        """Société opérationnelle configurée (recordset éventuellement vide)."""
        return self._get_config_ou_vide().societe_operationnelle_id

    @api.model
    def get_config(self):
        """Récupère la configuration active, validée."""
        config = self._get_config_ou_vide()
        if not config:
            raise UserError(_(
                "Aucune configuration de synchronisation trouvée. "
                "Créez-la depuis Paramètres > Technique > Synchronisation "
                "Inter-Sociétés > Configuration."
            ))
        if not config.societe_operationnelle_id or not config.societe_cible_id:
            raise UserError(_(
                "La configuration de synchronisation est incomplète : "
                "la société opérationnelle et la société cible sont obligatoires."
            ))
        return config

    def get_journal_cible(self, type_journal):
        """Journal de la société cible pour un type donné.

        Le journal configuré est prioritaire lorsque son type correspond.
        """
        self.ensure_one()
        journal = self.journal_fiscal_defaut_id
        if journal and journal.type == type_journal \
                and journal.company_id == self.societe_cible_id:
            return journal
        journal = self.env['account.journal'].sudo().search([
            ('type', '=', type_journal),
            ('company_id', '=', self.societe_cible_id.id),
        ], limit=1)
        if not journal:
            raise UserError(_(
                "Aucun journal de type « %(type)s » n'existe dans la société "
                "cible %(societe)s."
            ) % {'type': type_journal, 'societe': self.societe_cible_id.name})
        return journal

    def get_taxe_cible_forcee(self, taxe_source):
        """Correspondance de taxe définie manuellement, ou recordset vide."""
        self.ensure_one()
        mapping = self.sudo().mapping_taxe_ids.filtered(
            lambda m: m.taxe_source_id == taxe_source)
        return mapping[:1].taxe_cible_id

    def get_compte_cible_force(self, compte_source):
        """Correspondance de compte définie manuellement, ou recordset vide."""
        self.ensure_one()
        mapping = self.sudo().mapping_compte_ids.filtered(
            lambda m: m.compte_source_id == compte_source)
        return mapping[:1].compte_cible_id

    # ------------------------------------------------------------------
    # CONTRAINTES
    # ------------------------------------------------------------------
    @api.constrains('societe_operationnelle_id', 'societe_cible_id')
    def _check_societes_differentes(self):
        """Les deux sociétés doivent être différentes"""
        for config in self:
            if config.societe_operationnelle_id == config.societe_cible_id:
                raise ValidationError(_(
                    "La société opérationnelle et la société cible doivent être différentes."
                ))

    @api.constrains('societe_operationnelle_id')
    def _check_configuration_unique(self):
        """Le module raisonne sur une configuration unique.

        Tout le code lit `search([], limit=1)` : un second enregistrement
        modifierait silencieusement le comportement de la synchronisation.
        """
        if self.search_count([]) > 1:
            raise ValidationError(_(
                "Une seule configuration de synchronisation peut exister. "
                "Modifiez la configuration existante au lieu d'en créer une nouvelle."
            ))

    @api.constrains('journal_fiscal_defaut_id', 'societe_cible_id')
    def _check_journal_societe_cible(self):
        for config in self:
            journal = config.journal_fiscal_defaut_id
            if journal and journal.company_id != config.societe_cible_id:
                raise ValidationError(_(
                    "Le journal par défaut doit appartenir à la société cible."
                ))

    # ------------------------------------------------------------------
    # DONNEES PARTAGEES
    # ------------------------------------------------------------------
    def _domaine_partenaires_a_partager(self):
        """Contacts rattachés à l'une des deux sociétés synchronisées.

        Les contacts liés à une `res.company` (contact de la société
        elle-même) sont exclus : leur `company_id` fait partie du paramétrage
        de la société et ne doit jamais être vidé.
        """
        self.ensure_one()
        partenaires_societes = self.env['res.company'].sudo().search([]).partner_id
        return [
            ('company_id', 'in', (self.societe_operationnelle_id
                                  | self.societe_cible_id).ids),
            ('id', 'not in', partenaires_societes.ids),
        ]

    def _domaine_produits_a_partager(self):
        self.ensure_one()
        return [
            ('company_id', 'in', (self.societe_operationnelle_id
                                  | self.societe_cible_id).ids),
        ]

    @api.depends('societe_operationnelle_id', 'societe_cible_id')
    def _compute_donnees_partagees(self):
        Partner = self.env['res.partner'].sudo()
        Product = self.env['product.product'].sudo()
        for config in self:
            if not config.societe_operationnelle_id or not config.societe_cible_id:
                config.nb_contacts_partages = 0
                config.nb_produits_partages = 0
                config.nb_contacts_a_partager = 0
                config.nb_produits_a_partager = 0
                continue
            config.nb_contacts_partages = Partner.search_count([
                ('company_id', '=', False),
            ])
            config.nb_produits_partages = Product.search_count([
                ('company_id', '=', False),
            ])
            config.nb_contacts_a_partager = Partner.search_count(
                config._domaine_partenaires_a_partager())
            config.nb_produits_a_partager = Product.search_count(
                config._domaine_produits_a_partager())

    def action_configurer_donnees_partagees(self):
        """Rend partagés les contacts et produits des deux sociétés.

        Opération volontairement manuelle et réservée aux administrateurs de
        synchronisation : elle modifie des données de référence de façon
        irréversible (la société d'origine n'est pas conservée).
        """
        self.ensure_one()
        verifier_groupe_sync(self.env, GROUPE_SYNC_ADMIN,
                             _("configuration des données partagées"))
        resultat = self._configurer_donnees_partagees()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Données partagées mises à jour"),
                'message': _(
                    "%(contacts)s contact(s) et %(produits)s produit(s) sont "
                    "désormais partagés entre les deux sociétés."
                ) % resultat,
                'type': 'success',
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }

    def _configurer_donnees_partagees(self):
        """Passe `company_id = False` sur les contacts et produits concernés.

        Restreint aux deux sociétés configurées : le reste de la base n'est
        jamais touché. Les erreurs ne sont pas masquées — un échec partiel
        doit rester visible.
        """
        self.ensure_one()

        partenaires = self.env['res.partner'].sudo().search(
            self._domaine_partenaires_a_partager())
        if partenaires:
            partenaires.write({'company_id': False})
            _logger.info("%s contacts configurés comme partagés", len(partenaires))

        produits = self.env['product.product'].sudo().search(
            self._domaine_produits_a_partager())
        if produits:
            produits.write({'company_id': False})
            _logger.info("%s produits configurés comme partagés", len(produits))

        # Les comptes et taxes restent volontairement spécifiques à chaque
        # société : leur correspondance est établie au moment de la
        # synchronisation (voir account_move.py).
        return {'contacts': len(partenaires), 'produits': len(produits)}

    # ------------------------------------------------------------------
    # ACTIONS
    # ------------------------------------------------------------------
    @api.model
    def action_open(self):
        """Ouvre la fiche singleton existante ou un formulaire vide."""
        config = self.search([], limit=1)
        return {
            'type': 'ir.actions.act_window',
            'name': _("Configuration Synchronisation"),
            'res_model': 'cpss.sync.config',
            'view_mode': 'form',
            'res_id': config.id if config else False,
            'target': 'current',
        }

    def action_test_synchronisation(self):
        """Vérifie que la configuration permet de synchroniser."""
        self.ensure_one()
        verifier_groupe_sync(self.env, GROUPE_SYNC_ADMIN,
                             _("test de la configuration"))
        problemes = []

        if not self.societe_operationnelle_id or not self.societe_cible_id:
            problemes.append(_("Les deux sociétés doivent être renseignées."))
        else:
            for type_journal, libelle in (('sale', _("ventes")),
                                          ('purchase', _("achats"))):
                if not self.env['account.journal'].sudo().search_count([
                        ('type', '=', type_journal),
                        ('company_id', '=', self.societe_cible_id.id)]):
                    problemes.append(_(
                        "Aucun journal de %(type)s dans la société cible."
                    ) % {'type': libelle})

            if not self.env['account.account'].sudo().search_count([
                    ('company_id', '=', self.societe_cible_id.id)]):
                problemes.append(_(
                    "La société cible n'a aucun compte comptable "
                    "(plan comptable non installé ?)."))

            if self.nb_contacts_a_partager or self.nb_produits_a_partager:
                problemes.append(_(
                    "%(contacts)s contact(s) et %(produits)s produit(s) ne sont "
                    "pas encore partagés entre les deux sociétés."
                ) % {'contacts': self.nb_contacts_a_partager,
                     'produits': self.nb_produits_a_partager})

        if problemes:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Configuration incomplète"),
                    'message': "\n".join("• %s" % p for p in problemes),
                    'type': 'warning',
                    'sticky': True,
                },
            }

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Test Réussi"),
                'message': _("La configuration de synchronisation est fonctionnelle !"),
                'type': 'success',
            },
        }
