from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

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
    ], string="État de Partage", default='not_shared', copy=False, readonly=True)

    facture_societe_cible_id = fields.Many2one(
        'account.move', string="Facture Société cible",
        copy=False, readonly=True, check_company=False
    )
    facture_origine_operationnelle_id = fields.Many2one(
        'account.move', string="Facture Origine",
        copy=False, readonly=True, check_company=False
    )
    is_operational_company = fields.Boolean(compute="_compute_is_operational_company")
    active_company_ids = fields.Many2many('res.company', compute="_compute_selected_companies")

    # --- COMPUTES ---
    @api.depends('company_id')
    def _compute_is_operational_company(self):
        for move in self:
            config = self.env['cpss.sync.config'].search([], limit=1)
            move.is_operational_company = bool(config and move.company_id == config.societe_operationnelle_id)

    @api.depends_context('allowed_company_ids')
    def _compute_selected_companies(self):
        allowed_ids = self.env.context.get('allowed_company_ids', [])
        companies = self.env['res.company'].sudo().browse(allowed_ids)
        for rec in self:
            rec.active_company_ids = companies

    # --- ACTIONS UI ---
    def action_proposer_sync(self):
        self.ensure_one()
        if self.state != 'posted':
            raise UserError(_("Seules les factures validées peuvent être proposées."))
        if self.facture_societe_cible_id:
            raise UserError(_("Cette facture est déjà partagée."))
        self.partage = 'proposed'
        self._message_log(body=_("Facture proposée pour synchronisation."))

    def action_synchroniser(self):
        self.ensure_one()
        if self.partage != 'proposed':
            raise UserError(_("Seules les factures proposées peuvent être synchronisées."))

        config = self.env['cpss.sync.config'].get_config()

        ctx_fiscal = {
            'allowed_company_ids': [config.societe_cible_id.id],
            'default_company_id': config.societe_cible_id.id,
            'check_move_validity': False,
            'bypass_company_validation': True,
        }

        try:
            self_sync = self.with_context(ctx_fiscal).sudo()
            facture_cible = self_sync._synchroniser_chaine_complete(config)

            self.write({
                'partage': 'shared',
                'facture_societe_cible_id': facture_cible.id
            })

            paiements_existants = self._trouver_paiements_rapproches()
            for paiement in paiements_existants.filtered(lambda p: p.partage == 'not_shared'):
                try:
                    paiement._synchroniser_paiement_automatique()
                except Exception:
                    paiement.write({'partage': 'error'})

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

        except Exception as e:
            _logger.error("Erreur Sync: %s", str(e))
            self._log_sync_error(str(e), config)
            raise UserError(_("Échec de la synchronisation : %s") % str(e))

    def action_refuser_partage(self):
        self.ensure_one()
        self.partage = 'refused'
        self._message_log(body=_("Partage refusé."))

    # --- LOGIQUE DE CHAINE ---
    def _synchroniser_chaine_complete(self, config):
        if self.move_type in ['out_invoice', 'out_refund']:
            return self._synchroniser_chaine_vente(config)
        elif self.move_type in ['in_invoice', 'in_refund']:
            return self._synchroniser_chaine_achat(config)
        return self._creer_facture_cible_directe(config)

    # ---------------------------------------------------------
    # FLUX VENTES (Sale Order -> Pickings -> Invoice)
    # ---------------------------------------------------------
    def _synchroniser_chaine_vente(self, config):
        orig_name = self.invoice_origin
        commande_origine = self.env['sale.order'].sudo().search(
            [('name', '=', orig_name)], limit=1) if orig_name else None

        if not commande_origine:
            return self._creer_facture_cible_directe(config)

        # Recherche ou Création du SO Fiscal
        commande_cible = self.env['sale.order'].sudo().search([
            ('client_order_ref', '=', f"SYNC-{commande_origine.name}"),
            ('company_id', '=', config.societe_cible_id.id)
        ], limit=1)

        if not commande_cible:
            commande_cible = self._creer_commande_vente_cible(commande_origine, config)
            commande_cible.action_confirm()
            for picking in commande_cible.picking_ids:
                self._traiter_stock_cible(picking, commande_origine.name)

        return self._creer_facture_depuis_commande_vente(commande_cible, config)

    def _creer_commande_vente_cible(self, origin, config):
        if origin.partner_id.company_id:
            origin.partner_id.sudo().write({'company_id': False})
        vals = {
            'partner_id': origin.partner_id.id,
            'company_id': config.societe_cible_id.id,
            'date_order': origin.date_order,
            'client_order_ref': f"SYNC-{origin.name}",
            'order_line': []
        }
        for ligne in origin.order_line:
            taxes = self._mapper_taxes_vers_societe_cible_safe(ligne.tax_id, config)
            vals['order_line'].append((0, 0, {
                'product_id': ligne.product_id.id,
                'name': ligne.name,
                'product_uom_qty': ligne.product_uom_qty,
                'price_unit': ligne.price_unit,
                'tax_id': [(6, 0, taxes.ids)],
            }))
        return self.env['sale.order'].with_company(config.societe_cible_id).sudo().create(vals)

    def _creer_facture_depuis_commande_vente(self, so_cible, config):
        facture_vals = so_cible._prepare_invoice()
        facture_vals.update({
            'ref': f"SYNC-{self.name}",
            'facture_origine_operationnelle_id': self.id,
            'invoice_line_ids': []
        })
        for line in so_cible.order_line:
            line_vals = line._prepare_invoice_line()
            if not line_vals.get('account_id'):
                acc = (line.product_id.property_account_income_id
                       or line.product_id.categ_id.property_account_income_categ_id)
                acc_fisc = self._mapper_compte_vers_societe_cible(acc, config)
                line_vals['account_id'] = acc_fisc.id
            facture_vals['invoice_line_ids'].append((0, 0, line_vals))
        return self.env['account.move'].with_company(config.societe_cible_id).sudo().create(facture_vals)

    # ---------------------------------------------------------
    # FLUX ACHATS (Purchase Order -> Pickings -> Invoice)
    # ---------------------------------------------------------
    def _synchroniser_chaine_achat(self, config):
        orig_name = self.invoice_origin
        commande_origine = self.env['purchase.order'].sudo().search(
            [('name', '=', orig_name)], limit=1) if orig_name else None

        if not commande_origine:
            return self._creer_facture_cible_directe(config)

        # Recherche ou Création du PO Fiscal
        commande_cible = self.env['purchase.order'].sudo().search([
            ('partner_ref', '=', f"SYNC-{commande_origine.name}"),
            ('company_id', '=', config.societe_cible_id.id)
        ], limit=1)

        if not commande_cible:
            commande_cible = self._creer_commande_achat_cible(commande_origine, config)
            commande_cible.button_confirm()
            for picking in commande_cible.picking_ids:
                self._traiter_stock_cible(picking, commande_origine.name)

        return self._creer_facture_achat_depuis_po(commande_cible, config)

    def _creer_commande_achat_cible(self, origin, config):
        if origin.partner_id.company_id:
            origin.partner_id.sudo().write({'company_id': False})
        vals = {
            'partner_id': origin.partner_id.id,
            'company_id': config.societe_cible_id.id,
            'date_order': origin.date_order,
            'partner_ref': f"SYNC-{origin.name}",
            'order_line': []
        }
        for ligne in origin.order_line:
            taxes = self._mapper_taxes_vers_societe_cible_safe(ligne.taxes_id, config)
            vals['order_line'].append((0, 0, {
                'product_id': ligne.product_id.id,
                'name': ligne.name,
                'product_qty': ligne.product_qty,
                'price_unit': ligne.price_unit,
                'taxes_id': [(6, 0, taxes.ids)],
                'date_planned': ligne.date_planned,
            }))
        return self.env['purchase.order'].with_company(config.societe_cible_id).sudo().create(vals)

    def _creer_facture_achat_depuis_po(self, po_cible, config):
        invoice_vals = po_cible._prepare_invoice()
        invoice_vals.update({
            'ref': f"SYNC-{self.name}",
            'facture_origine_operationnelle_id': self.id,
            'invoice_line_ids': []
        })
        for line in po_cible.order_line:
            acc_src = (line.product_id.property_account_expense_id
                       or line.product_id.categ_id.property_account_expense_categ_id)
            acc = self._mapper_compte_vers_societe_cible(acc_src, config)
            taxes = self._mapper_taxes_vers_societe_cible_safe(line.taxes_id, config)
            invoice_vals['invoice_line_ids'].append((0, 0, {
                'product_id': line.product_id.id,
                'name': line.name,
                'quantity': line.product_qty,
                'price_unit': line.price_unit,
                'product_uom_id': line.product_uom.id,
                'account_id': acc.id,
                'tax_ids': [(6, 0, taxes.ids)],
                'purchase_line_id': line.id,
            }))
        return self.env['account.move'].with_company(config.societe_cible_id).sudo().create(invoice_vals)

    # ---------------------------------------------------------
    # GESTION DU STOCK ET DES LOTS (Odoo 16: quantity_done)
    # ---------------------------------------------------------
    def _traiter_stock_cible(self, picking, origin_name):
        if picking.state not in ['assigned', 'done']:
            picking.action_assign()
        for move in picking.move_ids:
            if move.product_id.tracking != 'none':
                lot_data = self._get_origin_lot_names(move.product_id, origin_name)
                if lot_data:
                    for item in lot_data:
                        lot = self._find_or_create_lot_v16(
                            move.product_id, item['name'], picking.company_id, origin_name)
                        self.env['stock.move.line'].sudo().create({
                            'move_id': move.id,
                            'picking_id': picking.id,
                            'product_id': move.product_id.id,
                            'lot_id': lot.id,
                            'qty_done': item['qty'],
                            'location_id': move.location_id.id,
                            'location_dest_id': move.location_dest_id.id,
                        })
                        
                else:
                    move.quantity_done = move.product_uom_qty
            else:
                move.quantity_done = move.product_uom_qty
        picking.button_validate()

    def _find_or_create_lot_v16(self, product, name, target_company, origin_name):
        lot = self.env['stock.lot'].sudo().search([
            ('name', '=', name),
            ('product_id', '=', product.id),
            '|', ('company_id', '=', target_company.id), ('company_id', '=', False)
        ], limit=1)
        if not lot:
            picking_origine = self.env['stock.picking'].sudo().search([
                ('origin', '=', origin_name), ('state', '=', 'done')
            ], limit=1)
            source_lot = self.env['stock.move.line'].sudo().search([
                ('picking_id', '=', picking_origine.id),
                ('product_id', '=', product.id),
                ('lot_id.name', '=', name)
            ], limit=1).lot_id
            vals = {'name': name, 'product_id': product.id, 'company_id': target_company.id}
            if source_lot:
                for f in ['expiration_date', 'use_date', 'removal_date', 'alert_date']:
                    if hasattr(source_lot, f):
                        vals[f] = source_lot[f]
            lot = self.env['stock.lot'].sudo().create(vals)
        return lot

    def _get_origin_lot_names(self, product, origin_name):
        """Retourne une liste de dict {name, qty} au lieu de juste les noms"""
        pickings = self.env['stock.picking'].sudo().search([
            ('origin', '=', origin_name), ('state', '=', 'done')
        ], limit=1)

        if not pickings:
            return []

        result = []
        for move in pickings.move_ids.filtered(lambda m: m.product_id == product):
            for ml in move.move_line_ids:
                if ml.lot_id:
                    result.append({
                        'name': ml.lot_id.name,
                        'qty': ml.qty_done or ml.reserved_uom_qty,
                    })
        return result


    # ---------------------------------------------------------
    # MAPPINGS ROBUSTES ET DIAGNOSTICS
    # ---------------------------------------------------------
    def _mapper_taxes_vers_societe_cible_safe(self, taxes_orig, config):
        if not taxes_orig:
            return self.env['account.tax']
        res = self.env['account.tax']
        for t in taxes_orig:
            # Stratégie 1: Nom + Montant + Type
            match = self.env['account.tax'].sudo().search([
                ('name', '=', t.name),
                ('amount', '=', t.amount),
                ('type_tax_use', '=', t.type_tax_use),
                ('company_id', '=', config.societe_cible_id.id)
            ], limit=1)
            # Stratégie 2: Montant + Type (Fallback)
            if not match:
                match = self.env['account.tax'].sudo().search([
                    ('amount', '=', t.amount),
                    ('type_tax_use', '=', t.type_tax_use),
                    ('company_id', '=', config.societe_cible_id.id)
                ], limit=1)
            if match:
                res |= match
        return res

    def _mapper_compte_vers_societe_cible(self, compte_orig, config):
        if not compte_orig:
            return self.env['account.account'].sudo().search([
                ('company_id', '=', config.societe_cible_id.id)
            ], limit=1)

        # Stratégie 1: Code exact
        compte = self.env['account.account'].sudo().search([
            ('code', '=', compte_orig.code),
            ('company_id', '=', config.societe_cible_id.id)
        ], limit=1)

        # Stratégie 2: Padding différent (ex: 700 -> 700000)
        if not compte and len(compte_orig.code) >= 3:
            for longueur in [6, 5, 4]:
                code_tronque = compte_orig.code[:longueur].ljust(longueur, '0')
                compte = self.env['account.account'].sudo().search([
                    ('code', '=', code_tronque),
                    ('company_id', '=', config.societe_cible_id.id)
                ], limit=1)
                if compte:
                    break

        # Stratégie 3: Fallback par type de compte
        if not compte:
            compte = self.env['account.account'].sudo().search([
                ('account_type', '=', compte_orig.account_type),
                ('company_id', '=', config.societe_cible_id.id)
            ], limit=1)

        if not compte:
            diag = self._diagnostiquer_comptes_manquants(compte_orig, config)
            raise UserError(_("❌ Compte %s introuvable dans %s\n\n%s") % (
                compte_orig.code, config.societe_cible_id.name, diag))
        return compte

    def _diagnostiquer_comptes_manquants(self, compte_op, config):
        lignes = [f"Type recherché : {compte_op.account_type}"]
        total = self.env['account.account'].sudo().search_count([
            ('company_id', '=', config.societe_cible_id.id)
        ])
        if total == 0:
            lignes.append("⚠️ Aucun compte dans la société cible (Plan comptable absent ?)")
        else:
            similaires = self.env['account.account'].sudo().search([
                ('code', '=like', f"{compte_op.code[:2]}%"),
                ('company_id', '=', config.societe_cible_id.id)
            ], limit=3)
            if similaires:
                lignes.append("📋 Suggestions : " + ", ".join(similaires.mapped('code')))
        return "\n".join(lignes)

    # ---------------------------------------------------------
    # FALLBACK DIRECT (Facture sans SO/PO)
    # ---------------------------------------------------------
    def _creer_facture_cible_directe(self, config):
        vals = self._preparer_vals_facture_cible(config)
        if not vals.get('invoice_line_ids'):
            raise UserError(_("Aucune ligne de facture n'a pu être mappée vers la société cible."))
        facture = self.env['account.move'].with_company(config.societe_cible_id).sudo().create(vals)
        facture.write({'facture_origine_operationnelle_id': self.id})
        return facture

    def _preparer_vals_facture_cible(self, config):
        j_type = 'sale' if self.move_type.startswith('out_') else 'purchase'
        journal = self.env['account.journal'].sudo().search([
            ('type', '=', j_type), ('company_id', '=', config.societe_cible_id.id)
        ], limit=1)
        vals = {
            'move_type': self.move_type,
            'partner_id': self.partner_id.id,
            'company_id': config.societe_cible_id.id,
            'journal_id': journal.id if journal else False,
            'invoice_date': self.invoice_date,
            'ref': f"SYNC-{self.name}",
            'invoice_line_ids': []
        }
        for l in self.invoice_line_ids:
            try:
                acc = self._mapper_compte_vers_societe_cible(l.account_id, config)
                taxes = self._mapper_taxes_vers_societe_cible_safe(l.tax_ids, config)
                vals['invoice_line_ids'].append((0, 0, {
                    'product_id': l.product_id.id,
                    'name': l.name,
                    'quantity': l.quantity,
                    'price_unit': l.price_unit,
                    'account_id': acc.id,
                    'tax_ids': [(6, 0, taxes.ids)],
                }))
            except Exception:
                continue
        return vals

    # ---------------------------------------------------------
    # PAIEMENTS ET LOGS
    # ---------------------------------------------------------
    def _trouver_paiements_rapproches(self):
        self.ensure_one()
        paiements = self.env['account.payment']
        lines = self.line_ids.filtered(
            lambda l: l.account_id.account_type in ['asset_receivable', 'liability_payable'])
        for line in lines:
            for match in line.matched_debit_ids + line.matched_credit_ids:
                pay_line = match.debit_move_id if match.credit_move_id == line else match.credit_move_id
                if pay_line.payment_id:
                    paiements |= pay_line.payment_id
        return paiements

    def _log_sync_success(self, facture_cible, config):
        if 'cpss.sync.log' in self.env:
            self.env['cpss.sync.log'].sudo()._log_sync_event(
                operation_name='Synchronisation Facture', status='success', sync_type='manual',
                source_doc=self, target_doc=facture_cible, config=config
            )
        self._message_log(body=_("✅ Facture synchronisée : %s") % facture_cible.name)

    def _log_sync_error(self, message_erreur, config):
        if 'cpss.sync.log' in self.env:
            self.env['cpss.sync.log'].sudo()._log_sync_event(
                operation_name='Synchronisation Facture', status='error', sync_type='manual',
                error_msg=message_erreur, source_doc=self, config=config
            )
        self._message_log(body=_("❌ Échec : %s") % message_erreur)