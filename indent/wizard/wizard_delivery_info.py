# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import models, fields, api, _
from openerp.tools import float_compare
from openerp.exceptions import UserError

class wizard_delivery_info(models.TransientModel):
    _name = 'wizard.delivery.info'
    _description = 'Wizard Delivery Info'

    indent_id = fields.Many2one('indent.order',string='Indent')
    driver_id = fields.Many2one('vehicle.driver',string='Driver')
    vehicle_id = fields.Many2one('vehicle.vehicle',string='Vehicle')
    brand_id = fields.Many2one(related='vehicle_id.brand_id', store=True, readonly=True, copy=False)
    model_id = fields.Many2one(related='vehicle_id.model_id', store=True, readonly=True, copy=False)
    vehicle_number = fields.Char(related='vehicle_id.vehicle_number', store=True, readonly=True, copy=False)

    @api.model
    def default_get(self, fields):
        res = {}
        active_id = self._context.get('active_id')
        if active_id:
            res = {'indent_id': active_id}
        return res

    @api.multi
    def process(self):
        self.ensure_one()
        vals={
        'driver_id':self.driver_id.id,
        'vehicle_id':self.vehicle_id.id,
        'model_id':self.model_id.id,
        'brand_id':self.brand_id.id,
        'vehicle_number':self.vehicle_number
        }
        
        self.indent_id.deliver(vals)
