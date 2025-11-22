/** @odoo-module **/

import { ListController } from "@web/views/list/list_controller";
import { listView } from "@web/views/list/list_view";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onWillUpdateProps, useState } from "@odoo/owl";

export class AlquilerDashboard extends Component {
    static template = "alquiler.AlquilerDashboard";
    
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ 
            data: {
                total_equipos: 0,
                total_sin_revisar: 0,
                total_revisada: 0,
                total_lista: 0,
                total_alquilada: 0,
                total_con_problemas: 0,
                total_partes: 0,
                total_externo: 0,
                total_vendida: 0,
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
            if (props.list && props.list.model && props.list.model.root) {
                domain = props.list.model.root.domain || [];
            }
            
            const result = await this.orm.call(
                "alquiler",
                "get_alquiler_dashboard_values",
                [],
                { domain: domain }
            );
            
            Object.assign(this.state.data, result);
            
        } catch (error) {
            console.error("Error cargando dashboard Alquiler:", error);
        }
    }

    filterByState(state) {
        console.log("Filtrando por estado:", state);
        
        let domain = [];
        
        switch(state) {
            case 'sin_revisar':
                domain = [['estado_alquiler_id', '=', 'sin_revisar']];
                break;
            case 'revisada':
                domain = [['estado_alquiler_id', '=', 'revisada']];
                break;
            case 'lista':
                domain = [['estado_alquiler_id', '=', 'lista']];
                break;
            case 'alquilada':
                domain = [['estado_alquiler_id', '=', 'alquilada']];
                break;
            case 'con_problemas':
                domain = [['estado_alquiler_id', '=', 'con_problemas']];
                break;
            case 'partes':
                domain = [['estado_alquiler_id', '=', 'partes']];
                break;
            case 'externo':
                domain = [['estado_alquiler_id', '=', 'externo']];
                break;
            case 'vendida':
                domain = [['estado_alquiler_id', '=', 'vendida']];
                break;
            case 'all':
                domain = [['estado_alquiler_id', '!=', 'vendida']];
                break;
        }

        console.log("Dominio aplicado:", domain);

        // Método 1: Intentar con action.doAction
        try {
            this.action.doAction({
                type: 'ir.actions.act_window',
                res_model: 'alquiler',
                name: 'Equipos en Alquiler',
                views: [[false, 'list'], [false, 'form']],
                domain: domain,
                context: {},
                target: 'current',
            });
        } catch (error) {
            console.error("Error al aplicar filtro con doAction:", error);
            
            // Método 2: Fallback - actualizar el modelo directamente
            try {
                if (this.props.list && this.props.list.model && this.props.list.model.root) {
                    this.props.list.model.root.domain = domain;
                    this.props.list.model.root.load();
                }
            } catch (error2) {
                console.error("Error al aplicar filtro con model.load:", error2);
            }
        }
    }
}

export class AlquilerListController extends ListController {
    setup() {
        super.setup();
    }
}

AlquilerListController.components = {
    ...ListController.components,
    AlquilerDashboard,
};

AlquilerListController.template = "alquiler.AlquilerListView";

export const alquilerListView = {
    ...listView,
    Controller: AlquilerListController,
};

registry.category("views").add("alquiler_tree_dashboard", alquilerListView);