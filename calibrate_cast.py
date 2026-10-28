"""
Cast Timing Calibration & Diagnostics Tool
Records high-speed frames during a cast to show the exact millisecond timing of the 2.0x peak.
"""

import colorsys
import os
import time
import mss
import numpy as np
from pynput import mouse, keyboard

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def is_green_hsv(r, g, b):
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    # Green in HSV: Hue ~ 90-135 deg, Saturation > 0.45, Value > 0.45
    return (85 <= (h * 360) <= 140) and (s >= 0.45) and (v >= 0.45)


def main():
    print("=" * 65)
    print(" 🎯 FISH IT - CAST ACCURACY CALIBRATOR")
    print("=" * 65)
    print(" Instructions:")
    print("   1. Switch to Roblox.")
    print("   2. Press [ENTER] in-game to start a test throw.")
    print("   3. This tool will record the bar at 500+ FPS and analyze")
    print("      the exact peak of 2.0x Luck!")
    print("=" * 65)

    mouse_ctrl = mouse.Controller()

    with mss.MSS() as sct:
        def on_press(key):
            if key == keyboard.Key.enter:
                print("\n[+] Recording cast in real time...")
                mouse_ctrl.press(mouse.Button.left)

                # Monitor vertical slice from Y=385 to Y=410 at X=847
                monitor = {"top": 385, "left": 845, "width": 5, "height": 30}
                frames = []
                t0 = time.time()

                while time.time() - t0 < 1.8:
                    raw = sct.grab(monitor)
                    t = time.time() - t0
                    frames.append((t, np.array(raw)))
                    time.sleep(0.001)

                mouse_ctrl.release(mouse.Button.left)
                print(f"[+] Captured {len(frames)} frames over {frames[-1][0]:.2f}s!")

                # Analyze peak
                print("\nAnalyzing 2.0x Peak Detection:")
                peak_time = None
                for t, img in frames:
                    pixels_rgb = img[:, :, [2, 1, 0]]
                    # Check top rows (Y=390 to Y=395, which is index 5 to 10 in our 30px crop)
                    top_pixels = pixels_rgb[5:11, :, :]
                    green_count = 0
                    for row in top_pixels:
                        for p in row:
                            if is_green_hsv(p[0], p[1], p[2]):
                                green_count += 1

                    if green_count >= 2:
                        peak_time = t
                        print(f" -> 2.0x Peak reached at +{t*1000:.1f}ms! (Green pixel count: {green_count})")
                        break

                if peak_time:
                    print(f"\n✅ Peak detected accurately at {peak_time*1000:.1f}ms from cast start.")
                else:
                    print("\n⚠️ No green detected in top rows. Check if Roblox window moved.")

                print("\nPress [ENTER] to test again, or [Q] to exit.")

            elif hasattr(key, "char") and key.char and key.char.lower() == 'q':
                return False

        listener = keyboard.Listener(on_press=on_press)
        listener.daemon = True
        listener.start()

        try:
            while listener.is_alive():
                time.sleep(0.1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()

