# -*- coding: utf-8 -*-
from odoo import models
from odoo.http import request


class IrHttp(models.AbstractModel):
    """Publie la couleur de chaque société autorisée dans la session.

    Le client a besoin de la couleur de la société active dès le premier
    rendu de la barre de navigation. La faire transiter par les informations
    de session évite un appel RPC supplémentaire au chargement, et permet au
    script de résoudre la couleur à partir du seul cookie de société active.
    """
    _inherit = 'ir.http'

    def session_info(self):
        info = super().session_info()
        societes = (info.get('user_companies') or {}).get('allowed_companies')
        if not societes:
            return info
        couleurs = {
            company.id: company.navbar_color or False
            for company in request.env.user.company_ids
        }
        for identifiant, donnees in societes.items():
            if isinstance(donnees, dict):
                donnees['navbar_color'] = couleurs.get(int(identifiant), False)
        return info
