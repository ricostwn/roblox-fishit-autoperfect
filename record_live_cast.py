"""
Screen Recorder & Frame Analyzer for Fish It
Records a live cast at high FPS, saves the frame sequence,
and automatically analyzes the exact pixel color transitions.
"""

import json
import os
import shutil
import time
from AppKit import NSWorkspace, NSApplicationActivateIgnoringOtherApps
import mss
import numpy as np
from PIL import Image
from pynput import mouse

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cast_frames")


def focus_roblox():
    ws = NSWorkspace.sharedWorkspace()
    for a in ws.runningApplications():
        if a.bundleIdentifier() == "com.roblox.RobloxPlayer":
            a.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
            return True
    return False


def record_cast():
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 65)
    print(" 🎥 RECORDING LIVE CAST IN ROBLOX")
    print("=" * 65)
    print("[1] Focusing Roblox window...")
    focus_roblox()
    time.sleep(0.5)

    mouse_ctrl = mouse.Controller()
    # Move mouse to safe center
    mouse_ctrl.position = (735, 450)
    time.sleep(0.3)

    print("[2] Pressing Left Click to start charge...")
    mouse_ctrl.press(mouse.Button.left)

    # Capture a 120px wide by 220px tall box around the bar:
    # X from 800 to 920, Y from 370 to 590
    monitor = {
        "top": 370,
        "left": 800,
        "width": 120,
        "height": 220
    }

    frames = []
    start_time = time.time()

    with mss.MSS() as sct:
        while time.time() - start_time < 1.6:
            raw = sct.grab(monitor)
            t = time.time() - start_time
            img_arr = np.array(raw)
            frames.append((t, img_arr))
            time.sleep(0.015)  # ~60 FPS

    mouse_ctrl.release(mouse.Button.left)
    print(f"[3] Released Left Click! Captured {len(frames)} frames over 1.6 seconds.")

    print(f"[4] Saving key sample frames to {OUTPUT_DIR}...")
    # Save every 3rd frame as PNG for inspection
    saved_paths = []
    for idx, (t, arr) in enumerate(frames):
        if idx % 3 == 0 or idx == len(frames) - 1:
            # Convert BGRA to RGB
            rgb_arr = arr[:, :, [2, 1, 0]]
            img = Image.fromarray(rgb_arr)
            filename = f"frame_{idx:03d}_{int(t*1000):04d}ms.png"
            path = os.path.join(OUTPUT_DIR, filename)
            img.save(path)
            saved_paths.append((t, path))

    print(f"✅ Saved {len(saved_paths)} frames.")
    return frames


if __name__ == "__main__":
    record_cast()

