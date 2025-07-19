/** @odoo-module **/
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class DashboardWidget extends Component {
    static template = "contador.DashboardWidget";
    
    setup() {
        this.orm = useService("orm");
        this.state = useState({
            stats: {},
            equipos: []
        });
        
        onWillStart(() => this.loadData());
    }
    
    async loadData() {
        const stats = await this.orm.call("contador.automatico", "obtener_estadisticas_dashboard", []);
        const equipos = await this.orm.call("contador.automatico", "obtener_lista_equipos_dashboard", []);
        
        this.state.stats = stats;
        this.state.equipos = equipos;
    }
}

DashboardWidget.template = "contador.DashboardWidget";
registry.category("actions").add("contador_dashboard_widget", DashboardWidget);