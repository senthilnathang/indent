# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp.osv import fields, osv
from openerp import SUPERUSER_ID, api, models
from openerp.tools.translate import _
from openerp.exceptions import UserError

class stock_picking_type(osv.osv):
    _name = _inherit = "stock.picking.type"
    _description = "The picking type determines the picking view"
    _columns = {
    'code': fields.selection([('incoming', 'Suppliers'),('indent', 'Indent'),('dump','Dump/Damage'), ('outgoing', 'Customers'), ('internal', 'Internal')], 'Type of Operation', required=True),
    }
class stock_location(osv.osv):
    _name = _inherit =  "stock.location"
    _columns = {
    'dump_location': fields.boolean('Is a Dump Location?', help='Check this box to allow using this location to put dump/expired goods.'),
    'damage_location': fields.boolean('Is a Damage Location?', help='Check this box to allow using this location to put damaged goods.'),
    }


class stock_picking(osv.osv):
    _inherit = 'stock.picking'

    def _default_location_source(self):
        # retrieve picking type from context; if none this returns an empty recordset
        picking_type_id = self._context.get('default_picking_type_id')
        picking_type = self.env['stock.picking.type'].browse(picking_type_id)
        return picking_type.default_location_src_id
        

    def _default_location_destination(self):
        # retrieve picking type from context; if none this returns an empty recordset
        picking_type_id = self._context.get('default_picking_type_id')
        picking_type = self.env['stock.picking.type'].browse(picking_type_id)
        return picking_type.default_location_dest_id

    _columns = {
        'indent_id': fields.related('move_lines', 'indent_line_id', 'order_id', string="Indent Orders",
            readonly=True, type="many2one", relation="indent.order"),
        'location_id': fields.many2one('stock.location', required=True, string="Source Location Zone",
                                      default=_default_location_source, readonly=True, states={'draft': [('readonly', False)]}),
        'location_dest_id': fields.many2one('stock.location', required=True,string="Destination Location Zone",
                                           default=_default_location_destination, readonly=False, states={'draft': [('readonly', False)]}),

    }


    def create(self, cr, user, vals, context=None):
        context = context or {}
        if ('name' not in vals) or (vals.get('name') in ('/', False)):
            ptype_id = vals.get('picking_type_id', context.get('default_picking_type_id', False))
            sequence_id = self.pool.get('stock.picking.type').browse(cr, user, ptype_id, context=context).sequence_id.id
            vals['name'] = self.pool.get('ir.sequence').next_by_id(cr, user, sequence_id, context=context)
        # As the on_change in one2many list is WIP, we will overwrite the locations on the stock moves here
        # As it is a create the format will be a list of (0, 0, dict)
        if vals.get('move_lines') and vals.get('location_id') and vals.get('location_dest_id'):
            for move in vals['move_lines']:
                if len(move) == 3:
                    move[2]['location_id'] = vals['location_id']
                    move[2]['location_dest_id'] = vals['location_dest_id']
        return super(stock_picking, self).create(cr, user, vals, context)

    def _prepare_values_extra_move(self, cr, uid, op, product, remaining_qty, context=None):
        res = super(stock_picking, self)._prepare_values_extra_move(cr, uid, op, product, remaining_qty, context=context)
        for m in op.linked_move_operation_ids:
            if m.move_id.indent_line_id and m.move_id.product_id == product:
                res['indent_line_id'] = m.move_id.indent_line_id.id
                break
        return res

    def do_new_transfer(self, cr, uid, ids, context=None):
        pack_op_obj = self.pool['stock.pack.operation']
        data_obj = self.pool['ir.model.data']
        for pick in self.browse(cr, uid, ids, context=context):
            to_delete = []
            if not pick.move_lines and not pick.pack_operation_ids:
                raise UserError(_('Please create some Initial Demand or Mark as Todo and create some Operations. '))
            # In draft or with no pack operations edited yet, ask if we can just do everything
            if pick.state == 'draft' or all([x.qty_done == 0.0 for x in pick.pack_operation_ids]):
                # If no lots when needed, raise error
                picking_type = pick.picking_type_id
                if (picking_type.use_create_lots or picking_type.use_existing_lots):
                    for pack in pick.pack_operation_ids:
                        if pack.product_id and pack.product_id.tracking != 'none':
                            raise UserError(_('Some products require lots, so you need to specify those first!'))
                if pick.backorder_id:
                    view = data_obj.xmlid_to_res_id(cr, uid, 'view_backorder_transfer')
                    wiz_id = self.pool['stock.backorder.transfer'].create(cr, uid, {'pick_id': pick.id}, context=context)
                    return {
                         'name': _('BackOrdercTransfer?'),
                         'type': 'ir.actions.act_window',
                         'view_type': 'form',
                         'view_mode': 'form',
                         'res_model': 'stock.backorder.transfer',
                         'views': [(view, 'form')],
                         'view_id': view,
                         'target': 'new',
                         'res_id': wiz_id,
                         'context': context,
                     }
                else:
                    view = data_obj.xmlid_to_res_id(cr, uid, 'stock.view_immediate_transfer')
                    wiz_id = self.pool['stock.immediate.transfer'].create(cr, uid, {'pick_id': pick.id}, context=context)
                    return {
                         'name': _('Immediate Transfer?'),
                         'type': 'ir.actions.act_window',
                         'view_type': 'form',
                         'view_mode': 'form',
                         'res_model': 'stock.immediate.transfer',
                         'views': [(view, 'form')],
                         'view_id': view,
                         'target': 'new',
                         'res_id': wiz_id,
                         'context': context,
                     }

            # Check backorder should check for other barcodes
            if self.check_backorder(cr, uid, pick, context=context):
                view = data_obj.xmlid_to_res_id(cr, uid, 'stock.view_backorder_confirmation')
                wiz_id = self.pool['stock.backorder.confirmation'].create(cr, uid, {'pick_id': pick.id}, context=context)
                return {
                         'name': _('Create Backorder?'),
                         'type': 'ir.actions.act_window',
                         'view_type': 'form',
                         'view_mode': 'form',
                         'res_model': 'stock.backorder.confirmation',
                         'views': [(view, 'form')],
                         'view_id': view,
                         'target': 'new',
                         'res_id': wiz_id,
                         'context': context,
                     }
            for operation in pick.pack_operation_ids:
                if operation.qty_done < 0:
                    raise UserError(_('No negative quantities allowed'))
                if operation.qty_done > 0:
                    pack_op_obj.write(cr, uid, operation.id, {'product_qty': operation.qty_done}, context=context)
                else:
                    to_delete.append(operation.id)
            if to_delete:
                pack_op_obj.unlink(cr, uid, to_delete, context=context)
        self.do_transfer(cr, uid, ids, context=context)
        return



class stock_move(osv.osv):
    _inherit = 'stock.move'
    _columns = {
        'indent_line_id': fields.many2one('indent.order.line',
            'Indent Order Line', ondelete='set null', select=True,
            readonly=True),
        'dumped': fields.related('location_dest_id', 'dump_location', type='boolean', relation='stock.location', string='Dump', readonly=True),

    }

    def get_price_unit(self, cr, uid, move, context=None):
        """ Returns the unit price to store on the quant """
        if move.indent_line_id:
            order = move.indent_line_id.order_id
            #if the currency of the PO is different than the company one, the price_unit on the move must be reevaluated
            #(was created at the rate of the PO confirmation, but must be valuated at the rate of stock move execution)
            if order.currency_id != move.company_id.currency_id:
                #we don't pass the move.date in the compute() for the currency rate on purpose because
                # 1) get_price_unit() is supposed to be called only through move.action_done(),
                # 2) the move hasn't yet the correct date (currently it is the expected date, after
                #    completion of action_done() it will be now() )
                price_unit = move.indent_line_id._get_stock_move_price_unit()
                move.write({'price_unit': price_unit})
                return price_unit
            return move.price_unit
        return super(stock_move, self).get_price_unit(cr, uid, move, context=context)

    def copy(self, cr, uid, id, default=None, context=None):
        default = default or {}
        context = context or {}
        if not default.get('split_from'):
            #we don't want to propagate the link to the indent order line except in case of move split
            default['indent_line_id'] = False
        return super(stock_move, self).copy(cr, uid, id, default, context)


class stock_warehouse(osv.osv):
    _inherit = 'stock.warehouse'
    _columns = {
        'buy_to_resupply': fields.boolean('Indent to resupply this warehouse',
                                          help="When products are bought, they can be delivered to this warehouse"),
        'buy_pull_id': fields.many2one('procurement.rule', 'Buy rule'),
        'wh_dump_stock_loc_id': fields.many2one('stock.location', 'Dump Location'),
        'indent_type_id': fields.many2one('stock.picking.type', 'Indent Type'),
        'dump_type_id': fields.many2one('stock.picking.type', 'Dump Type'),
    }
    _defaults = {
        'buy_to_resupply': True,
    }

    def _get_buy_pull_rule(self, cr, uid, warehouse, context=None):
        route_obj = self.pool.get('stock.location.route')
        data_obj = self.pool.get('ir.model.data')
        try:
            buy_route_id = data_obj.get_object_reference(cr, uid, 'indent', 'route_warehouse0_buy')[1]
        except:
            buy_route_id = route_obj.search(cr, uid, [('name', 'like', _('Buy'))], context=context)
            buy_route_id = buy_route_id and buy_route_id[0] or False
        if not buy_route_id:
            raise UserError(_('Can\'t find any generic Buy route.'))

        return {
            'name': self._format_routename(cr, uid, warehouse, _(' Buy'), context=context),
            'location_id': warehouse.in_type_id.default_location_dest_id.id,
            'route_id': buy_route_id,
            'action': 'buy',
            'picking_type_id': warehouse.in_type_id.id,
            'warehouse_id': warehouse.id,
            'group_propagation_option': 'none',
        }

    def create_routes(self, cr, uid, ids, warehouse, context=None):
        pull_obj = self.pool.get('procurement.rule')
        res = super(stock_warehouse, self).create_routes(cr, uid, ids, warehouse, context=context)
        if warehouse.buy_to_resupply:
            buy_pull_vals = self._get_buy_pull_rule(cr, uid, warehouse, context=context)
            buy_pull_id = pull_obj.create(cr, uid, buy_pull_vals, context=context)
            res['buy_pull_id'] = buy_pull_id
        return res


    def get_all_routes_for_wh(self, cr, uid, warehouse, context=None):
        all_routes = super(stock_warehouse, self).get_all_routes_for_wh(cr, uid, warehouse, context=context)
        if warehouse.buy_to_resupply and warehouse.buy_pull_id and warehouse.buy_pull_id.route_id:
            all_routes += [warehouse.buy_pull_id.route_id.id]
        return all_routes

    def _get_all_products_to_resupply(self, cr, uid, warehouse, context=None):
        res = super(stock_warehouse, self)._get_all_products_to_resupply(cr, uid, warehouse, context=context)
        if warehouse.buy_pull_id and warehouse.buy_pull_id.route_id:
            for product_id in res:
                for route in self.pool.get('product.product').browse(cr, uid, product_id, context=context).route_ids:
                    if route.id == warehouse.buy_pull_id.route_id.id:
                        res.remove(product_id)
                        break
        return res

    def _handle_renaming(self, cr, uid, warehouse, name, code, context=None):
        res = super(stock_warehouse, self)._handle_renaming(cr, uid, warehouse, name, code, context=context)
        pull_obj = self.pool.get('procurement.rule')
        #change the buy procurement rule name
        if warehouse.buy_pull_id:
            pull_obj.write(cr, uid, warehouse.buy_pull_id.id, {'name': warehouse.buy_pull_id.name.replace(warehouse.name, name, 1)}, context=context)
        return res

    def change_route(self, cr, uid, ids, warehouse, new_reception_step=False, new_delivery_step=False, context=None):
        res = super(stock_warehouse, self).change_route(cr, uid, ids, warehouse, new_reception_step=new_reception_step, new_delivery_step=new_delivery_step, context=context)
        if warehouse.in_type_id.default_location_dest_id != warehouse.buy_pull_id.location_id:
            self.pool.get('procurement.rule').write(cr, uid, warehouse.buy_pull_id.id, {'location_id': warehouse.in_type_id.default_location_dest_id.id}, context=context)
        return res


    def create_sequences_and_picking_types(self, cr, uid, warehouse, context=None):
        seq_obj = self.pool.get('ir.sequence')
        picking_type_obj = self.pool.get('stock.picking.type')
        #create new sequences
        in_seq_id = seq_obj.create(cr, SUPERUSER_ID, {'name': warehouse.name + _(' Sequence in'), 'prefix': warehouse.code + '/IN/', 'padding': 5}, context=context)
        indent_seq_id = seq_obj.create(cr, SUPERUSER_ID, {'name': warehouse.name + _(' Sequence indent'), 'prefix': warehouse.code + '/Indent/', 'padding': 5}, context=context)
        out_seq_id = seq_obj.create(cr, SUPERUSER_ID, {'name': warehouse.name + _(' Sequence out'), 'prefix': warehouse.code + '/OUT/', 'padding': 5}, context=context)
        pack_seq_id = seq_obj.create(cr, SUPERUSER_ID, {'name': warehouse.name + _(' Sequence packing'), 'prefix': warehouse.code + '/PACK/', 'padding': 5}, context=context)
        dump_seq_id = seq_obj.create(cr, SUPERUSER_ID, {'name': warehouse.name + _(' Sequence dump'), 'prefix': warehouse.code + '/DUMP/DAMAGE/', 'padding': 5}, context=context)
        pick_seq_id = seq_obj.create(cr, SUPERUSER_ID, {'name': warehouse.name + _(' Sequence picking'), 'prefix': warehouse.code + '/PICK/', 'padding': 5}, context=context)
        int_seq_id = seq_obj.create(cr, SUPERUSER_ID, {'name': warehouse.name + _(' Sequence internal'), 'prefix': warehouse.code + '/INT/', 'padding': 5}, context=context)

        wh_stock_loc = warehouse.lot_stock_id
        wh_input_stock_loc = warehouse.wh_input_stock_loc_id
        wh_output_stock_loc = warehouse.wh_output_stock_loc_id
        wh_pack_stock_loc = warehouse.wh_pack_stock_loc_id
        wh_dump_stock_loc = warehouse.wh_dump_stock_loc_id

        #create in, out, internal picking types for warehouse
        input_loc = wh_input_stock_loc
        if warehouse.reception_steps == 'one_step':
            input_loc = wh_stock_loc
        output_loc = wh_output_stock_loc
        if warehouse.delivery_steps == 'ship_only':
            output_loc = wh_stock_loc

        #choose the next available color for the picking types of this warehouse
        color = 0
        available_colors = [0, 3, 4, 5, 6, 7, 8, 1, 2]  # put white color first
        all_used_colors = self.pool.get('stock.picking.type').search_read(cr, uid, [('warehouse_id', '!=', False), ('color', '!=', False)], ['color'], order='color')
        #don't use sets to preserve the list order
        for x in all_used_colors:
            if x['color'] in available_colors:
                available_colors.remove(x['color'])
        if available_colors:
            color = available_colors[0]

        #order the picking types with a sequence allowing to have the following suit for each warehouse: reception, internal, pick, pack, ship. 
        max_sequence = self.pool.get('stock.picking.type').search_read(cr, uid, [], ['sequence'], order='sequence desc')
        max_sequence = max_sequence and max_sequence[0]['sequence'] or 0
        internal_active_false = (warehouse.reception_steps == 'one_step') and (warehouse.delivery_steps == 'ship_only')
        internal_active_false = internal_active_false and not self.user_has_groups(cr, uid, 'stock.group_locations')

        in_type_id = picking_type_obj.create(cr, uid, vals={
            'name': _('Receipts'),
            'warehouse_id': warehouse.id,
            'code': 'incoming',
            'use_create_lots': True,
            'use_existing_lots': False,
            'sequence_id': in_seq_id,
            'default_location_src_id': False,
            'default_location_dest_id': input_loc.id,
            'sequence': max_sequence + 1,
            'color': color}, context=context)
            
        pos_type_id = picking_type_obj.create(cr, uid, vals={
            'name': _('PoS Orders'),
            'warehouse_id': warehouse.id,
            'code': 'outgoing',
            'use_create_lots': False,
            'use_existing_lots': True,
            'sequence_id': out_seq_id,
            'return_picking_type_id': in_type_id,
            'default_location_src_id': output_loc.id,
            'default_location_dest_id': False,
            'sequence': max_sequence + 4,
            'color': color}, context=context)

        indent_type_id = picking_type_obj.create(cr, uid, vals={
            'name': _('Indents'),
            'warehouse_id': warehouse.id,
            'code': 'indent',
            'use_create_lots': True,
            'use_existing_lots': False,
            'sequence_id': in_seq_id,
            'default_location_src_id': False,
            'default_location_dest_id': input_loc.id,
            'sequence': max_sequence + 5,
            'color': color}, context=context)
        dump_type_id = picking_type_obj.create(cr, uid, vals={
            'name': _('Dump/Damage'),
            'warehouse_id': warehouse.id,
            'code': 'dump',
            'use_create_lots': False,
            'use_existing_lots': True,
            'sequence_id': out_seq_id,
            'return_picking_type_id': in_type_id,
            'default_location_src_id': input_loc.id,
            'default_location_dest_id': wh_dump_stock_loc.id,
            'sequence': max_sequence + 6,
            'color': color}, context=context)
        out_type_id = picking_type_obj.create(cr, uid, vals={
            'name': _('Delivery Orders'),
            'warehouse_id': warehouse.id,
            'code': 'outgoing',
            'use_create_lots': False,
            'use_existing_lots': True,
            'sequence_id': out_seq_id,
            'return_picking_type_id': in_type_id,
            'default_location_src_id': output_loc.id,
            'default_location_dest_id': False,
            'sequence': max_sequence + 4,
            'color': color}, context=context)
        picking_type_obj.write(cr, uid, [in_type_id], {'return_picking_type_id': out_type_id}, context=context)
        int_type_id = picking_type_obj.create(cr, uid, vals={
            'name': _('Internal Transfers'),
            'warehouse_id': warehouse.id,
            'code': 'internal',
            'use_create_lots': False,
            'use_existing_lots': True,
            'sequence_id': int_seq_id,
            'default_location_src_id': wh_stock_loc.id,
            'default_location_dest_id': wh_stock_loc.id,
            'active': not internal_active_false,
            'sequence': max_sequence + 2,
            'color': color}, context=context)
        pack_type_id = picking_type_obj.create(cr, uid, vals={
            'name': _('Pack'),
            'warehouse_id': warehouse.id,
            'code': 'internal',
            'use_create_lots': False,
            'use_existing_lots': True,
            'sequence_id': pack_seq_id,
            'default_location_src_id': wh_pack_stock_loc.id,
            'default_location_dest_id': output_loc.id,
            'active': warehouse.delivery_steps == 'pick_pack_ship',
            'sequence': max_sequence + 3,
            'color': color}, context=context)
        pick_type_id = picking_type_obj.create(cr, uid, vals={
            'name': _('Pick'),
            'warehouse_id': warehouse.id,
            'code': 'internal',
            'use_create_lots': False,
            'use_existing_lots': True,
            'sequence_id': pick_seq_id,
            'default_location_src_id': wh_stock_loc.id,
            'default_location_dest_id': output_loc.id if warehouse.delivery_steps == 'pick_ship' else wh_pack_stock_loc.id,
            'active': warehouse.delivery_steps != 'ship_only',
            'sequence': max_sequence + 2,
            'color': color}, context=context)

        #write picking types on WH
        vals = {
            'in_type_id': in_type_id,
            'indent_type_id': indent_type_id,
            'dump_type_id': dump_type_id,
            'out_type_id': out_type_id,
            'pack_type_id': pack_type_id,
            'pick_type_id': pick_type_id,
            'int_type_id': int_type_id,
        }
        super(stock_warehouse, self).write(cr, uid, warehouse.id, vals=vals, context=context)

    def write(self, cr, uid, ids, vals, context=None):
        if context is None:
            context = {}
        if isinstance(ids, (int, long)):
            ids = [ids]
        seq_obj = self.pool.get('ir.sequence')
        route_obj = self.pool.get('stock.location.route')
        context_with_inactive = context.copy()
        context_with_inactive['active_test'] = False
        for warehouse in self.browse(cr, uid, ids, context=context_with_inactive):
            #first of all, check if we need to delete and recreate route
            if vals.get('reception_steps') or vals.get('delivery_steps'):
                #activate and deactivate location according to reception and delivery option
                self.switch_location(cr, uid, warehouse.id, warehouse, vals.get('reception_steps', False), vals.get('delivery_steps', False), context=context)
                # switch between route
                self.change_route(cr, uid, ids, warehouse, vals.get('reception_steps', False), vals.get('delivery_steps', False), context=context_with_inactive)
                # Check if we need to change something to resupply warehouses and associated MTO rules
                self._check_resupply(cr, uid, warehouse, vals.get('reception_steps'), vals.get('delivery_steps'), context=context)
            if vals.get('code') or vals.get('name'):
                name = warehouse.name
                #rename sequence
                if vals.get('name'):
                    name = vals.get('name', warehouse.name)
                self._handle_renaming(cr, uid, warehouse, name, vals.get('code', warehouse.code), context=context_with_inactive)
                if warehouse.in_type_id:
                    seq_obj.write(cr, uid, warehouse.in_type_id.sequence_id.id, {'name': name + _(' Sequence in'), 'prefix': vals.get('code', warehouse.code) + '\IN\\'}, context=context)
                if warehouse.indent_type_id:
                    seq_obj.write(cr, uid, warehouse.in_type_id.sequence_id.id, {'name': name + _(' Sequence indent'), 'prefix': vals.get('code', warehouse.code) + '\Indent\\'}, context=context)
                if warehouse.dump_type_id:
                    seq_obj.write(cr, uid, warehouse.in_type_id.sequence_id.id, {'name': name + _(' Sequence dump'), 'prefix': vals.get('code', warehouse.code) + '\Dump/Damage\\'}, context=context)
                if warehouse.out_type_id:
                    seq_obj.write(cr, uid, warehouse.out_type_id.sequence_id.id, {'name': name + _(' Sequence out'), 'prefix': vals.get('code', warehouse.code) + '\OUT\\'}, context=context)
                if warehouse.pack_type_id:
                    seq_obj.write(cr, uid, warehouse.pack_type_id.sequence_id.id, {'name': name + _(' Sequence packing'), 'prefix': vals.get('code', warehouse.code) + '\PACK\\'}, context=context)
                if warehouse.pick_type_id:
                    seq_obj.write(cr, uid, warehouse.pick_type_id.sequence_id.id, {'name': name + _(' Sequence picking'), 'prefix': vals.get('code', warehouse.code) + '\PICK\\'}, context=context)
                if warehouse.int_type_id:
                    seq_obj.write(cr, uid, warehouse.int_type_id.sequence_id.id, {'name': name + _(' Sequence internal'), 'prefix': vals.get('code', warehouse.code) + '\INT\\'}, context=context)
        if vals.get('resupply_wh_ids') and not vals.get('resupply_route_ids'):
            for cmd in vals.get('resupply_wh_ids'):
                if cmd[0] == 6:
                    new_ids = set(cmd[2])
                    old_ids = set([wh.id for wh in warehouse.resupply_wh_ids])
                    to_add_wh_ids = new_ids - old_ids
                    if to_add_wh_ids:
                        supplier_warehouses = self.browse(cr, uid, list(to_add_wh_ids), context=context)
                        self._create_resupply_routes(cr, uid, warehouse, supplier_warehouses, warehouse.default_resupply_wh_id, context=context)
                    to_remove_wh_ids = old_ids - new_ids
                    if to_remove_wh_ids:
                        to_remove_route_ids = route_obj.search(cr, uid, [('supplied_wh_id', '=', warehouse.id), ('supplier_wh_id', 'in', list(to_remove_wh_ids))], context=context)
                        if to_remove_route_ids:
                            route_obj.unlink(cr, uid, to_remove_route_ids, context=context)
                else:
                    #not implemented
                    pass
        if 'default_resupply_wh_id' in vals:
            if vals.get('default_resupply_wh_id') == warehouse.id:
                raise UserError(_('The default resupply warehouse should be different than the warehouse itself!'))
            if warehouse.default_resupply_wh_id:
                #remove the existing resupplying route on the warehouse
                to_remove_route_ids = route_obj.search(cr, uid, [('supplied_wh_id', '=', warehouse.id), ('supplier_wh_id', '=', warehouse.default_resupply_wh_id.id)], context=context)
                for inter_wh_route_id in to_remove_route_ids:
                    self.write(cr, uid, [warehouse.id], {'route_ids': [(3, inter_wh_route_id)]})
            if vals.get('default_resupply_wh_id'):
                #assign the new resupplying route on all products
                to_assign_route_ids = route_obj.search(cr, uid, [('supplied_wh_id', '=', warehouse.id), ('supplier_wh_id', '=', vals.get('default_resupply_wh_id'))], context=context)
                for inter_wh_route_id in to_assign_route_ids:
                    self.write(cr, uid, [warehouse.id], {'route_ids': [(4, inter_wh_route_id)]})

        # If another partner assigned
        if vals.get('partner_id'):
            if not vals.get('company_id'):
                company = self.browse(cr, uid, ids[0], context=context).company_id
            else:
                company = self.pool['res.company'].browse(cr, uid, vals['company_id'])
            transit_loc = company.internal_transit_location_id.id
            self.pool['res.partner'].write(cr, uid, [vals['partner_id']], {'property_stock_customer': transit_loc,
                                                                            'property_stock_supplier': transit_loc}, context=context)
        return super(stock_warehouse, self).write(cr, uid, ids, vals=vals, context=context)
