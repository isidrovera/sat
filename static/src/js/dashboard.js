/**@odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component } from "@odoo/owl";

const actionRegistry = registry.category("actions");

class SatDashboard extends Component {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this._fetch_data();
    }

    _fetch_data() {
        this.orm.call("sat.dashboard", "get_dashboard_data", []).then((result) => {
            // Actualizamos los valores en los gráficos
            this._render_charts(result);
        });
    }

    _render_charts(data) {
        // Gráfico de barras
        var ctx1 = document.getElementById("myBarChart").getContext("2d");
        new Chart(ctx1, {
            type: 'bar',
            data: {
                labels: ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio'], // Ejemplo
                datasets: [{
                    label: 'Total Facturación',
                    data: data.total_facturacion_meses, // Ejemplo de datos
                    backgroundColor: 'rgba(54, 162, 235, 0.6)',
                }]
            },
        });

        // Gráfico circular
        var ctx2 = document.getElementById("myPieChart").getContext("2d");
        new Chart(ctx2, {
            type: 'pie',
            data: {
                labels: ['Costes', 'Ingresos', 'Beneficio'],
                datasets: [{
                    data: [data.total_costes, data.total_ingresos, data.total_beneficio],
                    backgroundColor: ['#FF6384', '#36A2EB', '#FFCE56'],
                }]
            },
        });
    }
}

SatDashboard.template = "sat.DashboardTemplate";
actionRegistry.add("sat_dashboard_tag", SatDashboard);
