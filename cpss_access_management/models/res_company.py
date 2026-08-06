# -*- coding: utf-8 -*-
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

COULEUR_HEXA = re.compile(r'^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$')

# Couleurs proposées par défaut, une par société, pour éviter d'avoir à
# choisir une teinte à la main sur une base multi-sociétés.
PALETTE_DEFAUT = (
    '#714B67',  # violet Odoo
    '#017E84',  # sarcelle
    '#A24689',  # magenta
    '#00689B',  # bleu
    '#875A7B',  # prune
    '#6C757D',  # gris
)


class ResCompany(models.Model):
    """Couleur d'identification de la société dans la barre de navigation.

    Le repère est purement visuel : sur une base multi-sociétés, il évite de
    saisir un document dans la mauvaise société sans s'en rendre compte. La
    couleur est publiée dans les informations de session et appliquée côté
    navigateur à partir du cookie de société active, sans aller la relire sur
    le serveur à chaque changement.
    """
    _inherit = 'res.company'

    navbar_color = fields.Char(
        string="Couleur de la barre de menu",
        help="Couleur hexadécimale (#RRGGBB) appliquée à la barre de "
             "navigation lorsque cette société est la société active. "
             "Laisser vide pour conserver la couleur standard d'Odoo.")

    @api.constrains('navbar_color')
    def _check_navbar_color(self):
        for company in self:
            couleur = (company.navbar_color or '').strip()
            if couleur and not COULEUR_HEXA.match(couleur):
                raise ValidationError(_(
                    "« %s » n'est pas une couleur hexadécimale valide. "
                    "Format attendu : #RRGGBB, par exemple #017E84."
                ) % company.navbar_color)

    @api.model
    def _cpss_couleur_par_defaut(self, index):
        return PALETTE_DEFAUT[index % len(PALETTE_DEFAUT)]

    def action_cpss_couleur_par_defaut(self):
        """Attribue une couleur distincte à chaque société sans couleur."""
        companies = self.search([]) if not self else self
        for index, company in enumerate(companies):
            if not company.navbar_color:
                company.navbar_color = self._cpss_couleur_par_defaut(index)
        return True
