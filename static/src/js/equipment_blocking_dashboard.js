/** @odoo-module **/

import { AbstractAction } from "@web/webclient/actions/abstract_action";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onMounted, useState, xml } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

export class EquipmentBlockingDashboard extends AbstractAction {
    static template = xml`
        <div class="o_dashboard_view">
            <!-- Header del Dashboard -->
            <div class="o_dashboard_header mb-4">
                <div class="d-flex align-items-center">
                    <i class="fa fa-shield-alt fa-2x text-primary me-3"></i>
                    <div>
                        <h2 class="mb-1">Sistema de Bloqueo de Equipos</h2>
                        <p class="text-muted mb-0">Gestión centralizada de estados de servicio y bloqueos remotos</p>
                    </div>
                </div>
            </div>

            <!-- Cards de estadísticas -->
            <div class="o_dashboard_stats row g-3 mb-4">
                <div class="col-xl-2 col-lg-4 col-md-6">
                    <div class="card border-0 shadow-sm h-100 dashboard-card" t-on-click="() => this.filterByStatus('activo')">
                        <div class="card-body">
                            <div class="d-flex justify-content-between align-items-start">
                                <div>
                                    <h6 class="text-muted text-uppercase fw-bold small mb-2">Equipos Activos</h6>
                                    <h2 class="h1 fw-bold mb-0" t-esc="state.dashboardData.equipos_activos"/>
                                    <small class="text-success">
                                        <i class="fa fa-arrow-up"></i> Funcionando normal
                                    </small>
                                </div>
                                <div class="bg-success rounded-circle p-3">
                                    <i class="fa fa-check-circle text-white fa-lg"></i>
                                </div>
                            </div>
                        </div>
                        <div class="card-footer bg-success" style="height: 4px; padding: 0;"></div>
                    </div>
                </div>

                <div class="col-xl-2 col-lg-4 col-md-6">
                    <div class="card border-0 shadow-sm h-100 dashboard-card" t-on-click="() => this.filterByStatus('suspendido')">
                        <div class="card-body">
                            <div class="d-flex justify-content-between align-items-start">
                                <div>
                                    <h6 class="text-muted text-uppercase fw-bold small mb-2">Suspendidos</h6>
                                    <h2 class="h1 fw-bold mb-0" t-esc="state.dashboardData.equipos_suspendidos"/>
                                    <small class="text-warning">
                                        <i class="fa fa-exclamation-triangle"></i> Por mora
                                    </small>
                                </div>
                                <div class="bg-warning rounded-circle p-3">
                                    <i class="fa fa-pause-circle text-white fa-lg"></i>
                                </div>
                            </div>
                        </div>
                        <div class="card-footer bg-warning" style="height: 4px; padding: 0;"></div>
                    </div>
                </div>

                <div class="col-xl-2 col-lg-4 col-md-6">
                    <div class="card border-0 shadow-sm h-100 dashboard-card" t-on-click="() => this.filterByStatus('bloqueado')">
                        <div class="card-body">
                            <div class="d-flex justify-content-between align-items-start">
                                <div>
                                    <h6 class="text-muted text-uppercase fw-bold small mb-2">Bloqueados</h6>
                                    <h2 class="h1 fw-bold mb-0" t-esc="state.dashboardData.equipos_bloqueados"/>
                                    <small class="text-danger">
                                        <i class="fa fa-ban"></i> Acceso denegado
                                    </small>
                                </div>
                                <div class="bg-danger rounded-circle p-3">
                                    <i class="fa fa-lock text-white fa-lg"></i>
                                </div>
                            </div>
                        </div>
                        <div class="card-footer bg-danger" style="height: 4px; padding: 0;"></div>
                    </div>
                </div>

                <div class="col-xl-2 col-lg-4 col-md-6">
                    <div class="card border-0 shadow-sm h-100 dashboard-card" t-on-click="() => this.filterByStatus('no_accesible')">
                        <div class="card-body">
                            <div class="d-flex justify-content-between align-items-start">
                                <div>
                                    <h6 class="text-muted text-uppercase fw-bold small mb-2">No Accesibles</h6>
                                    <h2 class="h1 fw-bold mb-0" t-esc="state.dashboardData.equipos_no_accesibles"/>
                                    <small class="text-muted">
                                        <i class="fa fa-tools"></i> Requiere manual
                                    </small>
                                </div>
                                <div class="bg-secondary rounded-circle p-3">
                                    <i class="fa fa-wifi-slash text-white fa-lg"></i>
                                </div>
                            </div>
                        </div>
                        <div class="card-footer bg-secondary" style="height: 4px; padding: 0;"></div>
                    </div>
                </div>

                <div class="col-xl-2 col-lg-4 col-md-6">
                    <div class="card border-0 shadow-sm h-100 dashboard-card" t-on-click="() => this.filterByStatus('pendiente_bloqueo')">
                        <div class="card-body">
                            <div class="d-flex justify-content-between align-items-start">
                                <div>
                                    <h6 class="text-muted text-uppercase fw-bold small mb-2">Pend. Bloqueo</h6>
                                    <h2 class="h1 fw-bold mb-0" t-esc="state.dashboardData.pendientes_bloqueo"/>
                                    <small class="text-info">
                                        <i class="fa fa-hourglass-half"></i> En proceso
                                    </small>
                                </div>
                                <div class="bg-info rounded-circle p-3">
                                    <i class="fa fa-clock text-white fa-lg"></i>
                                </div>
                            </div>
                        </div>
                        <div class="card-footer bg-info" style="height: 4px; padding: 0;"></div>
                    </div>
                </div>

                <div class="col-xl-2 col-lg-4 col-md-6">
                    <div class="card border-0 shadow-sm h-100 dashboard-card" t-on-click="() => this.filterByStatus('pendiente_desbloqueo')">
                        <div class="card-body">
                            <div class="d-flex justify-content-between align-items-start">
                                <div>
                                    <h6 class="text-muted text-uppercase fw-bold small mb-2">Pend. Desbloqueo</h6>
                                    <h2 class="h1 fw-bold mb-0" t-esc="state.dashboardData.pendientes_desbloqueo"/>
                                    <small class="text-primary">
                                        <i class="fa fa-sync-alt"></i> Restaurando
                                    </small>
                                </div>
                                <div class="bg-primary rounded-circle p-3">
                                    <i class="fa fa-unlock-alt text-white fa-lg"></i>
                                </div>
                            </div>
                        </div>
                        <div class="card-footer bg-primary" style="height: 4px; padding: 0;"></div>
                    </div>
                </div>
            </div>

            <!-- Panel de búsqueda -->
            <div class="o_dashboard_search card mb-4">
                <div class="card-body">
                    <div class="row g-3 align-items-end">
                        <div class="col-lg-6">
                            <label for="search-input" class="form-label fw-bold">
                                <i class="fa fa-search me-2"></i>Buscar Equipos Alquilados
                            </label>
                            <input type="text" class="form-control" 
                                   placeholder="Buscar por serie, cliente, modelo o marca..."
                                   t-model="state.searchTerm"
                                   t-on-keydown="onSearchKeydown" />
                        </div>
                        <div class="col-lg-6">
                            <div class="d-flex gap-2 flex-wrap">
                                <button type="button" class="btn btn-primary" t-on-click="searchEquipments">
                                    <i class="fa fa-search me-2"></i>Buscar
                                </button>
                                <button type="button" class="btn btn-warning" t-on-click="loadPendingEquipments">
                                    <i class="fa fa-exclamation-circle me-2"></i>Ver Pendientes
                                </button>
                                <button type="button" class="btn btn-success" t-on-click="loadAllEquipments">
                                    <i class="fa fa-list me-2"></i>Ver Todos
                                </button>
                                <button type="button" class="btn btn-info" t-on-click="refreshDashboard" t-att-disabled="state.loading">
                                    <i class="fa fa-sync-alt me-2"></i>Actualizar
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Resultados -->
            <div class="o_dashboard_results card">
                <div class="card-header bg-light">
                    <div class="d-flex justify-content-between align-items-center">
                        <h4 class="mb-0">
                            <i class="fa fa-list me-2"></i>Equipos Alquilados
                        </h4>
                        <span class="badge bg-primary" t-esc="state.equipments.length"/>
                    </div>
                </div>
                <div class="card-body">
                    <div t-if="state.loading" class="text-center py-5">
                        <div class="spinner-border text-primary mb-3"></div>
                        <p class="text-muted">Cargando equipos...</p>
                    </div>
                    <div t-elif="state.equipments.length === 0" class="text-center py-5">
                        <i class="fa fa-inbox fa-3x text-muted mb-3"></i>
                        <p class="text-muted">No se encontraron equipos.</p>
                        <button type="button" class="btn btn-primary" t-on-click="loadAllEquipments">
                            <i class="fa fa-list me-2"></i>Ver Todos los Equipos
                        </button>
                    </div>
                    <div t-else="">
                        <div t-foreach="state.equipments" t-as="equipment" t-key="equipment.id" class="equipment-card">
                            <div class="d-flex justify-content-between align-items-start mb-3">
                                <div>
                                    <h5 class="mb-1 fw-bold">Serie: <t t-esc="equipment.serie"/></h5>
                                    <p class="text-muted mb-0"><t t-esc="equipment.cliente"/> - <t t-esc="equipment.modelo"/></p>
                                </div>
                                <span t-attf-class="status-badge status-#{equipment.estado_bloqueo}">
                                    <t t-esc="equipment.estado_label"/>
                                </span>
                            </div>
                            
                            <div class="detail-grid">
                                <div class="detail-item">
                                    <i class="fa fa-industry"></i>
                                    <span>Marca: <t t-esc="equipment.marca"/></span>
                                </div>
                                <div class="detail-item">
                                    <i class="fa fa-map-marker-alt"></i>
                                    <span>Dirección: <t t-esc="equipment.direccion"/></span>
                                </div>
                                <div class="detail-item">
                                    <i class="fa fa-network-wired"></i>
                                    <span>IP: <t t-esc="equipment.ip_equipo or 'No configurada'"/></span>
                                </div>
                                <div class="detail-item">
                                    <i class="fa fa-wifi"></i>
                                    <span>Acceso remoto: <t t-if="equipment.acceso_remoto">Disponible</t><t t-else="">No disponible</t></span>
                                </div>
                            </div>
                            
                            <div t-if="equipment.motivo_bloqueo" class="alert alert-info py-2 mb-3">
                                <strong>Motivo:</strong> <t t-esc="equipment.motivo_bloqueo"/>
                            </div>
                            
                            <div t-if="equipment.fecha_bloqueo" class="text-muted small mb-3">
                                <i class="fa fa-clock"></i> <t t-esc="equipment.fecha_bloqueo"/>
                            </div>
                            
                            <div class="d-flex gap-2 justify-content-end flex-wrap">
                                <button t-if="equipment.puede_suspender" 
                                        class="btn btn-warning btn-sm" 
                                        t-on-click="() => this.openActionModal('suspend', equipment.id, equipment.serie)">
                                    <i class="fa fa-pause me-1"></i> Suspender
                                </button>
                                <button t-if="equipment.puede_bloquear" 
                                        class="btn btn-danger btn-sm" 
                                        t-on-click="() => this.openActionModal('block', equipment.id, equipment.serie)">
                                    <i class="fa fa-lock me-1"></i> Bloquear
                                </button>
                                <button t-if="equipment.puede_desbloquear" 
                                        class="btn btn-success btn-sm" 
                                        t-on-click="() => this.openActionModal('unblock', equipment.id, equipment.serie)">
                                    <i class="fa fa-unlock me-1"></i> Desbloquear
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;
    setup() {
        super.setup();
        
        this.orm = useService("orm");
        this.rpc = useService("rpc");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        
        this.state = useState({
            dashboardData: {
                equipos_activos: 0,
                equipos_suspendidos: 0,
                equipos_bloqueados: 0,
                equipos_no_accesibles: 0,
                pendientes_bloqueo: 0,
                pendientes_desbloqueo: 0
            },
            equipments: [],
            loading: false,
            currentFilter: 'todos',
            searchTerm: '',
            currentAction: null,
            currentEquipmentId: null
        });

        onWillStart(async () => {
            await this.loadDashboardData();
            await this.loadAllEquipments();
        });
    }

    // Event handlers
    onSearchKeydown(ev) {
        if (ev.key === 'Enter') {
            this.searchEquipments();
        }
    }

    // Métodos principales
    async loadDashboardData() {
        try {
            const result = await this.orm.call("alquiler", "get_dashboard_data", []);
            this.state.dashboardData = result;
        } catch (error) {
            console.error("Error loading dashboard data:", error);
            this.notification.add(_t("Error al cargar datos del dashboard"), { type: "danger" });
        }
    }

    async loadAllEquipments() {
        this.state.loading = true;
        this.state.currentFilter = 'todos';
        
        try {
            const equipments = await this.orm.searchRead(
                "alquiler",
                [["estado_alquiler_id", "=", "alquilada"]],
                [
                    "id", "serie", "cliente_id", "name", "marca", "direccion",
                    "ip_equipo", "estado_bloqueo", "acceso_remoto_disponible",
                    "motivo_bloqueo", "fecha_bloqueo"
                ]
            );
            
            this.state.equipments = this.processEquipments(equipments);
            
        } catch (error) {
            console.error("Error loading equipments:", error);
            this.notification.add(_t("Error al cargar equipos"), { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async searchEquipments() {
        const searchTerm = this.state.searchTerm.trim();
        this.state.loading = true;
        this.state.currentFilter = 'busqueda';
        
        try {
            let domain = [["estado_alquiler_id", "=", "alquilada"]];
            
            if (searchTerm) {
                domain.push([
                    "|", "|", "|",
                    ["serie", "ilike", searchTerm],
                    ["cliente_id", "ilike", searchTerm],
                    ["name", "ilike", searchTerm],
                    ["marca", "ilike", searchTerm]
                ]);
            }
            
            const equipments = await this.orm.searchRead(
                "alquiler",
                domain,
                [
                    "id", "serie", "cliente_id", "name", "marca", "direccion",
                    "ip_equipo", "estado_bloqueo", "acceso_remoto_disponible",
                    "motivo_bloqueo", "fecha_bloqueo"
                ]
            );
            
            this.state.equipments = this.processEquipments(equipments);
            
            const message = searchTerm 
                ? _t(`Encontrados ${equipments.length} equipos para "${searchTerm}"`)
                : _t(`Mostrando ${equipments.length} equipos alquilados`);
            this.notification.add(message, { type: "success" });
            
        } catch (error) {
            console.error("Error searching equipments:", error);
            this.notification.add(_t("Error al buscar equipos"), { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async filterByStatus(estado) {
        this.state.loading = true;
        this.state.currentFilter = estado;
        this.state.searchTerm = '';
        
        try {
            const equipments = await this.orm.searchRead(
                "alquiler",
                [
                    ["estado_alquiler_id", "=", "alquilada"],
                    ["estado_bloqueo", "=", estado]
                ],
                [
                    "id", "serie", "cliente_id", "name", "marca", "direccion",
                    "ip_equipo", "estado_bloqueo", "acceso_remoto_disponible",
                    "motivo_bloqueo", "fecha_bloqueo"
                ]
            );
            
            this.state.equipments = this.processEquipments(equipments);
            
            const estadoLabels = {
                'activo': 'equipos activos',
                'suspendido': 'equipos suspendidos',
                'bloqueado': 'equipos bloqueados',
                'no_accesible': 'equipos no accesibles',
                'pendiente_bloqueo': 'equipos pendientes de bloqueo',
                'pendiente_desbloqueo': 'equipos pendientes de desbloqueo'
            };
            
            const estadoLabel = estadoLabels[estado] || 'equipos';
            this.notification.add(_t(`Mostrando ${equipments.length} ${estadoLabel}`), { type: "success" });
            
        } catch (error) {
            console.error("Error filtering equipments:", error);
            this.notification.add(_t("Error al filtrar equipos"), { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async loadPendingEquipments() {
        this.state.loading = true;
        this.state.currentFilter = 'pendientes';
        this.state.searchTerm = '';
        
        try {
            const equipments = await this.orm.searchRead(
                "alquiler",
                [
                    ["estado_alquiler_id", "=", "alquilada"],
                    ["estado_bloqueo", "in", ["suspendido", "bloqueado", "no_accesible", "pendiente_bloqueo", "pendiente_desbloqueo"]]
                ],
                [
                    "id", "serie", "cliente_id", "name", "marca", "direccion",
                    "ip_equipo", "estado_bloqueo", "acceso_remoto_disponible",
                    "motivo_bloqueo", "fecha_bloqueo"
                ]
            );
            
            this.state.equipments = this.processEquipments(equipments);
            
            this.notification.add(_t(`${equipments.length} equipos requieren atención`), { type: "warning" });
            
        } catch (error) {
            console.error("Error loading pending equipments:", error);
            this.notification.add(_t("Error al cargar equipos pendientes"), { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async refreshDashboard() {
        this.state.loading = true;
        
        try {
            await this.loadDashboardData();
            
            // Recargar vista actual según el filtro
            switch(this.state.currentFilter) {
                case 'todos':
                    await this.loadAllEquipments();
                    break;
                case 'pendientes':
                    await this.loadPendingEquipments();
                    break;
                case 'busqueda':
                    await this.searchEquipments();
                    break;
                default:
                    if (['activo', 'suspendido', 'bloqueado', 'no_accesible', 'pendiente_bloqueo', 'pendiente_desbloqueo'].includes(this.state.currentFilter)) {
                        await this.filterByStatus(this.state.currentFilter);
                    } else {
                        await this.loadAllEquipments();
                    }
            }
            
            this.notification.add(_t('Dashboard actualizado correctamente'), { type: "success" });
            
        } catch (error) {
            console.error("Error refreshing dashboard:", error);
            this.notification.add(_t('Error al actualizar el dashboard'), { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    // Métodos de procesamiento
    processEquipments(equipments) {
        return equipments.map(equipment => {
            const estadoLabels = {
                'activo': 'Activo',
                'suspendido': 'Suspendido',
                'bloqueado': 'Bloqueado',
                'no_accesible': 'No Accesible',
                'pendiente_bloqueo': 'Pend. Bloqueo',
                'pendiente_desbloqueo': 'Pend. Desbloqueo'
            };
            
            return {
                ...equipment,
                cliente: equipment.cliente_id ? equipment.cliente_id[1] : '',
                modelo: equipment.name ? equipment.name[1] : '',
                estado_label: estadoLabels[equipment.estado_bloqueo] || equipment.estado_bloqueo,
                acceso_remoto: equipment.acceso_remoto_disponible || false,
                puede_suspender: equipment.estado_bloqueo === 'activo',
                puede_bloquear: ['activo', 'suspendido'].includes(equipment.estado_bloqueo) && equipment.acceso_remoto_disponible,
                puede_desbloquear: ['bloqueado', 'suspendido'].includes(equipment.estado_bloqueo)
            };
        });
    }

    // Métodos de acciones
    async openActionModal(action, equipmentId, serie) {
        // Por ahora usaremos dialog simple, después implementaremos modal complejo
        const equipment = this.state.equipments.find(eq => eq.id === equipmentId);
        
        if (!equipment) {
            this.notification.add(_t("Error: No se encontró el equipo"), { type: "danger" });
            return;
        }

        const actionLabels = {
            'suspend': 'Suspender Servicio',
            'block': 'Bloquear Equipo',
            'unblock': 'Desbloquear Equipo'
        };

        const motivo = prompt(`${actionLabels[action]} - Serie: ${serie}\n\nIngrese el motivo:`);
        
        if (motivo !== null) {
            await this.executeAction(action, equipmentId, motivo);
        }
    }

    async executeAction(action, equipmentId, motivo) {
        try {
            const methodMap = {
                'suspend': 'action_suspender_servicio',
                'block': 'action_bloquear_equipo',
                'unblock': 'action_desbloquear_equipo'
            };
            
            const method = methodMap[action];
            
            const result = await this.orm.call("alquiler", method, [equipmentId], { motivo: motivo });
            
            if (result.success !== false) {
                this.notification.add(_t('Acción ejecutada correctamente'), { type: "success" });
                await this.refreshDashboard();
            } else {
                this.notification.add(_t(result.error || 'Error al ejecutar la acción'), { type: "danger" });
            }
            
        } catch (error) {
            console.error("Error executing action:", error);
            this.notification.add(_t('Error al ejecutar la acción'), { type: "danger" });
        }
    }
}

// Registrar el componente
registry.category("actions").add("equipment_blocking_dashboard", EquipmentBlockingDashboard);} catch (error) {
            console.error("Error loading equipments:", error);
            this.notification.add(_t("Error al cargar equipos"), { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async searchEquipments() {
        const searchTerm = this.state.searchTerm.trim();
        this.state.loading = true;
        this.state.currentFilter = 'busqueda';
        
        try {
            let domain = [["estado_alquiler_id", "=", "alquilada"]];
            
            if (searchTerm) {
                domain.push([
                    "|", "|", "|",
                    ["serie", "ilike", searchTerm],
                    ["cliente_id", "ilike", searchTerm],
                    ["name", "ilike", searchTerm],
                    ["marca", "ilike", searchTerm]
                ]);
            }
            
            const equipments = await this.orm.searchRead(
                "alquiler",
                domain,
                [
                    "id", "serie", "cliente_id", "name", "marca", "direccion",
                    "ip_equipo", "estado_bloqueo", "acceso_remoto_disponible",
                    "motivo_bloqueo", "fecha_bloqueo", "puede_suspender",
                    "puede_bloquear", "puede_desbloquear"
                ]
            );
            
            this.state.equipments = this.processEquipments(equipments);
            this.displayEquipments(this.state.equipments);
            
            const message = searchTerm 
                ? _t(`Encontrados ${equipments.length} equipos para "${searchTerm}"`)
                : _t(`Mostrando ${equipments.length} equipos alquilados`);
            this.notification.add(message, { type: "success" });
            
        } catch (error) {
            console.error("Error searching equipments:", error);
            this.notification.add(_t("Error al buscar equipos"), { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async filterByStatus(estado) {
        this.state.loading = true;
        this.state.currentFilter = estado;
        this.state.searchTerm = '';
        
        try {
            const equipments = await this.orm.searchRead(
                "alquiler",
                [
                    ["estado_alquiler_id", "=", "alquilada"],
                    ["estado_bloqueo", "=", estado]
                ],
                [
                    "id", "serie", "cliente_id", "name", "marca", "direccion",
                    "ip_equipo", "estado_bloqueo", "acceso_remoto_disponible",
                    "motivo_bloqueo", "fecha_bloqueo", "puede_suspender",
                    "puede_bloquear", "puede_desbloquear"
                ]
            );
            
            this.state.equipments = this.processEquipments(equipments);
            this.displayEquipments(this.state.equipments);
            
            const estadoLabels = {
                'activo': 'equipos activos',
                'suspendido': 'equipos suspendidos',
                'bloqueado': 'equipos bloqueados',
                'no_accesible': 'equipos no accesibles',
                'pendiente_bloqueo': 'equipos pendientes de bloqueo',
                'pendiente_desbloqueo': 'equipos pendientes de desbloqueo'
            };
            
            const estadoLabel = estadoLabels[estado] || 'equipos';
            this.notification.add(_t(`Mostrando ${equipments.length} ${estadoLabel}`), { type: "success" });
            
        } catch (error) {
            console.error("Error filtering equipments:", error);
            this.notification.add(_t("Error al filtrar equipos"), { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async loadPendingEquipments() {
        this.state.loading = true;
        this.state.currentFilter = 'pendientes';
        this.state.searchTerm = '';
        
        try {
            const equipments = await this.orm.searchRead(
                "alquiler",
                [
                    ["estado_alquiler_id", "=", "alquilada"],
                    ["estado_bloqueo", "in", ["suspendido", "bloqueado", "no_accesible", "pendiente_bloqueo", "pendiente_desbloqueo"]]
                ],
                [
                    "id", "serie", "cliente_id", "name", "marca", "direccion",
                    "ip_equipo", "estado_bloqueo", "acceso_remoto_disponible",
                    "motivo_bloqueo", "fecha_bloqueo", "puede_suspender",
                    "puede_bloquear", "puede_desbloquear"
                ]
            );
            
            this.state.equipments = this.processEquipments(equipments);
            this.displayEquipments(this.state.equipments);
            
            this.notification.add(_t(`${equipments.length} equipos requieren atención`), { type: "warning" });
            
        } catch (error) {
            console.error("Error loading pending equipments:", error);
            this.notification.add(_t("Error al cargar equipos pendientes"), { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    // Métodos de procesamiento de datos
    processEquipments(equipments) {
        return equipments.map(equipment => {
            // Mapear estado_bloqueo a label
            const estadoLabels = {
                'activo': 'Activo',
                'suspendido': 'Suspendido',
                'bloqueado': 'Bloqueado',
                'no_accesible': 'No Accesible',
                'pendiente_bloqueo': 'Pend. Bloqueo',
                'pendiente_desbloqueo': 'Pend. Desbloqueo'
            };
            
            return {
                ...equipment,
                cliente: equipment.cliente_id ? equipment.cliente_id[1] : '',
                modelo: equipment.name || '',
                estado_label: estadoLabels[equipment.estado_bloqueo] || equipment.estado_bloqueo,
                acceso_remoto: equipment.acceso_remoto_disponible || false,
                puede_suspender: equipment.estado_bloqueo === 'activo',
                puede_bloquear: ['activo', 'suspendido'].includes(equipment.estado_bloqueo),
                puede_desbloquear: ['bloqueado', 'suspendido'].includes(equipment.estado_bloqueo)
            };
        });
    }

    // Métodos de UI
    updateDashboardStats() {
        const data = this.state.dashboardData;
        
        const updateElement = (id, value) => {
            const element = document.getElementById(id);
            if (element) {
                element.textContent = value;
            }
        };
        
        updateElement('equipos-activos', data.equipos_activos);
        updateElement('equipos-suspendidos', data.equipos_suspendidos);
        updateElement('equipos-bloqueados', data.equipos_bloqueados);
        updateElement('equipos-no-accesibles', data.equipos_no_accesibles);
        updateElement('pendientes-bloqueo', data.pendientes_bloqueo);
        updateElement('pendientes-desbloqueo', data.pendientes_desbloqueo);
    }

    displayEquipments(equipments) {
        const resultsContainer = document.getElementById('equipment-results');
        const resultsCount = document.getElementById('results-count');
        
        if (resultsCount) {
            resultsCount.textContent = equipments.length;
        }
        
        if (!resultsContainer) return;
        
        if (equipments.length === 0) {
            resultsContainer.innerHTML = this.getEmptyStateHTML();
            return;
        }
        
        const equipmentCards = equipments.map(equipment => this.createEquipmentCardHTML(equipment)).join('');
        resultsContainer.innerHTML = equipmentCards;
    }

    getEmptyStateHTML() {
        let emptyMessage = 'No se encontraron equipos con los criterios especificados.';
        let emptyIcon = 'fa fa-inbox';
        
        switch(this.state.currentFilter) {
            case 'activo':
                emptyMessage = 'No hay equipos activos en este momento.';
                emptyIcon = 'fa fa-check-circle';
                break;
            case 'suspendido':
                emptyMessage = 'No hay equipos suspendidos.';
                emptyIcon = 'fa fa-pause-circle';
                break;
            case 'bloqueado':
                emptyMessage = 'No hay equipos bloqueados.';
                emptyIcon = 'fa fa-lock';
                break;
            case 'pendientes':
                emptyMessage = 'No hay equipos pendientes de atención.';
                emptyIcon = 'fa fa-check-circle';
                break;
            case 'busqueda':
                emptyMessage = 'No se encontraron equipos que coincidan con la búsqueda.';
                emptyIcon = 'fa fa-search';
                break;
        }
        
        return `
            <div class="text-center py-5">
                <i class="${emptyIcon} fa-3x text-muted mb-3"></i>
                <p class="text-muted">${emptyMessage}</p>
                <button type="button" class="btn btn-primary" onclick="window.dashboardInstance.loadAllEquipments()">
                    <i class="fa fa-list me-2"></i>Ver Todos los Equipos
                </button>
            </div>
        `;
    }

    createEquipmentCardHTML(equipment) {
        const motivoSection = equipment.motivo_bloqueo ? 
            `<div class="alert alert-info py-2 mb-3">
                <strong>Motivo:</strong> ${this.escapeHtml(equipment.motivo_bloqueo)}
            </div>` : '';
        
        const fechaSection = equipment.fecha_bloqueo ? 
            `<div class="text-muted small mb-3">
                <i class="fa fa-clock"></i> ${this.escapeHtml(equipment.fecha_bloqueo)}
            </div>` : '';

        const buttons = [];
        
        if (equipment.puede_suspender) {
            buttons.push(`
                <button class="btn btn-warning btn-sm" onclick="window.dashboardInstance.openActionModal('suspend', ${equipment.id}, '${this.escapeHtml(equipment.serie)}')">
                    <i class="fa fa-pause me-1"></i> Suspender
                </button>
            `);
        }
        if (equipment.puede_bloquear) {
            buttons.push(`
                <button class="btn btn-danger btn-sm" onclick="window.dashboardInstance.openActionModal('block', ${equipment.id}, '${this.escapeHtml(equipment.serie)}')">
                    <i class="fa fa-lock me-1"></i> Bloquear
                </button>
            `);
        }
        if (equipment.puede_desbloquear) {
            buttons.push(`
                <button class="btn btn-success btn-sm" onclick="window.dashboardInstance.openActionModal('unblock', ${equipment.id}, '${this.escapeHtml(equipment.serie)}')">
                    <i class="fa fa-unlock me-1"></i> Desbloquear
                </button>
            `);
        }

        return `
            <div class="equipment-card">
                <div class="d-flex justify-content-between align-items-start mb-3">
                    <div>
                        <h5 class="mb-1 fw-bold">Serie: ${this.escapeHtml(equipment.serie)}</h5>
                        <p class="text-muted mb-0">${this.escapeHtml(equipment.cliente)} - ${this.escapeHtml(equipment.modelo)}</p>
                    </div>
                    <span class="status-badge status-${equipment.estado_bloqueo}">
                        ${this.escapeHtml(equipment.estado_label)}
                    </span>
                </div>
                
                <div class="detail-grid">
                    <div class="detail-item">
                        <i class="fa fa-industry"></i>
                        <span>Marca: ${this.escapeHtml(equipment.marca)}</span>
                    </div>
                    <div class="detail-item">
                        <i class="fa fa-map-marker-alt"></i>
                        <span>Dirección: ${this.escapeHtml(equipment.direccion)}</span>
                    </div>
                    <div class="detail-item">
                        <i class="fa fa-network-wired"></i>
                        <span>IP: ${this.escapeHtml(equipment.ip_equipo || 'No configurada')}</span>
                    </div>
                    <div class="detail-item">
                        <i class="fa fa-wifi"></i>
                        <span>Acceso remoto: ${equipment.acceso_remoto ? 'Disponible' : 'No disponible'}</span>
                    </div>
                </div>
                
                ${motivoSection}
                ${fechaSection}
                
                <div class="d-flex gap-2 justify-content-end flex-wrap">
                    ${buttons.join('')}
                </div>
            </div>
        `;
    }

    // Métodos de acciones
    async openActionModal(action, equipmentId, serie) {
        this.state.currentAction = action;
        this.state.currentEquipmentId = equipmentId;
        
        // Encontrar el equipo en el estado actual
        const equipment = this.state.equipments.find(eq => eq.id === equipmentId);
        
        if (!equipment) {
            this.notification.add(_t("Error: No se encontró el equipo"), { type: "danger" });
            return;
        }
        
        // Configurar modal
        const modal = document.getElementById('actionModal');
        const modalTitle = document.getElementById('modalTitle');
        const motivoInput = document.getElementById('motivoInput');
        const confirmBtn = document.getElementById('confirmActionBtn');
        const equipmentDetails = document.getElementById('equipmentDetails');
        
        // Actualizar detalles del equipo
        this.updateElement('detailCliente', equipment.cliente || 'No especificado');
        this.updateElement('detailModelo', equipment.modelo || 'No especificado');
        this.updateElement('detailIP', equipment.ip_equipo || 'No configurada');
        
        const estadoElement = document.getElementById('detailEstado');
        if (estadoElement) {
            estadoElement.innerHTML = `<span class="status-badge status-${equipment.estado_bloqueo}">${equipment.estado_label}</span>`;
        }
        
        if (equipmentDetails) {
            equipmentDetails.style.display = 'block';
        }
        
        // Configurar según la acción
        switch(action) {
            case 'suspend':
                modalTitle.textContent = `Suspender Servicio - Serie: ${serie}`;
                motivoInput.placeholder = 'Motivo de la suspensión (ej: Mora de pagos, incumplimiento contractual...)';
                confirmBtn.className = 'btn btn-warning';
                confirmBtn.innerHTML = '<span id="btnText"><i class="fa fa-pause me-2"></i>Suspender Servicio</span>';
                break;
            case 'block':
                modalTitle.textContent = `Bloquear Equipo - Serie: ${serie}`;
                motivoInput.placeholder = 'Motivo del bloqueo remoto (ej: Mantenimiento, violación de términos...)';
                confirmBtn.className = 'btn btn-danger';
                confirmBtn.innerHTML = '<span id="btnText"><i class="fa fa-lock me-2"></i>Bloquear Equipo</span>';
                break;
            case 'unblock':
                modalTitle.textContent = `Desbloquear Equipo - Serie: ${serie}`;
                motivoInput.placeholder = 'Observaciones del desbloqueo (ej: Pago realizado, problema resuelto...)';
                confirmBtn.className = 'btn btn-success';
                confirmBtn.innerHTML = '<span id="btnText"><i class="fa fa-unlock me-2"></i>Desbloquear Equipo</span>';
                break;
        }
        
        // Limpiar y mostrar modal
        motivoInput.value = '';
        document.getElementById('modalAlert').innerHTML = '';
        confirmBtn.disabled = false;
        
        // Mostrar modal usando Bootstrap
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
    }

    async executeAction() {
        const motivoInput = document.getElementById('motivoInput');
        const motivo = motivoInput.value.trim();
        const confirmBtn = document.getElementById('confirmActionBtn');
        
        // Validar motivo para acciones críticas
        if ((this.state.currentAction === 'suspend' || this.state.currentAction === 'block') && !motivo) {
            this.showModalAlert('warning', _t('Por favor, proporciona un motivo para esta acción.'));
            return;
        }
        
        // Mostrar loading
        confirmBtn.disabled = true;
        confirmBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Procesando...';
        
        try {
            const methodMap = {
                'suspend': 'action_suspender_servicio',
                'block': 'action_bloquear_equipo',
                'unblock': 'action_desbloquear_equipo'
            };
            
            const method = methodMap[this.state.currentAction];
            
            await this.rpc("/web/dataset/call_kw/alquiler/" + method, {
                model: "alquiler",
                method: method,
                args: [this.state.currentEquipmentId],
                kwargs: { motivo: motivo }
            });
            
            this.showModalAlert('success', _t('Acción ejecutada correctamente'));
            
            // Cerrar modal y actualizar después de 2 segundos
            setTimeout(() => {
                const modal = bootstrap.Modal.getInstance(document.getElementById('actionModal'));
                modal.hide();
                this.refreshDashboard();
            }, 2000);
            
        } catch (error) {
            console.error("Error executing action:", error);
            this.showModalAlert('danger', _t('Error al ejecutar la acción'));
        } finally {
            // Restaurar botón
            confirmBtn.disabled = false;
            this.resetConfirmButton();
        }
    }

    async refreshDashboard() {
        const refreshBtn = document.getElementById('refreshBtn');
        if (refreshBtn) {
            refreshBtn.disabled = true;
            refreshBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Actualizando...';
        }
        
        try {
            await this.loadDashboardData();
            
            // Recargar vista actual según el filtro
            switch(this.state.currentFilter) {
                case 'todos':
                    await this.loadAllEquipments();
                    break;
                case 'pendientes':
                    await this.loadPendingEquipments();
                    break;
                case 'busqueda':
                    await this.searchEquipments();
                    break;
                default:
                    if (['activo', 'suspendido', 'bloqueado', 'no_accesible', 'pendiente_bloqueo', 'pendiente_desbloqueo'].includes(this.state.currentFilter)) {
                        await this.filterByStatus(this.state.currentFilter);
                    } else {
                        await this.loadAllEquipments();
                    }
            }
            
            this.notification.add(_t('Dashboard actualizado correctamente'), { type: "success" });
            
        } catch (error) {
            console.error("Error refreshing dashboard:", error);
            this.notification.add(_t('Error al actualizar el dashboard'), { type: "danger" });
        } finally {
            if (refreshBtn) {
                refreshBtn.disabled = false;
                refreshBtn.innerHTML = '<i class="fa fa-sync-alt me-2"></i>Actualizar';
            }
        }
    }

    // Métodos de utilidad
    setupEventListeners() {
        // Exponer instancia globalmente para callbacks onclick
        window.dashboardInstance = this;
        
        // Event listeners para botones
        const searchBtn = document.getElementById('searchBtn');
        const pendingBtn = document.getElementById('pendingBtn');
        const showAllBtn = document.getElementById('showAllBtn');
        const refreshBtn = document.getElementById('refreshBtn');
        const confirmBtn = document.getElementById('confirmActionBtn');
        const searchInput = document.getElementById('search-input');
        
        if (searchBtn) {
            searchBtn.addEventListener('click', () => this.searchEquipments());
        }
        if (pendingBtn) {
            pendingBtn.addEventListener('click', () => this.loadPendingEquipments());
        }
        if (showAllBtn) {
            showAllBtn.addEventListener('click', () => this.loadAllEquipments());
        }
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.refreshDashboard());
        }
        if (confirmBtn) {
            confirmBtn.addEventListener('click', () => this.executeAction());
        }
        
        // Event listener para búsqueda
        if (searchInput) {
            searchInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    this.searchEquipments();
                }
            });
            
            searchInput.addEventListener('input', this.debounce((e) => {
                this.state.searchTerm = e.target.value;
                const value = e.target.value.trim();
                if (value.length >= 3) {
                    this.searchEquipments();
                } else if (value.length === 0) {
                    this.loadAllEquipments();
                }
            }, 500));
        }
        
        // Event listeners para cards de dashboard
        const dashboardCards = document.querySelectorAll('.dashboard-card');
        dashboardCards.forEach(card => {
            const filter = card.dataset.filter;
            if (filter) {
                card.addEventListener('click', () => this.filterByStatus(filter));
            }
        });
        
        // Shortcuts de teclado
        document.addEventListener('keydown', (e) => {
            // Ctrl/Cmd + K para buscar
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                e.preventDefault();
                if (searchInput) searchInput.focus();
            }
            
            // F5 para actualizar dashboard
            if (e.key === 'F5') {
                e.preventDefault();
                this.refreshDashboard();
            }
        });
    }

    initializeModal() {
        // Modal se inicializa automáticamente con Bootstrap 5
    }

    updateElement(id, value) {
        const element = document.getElementById(id);
        if (element) {
            element.textContent = value;
        }
    }

    showModalAlert(type, message) {
        const alertContainer = document.getElementById('modalAlert');
        if (!alertContainer) return;
        
        const alertClass = type === 'success' ? 'alert-success' : 
                         type === 'warning' ? 'alert-warning' : 'alert-danger';
        const icon = type === 'success' ? 'check-circle' : 
                    type === 'warning' ? 'exclamation-triangle' : 'exclamation-triangle';
        
        alertContainer.innerHTML = `
            <div class="alert ${alertClass} d-flex align-items-center" role="alert">
                <i class="fa fa-${icon} me-2"></i>
                <div>${this.escapeHtml(message)}</div>
            </div>
        `;
    }

    resetConfirmButton() {
        const confirmBtn = document.getElementById('confirmActionBtn');
        if (confirmBtn && this.state.currentAction) {
            const buttonConfigs = {
                'suspend': '<span id="btnText"><i class="fa fa-pause me-2"></i>Suspender Servicio</span>',
                'block': '<span id="btnText"><i class="fa fa-lock me-2"></i>Bloquear Equipo</span>',
                'unblock': '<span id="btnText"><i class="fa fa-unlock me-2"></i>Desbloquear Equipo</span>'
            };
            
            confirmBtn.innerHTML = buttonConfigs[this.state.currentAction] || '<span id="btnText">Confirmar</span>';
        }
    }

    escapeHtml(text) {
        if (!text) return '';
        const map = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        };
        return String(text).replace(/[&<>"']/g, m => map[m]);
    }

    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }
}

// Registrar el componente
registry.category("actions").add("equipment_blocking_dashboard", EquipmentBlockingDashboard);