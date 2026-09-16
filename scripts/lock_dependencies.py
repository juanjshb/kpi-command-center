"""Exporta las dependencias instaladas a locks portables, sin el paquete editable local."""

from importlib.metadata import distribution
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def resolve(root_extras):
    pending = [("kpi-command-center", root_extras)]
    visited, versions = set(), {}
    while pending:
        name, extras = pending.pop()
        key = (canonicalize_name(name), tuple(sorted(extras)))
        if key in visited:
            continue
        visited.add(key)
        dist = distribution(name)
        if canonicalize_name(name) != "kpi-command-center":
            versions[canonicalize_name(name)] = dist.version
        for raw in dist.requires or []:
            req = Requirement(raw)
            # Unión Linux/Windows; uvloop se omite porque es una optimización opcional.
            if req.name == "uvloop":
                continue
            supported = False
            for platform, system, os_name in [
                ("win32", "Windows", "nt"),
                ("linux", "Linux", "posix"),
            ]:
                env = {
                    **default_environment(),
                    "sys_platform": platform,
                    "platform_system": system,
                    "os_name": os_name,
                }
                supported |= any(
                    req.marker is None or req.marker.evaluate({**env, "extra": extra})
                    for extra in (extras or {""})
                )
            if supported:
                pending.append((req.name, req.extras))
    return versions


for filename, extras in [("requirements.lock", set()), ("requirements-dev.lock", {"dev"})]:
    versions = resolve(extras)
    Path(filename).write_text(
        "# Generado por scripts/lock_dependencies.py\n"
        + "".join(f"{name}=={version}\n" for name, version in sorted(versions.items())),
        encoding="utf-8",
    )
