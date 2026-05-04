/** @odoo-module **/

import { registry } from "@web/core/registry";
import { formView } from "@web/views/form/form_view";
import { FormController } from "@web/views/form/form_controller";
import { FormRenderer } from "@web/views/form/form_renderer";
import { useService } from "@web/core/utils/hooks";
import { useState, onMounted, onWillUnmount } from "@odoo/owl";


// Etiquetas legibles para el badge de estado
const STATE_LABELS = {
    nuevo: "NUEVO",
    proceso: "PROCESO",
    en_ruta: "EN RUTA",
    en_sitio: "EN SITIO",
    en_revision: "EN REVISIÓN",
    finalizado: "FINALIZADO",
};


export class MobileTicketRenderer extends FormRenderer {
    static template = "sat.MobileTicketRenderer";

    setup() {
        super.setup();
        this.ui = useService("ui");
        this.action = useService("action");

        this.uiState = useState({
            isMobile: this._checkMobile(),
            menuOpen: false,
            // Map de acordeones: { sectionId: { open: bool, manuallyToggled: bool } }
            accordions: {
                componentes: { open: true, manuallyToggled: false },
                accesorios: { open: true, manuallyToggled: false },
                informe: { open: false, manuallyToggled: false },
                pedidos: { open: false, manuallyToggled: false },
                ubicacion: { open: false, manuallyToggled: false },
                gps: { open: false, manuallyToggled: false },
                chat: { open: false, manuallyToggled: false },
            },
        });

        // Listener de resize para detectar cambios móvil/desktop
        this._onResize = () => {
            this.uiState.isMobile = this._checkMobile();
        };

        onMounted(() => {
            window.addEventListener("resize", this._onResize);
            this._autoCollapseCompleted();
        });

        onWillUnmount(() => {
            window.removeEventListener("resize", this._onResize);
        });
    }

    _checkMobile() {
        return window.innerWidth <= 768;
    }

    // ===== GETTERS DE DATOS DEL TICKET =====

    get record() {
        return this.props.record;
    }

    get data() {
        return this.record.data;
    }

    get ticketNumber() {
        return this.data.name || "";
    }

    get currentState() {
        return this.data.estado || "nuevo";
    }

    get stateLabel() {
        return STATE_LABELS[this.currentState] || this.currentState.toUpperCase();
    }

    get stateClass() {
        return `o_status_${this.currentState}`;
    }

    // ===== DATOS DEL CLIENTE =====

    get clientName() {
        const val = this.data.partner_id;
        if (!val) return "Sin cliente";
        if (Array.isArray(val)) return val[1];
        if (typeof val === "object") return val.display_name || "";
        return String(val);
    }

    get clientInitials() {
        const name = this.clientName;
        return name.split(" ")
            .filter(w => w.length > 0)
            .slice(0, 2)
            .map(w => w[0])
            .join("")
            .toUpperCase();
    }

    get clientAddress() {
        return this.data.equipo_direccion_completa || "";
    }

    get clientLocation() {
        const parts = [
            this.data.equipo_distrito,
            this.data.equipo_provincia,
            this.data.equipo_departamento,
        ].filter(p => p);
        return parts.join(", ");
    }

    get clientReference() {
        return this.data.equipo_direccion_referencia || "";
    }

    get hasCoordinates() {
        return !!this.data.equipo_tiene_coordenadas;
    }

    get contactName() {
        const val = this.data.contacto_id_r;
        if (!val) return "";
        if (Array.isArray(val)) return val[1];
        if (typeof val === "object") return val.display_name || "";
        return String(val);
    }

    get reporterName() {
        return this.data.reporter_name || "";
    }

    get reporterPhone() {
        return this.data.reporter_phone || "";
    }

    get tipoServicio() {
        const val = this.data.tipo_servicio_id;
        if (!val) return "";
        if (Array.isArray(val)) return val[1];
        if (typeof val === "object") return val.display_name || "";
        return String(val);
    }

    get agendaTexto() {
        return this.data.agenda_local || this.data.agenda || "";
    }

    get responsableName() {
        const val = this.data.responsable;
        if (!val) return "";
        if (Array.isArray(val)) return val[1];
        if (typeof val === "object") return val.display_name || "";
        return String(val);
    }

    get asistenciaName() {
        const val = this.data.asistencia_id;
        if (!val) return "";
        if (Array.isArray(val)) return val[1];
        if (typeof val === "object") return val.display_name || "";
        return String(val);
    }

    // ===== DATOS DEL EQUIPO =====

    get equipoMarca() {
        const val = this.data.marca_id_r;
        if (!val) return "";
        if (Array.isArray(val)) return val[1];
        if (typeof val === "object") return val.display_name || "";
        return String(val);
    }

    get equipoSerie() {
        const val = this.data.serie_id_r;
        if (!val) return "";
        if (Array.isArray(val)) return val[1];
        if (typeof val === "object") return val.display_name || "";
        return String(val);
    }

    get equipoModelo() {
        return this.data.product_alquiler || "";
    }

    get equipoTipo() {
        return this.data.tipo_id || "";
    }

    get esColor() {
        return this.data.tipo_id === "color";
    }

    // ===== DATOS DEL PROBLEMA =====

    get descripcionProblema() {
        return this.data.description || "";
    }

    get tienePhoto() {
        return !!this.data.problem_photo;
    }

    // ===== ACORDEONES =====

    get componentesCount() {
        const records = this.data.ticket_componente_eval_ids || [];
        return Array.isArray(records) ? records.length : (records.records ? records.records.length : 0);
    }

    get componentesEvaluados() {
        const list = this.data.ticket_componente_eval_ids;
        if (!list || !list.records) return 0;
        return list.records.filter(r => r.data.estado_id).length;
    }

    get componentesPendientes() {
        return this.componentesCount - this.componentesEvaluados;
    }

    get componentesCompleto() {
        return this.componentesCount > 0 && this.componentesPendientes === 0;
    }

    get accesoriosCount() {
        const records = this.data.ticket_accesorio_eval_ids || [];
        return Array.isArray(records) ? records.length : (records.records ? records.records.length : 0);
    }

    get accesoriosEvaluados() {
        const list = this.data.ticket_accesorio_eval_ids;
        if (!list || !list.records) return 0;
        return list.records.filter(r => r.data.estado_id).length;
    }

    get accesoriosPendientes() {
        return this.accesoriosCount - this.accesoriosEvaluados;
    }

    get accesoriosCompleto() {
        return this.accesoriosCount > 0 && this.accesoriosPendientes === 0;
    }

    get pedidosCount() {
        const list = this.data.ticket_pedido_ids;
        if (!list || !list.records) return 0;
        return list.records.length;
    }

    // Auto-colapsar las secciones que están completas (sin override manual)
    _autoCollapseCompleted() {
        const acc = this.uiState.accordions;

        if (this.componentesCompleto && !acc.componentes.manuallyToggled) {
            acc.componentes.open = false;
        }
        if (this.accesoriosCompleto && !acc.accesorios.manuallyToggled) {
            acc.accesorios.open = false;
        }
    }

    toggleAccordion(sectionId) {
        const acc = this.uiState.accordions[sectionId];
        if (!acc) return;
        acc.open = !acc.open;
        acc.manuallyToggled = true;
    }

    accordionClass(sectionId) {
        const acc = this.uiState.accordions[sectionId];
        if (!acc) return "";

        let cls = "o_mobile_accordion";
        if (acc.open) cls += " o_accordion_open";

        if (sectionId === "componentes") {
            if (this.componentesCompleto) cls += " o_accordion_complete";
            else if (this.componentesPendientes > 0) cls += " o_accordion_pending";
        } else if (sectionId === "accesorios") {
            if (this.accesoriosCompleto) cls += " o_accordion_complete";
            else if (this.accesoriosPendientes > 0) cls += " o_accordion_pending";
        }

        return cls;
    }

    isAccordionOpen(sectionId) {
        return this.uiState.accordions[sectionId]?.open || false;
    }

    // ===== ACCIONES =====

    toggleMenu() {
        this.uiState.menuOpen = !this.uiState.menuOpen;
    }

    closeMenu() {
        this.uiState.menuOpen = false;
    }

    async callAction(actionName, options = {}) {
        this.closeMenu();
        try {
            const result = await this.record.model.orm.call(
                this.record.resModel,
                actionName,
                [this.record.resId],
                options.kwargs || {}
            );
            // Si la acción devuelve una acción Odoo, ejecutarla
            if (result && typeof result === "object" && result.type) {
                await this.action.doAction(result);
            }
            // Recargar el record para ver cambios
            await this.record.load();
        } catch (err) {
            console.error("[MobileTicket] Error al ejecutar acción:", actionName, err);
        }
    }

    callPhone(phone) {
        if (!phone) return;
        window.location.href = `tel:${phone}`;
    }

    // ===== ACCIONES PRINCIPALES (bottom bar) =====

    get canCargarContadores() {
        return !!this.data.mostrar_boton_contadores;
    }

    get canCerrarTicket() {
        return ["proceso", "en_ruta", "en_sitio", "en_revision"].includes(this.currentState);
    }

    async onCargarContadores() {
        if (!this.canCargarContadores) return;
        if (!confirm("¿Cargar los contadores desde el equipo?")) return;
        await this.callAction("action_cargar_contadores");
    }

    async onCerrarTicket() {
        if (!this.canCerrarTicket) return;
        await this.callAction("action_finalizar");
    }

    // ===== ACCIONES SECUNDARIAS (menú ⋮) =====

    get menuActions() {
        const state = this.currentState;
        const actions = [];

        if (state === "nuevo") {
            actions.push({
                icon: "fa-paper-plane",
                label: "Asignar ticket",
                method: "action_asignar_ticket",
            });
        }

        if (state === "proceso") {
            actions.push({
                icon: "fa-car",
                label: "🚗 En ruta",
                method: "action_en_ruta",
            });
        }

        if (["proceso", "en_ruta"].includes(state)) {
            actions.push({
                icon: "fa-map-marker",
                label: "📍 Llegué al sitio",
                method: "action_en_sitio",
            });
        }

        if (state === "en_sitio") {
            actions.push({
                icon: "fa-wrench",
                label: "🔧 Iniciar revisión",
                method: "action_en_revision",
            });
        }

        // Acciones siempre disponibles
        actions.push(
            { icon: "fa-refresh", label: "Regenerar informe", method: "action_regenerar_informe" },
            { icon: "fa-eraser", label: "Limpiar informe", method: "action_limpiar_informe" },
            { icon: "fa-check-circle", label: "Generar evaluación", method: "action_crear_evaluacion" },
            { icon: "fa-paper-plane", label: "📤 Enviar a Administración", method: "action_enviar_informe_administracion" },
        );

        return actions;
    }

    // ===== UBICACIÓN =====

    async onAbrirMapa() {
        await this.callAction("action_abrir_mapa_equipo");
    }

    async onNavegar() {
        await this.callAction("action_navegar_a_equipo");
    }
}


export class MobileTicketController extends FormController {
    static template = "sat.MobileTicketController";
}


export const mobileTicketFormView = {
    ...formView,
    Renderer: MobileTicketRenderer,
    Controller: MobileTicketController,
};

registry.category("views").add("mobile_ticket_form", mobileTicketFormView);