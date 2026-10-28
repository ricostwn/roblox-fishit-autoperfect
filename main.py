"""
Fish It - 100% Fully Autonomous Dynamic Fishing Bot
Tracks the dynamic 2.0x green fill in real time (handles variable bar speeds, day & night!).
"""

import json
import os
import subprocess
import sys
import threading
import time
import mss
import numpy as np
from pynput import mouse, keyboard

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def play_sound(sound_name):
    """Cross-platform audio feedback (macOS afplay & Windows winsound)."""
    if sys.platform == "darwin":
        path = f"/System/Library/Sounds/{sound_name}.aiff"
        if os.path.exists(path):
            try:
                subprocess.Popen(["afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
    elif sys.platform == "win32":
        try:
            import winsound
            if sound_name in ["Hero", "Ping", "Tink"]:
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            else:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            pass


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}


def is_peak_green(pixel):
    """
    Detects the true 2.0x Luck green fill inside the bar.
    Prevents uint8 overflow by casting explicitly to python ints.
    Only the green bar fill has Green > 140 and Green significantly greater than both Red and Blue.
    """
    r, g, b = int(pixel[0]), int(pixel[1]), int(pixel[2])
    return (g > 140) and (g - r > 45) and (g - b > 45)


class InfiniteAutoFisher:
    def __init__(self, cfg):
        # 2.0x Luck top cap coordinates (center of bar at x=845, top at y=416)
        self.target_x = 845
        self.target_y = 416

        # Reeling detection coordinates (The red [STOP] button on the reel bar)
        self.stop_x = cfg.get("stop_button_x", 1095)
        self.stop_y = cfg.get("stop_button_y", 816)

        # Delays
        self.cast_settle_delay = cfg.get("cast_settle_delay", 1.5)
        self.post_catch_delay = cfg.get("post_catch_delay", 2.2)
        self.click_speed = cfg.get("click_speed", 0.025)

        self.mouse_ctrl = mouse.Controller()
        self.kb_ctrl = keyboard.Controller()

        self.is_running = True
        self.is_active = False
        self.worker_thread = None

    def is_reeling_active(self, sct):
        """Uses OpenCV template matching to detect the [STOP] button with >0.75 confidence."""
        if not hasattr(self, 'templ_stop') or self.templ_stop is None:
            templ_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "stop_button.png")
            if os.path.exists(templ_path):
                import cv2
                self.templ_stop = cv2.imread(templ_path, cv2.IMREAD_GRAYSCALE)
            else:
                self.templ_stop = None

        if self.templ_stop is not None:
            import cv2
            box = {
                "top": 760,
                "left": 1020,
                "width": 200,
                "height": 110
            }
            raw = np.array(sct.grab(box))
            gray = cv2.cvtColor(raw, cv2.COLOR_BGRA2GRAY)
            res = cv2.matchTemplate(gray, self.templ_stop, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(res)
            return max_val > 0.75

        return False

    def cast_perfect_rod(self, sct):
        """
        Dynamically tracks the rising green fill in real time.
        Whether the bar rises slowly or quickly, it releases the exact millisecond 2.0x is reached!
        """
        print("\n🎣 [1/3 CASTING] Holding Left Click -> Tracking dynamic 2.0x rise...")
        self.mouse_ctrl.press(mouse.Button.left)

        # 8px wide by 4px tall window directly across the 2.0x top cap (y=414..418)
        monitor = {
            "top": 414,
            "left": 841,
            "width": 8,
            "height": 4
        }

        start = time.time()
        timeout = 2.2
        hit = False

        while time.time() - start < timeout and self.is_active and self.is_running:
            # Physical safety guard: bar takes at least 450ms to reach 2.0x
            if time.time() - start < 0.45:
                time.sleep(0.01)
                continue

            raw = sct.grab(monitor)
            img = np.array(raw)
            pixels_rgb = img[:, :, [2, 1, 0]]

            # Check if any pixel inside the 2.0x cap turns into green fill
            for row in pixels_rgb:
                for p in row:
                    if is_peak_green(p):
                        hit = True
                        break
                if hit:
                    break

            if hit:
                break
            time.sleep(0.001)

        # Release immediately upon hitting 2.0x!
        self.mouse_ctrl.release(mouse.Button.left)
        elapsed = (time.time() - start) * 1000

        if hit:
            play_sound("Hero")
            print(f"🎯 [PERFECT 2.0x!] Reached 2.0x in {elapsed:.0f}ms! (Dynamic Tracking)")
        else:
            print(f"⏱️ [TIMEOUT] Bar did not reach top in {timeout}s.")

        time.sleep(self.cast_settle_delay)

    def reel_fish_in(self, sct):
        """Rapidly clicks until the red [STOP] button disappears (fish caught)."""
        print("🌀 [3/3 REELING] Fish on the line! Rapid clicking...")
        play_sound("Ping")

        check_counter = 0
        reel_start = time.time()
        max_reel_time = 35.0

        while self.is_active and self.is_running and (time.time() - reel_start < max_reel_time):
            self.mouse_ctrl.press(mouse.Button.left)
            time.sleep(0.02)
            self.mouse_ctrl.release(mouse.Button.left)
            time.sleep(self.click_speed)

            check_counter += 1
            if check_counter % 5 == 0:
                if not self.is_reeling_active(sct):
                    break

        self.mouse_ctrl.release(mouse.Button.left)
        play_sound("Hero")
        print("🏆 [CAUGHT!] Fish successfully caught!")
        print(f"⏳ Waiting {self.post_catch_delay}s for catch banner to clear before next cast...")
        time.sleep(self.post_catch_delay)

    def auto_loop(self):
        """Autonomous loop: Cast -> Wait for Bite -> Reel -> Repeat."""
        with mss.MSS() as sct:
            while self.is_running:
                if not self.is_active:
                    time.sleep(0.2)
                    continue

                # Step 1: Cast 2.0x
                self.cast_perfect_rod(sct)

                if not self.is_active or not self.is_running:
                    break

                # Step 2: Wait for Bite
                print("🐟 [2/3 WAITING] Bobber in water... Waiting for fish to bite...")
                bite_start = time.time()
                bite_timeout = 40.0
                bitten = False

                while time.time() - bite_start < bite_timeout and self.is_active and self.is_running:
                    if self.is_reeling_active(sct):
                        bitten = True
                        break
                    time.sleep(0.05)

                if not self.is_active or not self.is_running:
                    break

                # Step 3: Reel
                if bitten:
                    self.reel_fish_in(sct)
                else:
                    print("⚠️ [NO BITE] Timeout. Recasting...")

    def start_bot(self):
        if not self.is_active:
            self.is_active = True
            play_sound("Tink")
            print("\n🟢 >>> AUTO-FISHING BOT ACTIVE! <<<")
            if self.worker_thread is None or not self.worker_thread.is_alive():
                self.worker_thread = threading.Thread(target=self.auto_loop, daemon=True)
                self.worker_thread.start()

    def pause_bot(self):
        if self.is_active:
            self.is_active = False
            self.mouse_ctrl.release(mouse.Button.left)
            play_sound("Blow")
            print("\n⏸️ >>> BOT PAUSED <<< (Press [ENTER] or [P] to resume)")

    def run(self):
        print("=" * 65)
        print(" 🎣 FISH IT - 100% AUTONOMOUS BOT (DYNAMIC TRACKING)")
        print("=" * 65)
        print(" Features:")
        print("   • Dynamic Bar Tracking: Releases when 2.0x green arrives,")
        print("     regardless of whether the game charges slowly or quickly!")
        print("   • Zero-overflow color math: Day and Night lighting immune.")
        print("-" * 65)
        print(" Controls:")
        print("   • Press [ENTER] : START the infinite auto-fishing loop")
        print("   • Press [P]     : PAUSE / RESUME loop anytime")
        print("   • Press [Q]     : QUIT the bot safely")
        print("=" * 65)
        print("\n🚀 Ready! Switch to Roblox and press [ENTER] to start!\n")

        play_sound("Tink")

        def on_press(key):
            try:
                if key == keyboard.Key.enter:
                    if not self.is_active:
                        self.start_bot()
                elif hasattr(key, "char") and key.char:
                    char = key.char.lower()
                    if char == 'p':
                        if self.is_active:
                            self.pause_bot()
                        else:
                            self.start_bot()
                    elif char == 'q':
                        print("\n🛑 Quitting...")
                        self.is_running = False
                        self.is_active = False
                        self.mouse_ctrl.release(mouse.Button.left)
                        return False
            except Exception:
                pass

        listener = keyboard.Listener(on_press=on_press)
        listener.daemon = True
        listener.start()

        try:
            while self.is_running and listener.is_alive():
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.mouse_ctrl.release(mouse.Button.left)


def main():
    cfg = load_config()
    fisher = InfiniteAutoFisher(cfg)
    fisher.run()


if __name__ == "__main__":
    main()
