from odoo import models, fields, api

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_medical_device = fields.Boolean(
        string='Est un Dispositif Médical',
        default=False,
        help="Cochez si ce produit est un dispositif médical"
    )
    
    medical_device_designation = fields.Char(
        string='Désignation du Dispositif Médical',
        help="Désignation officielle du dispositif médical"
    )
    
    country_origin_id = fields.Many2one(
        'res.country',
        string="Pays d'Origine",
        help="Pays d'origine du dispositif médical"
    )
    
    certification_type = fields.Char(
        string='Type de Certification',
        help="Type de certification du dispositif médical (ex: CE, ISO 13485, FDA...)"
    )
    
    manufacturer_id = fields.Many2one(
        'res.partner',
        string='Société/Laboratoire Fabricant',
        domain="[('is_company', '=', True)]",
        help="Fabricant du dispositif médical"
    )

    @api.onchange('categ_id')
    def _onchange_categ_id_medical_device(self):
        """Auto-check is_medical_device if category is medical device"""
        if self.categ_id and self.categ_id.is_medical_device_category:
            self.is_medical_device = True


class ProductCategory(models.Model):
    _inherit = 'product.category'

    is_medical_device_category = fields.Boolean(
        string='Catégorie Dispositifs Médicaux',
        default=False,
        help="Cochez si cette catégorie contient des dispositifs médicaux"
    )