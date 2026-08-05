# Copyright 2025 CPSS
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from collections import defaultdict

import psycopg2
from psycopg2 import errorcodes

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .cpss_sync_config import GROUPE_SYNC_ADMIN, GROUPE_SYNC_USER, verifier_groupe_sync

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'
    _check_company_auto = True

    # --- CHAMPS ---
    partage = fields.Selection([
        ('not_shared', 'Non Partagée'),
        ('proposed', 'Proposée pour Partage'),
        ('shared', 'Partagée'),
        ('refused', 'Refusée'),
        ('error', 'Erreur'),
    ], string="État de Partage", default='not_shared', copy=False, readonly=True,
        index=True, tracking=True)

    facture_societe_cible_id = fields.Many2one(
        'account.move', string="Facture Société cible",
        copy=False, readonly=True, check_company=False
    )
    facture_origine_operationnelle_id = fields.Many2one(
        'account.move', string="Facture Origine",
        copy=False, readonly=True, check_company=False, index=True
    )
    is_operational_company = fields.Boolean(compute="_compute_is_operational_company")

    # --- COMPUTES ---
    @api.depends('company_id')
    def _compute_is_operational_company(self):
        # La configuration est lue une seule fois pour tout le recordset : un
        # `search` par enregistrement rendrait les vues liste très lentes.
        societe_operationnelle = self.env['cpss.sync.config']._get_societe_operationnelle()
        for move in self:
            move.is_operational_company = bool(societe_operationnelle) \
                and move.company_id == societe_operationnelle

    # --- OUTILS ---
    def _verrouiller_pour_sync(self):
        """Pose un verrou exclusif sur la facture source.

        Empêche deux synchronisations simultanées (double clic, rejeu d'une
        requête) de créer deux factures dans la société cible.
        """
        self.ensure_one()
        try:
            # Le savepoint évite qu'un échec de verrou n'invalide toute la
            # transaction en cours.
            with self.env.cr.savepoint():
                self.env.cr.execute(
                    "SELECT id FROM account_move WHERE id = %s FOR UPDATE NOWAIT",
                    (self.id,))
        except psycopg2.OperationalError as error:
            if error.pgcode != errorcodes.LOCK_NOT_AVAILABLE:
                raise
            raise UserError(_(
                "Une synchronisation est déjà en cours pour cette facture. "
                "Réessayez dans quelques instants."
            ))

    def _get_facture_cible_existante(self, config):
        """Facture déjà créée dans la société cible pour cette facture source."""
        self.ensure_one()
        return self.env['account.move'].sudo().search([
            ('facture_origine_operationnelle_id', '=', self.id),
            ('company_id', '=', config.societe_cible_id.id),
        ], limit=1)

    def _verifier_partenaire_partage(self, partenaire, config):
        """Le partenaire doit être visible depuis la société cible.

        La synchronisation ne modifie jamais les données de référence : si le
        contact est rattaché à une société, c'est à l'administrateur de le
        rendre partagé explicitement.
        """
        if partenaire.company_id and partenaire.company_id != config.societe_cible_id:
            raise UserError(_(
                "Le contact « %(contact)s » appartient à la société "
                "%(societe)s et n'est donc pas accessible depuis "
                "%(cible)s.\n\n"
                "Rendez ce contact partagé (champ Société vide) ou lancez "
                "l'action « Configurer les données partagées » depuis la "
                "configuration de synchronisation."
            ) % {
                'contact': partenaire.display_name,
                'societe': partenaire.company_id.name,
                'cible': config.societe_cible_id.name,
            })

    # --- ACTIONS UI ---
    def action_proposer_sync(self):
        self.ensure_one()
        verifier_groupe_sync(self.env, GROUPE_SYNC_USER, _("proposition de partage"))
        if self.state != 'posted':
            raise UserError(_("Seules les factures validées peuvent être proposées."))
        if self.facture_societe_cible_id:
            raise UserError(_("Cette facture est déjà partagée."))
        self.partage = 'proposed'
        self._message_log(body=_("Facture proposée pour synchronisation."))

    def action_synchroniser(self):
        self.ensure_one()
        verifier_groupe_sync(self.env, GROUPE_SYNC_ADMIN, _("partage de facture"))
        if self.partage != 'proposed':
            raise UserError(_("Seules les factures proposées peuvent être synchronisées."))

        config = self.env['cpss.sync.config'].get_config()
        if self.company_id != config.societe_operationnelle_id:
            raise UserError(_(
                "Seules les factures de la société opérationnelle (%s) "
                "peuvent être partagées."
            ) % config.societe_operationnelle_id.name)

        self._verrouiller_pour_sync()

        ctx_fiscal = {
            'allowed_company_ids': [config.societe_cible_id.id],
            'default_company_id': config.societe_cible_id.id,
            'check_move_validity': False,
        }

        try:
            self_sync = self.with_context(**ctx_fiscal).sudo()
            facture_cible = self_sync._synchroniser_chaine_complete(config)

            self.write({
                'partage': 'shared',
                'facture_societe_cible_id': facture_cible.id,
            })

            self._synchroniser_paiements_rapproches()
            self._log_sync_success(facture_cible, config)

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('✅ Synchronisation Terminée'),
                    'message': _('Facture cible : %s') % facture_cible.name,
                    'type': 'success',
                    'next': {
                        'type': 'ir.actions.client',
                        'tag': 'reload',
                    },
                },
            }

        except Exception as error:
            # Le `raise` qui suit annule la transaction : le log doit donc être
            # écrit sur un curseur séparé pour survivre au rollback.
            _logger.exception("Échec de la synchronisation de la facture %s", self.name)
            self._log_sync_error(str(error), config)
            raise UserError(_("Échec de la synchronisation : %s") % error)

    def action_refuser_partage(self):
        self.ensure_one()
        verifier_groupe_sync(self.env, GROUPE_SYNC_ADMIN, _("refus de partage"))
        self.partage = 'refused'
        self._message_log(body=_("Partage refusé."))

    # --- LOGIQUE DE CHAINE ---
    def _synchroniser_chaine_complete(self, config):
        self.ensure_one()

        # Garde-fou d'idempotence : si une facture cible existe déjà pour
        # cette facture source, on la réutilise au lieu d'en créer une seconde.
        existante = self._get_facture_cible_existante(config)
        if existante:
            _logger.info("Facture cible déjà existante pour %s : %s",
                         self.name, existante.name)
            return existante

        if self.move_type in ('out_invoice', 'out_refund'):
            return self._synchroniser_chaine_vente(config)
        if self.move_type in ('in_invoice', 'in_refund'):
            return self._synchroniser_chaine_achat(config)
        return self._creer_facture_cible_directe(config)

    def _verifier_devise_coherente(self, document_cible, config):
        """La copie doit être libellée dans la même devise que l'original.

        Sinon les `price_unit` recopiés seraient réinterprétés dans une autre
        devise et les montants de la société cible seraient faux.
        """
        if document_cible.currency_id != self.currency_id:
            raise UserError(_(
                "Devise incohérente : le document d'origine est en %(origine)s "
                "alors que la société cible utiliserait %(cible)s.\n\n"
                "Alignez la liste de prix / la devise du partenaire dans la "
                "société %(societe)s avant de synchroniser."
            ) % {
                'origine': self.currency_id.name,
                'cible': document_cible.currency_id.name,
                'societe': config.societe_cible_id.name,
            })

    # ---------------------------------------------------------
    # FLUX VENTES (Sale Order -> Pickings -> Invoice)
    # ---------------------------------------------------------
    def _synchroniser_chaine_vente(self, config):
        orig_name = self.invoice_origin
        commande_origine = self.env['sale.order'].sudo().search([
            ('name', '=', orig_name),
            ('company_id', '=', config.societe_operationnelle_id.id),
        ], limit=1) if orig_name else self.env['sale.order']

        if not commande_origine:
            return self._creer_facture_cible_directe(config)

        # Recherche ou Création du SO dans la société cible
        commande_cible = self.env['sale.order'].sudo().search([
            ('client_order_ref', '=', "SYNC-%s" % commande_origine.name),
            ('company_id', '=', config.societe_cible_id.id),
        ], limit=1)

        if not commande_cible:
            commande_cible = self._creer_commande_vente_cible(commande_origine, config)
            commande_cible.action_confirm()
            for picking in commande_cible.picking_ids:
                self._traiter_stock_cible(picking, commande_origine.name, config)

        return self._creer_facture_depuis_commande_vente(commande_cible, config)

    def _creer_commande_vente_cible(self, origin, config):
        self._verifier_partenaire_partage(origin.partner_id, config)

        vals = {
            'partner_id': origin.partner_id.id,
            'company_id': config.societe_cible_id.id,
            'date_order': origin.date_order,
            'client_order_ref': "SYNC-%s" % origin.name,
            'order_line': [],
        }
        for ligne in origin.order_line:
            if ligne.display_type:
                vals['order_line'].append((0, 0, {
                    'display_type': ligne.display_type,
                    'name': ligne.name,
                    'sequence': ligne.sequence,
                }))
                continue
            taxes = self._mapper_taxes_vers_societe_cible(ligne.tax_id, config)
            vals['order_line'].append((0, 0, {
                'product_id': ligne.product_id.id,
                'name': ligne.name,
                'sequence': ligne.sequence,
                'product_uom_qty': ligne.product_uom_qty,
                'product_uom': ligne.product_uom.id,
                'price_unit': ligne.price_unit,
                'discount': ligne.discount,
                'tax_id': [(6, 0, taxes.ids)],
            }))

        commande_cible = self.env['sale.order'] \
            .with_company(config.societe_cible_id).sudo().create(vals)
        self._verifier_devise_coherente(commande_cible, config)
        return commande_cible

    def _creer_facture_depuis_commande_vente(self, so_cible, config):
        so_cible = so_cible.with_company(config.societe_cible_id).sudo()
        facture_vals = so_cible._prepare_invoice()
        facture_vals.update({
            'ref': "SYNC-%s" % self.name,
            'invoice_date': self.invoice_date,
            'facture_origine_operationnelle_id': self.id,
            'invoice_line_ids': [],
        })
        for line in so_cible.order_line:
            line_vals = line._prepare_invoice_line()
            if not line_vals.get('account_id'):
                compte_source = (line.product_id.property_account_income_id
                                 or line.product_id.categ_id.property_account_income_categ_id)
                compte_cible = self._mapper_compte_vers_societe_cible(compte_source, config)
                if compte_cible:
                    line_vals['account_id'] = compte_cible.id
            facture_vals['invoice_line_ids'].append((0, 0, line_vals))

        self._verifier_lignes_facturables(facture_vals, so_cible)
        return self.env['account.move'] \
            .with_company(config.societe_cible_id).sudo().create(facture_vals)

    def _verifier_lignes_facturables(self, facture_vals, so_cible):
        """La commande cible doit avoir quelque chose à facturer.

        `_prepare_invoice_line` s'appuie sur `qty_to_invoice` : si les
        transferts de la société cible n'ont pas été validés, toutes les
        quantités seraient à zéro et la facture cible serait vide.
        """
        quantites = sum(
            vals.get('quantity') or 0.0
            for _cmd, _id, vals in facture_vals['invoice_line_ids']
        )
        if not quantites:
            raise UserError(_(
                "Aucune quantité à facturer sur la commande %s de la société "
                "cible. Vérifiez que les transferts associés ont bien été "
                "validés."
            ) % so_cible.name)

    # ---------------------------------------------------------
    # FLUX ACHATS (Purchase Order -> Pickings -> Invoice)
    # ---------------------------------------------------------
    def _synchroniser_chaine_achat(self, config):
        orig_name = self.invoice_origin
        commande_origine = self.env['purchase.order'].sudo().search([
            ('name', '=', orig_name),
            ('company_id', '=', config.societe_operationnelle_id.id),
        ], limit=1) if orig_name else self.env['purchase.order']

        if not commande_origine:
            return self._creer_facture_cible_directe(config)

        # Recherche ou Création du PO dans la société cible
        commande_cible = self.env['purchase.order'].sudo().search([
            ('partner_ref', '=', "SYNC-%s" % commande_origine.name),
            ('company_id', '=', config.societe_cible_id.id),
        ], limit=1)

        if not commande_cible:
            commande_cible = self._creer_commande_achat_cible(commande_origine, config)
            commande_cible.button_confirm()
            for picking in commande_cible.picking_ids:
                self._traiter_stock_cible(picking, commande_origine.name, config)

        return self._creer_facture_achat_depuis_po(commande_cible, config)

    def _creer_commande_achat_cible(self, origin, config):
        self._verifier_partenaire_partage(origin.partner_id, config)

        vals = {
            'partner_id': origin.partner_id.id,
            'company_id': config.societe_cible_id.id,
            'currency_id': origin.currency_id.id,
            'date_order': origin.date_order,
            'partner_ref': "SYNC-%s" % origin.name,
            'order_line': [],
        }
        for ligne in origin.order_line:
            if ligne.display_type:
                vals['order_line'].append((0, 0, {
                    'display_type': ligne.display_type,
                    'name': ligne.name,
                    'sequence': ligne.sequence,
                }))
                continue
            taxes = self._mapper_taxes_vers_societe_cible(ligne.taxes_id, config)
            vals['order_line'].append((0, 0, {
                'product_id': ligne.product_id.id,
                'name': ligne.name,
                'sequence': ligne.sequence,
                'product_qty': ligne.product_qty,
                'product_uom': ligne.product_uom.id,
                'price_unit': ligne.price_unit,
                'taxes_id': [(6, 0, taxes.ids)],
                'date_planned': ligne.date_planned,
            }))

        commande_cible = self.env['purchase.order'] \
            .with_company(config.societe_cible_id).sudo().create(vals)
        self._verifier_devise_coherente(commande_cible, config)
        return commande_cible

    def _creer_facture_achat_depuis_po(self, po_cible, config):
        po_cible = po_cible.with_company(config.societe_cible_id).sudo()
        invoice_vals = po_cible._prepare_invoice()
        invoice_vals.update({
            'ref': "SYNC-%s" % self.name,
            'invoice_date': self.invoice_date,
            'facture_origine_operationnelle_id': self.id,
            'invoice_line_ids': [],
        })
        for line in po_cible.order_line:
            if line.display_type:
                invoice_vals['invoice_line_ids'].append((0, 0, {
                    'display_type': line.display_type,
                    'name': line.name,
                    'sequence': line.sequence,
                }))
                continue
            compte_source = (line.product_id.property_account_expense_id
                             or line.product_id.categ_id.property_account_expense_categ_id)
            compte_cible = self._mapper_compte_vers_societe_cible(compte_source, config)
            taxes = self._mapper_taxes_vers_societe_cible(line.taxes_id, config)
            ligne_vals = {
                'product_id': line.product_id.id,
                'name': line.name,
                'sequence': line.sequence,
                'quantity': line.product_qty,
                'price_unit': line.price_unit,
                'product_uom_id': line.product_uom.id,
                'tax_ids': [(6, 0, taxes.ids)],
                'purchase_line_id': line.id,
            }
            if compte_cible:
                # Sans compte source, on laisse Odoo calculer le compte dans
                # le contexte de la société cible.
                ligne_vals['account_id'] = compte_cible.id
            invoice_vals['invoice_line_ids'].append((0, 0, ligne_vals))

        return self.env['account.move'] \
            .with_company(config.societe_cible_id).sudo().create(invoice_vals)

    # ---------------------------------------------------------
    # GESTION DU STOCK ET DES LOTS (Odoo 16 : qty_done / stock.lot)
    # ---------------------------------------------------------
    def _traiter_stock_cible(self, picking, origin_name, config):
        if picking.state in ('done', 'cancel'):
            return

        if picking.state != 'assigned':
            picking.action_assign()

        for move in picking.move_ids:
            if move.state in ('done', 'cancel'):
                continue

            lots = []
            if move.product_id.tracking != 'none':
                lots = self._get_origin_lot_names(move.product_id, origin_name, config)

            if not lots:
                move.quantity_done = move.product_uom_qty
                continue

            # Les lignes de réservation générées par `action_assign` sont
            # remplacées : les conserver doublerait les quantités traitées.
            move.move_line_ids.unlink()
            for lot_info in lots:
                lot = self._trouver_ou_creer_lot(
                    move.product_id, lot_info['name'], picking.company_id,
                    origin_name, config)
                self.env['stock.move.line'].sudo().create({
                    'move_id': move.id,
                    'picking_id': picking.id,
                    'company_id': picking.company_id.id,
                    'product_id': move.product_id.id,
                    'product_uom_id': move.product_uom.id,
                    'lot_id': lot.id,
                    'qty_done': lot_info['qty'],
                    'location_id': move.location_id.id,
                    'location_dest_id': move.location_dest_id.id,
                })

        self._valider_picking_cible(picking)

    def _valider_picking_cible(self, picking):
        """Valide un transfert en traitant les assistants éventuels.

        `button_validate` peut renvoyer une action (transfert immédiat,
        confirmation de reliquat) : ignorer cette valeur de retour laisserait
        le transfert non validé, et donc la facture cible sans quantité.
        """
        resultat = picking.button_validate()
        if isinstance(resultat, dict) and resultat.get('res_model'):
            assistant = self.env[resultat['res_model']] \
                .with_context(**(resultat.get('context') or {})).sudo().create({})
            if hasattr(assistant, 'process'):
                assistant.process()

        if picking.state != 'done':
            raise UserError(_(
                "Le transfert %(picking)s de la société cible n'a pas pu être "
                "validé (état : %(etat)s)."
            ) % {'picking': picking.name, 'etat': picking.state})

    def _trouver_ou_creer_lot(self, product, name, target_company, origin_name, config):
        lot = self.env['stock.lot'].sudo().search([
            ('name', '=', name),
            ('product_id', '=', product.id),
            '|', ('company_id', '=', target_company.id), ('company_id', '=', False),
        ], limit=1)
        if lot:
            return lot

        lot_source = self.env['stock.move.line'].sudo().search([
            ('picking_id.origin', '=', origin_name),
            ('picking_id.company_id', '=', config.societe_operationnelle_id.id),
            ('product_id', '=', product.id),
            ('lot_id.name', '=', name),
        ], limit=1).lot_id

        vals = {'name': name, 'product_id': product.id, 'company_id': target_company.id}
        if lot_source:
            for champ in ('expiration_date', 'use_date', 'removal_date', 'alert_date'):
                if champ in lot_source._fields:
                    vals[champ] = lot_source[champ]
        return self.env['stock.lot'].sudo().create(vals)

    def _get_origin_lot_names(self, product, origin_name, config):
        """Lots consommés dans la société opérationnelle : [{name, qty}].

        Tous les transferts terminés portant cette origine sont pris en
        compte (livraisons partielles, reliquats), et uniquement ceux de la
        société opérationnelle.
        """
        pickings = self.env['stock.picking'].sudo().search([
            ('origin', '=', origin_name),
            ('state', '=', 'done'),
            ('company_id', '=', config.societe_operationnelle_id.id),
        ])
        if not pickings:
            return []

        quantites = defaultdict(float)
        mouvements = pickings.move_ids.filtered(
            lambda m: m.product_id == product and m.state == 'done')
        for ligne in mouvements.move_line_ids.filtered(lambda ligne: ligne.lot_id):
            quantites[ligne.lot_id.name] += ligne.qty_done

        return [{'name': nom, 'qty': qty}
                for nom, qty in quantites.items() if qty > 0]

    # ---------------------------------------------------------
    # MAPPINGS ET DIAGNOSTICS
    # ---------------------------------------------------------
    def _mapper_taxes_vers_societe_cible(self, taxes_orig, config):
        """Taxes équivalentes dans la société cible.

        Une taxe sans correspondance certaine n'est jamais ignorée
        silencieusement : sur un module de conformité fiscale, une facture
        cible sans TVA ou avec la mauvaise TVA est pire qu'une erreur.
        """
        Tax = self.env['account.tax'].sudo()
        resultat = Tax
        for taxe in taxes_orig:
            # Stratégie 0 : correspondance forcée depuis la configuration
            correspondance = config.get_taxe_cible_forcee(taxe)

            # `price_include` distingue une taxe HT d'une taxe TTC : les deux
            # ne sont jamais interchangeables.
            domaine = [
                ('company_id', '=', config.societe_cible_id.id),
                ('type_tax_use', '=', taxe.type_tax_use),
                ('amount_type', '=', taxe.amount_type),
                ('price_include', '=', taxe.price_include),
            ]
            # Stratégie 1 : nom + montant (correspondance exacte)
            if not correspondance:
                correspondance = Tax.search(
                    domaine + [('name', '=', taxe.name), ('amount', '=', taxe.amount)],
                    limit=1)

            # Stratégie 2 : montant seul, à condition que le résultat soit unique
            if not correspondance:
                candidates = Tax.search(domaine + [('amount', '=', taxe.amount)])
                if len(candidates) == 1:
                    correspondance = candidates
                elif len(candidates) > 1:
                    raise UserError(_(
                        "La taxe « %(taxe)s » (%(montant)s, %(mode)s) correspond "
                        "à plusieurs taxes de la société %(societe)s :\n%(liste)s\n\n"
                        "Déclarez la correspondance à utiliser dans "
                        "Configuration Synchronisation > onglet « Correspondances "
                        "de Taxes »."
                    ) % {
                        'taxe': taxe.name,
                        'montant': taxe.amount,
                        'mode': _("TTC") if taxe.price_include else _("HT"),
                        'societe': config.societe_cible_id.name,
                        'liste': "\n".join("• %s" % nom
                                           for nom in candidates.mapped('name')),
                    })

            if not correspondance:
                raise UserError(_(
                    "Aucune taxe équivalente à « %(taxe)s » (%(montant)s, "
                    "%(usage)s, %(mode)s) dans la société %(societe)s.\n\n"
                    "Créez la taxe correspondante, ou déclarez la correspondance "
                    "dans Configuration Synchronisation > onglet "
                    "« Correspondances de Taxes »."
                ) % {
                    'taxe': taxe.name,
                    'montant': taxe.amount,
                    'usage': taxe.type_tax_use,
                    'mode': _("TTC") if taxe.price_include else _("HT"),
                    'societe': config.societe_cible_id.name,
                })
            resultat |= correspondance
        return resultat

    def _mapper_compte_vers_societe_cible(self, compte_orig, config):
        """Compte équivalent dans la société cible.

        Retourne un recordset vide si aucun compte source n'est fourni :
        l'appelant laisse alors Odoo déterminer le compte. En revanche, un
        compte source sans équivalent est une erreur — retomber sur un compte
        arbitraire du même type fausserait la comptabilité de la société cible.
        """
        if not compte_orig:
            return self.env['account.account']

        # Stratégie 0 : correspondance forcée depuis la configuration
        compte = config.get_compte_cible_force(compte_orig)
        if compte:
            return compte

        Account = self.env['account.account'].sudo()

        # Stratégie 1 : code exact
        compte = Account.search([
            ('code', '=', compte_orig.code),
            ('company_id', '=', config.societe_cible_id.id),
        ], limit=1)

        # Stratégie 2 : longueur de code différente (ex : 700 -> 700000)
        if not compte and len(compte_orig.code) >= 3:
            for longueur in (6, 5, 4):
                code_normalise = compte_orig.code[:longueur].ljust(longueur, '0')
                compte = Account.search([
                    ('code', '=', code_normalise),
                    ('company_id', '=', config.societe_cible_id.id),
                ], limit=1)
                if compte:
                    break

        if not compte:
            raise UserError(_(
                "Compte %(code)s introuvable dans %(societe)s.\n\n%(diag)s\n\n"
                "Créez le compte correspondant, ou déclarez la correspondance "
                "dans Configuration Synchronisation > onglet "
                "« Correspondances de Comptes »."
            ) % {
                'code': compte_orig.code,
                'societe': config.societe_cible_id.name,
                'diag': self._diagnostiquer_comptes_manquants(compte_orig, config),
            })
        return compte

    def _diagnostiquer_comptes_manquants(self, compte_op, config):
        lignes = [_("Type recherché : %s") % compte_op.account_type]
        Account = self.env['account.account'].sudo()
        total = Account.search_count([('company_id', '=', config.societe_cible_id.id)])
        if not total:
            lignes.append(_("⚠️ Aucun compte dans la société cible "
                            "(plan comptable absent ?)"))
        else:
            similaires = Account.search([
                ('code', '=like', "%s%%" % compte_op.code[:2]),
                ('company_id', '=', config.societe_cible_id.id),
            ], limit=3)
            if similaires:
                lignes.append(_("📋 Suggestions : %s") % ", ".join(similaires.mapped('code')))
        return "\n".join(lignes)

    # ---------------------------------------------------------
    # FALLBACK DIRECT (Facture sans SO/PO)
    # ---------------------------------------------------------
    def _creer_facture_cible_directe(self, config):
        vals = self._preparer_vals_facture_cible(config)
        return self.env['account.move'] \
            .with_company(config.societe_cible_id).sudo().create(vals)

    def _preparer_vals_facture_cible(self, config):
        type_journal = 'sale' if self.move_type.startswith('out_') else 'purchase'
        journal = config.get_journal_cible(type_journal)
        self._verifier_partenaire_partage(self.partner_id, config)

        vals = {
            'move_type': self.move_type,
            'partner_id': self.partner_id.id,
            'company_id': config.societe_cible_id.id,
            'journal_id': journal.id,
            'currency_id': self.currency_id.id,
            'invoice_date': self.invoice_date,
            'ref': "SYNC-%s" % self.name,
            'facture_origine_operationnelle_id': self.id,
            'invoice_line_ids': [],
        }

        nb_lignes = 0
        for ligne in self.invoice_line_ids:
            if ligne.display_type:
                vals['invoice_line_ids'].append((0, 0, {
                    'display_type': ligne.display_type,
                    'name': ligne.name,
                    'sequence': ligne.sequence,
                }))
                continue
            # Toute ligne non mappable interrompt la synchronisation : une
            # facture cible amputée d'une ligne serait fausse sans que
            # personne ne s'en aperçoive.
            compte = self._mapper_compte_vers_societe_cible(ligne.account_id, config)
            taxes = self._mapper_taxes_vers_societe_cible(ligne.tax_ids, config)
            ligne_vals = {
                'product_id': ligne.product_id.id,
                'name': ligne.name,
                'sequence': ligne.sequence,
                'quantity': ligne.quantity,
                'product_uom_id': ligne.product_uom_id.id,
                'price_unit': ligne.price_unit,
                'discount': ligne.discount,
                'tax_ids': [(6, 0, taxes.ids)],
            }
            if compte:
                ligne_vals['account_id'] = compte.id
            vals['invoice_line_ids'].append((0, 0, ligne_vals))
            nb_lignes += 1

        if not nb_lignes:
            raise UserError(_(
                "La facture %s ne contient aucune ligne à synchroniser."
            ) % self.name)
        return vals

    # ---------------------------------------------------------
    # PAIEMENTS ET LOGS
    # ---------------------------------------------------------
    def _synchroniser_paiements_rapproches(self):
        """Partage les paiements déjà rapprochés avec cette facture.

        Chaque paiement est isolé dans un savepoint : un échec ne doit ni
        annuler le partage de la facture, ni laisser un curseur inutilisable.
        """
        self.ensure_one()
        paiements = self._trouver_paiements_rapproches()
        for paiement in paiements.filtered(lambda p: p.partage == 'not_shared'):
            try:
                with self.env.cr.savepoint():
                    paiement._synchroniser_paiement_automatique()
            except Exception as error:
                _logger.exception("Échec du partage du paiement %s", paiement.name)
                paiement.write({
                    'partage': 'error',
                    'partage_error_message': str(error),
                })

    def _trouver_paiements_rapproches(self):
        self.ensure_one()
        paiements = self.env['account.payment']
        lignes = self.line_ids.filtered(
            lambda ligne: ligne.account_id.account_type in (
                'asset_receivable', 'liability_payable'))
        for ligne in lignes:
            for rapprochement in ligne.matched_debit_ids + ligne.matched_credit_ids:
                ligne_paiement = rapprochement.debit_move_id \
                    if rapprochement.credit_move_id == ligne \
                    else rapprochement.credit_move_id
                if ligne_paiement.payment_id:
                    paiements |= ligne_paiement.payment_id
        return paiements

    def _log_sync_success(self, facture_cible, config):
        self.env['cpss.sync.log'].sudo()._log_sync_event(
            operation_name='Synchronisation Facture', status='success',
            sync_type='manual', source_doc=self, target_doc=facture_cible,
            config=config,
        )
        self._message_log(body=_("✅ Facture synchronisée : %s") % facture_cible.name)

    def _log_sync_error(self, message_erreur, config):
        self.env['cpss.sync.log'].sudo()._log_sync_event_isolated(
            operation_name='Synchronisation Facture', status='error',
            sync_type='manual', error_msg=message_erreur, source_doc=self,
            config=config,
        )
