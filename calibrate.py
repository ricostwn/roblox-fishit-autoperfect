"""
Interactive Calibration Tool for Fish It Timing Bot
Helps you locate the exact screen coordinates and pixel colors of the reel minigame.
"""

import json
import os
import sys
import time
import mss
import numpy as np
from pynput import mouse, keyboard
from PIL import Image

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}


def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)
    print(f"\n[+] Configuration saved successfully to {CONFIG_FILE}")


def get_pixel_color(sct, x, y):
    """Grab a single pixel color using mss."""
    # Capture a 1x1 region
    monitor = {"top": int(y), "left": int(x), "width": 1, "height": 1}
    img = np.array(sct.grab(monitor))
    # mss returns BGRA format
    b, g, r = img[0, 0][:3]
    return int(r), int(g), int(b)


def main():
    print("=" * 60)
    print(" FISH IT - CALIBRATION ASSISTANT")
    print("=" * 60)
    print("\nInstructions:")
    print("1. Open Roblox and start the Fish It fishing minigame.")
    print("2. Position your game window where you usually keep it.")
    print("3. Move your mouse cursor over the target area (e.g., the 'PERFECT' zone")
    print("   or the exact spot the needle crosses when a reel should trigger).")
    print("4. Press [C] on your keyboard to CAPTURE the coordinates & color.")
    print("5. Press [Q] to quit without saving.\n")

    cfg = load_config()
    captured_data = {}
    done = False

    mouse_ctrl = mouse.Controller()

    with mss.mss() as sct:
        def on_press(key):
            nonlocal done, captured_data
            try:
                if hasattr(key, 'char') and key.char:
                    if key.char.lower() == 'c':
                        mx, my = mouse_ctrl.position
                        r, g, b = get_pixel_color(sct, mx, my)
                        captured_data = {
                            "x": int(mx),
                            "y": int(my),
                            "rgb": [r, g, b]
                        }
                        print(f"\n\n[CAPTURED TARGET]")
                        print(f" -> Coordinates: X={int(mx)}, Y={int(my)}")
                        print(f" -> Pixel Color: R={r}, G={g}, B={b} (Hex: #{r:02x}{g:02x}{b:02x})")
                        done = True
                        return False
                    elif key.char.lower() == 'q':
                        print("\n[!] Calibration cancelled.")
                        done = True
                        return False
            except Exception as e:
                print(f"Error handling key: {e}")

        listener = keyboard.Listener(on_press=on_press)
        listener.start()

        print("Tracking mouse... Hover over the target and press [C] (or [Q] to abort):")
        try:
            while not done and listener.is_alive():
                mx, my = mouse_ctrl.position
                try:
                    r, g, b = get_pixel_color(sct, mx, my)
                    sys.stdout.write(
                        f"\rMouse Pos: X={int(mx):4d}, Y={int(my):4d} | Current Color: RGB({r:3d}, {g:3d}, {b:3d})   "
                    )
                    sys.stdout.flush()
                except Exception:
                    pass
                time.sleep(0.08)
        except KeyboardInterrupt:
            print("\nAborted by user.")
            return

        listener.join()

    if captured_data:
        print("\n" + "-" * 50)
        action_choice = input("Trigger action: (1) Mouse Left Click, (2) Spacebar? [Default: 1]: ").strip()
        if action_choice == "2":
            cfg["action_type"] = "key"
            cfg["action_key"] = "space"
        else:
            cfg["action_type"] = "click"
            cfg["action_key"] = "left_click"

        cfg["target_x"] = captured_data["x"]
        cfg["target_y"] = captured_data["y"]
        cfg["target_color_rgb"] = captured_data["rgb"]

        # Save snapshot for user verification
        try:
            with mss.mss() as sct:
                box = {
                    "top": max(0, captured_data["y"] - 30),
                    "left": max(0, captured_data["x"] - 30),
                    "width": 60,
                    "height": 60
                }
                snap = sct.grab(box)
                img = Image.frombytes("RGB", snap.size, snap.bgra, "raw", "BGRX")
                snap_path = os.path.join(os.path.dirname(CONFIG_FILE), "calibration_preview.png")
                img.save(snap_path)
                print(f"[+] Saved 60x60 preview around target to: {snap_path}")
        except Exception as e:
            print(f"Note: Could not save preview snapshot: {e}")

        save_config(cfg)
        print("\nCalibration complete! You can now run `python3 main.py` to start.")


if __name__ == "__main__":
    main()

