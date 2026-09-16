BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001_core

CREATE TABLE institutions (
    nombre VARCHAR(150) NOT NULL, 
    es_propia BOOLEAN DEFAULT false NOT NULL, 
    color VARCHAR(7) NOT NULL, 
    id UUID NOT NULL, 
    CONSTRAINT pk_institutions PRIMARY KEY (id), 
    CONSTRAINT uq_institutions_nombre UNIQUE (nombre)
);

CREATE UNIQUE INDEX uq_institutions_own ON institutions (es_propia) WHERE es_propia = true;

CREATE TABLE provincias (
    nombre VARCHAR(100) NOT NULL, 
    region VARCHAR(100) NOT NULL, 
    poblacion INTEGER, 
    superficie_km2 FLOAT, 
    fuente VARCHAR(255), 
    id UUID NOT NULL, 
    CONSTRAINT pk_provincias PRIMARY KEY (id), 
    CONSTRAINT ck_provincias_population CHECK (poblacion >= 0), 
    CONSTRAINT ck_provincias_area CHECK (superficie_km2 > 0), 
    CONSTRAINT uq_provincias_nombre UNIQUE (nombre)
);

CREATE INDEX ix_provincias_region ON provincias (region);

CREATE TYPE user_role AS ENUM ('ADMIN', 'OPERATOR', 'ANALYST');

CREATE TABLE users (
    email VARCHAR(320) NOT NULL, 
    hashed_password VARCHAR(255) NOT NULL, 
    full_name VARCHAR(150) NOT NULL, 
    role user_role NOT NULL, 
    is_active BOOLEAN DEFAULT true NOT NULL, 
    token_version INTEGER DEFAULT '0' NOT NULL, 
    failed_login_attempts INTEGER DEFAULT '0' NOT NULL, 
    locked_until TIMESTAMP WITH TIME ZONE, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_users PRIMARY KEY (id), 
    CONSTRAINT ck_users_normalized_email CHECK (email = lower(email))
);

CREATE UNIQUE INDEX ix_users_email ON users (email);

CREATE TABLE audit_logs (
    actor_id UUID, 
    accion VARCHAR(60) NOT NULL, 
    entidad VARCHAR(80) NOT NULL, 
    entidad_id UUID, 
    cambios JSON NOT NULL, 
    fecha TIMESTAMP WITH TIME ZONE NOT NULL, 
    id UUID NOT NULL, 
    CONSTRAINT pk_audit_logs PRIMARY KEY (id), 
    CONSTRAINT fk_audit_logs_actor_id_users FOREIGN KEY(actor_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_audit_logs_actor_id ON audit_logs (actor_id);

CREATE INDEX ix_audit_logs_entidad ON audit_logs (entidad);

CREATE INDEX ix_audit_logs_fecha ON audit_logs (fecha);

CREATE TYPE location_type AS ENUM ('ATM', 'SUCURSAL');

CREATE TYPE candidate_status AS ENUM ('PROPUESTA', 'EN_EVALUACION', 'APROBADA', 'DESCARTADA');

CREATE TABLE candidate_locations (
    codigo VARCHAR(40) NOT NULL, 
    nombre VARCHAR(150) NOT NULL, 
    provincia VARCHAR(100) NOT NULL, 
    municipio VARCHAR(100) NOT NULL, 
    tipo location_type NOT NULL, 
    latitud FLOAT NOT NULL, 
    longitud FLOAT NOT NULL, 
    potencial_mercado FLOAT NOT NULL, 
    densidad_poblacional FLOAT NOT NULL, 
    estado candidate_status NOT NULL, 
    fuente VARCHAR(255) NOT NULL, 
    notas TEXT, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_candidate_locations PRIMARY KEY (id), 
    CONSTRAINT ck_candidate_locations_coordinates CHECK (latitud BETWEEN -90 AND 90 AND longitud BETWEEN -180 AND 180), 
    CONSTRAINT ck_candidate_locations_score_density CHECK (potencial_mercado BETWEEN 0 AND 100 AND densidad_poblacional >= 0), 
    CONSTRAINT fk_candidate_locations_provincia_provincias FOREIGN KEY(provincia) REFERENCES provincias (nombre) ON DELETE RESTRICT, 
    CONSTRAINT uq_candidate_locations_codigo UNIQUE (codigo)
);

CREATE INDEX ix_candidate_locations_potencial_mercado ON candidate_locations (potencial_mercado);

CREATE INDEX ix_candidate_locations_provincia ON candidate_locations (provincia);

CREATE TABLE competitor_locations (
    institucion_id UUID NOT NULL, 
    codigo VARCHAR(80) NOT NULL, 
    nombre VARCHAR(150) NOT NULL, 
    provincia VARCHAR(100) NOT NULL, 
    tipo location_type NOT NULL, 
    latitud FLOAT NOT NULL, 
    longitud FLOAT NOT NULL, 
    fuente VARCHAR(255) NOT NULL, 
    fecha_verificacion DATE NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_competitor_locations PRIMARY KEY (id), 
    CONSTRAINT ck_competitor_locations_coordinates CHECK (latitud BETWEEN -90 AND 90 AND longitud BETWEEN -180 AND 180), 
    CONSTRAINT fk_competitor_locations_institucion_id_institutions FOREIGN KEY(institucion_id) REFERENCES institutions (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_competitor_locations_provincia_provincias FOREIGN KEY(provincia) REFERENCES provincias (nombre) ON DELETE RESTRICT, 
    CONSTRAINT uq_competitor_locations_institucion_id UNIQUE (institucion_id, codigo)
);

CREATE INDEX ix_competitor_locations_institucion_id ON competitor_locations (institucion_id);

CREATE INDEX ix_competitor_locations_provincia ON competitor_locations (provincia);

CREATE TABLE market_snapshots (
    institucion_id UUID NOT NULL, 
    provincia VARCHAR(100) NOT NULL, 
    fecha DATE NOT NULL, 
    total_atms INTEGER NOT NULL, 
    total_sucursales INTEGER NOT NULL, 
    depositos NUMERIC(20, 2) NOT NULL, 
    prestamos NUMERIC(20, 2) NOT NULL, 
    transacciones INTEGER NOT NULL, 
    utilizacion_pct FLOAT, 
    fuente VARCHAR(255) NOT NULL, 
    id UUID NOT NULL, 
    CONSTRAINT pk_market_snapshots PRIMARY KEY (id), 
    CONSTRAINT ck_market_snapshots_positive_metrics CHECK (total_atms >= 0 AND total_sucursales >= 0 AND transacciones >= 0 AND depositos >= 0 AND prestamos >= 0), 
    CONSTRAINT ck_market_snapshots_utilization CHECK (utilizacion_pct BETWEEN 0 AND 100), 
    CONSTRAINT fk_market_snapshots_institucion_id_institutions FOREIGN KEY(institucion_id) REFERENCES institutions (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_market_snapshots_provincia_provincias FOREIGN KEY(provincia) REFERENCES provincias (nombre) ON DELETE RESTRICT, 
    CONSTRAINT uq_market_snapshots_institucion_id UNIQUE (institucion_id, provincia, fecha)
);

CREATE INDEX ix_market_snapshots_fecha ON market_snapshots (fecha);

CREATE INDEX ix_market_snapshots_institucion_id ON market_snapshots (institucion_id);

CREATE INDEX ix_market_snapshots_provincia ON market_snapshots (provincia);

CREATE TYPE branch_status AS ENUM ('OPERATIVA', 'MANTENIMIENTO', 'CERRADA');

CREATE TABLE sucursales (
    codigo VARCHAR(40) NOT NULL, 
    nombre VARCHAR(150) NOT NULL, 
    provincia VARCHAR(100) NOT NULL, 
    municipio VARCHAR(100) NOT NULL, 
    direccion TEXT NOT NULL, 
    latitud FLOAT NOT NULL, 
    longitud FLOAT NOT NULL, 
    estado branch_status NOT NULL, 
    total_cajeros_humanos INTEGER NOT NULL, 
    sla_objetivo_segundos INTEGER NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_sucursales PRIMARY KEY (id), 
    CONSTRAINT ck_sucursales_coordinates CHECK (latitud BETWEEN -90 AND 90 AND longitud BETWEEN -180 AND 180), 
    CONSTRAINT ck_sucursales_capacity_sla CHECK (total_cajeros_humanos >= 0 AND sla_objetivo_segundos > 0), 
    CONSTRAINT fk_sucursales_provincia_provincias FOREIGN KEY(provincia) REFERENCES provincias (nombre) ON DELETE RESTRICT, 
    CONSTRAINT uq_sucursales_codigo UNIQUE (codigo)
);

CREATE INDEX ix_sucursales_provincia ON sucursales (provincia);

CREATE TYPE atm_type AS ENUM ('DISPENSADOR', 'CDM_DEPOSITO');

CREATE TYPE atm_status AS ENUM ('OPERATIVO', 'BAJO_EFECTIVO', 'FUERA_DE_SERVICIO', 'MANTENIMIENTO');

CREATE TABLE atms (
    codigo_unico VARCHAR(40) NOT NULL, 
    sucursal_id UUID, 
    nombre VARCHAR(150) NOT NULL, 
    provincia VARCHAR(100) NOT NULL, 
    municipio VARCHAR(100) NOT NULL, 
    direccion TEXT NOT NULL, 
    tipo atm_type NOT NULL, 
    nivel_efectivo_pct FLOAT NOT NULL, 
    capacidad_efectivo NUMERIC(18, 2) NOT NULL, 
    estado atm_status NOT NULL, 
    latitud FLOAT NOT NULL, 
    longitud FLOAT NOT NULL, 
    ultima_comunicacion TIMESTAMP WITH TIME ZONE, 
    ultimo_mantenimiento TIMESTAMP WITH TIME ZONE, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_atms PRIMARY KEY (id), 
    CONSTRAINT ck_atms_cash_capacity CHECK (capacidad_efectivo > 0), 
    CONSTRAINT ck_atms_coordinates CHECK (latitud BETWEEN -90 AND 90 AND longitud BETWEEN -180 AND 180), 
    CONSTRAINT ck_atms_cash_percentage CHECK (nivel_efectivo_pct BETWEEN 0 AND 100), 
    CONSTRAINT fk_atms_provincia_provincias FOREIGN KEY(provincia) REFERENCES provincias (nombre) ON DELETE RESTRICT, 
    CONSTRAINT fk_atms_sucursal_id_sucursales FOREIGN KEY(sucursal_id) REFERENCES sucursales (id) ON DELETE RESTRICT
);

CREATE UNIQUE INDEX ix_atms_codigo_unico ON atms (codigo_unico);

CREATE INDEX ix_atms_estado ON atms (estado);

CREATE INDEX ix_atms_provincia ON atms (provincia);

CREATE INDEX ix_atms_sucursal_id ON atms (sucursal_id);

CREATE TABLE branch_financials (
    sucursal_id UUID NOT NULL, 
    fecha DATE NOT NULL, 
    depositos NUMERIC(20, 2) NOT NULL, 
    prestamos NUMERIC(20, 2) NOT NULL, 
    id UUID NOT NULL, 
    CONSTRAINT pk_branch_financials PRIMARY KEY (id), 
    CONSTRAINT ck_branch_financials_balances CHECK (depositos >= 0 AND prestamos >= 0), 
    CONSTRAINT fk_branch_financials_sucursal_id_sucursales FOREIGN KEY(sucursal_id) REFERENCES sucursales (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_branch_financials_sucursal_id UNIQUE (sucursal_id, fecha)
);

CREATE INDEX ix_branch_financials_fecha ON branch_financials (fecha);

CREATE INDEX ix_branch_financials_sucursal_id ON branch_financials (sucursal_id);

CREATE TABLE branch_readings (
    sucursal_id UUID NOT NULL, 
    hora TIMESTAMP WITH TIME ZONE NOT NULL, 
    visitantes INTEGER NOT NULL, 
    clientes_atendidos INTEGER NOT NULL, 
    clientes_dentro_sla INTEGER NOT NULL, 
    espera_total_segundos INTEGER NOT NULL, 
    cajeros_disponibles INTEGER NOT NULL, 
    cola_actual INTEGER NOT NULL, 
    segundos_cajero_disponibles INTEGER NOT NULL, 
    segundos_cajero_ocupados INTEGER NOT NULL, 
    id UUID NOT NULL, 
    CONSTRAINT pk_branch_readings PRIMARY KEY (id), 
    CONSTRAINT ck_branch_readings_wait_denominator CHECK (clientes_atendidos > 0 OR espera_total_segundos = 0), 
    CONSTRAINT ck_branch_readings_queue CHECK (espera_total_segundos >= 0 AND cajeros_disponibles >= 0 AND cola_actual >= 0), 
    CONSTRAINT ck_branch_readings_tellers CHECK (segundos_cajero_disponibles >= 0 AND segundos_cajero_ocupados BETWEEN 0 AND segundos_cajero_disponibles), 
    CONSTRAINT ck_branch_readings_customers CHECK (visitantes >= 0 AND clientes_atendidos >= 0 AND clientes_dentro_sla BETWEEN 0 AND clientes_atendidos), 
    CONSTRAINT fk_branch_readings_sucursal_id_sucursales FOREIGN KEY(sucursal_id) REFERENCES sucursales (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_branch_readings_sucursal_id UNIQUE (sucursal_id, hora)
);

CREATE INDEX ix_branch_readings_hora ON branch_readings (hora);

CREATE INDEX ix_branch_readings_sucursal_id ON branch_readings (sucursal_id);

CREATE TABLE atm_readings (
    atm_id UUID NOT NULL, 
    hora TIMESTAMP WITH TIME ZONE NOT NULL, 
    transacciones INTEGER NOT NULL, 
    transacciones_exitosas INTEGER NOT NULL, 
    monto_retirado NUMERIC(18, 2) NOT NULL, 
    nivel_efectivo_pct FLOAT NOT NULL, 
    segundos_observados INTEGER NOT NULL, 
    segundos_disponible INTEGER NOT NULL, 
    segundos_utilizado INTEGER NOT NULL, 
    id UUID NOT NULL, 
    CONSTRAINT pk_atm_readings PRIMARY KEY (id), 
    CONSTRAINT ck_atm_readings_cash CHECK (nivel_efectivo_pct BETWEEN 0 AND 100), 
    CONSTRAINT ck_atm_readings_time_counters CHECK (segundos_observados BETWEEN 1 AND 3600 AND segundos_disponible BETWEEN 0 AND segundos_observados AND segundos_utilizado BETWEEN 0 AND segundos_disponible), 
    CONSTRAINT ck_atm_readings_transactions CHECK (transacciones >= 0 AND transacciones_exitosas BETWEEN 0 AND transacciones AND monto_retirado >= 0), 
    CONSTRAINT fk_atm_readings_atm_id_atms FOREIGN KEY(atm_id) REFERENCES atms (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_atm_readings_atm_id UNIQUE (atm_id, hora)
);

CREATE INDEX ix_atm_readings_atm_id ON atm_readings (atm_id);

CREATE INDEX ix_atm_readings_hora ON atm_readings (hora);

CREATE TYPE severity AS ENUM ('BAJA', 'MEDIA', 'ALTA', 'CRITICA');

CREATE TYPE incident_status AS ENUM ('ABIERTA', 'EN_PROCESO', 'RESUELTA', 'CANCELADA');

CREATE TABLE incidencias (
    atm_id UUID, 
    sucursal_id UUID, 
    tipo_falla VARCHAR(150) NOT NULL, 
    severidad severity NOT NULL, 
    estado incident_status NOT NULL, 
    descripcion TEXT NOT NULL, 
    resolucion TEXT, 
    creado_por_id UUID NOT NULL, 
    asignado_a_id UUID, 
    fecha_apertura TIMESTAMP WITH TIME ZONE NOT NULL, 
    fecha_cierre TIMESTAMP WITH TIME ZONE, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_incidencias PRIMARY KEY (id), 
    CONSTRAINT ck_incidencias_closure_state CHECK ((estado IN ('ABIERTA','EN_PROCESO') AND fecha_cierre IS NULL) OR (estado IN ('RESUELTA','CANCELADA') AND fecha_cierre IS NOT NULL AND resolucion IS NOT NULL)), 
    CONSTRAINT ck_incidencias_exactly_one_target CHECK ((atm_id IS NOT NULL AND sucursal_id IS NULL) OR (atm_id IS NULL AND sucursal_id IS NOT NULL)), 
    CONSTRAINT ck_incidencias_closure_time CHECK (fecha_cierre >= fecha_apertura), 
    CONSTRAINT fk_incidencias_asignado_a_id_users FOREIGN KEY(asignado_a_id) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_incidencias_atm_id_atms FOREIGN KEY(atm_id) REFERENCES atms (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_incidencias_creado_por_id_users FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_incidencias_sucursal_id_sucursales FOREIGN KEY(sucursal_id) REFERENCES sucursales (id) ON DELETE RESTRICT
);

CREATE INDEX ix_incidencias_atm_id ON incidencias (atm_id);

CREATE INDEX ix_incidencias_estado ON incidencias (estado);

CREATE INDEX ix_incidencias_fecha_apertura ON incidencias (fecha_apertura);

CREATE INDEX ix_incidencias_sucursal_id ON incidencias (sucursal_id);

CREATE TYPE refill_status AS ENUM ('PROGRAMADA', 'EN_TRANSITO', 'COMPLETADA', 'CANCELADA');

CREATE TABLE logistica_recargas (
    atm_id UUID NOT NULL, 
    monto_solicitado NUMERIC(18, 2) NOT NULL, 
    monto_entregado NUMERIC(18, 2), 
    transportadora VARCHAR(150) NOT NULL, 
    referencia VARCHAR(80) NOT NULL, 
    estado refill_status NOT NULL, 
    fecha_programada TIMESTAMP WITH TIME ZONE NOT NULL, 
    fecha_ejecucion TIMESTAMP WITH TIME ZONE, 
    notas TEXT, 
    creado_por_id UUID NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_logistica_recargas PRIMARY KEY (id), 
    CONSTRAINT ck_logistica_recargas_execution_state CHECK ((estado = 'COMPLETADA' AND fecha_ejecucion IS NOT NULL AND monto_entregado IS NOT NULL) OR (estado != 'COMPLETADA' AND fecha_ejecucion IS NULL AND monto_entregado IS NULL)), 
    CONSTRAINT ck_logistica_recargas_positive_amount CHECK (monto_solicitado > 0 AND (monto_entregado IS NULL OR monto_entregado > 0)), 
    CONSTRAINT fk_logistica_recargas_atm_id_atms FOREIGN KEY(atm_id) REFERENCES atms (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_logistica_recargas_creado_por_id_users FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_logistica_recargas_referencia UNIQUE (referencia)
);

CREATE INDEX ix_logistica_recargas_atm_id ON logistica_recargas (atm_id);

CREATE INDEX ix_logistica_recargas_estado ON logistica_recargas (estado);

CREATE INDEX ix_logistica_recargas_fecha_programada ON logistica_recargas (fecha_programada);

INSERT INTO alembic_version (version_num) VALUES ('0001_core') RETURNING alembic_version.version_num;

COMMIT;

