#!/usr/bin/env python3
import os
import sys
import json
import re
import subprocess
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
STATUS_FILE = os.path.join(BASE_DIR, "status.json")

def is_enabled():
    if not os.path.exists(CONFIG_FILE):
        return True
    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
            return data.get("enabled", True)
    except Exception:
        return True

def set_enabled(state):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump({"enabled": state}, f, indent=4)
        if os.path.exists(STATUS_FILE):
            with open(STATUS_FILE, "r") as f:
                s = json.load(f)
            s["enabled"] = state
            with open(STATUS_FILE, "w") as f:
                json.dump(s, f, indent=4)
    except Exception as e:
        print(f"Error saving config: {e}", file=sys.stderr)

def get_conky_geometry():
    try:
        res = subprocess.run(
            ["xdotool", "search", "--class", "Conky", "getwindowgeometry"],
            capture_output=True,
            text=True,
            check=True
        )
        pos = re.search(r"Position:\s*(\d+),(\d+)", res.stdout)
        geo = re.search(r"Geometry:\s*(\d+)x(\d+)", res.stdout)
        if pos and geo:
            return int(pos.group(1)), int(pos.group(2)), int(geo.group(1)), int(geo.group(2))
    except Exception:
        pass
    return None

class SwitcherToggleWidget(Gtk.Window):
    def __init__(self):
        super().__init__(title="Conky EasyEffects Switcher Footer")
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_app_paintable(True)
        
        # Enable RGBA for visual matching Conky's ARGB visual
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)

        # Set dock / desktop type hint so it stays nicely on desktop like Conky
        self.set_type_hint(Gdk.WindowTypeHint.DOCK)

        # Main Container VBox
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.set_name("conky-footer-box")
        self.add(box)

        # Separator line matching Conky's ${color1}${hr 1}
        separator = Gtk.Box()
        separator.set_name("conky-separator")
        separator.set_size_request(-1, 1)
        box.pack_start(separator, False, False, 0)

        # Full-width Toggle Button
        self.button = Gtk.Button()
        self.button.set_name("conky-toggle-button")
        self.button.connect("clicked", self.on_toggle_clicked)
        box.pack_start(self.button, True, True, 0)

        self.apply_styles()

        self.current_state = None
        self.update_ui()

        # Update position relative to Conky window
        self.sync_geometry()

        # Periodic updates (1s timer)
        GLib.timeout_add_seconds(1, self.on_timer)

    def apply_styles(self):
        css_provider = Gtk.CssProvider()
        css_data = """
        #conky-footer-box {
            background-color: rgba(18, 13, 24, 0.94);
            border-bottom-left-radius: 6px;
            border-bottom-right-radius: 6px;
            padding: 2px 10px 8px 10px;
        }
        #conky-separator {
            background-color: rgba(148, 163, 184, 0.3);
            margin: 2px 0px 6px 0px;
        }
        #conky-toggle-button {
            background-color: rgba(30, 27, 46, 0.8);
            border: 1px solid rgba(148, 163, 184, 0.3);
            border-radius: 4px;
            padding: 6px 0px;
            font-family: "IBM Plex Mono", monospace;
            font-size: 10.5px;
            font-weight: bold;
            outline: none;
        }
        #conky-toggle-button:hover {
            background-color: rgba(56, 189, 248, 0.2);
            border-color: #38bdf8;
        }
        #conky-toggle-button.enabled {
            color: #34d399;
        }
        #conky-toggle-button.disabled {
            color: #fda4af;
        }
        """
        css_provider.load_from_data(css_data.encode("utf-8"))
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def sync_geometry(self):
        geom = get_conky_geometry()
        if geom:
            x, y, w, h = geom
            # Width matches Conky window width
            self.set_size_request(w, -1)
            self.resize(w, 36)
            # Position at bottom of Conky: X=x, Y=y+h
            self.move(x, y + h)

    def update_ui(self):
        enabled = is_enabled()
        if enabled != self.current_state:
            self.current_state = enabled
            style_ctx = self.button.get_style_context()
            if enabled:
                self.button.set_label("EASYEFFECTS SWITCHER: [ON]")
                style_ctx.remove_class("disabled")
                style_ctx.add_class("enabled")
            else:
                self.button.set_label("EASYEFFECTS SWITCHER: [OFF]")
                style_ctx.remove_class("enabled")
                style_ctx.add_class("disabled")

    def on_timer(self):
        self.update_ui()
        self.sync_geometry()
        return True

    def on_toggle_clicked(self, button):
        new_state = not is_enabled()
        set_enabled(new_state)
        self.update_ui()

def main():
    win = SwitcherToggleWidget()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()

if __name__ == "__main__":
    main()
