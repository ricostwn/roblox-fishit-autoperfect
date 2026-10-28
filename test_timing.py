"""
Interactive Hold-Time Tuner for Fish It
Find the exact millisecond duration for 100% 2.0x Perfect Casts!
"""

import json
import os
import subprocess
import sys
import time
from pynput import mouse, keyboard

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def play_sound(sound_name):
    path = f"/System/Library/Sounds/{sound_name}.aiff"
    if os.path.exists(path):
        try:
            subprocess.Popen(["afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}


def save_hold_time(hold_time_ms):
    cfg = load_config()
    cfg["use_timed_cast"] = True
    cfg["cast_hold_ms"] = hold_time_ms
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)
    print(f"\n[SAVED!] Saved cast_hold_ms = {hold_time_ms} ms to {CONFIG_FILE}")


def main():
    cfg = load_config()
    current_ms = cfg.get("cast_hold_ms", 850)

    print("=" * 65)
    print(" 🎯 FISH IT - PURE TIMING CALIBRATOR")
    print("=" * 65)
    print(" This tool tests holding Left Click for an exact millisecond duration.")
    print(" It is 100% immune to day/night, shadows, and camera angles!")
    print("-" * 65)
    print(" Controls (use while playing Roblox):")
    print("   • [ENTER]      : Cast rod with current hold duration")
    print("   • [UP ARROW]   : +1 ms (Fine tune longer)")
    print("   • [DOWN ARROW] : -1 ms (Fine tune shorter)")
    print("   • [RIGHT ARROW]: +5 ms (Bigger step)")
    print("   • [LEFT ARROW] : -5 ms (Bigger step)")
    print("   • [S]          : SAVE this duration to config.json when you hit 2.0x!")
    print("   • [Q]          : Quit")
    print("=" * 65)
    print(f"\n👉 Starting Hold Duration: {current_ms} ms\n")
    print("Switch to Roblox and press [ENTER] to test your first throw!\n")

    mouse_ctrl = mouse.Controller()
    is_running = True

    def execute_throw(duration_ms):
        print(f"\n🎣 Testing throw: holding for {duration_ms} ms...")
        mouse_ctrl.press(mouse.Button.left)
        time.sleep(duration_ms / 1000.0)
        mouse_ctrl.release(mouse.Button.left)
        play_sound("Hero")
        print(f" -> Released! (Duration: {duration_ms} ms)")
        print(f"    • Hit 1.9x? Press [UP ARROW] to add +1ms")
        print(f"    • Overshot? Press [DOWN ARROW] to reduce -1ms")
        print(f"    • Hit 2.0x PERFECT? Press [S] to SAVE!")

    def on_press(key):
        nonlocal current_ms, is_running
        try:
            if key == keyboard.Key.enter:
                execute_throw(current_ms)

            elif key == keyboard.Key.up:
                current_ms += 1
                play_sound("Ping")
                print(f"\n⬆️  [+1ms] Current hold time: {current_ms} ms  (Press [ENTER] to test)")

            elif key == keyboard.Key.down:
                current_ms = max(100, current_ms - 1)
                play_sound("Blow")
                print(f"\n⬇️  [-1ms] Current hold time: {current_ms} ms  (Press [ENTER] to test)")

            elif key == keyboard.Key.right:
                current_ms += 5
                play_sound("Ping")
                print(f"\n⏩ [+5ms] Current hold time: {current_ms} ms  (Press [ENTER] to test)")

            elif key == keyboard.Key.left:
                current_ms = max(100, current_ms - 5)
                play_sound("Blow")
                print(f"\n⏪ [-5ms] Current hold time: {current_ms} ms  (Press [ENTER] to test)")

            elif hasattr(key, "char") and key.char:
                c = key.char.lower()
                if c == 's':
                    save_hold_time(current_ms)
                    play_sound("Tink")
                    print("✅ You're ready! Run `python3 main.py` for infinite auto-fishing.")
                elif c == 'q':
                    print("\n🛑 Quitting...")
                    is_running = False
                    return False
        except Exception as e:
            pass

    listener = keyboard.Listener(on_press=on_press)
    listener.daemon = True
    listener.start()

    try:
        while is_running and listener.is_alive():
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

