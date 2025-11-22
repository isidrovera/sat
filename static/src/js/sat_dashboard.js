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
                total_no_disponibles: 0,
                total_sin_revisar: 0,
                total_para_revision: 0,
                total_en_revision: 0,
                total_finalizado: 0,
                total_problemas: 0,
                total_de_partes: 0,
                total_entregada: 0,
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
            
            // Obtener dominio desde el list
            let domain = [];
            if (props.list && props.list.model && props.list.model.root) {
                domain = props.list.model.root.domain || [];
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
            case 'no_disponible':
                domain = [['disponibilidad_id', '=', 'no_disponible']];
                break;
            case 'sin_revisar':
                domain = [['estado_ventas_id', '=', 'sin_revisar']];
                break;
            case 'para_revision':
                domain = [['estado_ventas_id', '=', 'para_revision']];
                break;
            case 'en_revision':
                domain = [['estado_ventas_id', '=', 'en_revision']];
                break;
            case 'finalizado':
                domain = [['estado_ventas_id', '=', 'finalizado']];
                break;
            case 'con_problemas':
                domain = [['estado_ventas_id', '=', 'con_problemas']];
                break;
            case 'de_partes':
                domain = [['estado_ventas_id', '=', 'de_partes']];
                break;
            case 'entregada':
                domain = [['estado_ventas_id', '=', 'entregada']];
                break;
            case 'all':
                domain = [];
                break;
        }

        // Aplicar el filtro usando el searchModel
        if (this.props.list && this.props.list.model) {
            this.props.list.model.root.domain = domain;
            this.props.list.model.load();
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