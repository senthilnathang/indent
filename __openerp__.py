# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.


{
    'name': 'Indent Management',
    'version': '1.2',
    'category': 'Indent Management',
    'sequence': 60,
    'summary': 'Indent Orders, Receipts',
    'description': """
        Manage Indents for Bakery and Confectionary
    """,
    'author': "Senthilnatha G",
    'website': "https://www.senthilnathan,info",

    'price': 499,
    'currency': 'EUR',
    'depends': ['account_accountant','account','stock','purchase','stock_account', 'report','point_of_sale'],
    'data': [
        'security/indent_security.xml',
        'security/advance_order_security.xml',
        'security/ir.model.access.csv',
        
        'data/indent_sequence.xml',
        'data/advance_sequence.xml',
        'data/indent_data.xml',
        'data/stock_data.xml',
        
        'indent_menu.xml',
        'indent_report.xml',
        'advance_report.xml',
        
        
        'views/product_categ_type_view.xml',
        'views/product_categ_type_lines_view.xml',
        'views/indent_view.xml',
        'views/custom_indent_view.xml',
        'views/factory_indent_view.xml',
        'views/store_indent_view.xml',
        'views/advance_order_view.xml',
        'views/stock_view.xml',
        'views/stock_immediate_transfer.xml',
        'views/stock_backorder_confirmation.xml',
        'views/wizard_delivery_info.xml',
        'views/res_partner_view.xml',
        'views/product_view.xml',
        
        'report/indent_report_view.xml',
        'views/report_indentorder.xml',
        'views/report_advanceorder.xml',

        #~ 'views/backend.xml',
        #~ 'views/templates.xml',
    ],
    'test': [
    ],
    'demo': [
    ],
    'qweb': [ 
    'static/src/xml/indent.xml',    
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
    'license': 'OEEL-1',
}
