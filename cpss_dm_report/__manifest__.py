{
    'name': 'Rapport Dispositifs Médicaux',
    'version': '16.0.1.0.0',
    'category': 'Inventory/Reporting',
    'summary': 'Rapport mensuel des dispositifs médicaux pour le Ministère de l\'Industrie Pharmaceutique',
    'description': """
        Module de génération de rapport Excel pour les dispositifs médicaux.
        - Suivi des mouvements de stock (entrées/sorties)
        - Export Excel conforme aux exigences du Ministère
        - Traçabilité par lots/numéros de série
    """,
    'author': 'CPSS',
    'website': 'https://www.cpss-dz.com',
    "license": "OPL-1",
    "price": "50",
    "currency": 'EUR',
    'depends': [
        'base',
        'product',
        'stock',
        'product_expiry',
        'purchase',
        'sale_stock',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/product_category_data.xml',
        'views/wizard_views.xml',
        'views/product_views.xml',
        'views/stock_lot_views.xml',
    ],
    'external_dependencies': {
        'python': ['xlsxwriter'],
    },
    'images': ['images/cpss_banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}