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
        // Llamamos al método get_dashboard_data del modelo sat.dashboard
        this.orm.call("sat.dashboard", "get_dashboard_data", []).then((result) => {
            // Renderizamos las tiles y los gráficos con los datos obtenidos
            this._render_tiles(result);
            this._render_charts(result);
        });
    }

    _render_tiles(data) {
        // Mostrar el número de registros en las tiles
        document.getElementById('total_evaluaciones').textContent = data.total_evaluaciones;
        document.getElementById('total_reparaciones').textContent = data.total_reparaciones;
        document.getElementById('total_alquileres').textContent = data.total_alquileres;
        document.getElementById('total_maquinas').textContent = data.total_maquinas;
    }

    _render_charts(data) {
        // Gráfico de barras: Evaluaciones, Reparaciones, Alquileres, Máquinas en Alquiler
        var ctx1 = document.getElementById("myBarChart").getContext("2d");
        new Chart(ctx1, {
            type: 'bar',
            data: {
                labels: ['Evaluaciones', 'Reparaciones', 'Alquileres', 'Máquinas en Alquiler'],
                datasets: [{
                    label: 'Cantidad',
                    data: [data.total_evaluaciones, data.total_reparaciones, data.total_alquileres, data.total_maquinas],
                    backgroundColor: ['#36A2EB', '#FF6384', '#FFCE56', '#4BC0C0'],
                }]
            },
        });

        // Otros gráficos aquí...
    }
}

SatDashboard.template = "sat.DashboardTemplate";
actionRegistry.add("sat_dashboard_tag", SatDashboard);
