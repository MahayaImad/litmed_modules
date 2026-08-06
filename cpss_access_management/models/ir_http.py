# -*- coding: utf-8 -*-
import hashlib

from odoo import models


class IrHttp(models.AbstractModel):
    """Informations de session complétées par le module.

    Deux besoins, tous deux résolus au chargement pour éviter un aller-retour
    supplémentaire : la couleur de chaque société autorisée, et une empreinte
    de cache des menus qui tienne compte de la société active.
    """
    _inherit = 'ir.http'

    def session_info(self):
        info = super().session_info()
        self._cpss_ajouter_couleurs_societes(info)
        self._cpss_varier_empreinte_menus(info)
        return info

    def _cpss_ajouter_couleurs_societes(self, info):
        """Publie la couleur de chaque société autorisée.

        Le script de la barre de navigation résout ainsi la couleur à partir
        du seul cookie de société active, sans appel au serveur.
        """
        societes = (info.get('user_companies') or {}).get('allowed_companies')
        if not societes:
            return
        couleurs = {
            company.id: company.navbar_color or False
            for company in self.env.user.company_ids
        }
        for identifiant, donnees in societes.items():
            if isinstance(donnees, dict):
                donnees['navbar_color'] = couleurs.get(int(identifiant), False)

    def _cpss_varier_empreinte_menus(self, info):
        """Fait entrer la société active dans l'empreinte de cache des menus.

        Odoo sert ``/web/webclient/load_menus/<empreinte>`` avec un cache
        navigateur de longue durée, et cette empreinte ne dépend pas de la
        société. Sans cette variation, un basculement de société rejouerait
        le menu mis en cache pour la société précédente : les restrictions par
        société seraient calculées correctement côté serveur mais jamais
        redemandées par le client.

        L'ensemble des menus masqués entre aussi dans l'empreinte, pour qu'un
        changement de règle soit visible sans vider le cache du navigateur.
        """
        empreintes = info.get('cache_hashes')
        if not isinstance(empreintes, dict) or 'load_menus' not in empreintes:
            return
        resolveur = self.env['cpss.access.resolver']
        graine = '%s-%s-%s' % (
            empreintes['load_menus'],
            resolveur._get_active_company_id(),
            sorted(resolveur._get_user_restrictions()['menus']),
        )
        empreintes['load_menus'] = hashlib.sha1(
            graine.encode('utf-8')).hexdigest()
