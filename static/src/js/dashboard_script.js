odoo.define('sat.Dashboard', function (require) {
    "use strict";

    var core = require('web.core');
    var ajax = require('web.ajax');

    function fetchDataAndRender(start_date, end_date) {
        ajax.jsonRpc("/dashboard/data", 'call', {start_date: start_date, end_date: end_date}).then(function (data) {
            renderCharts(data);
        });
    }

    function renderCharts(data) {
        var ctx = document.getElementById('myChart').getContext('2d');
        var labels = Object.keys(data);
        var datasets = [];
        Object.keys(data).forEach(function(tech) {
            var dataset = {
                label: tech,
                data: Object.values(data[tech]),
                backgroundColor: generateColor(),
                borderColor: generateColor(),
                borderWidth: 1
            };
            datasets.push(dataset);
        });

        var myChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: datasets
            },
            options: {
                scales: {
                    y: {
                        beginAtZero: true
                    }
                }
            }
        });
    }

    function generateColor() {
        var r = Math.floor(Math.random() * 256);
        var g = Math.floor(Math.random() * 256);
        var b = Math.floor(Math.random() * 256);
        return `rgba(${r}, ${g}, ${b}, 0.5)`;
    }

    $(document).ready(function () {
        fetchDataAndRender(null, null); // Fetch all data initially
        // Handle date range changes
        $('#dateRangeSelector').on('change', function() {
            var dates = $(this).val().split(' to ');
            fetchDataAndRender(dates[0], dates[1]);
        });
    });
});
