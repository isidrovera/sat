/** @odoo-module **/

import { ListController } from "@web/views/list/list_controller";
import { listView } from "@web/views/list/list_view";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onWillUpdateProps, useState } from "@odoo/owl";

export class SatDashboard extends Component {
    static template = "sat.SatSatDashboard";
    
    setup() {
        this.orm = useService("orm");
        this.state = useState({ 
            data: {
                total_maquinas: 0,
                total_disponibles: 0,
                total_separadas: 0,
                total_problemas: 0,
                company_currency_symbol: '',
                avg_precio_compra: 0,
                stock_value_available: 0,
                ingresadas_7: 0,
                entregadas_30: 0,
            }
        });
        
        onWillStart(async () => {
            await this.loadData();
        });

        onWillUpdateProps(async (nextProps) => {
            await this.loadData(nextProps);
        });
    }
    
    async loadData(props) {
        try {
            props = props || this.props;
            
            // Obtener dominio desde el modelo si existe
            let domain = [];
            if (props.model && props.model.root) {
                domain = props.model.root.domain || [];
            } else if (props.domain) {
                domain = props.domain;
            }
            
            const result = await this.orm.call(
                "sat.sat",
                "get_sat_dashboard_values",
                [],
                { domain: domain }
            );
            
            Object.assign(this.state.data, result);
            
        } catch (error) {
            console.error("Error cargando dashboard SAT:", error);
        }
    }
}

export class SatListController extends ListController {
    setup() {
        super.setup();
    }
}

SatListController.components = {
    ...ListController.components,
    SatDashboard,
};

SatListController.template = "sat.SatListView";

export const satListView = {
    ...listView,
    Controller: SatListController,
};

registry.category("views").add("sat_tree_dashboard", satListView);