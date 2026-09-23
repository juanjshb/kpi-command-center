from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin, utcnow
from app.models.enums import (
    ATMStatus,
    ATMType,
    BranchStatus,
    CandidateStatus,
    IncidentStatus,
    JobRunStatus,
    LocationType,
    RefillStatus,
    Role,
    Severity,
)


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(150))
    role: Mapped[Role] = mapped_column(Enum(Role, name="user_role"), default=Role.ANALYST)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("email = lower(email)", name="normalized_email"),)


class Provincia(UUIDMixin, Base):
    __tablename__ = "provincias"
    nombre: Mapped[str] = mapped_column(String(100), unique=True)
    region: Mapped[str] = mapped_column(String(100), index=True)
    poblacion: Mapped[int | None] = mapped_column(Integer)
    superficie_km2: Mapped[float | None] = mapped_column(Float)
    fuente: Mapped[str | None] = mapped_column(String(255))
    __table_args__ = (
        CheckConstraint("poblacion >= 0", name="population"),
        CheckConstraint("superficie_km2 > 0", name="area"),
    )


class Sucursal(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "sucursales"
    codigo: Mapped[str] = mapped_column(String(40), unique=True)
    nombre: Mapped[str] = mapped_column(String(150))
    provincia: Mapped[str] = mapped_column(
        ForeignKey("provincias.nombre", ondelete="RESTRICT"), index=True
    )
    municipio: Mapped[str] = mapped_column(String(100))
    direccion: Mapped[str] = mapped_column(Text)
    latitud: Mapped[float] = mapped_column(Float)
    longitud: Mapped[float] = mapped_column(Float)
    estado: Mapped[BranchStatus] = mapped_column(
        Enum(BranchStatus, name="branch_status"), default=BranchStatus.OPERATIVA
    )
    total_cajeros_humanos: Mapped[int] = mapped_column(Integer, default=6)
    sla_objetivo_segundos: Mapped[int] = mapped_column(Integer, default=600)
    fuente: Mapped[str | None] = mapped_column(String(80))
    fuente_id: Mapped[str | None] = mapped_column(String(80))
    telefono: Mapped[str | None] = mapped_column(String(80))
    zona: Mapped[str | None] = mapped_column(String(100))
    horario_extendido: Mapped[bool | None] = mapped_column(Boolean)
    servicios: Mapped[str | None] = mapped_column(Text)
    horario: Mapped[list | None] = mapped_column(JSON)
    actualizado_fuente_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("fuente", "fuente_id"),
        CheckConstraint(
            "latitud BETWEEN -90 AND 90 AND longitud BETWEEN -180 AND 180", name="coordinates"
        ),
        CheckConstraint(
            "total_cajeros_humanos >= 0 AND sla_objetivo_segundos > 0", name="capacity_sla"
        ),
    )


class ATM(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "atms"
    codigo_unico: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    sucursal_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("sucursales.id", ondelete="RESTRICT"), index=True
    )
    nombre: Mapped[str] = mapped_column(String(150))
    provincia: Mapped[str] = mapped_column(
        ForeignKey("provincias.nombre", ondelete="RESTRICT"), index=True
    )
    municipio: Mapped[str] = mapped_column(String(100))
    direccion: Mapped[str] = mapped_column(Text)
    tipo: Mapped[ATMType] = mapped_column(Enum(ATMType, name="atm_type"))
    nivel_efectivo_pct: Mapped[float] = mapped_column(Float, default=100)
    capacidad_efectivo: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=1000000)
    estado: Mapped[ATMStatus] = mapped_column(
        Enum(ATMStatus, name="atm_status"), default=ATMStatus.OPERATIVO, index=True
    )
    latitud: Mapped[float] = mapped_column(Float)
    longitud: Mapped[float] = mapped_column(Float)
    ultima_comunicacion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ultimo_mantenimiento: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fuente: Mapped[str | None] = mapped_column(String(80))
    fuente_id: Mapped[str | None] = mapped_column(String(80))
    telefono: Mapped[str | None] = mapped_column(String(80))
    zona: Mapped[str | None] = mapped_column(String(100))
    horario_extendido: Mapped[bool | None] = mapped_column(Boolean)
    servicios: Mapped[str | None] = mapped_column(Text)
    horario: Mapped[list | None] = mapped_column(JSON)
    actualizado_fuente_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("fuente", "fuente_id"),
        CheckConstraint("nivel_efectivo_pct BETWEEN 0 AND 100", name="cash_percentage"),
        CheckConstraint("capacidad_efectivo > 0", name="cash_capacity"),
        CheckConstraint(
            "latitud BETWEEN -90 AND 90 AND longitud BETWEEN -180 AND 180", name="coordinates"
        ),
    )


class Subagente(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "subagentes"
    codigo_unico: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String(150))
    provincia: Mapped[str | None] = mapped_column(
        ForeignKey("provincias.nombre", ondelete="RESTRICT"), index=True
    )
    municipio: Mapped[str | None] = mapped_column(String(100))
    direccion: Mapped[str] = mapped_column(Text)
    telefono: Mapped[str | None] = mapped_column(String(80))
    zona: Mapped[str | None] = mapped_column(String(100))
    latitud: Mapped[float | None] = mapped_column(Float)
    longitud: Mapped[float | None] = mapped_column(Float)
    horario_extendido: Mapped[bool | None] = mapped_column(Boolean)
    servicios: Mapped[str | None] = mapped_column(Text)
    horario: Mapped[list | None] = mapped_column(JSON)
    fuente: Mapped[str] = mapped_column(String(80))
    fuente_id: Mapped[str] = mapped_column(String(80))
    actualizado_fuente_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    __table_args__ = (
        UniqueConstraint("fuente", "fuente_id"),
        CheckConstraint(
            "(latitud IS NULL AND longitud IS NULL) OR "
            "(latitud BETWEEN -90 AND 90 AND longitud BETWEEN -180 AND 180)",
            name="coordinates",
        ),
    )


class JobRun(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "job_runs"
    job_key: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[JobRunStatus] = mapped_column(
        Enum(JobRunStatus, name="job_run_status"),
        default=JobRunStatus.PENDING,
        server_default=JobRunStatus.PENDING.value,
        index=True,
    )
    requested_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    progress_current: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    progress_total: Mapped[int | None] = mapped_column(Integer)
    message: Mapped[str | None] = mapped_column(String(255))
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        Index(
            "uq_job_runs_active_key",
            "job_key",
            unique=True,
            postgresql_where=text("status IN ('PENDING','RUNNING')"),
        ),
        CheckConstraint(
            "progress_current >= 0 AND (progress_total IS NULL OR progress_total >= progress_current)",
            name="progress",
        ),
        CheckConstraint(
            "(status IN ('PENDING','RUNNING') AND finished_at IS NULL) OR "
            "(status IN ('SUCCEEDED','FAILED') AND finished_at IS NOT NULL)",
            name="lifecycle",
        ),
    )


class Incidencia(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "incidencias"
    atm_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("atms.id", ondelete="RESTRICT"), index=True
    )
    sucursal_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("sucursales.id", ondelete="RESTRICT"), index=True
    )
    tipo_falla: Mapped[str] = mapped_column(String(150))
    severidad: Mapped[Severity] = mapped_column(Enum(Severity, name="severity"))
    estado: Mapped[IncidentStatus] = mapped_column(
        Enum(IncidentStatus, name="incident_status"), default=IncidentStatus.ABIERTA, index=True
    )
    descripcion: Mapped[str] = mapped_column(Text)
    resolucion: Mapped[str | None] = mapped_column(Text)
    creado_por_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    asignado_a_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    fecha_apertura: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    fecha_cierre: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint(
            "(atm_id IS NOT NULL AND sucursal_id IS NULL) OR (atm_id IS NULL AND sucursal_id IS NOT NULL)",
            name="exactly_one_target",
        ),
        CheckConstraint(
            "(estado IN ('ABIERTA','EN_PROCESO') AND fecha_cierre IS NULL) OR (estado IN ('RESUELTA','CANCELADA') AND fecha_cierre IS NOT NULL AND resolucion IS NOT NULL)",
            name="closure_state",
        ),
        CheckConstraint("fecha_cierre >= fecha_apertura", name="closure_time"),
    )


class LogisticaRecarga(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "logistica_recargas"
    atm_id: Mapped[UUID] = mapped_column(ForeignKey("atms.id", ondelete="RESTRICT"), index=True)
    monto_solicitado: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    monto_entregado: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    transportadora: Mapped[str] = mapped_column(String(150))
    referencia: Mapped[str] = mapped_column(String(80), unique=True)
    estado: Mapped[RefillStatus] = mapped_column(
        Enum(RefillStatus, name="refill_status"), default=RefillStatus.PROGRAMADA, index=True
    )
    fecha_programada: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    fecha_ejecucion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notas: Mapped[str | None] = mapped_column(Text)
    creado_por_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    __table_args__ = (
        CheckConstraint(
            "monto_solicitado > 0 AND (monto_entregado IS NULL OR monto_entregado > 0)",
            name="positive_amount",
        ),
        CheckConstraint(
            "(estado = 'COMPLETADA' AND fecha_ejecucion IS NOT NULL AND monto_entregado IS NOT NULL) OR (estado != 'COMPLETADA' AND fecha_ejecucion IS NULL AND monto_entregado IS NULL)",
            name="execution_state",
        ),
    )


class ATMReading(UUIDMixin, Base):
    __tablename__ = "atm_readings"
    atm_id: Mapped[UUID] = mapped_column(ForeignKey("atms.id", ondelete="RESTRICT"), index=True)
    hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    transacciones: Mapped[int] = mapped_column(Integer)
    transacciones_exitosas: Mapped[int] = mapped_column(Integer)
    monto_retirado: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    nivel_efectivo_pct: Mapped[float] = mapped_column(Float)
    segundos_observados: Mapped[int] = mapped_column(Integer)
    segundos_disponible: Mapped[int] = mapped_column(Integer)
    segundos_utilizado: Mapped[int] = mapped_column(Integer)
    __table_args__ = (
        UniqueConstraint("atm_id", "hora"),
        CheckConstraint(
            "transacciones >= 0 AND transacciones_exitosas BETWEEN 0 AND transacciones AND monto_retirado >= 0",
            name="transactions",
        ),
        CheckConstraint("nivel_efectivo_pct BETWEEN 0 AND 100", name="cash"),
        CheckConstraint(
            "segundos_observados BETWEEN 1 AND 3600 AND segundos_disponible BETWEEN 0 AND segundos_observados AND segundos_utilizado BETWEEN 0 AND segundos_disponible",
            name="time_counters",
        ),
    )


class BranchReading(UUIDMixin, Base):
    __tablename__ = "branch_readings"
    sucursal_id: Mapped[UUID] = mapped_column(
        ForeignKey("sucursales.id", ondelete="RESTRICT"), index=True
    )
    hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    visitantes: Mapped[int] = mapped_column(Integer)
    clientes_atendidos: Mapped[int] = mapped_column(Integer)
    clientes_dentro_sla: Mapped[int] = mapped_column(Integer)
    espera_total_segundos: Mapped[int] = mapped_column(Integer)
    cajeros_disponibles: Mapped[int] = mapped_column(Integer)
    cola_actual: Mapped[int] = mapped_column(Integer)
    segundos_cajero_disponibles: Mapped[int] = mapped_column(Integer)
    segundos_cajero_ocupados: Mapped[int] = mapped_column(Integer)
    __table_args__ = (
        UniqueConstraint("sucursal_id", "hora"),
        CheckConstraint(
            "visitantes >= 0 AND clientes_atendidos >= 0 AND clientes_dentro_sla BETWEEN 0 AND clientes_atendidos",
            name="customers",
        ),
        CheckConstraint(
            "espera_total_segundos >= 0 AND cajeros_disponibles >= 0 AND cola_actual >= 0",
            name="queue",
        ),
        CheckConstraint(
            "segundos_cajero_disponibles >= 0 AND segundos_cajero_ocupados BETWEEN 0 AND segundos_cajero_disponibles",
            name="tellers",
        ),
        CheckConstraint(
            "clientes_atendidos > 0 OR espera_total_segundos = 0", name="wait_denominator"
        ),
    )


class BranchFinancial(UUIDMixin, Base):
    __tablename__ = "branch_financials"
    sucursal_id: Mapped[UUID] = mapped_column(
        ForeignKey("sucursales.id", ondelete="RESTRICT"), index=True
    )
    fecha: Mapped[date] = mapped_column(Date, index=True)
    depositos: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    prestamos: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    __table_args__ = (
        UniqueConstraint("sucursal_id", "fecha"),
        CheckConstraint("depositos >= 0 AND prestamos >= 0", name="balances"),
    )


class Institution(UUIDMixin, Base):
    __tablename__ = "institutions"
    nombre: Mapped[str] = mapped_column(String(150), unique=True)
    es_propia: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    color: Mapped[str] = mapped_column(String(7), default="#808080")
    __table_args__ = (
        Index(
            "uq_institutions_own",
            "es_propia",
            unique=True,
            postgresql_where=text("es_propia = true"),
        ),
    )


class CompetitorLocation(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "competitor_locations"
    institucion_id: Mapped[UUID] = mapped_column(
        ForeignKey("institutions.id", ondelete="RESTRICT"), index=True
    )
    codigo: Mapped[str] = mapped_column(String(80))
    nombre: Mapped[str] = mapped_column(String(150))
    provincia: Mapped[str] = mapped_column(
        ForeignKey("provincias.nombre", ondelete="RESTRICT"), index=True
    )
    tipo: Mapped[LocationType] = mapped_column(Enum(LocationType, name="location_type"))
    latitud: Mapped[float] = mapped_column(Float)
    longitud: Mapped[float] = mapped_column(Float)
    fuente: Mapped[str] = mapped_column(String(255))
    fecha_verificacion: Mapped[date] = mapped_column(Date)
    __table_args__ = (
        UniqueConstraint("institucion_id", "codigo"),
        CheckConstraint(
            "latitud BETWEEN -90 AND 90 AND longitud BETWEEN -180 AND 180", name="coordinates"
        ),
    )


class MarketSnapshot(UUIDMixin, Base):
    __tablename__ = "market_snapshots"
    institucion_id: Mapped[UUID] = mapped_column(
        ForeignKey("institutions.id", ondelete="RESTRICT"), index=True
    )
    provincia: Mapped[str] = mapped_column(
        ForeignKey("provincias.nombre", ondelete="RESTRICT"), index=True
    )
    fecha: Mapped[date] = mapped_column(Date, index=True)
    total_atms: Mapped[int] = mapped_column(Integer)
    total_sucursales: Mapped[int] = mapped_column(Integer)
    depositos: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    prestamos: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    transacciones: Mapped[int] = mapped_column(Integer)
    utilizacion_pct: Mapped[float | None] = mapped_column(Float)
    fuente: Mapped[str] = mapped_column(String(255))
    __table_args__ = (
        UniqueConstraint("institucion_id", "provincia", "fecha"),
        CheckConstraint(
            "total_atms >= 0 AND total_sucursales >= 0 AND transacciones >= 0 AND depositos >= 0 AND prestamos >= 0",
            name="positive_metrics",
        ),
        CheckConstraint("utilizacion_pct BETWEEN 0 AND 100", name="utilization"),
    )


class CandidateLocation(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "candidate_locations"
    codigo: Mapped[str] = mapped_column(String(40), unique=True)
    nombre: Mapped[str] = mapped_column(String(150))
    provincia: Mapped[str] = mapped_column(
        ForeignKey("provincias.nombre", ondelete="RESTRICT"), index=True
    )
    municipio: Mapped[str] = mapped_column(String(100))
    tipo: Mapped[LocationType] = mapped_column(Enum(LocationType, name="location_type"))
    latitud: Mapped[float] = mapped_column(Float)
    longitud: Mapped[float] = mapped_column(Float)
    potencial_mercado: Mapped[float] = mapped_column(Float, index=True)
    densidad_poblacional: Mapped[float] = mapped_column(Float)
    estado: Mapped[CandidateStatus] = mapped_column(
        Enum(CandidateStatus, name="candidate_status"), default=CandidateStatus.PROPUESTA
    )
    fuente: Mapped[str] = mapped_column(String(255))
    notas: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        CheckConstraint(
            "potencial_mercado BETWEEN 0 AND 100 AND densidad_poblacional >= 0",
            name="score_density",
        ),
        CheckConstraint(
            "latitud BETWEEN -90 AND 90 AND longitud BETWEEN -180 AND 180", name="coordinates"
        ),
    )


class AuditLog(UUIDMixin, Base):
    __tablename__ = "audit_logs"
    actor_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    accion: Mapped[str] = mapped_column(String(60))
    entidad: Mapped[str] = mapped_column(String(80), index=True)
    entidad_id: Mapped[UUID | None]
    cambios: Mapped[dict] = mapped_column(JSON)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
