/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const STATE_LABELS = {
    nuevo: "NUEVO",
    proceso: "PROCESO",
    en_ruta: "EN RUTA",
    en_sitio: "EN SITIO",
    en_revision: "EN REVISIÓN",
    finalizado: "FINALIZADO",
};


export class MobileTicketLayout extends Component {
    static template = "sat.MobileTicketLayout";
    static props = { ...standardFieldProps };

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");

        this.uiState = useState({
            isMobile: this._checkMobile(),
            menuOpen: false,
            accordions: {
                componentes: { open: true, manuallyToggled: false },
                accesorios: { open: true, manuallyToggled: false },
                informe: { open: false, manuallyToggled: false },
                pedidos: { open: false, manuallyToggled: false },
                ubicacion: { open: false, manuallyToggled: false },
                gps: { open: false, manuallyToggled: false },
            },
        });

        this._onResize = () => {
            this.uiState.isMobile = this._checkMobile();
        };

        onMounted(() => {
            window.addEventListener("resize", this._onResize);
            if (this.uiState.isMobile) {
                document.body.classList.add("o_mobile_ticket_active");
            }
        });

        onWillUnmount(() => {
            window.removeEventListener("resize", this._onResize);
            document.body.classList.remove("o_mobile_ticket_active");
        });
    }

    _checkMobile() {
        return window.innerWidth <= 768;
    }

    get record() {
        return this.props.record;
    }

    get data() {
        return this.record.data;
    }

    _readM2O(field) {
        const val = this.data[field];
        if (!val) return "";
        if (Array.isArray(val)) return val[1] || "";
        if (typeof val === "object") return val.display_name || "";
        return String(val);
    }

    get ticketNumber() { return this.data.name || ""; }
    get currentState() { return this.data.estado || "nuevo"; }
    get stateLabel() { return STATE_LABELS[this.currentState] || this.currentState.toUpperCase(); }
    get stateClass() { return `o_status_${this.currentState}`; }

    get clientName() { return this._readM2O("partner_id") || "Sin cliente"; }
    get clientInitials() {
        return this.clientName.split(" ").filter(w => w).slice(0, 2)
            .map(w => w[0]).join("").toUpperCase();
    }
    get clientAddress() { return this.data.equipo_direccion_completa || ""; }
    get clientLocation() {
        return [this.data.equipo_distrito, this.data.equipo_provincia, this.data.equipo_departamento]
            .filter(p => p).join(", ");
    }
    get clientReference() { return this.data.equipo_direccion_referencia || ""; }
    get hasCoordinates() { return !!this.data.equipo_tiene_coordenadas; }
    get contactName() { return this._readM2O("contacto_id_r"); }
    get reporterName() { return this.data.reporter_name || ""; }
    get reporterPhone() { return this.data.reporter_phone || ""; }
    get tipoServicio() { return this._readM2O("tipo_servicio_id"); }
    get agendaTexto() { return this.data.agenda_local || this.data.agenda || ""; }
    get responsableName() { return this._readM2O("responsable"); }
    get asistenciaName() { return this._readM2O("asistencia_id"); }

    get equipoMarca() { return this._readM2O("marca_id_r"); }
    get equipoSerie() { return this._readM2O("serie_id_r"); }
    get equipoModelo() { return this.data.product_alquiler || ""; }
    get esColor() { return this.data.tipo_id === "color"; }

    get contadorK() { return this.data.contometrok_id || 0; }
    get contadorColor() { return this.data.contometroc_id || 0; }
    get contadorScan() { return this.data.contometros_id || 0; }

    get descripcionProblema() { return this.data.description || ""; }
    get tienePhoto() { return !!this.data.problem_photo; }

    _countList(field) {
        const list = this.data[field];
        if (!list) return 0;
        if (Array.isArray(list)) return list.length;
        if (list.records) return list.records.length;
        return 0;
    }

    _countWithEstado(field) {
        const list = this.data[field];
        if (!list || !list.records) return 0;
        return list.records.filter(r => r.data.estado_id).length;
    }

    get componentesCount() { return this._countList("ticket_componente_eval_ids"); }
    get componentesEvaluados() { return this._countWithEstado("ticket_componente_eval_ids"); }
    get componentesPendientes() { return this.componentesCount - this.componentesEvaluados; }
    get componentesCompleto() { return this.componentesCount > 0 && this.componentesPendientes === 0; }

    get accesoriosCount() { return this._countList("ticket_accesorio_eval_ids"); }
    get accesoriosEvaluados() { return this._countWithEstado("ticket_accesorio_eval_ids"); }
    get accesoriosPendientes() { return this.accesoriosCount - this.accesoriosEvaluados; }
    get accesoriosCompleto() { return this.accesoriosCount > 0 && this.accesoriosPendientes === 0; }

    get pedidosCount() { return this._countList("ticket_pedido_ids"); }

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

    toggleMenu() { this.uiState.menuOpen = !this.uiState.menuOpen; }
    closeMenu() { this.uiState.menuOpen = false; }

    async callAction(actionName) {
        this.closeMenu();
        try {
            const result = await this.orm.call(
                this.record.resModel,
                actionName,
                [this.record.resId],
                {}
            );
            if (result && typeof result === "object" && result.type) {
                await this.action.doAction(result);
            }
            await this.record.load();
        } catch (err) {
            console.error("[MobileTicket] Error en acción:", actionName, err);
        }
    }

    get canCargarContadores() { return !!this.data.mostrar_boton_contadores; }
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

    get menuActions() {
        const state = this.currentState;
        const actions = [];

        if (state === "nuevo") {
            actions.push({ icon: "fa-paper-plane", label: "Asignar ticket", method: "action_asignar_ticket" });
        }
        if (state === "proceso") {
            actions.push({ icon: "fa-car", label: "🚗 En ruta", method: "action_en_ruta" });
        }
        if (["proceso", "en_ruta"].includes(state)) {
            actions.push({ icon: "fa-map-marker", label: "📍 Llegué al sitio", method: "action_en_sitio" });
        }
        if (state === "en_sitio") {
            actions.push({ icon: "fa-wrench", label: "🔧 Iniciar revisión", method: "action_en_revision" });
        }

        actions.push(
            { icon: "fa-refresh", label: "Regenerar informe", method: "action_regenerar_informe" },
            { icon: "fa-eraser", label: "Limpiar informe", method: "action_limpiar_informe" },
            { icon: "fa-check-circle", label: "Generar evaluación", method: "action_crear_evaluacion" },
            { icon: "fa-paper-plane", label: "📤 Enviar a Administración", method: "action_enviar_informe_administracion" },
        );

        return actions;
    }

    async onAbrirMapa() { await this.callAction("action_abrir_mapa_equipo"); }
    async onNavegar() { await this.callAction("action_navegar_a_equipo"); }
    callPhone(phone) { if (phone) window.location.href = `tel:${phone}`; }
}


export const mobileTicketLayoutField = {
    component: MobileTicketLayout,
    supportedTypes: ["char", "text", "boolean", "integer"],
};

registry.category("fields").add("mobile_layout", mobileTicketLayoutField);