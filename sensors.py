"""Read live hardware stats from the system."""

import shutil
import subprocess
from pathlib import Path
import psutil

HWMON_ROOT = Path("/sys/class/hwmon")


def find_hwmon(chip_name: str) -> Path | None:
    """Find first hwmon dir by chip name (e.g. 'k10temp', 'nvme') instead of a fixed index."""
    matches = find_hwmon_all(chip_name)
    return matches[0] if matches else None


def find_hwmon_all(chip_name: str) -> list[Path]:
    """Find all hwmon dirs matching a chip name (some chips, like RAM DIMMs, appear more than once)."""
    matches = []
    for hwmon_dir in sorted(HWMON_ROOT.glob("hwmon*")):
        name_file = hwmon_dir / "name"
        if name_file.exists() and name_file.read_text().strip() == chip_name:
            matches.append(hwmon_dir)
    return matches


def find_temp_input(hwmon_dir: Path, label: str | None = None) -> Path | None:
    """Find temp*_input in a hwmon dir, optionally matching a specific label (e.g. 'Tctl')."""
    if label is None:
        candidates = sorted(hwmon_dir.glob("temp*_input"))
        return candidates[0] if candidates else None

    for label_file in sorted(hwmon_dir.glob("temp*_label")):
        if label_file.read_text().strip() == label:
            input_file = label_file.with_name(label_file.name.replace("_label", "_input"))
            if input_file.exists():
                return input_file
    return None


def get_resolution() -> tuple[int, int]:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gdk, Gtk

    Gtk.init()
    display = Gdk.Display.get_default()
    monitor = display.get_monitors().get_item(0)
    geo = monitor.get_geometry()
    return geo.width, geo.height


def find_cpu_hwmon() -> tuple[Path, str] | None:
    """Detect CPU vendor by checking for known hwmon chip names. Returns (hwmon_dir, chip_name)."""
    for chip_name in ("k10temp", "coretemp"):  # AMD, Intel
        hwmon = find_hwmon(chip_name)
        if hwmon is not None:
            return hwmon, chip_name
    return None


def get_cpu_temp() -> float:
    found = find_cpu_hwmon()
    if found is None:
        raise RuntimeError("No supported CPU temp sensor found (checked k10temp, coretemp)")
    hwmon, chip_name = found
    label = "Tctl" if chip_name == "k10temp" else "Package id 0"
    temp_file = find_temp_input(hwmon, label=label)
    if temp_file is None:
        temp_file = find_temp_input(hwmon)  # fallback: first temp input
    raw = temp_file.read_text().strip()
    return int(raw) / 1000.0


def get_cpu_load(interval: float = 0.15) -> list[float]:
    return psutil.cpu_percent(interval=interval, percpu=True)


def get_cpu_freq() -> float:
    return psutil.cpu_freq().current


def get_ram() -> tuple[float, float, float]:
    vm = psutil.virtual_memory()
    return vm.used / (1024**3), vm.total / (1024**3), vm.percent


def get_nvme_temp() -> float:
    hwmon = find_hwmon("nvme")
    if hwmon is None:
        raise RuntimeError("nvme sensor not found")
    temp_file = find_temp_input(hwmon, label="Composite")
    if temp_file is None:
        temp_file = find_temp_input(hwmon)  # fallback: first temp input
    raw = temp_file.read_text().strip()
    return int(raw) / 1000.0


def get_disk_usage(path: str = "/") -> tuple[float, float, float]:
    usage = shutil.disk_usage(path)
    used_gb = usage.used / (1024**3)
    total_gb = usage.total / (1024**3)
    pct = usage.used / usage.total * 100
    return used_gb, total_gb, pct


def get_gpu_stats() -> dict:
    if shutil.which("nvidia-smi") is not None:
        return _get_nvidia_gpu_stats()
    if shutil.which("rocm-smi") is not None:
        raise NotImplementedError(
            "AMD GPU detected (rocm-smi present) but parsing isn't implemented yet — "
            "couldn't verify rocm-smi's JSON output structure without real AMD GPU hardware to test against."
        )
    raise RuntimeError("No supported GPU monitoring tool found (checked nvidia-smi, rocm-smi)")


def _get_nvidia_gpu_stats() -> dict:
    result = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=temperature.gpu,power.draw,clocks.current.graphics,memory.used,memory.total,utilization.gpu",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    temp, power, clock, mem_used, mem_total, util = result.stdout.strip().split(", ")
    return {
        "temp": float(temp),
        "power_w": float(power),
        "clock_mhz": float(clock),
        "vram_used_mib": float(mem_used),
        "vram_total_mib": float(mem_total),
        "util_pct": float(util),
    }


def collect_all() -> dict:
    stats = {
        "cpu_temp": get_cpu_temp(),
        "cpu_freq": get_cpu_freq(),
        "cpu_load": get_cpu_load(),
        "nvme_temp": get_nvme_temp(),
        "gpu": get_gpu_stats(),
    }
    ram_used, ram_total, ram_pct = get_ram()
    stats["ram_used"], stats["ram_total"], stats["ram_pct"] = ram_used, ram_total, ram_pct

    disk_used, disk_total, disk_pct = get_disk_usage()
    stats["disk_used"], stats["disk_total"], stats["disk_pct"] = disk_used, disk_total, disk_pct

    return stats
