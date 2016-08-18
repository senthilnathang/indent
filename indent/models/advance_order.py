# -*- coding: utf-8 -*-

import json
from lxml import etree
from datetime import datetime
from dateutil.relativedelta import relativedelta
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT
from openerp import api, fields, models, _
from openerp.tools import float_is_zero, float_compare
from openerp.tools.misc import formatLang

from openerp.exceptions import UserError, RedirectWarning, ValidationError
from openerp import netsvc
import openerp.addons.decimal_precision as dp



    
class AdvanceOrder(models.Model):
    _name = "advance.order"
    _inherit = ['mail.thread']
    _description = "Advance Order"
    _order = "date_order desc, id desc"



    @api.one
    @api.depends('state', 'payment_ids','advance_order_line_ids.price_total')
    def _compute_amount(self):
        self.amount_total = sum(line.price_total for line in self.advance_order_line_ids)
        self.amount_due = self.amount_total - self.amount_paid
        remain = ((self.amount_total)*100)%100
        if remain !=0:
            if remain < 50:
                self.amount_round_off = -remain/100
            else:
                self.amount_round_off = (100 - remain)/100
        self.amount_total = sum(line.price_total for line in self.advance_order_line_ids)
        #~ self.amount_total = sum(line.price_total for line in self.advance_order_line_ids)+self.amount_round_off
        if self.payment_ids:
            self.amount_paid = sum(x.amount  for x in self.payment_ids if x.state == 'posted')
            self.amount_due = self.amount_total - self.amount_paid
        else:
            self.amount_paid = 0.0
            self.amount_due = self.amount_total - self.payment_amount
                

    name = fields.Char(string='Reference/Description', index=True,
        readonly=True, states={'draft': [('readonly', False)]}, copy=False, help='The name that will be used on account move lines')
    user_id = fields.Many2one('res.users','User',required=True,default=lambda self: self.env.user,readonly=True, index=True)
    company_id = fields.Many2one('res.company', string='Company', change_default=True,
        required=True, readonly=True, states={'draft': [('readonly', False)]},
        default=lambda self: self.env['res.company']._company_default_get('advance.order'))
    payment_type = fields.Selection([('cash','CASH'),('bank','Credit/Debit Card')],'Payment Type',readonly=True, states={'draft': [('readonly', False)]}, index=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True, default=lambda self: self.env.user.company_id.currency_id)
    partner_id = fields.Many2one('res.partner','Customer',required=True,readonly=True, states={'draft': [('readonly', False)]}, index=True,)
    total_receivable = fields.Monetary(string='Receivable',related='partner_id.credit',store=True)
    total_receivable_all = fields.Monetary(string='Receivable',related='partner_id.credit')
    invoice_id = fields.Many2one('account.invoice','Invoice',copy=False)
    payment_amount = fields.Float('Advance Amount',copy=False,readonly=True, states={'draft': [('readonly', False)]}, index=True)
    state = fields.Selection([
            ('draft','New'),
            ('approved', 'Approved'),
            ('production', 'In Production'),
            ('completed', 'Production Completed'),
            ('cancel', 'Cancelled'),
            ('dispatched', 'Dispatched'),
            ('delivered', 'Delivered'),
        ], string='Status', index=True, readonly=True, default='draft',
        track_visibility='onchange', copy=False)
    sent = fields.Boolean(readonly=True, default=False, copy=False,
        help="It indicates that the invoice has been sent.")
    date_order = fields.Datetime(string='Order Date', default=fields.Datetime.now,
        readonly=True, states={'draft': [('readonly', False)]}, index=True,
        help="Keep empty to use the current date", copy=False) 
    date_delivery = fields.Datetime(string='Delivery Date', default=fields.Datetime.now,
        readonly=True, states={'draft': [('readonly', False)]}, index=True,
        help="Keep empty to use the current date", copy=False) 
    advance_order_line_ids = fields.One2many('advance.order.line', 'advance_order_id', string='Advance Order Lines',
        readonly=True, states={'draft': [('readonly', False)]}, copy=True)
    #~ amount_round_off = fields.Float(string='Round Off',
        #~ store=True, readonly=True, compute='_compute_amount')
    amount_total = fields.Float(string='Total',
        store=True, readonly=True, compute='_compute_amount')
    amount_due = fields.Float(string='Amount Due',
        compute='_compute_amount', store=True, help="Remaining amount due.")
    amount_paid = fields.Float(string='Amount Paid',
        compute='_compute_amount', store=True, help="Paid amount.")
    communication = fields.Char(string='Notes',size=128,readonly=True, states={'draft': [('readonly', False)]}, copy=True)
    reason = fields.Text(string='Cancellation Reason',size=128,readonly=True, states={'draft': [('readonly', False)]}, copy=True)
    payment_ids = fields.One2many('account.payment','advance_order_id',string='Payments',readonly=True, states={'draft': [('readonly', False)]}, copy=False)

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('advance.order') or 'New'
        result = super(AdvanceOrder, self).create(vals)
        return result

    @api.multi
    def unlink(self):
        for order in self:
            if not order.state == 'cancel' or 'draft':
                raise UserError(_('In order to delete a advance order, you must cancel it first.'))
        return super(AdvanceOrder, self).unlink()

    @api.multi
    def create_invoice(self,lines,partner_id):
        AccountInvoice=self.env['account.invoice']
        AccountInvoiceLine=self.env['account.invoice.line']
        vals = {
        'company_id':self.company_id.id,
        'partner_id':partner_id.id,
        'account_id':partner_id.property_account_receivable_id.id,
        'advance_order_id':self.id,
        }
        invoice = AccountInvoice.create(vals)
        for line in lines:
            line_vals = { 
            'invoice_id':invoice.id,
            'product_id':line.product_id.id , 
            'name':line.name,
            'quantity':line.quantity,
            'price_unit':line.price_subtotal,
            'account_id':line.product_id.property_account_income_id.id or line.product_id.categ_id.property_account_income_categ_id.id,
            }
            invoice_lines = AccountInvoiceLine.create(line_vals)
        invoice.compute_taxes()
        wf_service = netsvc.LocalService('workflow')
        wf_service.trg_validate(self.env.uid,'account.invoice',invoice.id,'invoice_open',self.env.cr) 
        #~ invoice.invoice_validate()
        return invoice

        

    def get_payment_vals(self,amount,invoice_id,partner_id,payment_type):
        
        """ Hook for extension """
        if payment_type in ['bank']:
            pay_type = 'bank'
        else:
            pay_type = 'cash'
        AccountJournal = self.env['account.journal'].search([('type','=',pay_type),('company_id','=',self.company_id.id)])
        if AccountJournal:
            journal_id= AccountJournal[0].id
        else:
            journal_id = False
        return {
            'journal_id': journal_id,
            'payment_method_id': 1, #self.payment_method_id.id,
            'payment_date': self.date_order,
            'communication': self.communication and self.communication or 'Advance Payment',
            'invoice_ids': [(4, invoice_id.id, None)],
            'payment_type': 'inbound', #self.payment_type,
            'amount': amount,
            'currency_id': 1, #self.currency_id.id,
            'partner_id': self.partner_id.id,
            'partner_type': 'customer' ,#self.partner_type,
            'advance_order_id': self.id,
            'company_id':self.company_id.id,
        }


        
    @api.multi
    def create_payment(self,amount,invoice_id,partner_id,payment_type):
        AccountPayment=self.env['account.payment']
        payment =  AccountPayment.create(self.get_payment_vals(amount,invoice_id,partner_id,payment_type))
        payment.post()
        return {'type': 'ir.actions.act_window_close'}
        
    @api.multi
    def button_approve(self):
        vals={'state': 'approved'}
        line_vals={'state': 'approved'}
        [line.write(line_vals) for line in self.advance_order_line_ids]
        if len(self.advance_order_line_ids) == 0 :
            raise UserError(_('Please add some items in advance order.'))
        else:
            invoice_id = self.create_invoice(self.advance_order_line_ids,self.partner_id)
            if self.payment_amount > 0.0:
                self.create_payment(self.payment_amount,invoice_id,self.partner_id,self.payment_type)
            vals.update({'invoice_id':invoice_id.id})
        print vals
        self.write(vals)
        return True

    @api.multi
    def button_deliver(self):
        vals={'state': 'delivered'}
        line_vals={'state': 'delivered'}
        [line.write(line_vals) for line in self.advance_order_line_ids]
        self.write(vals)
        return True

    @api.multi 
    def button_start_production(self):
        vals={'state': 'production'}
        line_vals={'state': 'production'}
        [line.write(line_vals) for line in self.advance_order_line_ids]
        self.write(vals)
        return {} 

    @api.multi 
    def button_complete(self):
        vals={'state': 'completed'}
        line_vals={'state': 'completed'}
        [line.write(line_vals) for line in self.advance_order_line_ids]
        self.write(vals)
        return {} 

    @api.multi 
    def button_dispatch(self):
        vals={'state': 'dispatched'}
        line_vals={'state': 'dispatched'}
        [line.write(line_vals) for line in self.advance_order_line_ids]
        self.write(vals)
        return {} 

    @api.multi 
    def button_cancel(self,notes):
        vals={'state': 'cancel'}
        line_vals={'state': 'cancel'}
        [line.write(line_vals) for line in self.advance_order_line_ids]
        vals.update({'reason':notes})
        [payment.cancel() for payment in self.payment_ids]
        [payment.unlink() for payment in self.payment_ids]
        self.invoice_id.action_cancel()
        self.invoice_id.write(vals)
        self.write(vals)
        return {} 
        
    #~ @api.multi 
    #~ def button_reopen(self):
        #~ vals={'state': 'draft'}
        #~ [line.write(vals) for line in self.advance_order_line_ids]
        #~ self.write(vals)
        #~ return {} 
        
    #~ @api.multi 
    #~ def button_done(self):
        #~ vals={'state': 'done'}
        #~ [line.write(vals) for line in self.advance_order_line_ids]
        #~ self.write(vals)
        #~ return {} 

class AdvanceOrderLine(models.Model):
    _name = "advance.order.line"
    _description = "Advance Order Line"
    _order = "advance_order_id,sequence,id"
    




    @api.onchange('product_id')
    def onchange_product_id(self):
        if self.product_id:
            self.name=self.product_id.name
            self.uom_id = self.product_id.uom_id.id

    @api.depends('price_unit', 'unit','quantity','product_id', 'advance_order_id.partner_id')
    def _compute_price(self):
        for line in self:
            if line.product_id:
                line.price_unit =  line.product_id.list_price 
                line.price_subtotal = line.price_unit * line.unit
            line.price_total = line.price_subtotal * line.quantity


    name = fields.Text(string='Description', required=True,readonly=False)
    origin = fields.Char(string='Source Document',
        help="Reference of the document that produced this invoice.")
    

    sequence = fields.Integer(default=10,
        help="Gives the sequence of this line when displaying the invoice.")
    advance_order_id = fields.Many2one('advance.order', string='Advance Order Reference',
        ondelete='cascade', index=True)
    partner_id = fields.Many2one('res.partner', readonly=True,string='Customer')
    uom_id = fields.Many2one('product.uom', string='Unit of Measure',
        ondelete='set null', index=True, oldname='uos_id')
    product_id = fields.Many2one('product.product', string='Product')
    unit = fields.Float(string='Unit', required=True, digits=dp.get_precision('Product Price'), default=1.0)
    price_unit = fields.Float(string='Price Unit',  compute='_compute_price')
    price_subtotal = fields.Float(string='Sub Total',
        store=True, readonly=True, compute='_compute_price')
    price_total = fields.Float(string='Total',
        store=True, readonly=True, compute='_compute_price')
    quantity = fields.Integer(string='Quantity',
        required=True, default=1)
    date_order = fields.Datetime(related='advance_order_id.date_order', string='Advance Order Order Date', readonly=True)
    #~ date_delivery = fields.Datetime(string='Delivery Date',
        #~ readonly=True, states={'draft': [('readonly', False)]}, index=True,
        #~ help="Keep empty to use the current date", copy=False)
    state = fields.Selection([
            ('draft','New'),
            ('approved', 'Approve'),
            ('production', 'In Production'),
            ('completed', 'Production Completed'),
            ('cancel', 'Cancelled'),
            ('dispatched', 'Dispatched'),
            ('delivered', 'Delivered'),
        ], string='Status', index=True, readonly=True, default='draft',
        track_visibility='onchange', copy=False)
    advance_order_line_tax_ids = fields.Many2many('account.tax',
        'advance_order_line_tax', 'advance_order_line_id', 'tax_id',
        string='Taxes', domain=[('type_tax_use','!=','none'), '|', ('active', '=', False), ('active', '=', True)], oldname='invoice_line_tax_id')

        
    @api.multi
    def button_start_production(self):
        vals ={'state': 'production'}
        advanceorder_vals ={'state': 'production'}
        flag = False
        self.write(vals)
        self.advance_order_id.write(advanceorder_vals)
        return {}
        
    @api.multi
    def button_complete(self):
        state ='completed'
        advanceorder_state ='completed'
        vals = {'state': state}
        advanceorder_vals = {'state': advanceorder_state}
        self.write(vals)
        flag = self.flag_check(True,state)
        if flag:
            self.advance_order_id.write(advanceorder_vals)
        return True

    @api.multi
    def button_deliver(self,vals):
        state='dispatched'
        vals={'state': 'delivered'}
        advanceorder_vals={'state': 'delivered'}
        flag = self.flag_check(True,state)
        self.write(vals)
        if flag:
            self.advance_order_id.write(advanceorder_vals)
        return True


    @api.multi 
    def button_dispatch(self):
        state='dispatched'
        vals={'state': 'dispatched'}
        advanceorder_vals={'state': 'dispatched'}
        flag = self.flag_check(True,state)
        self.write(vals)
        if flag:
            self.advance_order_id.write(advanceorder_vals)
        return {}

    #~ @api.multi
    #~ def button_done(self):
        #~ state='done'
        #~ vals = {'state': state}
        #~ self.write(vals)
        #~ flag = self.flag_check(True,state)
        #~ if flag:
            #~ self.advance_order_id.write(advanceorder_vals)
        #~ return True

    @api.multi
    def flag_check(self,flag,state):
        for line in self.advance_order_id.advance_order_line_ids:
             if line.state == state:
                 flag = True
             else:
                 flag = False
        return flag

    @api.multi
    def button_draft(self):
        self.write({'state': 'draft'})

    @api.multi
    def button_cancel(self):
        self.write({'state': 'cancel'})



class AdvanceOrderCancel(models.Model):
    _name = "advance.order.cancel"
    _inherit = ['mail.thread']
    _description = "Advance Order Cancel"
    
    notes = fields.Text('Reason')
    invoice_id = fields.Many2one('account.invoice',required=True)
    advance_order_id = fields.Many2one('advance.order',required=True)


    @api.model
    def default_get(self, fields):
        res = super(AdvanceOrderCancel, self).default_get(fields)
        advance_order_id = self.env.context.get('active_id')
        advance_order = self.env['advance.order'].browse(advance_order_id)
        if 'advance_order_id' in fields:
            res.update({'advance_order_id': advance_order.id})
        if 'invoice_id' in fields:
            res.update({'invoice_id': advance_order.invoice_id.id})
        return res
        
    @api.multi
    def button_confirm(self):
        self.advance_order_id.button_cancel(self.notes)
        return True

    @api.multi
    def button_cancel(self):
        return {'type': 'ir.actions.act_window_close'}
