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


class CpssDmReportWizard(models.TransientModel):
    _name = 'cpss.dm.report.wizard'
    _description = 'Assistant Rapport Dispositifs Médicaux'

    date_from = fields.Date(string='Date Début', required=True, default=lambda self: fields.Date.today().replace(day=1))
    date_to = fields.Date(string='Date Fin', required=True, default=fields.Date.today)
    company_id = fields.Many2one('res.company', string='Société', required=True, default=lambda self: self.env.company)

    move_type_filter = fields.Selection([
        ('all', 'Entrées et Sorties'),
        ('entry', 'Entrées uniquement'),
        ('exit', 'Sorties uniquement'),
    ], string='Type de Mouvement', default='all', required=True)

    excel_file = fields.Binary(string='Fichier Excel')
    excel_filename = fields.Char(string='Nom du fichier')

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for record in self:
            if record.date_from > record.date_to:
                raise UserError(_("La date de début doit être antérieure à la date de fin."))

    def _get_historical_stock_qty(self, product, move_line=None, reference_date=None, lot_id=None):
        """Calcul du stock à une date T ou après un mouvement spécifique."""
        quant_domain = [('product_id', '=', product.id), ('company_id', '=', self.company_id.id),
                        ('location_id.usage', '=', 'internal')]
        if lot_id:
            quant_domain.append(('lot_id', '=', lot_id.id))

        quants = self.env['stock.quant'].search(quant_domain)
        current_stock = sum(quants.mapped('quantity'))

        target_date = move_line.date if move_line else reference_date
        target_id = move_line.id if move_line else 0

        move_domain = [('product_id', '=', product.id), ('state', '=', 'done'), ('company_id', '=', self.company_id.id)]
        if lot_id:
            move_domain.append(('lot_id', '=', lot_id.id))

        if move_line:
            move_domain += ['|', ('date', '>', target_date), '&', ('date', '=', target_date), ('id', '>', target_id)]
        else:
            move_domain += [('date', '>', target_date)]

        future_moves = self.env['stock.move.line'].search(move_domain)

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
        products = self.env['product.product'].search([('is_medical_device', '=', True), ('type', '=', 'product')])
        data = []

        for product in products:
            template = product.product_tmpl_id
            packaging = product.packaging_ids[0].name if product.packaging_ids else ''
            country_cert = f"{template.country_origin_id.name or ''} / {template.certification_type or ''}".strip(' / ')

            # Pré-calculer le stock FINAL au lot pour la colonne supplémentaire
            # On le fera à la volée pour chaque lot trouvé

            # A. Mouvements sur la période
            move_domain = [('product_id', '=', product.id), ('state', '=', 'done'), ('date', '>=', self.date_from),
                           ('date', '<=', self.date_to), ('company_id', '=', self.company_id.id)]
            move_lines = self.env['stock.move.line'].search(move_domain, order='date asc, id asc')

            if move_lines:
                for line in move_lines:
                    move_type, partner = self._get_move_type(line)
                    if move_type == 'internal': continue
                    if self.move_type_filter == 'entry' and move_type != 'entry': continue
                    if self.move_type_filter == 'exit' and move_type != 'exit': continue

                    # Stock final du lot à date_to
                    final_stock_val = self._get_historical_stock_qty(product, reference_date=self.date_to,
                                                                     lot_id=line.lot_id)

                    data.append({
                        'etablissement': self.company_id.name,
                        'designation_dm': template.medical_device_designation or template.name,
                        'denomination_commerciale': product.display_name,
                        'conditionnement': packaging,
                        'fabricant': template.manufacturer_id.name if template.manufacturer_id else '',
                        'pays_certification': country_cert,
                        'date_fabrication': getattr(line.lot_id, 'manufacturing_date', False),
                        'date_peremption': getattr(line.lot_id, 'expiration_date', False) or getattr(line.lot_id,
                                                                                                     'use_date', False),
                        'numero_lot': line.lot_id.name if line.lot_id else '',
                        'quantite_stock': self._get_historical_stock_qty(product, move_line=line, lot_id=line.lot_id),
                        'qty_livree': line.qty_done,
                        'client': partner.name if partner else '',
                        'date_mouvement': line.date,
                        'observation': 'Entrée' if move_type == 'entry' else 'Sortie',
                        'stock_final_periode': final_stock_val,
                    })

            # B. États de stock pour les Lots SANS mouvement
            if self.move_type_filter == 'all':
                quants = self.env['stock.quant'].search(
                    [('product_id', '=', product.id), ('company_id', '=', self.company_id.id),
                     ('location_id.usage', '=', 'internal')])
                lots_in_stock = quants.mapped('lot_id')

                for lot in lots_in_stock:
                    if any(m.lot_id == lot for m in move_lines): continue

                    stock_at_end = self._get_historical_stock_qty(product, reference_date=self.date_to, lot_id=lot)
                    if stock_at_end > 0:
                        data.append({
                            'etablissement': self.company_id.name,
                            'designation_dm': template.medical_device_designation or template.name,
                            'denomination_commerciale': product.display_name,
                            'conditionnement': packaging,
                            'fabricant': template.manufacturer_id.name if template.manufacturer_id else '',
                            'pays_certification': country_cert,
                            'date_fabrication': getattr(lot, 'manufacturing_date', False),
                            'date_peremption': getattr(lot, 'expiration_date', False) or getattr(lot, 'use_date',
                                                                                                 False),
                            'numero_lot': lot.name,
                            'quantite_stock': stock_at_end,
                            'qty_livree': 0,
                            'client': '',
                            'date_mouvement': False,
                            'observation': 'Stock statique (sans mouvement)',
                            'stock_final_periode': stock_at_end,
                        })
        return data

    def generate_excel_report(self):
        if not xlsxwriter: raise UserError(_("xlsxwriter missing."))
        data = self._prepare_report_data()
        if not data: raise UserError(_("Aucune donnée."))
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Rapport DM')

        # Formats
        header_fmt = workbook.add_format(
            {'bold': True, 'bg_color': '#4472C4', 'font_color': 'white', 'border': 1, 'align': 'center',
             'valign': 'vcenter', 'text_wrap': True})
        cell_fmt = workbook.add_format({'border': 1, 'align': 'left', 'valign': 'vcenter'})
        num_fmt = workbook.add_format({'border': 1, 'align': 'center', 'valign': 'vcenter', 'num_format': '#,##0'})
        date_fmt = workbook.add_format(
            {'border': 1, 'align': 'center', 'valign': 'vcenter', 'num_format': 'dd/mm/yyyy'})
        final_stock_fmt = workbook.add_format({'border': 1, 'align': 'center', 'bg_color': '#E2EFDA',
                                               'num_format': '#,##0'})  # Vert clair pour distinguer
        title_fmt = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'center'})

        headers = [
            ('ETABLISSEMENT PHARMACEUTIQUE', 25), ('DESIGNATION DM', 35), ('DENOMINATION COMMERCIALE', 30),
            ('CONDITIONNEMENT', 15), ('FABRICANT', 25), ('PAYS / CERTIFICATION', 30),
            ('DATE FABRICATION', 15), ('DATE PEREMPTION', 15), ('N° LOT', 15),
            ('STOCK AU MOUVEMENT', 18), ('QTE LIVREE/RECUE', 15), ('CLIENTS', 25),
            ('A LA DATE DU', 15), ('OBSERVATION', 20)
        ]

        worksheet.merge_range(0, 0, 0, len(headers) - 1, 'RAPPORT MENSUEL DES DISPOSITIFS MEDICAUX', title_fmt)
        worksheet.merge_range(1, 0, 1, len(headers) - 1, f"Période: {self.date_from} au {self.date_to}", title_fmt)

        # En-têtes principaux
        for col, (header, width) in enumerate(headers):
            worksheet.write(4, col, header, header_fmt)
            worksheet.set_column(col, col, width)

        # Colonne supplémentaire séparée
        buffer_col = len(headers)
        worksheet.set_column(buffer_col, buffer_col, 3)  # Colonne vide étroite
        final_stock_col = buffer_col + 1
        worksheet.write(4, final_stock_col, 'STOCK FINAL PERIODE', header_fmt)
        worksheet.set_column(final_stock_col, final_stock_col, 18)

        row_idx = 5
        for row in data:
            worksheet.write(row_idx, 0, row['etablissement'], cell_fmt)
            worksheet.write(row_idx, 1, row['designation_dm'], cell_fmt)
            worksheet.write(row_idx, 2, row['denomination_commerciale'], cell_fmt)
            worksheet.write(row_idx, 3, row['conditionnement'], cell_fmt)
            worksheet.write(row_idx, 4, row['fabricant'], cell_fmt)
            worksheet.write(row_idx, 5, row['pays_certification'], cell_fmt)

            if row['date_fabrication']:
                worksheet.write_datetime(row_idx, 6, row['date_fabrication'], date_fmt)
            else:
                worksheet.write(row_idx, 6, '', cell_fmt)

            if row['date_peremption']:
                worksheet.write_datetime(row_idx, 7, row['date_peremption'], date_fmt)
            else:
                worksheet.write(row_idx, 7, '', cell_fmt)

            worksheet.write(row_idx, 8, row['numero_lot'], cell_fmt)
            worksheet.write(row_idx, 9, row['quantite_stock'], num_fmt)
            worksheet.write(row_idx, 10, row['qty_livree'], num_fmt)
            worksheet.write(row_idx, 11, row['client'], cell_fmt)

            if row['date_mouvement']:
                worksheet.write_datetime(row_idx, 12, row['date_mouvement'], date_fmt)
            else:
                worksheet.write(row_idx, 12, '', cell_fmt)

            worksheet.write(row_idx, 13, row['observation'], cell_fmt)

            # Écriture du Stock Final dans la colonne séparée
            worksheet.write(row_idx, final_stock_col, row['stock_final_periode'], final_stock_fmt)

            row_idx += 1

        worksheet.freeze_panes(5, 0)
        workbook.close()
        output.seek(0)
        self.excel_file = base64.b64encode(output.read())
        self.excel_filename = f"rapport_dm_{self.date_to}.xlsx"

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/?model=cpss.dm.report.wizard&id={self.id}&field=excel_file&filename_field=excel_filename&download=true',
            'target': 'self',
        }