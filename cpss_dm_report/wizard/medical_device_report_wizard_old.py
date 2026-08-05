import io
import base64
import logging
from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class MedicalDeviceReportWizard(models.TransientModel):
    _name = 'medical.device.report.wizard'
    _description = 'Assistant Rapport Dispositifs Médicaux'

    date_from = fields.Date(string='Date Début', required=True, default=lambda self: fields.Date.today().replace(day=1))
    date_to = fields.Date(string='Date Fin', required=True, default=fields.Date.today)
    company_id = fields.Many2one('res.company', string='Société', required=True, default=lambda self: self.env.company)
    excel_file = fields.Binary(string='Fichier Excel')
    excel_filename = fields.Char(string='Nom du fichier')

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for record in self:
            if record.date_from > record.date_to:
                raise UserError(_("La date de début doit être antérieure à la date de fin."))

    def _get_historical_stock_qty_reverse(self, product, move_line=None, reference_date=None):
        """
        Calcul inverse : Stock à l'instant T = Stock Actuel - (Mouvements futurs).
        Si move_line est fourni, utilise l'ID comme tie-breaker.
        Si seul reference_date est fourni, calcule le stock à la fin de cette journée.
        """
        current_stock = product.with_context(company_id=self.company_id.id).qty_available

        domain = [
            ('product_id', '=', product.id),
            ('state', '=', 'done'),
            ('company_id', '=', self.company_id.id),
        ]

        if move_line:
            domain += ['|', ('date', '>', move_line.date), '&', ('date', '=', move_line.date),
                       ('id', '>', move_line.id)]
        elif reference_date:
            # Pour les produits sans mouvement, on veut le stock à la date de fin du rapport
            domain += [('date', '>', reference_date)]

        future_moves = self.env['stock.move.line'].search(domain)

        diff = 0.0
        for move in future_moves:
            if move.location_dest_id.usage == 'internal' and move.location_id.usage != 'internal':
                diff += move.qty_done
            elif move.location_id.usage == 'internal' and move.location_dest_id.usage != 'internal':
                diff -= move.qty_done

        return current_stock - diff

    def _get_move_type(self, move_line):
        move = move_line.move_id
        picking = move.picking_id
        if picking:
            if picking.picking_type_id.code == 'incoming':
                return 'entry', picking.partner_id
            elif picking.picking_type_id.code == 'outgoing':
                return 'exit', picking.partner_id

        if move_line.location_dest_id.usage == 'internal' and move_line.location_id.usage != 'internal':
            return 'entry', move.partner_id
        elif move_line.location_id.usage == 'internal' and move_line.location_dest_id.usage != 'internal':
            return 'exit', move.partner_id
        return 'internal', move.partner_id

    def _prepare_report_data(self):
        """
        Prépare les données en incluant :
        1. Les produits avec mouvements (historique ligne par ligne)
        2. Les produits sans mouvements mais en stock (une seule ligne d'état)
        """
        # 1. Trouver tous les produits DM
        all_medical_products = self.env['product.product'].search([
            ('is_medical_device', '=', True),
            ('type', '=', 'product')
        ])

        # 2. Trouver tous les mouvements sur la période
        move_domain = [
            ('state', '=', 'done'),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('product_id.is_medical_device', '=', True),
            ('company_id', '=', self.company_id.id),
        ]
        all_moves = self.env['stock.move.line'].search(move_domain,
                                                       order='product_id asc, date asc, lot_id asc, id asc')

        products_with_moves = all_moves.mapped('product_id')
        data = []

        # Cas A : Produits avec mouvements
        for line in all_moves:
            product = line.product_id
            template = product.product_tmpl_id
            move_type, partner = self._get_move_type(line)
            if move_type == 'internal': continue

            mfg_date = line.lot_id.create_date if line.lot_id else False
            exp_date = getattr(line.lot_id, 'expiration_date', False) or getattr(line.lot_id, 'use_date',
                                                                                 False) if line.lot_id else False

            data.append(self._format_row(product, template, line, move_type, partner, mfg_date, exp_date))

        # Cas B : Produits sans mouvement mais potentiellement en stock
        products_without_moves = all_medical_products - products_with_moves
        for product in products_without_moves:
            # On calcule le stock à la date de fin
            stock_at_end = self._get_historical_stock_qty_reverse(product, reference_date=self.date_to)

            if stock_at_end != 0:
                template = product.product_tmpl_id
                data.append({
                    'etablissement': self.company_id.name,
                    'designation_dm': product.medical_device_designation or product.display_name,
                    'denomination_commerciale': product.name,
                    'conditionnement': product.packaging_ids[0].name if product.packaging_ids else '',
                    'fabricant': template.manufacturer_id.name if template.manufacturer_id else '',
                    'pays_certification': f"{template.country_origin_id.name or ''} / {template.certification_type or ''}".strip(
                        ' / '),
                    'date_fabrication': False,
                    'date_peremption': False,
                    'numero_lot': '',
                    'quantite_stock': stock_at_end,
                    'qty_livree': 0,
                    'client': '',
                    'date_mouvement': False,
                    'observation': _('Aucun mouvement (Solde au %s)') % self.date_to.strftime('%d/%m/%Y'),
                })

        # Tri Final : Produit, Date (False en dernier pour les soldes fixes)
        return sorted(data, key=lambda x: (x['denomination_commerciale'], x['date_mouvement'] or datetime.max))

    def _format_row(self, product, template, line, move_type, partner, mfg_date, exp_date):
        return {
            'etablissement': self.company_id.name,
            'designation_dm': product.medical_device_designation or product.display_name,
            'denomination_commerciale': product.name,
            'conditionnement': product.packaging_ids[0].name if product.packaging_ids else '',
            'fabricant': template.manufacturer_id.name if template.manufacturer_id else '',
            'pays_certification': f"{template.country_origin_id.name or ''} / {template.certification_type or ''}".strip(
                ' / '),
            'date_fabrication': mfg_date,
            'date_peremption': exp_date,
            'numero_lot': line.lot_id.name if line.lot_id else '',
            'quantite_stock': self._get_historical_stock_qty_reverse(product, line),
            'qty_livree': line.qty_done if move_type == 'exit' else 0,
            'client': partner.name if partner else '',
            'date_mouvement': line.date,
            'observation': 'Entrée' if move_type == 'entry' else 'Sortie',
        }

    def generate_excel_report(self):
        if not xlsxwriter: raise UserError(_("xlsxwriter missing."))
        data = self._prepare_report_data()
        if not data: raise UserError(_("Aucune donnée."))

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Rapport DM')

        # Styles
        h_fmt = workbook.add_format(
            {'bold': True, 'bg_color': '#4472C4', 'font_color': 'white', 'border': 1, 'align': 'center',
             'valign': 'vcenter', 'text_wrap': True})
        c_fmt = workbook.add_format({'border': 1, 'valign': 'vcenter'})
        n_fmt = workbook.add_format({'border': 1, 'align': 'center', 'num_format': '#,##0'})
        d_fmt = workbook.add_format({'border': 1, 'align': 'center', 'num_format': 'dd/mm/yyyy'})

        headers = [
            ('ETABLISSEMENT', 20), ('DESIGNATION DM', 35), ('DENOMINATION', 25),
            ('CONDITIONNEMENT', 15), ('FABRICANT', 20), ('PAYS/CERTIF', 25),
            ('DATE FAB.', 15), ('DATE PEREMP.', 15), ('N° LOT', 15),
            ('STOCK AU MOMENT', 15), ('QTE LIVREE', 15), ('CLIENT', 20),
            ('DATE MOUV.', 15), ('OBSERVATION', 25)
        ]

        for col, (h, w) in enumerate(headers):
            worksheet.write(0, col, h, h_fmt)
            worksheet.set_column(col, col, w)

        for idx, row in enumerate(data, 1):
            worksheet.write(idx, 0, row['etablissement'], c_fmt)
            worksheet.write(idx, 1, row['designation_dm'], c_fmt)
            worksheet.write(idx, 2, row['denomination_commerciale'], c_fmt)
            worksheet.write(idx, 3, row['conditionnement'], c_fmt)
            worksheet.write(idx, 4, row['fabricant'], c_fmt)
            worksheet.write(idx, 5, row['pays_certification'], c_fmt)
            if row['date_fabrication']:
                worksheet.write_datetime(idx, 6, row['date_fabrication'], d_fmt)
            else:
                worksheet.write(idx, 6, '', c_fmt)
            if row['date_peremption']:
                worksheet.write_datetime(idx, 7, row['date_peremption'], d_fmt)
            else:
                worksheet.write(idx, 7, '', c_fmt)
            worksheet.write(idx, 8, row['numero_lot'], c_fmt)
            worksheet.write(idx, 9, row['quantite_stock'], n_fmt)
            worksheet.write(idx, 10, row['qty_livree'], n_fmt)
            worksheet.write(idx, 11, row['client'], c_fmt)
            if row['date_mouvement']:
                worksheet.write_datetime(idx, 12, row['date_mouvement'], d_fmt)
            else:
                worksheet.write(idx, 12, '', d_fmt)
            worksheet.write(idx, 13, row['observation'], c_fmt)

        worksheet.freeze_panes(1, 0)
        workbook.close()
        output.seek(0)
        self.write(
            {'excel_file': base64.b64encode(output.read()), 'excel_filename': f"Rapport_DM_{self.date_from}.xlsx"})
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/?model={self._name}&id={self.id}&field=excel_file&filename_field=excel_filename&download=true',
            'target': 'self',
        }