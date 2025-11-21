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
        this.action = useService("action");
        this.state = useState({ 
            data: {
                total_maquinas: 0,
                total_disponibles: 0,
                total_separadas: 0,
                total_problemas: 0,
                total_en_revision: 0,
                total_sin_revisar: 0,
                company_currency_symbol: '',
                top_asesoras: [],
                top_modelos: [],
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

    filterByState(state) {
        let domain = [];
        
        switch(state) {
            case 'disponible':
                domain = [['disponibilidad_id', '=', 'disponible']];
                break;
            case 'separada':
                domain = [['disponibilidad_id', '=', 'separada']];
                break;
            case 'con_problemas':
                domain = [['estado_ventas_id', 'in', ['con_problemas', 'de_partes']]];
                break;
            case 'en_revision':
                domain = [['estado_ventas_id', 'in', ['para_revision', 'en_revision']]];
                break;
            case 'sin_revisar':
                domain = [['estado_ventas_id', '=', 'sin_revisar']];
                break;
            case 'all':
                domain = [];
                break;
        }

        // Aplicar el filtro al modelo
        if (this.props.model && this.props.model.root) {
            this.props.model.root.domain = domain;
            this.props.model.load();
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