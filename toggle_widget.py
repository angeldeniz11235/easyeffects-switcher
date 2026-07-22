#!/usr/bin/env python3
import os
import sys
import json
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, Pango

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

class SwitcherToggleWidget(Gtk.Window):
    def __init__(self):
        super().__init__(title="EasyEffects Switcher Toggle")
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_below(False) # Allows easy interaction
        self.set_app_paintable(True)
        self.set_visual(self.get_screen().get_rgba_visual())

        # Main Box
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.set_name("main-container")
        self.add(box)

        # Toggle Button
        self.button = Gtk.Button()
        self.button.set_name("toggle-button")
        self.button.connect("clicked", self.on_toggle_clicked)
        box.pack_start(self.button, True, True, 0)

        # Apply CSS styling
        self.apply_styles()

        # Update initial UI state
        self.current_state = None
        self.update_ui()

        # Timer to poll for external state changes
        GLib.timeout_add_seconds(1, self.update_ui)

    def apply_styles(self):
        css_provider = Gtk.CssProvider()
        css_data = """
        #main-container {
            background-color: rgba(18, 13, 24, 0.94);
            border: 1px solid rgba(148, 163, 184, 0.3);
            border-radius: 8px;
            padding: 4px;
        }
        #toggle-button {
            background-color: #1e1b2e;
            border: 1px solid #38bdf8;
            border-radius: 6px;
            padding: 6px 12px;
            font-family: "IBM Plex Mono", monospace;
            font-size: 11px;
            font-weight: bold;
            outline: none;
            transition: all 200ms ease;
        }
        #toggle-button:hover {
            background-color: #2a243e;
            border-color: #c084fc;
        }
        #toggle-button.enabled {
            color: #34d399;
        }
        #toggle-button.disabled {
            color: #fda4af;
        }
        """
        css_provider.load_from_data(css_data.encode("utf-8"))
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def update_ui(self):
        enabled = is_enabled()
        if enabled != self.current_state:
            self.current_state = enabled
            style_ctx = self.button.get_style_context()
            if enabled:
                self.button.set_label("SWITCHER: [ON]")
                style_ctx.remove_class("disabled")
                style_ctx.add_class("enabled")
            else:
                self.button.set_label("SWITCHER: [OFF]")
                style_ctx.remove_class("enabled")
                style_ctx.add_class("disabled")
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
