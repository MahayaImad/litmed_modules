{
    'name': 'CPSS Invoice Reshaping',
    'version': '16.0.1.0.0',
    'category': 'Accounting/Localizations',
    'summary': 'Move default Lots table into specific Invoice Lines and change invoices logic',
    'depends': ['account', 'stock_account', 'l10n_dz_cpss_invoice'],
    'data':[
        'views/report_invoice.xml',
        'views/report_invoice_lots.xml',
        'views/report_invoice_bl_ttc.xml',
        'views/report_invoice_bl.xml',
        'views/report_invoice_document_hide_lots.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}