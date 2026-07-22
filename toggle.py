#!/usr/bin/env python3
import json
import os
import sys

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

def set_enabled(enabled_state):
    config = {"enabled": enabled_state}
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"Error saving config: {e}", file=sys.stderr)
        return False

    # Also update status.json enabled flag immediately if status file exists
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r") as f:
                status_data = json.load(f)
            status_data["enabled"] = enabled_state
            with open(STATUS_FILE, "w") as f:
                json.dump(status_data, f, indent=4)
        except Exception:
            pass

    return True

def toggle():
    current = is_enabled()
    new_state = not current
    set_enabled(new_state)
    state_str = "ENABLED" if new_state else "DISABLED"
    print(f"EasyEffects Switcher is now {state_str}")
    return new_state

if __name__ == "__main__":
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in ["on", "enable", "true", "1"]:
            set_enabled(True)
            print("EasyEffects Switcher is now ENABLED")
        elif arg in ["off", "disable", "false", "0"]:
            set_enabled(False)
            print("EasyEffects Switcher is now DISABLED")
        elif arg in ["status", "check"]:
            print(f"EasyEffects Switcher is {'ENABLED' if is_enabled() else 'DISABLED'}")
        else:
            toggle()
    else:
        toggle()
