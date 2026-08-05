# -*- coding: utf-8 -*-
from . import models


def post_init_hook(cr, registry):
    """
    Hook exécuté après l'installation du module
    Corrige les sociétés existantes sans journal de transfert
    """
    from odoo import api, SUPERUSER_ID
    import logging

    _logger = logging.getLogger(__name__)

    env = api.Environment(cr, SUPERUSER_ID, {})

    # Rechercher toutes les sociétés sans journal de transfert
    companies = env['res.company'].search([
        ('transfer_tax_journal', '=', False)
    ])

    _logger.info(f"Correction de {len(companies)} société(s) sans journal de transfert")

    for company in companies:
        # Rechercher un journal général pour cette société
        default_journal = env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', company.id)
        ], limit=1)

        if default_journal:
            try:
                company.write({'transfer_tax_journal': default_journal.id})
                _logger.info(f"Journal de transfert défini pour la société {company.name}: {default_journal.name}")
            except Exception as e:
                _logger.error(f"Erreur lors de la définition du journal pour {company.name}: {str(e)}")
        else:
            _logger.warning(f"Aucun journal général trouvé pour la société {company.name}")

    _logger.info("Correction des sociétés terminée")