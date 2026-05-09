/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const TAG = "[MobileTicket]";

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

    static props = {
        ...standardFieldProps,
    };

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.uiState = useState({
            isMobile: this._checkMobile(),
            menuOpen: false,
            saving: false,
            actionLoading: false,
            lastActionName: null,
            retornoLoading: false,
            retornoOptions: [],

            contadoresDirty: false,
            contadorDraft: {
                k: "",
                color: "",
                scan: "",
            },

            accordions: {
                componentes: { open: true },
                accesorios: { open: true },
                informe: { open: false },
                pedidos: { open: false },
                ubicacion: { open: false },
                gps: { open: false },
            },
        });

        this._onResize = () => {
            const oldIsMobile = this.uiState.isMobile;
            const newIsMobile = this._checkMobile();

            this.uiState.isMobile = newIsMobile;

            console.log(TAG, "[resize]", {
                oldIsMobile,
                newIsMobile,
                width: window.innerWidth,
            });

            if (this.uiState.isMobile) {
                document.body.classList.add("o_mobile_ticket_active");
            } else {
                document.body.classList.remove("o_mobile_ticket_active");
                this.uiState.menuOpen = false;
            }
        };

        onMounted(() => {
            console.log(TAG, "[mounted]", {
                isMobile: this.uiState.isMobile,
                resModel: this.record?.resModel,
                resId: this.record?.resId,
                data: this.data,
                fields: this.record?.fields,
            });

            window.addEventListener("resize", this._onResize);

            if (this.uiState.isMobile) {
                document.body.classList.add("o_mobile_ticket_active");
            }

            this.loadRetornoOptions();
            this.initContadoresDraft();
        });

        onWillUnmount(() => {
            console.log(TAG, "[willUnmount]");

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
        return this.record?.data || {};
    }

    _readM2O(fieldName) {
        const value = this.data[fieldName];

        if (!value) {
            return "";
        }

        if (Array.isArray(value)) {
            return value[1] || "";
        }

        if (typeof value === "object") {
            return value.display_name || value.name || "";
        }

        return String(value);
    }

    // ============================================================
    // NOTIFICACIONES / ERRORES
    // ============================================================

    notifyInfo(message, options = {}) {
        this.notification.add(message, {
            type: "info",
            sticky: false,
            ...options,
        });
    }

    notifySuccess(message, options = {}) {
        this.notification.add(message, {
            type: "success",
            sticky: false,
            ...options,
        });
    }

    notifyWarning(message, options = {}) {
        this.notification.add(message, {
            type: "warning",
            sticky: false,
            ...options,
        });
    }

    notifyDanger(message, options = {}) {
        this.notification.add(message, {
            type: "danger",
            sticky: true,
            ...options,
        });
    }

    _extractOdooErrorMessage(error) {
        console.error(TAG, "[_extractOdooErrorMessage] raw error", error);

        const candidates = [
            error?.data?.message,
            error?.data?.debug,
            error?.message,
            error?.cause?.message,
            error?.exceptionName,
        ];

        for (const candidate of candidates) {
            if (candidate && typeof candidate === "string") {
                let message = candidate.trim();

                if (message.includes("odoo.exceptions.ValidationError:")) {
                    message = message.split("odoo.exceptions.ValidationError:").pop().trim();
                }

                if (message.includes("odoo.exceptions.UserError:")) {
                    message = message.split("odoo.exceptions.UserError:").pop().trim();
                }

                if (message.includes("ValidationError:")) {
                    message = message.split("ValidationError:").pop().trim();
                }

                if (message.includes("UserError:")) {
                    message = message.split("UserError:").pop().trim();
                }

                // Si llega traceback completo, quedarse con la última línea útil.
                const lines = message
                    .split("\n")
                    .map((line) => line.trim())
                    .filter((line) => line);

                if (lines.length > 1) {
                    message = lines[lines.length - 1];
                }

                message = message
                    .replace(/^['"]+/, "")
                    .replace(/['"]+$/, "")
                    .trim();

                if (message) {
                    return message;
                }
            }
        }

        return "No se pudo completar la operación. Revisa los datos e inténtalo nuevamente.";
    }

    // ============================================================
    // RETORNO
    // ============================================================

    get retornoField() {
        const field = this.record?.fields?.retorno_id || null;

        console.log(TAG, "[retornoField]", {
            field,
            value: this.data.retorno_id,
        });

        return field;
    }

    get retornoId() {
        const value = this.data.retorno_id;

        if (value === false || value === null || value === undefined || value === "") {
            return "";
        }

        if (Array.isArray(value)) {
            return String(value[0] || "");
        }

        if (typeof value === "object") {
            return String(value.id || value.resId || value.value || "");
        }

        return String(value);
    }

    get retornoLabel() {
        const retornoId = this.retornoId;
        const options = this.uiState.retornoOptions || [];

        const found = options.find((opt) => String(opt.value) === String(retornoId));

        if (found) {
            return found.label;
        }

        if (retornoId === "si") {
            return "Si";
        }

        if (retornoId === "no") {
            return "No";
        }

        return retornoId || "";
    }

    get retornoIsSet() {
        return !!this.retornoId;
    }

    _getRetornoFallbackOptions() {
        return [
            { value: "si", label: "Si" },
            { value: "no", label: "No" },
        ];
    }

    async loadRetornoOptions() {
        console.log(TAG, "[loadRetornoOptions] start", {
            field: this.retornoField,
            currentValue: this.data.retorno_id,
            retornoId: this.retornoId,
        });

        const field = this.retornoField;

        this.uiState.retornoLoading = true;

        try {
            if (!field) {
                this.uiState.retornoOptions = this._getRetornoFallbackOptions();

                console.warn(TAG, "[loadRetornoOptions] retorno_id no está disponible en record.fields. Usando fallback.", {
                    options: this.uiState.retornoOptions,
                    currentValue: this.data.retorno_id,
                    retornoId: this.retornoId,
                });

                return;
            }

            if (field.selection && Array.isArray(field.selection)) {
                this.uiState.retornoOptions = field.selection
                    .filter((opt) => opt)
                    .map((opt) => {
                        if (Array.isArray(opt)) {
                            return {
                                value: String(opt[0]),
                                label: opt[1] || String(opt[0]),
                            };
                        }

                        return {
                            value: String(opt.value || opt[0] || ""),
                            label: opt.label || opt[1] || opt.value || "",
                        };
                    })
                    .filter((opt) => opt.value);

                if (!this.uiState.retornoOptions.length) {
                    this.uiState.retornoOptions = this._getRetornoFallbackOptions();
                }

                console.log(TAG, "[loadRetornoOptions] selection cargada", {
                    total: this.uiState.retornoOptions.length,
                    options: this.uiState.retornoOptions,
                    retornoId: this.retornoId,
                    retornoLabel: this.retornoLabel,
                });

                return;
            }

            if (field.relation) {
                const records = await this.orm.searchRead(
                    field.relation,
                    [],
                    ["id", "name"],
                    { limit: 100 }
                );

                this.uiState.retornoOptions = (records || []).map((record) => ({
                    value: String(record.id),
                    label: record.name,
                }));

                console.log(TAG, "[loadRetornoOptions] many2one cargado", {
                    relation: field.relation,
                    total: this.uiState.retornoOptions.length,
                    options: this.uiState.retornoOptions,
                    retornoId: this.retornoId,
                    retornoLabel: this.retornoLabel,
                });

                return;
            }

            this.uiState.retornoOptions = this._getRetornoFallbackOptions();

            console.warn(TAG, "[loadRetornoOptions] retorno_id no tiene selection ni relation. Usando fallback.", {
                field,
                options: this.uiState.retornoOptions,
            });

        } catch (error) {
            console.error(TAG, "[loadRetornoOptions] error", error);

            this.uiState.retornoOptions = this._getRetornoFallbackOptions();

            this.notifyWarning("No se pudieron cargar las opciones de retorno. Se usaron opciones por defecto.");

        } finally {
            this.uiState.retornoLoading = false;

            console.log(TAG, "[loadRetornoOptions] finally", {
                retornoLoading: this.uiState.retornoLoading,
                options: this.uiState.retornoOptions,
                retornoId: this.retornoId,
                retornoLabel: this.retornoLabel,
            });
        }
    }

    async onChangeRetorno(ev) {
        const rawValue = ev?.target?.value || "";
        const value = rawValue || false;

        console.log(TAG, "[onChangeRetorno] start", {
            rawValue,
            value,
            oldValue: this.data.retorno_id,
            oldRetornoId: this.retornoId,
            field: this.retornoField,
        });

        if (!value) {
            this.notifyWarning("Selecciona si el ticket requiere retorno.");
            return;
        }

        const ok = await this.saveMobileValues({
            retorno_id: value,
        }, {
            successMessage: "Retorno guardado correctamente.",
            errorPrefix: "No se pudo guardar el retorno.",
        });

        console.log(TAG, "[onChangeRetorno] done", {
            ok,
            value,
            newValue: this.data.retorno_id,
            newRetornoId: this.retornoId,
            retornoLabel: this.retornoLabel,
        });
    }

    // ============================================================
    // GETTERS BASE
    // ============================================================

    get ticketNumber() {
        return this.data.name || "";
    }

    get currentState() {
        return this.data.estado || "nuevo";
    }

    get stateLabel() {
        return STATE_LABELS[this.currentState] || String(this.currentState || "").toUpperCase();
    }

    get stateClass() {
        return `o_status_${this.currentState}`;
    }

    get clientName() {
        return this._readM2O("partner_id") || "Sin cliente";
    }

    get clientInitials() {
        return this.clientName
            .split(" ")
            .filter((word) => word)
            .slice(0, 2)
            .map((word) => word[0])
            .join("")
            .toUpperCase();
    }

    get clientAddress() {
        return this.data.equipo_direccion_completa || "";
    }

    get clientLocation() {
        return [
            this.data.equipo_distrito,
            this.data.equipo_provincia,
            this.data.equipo_departamento,
        ]
            .filter((part) => part)
            .join(", ");
    }

    get clientReference() {
        return this.data.equipo_direccion_referencia || "";
    }

    get hasCoordinates() {
        return !!this.data.equipo_tiene_coordenadas;
    }

    get contactName() {
        return this._readM2O("contacto_id_r");
    }

    get reporterName() {
        return this.data.reporter_name || "";
    }

    get reporterPhone() {
        return this.data.reporter_phone || "";
    }

    get tipoServicio() {
        return this._readM2O("tipo_servicio_id");
    }

    get agendaTexto() {
        return this.data.agenda_local || this.data.agenda || "";
    }

    get responsableName() {
        return this._readM2O("responsable");
    }

    get asistenciaName() {
        return this._readM2O("asistencia_id");
    }

    get equipoMarca() {
        return this._readM2O("marca_id_r");
    }

    get equipoSerie() {
        return this._readM2O("serie_id_r");
    }

    get equipoModelo() {
        return this.data.product_alquiler || "";
    }

    get esColor() {
        return this.data.tipo_id === "color";
    }

    get contadorK() {
        return this.data.contometrok_id || 0;
    }

    get contadorColor() {
        return this.data.contometroc_id || 0;
    }

    get contadorScan() {
        return this.data.contometros_id || 0;
    }

    get descripcionProblema() {
        return this.data.description || "";
    }

    get tienePhoto() {
        return !!this.data.problem_photo;
    }

    get informeHtml() {
        return this.data.informe_id || "";
    }

    _countList(fieldName) {
        const list = this.data[fieldName];

        if (!list) {
            return 0;
        }

        if (Array.isArray(list)) {
            return list.length;
        }

        if (list.records) {
            return list.records.length;
        }

        return 0;
    }

    _countWithEstado(fieldName) {
        const list = this.data[fieldName];

        if (!list || !list.records) {
            return 0;
        }

        return list.records.filter((item) => !!item.data.estado_id).length;
    }

    get componentesCount() {
        return this._countList("ticket_componente_eval_ids");
    }

    get componentesEvaluados() {
        return this._countWithEstado("ticket_componente_eval_ids");
    }

    get componentesPendientes() {
        return Math.max(this.componentesCount - this.componentesEvaluados, 0);
    }

    get componentesCompleto() {
        return this.componentesCount > 0 && this.componentesPendientes === 0;
    }

    get accesoriosCount() {
        return this._countList("ticket_accesorio_eval_ids");
    }

    get accesoriosEvaluados() {
        return this._countWithEstado("ticket_accesorio_eval_ids");
    }

    get accesoriosPendientes() {
        return Math.max(this.accesoriosCount - this.accesoriosEvaluados, 0);
    }

    get accesoriosCompleto() {
        return this.accesoriosCount > 0 && this.accesoriosPendientes === 0;
    }

    get pedidosCount() {
        return this._countList("ticket_pedido_ids");
    }

    get canCargarContadores() {
        return !!this.data.mostrar_boton_contadores;
    }

    get canCerrarTicket() {
        return ["proceso", "en_ruta", "en_sitio", "en_revision"].includes(this.currentState);
    }

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

        actions.push(
            {
                icon: "fa-refresh",
                label: "Regenerar informe",
                method: "action_regenerar_informe",
            },
            {
                icon: "fa-eraser",
                label: "Limpiar informe",
                method: "action_limpiar_informe",
            },
            {
                icon: "fa-check-circle",
                label: "Generar evaluación",
                method: "action_crear_evaluacion",
            },
            {
                icon: "fa-paper-plane",
                label: "📤 Enviar a Administración",
                method: "action_enviar_informe_administracion",
            }
        );

        return actions;
    }

    // ============================================================
    // ACCORDIONS / UI
    // ============================================================

    accordionClass(sectionId) {
        const accordion = this.uiState.accordions[sectionId];

        if (!accordion) {
            return "o_mobile_accordion";
        }

        let className = "o_mobile_accordion";

        if (accordion.open) {
            className += " o_accordion_open";
        }

        if (sectionId === "componentes") {
            if (this.componentesCompleto) {
                className += " o_accordion_complete";
            } else if (this.componentesPendientes > 0) {
                className += " o_accordion_pending";
            }
        }

        if (sectionId === "accesorios") {
            if (this.accesoriosCompleto) {
                className += " o_accordion_complete";
            } else if (this.accesoriosPendientes > 0) {
                className += " o_accordion_pending";
            }
        }

        return className;
    }

    isAccordionOpen(sectionId) {
        return !!this.uiState.accordions[sectionId]?.open;
    }

    toggleAccordion(sectionId) {
        const accordion = this.uiState.accordions[sectionId];

        console.log(TAG, "[toggleAccordion]", {
            sectionId,
            exists: !!accordion,
            before: accordion?.open,
        });

        if (!accordion) {
            return;
        }

        accordion.open = !accordion.open;

        console.log(TAG, "[toggleAccordion] after", {
            sectionId,
            after: accordion.open,
        });
    }

    toggleComponentes() {
        this.toggleAccordion("componentes");
    }

    toggleAccesorios() {
        this.toggleAccordion("accesorios");
    }

    toggleInforme() {
        this.toggleAccordion("informe");
    }

    toggleMenu() {
        this.uiState.menuOpen = !this.uiState.menuOpen;

        console.log(TAG, "[toggleMenu]", {
            menuOpen: this.uiState.menuOpen,
        });
    }

    closeMenu() {
        this.uiState.menuOpen = false;
    }

    // ============================================================
    // RECARGA / GUARDADO
    // ============================================================

    async reloadRecord() {
        console.log(TAG, "[reloadRecord] start", {
            hasLoad: !!this.record?.load,
            resModel: this.record?.resModel,
            resId: this.record?.resId,
        });

        if (this.record?.load) {
            await this.record.load();
        }

        console.log(TAG, "[reloadRecord] done", {
            data: this.data,
        });
    }

    async saveMobileValues(values, options = {}) {
        const successMessage = options.successMessage || "Cambios guardados correctamente.";
        const errorPrefix = options.errorPrefix || "No se pudo guardar el cambio.";

        console.log(TAG, "[saveMobileValues] start", {
            values,
            options,
            resModel: this.record?.resModel,
            resId: this.record?.resId,
            saving: this.uiState.saving,
        });

        if (!this.record?.resModel || !this.record?.resId) {
            console.warn(TAG, "[saveMobileValues] no resModel/resId");

            this.notifyDanger("No se pudo guardar: el ticket no tiene modelo o ID válido.");

            return false;
        }

        if (this.uiState.saving) {
            console.warn(TAG, "[saveMobileValues] already saving");

            this.notifyWarning("Espera un momento, ya se está guardando otro cambio.");

            return false;
        }

        this.uiState.saving = true;

        try {
            await this.orm.write(this.record.resModel, [this.record.resId], values);

            console.log(TAG, "[saveMobileValues] write OK");

            await this.reloadRecord();

            this.notifySuccess(successMessage);

            return true;

        } catch (error) {
            console.error(TAG, "[saveMobileValues] error", error);

            const serverMessage = this._extractOdooErrorMessage(error);
            const finalMessage = serverMessage
                ? `${errorPrefix}\n\n${serverMessage}`
                : errorPrefix;

            console.warn(TAG, "[saveMobileValues] mensaje final", {
                finalMessage,
                serverMessage,
                values,
            });

            this.notifyDanger(finalMessage, {
                sticky: true,
            });

            try {
                await this.reloadRecord();
                this.initContadoresDraft();
            } catch (reloadError) {
                console.error(TAG, "[saveMobileValues] error recargando luego de fallo", reloadError);
            }

            return false;

        } finally {
            this.uiState.saving = false;

            console.log(TAG, "[saveMobileValues] finally", {
                saving: this.uiState.saving,
            });
        }
    }

    async onMobileBack() {
        console.log(TAG, "[onMobileBack] start", {
            saving: this.uiState.saving,
            actionLoading: this.uiState.actionLoading,
            lastActionName: this.uiState.lastActionName,
            contadoresDirty: this.uiState.contadoresDirty,
        });

        if (this.uiState.saving || this.uiState.actionLoading) {
            this.notifyWarning("Espera un momento, se está guardando o ejecutando una acción.");

            console.warn(TAG, "[onMobileBack] bloqueado por proceso activo");

            return;
        }

        if (this.uiState.contadoresDirty) {
            if (!confirm("Hay contadores pendientes por guardar. ¿Deseas salir sin guardar?")) {
                console.log(TAG, "[onMobileBack] cancelado por contadores pendientes");
                return;
            }
        }

        try {
            window.history.back();

            console.log(TAG, "[onMobileBack] history.back ejecutado");

        } catch (error) {
            console.error(TAG, "[onMobileBack] error", error);

            this.notifyDanger("No se pudo volver atrás.");
        }
    }

    // ============================================================
    // CONTADORES MÓVIL
    // ============================================================

    initContadoresDraft() {
        console.log(TAG, "[initContadoresDraft] start", {
            contometrok_id: this.data.contometrok_id,
            contometroc_id: this.data.contometroc_id,
            contometros_id: this.data.contometros_id,
            dirtyBefore: this.uiState.contadoresDirty,
        });

        this.uiState.contadorDraft.k = String(this.data.contometrok_id || "");
        this.uiState.contadorDraft.color = String(this.data.contometroc_id || "");
        this.uiState.contadorDraft.scan = String(this.data.contometros_id || "");
        this.uiState.contadoresDirty = false;

        console.log(TAG, "[initContadoresDraft] done", {
            draft: this.uiState.contadorDraft,
            dirty: this.uiState.contadoresDirty,
        });
    }

    _cleanCounterInput(value) {
        return String(value || "")
            .trim()
            .replace(/,/g, "")
            .replace(/\s/g, "");
    }

    _isValidCounterNumber(value, { allowEmpty = false, allowZero = false } = {}) {
        const cleaned = this._cleanCounterInput(value);

        if (!cleaned) {
            return !!allowEmpty;
        }

        if (!/^\d+$/.test(cleaned)) {
            return false;
        }

        const numberValue = Number(cleaned);

        if (!Number.isFinite(numberValue)) {
            return false;
        }

        if (!allowZero && numberValue <= 0) {
            return false;
        }

        if (allowZero && numberValue < 0) {
            return false;
        }

        return true;
    }

    _validateCounterDraft() {
        const k = this._cleanCounterInput(this.uiState.contadorDraft.k);
        const color = this._cleanCounterInput(this.uiState.contadorDraft.color);
        const scan = this._cleanCounterInput(this.uiState.contadorDraft.scan);

        console.log(TAG, "[_validateCounterDraft]", {
            k,
            color,
            scan,
            esColor: this.esColor,
        });

        if (!k) {
            return {
                ok: false,
                message: "Ingrese el contador K antes de guardar.",
                field: "k",
            };
        }

        if (!this._isValidCounterNumber(k, { allowEmpty: false, allowZero: false })) {
            return {
                ok: false,
                message: "El contador K debe ser un número entero mayor a 0.",
                field: "k",
            };
        }

        if (this.esColor && !color) {
            return {
                ok: false,
                message: "Ingrese el contador Color antes de guardar.",
                field: "color",
            };
        }

        if (this.esColor && !this._isValidCounterNumber(color, { allowEmpty: false, allowZero: false })) {
            return {
                ok: false,
                message: "El contador Color debe ser un número entero mayor a 0.",
                field: "color",
            };
        }

        if (scan && !this._isValidCounterNumber(scan, { allowEmpty: true, allowZero: true })) {
            return {
                ok: false,
                message: "El contador Scan debe ser un número entero válido.",
                field: "scan",
            };
        }

        return {
            ok: true,
            k,
            color,
            scan,
        };
    }

    onInputContadorK(ev) {
        const value = this._cleanCounterInput(ev.target.value);

        console.log(TAG, "[onInputContadorK]", {
            raw: ev.target.value,
            value,
            previous: this.uiState.contadorDraft.k,
        });

        this.uiState.contadorDraft.k = value;
        this.uiState.contadoresDirty = true;
    }

    onInputContadorColor(ev) {
        const value = this._cleanCounterInput(ev.target.value);

        console.log(TAG, "[onInputContadorColor]", {
            raw: ev.target.value,
            value,
            previous: this.uiState.contadorDraft.color,
        });

        this.uiState.contadorDraft.color = value;
        this.uiState.contadoresDirty = true;
    }

    onInputContadorScan(ev) {
        const value = this._cleanCounterInput(ev.target.value);

        console.log(TAG, "[onInputContadorScan]", {
            raw: ev.target.value,
            value,
            previous: this.uiState.contadorDraft.scan,
        });

        this.uiState.contadorDraft.scan = value;
        this.uiState.contadoresDirty = true;
    }

    async onGuardarContadores() {
        console.log(TAG, "[onGuardarContadores] start", {
            draft: this.uiState.contadorDraft,
            esColor: this.esColor,
            currentState: this.currentState,
            currentData: {
                contometrok_id: this.data.contometrok_id,
                contometroc_id: this.data.contometroc_id,
                contometros_id: this.data.contometros_id,
            },
        });

        if (this.currentState === "finalizado") {
            this.notifyWarning("No se pueden modificar contadores en un ticket finalizado.");
            return;
        }

        if (this.uiState.saving) {
            this.notifyWarning("Espera un momento, ya se está guardando.");
            return;
        }

        const validation = this._validateCounterDraft();

        if (!validation.ok) {
            console.warn(TAG, "[onGuardarContadores] validación local falló", validation);

            this.notifyWarning(validation.message, {
                sticky: false,
            });

            return;
        }

        const values = {
            contometrok_id: validation.k,
            contometros_id: validation.scan || false,
        };

        if (this.esColor) {
            values.contometroc_id = validation.color;
        }

        console.log(TAG, "[onGuardarContadores] values", values);

        const ok = await this.saveMobileValues(values, {
            successMessage: "Contadores guardados correctamente.",
            errorPrefix: "No se pudieron guardar los contadores.",
        });

        console.log(TAG, "[onGuardarContadores] save result", {
            ok,
            values,
        });

        if (ok) {
            this.initContadoresDraft();
        } else {
            console.warn(TAG, "[onGuardarContadores] no se guardó por validación o error del servidor", {
                values,
            });
        }
    }

    // ============================================================
    // OTROS CAMPOS
    // ============================================================

    async onChangeDescription(ev) {
        const value = ev.target.value || "";

        console.log(TAG, "[onChangeDescription]", value);

        const ok = await this.saveMobileValues({
            description: value,
        }, {
            successMessage: "Problema reportado guardado correctamente.",
            errorPrefix: "No se pudo guardar el problema reportado.",
        });

        console.log(TAG, "[onChangeDescription] result", { ok });
    }

    async onChangeInforme(ev) {
        const value = ev.target.value || "";

        console.log(TAG, "[onChangeInforme]", value);

        const ok = await this.saveMobileValues({
            informe_id: value,
        }, {
            successMessage: "Informe técnico guardado correctamente.",
            errorPrefix: "No se pudo guardar el informe técnico.",
        });

        console.log(TAG, "[onChangeInforme] result", { ok });
    }

    // ============================================================
    // ACCIONES
    // ============================================================

    normalizeAction(action, actionName = "") {
        console.log(TAG, "[normalizeAction] input", {
            actionName,
            action,
        });

        if (!action || typeof action !== "object") {
            console.log(TAG, "[normalizeAction] action vacía o no objeto", {
                actionName,
                action,
            });

            return action;
        }

        if (action.type === "ir.actions.act_window") {
            const viewMode = action.view_mode || "form";

            if (!action.views) {
                const firstViewMode = viewMode.split(",")[0] || "form";
                let viewId = false;

                if (Array.isArray(action.view_id)) {
                    viewId = action.view_id[0] || false;
                } else if (typeof action.view_id === "number") {
                    viewId = action.view_id;
                }

                action.views = [[viewId, firstViewMode]];

                console.warn(TAG, "[normalizeAction] action.views no venía definido. Se agregó.", {
                    actionName,
                    viewMode,
                    viewId,
                    views: action.views,
                });
            }

            if (!action.view_mode) {
                action.view_mode = action.views.map((view) => view[1]).join(",");

                console.warn(TAG, "[normalizeAction] action.view_mode no venía definido. Se agregó.", {
                    actionName,
                    view_mode: action.view_mode,
                });
            }

            if (!action.target) {
                action.target = "current";

                console.warn(TAG, "[normalizeAction] action.target no venía definido. Se agregó current.", {
                    actionName,
                });
            }
        }

        console.log(TAG, "[normalizeAction] output", {
            actionName,
            action,
        });

        return action;
    }

    async callAction(actionName, kwargs = {}, options = {}) {
        this.closeMenu();

        console.log(TAG, "[callAction] start", {
            actionName,
            kwargs,
            options,
            resModel: this.record?.resModel,
            resId: this.record?.resId,
            currentState: this.currentState,
            retornoId: this.retornoId,
            contadoresDirty: this.uiState.contadoresDirty,
            data: this.data,
        });

        if (!this.record?.resModel || !this.record?.resId) {
            console.warn(TAG, "[callAction] no resModel/resId", {
                actionName,
                record: this.record,
            });

            this.notifyWarning("No se pudo ejecutar la acción: el ticket no tiene ID.");

            return false;
        }

        if (this.uiState.actionLoading) {
            console.warn(TAG, "[callAction] acción bloqueada porque otra está en ejecución", {
                actionName,
                lastActionName: this.uiState.lastActionName,
            });

            this.notifyWarning("Espera un momento, ya se está ejecutando otra acción.");

            return false;
        }

        this.uiState.actionLoading = true;
        this.uiState.lastActionName = actionName;

        let result = null;
        let normalizedAction = null;

        try {
            console.log(TAG, "[callAction] orm.call before", {
                model: this.record.resModel,
                method: actionName,
                args: [[this.record.resId]],
                kwargs,
            });

            result = await this.orm.call(
                this.record.resModel,
                actionName,
                [[this.record.resId]],
                kwargs
            );

            console.log(TAG, "[callAction] orm.call result", {
                actionName,
                result,
            });

            if (result && typeof result === "object" && result.type) {
                normalizedAction = this.normalizeAction(result, actionName);

                console.log(TAG, "[callAction] doAction before", {
                    actionName,
                    normalizedAction,
                });

                await this.action.doAction(normalizedAction);

                console.log(TAG, "[callAction] doAction success", {
                    actionName,
                    normalizedAction,
                });
            } else {
                console.log(TAG, "[callAction] método sin acción retornada", {
                    actionName,
                    result,
                });
            }

            if (!(normalizedAction && normalizedAction.type === "ir.actions.act_window" && normalizedAction.target === "new")) {
                await this.reloadRecord();
                this.initContadoresDraft();
            } else {
                console.log(TAG, "[callAction] no reload porque se abrió modal/wizard", {
                    actionName,
                    normalizedAction,
                });
            }

            if (options.successMessage) {
                this.notifySuccess(options.successMessage);
            }

            return true;

        } catch (error) {
            console.error(TAG, "[callAction] error", {
                actionName,
                error,
            });

            const serverMessage = this._extractOdooErrorMessage(error);
            const errorPrefix = options.errorPrefix || "No se pudo ejecutar la acción.";
            const finalMessage = serverMessage
                ? `${errorPrefix}\n\n${serverMessage}`
                : errorPrefix;

            this.notifyDanger(finalMessage, {
                sticky: true,
            });

            return false;

        } finally {
            this.uiState.actionLoading = false;
            this.uiState.lastActionName = null;

            console.log(TAG, "[callAction] finally", {
                actionName,
                actionLoading: this.uiState.actionLoading,
            });
        }
    }

    async onMenuAction(actionItem) {
        console.log(TAG, "[onMenuAction]", {
            actionItem,
        });

        if (!actionItem || !actionItem.method) {
            console.warn(TAG, "[onMenuAction] actionItem inválido", {
                actionItem,
            });

            this.notifyWarning("La acción seleccionada no es válida.");

            return;
        }

        if (this.uiState.contadoresDirty) {
            this.notifyWarning("Guarda los contadores antes de ejecutar otra acción.");
            return;
        }

        await this.callAction(actionItem.method, {}, {
            errorPrefix: `No se pudo ejecutar: ${actionItem.label || actionItem.method}.`,
        });
    }

    async onCargarContadores() {
        console.log(TAG, "[onCargarContadores] start", {
            canCargarContadores: this.canCargarContadores,
            contadoresDirty: this.uiState.contadoresDirty,
        });

        if (this.uiState.contadoresDirty) {
            this.notifyWarning("Tienes contadores escritos pendientes por guardar. Guárdalos o recarga antes de cargar contadores desde el equipo.");
            return;
        }

        if (!this.canCargarContadores) {
            console.warn(TAG, "[onCargarContadores] no permitido");

            this.notifyWarning("No hay contadores disponibles para cargar desde el equipo en este momento.");

            return;
        }

        if (!confirm("¿Cargar los contadores desde el equipo?")) {
            console.log(TAG, "[onCargarContadores] cancelado por usuario");
            return;
        }

        const ok = await this.callAction("action_cargar_contadores", {}, {
            successMessage: "Contadores cargados desde el equipo.",
            errorPrefix: "No se pudieron cargar los contadores desde el equipo.",
        });

        console.log(TAG, "[onCargarContadores] result", { ok });
    }

    async onCerrarTicket() {
        console.log(TAG, "[onCerrarTicket] start", {
            canCerrarTicket: this.canCerrarTicket,
            currentState: this.currentState,
            retornoId: this.retornoId,
            contadoresDirty: this.uiState.contadoresDirty,
            resId: this.record?.resId,
        });

        if (!this.canCerrarTicket) {
            console.warn(TAG, "[onCerrarTicket] no permitido por estado", {
                currentState: this.currentState,
            });

            this.notifyWarning("Este ticket no se puede cerrar desde el estado actual.");

            return;
        }

        if (this.uiState.contadoresDirty) {
            this.notifyWarning("Guarda los contadores antes de cerrar el ticket.");

            console.warn(TAG, "[onCerrarTicket] contadores pendientes por guardar", {
                draft: this.uiState.contadorDraft,
            });

            return;
        }

        if (!this.retornoIsSet) {
            this.notifyWarning("Antes de cerrar, indica si requiere retorno.");

            console.warn(TAG, "[onCerrarTicket] retorno no definido");
            return;
        }

        if (!confirm("¿Cerrar este ticket?")) {
            console.log(TAG, "[onCerrarTicket] cancelado por usuario");
            return;
        }

        const ok = await this.callAction("action_finalizar", {}, {
            successMessage: "Ticket cerrado correctamente.",
            errorPrefix: "No se pudo cerrar el ticket.",
        });

        console.log(TAG, "[onCerrarTicket] result", { ok });
    }

    async onAbrirMapa() {
        console.log(TAG, "[onAbrirMapa]");

        if (!this.hasCoordinates) {
            this.notifyWarning("El equipo no tiene coordenadas registradas.");
            return;
        }

        await this.callAction("action_abrir_mapa_equipo", {}, {
            errorPrefix: "No se pudo abrir el mapa.",
        });
    }

    async onNavegar() {
        console.log(TAG, "[onNavegar]");

        if (!this.hasCoordinates) {
            this.notifyWarning("El equipo no tiene coordenadas para navegar.");
            return;
        }

        await this.callAction("action_navegar_a_equipo", {}, {
            errorPrefix: "No se pudo abrir la navegación.",
        });
    }

    async openComponentes() {
        this.closeMenu();

        console.log(TAG, "[openComponentes] start", {
            resId: this.record?.resId,
            resModel: this.record?.resModel,
        });

        if (this.uiState.contadoresDirty) {
            this.notifyWarning("Guarda los contadores antes de abrir componentes.");
            return;
        }

        if (!this.record?.resId) {
            console.warn(TAG, "[openComponentes] no resId");

            this.notifyWarning("No se pueden abrir componentes: el ticket no tiene ID.");

            return;
        }

        try {
            await this.action.doAction("sat.action_ticket_componente_evaluacion_mobile", {
                additionalContext: {
                    active_id: this.record.resId,
                    active_ids: [this.record.resId],
                    active_model: this.record.resModel,
                    default_ticket_id: this.record.resId,
                    mobile_ticket_eval: true,
                },
            });

            console.log(TAG, "[openComponentes] doAction OK");

        } catch (error) {
            console.error(TAG, "[openComponentes] error", error);

            this.notifyDanger("No se pudo abrir la evaluación de componentes.");
        }
    }

    async openAccesorios() {
        this.closeMenu();

        console.log(TAG, "[openAccesorios] start", {
            resId: this.record?.resId,
            resModel: this.record?.resModel,
        });

        if (this.uiState.contadoresDirty) {
            this.notifyWarning("Guarda los contadores antes de abrir accesorios.");
            return;
        }

        if (!this.record?.resId) {
            console.warn(TAG, "[openAccesorios] no resId");

            this.notifyWarning("No se pueden abrir accesorios: el ticket no tiene ID.");

            return;
        }

        try {
            await this.action.doAction("sat.action_ticket_accesorio_evaluacion_mobile", {
                additionalContext: {
                    active_id: this.record.resId,
                    active_ids: [this.record.resId],
                    active_model: this.record.resModel,
                    default_ticket_id: this.record.resId,
                    mobile_ticket_eval: true,
                },
            });

            console.log(TAG, "[openAccesorios] doAction OK");

        } catch (error) {
            console.error(TAG, "[openAccesorios] error", error);

            this.notifyDanger("No se pudo abrir la evaluación de accesorios.");
        }
    }

    async openPedidos() {
        this.closeMenu();

        console.log(TAG, "[openPedidos] start", {
            resId: this.record?.resId,
            resModel: this.record?.resModel,
        });

        if (this.uiState.contadoresDirty) {
            this.notifyWarning("Guarda los contadores antes de abrir pedidos.");
            return;
        }

        if (!this.record?.resId) {
            console.warn(TAG, "[openPedidos] no resId");

            this.notifyWarning("No se pueden abrir pedidos: el ticket no tiene ID.");

            return;
        }

        const action = {
            type: "ir.actions.act_window",
            name: "Pedidos de repuestos",
            res_model: "ticket.repuesto.pedido",
            view_mode: "list,form",
            views: [
                [false, "list"],
                [false, "form"],
            ],
            target: "current",
            domain: [["ticket_id", "=", this.record.resId]],
            context: {
                default_ticket_id: this.record.resId,
                active_id: this.record.resId,
                active_ids: [this.record.resId],
                active_model: this.record.resModel,
            },
        };

        console.log(TAG, "[openPedidos] doAction", {
            action,
        });

        try {
            await this.action.doAction(action);

        } catch (error) {
            console.error(TAG, "[openPedidos] error", error);

            this.notifyDanger("No se pudieron abrir los pedidos de repuestos.");
        }
    }

    async openFullForm() {
        this.closeMenu();

        console.log(TAG, "[openFullForm] start", {
            resModel: this.record?.resModel,
            resId: this.record?.resId,
        });

        if (this.uiState.contadoresDirty) {
            if (!confirm("Hay contadores pendientes por guardar. ¿Abrir el formulario completo sin guardar?")) {
                return;
            }
        }

        if (!this.record?.resModel || !this.record?.resId) {
            console.warn(TAG, "[openFullForm] no resModel/resId");

            this.notifyWarning("No se puede abrir el formulario completo: el ticket no tiene ID.");

            return;
        }

        const action = {
            type: "ir.actions.act_window",
            name: "Ticket",
            res_model: this.record.resModel,
            res_id: this.record.resId,
            view_mode: "form",
            views: [[false, "form"]],
            target: "current",
            context: {
                active_id: this.record.resId,
                active_ids: [this.record.resId],
                active_model: this.record.resModel,
            },
        };

        console.log(TAG, "[openFullForm] doAction", {
            action,
        });

        try {
            await this.action.doAction(action);

        } catch (error) {
            console.error(TAG, "[openFullForm] error", error);

            this.notifyDanger("No se pudo abrir el formulario completo.");
        }
    }

    callPhone(phone) {
        console.log(TAG, "[callPhone]", {
            phone,
        });

        if (!phone) {
            this.notifyWarning("No hay número de teléfono disponible.");
            return;
        }

        window.location.href = `tel:${phone}`;
    }
}

export const mobileTicketLayoutField = {
    component: MobileTicketLayout,
    supportedTypes: ["char", "text", "boolean", "integer"],
};

registry.category("fields").add("mobile_layout", mobileTicketLayoutField);