
{
    "name": "CPSS Sync Inter Company Base",
    "summary": "Base module for synchronization between operational and fiscal companies",
    "version": "16.0.1.1.0",
    "category": "Accounting & Finance",
    "website": "https://github.com/cpss/odoo-modules",
    "author": "CPSS",
    "license": "AGPL-3",
    "installable": True,
    "depends": [
        "base",
        "mail",
        "account",
        "sale",
        "purchase",
        "stock",
        #"l10n_dz_cpss",
    ],
    "data": [
        # Security
        "security/sync_security.xml",
        "security/ir_rules_sync.xml",
        "security/ir.model.access.csv",

        # Data
        "data/auto_setup_data.xml",

        # Views
        'views/cpss_sync_config_views.xml',
        'views/cpss_sync_log_views.xml',
        'views/account_move_views.xml',
        'views/account_payment_views.xml',
        'views/sync_menus.xml',
    ],

    "external_dependencies": {
        "python": [],
    },
    "pre_init_hook": "pre_init_hook",
    "post_init_hook": "post_init_hook",
}