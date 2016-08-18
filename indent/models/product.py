# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import datetime
from dateutil.relativedelta import relativedelta
from openerp import api, fields, models, _, SUPERUSER_ID
#~ from openerp.addons.hsr_pos.models import fields as fields2
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT
from openerp.tools.translate import _
from openerp.tools.float_utils import float_is_zero, float_compare
import openerp.addons.decimal_precision as dp
from openerp.exceptions import UserError, AccessError

class ProductCategType(models.Model):
    _name = 'product.categ.type'
    _description ='Product Categ Type'
    name = fields.Char('Product Category Type',size=128,required=True)
    order_type = fields.Selection([('factory','Factory'),('store','Store')],'Order Type')
    product_lines = fields.One2many('product.categ.type.lines','product_categ_type_id','Product Lines')

class ProductCategTypeLines(models.Model):
    _name = 'product.categ.type.lines'
    _description ='Product Categ Type Lines'
    product_id = fields.Many2one('product.product','Product')
    product_categ_type_id = fields.Many2one('product.categ.type','Product Categ Type')

class ProductTemplate(models.Model):
    _name = 'product.template'
    _inherit = 'product.template'

    @api.model
    def _get_buy_route(self):
        buy_route = self.env.ref('indent.route_warehouse0_buy')
        if buy_route:
            return buy_route.ids
        return []

    @api.multi
    def _indent_count(self):
        for template in self:
            template.indent_count_raised = sum([p.indent_count_raised for p in template.product_variant_ids])
            template.indent_count_received = sum([p.indent_count_received for p in template.product_variant_ids])
            template.pos_sales_count = sum([p.pos_sales_count for p in template.product_variant_ids])
        return True

    property_account_creditor_price_difference = fields.Many2one(
        'account.account', string="Price Difference Account", company_dependent=True,
        help="This account will be used to value price difference between indent price and cost price.")
    indent_ok = fields.Boolean('Can be Indented', default=True)
    indent_count_raised = fields.Integer(compute='_indent_count', string='# Indents Raised')
    indent_count_received = fields.Integer(compute='_indent_count', string='# Indents Received')
    pos_sales_count = fields.Integer(compute='_indent_count', string='# POS Sales')
    indent_method = fields.Selection([
        ('indent', 'On ordered quantities'),
        ('receive', 'On received quantities'),
        ], string="Control Indent Bills", default="receive")
    route_ids = fields.Many2many(default=lambda self: self._get_buy_route())
    product_categ_type_id = fields.Many2one('product.categ.type','Product Category Type')


class ProductProduct(models.Model):
    _name = 'product.product'
    _inherit = 'product.product'

    @api.multi
    def _indent_count(self):
        domain_receive = [
            ('state', 'in', [ 'done']),
            ('product_id', 'in', self.mapped('id')),
        ]
        domain_raise = [
            ('state', 'in', [ 'approve','production','produced','dispatch','delivered','done']),
            ('product_id', 'in', self.mapped('id')),
        ]
        r = {}
        for group in self.env['indent.report'].read_group(domain_raise, ['product_id', 'quantity'], ['product_id']):
            r[group['product_id'][0]] = group['quantity']
        for product in self:
            product.indent_count_raised = r.get(product.id, 0)

        for group in self.env['indent.report'].read_group(domain_receive, ['product_id', 'quantity'], ['product_id']):
            r[group['product_id'][0]] = group['quantity']
        for product in self:
            product.indent_count_received = r.get(product.id, 0)
        return True

    @api.multi
    def _pos_sales_count(self):
        r = {}
        domain = [
            ('state', 'in', ['paid', 'done','invoiced']),
            ('product_id', 'in', self.ids),
        ]
        for group in self.env['report.pos.order'].read_group(domain, ['product_id', 'product_qty'], ['product_id']):
            r[group['product_id'][0]] = group['product_qty']
        for product in self:
            product.pos_sales_count = r.get(product.id, 0)
        return r

    def _stock_move_dump_count(self):
        r = {}
        move_pool=self.env['stock.move']
        domain = [
            ('product_id', 'in', self.ids),
            ('location_dest_id.dump_location','=',True),
            ('state','in',['done'])
        ]
        for group in  move_pool.read_group(domain, ['product_id','product_qty'], ['product_id']) :
            r[group['product_id'][0]] = group['product_qty']
        for product in self:
            product.dump_count = r.get(product.id, 0)
        #~ domain = [
            #~ ('product_id', 'in', self.ids),
            #~ ('location_id.usage', '=', 'internal'),
            #~ ('location_dest_id.usage', '!=', 'internal'),
            #~ ('state','in',['confirmed','assigned','pending'])
        #~ ],
        #~ for group in  move_pool.read_group(domain, ['product_id'], ['product_id']) :
             #~ r[group['product_id'][0]] = group['product_id_count']
        #~ for product in self:
            #~ product.delivery_count = r.get(product.id, 0)
        return r



    pos_sales_count = fields.Integer(compute='_pos_sales_count', string='# POS Sales')
    indent_count_raised = fields.Integer(compute='_indent_count', string='# Indents Raised')
    indent_count_received  = fields.Integer(compute='_indent_count', string='# Indents Received')
    dump_count = fields.Integer(compute ='_stock_move_dump_count', string="Dump")
    #~ delivery_count = fields.Integer(compute='_stock_move_count', string="Delivery")
