odoo.define('hsr_pos.indentorder', function (require) {
"use strict";

var gui = require('point_of_sale.gui');
var models = require('point_of_sale.models');
var screens = require('point_of_sale.screens');
var core = require('web.core');

var QWeb = core.qweb;
var Model = require('web.DataModel');


var IndentScreenWidget = screens.ActionButtonWidget.extend({
    template: 'IndentOrderButton',

    button_click: function(){
        var self = this;

        this._super();
        var order = this.pos.get_order();
        if(!order){
            return;
        }
        var orderlines = order.get_orderlines();
        self.pay(order,orderlines);
    },

    pay: function(order,orderlines){
        var o = new Model('indent.order');
        //console.log(order.export_as_JSON());
        var indent = o.call('create_from_ui',
        [order.export_as_JSON()],
            undefined,
            {
                shadow: false,
                timeout: false
            }
            ); 
        order.remove_orderline(orderlines);
        this.gui.show_screen('products');
        //return indent;
    }

});


screens.define_action_button({
    'name': 'indentorder',
    'widget': IndentOrderButton,
});

});


