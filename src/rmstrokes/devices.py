"""Device presets: the one place canvas sizes and pixel densities are defined.

Values come from the manufacturer's published screen specs. Everything else (page layout, PDF page
size, .rm coordinates) is derived from these. Only the reMarkable 2 has been checked on hardware;
the Paper Pro and Paper Pro Move presets are marked ``verified=False`` until someone checks a
device-made file (see docs/format-notes.md).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Device:
    key: str
    name: str
    width: int  # portrait canvas, device pixels
    height: int
    dpi: int
    # Paper Pro writes its canvas size into the .rm SceneInfo block; rM2 files omit it.
    paper_size: tuple[int, int] | None
    color: bool = False  # colour e-ink (Gallery 3) panel
    verified: bool = False  # output checked on a real tablet of this model

    @property
    def pt_per_px(self) -> float:
        """PDF points per device pixel. 1 px = 72/dpi pt, the scale rmc uses, so PDF content and
        .rm strokes line up 1:1 (verified on an rM2; check on each new device)."""
        return 72.0 / self.dpi

    @property
    def page_size_pt(self) -> tuple[float, float]:
        return self.width * self.pt_per_px, self.height * self.pt_per_px

    def mm(self, millimetres: float) -> float:
        """Physical length -> device pixels."""
        return millimetres / 25.4 * self.dpi


DEVICES: dict[str, Device] = {
    "rm2": Device("rm2", "reMarkable 2", 1404, 1872, 226, None, verified=True),
    "pro": Device("pro", "reMarkable Paper Pro", 1620, 2160, 229, (1620, 2160), color=True),
    # Paper Pro Move: 7.3" 1696x954 @ 264 PPI. Whether the firmware writes
    # paper_size=(954, 1696) is unverified - check a device-made file.
    "move": Device("move", "reMarkable Paper Pro Move", 954, 1696, 264, (954, 1696), color=True),
}


# Names accepted on the command line besides the keys above.
ALIASES: dict[str, str] = {
    "remarkable-2": "rm2", "remarkable2": "rm2",
    "paper-pro": "pro", "paper-pro-move": "move",
}


def device_key(name: str) -> str:
    """Canonical key for a device key or alias ('paper-pro' -> 'pro')."""
    key = ALIASES.get(name.lower(), name.lower())
    if key not in DEVICES:
        names = ", ".join([*DEVICES, *ALIASES])
        raise ValueError(f"unknown device {name!r}; choose from {names}")
    return key


def get_device(key: str | Device) -> Device:
    return key if isinstance(key, Device) else DEVICES[device_key(key)]
