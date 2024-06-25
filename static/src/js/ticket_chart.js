// sat/static/src/js/ticket_chart.js
odoo.define('sat.ticket_chart', function (require) {
    "use strict";

    var ajax = require('web.ajax');
    var core = require('web.core');
    var Widget = require('web.Widget');
    var qweb = core.qweb;

    var TicketChart = Widget.extend({
        template: 'sat.TicketChart',
        start: function () {
            var self = this;
            this._super.apply(this, arguments);
            ajax.jsonRpc('/ticket/alquiler/chart_data', 'call', {}).then(function (data) {
                var chartDom = document.getElementById('ticket_chart_container');
                var myChart = echarts.init(chartDom);
                var option = {
                    title: {
                        text: 'Tickets por Mes'
                    },
                    tooltip: {
                        trigger: 'axis'
                    },
                    xAxis: {
                        type: 'category',
                        data: data.months
                    },
                    yAxis: {
                        type: 'value'
                    },
                    series: [{
                        data: data.counts,
                        type: 'line'
                    }]
                };
                myChart.setOption(option);
            });
        },
    });

    core.action_registry.add('sat.ticket_chart_action', TicketChart);
});
