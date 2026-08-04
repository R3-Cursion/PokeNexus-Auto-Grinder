import cv2
import numpy as np
import pyautogui
import time
import random
import keyboard
import winsound
import os
import serial
import threading
import tkinter as tk
from tkinter import ttk, messagebox

# ==========================================
# CONFIGURATION
# ==========================================
SECONDS_PER_BLOCK = 1.0 / 7.0 
DEFAULT_BOUND_LEFT = -7.0
DEFAULT_BOUND_RIGHT = 7.0

TARGET_IMAGES = ['target_1.png', 'target_2.png', 'target_3.png']
RARE_POPUP_IMAGE = 'base_image_rare_pokemon.png'
REFERENCE_FRAME_IMAGE = 'reference_frame.png'
DEBUG_FOLDER = 'debug'

# ==========================================
# ARDUINO SETUP
# ==========================================
arduino_connected = False
try:
    arduino = serial.Serial('COM3', 9600)
    time.sleep(2)
    arduino_connected = True
    print("✅ Arduino OLED Connected!")
except Exception:
    print("⚠️ Arduino not found. Running on PC screen only.")

def send_to_oled(msg):
    if arduino_connected:
        short_msg = msg[:21] 
        try:
            arduino.write((short_msg + '\n').encode())
        except Exception:
            pass

# ==========================================
# GUI & BOT APP CLASS
# ==========================================
class AutoGrinderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("PokeNexus Auto Grinder")
        self.root.geometry("380x510")
        self.root.resizable(False, False)
        self.root.attributes('-topmost', True)
        self.root.configure(padx=15, pady=15)

        # Internal Bot States
        self.is_running = False
        self.bot_thread = None

        self.MASTER_ROI = None
        self.BATTLE_ROI = None

        self.current_pos = 0.0
        self.target_pos = 0.0
        self.currently_held_key = None
        self.last_tick_time = 0.0
        self.last_oled_update = 0.0

        self.target_templates = []
        self.rare_popup_template = None
        self.reference_template = None

        # Movement Bound Variables for GUI
        self.bound_left_val = DEFAULT_BOUND_LEFT
        self.bound_right_val = DEFAULT_BOUND_RIGHT
        
        self.bound_left_var = tk.StringVar(value=f"{self.bound_left_val:.1f}")
        self.bound_right_var = tk.StringVar(value=f"{self.bound_right_val:.1f}")

        # Build UI Components
        self.create_widgets()
        self.setup_debug_folder()
        self.load_templates()

        # Update Arduino Status on GUI
        ard_status = "Connected (COM3)" if arduino_connected else "Not Connected"
        self.arduino_label.config(text=f"Arduino: {ard_status}")

    def create_widgets(self):
        # Header
        tk.Label(self.root, text="PokeNexus Auto Grinder", font=("Segoe UI", 14, "bold")).pack(pady=(0, 5))
        
        # Status Card
        self.status_frame = tk.LabelFrame(self.root, text=" System Status ", font=("Segoe UI", 9, "bold"), padx=10, pady=8)
        self.status_frame.pack(fill="x", pady=4)

        self.status_label = tk.Label(self.status_frame, text="Status: IDLE", font=("Segoe UI", 10, "bold"), fg="gray")
        self.status_label.pack(anchor="w")

        self.arduino_label = tk.Label(self.status_frame, text="Arduino: Checking...", font=("Segoe UI", 9), fg="#555")
        self.arduino_label.pack(anchor="w")

        # Movement Bounds Card
        self.bounds_frame = tk.LabelFrame(self.root, text=" Movement Bounds (Blocks) ", font=("Segoe UI", 9, "bold"), padx=10, pady=8)
        self.bounds_frame.pack(fill="x", pady=4)

        bounds_grid = tk.Frame(self.bounds_frame)
        bounds_grid.pack(fill="x")

        # Left Bound +/- Controls
        tk.Label(bounds_grid, text="Left:", font=("Segoe UI", 9)).grid(row=0, column=0, padx=(0, 5), sticky="w")
        left_ctrl = tk.Frame(bounds_grid)
        left_ctrl.grid(row=0, column=1, padx=(0, 15))
        
        tk.Button(left_ctrl, text="-", width=2, command=lambda: self.adjust_bound('left', -1.0)).pack(side="left")
        tk.Label(left_ctrl, textvariable=self.bound_left_var, width=5, font=("Segoe UI", 9, "bold")).pack(side="left")
        tk.Button(left_ctrl, text="+", width=2, command=lambda: self.adjust_bound('left', 1.0)).pack(side="left")

        # Right Bound +/- Controls
        tk.Label(bounds_grid, text="Right:", font=("Segoe UI", 9)).grid(row=0, column=2, padx=(0, 5), sticky="w")
        right_ctrl = tk.Frame(bounds_grid)
        right_ctrl.grid(row=0, column=3)
        
        tk.Button(right_ctrl, text="-", width=2, command=lambda: self.adjust_bound('right', -1.0)).pack(side="left")
        tk.Label(right_ctrl, textvariable=self.bound_right_var, width=5, font=("Segoe UI", 9, "bold")).pack(side="left")
        tk.Button(right_ctrl, text="+", width=2, command=lambda: self.adjust_bound('right', 1.0)).pack(side="left")

        # Telemetry Card
        self.telemetry_frame = tk.LabelFrame(self.root, text=" Live Vision Metrics ", font=("Segoe UI", 9, "bold"), padx=10, pady=8)
        self.telemetry_frame.pack(fill="x", pady=4)

        self.ui_match_label = tk.Label(self.telemetry_frame, text="UI Frame Match:  0.0%", font=("Segoe UI", 9))
        self.ui_match_label.pack(anchor="w")

        self.rare_sim_label = tk.Label(self.telemetry_frame, text="Rare Popup Sim:  0.0%", font=("Segoe UI", 9))
        self.rare_sim_label.pack(anchor="w")

        self.target_sim_label = tk.Label(self.telemetry_frame, text="Target Match Sim: 0.0%", font=("Segoe UI", 9))
        self.target_sim_label.pack(anchor="w")

        # Controls Card
        self.controls_frame = tk.Frame(self.root)
        self.controls_frame.pack(fill="x", pady=8)

        self.start_btn = tk.Button(self.controls_frame, text="▶ START BOT", font=("Segoe UI", 10, "bold"), 
                                   bg="#4CAF50", fg="white", width=16, height=2, command=self.start_bot)
        self.start_btn.pack(side="left", padx=5)

        self.stop_btn = tk.Button(self.controls_frame, text="⏹ STOP BOT (Q)", font=("Segoe UI", 10, "bold"), 
                                  bg="#f44336", fg="white", width=16, height=2, state="disabled", command=self.stop_bot)
        self.stop_btn.pack(side="right", padx=5)

        # Bottom Utilities
        tk.Button(self.root, text="📂 Open Debug Folder", font=("Segoe UI", 9), command=self.open_debug_folder).pack(fill="x", pady=(4, 0))

    def adjust_bound(self, side, amount):
        """Increases or decreases the bounds safely while enforcing limits."""
        if side == 'left':
            new_val = self.bound_left_val + amount
            # Must stay between -12 and +12, and cannot be greater than or equal to the Right Bound
            if -12.0 <= new_val <= 12.0 and new_val < self.bound_right_val:
                self.bound_left_val = new_val
                self.bound_left_var.set(f"{self.bound_left_val:.1f}")
        elif side == 'right':
            new_val = self.bound_right_val + amount
            # Must stay between -12 and +12, and cannot be less than or equal to the Left Bound
            if -12.0 <= new_val <= 12.0 and new_val > self.bound_left_val:
                self.bound_right_val = new_val
                self.bound_right_var.set(f"{self.bound_right_val:.1f}")

    def get_bounds(self):
        """Returns the active bounds for the movement logic."""
        return self.bound_left_val, self.bound_right_val

    def setup_debug_folder(self):
        if not os.path.exists(DEBUG_FOLDER):
            os.makedirs(DEBUG_FOLDER)

    def open_debug_folder(self):
        try:
            os.startfile(os.path.abspath(DEBUG_FOLDER))
        except Exception:
            pass

    def load_templates(self):
        send_to_oled("Loading AI Vision...")
        
        for photo_name in TARGET_IMAGES:
            if os.path.exists(photo_name):
                img = cv2.imread(photo_name)
                if img is not None:
                    self.target_templates.append((photo_name, img))
            
        if os.path.exists(RARE_POPUP_IMAGE):
            self.rare_popup_template = cv2.imread(RARE_POPUP_IMAGE)
            
        if os.path.exists(REFERENCE_FRAME_IMAGE):
            self.reference_template = cv2.imread(REFERENCE_FRAME_IMAGE)

        if not self.target_templates or self.reference_template is None:
            messagebox.showerror("Error", "Missing required image files!\nEnsure reference_frame.png & targets exist.")
            send_to_oled("ERR: Vision Failed")
        else:
            send_to_oled("Vision Ready.")

    def set_status(self, text, color):
        self.status_label.config(text=f"Status: {text}", fg=color)

    # ==========================================
    # BOT MOVEMENT & COMBAT HELPERS
    # ==========================================
    def human_sleep(self, base, variance):
        time.sleep(max(0.01, random.gauss(base, variance)))

    def release_movement(self):
        if self.currently_held_key:
            keyboard.release(self.currently_held_key)
            self.currently_held_key = None

    def execute_kill(self):
        print("Executing Kill Sequence (1 -> 1)...")
        send_to_oled("Action: Attack")
        time.sleep(2.5) # Wait for battle animation to finish
        keyboard.send('1') 
        self.human_sleep(0.10, 0.03)
        keyboard.send('1')
        
        send_to_oled("Waiting turn")
        time.sleep(4.0)

    def play_alarm(self):
        send_to_oled("PAUSED! Check PC")
        for _ in range(5):
            winsound.Beep(1500, 400)
            time.sleep(0.1)

    def pick_new_destination(self):
        b_left, b_right = self.get_bounds()
        self.target_pos = random.uniform(b_left, b_right)

    def update_movement_hold(self):
        now = time.time()
        delta_time = now - self.last_tick_time
        self.last_tick_time = now
        
        b_left, b_right = self.get_bounds()

        if self.currently_held_key:
            blocks_moved = delta_time / SECONDS_PER_BLOCK
            self.current_pos += blocks_moved if self.currently_held_key == 'd' else -blocks_moved
            self.current_pos = max(b_left, min(b_right, self.current_pos))
            
        distance = self.target_pos - self.current_pos
        
        if abs(distance) < 0.2: 
            self.release_movement()
            return True 
            
        direction = 'd' if distance > 0 else 'a'
        
        if self.currently_held_key != direction:
            self.release_movement()
            keyboard.press(direction)
            self.currently_held_key = direction
            
        return False

    # ==========================================
    # MAIN BOT LOOP (BACKGROUND THREAD)
    # ==========================================
    def start_bot(self):
        if not self.is_running:
            self.is_running = True
            self.start_btn.config(state="disabled")
            self.stop_btn.config(state="normal")
            
            self.bot_thread = threading.Thread(target=self.run_bot_loop, daemon=True)
            self.bot_thread.start()

    def stop_bot(self):
        self.is_running = False

    def run_bot_loop(self):
        print("=======================================")
        print(" Auto Grinder Active")
        print("=======================================")
        
        send_to_oled("Starting in 3s...")
        time.sleep(3)
        self.pick_new_destination()
        
        self.last_tick_time = time.time()
        self.last_oled_update = time.time()
        send_to_oled("Bot Active")

        try:
            while self.is_running and not keyboard.is_pressed('q'):
                
                # PHASE 1: INITIALIZATION (FIND ROIs)
                if self.MASTER_ROI is None:
                    self.set_status("Searching UI...", "#ff9800")
                    screenshot = pyautogui.screenshot()
                    full_screen_frame = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
                    result = cv2.matchTemplate(full_screen_frame, self.reference_template, cv2.TM_CCOEFF_NORMED)
                    _, ref_max_val, _, ref_max_loc = cv2.minMaxLoc(result)
                    
                    ref_sim = ref_max_val * 100
                    self.ui_match_label.config(text=f"UI Frame Match:  {ref_sim:.1f}%")

                    if (time.time() - self.last_oled_update > 1.0):
                        send_to_oled(f"Hunt Sim: {ref_sim:.0f}%")
                        self.last_oled_update = time.time()
                    
                    if ref_sim >= 70.0:
                        self.release_movement()
                        
                        th, tw = self.reference_template.shape[:2]
                        base_x, base_y = int(ref_max_loc[0]), int(ref_max_loc[1])
                        self.MASTER_ROI = (base_x, base_y, int(tw), int(th))
                        self.BATTLE_ROI = (base_x + (tw // 2), base_y, tw // 2, th // 2)
                        
                        send_to_oled("Encounter Found!")
                        time.sleep(1.0)
                        continue 
                    else:
                        arrived = self.update_movement_hold()
                        if arrived:
                            time.sleep(max(0.05, random.gauss(0.2, 0.05)))
                            self.pick_new_destination()
                            self.last_tick_time = time.time() 
                        continue

                # PHASE 2: PERMANENT LOOP
                else:
                    self.set_status("Active Battle Loop", "#4CAF50")
                    
                    screenshot_master = pyautogui.screenshot(region=self.MASTER_ROI)
                    master_frame = cv2.cvtColor(np.array(screenshot_master), cv2.COLOR_RGB2BGR)
                    cv2.imwrite(os.path.join(DEBUG_FOLDER, "master_roi.png"), master_frame)
                    
                    # Rare Check
                    rare_sim = 0.0
                    if self.rare_popup_template is not None:
                        res_rare = cv2.matchTemplate(master_frame, self.rare_popup_template, cv2.TM_CCOEFF_NORMED)
                        _, max_val_rare, _, _ = cv2.minMaxLoc(res_rare)
                        rare_sim = max_val_rare * 100
                        
                    self.rare_sim_label.config(text=f"Rare Popup Sim:  {rare_sim:.1f}%")

                    if rare_sim >= 75.0:
                        self.release_movement()
                        self.set_status("🚨 RARE DETECTED!", "red")
                        send_to_oled(f"*** RARE {rare_sim:.0f}% ***")
                        cv2.imwrite(os.path.join(DEBUG_FOLDER, "rare_detected.png"), master_frame)
                        self.play_alarm()
                        break 
                    
                    # Target Check
                    screenshot_battle = pyautogui.screenshot(region=self.BATTLE_ROI)
                    battle_frame = cv2.cvtColor(np.array(screenshot_battle), cv2.COLOR_RGB2BGR)
                    cv2.imwrite(os.path.join(DEBUG_FOLDER, "battle_roi.png"), battle_frame)
                    
                    highest_sim = 0.0
                    best_match_name = None
                    
                    for name, template in self.target_templates:
                        th, tw = template.shape[:2]
                        if th <= battle_frame.shape[0] and tw <= battle_frame.shape[1]:
                            res_target = cv2.matchTemplate(battle_frame, template, cv2.TM_CCOEFF_NORMED)
                            _, max_val_target, _, _ = cv2.minMaxLoc(res_target)
                            sim = max_val_target * 100
                            
                            if sim > highest_sim:
                                highest_sim = sim
                                best_match_name = name

                    self.target_sim_label.config(text=f"Target Match Sim: {highest_sim:.1f}%")

                    if (time.time() - self.last_oled_update > 1.0):
                        send_to_oled(f"Target Sim: {highest_sim:.0f}%")
                        self.last_oled_update = time.time()
                    
                    if highest_sim >= 30.0:
                        self.release_movement()
                        self.execute_kill()
                        self.last_tick_time = time.time() 
                    else:
                        arrived = self.update_movement_hold()
                        if arrived:
                            time.sleep(max(0.05, random.gauss(0.2, 0.05)))
                            self.pick_new_destination()
                            self.last_tick_time = time.time() 
                        
        finally:
            self.release_movement()
            keyboard.release('a')
            keyboard.release('d')
            self.is_running = False
            self.set_status("IDLE", "gray")
            self.start_btn.config(state="normal")
            self.stop_btn.config(state="disabled")
            send_to_oled("Bot Offline")


if __name__ == "__main__":
    root = tk.Tk()
    app = AutoGrinderGUI(root)
    root.mainloop()