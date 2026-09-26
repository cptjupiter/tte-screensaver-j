"""
Spielplatz-Modus für tte-screensaver.

Läuft in einem normalen Fenster (kein Bildschirmschoner-Verhalten) und
lässt sich per Tastatur steuern. Themen liegen als JSON-Dateien im Ordner
`themes/` und werden beim Speichern automatisch neu geladen.

Start:  python run.py /play     oder     python playground.py
"""

from __future__ import annotations

import importlib
import inspect
import json
import pkgutil
import random
import re
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

import pygame

from .config import DEFAULT_ASCII_ART
from .renderer import ANSIRenderer

ROOT = Path(__file__).resolve().parent.parent
THEMES_DIR = ROOT / "themes"
SCREENSHOT_DIR = ROOT / "screenshots"

HOLD_SECONDS = 2.5  # so lange bleibt das fertige Bild stehen
HEX_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")

HELP_LINES = [
    "← / →      Effekt zurück / weiter",
    "↑ / ↓      Thema zurück / weiter",
    "R          Effekt neu starten",
    "Leertaste  Pause",
    "A          Modus: Wiederholen / Zufall",
    "+ / -      Schrift grösser / kleiner",
    "F          Vollbild an / aus",
    "F5         Themen neu laden (passiert auch automatisch)",
    "I          Einstellungen des Effekts in der Konsole anzeigen",
    "S          Screenshot speichern",
    "H          Diese Hilfe ein / aus",
    "Esc        Beenden",
]


# ---------------------------------------------------------------------------
# Effekte
# ---------------------------------------------------------------------------

def discover_effects() -> Dict[str, type]:
    """Findet alle Effekte der installierten terminaltexteffects-Version."""
    import terminaltexteffects.effects as effects_pkg
    from terminaltexteffects.engine.base_effect import BaseEffect

    found: Dict[str, type] = {}
    for module_info in pkgutil.iter_modules(effects_pkg.__path__):
        if not module_info.name.startswith("effect_"):
            continue
        try:
            module = importlib.import_module(f"terminaltexteffects.effects.{module_info.name}")
        except Exception as exc:  # pragma: no cover - defekte Einzelmodule überspringen
            print(f"Effekt {module_info.name} nicht ladbar: {exc}", file=sys.stderr)
            continue
        for name, cls in inspect.getmembers(module, inspect.isclass):
            if issubclass(cls, BaseEffect) and cls is not BaseEffect and cls.__module__ == module.__name__:
                found[name] = cls
    return dict(sorted(found.items()))


def to_tte_value(key: str, value: Any) -> Any:
    """Wandelt JSON-Werte in die Typen um, die terminaltexteffects erwartet."""
    from terminaltexteffects.utils.graphics import Color, Gradient

    if key.endswith("direction") and isinstance(value, str):
        return Gradient.Direction[value.strip().upper()]
    if isinstance(value, str) and HEX_RE.match(value):
        return Color(value.lstrip("#"))
    if isinstance(value, list):
        return tuple(to_tte_value(key, v) for v in value)
    return value


def describe_config(effect_cls: type) -> str:
    """Listet die Einstellungen eines Effekts mit Standardwerten."""
    effect = effect_cls("x")
    cfg = effect.effect_config
    lines = [f"\n=== Einstellungen für {effect_cls.__name__} ==="]
    for name in sorted(vars(cfg)):
        if name.startswith("_") or name == "parser_spec":
            continue
        value = getattr(cfg, name)
        lines.append(f"  {name:32} = {format_value(value)}")
    lines.append("In einem Thema unter \"effect_settings\": {\"%s\": {...}} setzbar.\n" % effect_cls.__name__)
    return "\n".join(lines)


def format_value(value: Any) -> str:
    if isinstance(value, tuple):
        return "[" + ", ".join(format_value(v) for v in value) + "]"
    rgb = getattr(value, "rgb_color", None)
    if rgb:
        return f'"#{rgb}"'
    if hasattr(value, "name") and value.__class__.__name__ == "Direction":
        return f'"{value.name.lower()}"'
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    return repr(value)


# ---------------------------------------------------------------------------
# Themen
# ---------------------------------------------------------------------------

@dataclass
class Theme:
    name: str
    path: Optional[Path]
    ascii_art: str = DEFAULT_ASCII_ART
    background: Tuple[int, int, int] = (0, 0, 0)
    font_size: int = 18
    colors: List[str] = field(default_factory=list)
    direction: Optional[str] = None
    effects: List[str] = field(default_factory=list)
    effect_settings: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    error: Optional[str] = None


def hex_to_rgb(value: str) -> Tuple[int, int, int]:
    value = value.lstrip("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def build_ascii_art(data: dict, theme_dir: Path) -> str:
    if "ascii_file" in data:
        return (theme_dir / data["ascii_file"]).read_text(encoding="utf-8").rstrip("\n")
    if "text" in data:
        try:
            import pyfiglet
        except ImportError as exc:
            raise RuntimeError("Für \"text\" wird pyfiglet benötigt: pip install pyfiglet") from exc
        art = pyfiglet.figlet_format(data["text"], font=data.get("font", "ansi_shadow"))
        return "\n".join(line.rstrip() for line in art.splitlines()).strip("\n")
    if "ascii_art" in data:
        art = data["ascii_art"]
        return "\n".join(art) if isinstance(art, list) else art
    return DEFAULT_ASCII_ART


def load_theme(path: Path) -> Theme:
    theme = Theme(name=path.stem, path=path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        theme.name = data.get("name", path.stem)
        theme.ascii_art = build_ascii_art(data, path.parent)
        if "background" in data:
            theme.background = hex_to_rgb(data["background"])
        theme.font_size = int(data.get("font_size", theme.font_size))
        theme.colors = list(data.get("colors", []))
        theme.direction = data.get("direction")
        theme.effects = list(data.get("effects", []))
        theme.effect_settings = dict(data.get("effect_settings", {}))
    except Exception as exc:
        theme.error = f"{path.name}: {exc}"
    return theme


def load_themes() -> List[Theme]:
    if not THEMES_DIR.exists():
        return [Theme(name="Standard", path=None)]
    themes = [load_theme(p) for p in sorted(THEMES_DIR.glob("*.json")) if not p.name.startswith("_")]
    return themes or [Theme(name="Standard", path=None)]


def themes_signature() -> Tuple:
    """Änderungszeitpunkte aller Dateien im Themen-Ordner (für automatisches Neuladen)."""
    if not THEMES_DIR.exists():
        return ()
    return tuple(sorted((p.name, p.stat().st_mtime) for p in THEMES_DIR.iterdir() if p.is_file()))


# ---------------------------------------------------------------------------
# Spielplatz
# ---------------------------------------------------------------------------

class Playground:
    def __init__(self) -> None:
        self.all_effects = discover_effects()
        self.themes = load_themes()
        self.theme_index = 0
        self.effect_index = 0
        self.font_offset = 0
        self.paused = False
        self.random_mode = False
        self.show_help = False
        self.fullscreen = False
        self.window_size = (1280, 720)
        self.message: Optional[Tuple[str, float, Tuple[int, int, int]]] = None
        self.effect_error: Optional[str] = None
        self.frame: Optional[str] = None
        self.iterator: Optional[Iterator[str]] = None
        self._signature = themes_signature()
        self._last_check = 0.0
        self.hold_until: Optional[float] = None  # Endbild kurz stehen lassen

    # --- Hilfsfunktionen ---------------------------------------------------

    @property
    def theme(self) -> Theme:
        return self.themes[self.theme_index]

    def effect_names(self) -> List[str]:
        wanted = [e for e in self.theme.effects if e in self.all_effects]
        return wanted or list(self.all_effects)

    @property
    def effect_name(self) -> str:
        names = self.effect_names()
        return names[self.effect_index % len(names)]

    def notify(self, text: str, color: Tuple[int, int, int] = (230, 230, 230), seconds: float = 2.5) -> None:
        self.message = (text, time.time() + seconds, color)
        print(text)

    # --- Aufbau ------------------------------------------------------------

    def setup_display(self) -> None:
        if self.fullscreen:
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            self.screen = pygame.display.set_mode(self.window_size, pygame.RESIZABLE)
        pygame.display.set_caption("TTE Spielplatz")

    def setup_renderer(self) -> None:
        size = max(8, self.theme.font_size + self.font_offset)
        self.renderer = ANSIRenderer(font_size=size, background_color=self.theme.background)
        self.overlay_font = pygame.font.SysFont("consolas,dejavu sans mono,monospace", 15)

    def start_effect(self) -> None:
        """Baut den aktuellen Effekt mit dem aktuellen Thema neu auf."""
        self.effect_error = None
        self.frame = None
        self.hold_until = None
        width, height = self.screen.get_size()
        self.canvas_w = max(10, width // self.renderer.char_width)
        self.canvas_h = max(5, height // self.renderer.char_height)
        name = self.effect_name
        try:
            effect = self.all_effects[name](self.theme.ascii_art)
            tc = effect.terminal_config
            tc.ignore_terminal_dimensions = True
            tc.canvas_width = self.canvas_w
            tc.canvas_height = self.canvas_h
            tc.anchor_text = "c"
            tc.frame_rate = 0

            cfg = effect.effect_config
            if self.theme.colors and hasattr(cfg, "final_gradient_stops"):
                cfg.final_gradient_stops = to_tte_value("final_gradient_stops", self.theme.colors)
            if self.theme.direction and hasattr(cfg, "final_gradient_direction"):
                cfg.final_gradient_direction = to_tte_value("final_gradient_direction", self.theme.direction)
            for key, value in self.theme.effect_settings.get(name, {}).items():
                if not hasattr(cfg, key):
                    self.notify(f"{name} kennt die Einstellung \"{key}\" nicht (Taste I zeigt alle)", (255, 170, 60), 5)
                    continue
                setattr(cfg, key, to_tte_value(key, value))

            self.iterator = iter(effect)
        except Exception as exc:
            self.iterator = None
            self.effect_error = f"{name}: {exc}"
            traceback.print_exc()

    def rebuild(self) -> None:
        self.setup_renderer()
        self.start_effect()

    # --- Aktionen ------------------------------------------------------------

    def change_effect(self, step: int) -> None:
        self.effect_index = (self.effect_index + step) % len(self.effect_names())
        self.start_effect()

    def change_theme(self, step: int) -> None:
        current = self.effect_name
        self.theme_index = (self.theme_index + step) % len(self.themes)
        names = self.effect_names()
        self.effect_index = names.index(current) if current in names else 0
        self.rebuild()
        self.notify(f"Thema: {self.theme.name}")

    def reload_themes(self, automatic: bool = False) -> None:
        current_theme = self.theme.path
        current_effect = self.effect_name
        self.themes = load_themes()
        paths = [t.path for t in self.themes]
        self.theme_index = paths.index(current_theme) if current_theme in paths else 0
        names = self.effect_names()
        self.effect_index = names.index(current_effect) if current_effect in names else 0
        self.rebuild()
        self._signature = themes_signature()
        if self.theme.error:
            self.notify(f"Fehler im Thema – {self.theme.error}", (255, 90, 90), 8)
        else:
            self.notify("Themen neu geladen" + (" (Datei gespeichert)" if automatic else ""))

    def next_after_finish(self) -> None:
        if self.random_mode and len(self.effect_names()) > 1:
            choices = [i for i in range(len(self.effect_names())) if i != self.effect_index]
            self.effect_index = random.choice(choices)
        self.start_effect()

    def screenshot(self) -> None:
        SCREENSHOT_DIR.mkdir(exist_ok=True)
        path = SCREENSHOT_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}_{self.theme.name}_{self.effect_name}.png"
        pygame.image.save(self.screen, str(path))
        self.notify(f"Screenshot: {path.name}")

    def toggle_fullscreen(self) -> None:
        self.fullscreen = not self.fullscreen
        self.setup_display()
        self.start_effect()

    # --- Ereignisse ----------------------------------------------------------

    def handle_events(self) -> bool:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.VIDEORESIZE and not self.fullscreen:
                self.window_size = (event.w, event.h)
                self.start_effect()
            if event.type != pygame.KEYDOWN:
                continue

            key = event.key
            if key == pygame.K_ESCAPE:
                if self.fullscreen:
                    self.toggle_fullscreen()
                else:
                    return False
            elif key == pygame.K_RIGHT:
                self.change_effect(1)
            elif key == pygame.K_LEFT:
                self.change_effect(-1)
            elif key == pygame.K_DOWN:
                self.change_theme(1)
            elif key == pygame.K_UP:
                self.change_theme(-1)
            elif key == pygame.K_r:
                self.start_effect()
            elif key == pygame.K_SPACE:
                self.paused = not self.paused
            elif key == pygame.K_a:
                self.random_mode = not self.random_mode
                self.notify("Modus: " + ("Zufall" if self.random_mode else "Wiederholen"))
            elif key in (pygame.K_PLUS, pygame.K_KP_PLUS, pygame.K_EQUALS):
                self.font_offset += 2
                self.rebuild()
            elif key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                self.font_offset -= 2
                self.rebuild()
            elif key == pygame.K_f:
                self.toggle_fullscreen()
            elif key == pygame.K_F5:
                self.reload_themes()
            elif key == pygame.K_i:
                print(describe_config(self.all_effects[self.effect_name]))
                self.notify("Einstellungen in der Konsole ausgegeben")
            elif key == pygame.K_s:
                self.screenshot()
            elif key in (pygame.K_h, pygame.K_F1):
                self.show_help = not self.show_help
        return True

    def check_theme_files(self) -> None:
        now = time.time()
        if now - self._last_check < 0.7:
            return
        self._last_check = now
        try:
            if themes_signature() != self._signature:
                self.reload_themes(automatic=True)
        except OSError:
            pass  # Datei wird gerade geschrieben – beim nächsten Mal

    # --- Zeichnen ------------------------------------------------------------

    def draw_text_box(self, lines: List[Tuple[str, Tuple[int, int, int]]], pos: str) -> None:
        pad = 8
        surfaces = [self.overlay_font.render(text, True, color) for text, color in lines]
        w = max(s.get_width() for s in surfaces) + pad * 2
        h = sum(s.get_height() for s in surfaces) + pad * 2
        sw, sh = self.screen.get_size()
        x, y = {
            "bottom": (10, sh - h - 10),
            "top": (sw - w - 10, 10),
            "center": ((sw - w) // 2, (sh - h) // 2),
        }[pos]
        box = pygame.Surface((w, h), pygame.SRCALPHA)
        box.fill((0, 0, 0, 225))
        self.screen.blit(box, (x, y))
        y += pad
        for s in surfaces:
            self.screen.blit(s, (x + pad, y))
            y += s.get_height()

    def draw(self) -> None:
        self.screen.fill(self.theme.background)
        if self.frame:
            self.renderer.render_frame(self.frame, self.screen, canvas_width=self.canvas_w, canvas_height=self.canvas_h)

        names = self.effect_names()
        status = (
            f"Thema: {self.theme.name} ({self.theme_index + 1}/{len(self.themes)})   "
            f"Effekt: {self.effect_name} ({self.effect_index % len(names) + 1}/{len(names)})   "
            f"{'Zufall' if self.random_mode else 'Wiederholen'}"
            f"{'   PAUSE' if self.paused else ''}   H = Hilfe"
        )
        lines = [(status, (200, 200, 200))]
        if self.theme.error:
            lines.append((f"Fehler im Thema: {self.theme.error}", (255, 90, 90)))
        if self.effect_error:
            lines.append((f"Effekt-Fehler: {self.effect_error}", (255, 90, 90)))
        self.draw_text_box(lines, "bottom")

        if self.message and time.time() < self.message[1]:
            self.draw_text_box([(self.message[0], self.message[2])], "top")
        if self.show_help:
            self.draw_text_box([("Tasten", (255, 255, 255))] + [(l, (210, 210, 210)) for l in HELP_LINES], "center")

    # --- Hauptschleife ---------------------------------------------------------

    def run(self, max_frames: Optional[int] = None) -> None:
        pygame.init()
        pygame.key.set_repeat(350, 60)
        self.setup_display()
        self.rebuild()
        if self.theme.error:
            self.notify(f"Fehler im Thema – {self.theme.error}", (255, 90, 90), 8)
        print(f"{len(self.all_effects)} Effekte, {len(self.themes)} Themen geladen. Taste H zeigt die Hilfe.")
        clock = pygame.time.Clock()
        frames = 0
        try:
            while self.handle_events():
                self.check_theme_files()
                if self.hold_until and time.time() >= self.hold_until:
                    self.next_after_finish()
                elif not self.paused and not self.hold_until and self.iterator is not None:
                    try:
                        self.frame = next(self.iterator)
                    except StopIteration:
                        self.hold_until = time.time() + HOLD_SECONDS
                    except Exception as exc:
                        self.effect_error = f"{self.effect_name}: {exc}"
                        self.iterator = None
                self.draw()
                pygame.display.flip()
                clock.tick(60)
                frames += 1
                if max_frames and frames >= max_frames:
                    break
        finally:
            pygame.quit()


def run_playground() -> None:
    Playground().run()


if __name__ == "__main__":
    run_playground()
