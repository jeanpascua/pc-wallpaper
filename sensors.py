"""Read live hardware stats from the system."""

import shutil
import subprocess
import time
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


def find_input_by_label(hwmon_dir: Path, kind: str, label: str) -> Path | None:
    """Find <kind><N>_input matching a label (e.g. kind='in', label='vddgfx')."""
    for label_file in sorted(hwmon_dir.glob(f"{kind}*_label")):
        if label_file.read_text().strip() == label:
            input_file = label_file.with_name(label_file.name.replace("_label", "_input"))
            if input_file.exists():
                return input_file
    return None


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


def get_cpu_temp() -> float:
    hwmon = find_hwmon("k10temp")
    if hwmon is None:
        raise RuntimeError("k10temp sensor not found")
    temp_file = find_temp_input(hwmon, label="Tctl")
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


def get_ram_dimm_temps() -> list[float]:
    temps = []
    for hwmon in find_hwmon_all("spd5118"):
        temp_file = find_temp_input(hwmon)
        if temp_file:
            temps.append(int(temp_file.read_text().strip()) / 1000.0)
    return temps


def get_wifi_temp() -> float | None:
    hwmon = find_hwmon("mt7921_phy0")
    if hwmon is None:
        return None
    temp_file = find_temp_input(hwmon)
    if temp_file is None:
        return None
    return int(temp_file.read_text().strip()) / 1000.0


def get_igpu_voltage() -> dict | None:
    hwmon = find_hwmon("amdgpu")
    if hwmon is None:
        return None
    vddgfx_file = find_input_by_label(hwmon, "in", "vddgfx")
    vddnb_file = find_input_by_label(hwmon, "in", "vddnb")
    if vddgfx_file is None or vddnb_file is None:
        return None
    return {
        "vddgfx": int(vddgfx_file.read_text().strip()) / 1000.0,
        "vddnb": int(vddnb_file.read_text().strip()) / 1000.0,
    }


def get_igpu_stats() -> dict | None:
    """7700X's built-in Radeon graphics — separate from the RTX 3090."""
    hwmon = find_hwmon("amdgpu")
    if hwmon is None:
        return None
    temp_file = find_input_by_label(hwmon, "temp", "edge")
    power_file = find_input_by_label(hwmon, "power", "PPT")
    freq_file = find_input_by_label(hwmon, "freq", "sclk")
    if not (temp_file and power_file and freq_file):
        return None
    return {
        "temp": int(temp_file.read_text().strip()) / 1000.0,
        "power_w": int(power_file.read_text().strip()) / 1_000_000.0,
        "clock_mhz": int(freq_file.read_text().strip()) / 1_000_000.0,
    }


def get_cpu_chiplet_temp() -> float | None:
    hwmon = find_hwmon("k10temp")
    if hwmon is None:
        return None
    temp_file = find_temp_input(hwmon, label="Tccd1")
    if temp_file is None:
        return None
    return int(temp_file.read_text().strip()) / 1000.0


def get_nvme_sensor_temps() -> dict:
    hwmon = find_hwmon("nvme")
    if hwmon is None:
        return {}
    result = {}
    for label in ("Sensor 1", "Sensor 2"):
        temp_file = find_temp_input(hwmon, label=label)
        if temp_file:
            result[label] = int(temp_file.read_text().strip()) / 1000.0
    return result


def get_disk_usage(path: str = "/") -> tuple[float, float, float]:
    usage = shutil.disk_usage(path)
    used_gb = usage.used / (1024**3)
    total_gb = usage.total / (1024**3)
    pct = usage.used / usage.total * 100
    return used_gb, total_gb, pct


def get_network_snapshot() -> tuple[float, int, int]:
    """(timestamp, cumulative bytes_sent, cumulative bytes_recv)."""
    counters = psutil.net_io_counters()
    return time.monotonic(), counters.bytes_sent, counters.bytes_recv


def compute_network_rate(prev: tuple[float, int, int], curr: tuple[float, int, int]) -> tuple[float, float]:
    """Returns (up_mbps, down_mbps) from two snapshots."""
    t0, s0, r0 = prev
    t1, s1, r1 = curr
    dt = max(t1 - t0, 0.001)
    up_mbps = (s1 - s0) * 8 / dt / 1_000_000
    down_mbps = (r1 - r0) * 8 / dt / 1_000_000
    return up_mbps, down_mbps


def get_gpu_stats() -> dict:
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


def collect_all(prev_net: tuple[float, int, int] | None = None) -> tuple[dict, tuple[float, int, int]]:
    """Returns (stats, net_snapshot) — pass the returned snapshot back in as prev_net next call."""
    stats = {
        "cpu_temp": get_cpu_temp(),
        "cpu_chiplet_temp": get_cpu_chiplet_temp(),
        "cpu_freq": get_cpu_freq(),
        "cpu_load": get_cpu_load(),
        "nvme_temp": get_nvme_temp(),
        "nvme_sensor_temps": get_nvme_sensor_temps(),
        "gpu": get_gpu_stats(),
        "igpu": get_igpu_stats(),
        "ram_dimm_temps": get_ram_dimm_temps(),
        "wifi_temp": get_wifi_temp(),
        "igpu_voltage": get_igpu_voltage(),
    }
    ram_used, ram_total, ram_pct = get_ram()
    stats["ram_used"], stats["ram_total"], stats["ram_pct"] = ram_used, ram_total, ram_pct

    disk_used, disk_total, disk_pct = get_disk_usage()
    stats["disk_used"], stats["disk_total"], stats["disk_pct"] = disk_used, disk_total, disk_pct

    net_snapshot = get_network_snapshot()
    if prev_net is not None:
        stats["net_up_mbps"], stats["net_down_mbps"] = compute_network_rate(prev_net, net_snapshot)
    else:
        stats["net_up_mbps"], stats["net_down_mbps"] = 0.0, 0.0

    return stats, net_snapshot
