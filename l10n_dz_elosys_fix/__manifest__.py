# -*- coding: utf-8 -*-
{
    'name': "Correctif - Comptabilité Algérie",
    'summary': """Correctif pour résoudre l'erreur 'can't adapt type account.journal'""",
    'description': """
        Ce module corrige les problèmes suivants dans l10n_dz_elosys:
        - Erreur PostgreSQL lors de la création de sociétés
        - Conversion correcte des recordsets en IDs
        - Gestion améliorée des valeurs par défaut
    """,
    'version': '16.0.1.0.0',
    'category': 'Accounting/Localizations',
    'author': 'CPSS',
    'license': 'LGPL-3',

    'depends': [
        'l10n_dz_elosys',
    ],

    'data': [],

    'post_init_hook': 'post_init_hook',

    'installable': True,
    'auto_install': False,
    'application': False,
}