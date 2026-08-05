{
    'name': "Factures aux normes Algériennes",
    'summary': "Factures aux normes algériennes.",
    'category': 'Accounting/accounting',
    'version': '16.0.2.1',

    "contributors": [
        "Cedar Peak Systems & Solutions Team",
    ],
    'sequence': 1,

    'author': 'Cedar Peak Systems & Solutions (CPSS)',
    'website': 'https://cedarpss.com/',

    "license": "LGPL-3",
    "price": 0,
    "currency": 'USD',

    'depends': [
        'base',
        'account',
        'sale',
        'purchase',
        'stock',
        'l10n_dz_invoice',
    ],
    'data': [
        'views/res_campany_views.xml',
        'reports/sale_invoice_report.xml',
        'reports/purchase_order_report.xml',
        'reports/account_invoice_report.xml',
        #'reports/stock_deliveryslip_report.xml',
        'reports/inherit_header_footer_boxed.xml',
        'reports/inherit_header_footer_bold.xml',
        'reports/inherit_header_footer.xml',
    ],
    'images': ['images/cpss_banner.png'],
    'installable': True,
    'auto_install': False,
    'application': True,
}