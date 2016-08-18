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

class VehicleDriver(models.Model):
    _name = 'vehicle.driver'
    _description ='Driver'
    name = fields.Char('Name',size=128,required=True)
    
class VehicleModel(models.Model):
    _name = 'vehicle.model'
    _description ='Vehicle Model'
    name = fields.Char('Name',required=True)
    
class VehicleBrand(models.Model):
    _name = 'vehicle.brand'
    _description ='Vehicle Brand'
    name = fields.Char('Name',required=True)
    
class VehicleVehicle(models.Model):
    _name = 'vehicle.vehicle'
    _rec_name ='model_id'
    _description ='Vehicle'
    model_id = fields.Many2one('vehicle.model',string='Model',required=True)
    brand_id = fields.Many2one('vehicle.brand',string='Brand',required=True)
    vehicle_number = fields.Char('Vehicle Number',required=True)

 
