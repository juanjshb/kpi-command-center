from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any, Generic, TypeVar
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    model_validator,
)

from app.db.base import utcnow
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


def aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("La fecha debe incluir zona horaria")
    return value.astimezone(UTC)


def hourly(value: datetime) -> datetime:
    value = aware(value)
    if value.minute or value.second or value.microsecond:
        raise ValueError("hora debe ser el inicio exacto de una hora")
    if value + timedelta(hours=1) > utcnow():
        raise ValueError("Solo se aceptan horas completadas")
    return value


def bcrypt_password(value: str) -> str:
    if len(value.encode("utf-8")) > 72:
        raise ValueError("Bcrypt admite hasta 72 bytes UTF-8")
    return value


AwareTime = Annotated[datetime, AfterValidator(aware)]
Hour = Annotated[datetime, AfterValidator(hourly)]
Password = Annotated[
    str,
    StringConstraints(strip_whitespace=False, min_length=12, max_length=72),
    AfterValidator(bcrypt_password),
]
Name = Annotated[str, Field(min_length=1, max_length=150)]
Code = Annotated[str, Field(min_length=1, max_length=40)]
ProvinceName = Annotated[str, Field(min_length=1, max_length=100)]
Money = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=2)]
PositiveMoney = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=2)]
Pct = Annotated[float, Field(ge=0, le=100)]
Lat = Annotated[float, Field(ge=-90, le=90)]
Lng = Annotated[float, Field(ge=-180, le=180)]


class Schema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True, extra="forbid", str_strip_whitespace=True, allow_inf_nan=False
    )


class Patch(Schema):
    @model_validator(mode="after")
    def not_empty_or_null(self):
        if not self.model_fields_set:
            raise ValueError("Debe enviar al menos un campo")
        if any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError("No se permiten campos nulos en esta actualización")
        return self


T = TypeVar("T")


class Page(Schema, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class Identified(Schema):
    id: UUID


class UserCreate(Schema):
    email: EmailStr
    full_name: Name
    password: Password = Field(json_schema_extra={"writeOnly": True})
    role: Role = Role.ANALYST


class UserOut(Identified):
    email: EmailStr
    full_name: str
    role: Role
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserPatch(Patch):
    full_name: Name | None = None
    role: Role | None = None
    is_active: bool | None = None


class PasswordChange(Schema):
    current_password: Annotated[str, StringConstraints(strip_whitespace=False)] = Field(
        min_length=1, max_length=72, json_schema_extra={"writeOnly": True}
    )
    new_password: Password = Field(json_schema_extra={"writeOnly": True})


class Token(Schema):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class ProvinceCreate(Schema):
    nombre: ProvinceName
    region: ProvinceName
    poblacion: int | None = Field(default=None, ge=0)
    superficie_km2: float | None = Field(default=None, gt=0)
    fuente: str | None = Field(default=None, max_length=255)


class ProvinceOut(ProvinceCreate, Identified):
    pass


class BranchCreate(Schema):
    codigo: Code
    nombre: Name
    provincia: ProvinceName
    municipio: ProvinceName
    direccion: str = Field(min_length=1, max_length=1000)
    latitud: Lat
    longitud: Lng
    estado: BranchStatus = BranchStatus.OPERATIVA
    total_cajeros_humanos: int = Field(default=6, ge=0, le=1000)
    sla_objetivo_segundos: int = Field(default=600, gt=0, le=86400)


class BranchOut(BranchCreate, Identified):
    fuente: str | None
    fuente_id: str | None
    telefono: str | None
    zona: str | None
    horario_extendido: bool | None
    servicios: str | None
    horario: list[dict[str, Any]] | None
    actualizado_fuente_en: datetime | None
    created_at: datetime
    updated_at: datetime


class BranchPatch(Patch):
    nombre: Name | None = None
    direccion: str | None = Field(default=None, min_length=1, max_length=1000)
    estado: BranchStatus | None = None
    total_cajeros_humanos: int | None = Field(default=None, ge=0, le=1000)
    sla_objetivo_segundos: int | None = Field(default=None, gt=0, le=86400)


class ATMCreate(Schema):
    codigo_unico: Code
    sucursal_id: UUID | None = None
    nombre: Name
    provincia: ProvinceName
    municipio: ProvinceName
    direccion: str = Field(min_length=1, max_length=1000)
    tipo: ATMType
    nivel_efectivo_pct: Pct = 100
    capacidad_efectivo: PositiveMoney = Decimal("1000000.00")
    estado: ATMStatus = ATMStatus.OPERATIVO
    latitud: Lat
    longitud: Lng


class ATMOut(ATMCreate, Identified):
    fuente: str | None
    fuente_id: str | None
    telefono: str | None
    zona: str | None
    horario_extendido: bool | None
    servicios: str | None
    horario: list[dict[str, Any]] | None
    actualizado_fuente_en: datetime | None
    ultima_comunicacion: datetime | None
    ultimo_mantenimiento: datetime | None
    created_at: datetime
    updated_at: datetime


class SubagentCreate(Schema):
    codigo_unico: Code
    nombre: Name
    provincia: ProvinceName | None = None
    municipio: ProvinceName | None = None
    direccion: str = Field(min_length=1, max_length=1000)
    telefono: str | None = Field(default=None, max_length=80)
    zona: str | None = Field(default=None, max_length=100)
    latitud: Lat | None = None
    longitud: Lng | None = None
    horario_extendido: bool | None = None
    servicios: str | None = Field(default=None, max_length=10000)
    horario: list[dict[str, Any]] | None = None
    activo: bool = True

    @model_validator(mode="after")
    def coordinate_pair(self):
        if (self.latitud is None) != (self.longitud is None):
            raise ValueError("latitud y longitud deben enviarse juntas")
        return self


class SubagentOut(SubagentCreate, Identified):
    fuente: str
    fuente_id: str
    actualizado_fuente_en: datetime | None
    created_at: datetime
    updated_at: datetime


class SubagentPatch(Patch):
    nombre: Name | None = None
    provincia: ProvinceName | None = None
    municipio: ProvinceName | None = None
    direccion: str | None = Field(default=None, min_length=1, max_length=1000)
    telefono: str | None = Field(default=None, max_length=80)
    zona: str | None = Field(default=None, max_length=100)
    latitud: Lat | None = None
    longitud: Lng | None = None
    horario_extendido: bool | None = None
    servicios: str | None = Field(default=None, max_length=10000)
    horario: list[dict[str, Any]] | None = None
    activo: bool | None = None


class SubagentSummary(Schema):
    total: int
    activos: int
    con_coordenadas: int
    sin_coordenadas: int
    horario_extendido: int
    provincias: int
    ultima_actualizacion_fuente: datetime | None


class JobRunOut(Identified):
    job_key: str
    status: JobRunStatus
    requested_by_id: UUID | None
    started_at: datetime | None
    finished_at: datetime | None
    progress_current: int
    progress_total: int | None
    message: str | None
    result: dict[str, Any] | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class ATMStatusPatch(Patch):
    estado: ATMStatus | None = None
    nivel_efectivo_pct: Pct | None = None
    ultimo_mantenimiento: AwareTime | None = None

    @model_validator(mode="after")
    def past_maintenance(self):
        if self.ultimo_mantenimiento and self.ultimo_mantenimiento > utcnow():
            raise ValueError("El último mantenimiento no puede estar en el futuro")
        return self


class Heartbeat(Schema):
    estado: ATMStatus
    nivel_efectivo_pct: Pct


class IncidentCreate(Schema):
    atm_id: UUID | None = None
    sucursal_id: UUID | None = None
    tipo_falla: Name
    severidad: Severity
    descripcion: str = Field(min_length=1, max_length=10000)
    asignado_a_id: UUID | None = None

    @model_validator(mode="after")
    def one_target(self):
        if (self.atm_id is None) == (self.sucursal_id is None):
            raise ValueError("Indique exactamente uno de atm_id o sucursal_id")
        return self


class IncidentOut(IncidentCreate, Identified):
    estado: IncidentStatus
    resolucion: str | None
    creado_por_id: UUID
    fecha_apertura: datetime
    fecha_cierre: datetime | None


class IncidentAssign(Schema):
    asignado_a_id: UUID


class IncidentClose(Schema):
    resolucion: str = Field(min_length=1, max_length=10000)
    estado: IncidentStatus = IncidentStatus.RESUELTA

    @model_validator(mode="after")
    def terminal(self):
        if self.estado not in (IncidentStatus.RESUELTA, IncidentStatus.CANCELADA):
            raise ValueError("El cierre requiere RESUELTA o CANCELADA")
        return self


class RefillCreate(Schema):
    atm_id: UUID
    monto_solicitado: PositiveMoney
    transportadora: Name
    referencia: str = Field(min_length=1, max_length=80)
    fecha_programada: AwareTime
    notas: str | None = Field(default=None, max_length=5000)


class RefillOut(RefillCreate, Identified):
    monto_entregado: Decimal | None
    estado: RefillStatus
    fecha_ejecucion: datetime | None
    creado_por_id: UUID


class RefillUpdate(Schema):
    estado: RefillStatus
    monto_entregado: PositiveMoney | None = None
    nivel_efectivo_pct: Pct | None = None

    @model_validator(mode="after")
    def completion(self):
        complete = self.estado == RefillStatus.COMPLETADA
        if complete and (self.monto_entregado is None or self.nivel_efectivo_pct is None):
            raise ValueError("Complete con monto_entregado y nivel_efectivo_pct medido")
        if not complete and (
            self.monto_entregado is not None or self.nivel_efectivo_pct is not None
        ):
            raise ValueError("Los importes de ejecución solo se aceptan al completar")
        return self


class ATMReadingCreate(Schema):
    hora: Hour
    transacciones: int = Field(ge=0, le=2147483647)
    transacciones_exitosas: int = Field(ge=0)
    monto_retirado: Money
    nivel_efectivo_pct: Pct
    segundos_observados: int = Field(ge=1, le=3600)
    segundos_disponible: int = Field(ge=0, le=3600)
    segundos_utilizado: int = Field(ge=0, le=3600)

    @model_validator(mode="after")
    def counters(self):
        if not self.segundos_utilizado <= self.segundos_disponible <= self.segundos_observados:
            raise ValueError("Contadores temporales inconsistentes")
        if self.transacciones_exitosas > self.transacciones:
            raise ValueError("Éxitos superiores al total de transacciones")
        return self


class ATMReadingOut(ATMReadingCreate, Identified):
    atm_id: UUID


class BranchReadingCreate(Schema):
    hora: Hour
    visitantes: int = Field(ge=0, le=1000000)
    clientes_atendidos: int = Field(ge=0, le=1000000)
    clientes_dentro_sla: int = Field(ge=0, le=1000000)
    espera_total_segundos: int = Field(ge=0, le=2147483647)
    cajeros_disponibles: int = Field(ge=0, le=1000)
    cola_actual: int = Field(ge=0, le=1000000)
    segundos_cajero_disponibles: int = Field(ge=0, le=3600000)
    segundos_cajero_ocupados: int = Field(ge=0, le=3600000)

    @model_validator(mode="after")
    def counters(self):
        if self.clientes_dentro_sla > self.clientes_atendidos:
            raise ValueError("Clientes SLA superiores a los atendidos")
        if self.segundos_cajero_ocupados > self.segundos_cajero_disponibles:
            raise ValueError("Ocupación superior al tiempo disponible")
        if self.clientes_atendidos == 0 and self.espera_total_segundos:
            raise ValueError("La espera agregada requiere clientes atendidos")
        return self


class BranchReadingOut(BranchReadingCreate, Identified):
    sucursal_id: UUID


class FinancialCreate(Schema):
    fecha: date
    depositos: Money
    prestamos: Money


class FinancialOut(FinancialCreate, Identified):
    sucursal_id: UUID


class InstitutionCreate(Schema):
    nombre: Name
    es_propia: bool = False
    color: str = Field(default="#808080", pattern=r"^#[0-9A-Fa-f]{6}$")


class InstitutionOut(InstitutionCreate, Identified):
    pass


class CompetitorCreate(Schema):
    institucion_id: UUID
    codigo: str = Field(min_length=1, max_length=80)
    nombre: Name
    provincia: ProvinceName
    tipo: LocationType
    latitud: Lat
    longitud: Lng
    fuente: str = Field(min_length=1, max_length=255)
    fecha_verificacion: date


class CompetitorOut(CompetitorCreate, Identified):
    pass


class MarketCreate(Schema):
    institucion_id: UUID
    provincia: ProvinceName
    fecha: date
    total_atms: int = Field(ge=0, le=2147483647)
    total_sucursales: int = Field(ge=0, le=2147483647)
    depositos: Money
    prestamos: Money
    transacciones: int = Field(ge=0, le=2147483647)
    utilizacion_pct: Pct | None = None
    fuente: str = Field(min_length=1, max_length=255)


class MarketOut(MarketCreate, Identified):
    pass


class CandidateCreate(Schema):
    codigo: Code
    nombre: Name
    provincia: ProvinceName
    municipio: ProvinceName
    tipo: LocationType
    latitud: Lat
    longitud: Lng
    potencial_mercado: Pct
    densidad_poblacional: float = Field(ge=0)
    estado: CandidateStatus = CandidateStatus.PROPUESTA
    fuente: str = Field(min_length=1, max_length=255)
    notas: str | None = Field(default=None, max_length=5000)


class CandidateOut(CandidateCreate, Identified):
    pass


class CandidatePatch(Patch):
    estado: CandidateStatus | None = None
    potencial_mercado: Pct | None = None
    notas: str | None = Field(default=None, min_length=1, max_length=5000)


class AuditOut(Identified):
    actor_id: UUID | None
    accion: str
    entidad: str
    entidad_id: UUID | None
    cambios: dict
    fecha: datetime
