"""Draw stats onto a PNG image, hacker terminal theme, two-column layout."""

import random
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

OUT_PATH = Path.home() / ".cache/pc-wallpaper/current.png"

# palette — monochrome green terminal, alert colors stay distinct
BG_COLOR = (2, 5, 2)
GRID_COLOR = (12, 26, 12)
GREEN = (60, 255, 90)
GREEN_DIM = (20, 130, 45)
TEXT_COLOR = GREEN
WARN_COLOR = (255, 180, 40)
CRIT_COLOR = (255, 60, 60)

FONT_PATH = "/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-ExtraBold.ttf"
FONT_SIZE = 34
HEADER_FONT_SIZE = 28
TERM_FONT_SIZE = 30
LINE_HEIGHT = 50
MARGIN_X = 60
GRID_SPACING = 80
GLOW_RADIUS = 8
CORNER_SIZE = 40
FRAME_MARGIN = 24
TOP_BAR_CLEARANCE = 48   # keep clear of GNOME's top bar
BOTTOM_DOCK_CLEARANCE = 90  # keep clear of Ubuntu Dock (bottom-positioned)
PANEL_PAD_X = 32
SCANLINE_SPACING = 4
SCANLINE_DARKNESS = 32
VIGNETTE_MIN = 150
RAIN_DENSITY = 160  # number of background digits
RAIN_SEED = 1337    # fixed so texture doesn't flicker between frames


def temp_color(value: float, warn=70, crit=85) -> tuple[int, int, int]:
    if value >= crit:
        return CRIT_COLOR
    if value >= warn:
        return WARN_COLOR
    return GREEN


def draw_grid(draw, width, height):
    for gx in range(0, width, GRID_SPACING):
        draw.line([(gx, 0), (gx, height)], fill=GRID_COLOR, width=1)
    for gy in range(0, height, GRID_SPACING):
        draw.line([(0, gy), (width, gy)], fill=GRID_COLOR, width=1)


def draw_digit_rain(draw, width, height, font):
    """Sparse, fixed-position faint digits — texture, not real animation (seed is constant)."""
    rng = random.Random(RAIN_SEED)
    chars = "01"
    for _ in range(RAIN_DENSITY):
        x = rng.randint(0, width)
        y = rng.randint(0, height)
        shade = rng.randint(10, 28)
        draw.text((x, y), rng.choice(chars), fill=(0, shade, 0), font=font)


def draw_corner_brackets(draw, width, height, color=GREEN):
    m = FRAME_MARGIN
    s = CORNER_SIZE
    top = TOP_BAR_CLEARANCE
    bottom = height - BOTTOM_DOCK_CLEARANCE
    corners = [
        ((m, top), (m + s, top), (m, top + s)),
        ((width - m, top), (width - m - s, top), (width - m, top + s)),
        ((m, bottom), (m + s, bottom), (m, bottom - s)),
        ((width - m, bottom), (width - m - s, bottom), (width - m, bottom - s)),
    ]
    for origin, h_end, v_end in corners:
        draw.line([origin, h_end], fill=color, width=3)
        draw.line([origin, v_end], fill=color, width=3)


def apply_scanlines(img: Image.Image) -> Image.Image:
    overlay = Image.new("RGB", img.size, (255, 255, 255))
    overlay_draw = ImageDraw.Draw(overlay)
    shade = 255 - SCANLINE_DARKNESS
    for y in range(0, img.size[1], SCANLINE_SPACING):
        overlay_draw.line([(0, y), (img.size[0], y)], fill=(shade, shade, shade), width=1)
    return ImageChops.multiply(img, overlay)


def apply_vignette(img: Image.Image) -> Image.Image:
    grad = Image.radial_gradient("L").resize(img.size)
    grad = grad.point(lambda p: VIGNETTE_MIN + (255 - VIGNETTE_MIN) * (p / 255))
    overlay = Image.merge("RGB", (grad, grad, grad))
    return ImageChops.multiply(img, overlay)


def build_sections(stats: dict) -> list:
    cpu_temp = stats["cpu_temp"]
    nvme_temp = stats["nvme_temp"]
    gpu_temp = stats["gpu"]["temp"]
    cpu_load_list = stats["cpu_load"]
    cpu_load_pct = sum(cpu_load_list) / len(cpu_load_list)
    gpu_util_pct = stats["gpu"]["util_pct"]

    # Numbers are fixed-width padded so label text never changes length between
    # frames — otherwise a digit-count change (e.g. 9.9 -> 41.0) shifts the panel.
    # each line: (text, color)
    ram_color = temp_color(stats["ram_pct"], warn=80, crit=95)
    disk_color = temp_color(stats["disk_pct"], warn=85, crit=95)
    vram_pct = stats["gpu"]["vram_used_mib"] / stats["gpu"]["vram_total_mib"] * 100
    vram_color = temp_color(vram_pct, warn=80, crit=95)

    cpu_lines = [
        (f"TEMP  {cpu_temp:.1f}C", temp_color(cpu_temp)),
        (f"FREQ  {stats['cpu_freq']:.0f} MHz", GREEN),
        (f"LOAD  {cpu_load_pct:.0f}%", temp_color(cpu_load_pct, warn=70, crit=90)),
        (f"RAM   {stats['ram_used']:.1f}/{stats['ram_total']:.1f} GB ({stats['ram_pct']:.0f}%)", ram_color),
    ]

    storage_lines = [
        (f"NVME  {nvme_temp:.1f}C", temp_color(nvme_temp, warn=60, crit=75)),
        (f"DISK  {stats['disk_used']:.0f}/{stats['disk_total']:.0f} GB ({stats['disk_pct']:.0f}%)", disk_color),
    ]

    gpu_lines = [
        (f"TEMP  {gpu_temp:.0f}C", temp_color(gpu_temp, warn=75, crit=87)),
        (f"PWR   {stats['gpu']['power_w']:.0f} W", GREEN),
        (f"UTIL  {gpu_util_pct:.0f}%", GREEN),
        (
            f"VRAM  {stats['gpu']['vram_used_mib']:.0f}/{stats['gpu']['vram_total_mib']:.0f} MiB ({vram_pct:.0f}%)",
            vram_color,
        ),
    ]

    return [
        ("CPU // 7700X", cpu_lines),
        ("STORAGE", storage_lines),
        ("GPU // RTX 3090", gpu_lines),
    ]


def compute_label_width(sections, font) -> int:
    """Widest label across all sections, so every panel is a consistent width."""
    max_width = 0
    for _, lines in sections:
        for text, _ in lines:
            label = f"$ {text}"
            max_width = max(max_width, font.getlength(label))
    return int(max_width)


def render_column(glow_draw, sections, x, font, header_font, label_width, start_y):
    y = start_y

    for title, lines in sections:
        glow_draw.text((x, y), title, fill=GREEN, font=header_font)
        underline_y = y + HEADER_FONT_SIZE + 4
        glow_draw.line([(x, underline_y), (x + label_width, underline_y)], fill=GREEN_DIM, width=2)
        y += LINE_HEIGHT

        for text, color in lines:
            label = f"$ {text}"
            glow_draw.text((x, y), label, fill=color, font=font)
            y += LINE_HEIGHT

        y += LINE_HEIGHT // 2 + 20


def draw_terminal_header(glow_draw, width, font):
    clock_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prompt = f"root@desktop:~$ monitor --watch  [{clock_text}]"
    glow_draw.text((MARGIN_X, TOP_BAR_CLEARANCE + 6), prompt, fill=GREEN, font=font)


def render(stats: dict, width: int, height: int) -> None:
    base = Image.new("RGB", (width, height), BG_COLOR)
    base_draw = ImageDraw.Draw(base)
    draw_grid(base_draw, width, height)
    small_font = ImageFont.truetype(FONT_PATH, 16)
    draw_digit_rain(base_draw, width, height, small_font)
    draw_corner_brackets(base_draw, width, height)

    # glow layer: draw all neon content on black, blur, screen-blend onto base
    glow = Image.new("RGB", (width, height), (0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)

    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    header_font = ImageFont.truetype(FONT_PATH, HEADER_FONT_SIZE)
    term_font = ImageFont.truetype(FONT_PATH, TERM_FONT_SIZE)

    draw_terminal_header(glow_draw, width, term_font)

    sections = build_sections(stats)
    label_width = compute_label_width(sections, font)

    col_x = MARGIN_X + PANEL_PAD_X

    lines_total = sum(len(lines) for _, lines in sections)
    headers_total = len(sections)
    content_height = lines_total * LINE_HEIGHT + headers_total * (LINE_HEIGHT + LINE_HEIGHT // 2 + 20)
    safe_top = TOP_BAR_CLEARANCE + 70  # below the terminal header line
    safe_bottom = height - BOTTOM_DOCK_CLEARANCE
    start_y = safe_top + max(0, (safe_bottom - safe_top - content_height) // 2)

    render_column(glow_draw, sections, col_x, font, header_font, label_width, start_y)

    blurred = glow.filter(ImageFilter.GaussianBlur(GLOW_RADIUS))
    composited = ImageChops.screen(base, blurred)
    # paste sharp neon layer back on top so text/bars stay crisp, glow is the halo
    final = ImageChops.screen(composited, glow)

    final = apply_vignette(final)
    final = apply_scanlines(final)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = OUT_PATH.with_suffix(".tmp.png")
    final.save(tmp_path)
    tmp_path.replace(OUT_PATH)  # atomic — no window where a reader sees a partial file
