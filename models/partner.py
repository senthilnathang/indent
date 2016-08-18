from openerp import tools, api
from openerp import models,fields

class ResPartner(models.Model):
    _description = 'Partner'
    _inherit = "res.partner"
    outlet = fields.Boolean('Outlet')
    warehouse = fields.Boolean('Warehouse')
