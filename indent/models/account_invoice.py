# -*- coding: utf-8 -*-

import json
from lxml import etree
from datetime import datetime
from dateutil.relativedelta import relativedelta

from openerp import api, fields, models, _
from openerp.tools import float_is_zero, float_compare
from openerp.tools.misc import formatLang

from openerp.exceptions import UserError, RedirectWarning, ValidationError

import openerp.addons.decimal_precision as dp


class AccountInvoice(models.Model):
    _inherit = "account.invoice"

    advance_order_id = fields.Many2one('advance.order','Advance Order')
    total_payable = fields.Monetary(string='Payable',related='partner_id.debit')
    total_receivable = fields.Monetary(string='Receivable',related='partner_id.credit')
    
    
