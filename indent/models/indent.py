# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import datetime
import datetime as DT
from dateutil.relativedelta import relativedelta
from openerp import api, fields, models, _, SUPERUSER_ID
#~ from openerp.addons.hsr_pos import fields as fields2
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT
from openerp.tools.translate import _
from openerp.tools.float_utils import float_is_zero, float_compare
import openerp.addons.decimal_precision as dp
from openerp.exceptions import UserError, RedirectWarning, ValidationError, AccessError




class IndentOrder(models.Model):
    _name = "indent.order"
    _inherit = ['mail.thread', 'ir.needaction_mixin']
    _description = "Indent Order"
    _order = 'date_order desc, id desc'
    @api.multi
    def _inverse_date_planned(self):
        for order in self:
            order.order_line.write({'date_planned': self.date_planned})

    @api.depends('order_line.date_planned')
    def _compute_date_planned(self):
        for order in self:
            min_date = False
            for line in order.order_line:
                if not min_date or line.date_planned < min_date:
                    min_date = line.date_planned
            if min_date:
                order.date_planned = min_date
 
    @api.model
    def _default_picking_type(self):
        type_obj = self.env['stock.picking.type']
        company_id = self.env.context.get('company_id') or self.env.user.company_id.id
        types = type_obj.search([('code', '=', 'indent'), ('warehouse_id.company_id', '=', company_id)])
        if not types:
            types = type_obj.search([('code', '=', 'internal'), ('warehouse_id', '=', False)])
        return types[:1]

    @api.model
    def _default_product_categ_type_id(self):
        prod_categ_type_obj = self.env['product.categ.type']
        types = prod_categ_type_obj.search([('name', '=', self._context.get('indent_type'))])
        if types:
            return types.id

    @api.depends('order_line.move_ids.picking_id')
    def _compute_picking(self):
        for order in self:
            pickings = self.env['stock.picking']
            for line in order.order_line:
                moves = line.move_ids.filtered(lambda r: r.state != 'cancel')
                pickings |= moves.mapped('picking_id')
            order.picking_ids = pickings
            order.picking_count = len(pickings)

    @api.one
    @api.depends('order_line.price_subtotal','order_line.product_qty','order_line.product_id','order_line.price_unit')
    def _compute_amount(self):
        self.amount_total = sum((line.price_unit * line.product_qty) for line in self.order_line)
        self.qty_total = sum(line.product_qty for line in self.order_line)


    @api.model
    def default_get(self, fields):
        lines=[]
        res = super(IndentOrder, self).default_get(fields)
        #~ asset_id = self.env.context.get('active_id')
        #~ asset = self.env['account.asset.asset'].browse(asset_id)
        if  self._context.get('indent_type'):
            prod_categ_type_obj = self.env['product.categ.type']
            types = prod_categ_type_obj.search([('name', '=', self._context.get('indent_type'))])
            res.update({'product_categ_type_id':types.id})
            #~ if 'product_categ_type_id' in fields:
            product_ids = [x.product_id  for x in types.product_lines]
            date_today = datetime.today().strftime(DEFAULT_SERVER_DATETIME_FORMAT)
            for prod in product_ids:
                line ={
                'product_id':prod.id,
                'product_categ_id': prod.categ_id.id,
                'product_uom':prod.product_tmpl_id.uom_id.id,
                'name':prod.name,
                'product_suggested_qty':self._get_suggested_qty(prod),
                'product_qty':0,
                'price_unit':prod.lst_price,
                'date_planned':date_today,
                }
                lines.append((0,0,line))
            res.update({'order_line': lines})
        return res

    READONLY_STATES = {
        'done': [('readonly', True)],
        'cancel': [('readonly', True)],
        'approved':[('readonly',True)],
        'production':[('readonly',True)],
        'produced':[('readonly',True)],
        'delivered':[('readonly',True)],
    }

    name = fields.Char('Order Reference', states=READONLY_STATES, required=True, select=True, copy=False, default='New')
    origin = fields.Char('Source Document', copy=False,\
        help="Reference of the document that generated this indent order "
             "request (e.g. a sale order or an internal procurement request)")
    partner_ref = fields.Char('Reference', states=READONLY_STATES, copy=False,\
        help="Reference of the sales order or bid sent by the vendor. "
             "It's used to do the matching when you receive the "
             "products as this reference is usually written on the "
             "delivery order sent by your vendor.")
    date_order = fields.Datetime('Order Date', required=True, states=READONLY_STATES, select=True, copy=False, default=fields.Datetime.now,\
        help="Depicts the date where the Quotation should be validated and converted into a indent order.")
    date_approve = fields.Date('Approval Date', readonly=1, select=True, copy=False)
    user_id = fields.Many2one('res.users',string='Raised By',readonly=True,default=lambda self: self.env.user)
    partner_id = fields.Many2one('res.partner', string='For',default=lambda self: self.env.user.company_id.partner_id.id,  states=READONLY_STATES, change_default=True, track_visibility='always')
    dest_address_id = fields.Many2one('res.partner', string='Drop Ship Address', states=READONLY_STATES,\
        help="Put an address if you want to deliver directly from the vendor to the customer. "\
             "Otherwise, keep empty to deliver to your own company.")
    currency_id = fields.Many2one('res.currency', 'Currency', required=True, states=READONLY_STATES,\
        default=lambda self: self.env.user.company_id.currency_id.id)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('production', 'In Production'),
        ('produced', 'Production Completed'),
        ('dispatched','Dispatched'),
        ('delivered', 'Delivered'),
        ('done', 'Done'),
        ('cancel', 'Cancelled')
        ], string='Status', readonly=True, select=True, copy=False, default='draft', track_visibility='onchange')
    order_line = fields.One2many('indent.order.line', 'order_id', string='Lines', states=READONLY_STATES, copy=True)
    notes = fields.Text('Terms and Conditions')

    picking_count = fields.Integer(string='Receptions', states=READONLY_STATES, default=0)
    picking_ids = fields.Many2many('stock.picking', states=READONLY_STATES,  compute='_compute_picking', string='Receptions', copy=False)

    date_planned = fields.Datetime(string='Scheduled Date', states=READONLY_STATES, compute='_compute_date_planned', inverse='_inverse_date_planned', required=True, select=True, oldname='minimum_planned_date')

    fiscal_position_id = fields.Many2one('account.fiscal.position', states=READONLY_STATES, string='Fiscal Position', oldname='fiscal_position')
    incoterm_id = fields.Many2one('stock.incoterms', 'Incoterm', states=READONLY_STATES, help="International Commercial Terms are a series of predefined commercial terms used in international transactions.")

    product_id = fields.Many2one('product.product', states=READONLY_STATES, related='order_line.product_id', string='Product')
    create_uid = fields.Many2one('res.users',  'Responsible',states=READONLY_STATES)
    company_id = fields.Many2one('res.company', 'Company', required=True, select=1, states=READONLY_STATES, default=lambda self: self.env.user.company_id.id)

    picking_type_id = fields.Many2one('stock.picking.type', 'Deliver To', states=READONLY_STATES,
        default=_default_picking_type,
        help="This will determine picking type of incoming shipment")
    default_location_dest_id_usage = fields.Selection(related='picking_type_id.default_location_dest_id.usage', states=READONLY_STATES, string='Destination Location Type',\
        help="Technical field used to display the Drop Ship Address", readonly=True)
    group_id = fields.Many2one('procurement.group', string="Procurement Group")
    product_categ_type_id = fields.Many2one('product.categ.type', 'Order Type',states=READONLY_STATES)#,default=_default_product_categ_type_id)
    amount_total = fields.Monetary(string='Total Amount', 
        store=True, readonly=True, compute='_compute_amount')
        
    qty_total = fields.Monetary(string='Total Qty', 
        store=True, readonly=True, compute='_compute_amount')

    driver_id = fields.Many2one('vehicle.driver', string='Driver', states=READONLY_STATES,)
    vehicle_id = fields.Many2one('vehicle.vehicle', string='Vehicle', states=READONLY_STATES,)
    brand_id = fields.Many2one(related='vehicle_id.brand_id', store=True, readonly=True, copy=False)
    model_id = fields.Many2one(related='vehicle_id.model_id', store=True, readonly=True, copy=False)
    vehicle_number = fields.Char(related='vehicle_id.vehicle_number', store=True, readonly=True, copy=False)


    @api.multi
    def button_approve(self):
        vals={'state': 'approved'}
        flag = False
        qty = [line for line in self.order_line if line.product_qty >0.0]
        if len(qty)>0:
            [line.unlink() for line in self.order_line if line.product_qty <=0.0]
        else:
            raise UserError(_('There is no quantity in single line.'))
        self.write(vals)
        return True

        
    @api.multi
    def button_production(self):
        self.write({'state': 'production'})
        return {}
        
    @api.multi
    def button_produced(self):
        self.write({'state': 'produced'})
        return {}

    @api.multi
    def button_deliver(self):
        data_obj = self.env['ir.model.data']
        view = data_obj.xmlid_to_res_id('indent.view_wizard_delivery_info')
        wiz_id = self.env['wizard.delivery.info'].create({'indent_id': self.id})
        return {
             'name': _('Delivery Details'),
             'type': 'ir.actions.act_window',
             'view_type': 'form',
             'view_mode': 'form',
             'res_model': 'wizard.delivery.info',
             'views': [(view, 'form')],
             'view_id': view,
             'target': 'new',
             'res_id': wiz_id.id,
             'context': self._context,
         }
    @api.multi
    def deliver(self,vals):
        self. _prepare_picking()
        picking = self._create_picking()
        vals.update({'state': 'delivered'})
        self.write(vals)
        return {}

    @api.multi
    def button_dispatch(self):
        self.write({'state': 'dispatched'})
        return {}

    @api.multi
    def button_done(self):
        self.write({'state': 'done'})


    @api.multi
    def button_draft(self):
        self.write({'state': 'draft'})

    @api.multi
    def button_cancel(self):
        for order in self:
            for pick in order.picking_ids:
                if pick.state == 'done':
                    raise UserError(_('Unable to cancel indent order %s as some receptions have already been done.') % (order.name))
            for pick in order.picking_ids.filtered(lambda r: r.state != 'cancel'):
                pick.action_cancel()
            if not self.env.context.get('cancel_procurement'):
                procurements = order.order_line.mapped('procurement_ids')
                procurements.filtered(lambda r: r.state not in ('cancel', 'exception') and r.rule_id.propagate).write({'state': 'cancel'})
                procurements.filtered(lambda r: r.state not in ('cancel', 'exception') and not r.rule_id.propagate).write({'state': 'exception'})
                moves = procurements.filtered(lambda r: r.rule_id.propagate).mapped('move_dest_id')
                moves.filtered(lambda r: r.state != 'cancel').action_cancel()

        self.write({'state': 'cancel'})





    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('indent.order') or 'New'
        if self._context.get('approve'):
            if 'order_line' in vals:
                new_lines = [item for item in vals['order_line'] if item[2]['product_qty'] >  0.0]
                vals.update({'order_line':new_lines})
                
        result = super(IndentOrder, self).create(vals)
        return result



    @api.multi
    def unlink(self):
        for order in self:
            if not order.state == 'cancel':
                raise UserError(_('In order to delete a indent order, you must cancel it first.'))
        return super(IndentOrder, self).unlink()


    @api.onchange('partner_id')
    def onchange_partner_id(self):
        if not self.partner_id:
            self.fiscal_position_id = False
            self.payment_term_id = False
        else:
            self.fiscal_position_id = self.env['account.fiscal.position'].get_fiscal_position(self.partner_id.id)
            self.payment_term_id = self.partner_id.property_supplier_payment_term_id.id
        return {}


    @api.multi
    def _get_suggested_qty(self,product):
        indent_order_line_obj = self.env['indent.order.line']
        qty=0
        if product:
            end = datetime.strftime((datetime.today() - DT.timedelta(days=7)),"%Y-%m-%d %H:%M:%S")
            start = datetime.strftime((datetime.today() - DT.timedelta(days=28)),"%Y-%m-%d %H:%M:%S")
            indent_order_lines = indent_order_line_obj.search([('product_id','=',product.id),('date_planned','>=',start),('date_planned','<=',end)])
            qty = int(sum(line.product_qty for line in indent_order_lines)/4)
        return qty
    
    @api.onchange('product_categ_type_id')
    def _onchange_product_categ_type_id(self):
        lines=[]
        indent_line_obj = self.env['indent.order.line']
        if self.product_categ_type_id:
            product_ids = [x.product_id  for x in self.product_categ_type_id.product_lines]
            date_today = datetime.today().strftime(DEFAULT_SERVER_DATETIME_FORMAT)
            for prod in product_ids:
                line ={
                'product_id':prod.id,
                'product_categ_id': prod.categ_id.id,
                'product_uom':prod.product_tmpl_id.uom_id.id,
                'name':prod.name,
                'product_suggested_qty':self._get_suggested_qty(prod),
                'product_qty':0,
                'price_unit':prod.lst_price,
                'date_planned':date_today,
                }
                lines.append((0,0,line))
        self.order_line=lines


    @api.multi
    def _get_destination_location(self):
        self.ensure_one()
        if self.dest_address_id:
            return self.dest_address_id.property_stock_customer.id
        return self.picking_type_id.default_location_dest_id.id

    @api.model
    def _prepare_picking(self):
        if not self.group_id:
            self.group_id = self.group_id.create({
                'name': self.name,
                'partner_id': self.partner_id.id
            })
        return {
            'picking_type_id': self.picking_type_id.id,
            'partner_id': self.partner_id.id,
            'date': self.date_order,
            'origin': self.name,
            'location_dest_id': self._get_destination_location(),
            'location_id': self.picking_type_id.default_location_src_id.id
        }

    @api.multi
    def _create_picking(self):
        for order in self:
            if any([ptype in ['product', 'consu'] for ptype in order.order_line.mapped('product_id.type')]):
                res = order._prepare_picking()
                picking = self.env['stock.picking'].create(res)
                moves = order.order_line.filtered(lambda r: r.product_id.type in ['product', 'consu'])._create_stock_moves(picking)
                move_ids = moves.action_confirm()
                moves = self.env['stock.move'].browse(move_ids)
                moves.force_assign()
        return True


    @api.multi
    def action_view_picking(self):
        '''
        This function returns an action that display existing picking orders of given indent order ids.
        When only one found, show the picking immediately.
        '''
        action = self.env.ref('stock.action_picking_tree')
        result = action.read()[0]

        #override the context to get rid of the default filtering on picking type
        result['context'] = {}
        pick_ids = sum([order.picking_ids.ids for order in self], [])
        #choose the view_mode accordingly
        if len(pick_ids) > 1:
            result['domain'] = "[('id','in',[" + ','.join(map(str, pick_ids)) + "])]"
        elif len(pick_ids) == 1:
            res = self.env.ref('stock.view_picking_form', False)
            result['views'] = [(res and res.id or False, 'form')]
            result['res_id'] = pick_ids and pick_ids[0] or False
        return result



class IndentOrderLine(models.Model):
    _name = 'indent.order.line'
    _description = 'Indent Order Line'


    @api.depends('order_id.state', 'move_ids.state')
    def _compute_qty_received(self):
        productuom = self.env['product.uom']
        for line in self:
            if line.order_id.state not in ['indent', 'done']:
                line.qty_received = 0.0
                continue
            if line.product_id.type not in ['consu', 'product']:
                line.qty_received = line.product_qty
                continue
            bom_delivered = self.sudo()._get_bom_delivered(line.sudo())
            if bom_delivered and any(bom_delivered.values()):
                total = line.product_qty
            elif bom_delivered:
                total = 0.0
            else:
                total = 0.0
                for move in line.move_ids:
                    if move.state == 'done':
                        if move.product_uom != line.product_uom:
                            total += productuom._compute_qty_obj(move.product_uom, move.product_uom_qty, line.product_uom)
                        else:
                            total += move.product_uom_qty
            line.qty_received = total

    @api.depends('product_qty',  'price_unit', 'product_id','order_id.partner_id','order_id.product_categ_type_id')
    def _compute_amount(self):
        """
        Compute the amounts of the  line.
        """
        self.price_subtotal = (self.price_unit * self.product_qty)

    @api.depends('product_qty')
    @api.multi
    def _suggested_qty(self):
        self.product_suggested_qty =10.0

    name = fields.Text(string='Description', required=True)
    product_suggested_qty = fields.Integer(string='Suggested Quantity', readonly=True,digits=dp.get_precision('Product Unit of Measure'))
    product_qty = fields.Integer(string='Quantity',digits=dp.get_precision('Product Unit of Measure'), required=True)
    date_planned = fields.Datetime(string='Scheduled Date', required=True, select=True)
    product_uom = fields.Many2one('product.uom', string='Product Unit of Measure', required=True)
    product_id = fields.Many2one('product.product', string='Product', domain=[('indent_ok', '=', True)], change_default=True, required=True)
    product_categ_id = fields.Many2one('product.category', string='Category',readonly=True)
    move_ids = fields.One2many('stock.move', 'indent_line_id', string='Reservation',  ondelete='set null', copy=False)
    order_id = fields.Many2one('indent.order', string='Order Reference', required=True,select=True, ondelete='cascade')
    account_analytic_id = fields.Many2one('account.analytic.account', readonly=True, string='Analytic Account', domain=[('account_type', '=', 'normal')])
    company_id = fields.Many2one('res.company', related='order_id.company_id', string='Company', store=True, readonly=True)
    state = fields.Selection(related='order_id.state', stored=True)
    price_unit = fields.Float('Unit Price',required=True)
    price_subtotal = fields.Float(_compute='_compute_amount',string='Price Subtotal',readonly=True,store=True)
    partner_id = fields.Many2one('res.partner', related='order_id.partner_id', string='Outlet', readonly=True, store=True)
    date_order = fields.Datetime(related='order_id.date_order', string='Order Date', readonly=True)
    procurement_ids = fields.One2many('procurement.order', 'indent_line_id', string='Associated Procurements', copy=False)


    #~ @api.multi
    #~ def create(self, vals):
        #~ return super(IndentOrderLine, self).create(vals)


    @api.multi
    def _create_stock_moves(self, picking):
        moves = self.env['stock.move']
        done = self.env['stock.move'].browse()
        for line in self:
            #~ price_unit = line._get_stock_move_price_unit()

            template = {
                'name': line.name or '',
                'product_id': line.product_id.id,
                'product_uom': line.product_uom.id,
                'date': line.order_id.date_order,
                'date_expected': line.date_planned,
                'location_id': line.order_id.picking_type_id.default_location_src_id.id,
                'location_dest_id': line.order_id._get_destination_location(),
                'picking_id': picking.id,
                'partner_id': line.order_id.dest_address_id.id,
                'move_dest_id': False,
                'state': 'draft',
                'indent_line_id': line.id,
                'company_id': line.order_id.company_id.id,
                'price_unit': line.product_id.standard_price,
                'picking_type_id': line.order_id.picking_type_id.id,
                'group_id': line.order_id.group_id.id,
                'procurement_id': False,
                'origin': line.order_id.name,
                'route_ids': line.order_id.picking_type_id.warehouse_id and [(6, 0, [x.id for x in line.order_id.picking_type_id.warehouse_id.route_ids])] or [],
                'warehouse_id':line.order_id.picking_type_id.warehouse_id.id,
            }

            # Fullfill all related procurements with this po line
            diff_quantity = line.product_qty
            for procurement in line.procurement_ids:
                procurement_qty = procurement.product_uom._compute_qty_obj(procurement.product_uom, procurement.product_qty, line.product_uom)
                tmp = template.copy()
                tmp.update({
                    'product_uom_qty': min(procurement_qty, diff_quantity),
                    'move_dest_id': procurement.move_dest_id.id,  #move destination is same as procurement destination
                    'procurement_id': procurement.id,
                    'propagate': procurement.rule_id.propagate,
                })
                done += moves.create(tmp)
                diff_quantity -= min(procurement_qty, diff_quantity)
            if float_compare(diff_quantity, 0.0, precision_rounding=line.product_uom.rounding) > 0:
                template['product_uom_qty'] = diff_quantity
                done += moves.create(template)
        return done

    @api.multi
    def unlink(self):
        for line in self:
            if line.order_id.state in ['approved', 'done']:
                raise UserError(_('Cannot delete a indent order line which is in state \'%s\'.') %(line.state,))
            for proc in line.procurement_ids:
                proc.message_post(body=_('Indent order line deleted.'))
            line.procurement_ids.write({'state': 'exception'})
        return super(IndentOrderLine, self).unlink()

    @api.model
    def _get_date_planned(self, seller, po=False):
        """Return the datetime value to use as Schedule Date (``date_planned``) for
           PO Lines that correspond to the given product.seller_ids,
           when ordered at `date_order_str`.

           :param browse_record | False product: product.product, used to
               determine delivery delay thanks to the selected seller field (if False, default delay = 0)
           :param browse_record | False po: indent.order, necessary only if
               the PO line is not yet attached to a PO.
           :rtype: datetime
           :return: desired Schedule Date for the PO line
        """
        date_order = po.date_order if po else self.order_id.date_order
        if date_order:
            return datetime.strptime(date_order, DEFAULT_SERVER_DATETIME_FORMAT) + relativedelta(days=seller.delay if seller else 0)
        else:
            return datetime.today() + relativedelta(days=seller.delay if seller else 0)

    @api.onchange('product_id')
    def onchange_product_id(self):
        result = {}
        if not self.product_id:
            return result

        # Reset date, price and quantity since _onchange_quantity will provide default values
        self.date_planned = datetime.today().strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        self.price_unit = self.product_qty = 0.0
        self.product_uom = self.product_id.uom_po_id or self.product_id.uom_id
        #~ result['domain'] = {'product_uom': [('category_id', '=', self.product_id.uom_id.category_id.id)]}

        if self.product_id:
            self.price_unit = self.product_id.lst_price
            #~ print self.product_id.lst_price,self.price_unit
        product_lang = self.product_id.with_context({
            'lang': self.partner_id.lang,
            'partner_id': self.partner_id.id,
        })
        self.name = product_lang.display_name

        fpos = self.order_id.fiscal_position_id
        if self.env.uid == SUPERUSER_ID:
            company_id = self.env.user.company_id.id

        self._suggest_quantity()
        #~ self._onchange_quantity()


    def _suggest_quantity(self):
        '''
        Suggest a minimal quantity based on the suggestion
        '''
        if self.product_id:
            end = datetime.strftime((datetime.today() - DT.timedelta(days=7)),"%Y-%m-%d %H:%M:%S")
            start = datetime.strftime((datetime.today() - DT.timedelta(days=28)),"%Y-%m-%d %H:%M:%S")
            indent_order_lines = self.search([('product_id','=',self.product_id.id),('date_planned','>=',start),('date_planned','<=',end)])
            self.product_qty = int(sum(line.product_qty for line in indent_order_lines)/4)
        else:
            self.product_qty = 0





class ProcurementOrder(models.Model):
    _inherit = 'procurement.order'

    indent_line_id = fields.Many2one('indent.order.line', string='Indent Order Line')
    indent_id = fields.Many2one(related='indent_line_id.order_id', string='Indent Order')

    @api.multi
    def propagate_cancels(self):
        result = super(ProcurementOrder, self).propagate_cancels()
        for procurement in self:
            if procurement.rule_id.action == 'buy' and procurement.indent_line_id:
                if procurement.indent_line_id.order_id.state not in ('draft', 'cancel', 'sent', 'to validate'):
                    raise UserError(
                        _('Can not cancel a procurement related to a indent order. Please cancel the indent order first.'))
            if procurement.indent_line_id:
                price_unit = 0.0
                product_qty = 0.0
                others_procs = procurement.indent_line_id.procurement_ids.filtered(lambda r: r != procurement)
                for other_proc in others_procs:
                    if other_proc.state not in ['cancel', 'draft']:
                        product_qty += other_proc.product_uom._compute_qty_obj(other_proc.product_uom, other_proc.product_qty, procurement.indent_line_id.product_uom)

                precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
                if not float_is_zero(product_qty, precision_digits=precision):
                    seller = procurement.product_id._select_seller(
                        procurement.product_id,
                        partner_id=procurement.indent_line_id.partner_id,
                        quantity=product_qty,
                        date=procurement.indent_line_id.order_id.date_order and procurement.indent_line_id.order_id.date_order[:10],
                        uom_id=procurement.product_uom)

                    price_unit = self.env['account.tax']._fix_tax_included_price(seller.price, procurement.indent_line_id.product_id.supplier_taxes_id, procurement.indent_line_id.taxes_id) if seller else 0.0
                    if price_unit and seller and procurement.indent_line_id.order_id.currency_id and seller.currency_id != procurement.indent_line_id.order_id.currency_id:
                        price_unit = seller.currency_id.compute(price_unit, procurement.indent_line_id.order_id.currency_id)

                    if seller and seller.product_uom != procurement.product_uom:
                        price_unit = self.env['product.uom']._compute_price(seller.product_uom.id, price_unit, to_uom_id=procurement.product_uom.id)

                procurement.indent_line_id.product_qty = product_qty
                procurement.indent_line_id.price_unit = price_unit

        return result

    @api.model
    def _run(self, procurement):
        if procurement.rule_id and procurement.rule_id.action == 'buy':
            return procurement.make_po()
        return super(ProcurementOrder, self)._run(procurement)

    @api.model
    def _check(self, procurement):
        if procurement.indent_line_id:
            if not procurement.move_ids:
                return False
            return all(move.state == 'done' for move in procurement.move_ids)
        return super(ProcurementOrder, self)._check(procurement)

    @api.v8
    def _get_indent_schedule_date(self):
        procurement_date_planned = datetime.strptime(self.date_planned, DEFAULT_SERVER_DATETIME_FORMAT)
        schedule_date = (procurement_date_planned - relativedelta(days=self.company_id.po_lead))
        return schedule_date

    @api.v7
    def _get_indent_schedule_date(self, procurement):
        """Return the datetime value to use as Schedule Date (``date_planned``) for the
           Indent Order Lines created to satisfy the given procurement.

           :param browse_record procurement: the procurement for which a PO will be created.
           :rtype: datetime
           :return: the desired Schedule Date for the PO lines
        """
        procurement_date_planned = datetime.strptime(procurement.date_planned, DEFAULT_SERVER_DATETIME_FORMAT)
        schedule_date = (procurement_date_planned - relativedelta(days=procurement.company_id.po_lead))
        return schedule_date

    @api.v8
    def _get_indent_order_date(self, schedule_date):
        self.ensure_one()
        seller_delay = int(self.product_id._select_seller(self.product_id).delay)
        return schedule_date - relativedelta(days=seller_delay)

    @api.v7
    def _get_indent_order_date(self, cr, uid, procurement, company, schedule_date, context=None):
        """Return the datetime value to use as Order Date (``date_order``) for the
           Indent Order created to satisfy the given procurement.

           :param browse_record procurement: the procurement for which a PO will be created.
           :param browse_report company: the company to which the new PO will belong to.
           :param datetime schedule_date: desired Scheduled Date for the Indent Order lines.
           :rtype: datetime
           :return: the desired Order Date for the PO
        """
        seller_delay = int(procurement.product_id._select_seller(procurement.product_id).delay)
        return schedule_date - relativedelta(days=seller_delay)

    @api.multi
    def _prepare_indent_order_line(self, po, supplier):
        self.ensure_one()

        seller = self.product_id._select_seller(
            self.product_id,
            partner_id=supplier.name,
            quantity=self.product_qty,
            date=po.date_order and po.date_order[:10],
            uom_id=self.product_uom)

        name = product_lang.display_name
        if product_lang.description_indent:
            name += '\n' + product_lang.description_indent

        date_planned = self.env['indent.order.line']._get_date_planned(seller, po=po).strftime(DEFAULT_SERVER_DATETIME_FORMAT)

        return {
            'name': name,
            'product_qty': self.product_qty,
            'product_id': self.product_id.id,
            'product_uom': self.product_uom.id,
            'price_unit': price_unit,
            'date_planned': date_planned,
            'taxes_id': [(6, 0, taxes_id.ids)],
            'procurement_ids': [(4, self.id)],
            'order_id': po.id,
        }

    @api.multi
    def _prepare_indent_order(self, partner):
        self.ensure_one()
        schedule_date = self._get_indent_schedule_date()
        indent_date = self._get_indent_order_date(schedule_date)
        fpos = self.env['account.fiscal.position'].get_fiscal_position(partner.id)

        gpo = self.rule_id.group_propagation_option
        group = (gpo == 'fixed' and self.rule_id.group_id.id) or \
                (gpo == 'propagate' and self.group_id.id) or False

        return {
            'partner_id': partner.id,
            'picking_type_id': self.rule_id.picking_type_id.id,
            'company_id': self.company_id.id,
            'currency_id': partner.property_indent_currency_id.id or self.env.user.company_id.currency_id.id,
            'dest_address_id': self.partner_dest_id.id,
            'origin': self.origin,
            'payment_term_id': partner.property_supplier_payment_term_id.id,
            'date_order': indent_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT),
            'fiscal_position_id': fpos,
            'group_id': group
        }

    @api.multi
    def make_io(self):
        cache = {}
        res = []
        for procurement in self:
            suppliers = procurement.product_id.seller_ids.filtered(lambda r: not r.product_id or r.product_id == procurement.product_id)
            if not suppliers:
                procurement.message_iost(body=_('No vendor associated to product %s. Please set one to fix this procurement.') % (procurement.product_id.name))
                continue
            supplier = suppliers[0]
            partner = supplier.name

            gio = procurement.rule_id.group_propagation_option
            group = (gio == 'fixed' and procurement.rule_id.group_id) or \
                    (gio == 'propagate' and procurement.group_id) or False

            domain = (
                ('partner_id', '=', partner.id),
                ('state', '=', 'draft'),
                ('picking_type_id', '=', procurement.rule_id.picking_type_id.id),
                ('company_id', '=', procurement.company_id.id),
                ('dest_address_id', '=', procurement.partner_dest_id.id))
            if group:
                domain += (('group_id', '=', group.id),)

            if domain in cache:
                io = cache[domain]
            else:
                io = self.env['indent.order'].search([dom for dom in domain])
                io = io[0] if io else False
                cache[domain] = io
            if not io:
                vals = procurement._prepare_indent_order(partner)
                io = self.env['indent.order'].create(vals)
                cache[domain] = io
            elif not io.origin or procurement.origin not in io.origin.split(', '):
                # Keep track of all procurements
                if io.origin:
                    if procurement.origin:
                        io.write({'origin': io.origin + ', ' + procurement.origin})
                    else:
                        io.write({'origin': io.origin})
                else:
                    io.write({'origin': procurement.origin})
            if io:
                res += [procurement.id]

            # Create Line
            io_line = False
            for line in io.order_line:
                if line.product_id == procurement.product_id and line.product_uom == procurement.product_uom:
                    seller = self.product_id._select_seller(
                        self.product_id,
                        partner_id=partner,
                        quantity=line.product_qty + procurement.product_qty,
                        date=io.date_order and io.date_order[:10],
                        uom_id=self.product_uom)

                    price_unit = self.env['account.tax']._fix_tax_included_price(seller.price, line.product_id.supplier_taxes_id, line.taxes_id) if seller else 0.0
                    if price_unit and seller and io.currency_id and seller.currency_id != io.currency_id:
                        price_unit = seller.currency_id.compute(price_unit, io.currency_id)

                    if seller and self.product_uom and seller.product_uom != self.product_uom:
                        price_unit = self.env['product.uom']._compute_price(seller.product_uom.id, price_unit, to_uom_id=self.product_uom.id)

                    io_line = line.write({
                        'product_qty': line.product_qty + procurement.product_qty,
                        'price_unit': price_unit,
                        'procurement_ids': [(4, procurement.id)]
                    })
                    break
            if not io_line:
                vals = procurement._prepare_indent_order_line(io, supplier)
                self.env['indent.order.line'].create(vals)
        return res








class MailComposeMessage(models.Model):
    _inherit = 'mail.compose.message'

    @api.multi
    def send_mail(self, auto_commit=False):
        if self._context.get('default_model') == 'indent.order' and self._context.get('default_res_id'):
            order = self.env['indent.order'].browse([self._context['default_res_id']])
            if order.state == 'draft':
                order.state = 'sent'
        return super(MailComposeMessage, self.with_context(mail_post_autofollow=True)).send_mail(auto_commit=auto_commit)
