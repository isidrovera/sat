/** @odoo-module **/
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
            document.getElementById("total_maquinas").innerText = result.total_maquinas;
            document.getElementById("total_reparaciones").innerText = result.total_reparaciones;
            document.getElementById("total_alquileres").innerText = result.total_alquileres;
        });
    }
}

SatDashboard.template = "sat.DashboardTemplate";
actionRegistry.add("sat_dashboard_tag", SatDashboard);
