"""
Fish It - Modern macOS Dark-Mode Gaming Overlay (CustomTkinter)
Proportional, clean, high-DPI floating HUD for Roblox Fish It.
"""

import json
import os
import subprocess
import sys
import threading
import time
import cv2
import customtkinter as ctk
import mss
import numpy as np
from pynput import mouse

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def play_sound(sound_name):
    """Play macOS system audio chime in background."""
    path = f"/System/Library/Sounds/{sound_name}.aiff"
    if os.path.exists(path):
        try:
            subprocess.Popen(["afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "target_x": 845,
        "target_y": 415,
        "stop_button_x": 1095,
        "stop_button_y": 816,
        "cast_settle_delay": 1.5,
        "post_catch_delay": 2.2,
        "click_speed": 0.025,
        "always_on_top": True
    }


def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


def is_peak_green(pixel):
    """Detects 2.0x Luck green fill without uint8 overflow."""
    r, g, b = int(pixel[0]), int(pixel[1]), int(pixel[2])
    return (g > 140) and (g - r > 45) and (g - b > 45)


def focus_roblox_window():
    """Brings Roblox directly to the front and activates the window."""
    try:
        from AppKit import NSWorkspace, NSApplicationActivateIgnoringOtherApps
        ws = NSWorkspace.sharedWorkspace()
        apps = ws.runningApplications()
        roblox = [a for a in apps if a.bundleIdentifier() == "com.roblox.RobloxPlayer"]
        if roblox:
            roblox[0].activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
            return True
    except Exception:
        pass
    return False


class FishingEngine:
    def __init__(self, on_status_change, on_catch, on_cast):
        self.cfg = load_config()
        self.target_x = self.cfg.get("target_x", 845)
        self.target_y = self.cfg.get("target_y", 416)
        self.stop_x = self.cfg.get("stop_button_x", 1095)
        self.stop_y = self.cfg.get("stop_button_y", 816)

        self.cast_settle_delay = self.cfg.get("cast_settle_delay", 1.5)
        self.post_catch_delay = self.cfg.get("post_catch_delay", 2.2)
        self.click_speed = self.cfg.get("click_speed", 0.025)

        self.on_status_change = on_status_change
        self.on_catch = on_catch
        self.on_cast = on_cast

        # Load OpenCV templates for dynamic vision
        templ_charge_path = os.path.join(TEMPLATES_DIR, "charge_label.png")
        templ_stop_path = os.path.join(TEMPLATES_DIR, "stop_button.png")
        self.templ_charge = cv2.imread(templ_charge_path, cv2.IMREAD_GRAYSCALE) if os.path.exists(templ_charge_path) else None
        self.templ_stop = cv2.imread(templ_stop_path, cv2.IMREAD_GRAYSCALE) if os.path.exists(templ_stop_path) else None

        self.mouse_ctrl = mouse.Controller()
        self.is_running = True
        self.is_active = False
        self.worker_thread = None

    def update_post_catch_delay(self, val):
        self.post_catch_delay = round(float(val), 1)
        self.cfg["post_catch_delay"] = self.post_catch_delay
        save_config(self.cfg)

    def is_reeling_active(self, sct):
        # Scan bottom-right area where STOP button appears: x=[1050, 1200], y=[770, 860]
        box = {
            "top": 770,
            "left": 1050,
            "width": 150,
            "height": 90
        }
        raw = np.array(sct.grab(box))

        # 1. OpenCV template matching for STOP button
        if self.templ_stop is not None:
            gray = cv2.cvtColor(raw, cv2.COLOR_BGRA2GRAY)
            res = cv2.matchTemplate(gray, self.templ_stop, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(res)
            if max_val > 0.70:
                return True

        # 2. Color fallback
        pixels_rgb = raw[:, :, [2, 1, 0]]
        for row in pixels_rgb:
            for p in row:
                r, g, b = int(p[0]), int(p[1]), int(p[2])
                if r > 165 and g < 100 and b < 120 and (r - g > 60):
                    return True
        return False

    def did_fish_escape(self, sct):
        """Checks if 'The fish got away!' red banner appears at (733, 179)."""
        box = {
            "top": 172,
            "left": 713,
            "width": 40,
            "height": 15
        }
        raw = sct.grab(box)
        img = np.array(raw)
        pixels_rgb = img[:, :, [2, 1, 0]]
        red_count = 0
        for row in pixels_rgb:
            for p in row:
                r, g, b = int(p[0]), int(p[1]), int(p[2])
                if r > 160 and g < 95 and b < 85 and (r - g > 65):
                    red_count += 1
        return red_count >= 5

    def cast_perfect_rod(self, sct):
        self.on_status_change("🎣 CASTING (CV Tracking)...", "#38bdf8")
        self.mouse_ctrl.press(mouse.Button.left)

        # Wide dynamic search area around character: x=[750, 950], y=[340, 600]
        # (width=200, height=260) - completely covers camera shifts and rotations!
        search_box = {
            "top": 340,
            "left": 750,
            "width": 200,
            "height": 260
        }

        start = time.time()
        timeout = 2.2
        hit = False

        while time.time() - start < timeout and self.is_active and self.is_running:
            # Physical safety guard: bar takes at least 450ms to reach 2.0x
            if time.time() - start < 0.45:
                time.sleep(0.01)
                continue

            raw = np.array(sct.grab(search_box))

            # Dynamic OpenCV Template Tracking
            if self.templ_charge is not None:
                gray = cv2.cvtColor(raw, cv2.COLOR_BGRA2GRAY)
                res = cv2.matchTemplate(gray, self.templ_charge, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(res)

                if max_val > 0.65:
                    ax, ay = max_loc
                    # Dynamic 2.0x peak point relative to found anchor:
                    px = ax + 20
                    py = ay - 129

                    if 0 <= py < raw.shape[0] and 0 <= px < raw.shape[1]:
                        # Check 3x3 pixel area around dynamic peak for green
                        peak_crop = raw[max(0, py-1):py+2, max(0, px-1):px+2, [2, 1, 0]]
                        for row in peak_crop:
                            for p in row:
                                if is_peak_green(p):
                                    hit = True
                                    break
                            if hit:
                                break

            # Fallback fixed check if template wasn't matched
            if not hit:
                p = raw[416-340, 845-750, [2, 1, 0]]
                if is_peak_green(p):
                    hit = True

            if hit:
                break
            time.sleep(0.001)

        self.mouse_ctrl.release(mouse.Button.left)

        if hit:
            play_sound("Hero")
            self.on_status_change("🎯 PERFECT 2.0x CAST!", "#10b981")
            self.on_cast(perfect=True)
        else:
            self.on_status_change("⏱️ Cast Timeout", "#f43f5e")
            self.on_cast(perfect=False)

        time.sleep(self.cast_settle_delay)

    def reel_fish_in(self, sct):
        self.on_status_change("🌀 REELING FISH...", "#f59e0b")
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
        time.sleep(0.35)  # Wait for catch or escape banner to render

        if self.did_fish_escape(sct):
            play_sound("Blow")
            self.on_status_change("⚠️ FISH GOT AWAY!", "#f43f5e")
        else:
            play_sound("Hero")
            self.on_catch()
            self.on_status_change("🏆 FISH CAUGHT!", "#10b981")

        time.sleep(self.post_catch_delay)

    def auto_loop(self):
        with mss.MSS() as sct:
            while self.is_running:
                if not self.is_active:
                    time.sleep(0.2)
                    continue

                # Step 1: Cast
                self.cast_perfect_rod(sct)

                if not self.is_active or not self.is_running:
                    break

                # Step 2: Wait for bite
                self.on_status_change("🐟 WAITING FOR BITE...", "#06b6d4")
                bite_start = time.time()
                bitten = False

                while time.time() - bite_start < 40.0 and self.is_active and self.is_running:
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
                    self.on_status_change("⚠️ Bite Timeout -> Recasting", "#eab308")

    def start(self, auto_focus=True):
        if not self.is_active:
            self.is_active = True
            play_sound("Tink")

            def run_starter():
                if auto_focus:
                    self.on_status_change("🚀 Focusing Roblox...", "#38bdf8")
                    focus_roblox_window()
                    # Move mouse into Roblox viewport (center of screen, away from GUI)
                    self.mouse_ctrl.position = (735, 450)
                    time.sleep(0.35)  # Let macOS window focus settle

                self.on_status_change("🟢 RUNNING (Loop Active)", "#10b981")
                self.auto_loop()

            if self.worker_thread is None or not self.worker_thread.is_alive():
                self.worker_thread = threading.Thread(target=run_starter, daemon=True)
                self.worker_thread.start()

    def pause(self):
        if self.is_active:
            self.is_active = False
            self.mouse_ctrl.release(mouse.Button.left)
            play_sound("Blow")
            self.on_status_change("⏸️ PAUSED (Press Start or Enter)", "#94a3b8")

    def toggle(self):
        if self.is_active:
            self.pause()
        else:
            self.start()

    def shutdown(self):
        self.is_running = False
        self.is_active = False
        self.mouse_ctrl.release(mouse.Button.left)


class ModernOverlayApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Appearance configuration
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        self.title("Fish It")
        self.geometry("340x480")
        self.resizable(False, False)

        self.cfg = load_config()
        self.always_on_top = self.cfg.get("always_on_top", True)
        self.wm_attributes("-topmost", self.always_on_top)

        # Stats
        self.catches = 0
        self.perfect_casts = 0
        self.total_casts = 0
        self.session_start = None

        # Engine
        self.engine = FishingEngine(
            on_status_change=self.safe_set_status,
            on_catch=self.safe_add_catch,
            on_cast=self.safe_add_cast
        )

        self.build_ui()
        self.update_timer()

    def build_ui(self):
        # Main container with 16px margins
        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True, padx=16, pady=16)

        # 1. Header Row
        header_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 12))

        title_label = ctk.CTkLabel(
            header_frame,
            text="🎣 Fish It",
            font=ctk.CTkFont(family="SF Pro Display", size=18, weight="bold"),
            text_color="#f8fafc"
        )
        title_label.pack(side="left")

        self.ontop_switch = ctk.CTkSwitch(
            header_frame,
            text="Pin HUD",
            font=ctk.CTkFont(size=11),
            text_color="#94a3b8",
            progress_color="#3b82f6",
            command=self.toggle_pin,
            width=36,
            height=18
        )
        if self.always_on_top:
            self.ontop_switch.select()
        self.ontop_switch.pack(side="right")

        # 2. Live Status Banner Card
        self.status_card = ctk.CTkFrame(
            self.container,
            fg_color="#1e293b",
            corner_radius=12,
            border_width=1,
            border_color="#334155"
        )
        self.status_card.pack(fill="x", pady=(0, 12))

        self.status_text = ctk.CTkLabel(
            self.status_card,
            text="⏸️ PAUSED (Ready)",
            font=ctk.CTkFont(family="SF Pro Text", size=13, weight="bold"),
            text_color="#94a3b8"
        )
        self.status_text.pack(pady=(10, 2))

        timer_row = ctk.CTkFrame(self.status_card, fg_color="transparent")
        timer_row.pack(fill="x", padx=12, pady=(0, 8))

        self.timer_text = ctk.CTkLabel(
            timer_row,
            text="⏱️ 00:00:00",
            font=ctk.CTkFont(family="SF Pro Text", size=11),
            text_color="#64748b"
        )
        self.timer_text.pack(side="left")

        self.reset_btn = ctk.CTkButton(
            timer_row,
            text="↺ Reset",
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#334155",
            hover_color="#475569",
            text_color="#94a3b8",
            corner_radius=6,
            width=54,
            height=20,
            command=self.reset_stats
        )
        self.reset_btn.pack(side="right")

        # 3. Two-Column Stats Cards (Equal 50/50 proportion)
        stats_row = ctk.CTkFrame(self.container, fg_color="transparent")
        stats_row.pack(fill="x", pady=(0, 14))

        # Left Card: Perfect Casts Ratio & Accuracy
        perfect_card = ctk.CTkFrame(
            stats_row,
            fg_color="#1e293b",
            corner_radius=10,
            border_width=1,
            border_color="#334155"
        )
        perfect_card.pack(side="left", fill="both", expand=True, padx=(0, 6))

        ctk.CTkLabel(
            perfect_card,
            text="PERFECT 2.0x",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#64748b"
        ).pack(pady=(8, 0))

        self.perfect_ratio_lbl = ctk.CTkLabel(
            perfect_card,
            text="0 / 0",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#38bdf8"
        )
        self.perfect_ratio_lbl.pack(pady=(0, 0))

        self.accuracy_lbl = ctk.CTkLabel(
            perfect_card,
            text="100.0% Accuracy",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#10b981"
        )
        self.accuracy_lbl.pack(pady=(0, 8))

        # Right Card: Fish Catches
        catch_card = ctk.CTkFrame(
            stats_row,
            fg_color="#1e293b",
            corner_radius=10,
            border_width=1,
            border_color="#334155"
        )
        catch_card.pack(side="right", fill="both", expand=True, padx=(6, 0))

        ctk.CTkLabel(
            catch_card,
            text="FISH CAUGHT",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#64748b"
        ).pack(pady=(8, 0))

        self.catches_label = ctk.CTkLabel(
            catch_card,
            text="0",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#10b981"
        )
        self.catches_label.pack(pady=(0, 0))

        self.catch_sub_lbl = ctk.CTkLabel(
            catch_card,
            text="Reeled In",
            font=ctk.CTkFont(size=10),
            text_color="#64748b"
        )
        self.catch_sub_lbl.pack(pady=(0, 8))

        # 4. Action Buttons (Side by Side)
        btn_row = ctk.CTkFrame(self.container, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 14))

        self.start_btn = ctk.CTkButton(
            btn_row,
            text="▶ START",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#10b981",
            hover_color="#059669",
            text_color="#ffffff",
            corner_radius=10,
            height=42,
            command=self.on_start_click
        )
        self.start_btn.pack(side="left", fill="both", expand=True, padx=(0, 6))

        self.pause_btn = ctk.CTkButton(
            btn_row,
            text="⏸ PAUSE",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#f59e0b",
            hover_color="#d97706",
            text_color="#ffffff",
            corner_radius=10,
            height=42,
            command=self.on_pause_click
        )
        self.pause_btn.pack(side="right", fill="both", expand=True, padx=(6, 0))

        # 5. Settings Card
        settings_card = ctk.CTkFrame(
            self.container,
            fg_color="#1e293b",
            corner_radius=10,
            border_width=1,
            border_color="#334155"
        )
        settings_card.pack(fill="x", pady=(0, 12), padx=0)

        # Catch delay slider row
        delay_header = ctk.CTkFrame(settings_card, fg_color="transparent")
        delay_header.pack(fill="x", padx=12, pady=(8, 2))

        ctk.CTkLabel(
            delay_header,
            text="Catch Delay",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#94a3b8"
        ).pack(side="left")

        self.delay_val_lbl = ctk.CTkLabel(
            delay_header,
            text=f"{self.engine.post_catch_delay}s",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#38bdf8"
        )
        self.delay_val_lbl.pack(side="right")

        self.delay_slider = ctk.CTkSlider(
            settings_card,
            from_=1.0,
            to=4.0,
            number_of_steps=30,
            progress_color="#38bdf8",
            button_color="#f8fafc",
            button_hover_color="#e2e8f0",
            command=self.on_slider_move,
            height=14
        )
        self.delay_slider.set(self.engine.post_catch_delay)
        self.delay_slider.pack(fill="x", padx=12, pady=(0, 10))

        # 6. Minimal Footer
        ctk.CTkLabel(
            self.container,
            text="Fish It Assistant • Pure GUI Control",
            font=ctk.CTkFont(size=10),
            text_color="#64748b"
        ).pack(side="bottom")

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def toggle_pin(self):
        self.always_on_top = self.ontop_switch.get() == 1
        self.wm_attributes("-topmost", self.always_on_top)
        self.cfg["always_on_top"] = self.always_on_top
        save_config(self.cfg)

    def on_slider_move(self, val):
        rounded = round(float(val), 1)
        self.delay_val_lbl.configure(text=f"{rounded}s")
        self.engine.update_post_catch_delay(rounded)

    def on_start_click(self):
        if not self.engine.is_active:
            if self.session_start is None:
                self.session_start = time.time()
            self.engine.start(auto_focus=True)

    def on_pause_click(self):
        self.engine.pause()

    def safe_set_status(self, text, color):
        self.after(0, lambda: self.status_text.configure(text=text, text_color=color))

    def safe_add_catch(self):
        self.catches += 1
        self.after(0, self.update_stats_display)

    def safe_add_cast(self, perfect=True):
        self.total_casts += 1
        if perfect:
            self.perfect_casts += 1
        self.after(0, self.update_stats_display)

    def update_stats_display(self):
        self.catches_label.configure(text=str(self.catches))
        self.perfect_ratio_lbl.configure(text=f"{self.perfect_casts} / {self.total_casts}")
        
        acc = (self.perfect_casts / self.total_casts * 100.0) if self.total_casts > 0 else 100.0
        acc_color = "#10b981" if acc >= 90 else ("#f59e0b" if acc >= 75 else "#f43f5e")
        self.accuracy_lbl.configure(text=f"{acc:.1f}% Accuracy", text_color=acc_color)

    def reset_stats(self):
        self.catches = 0
        self.perfect_casts = 0
        self.total_casts = 0
        self.session_start = time.time() if self.engine.is_active else None
        self.update_stats_display()
        self.timer_text.configure(text="⏱️ 00:00:00")
        play_sound("Ping")

    def update_timer(self):
        if self.engine.is_active and self.session_start:
            elapsed = int(time.time() - self.session_start)
            mins, secs = divmod(elapsed, 60)
            hrs, mins = divmod(mins, 60)
            self.timer_text.configure(text=f"⏱️ {hrs:02d}:{mins:02d}:{secs:02d}")
        self.after(1000, self.update_timer)

    def on_close(self):
        self.engine.shutdown()
        self.destroy()
        sys.exit(0)


def main():
    app = ModernOverlayApp()
    app.mainloop()


if __name__ == "__main__":
    main()
