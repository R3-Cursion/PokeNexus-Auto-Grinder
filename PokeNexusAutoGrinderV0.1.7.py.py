import cv2
import numpy as np
import pyautogui
import time
import random
import keyboard
import winsound
import os
import io
import wave
import ctypes
import json
import serial
import threading
import traceback
import tkinter as tk
from tkinter import messagebox, filedialog

pyautogui.FAILSAFE = False

# ==========================================
# CONFIGURATION
# ==========================================
DEFAULT_BLOCKS_PER_SEC = 7.0
DEFAULT_BOUND_LEFT = -7.0
DEFAULT_BOUND_RIGHT = 7.0

# Folders & Master Images
TARGETS_FOLDER = 'targets'
DEBUG_FOLDER = 'debug'
CAPTURED_ROIS_FOLDER = 'captured_rois'

# The permanent anchor base name used by the Screenshotter (supports .png, .jpg, .jpeg, .bmp)
SYSTEM_REF_IMAGE_NAME = 'system_reference_frame'
# The active anchor captured by the user and used by the Auto Grinder
REFERENCE_FRAME_IMAGE = 'reference_frame.png'
# The rare pokemon base image to detect and its target click image 'x'
RARE_BASE_IMAGE_NAME = 'base_image_rare_pokemon'
RARE_BASE_IMAGE_DEFAULT = 'base_image_rare_pokemon.png'
X_CLICK_IMAGE_NAME = 'x'
# Persistent JSON configuration file
CONFIG_FILE = 'bot_config.json'


# ==========================================
# 1. HARDWARE INTERFACE (Single Responsibility)
# ==========================================
class OledDisplay:
    def __init__(self, port='COM3', baud=9600):
        self.connected = False
        self.serial_conn = None
        self.last_update = 0.0
        self.port = port
        self.baud = baud
        self.connect(port, baud)

    def connect(self, port='COM3', baud=9600):
        if self.serial_conn:
            try:
                self.serial_conn.close()
            except Exception:
                pass
        self.connected = False
        self.serial_conn = None
        self.port = port
        self.baud = baud
        try:
            self.serial_conn = serial.Serial(port, int(baud))
            time.sleep(2)
            self.connected = True
            print(f"✅ Arduino OLED Connected ({port} @ {baud})!")
        except Exception:
            print(f"⚠️ Arduino not found on {port}. Running on PC screen only.")
        return self.connected

    def send(self, msg):
        if self.connected and self.serial_conn:
            short_msg = msg[:21]
            try:
                self.serial_conn.write((short_msg + '\n').encode())
            except Exception:
                pass

    def send_throttled(self, msg, interval=1.0):
        if (time.time() - self.last_update) > interval:
            self.send(msg)
            self.last_update = time.time()


# ==========================================
# 2. CONFIGURATION MANAGER (Single Responsibility)
# ==========================================
class ConfigManager:
    VALID_ACTIONS = ("kill_1", "kill_2", "kill_3", "kill_4", "catch", "alert")

    DEFAULT_CONFIG = {
        "movement": {
            "bound_left": DEFAULT_BOUND_LEFT,
            "bound_right": DEFAULT_BOUND_RIGHT,
            "key_left": "a",
            "key_right": "d",
            "blocks_per_sec": DEFAULT_BLOCKS_PER_SEC,
            "stop_pause": 0.2
        },
        "thresholds": {
            "ui_lock_sim": 40.0,
            "battle_ui_sim": 50.0,
            "target_sim": 94.0,
            "unrecog_sim": 30.0,
            "rare_base_sim": 45.0,
            "x_click_sim": 65.0
        },
        "timings": {
            "start_delay": 3.0,
            "hold_start_sec": 2.0,
            "battle_spawn_wait": 1.7,
            "action_cooldown": 3.2,
            "anim_grace_period": 2.5,
            "stuck_timeout": 300.0
        },
        "general": {
            "unrecognized_action": "ignore",
            "unrecognized_kill_move": 1,
            "auto_capture": False,
            "new_target_default_action": "ask",
            "enable_stuck_alarm": False,
            "enable_debug_screenshots": False,
            "start_hotkey": "e",
            "stop_hotkey": "q",
            "com_port": "COM3",
            "baud_rate": 9600
        },
        "kill_1": {
            "include_swap": False,
            "pre_delay": 0.2,
            "key_1": "1",
            "mid_delay": 0.10,
            "mid_var": 0.03,
            "key_2": "1",
            "post_delay": 1.0
        },
        "kill_2": {
            "include_swap": False,
            "pre_delay": 0.2,
            "key_1": "1",
            "mid_delay": 0.10,
            "mid_var": 0.03,
            "key_2": "2",
            "post_delay": 1.0
        },
        "kill_3": {
            "include_swap": False,
            "pre_delay": 0.2,
            "key_1": "1",
            "mid_delay": 0.10,
            "mid_var": 0.03,
            "key_2": "3",
            "post_delay": 1.0
        },
        "kill_4": {
            "include_swap": False,
            "pre_delay": 0.2,
            "key_1": "1",
            "mid_delay": 0.10,
            "mid_var": 0.03,
            "key_2": "4",
            "post_delay": 1.0
        },
        "swap": {
            "pre_delay": 1.0,
            "key_1": "3",
            "mid_delay": 0.10,
            "mid_var": 0.03,
            "key_2": "6",
            "post_delay": 3.3
        },
        "catch": {
            "include_swap": True,
            "pre_delay": 0.2,
            "key_1": "2",
            "mid_delay": 0.10,
            "mid_var": 0.03,
            "key_2": "3",
            "post_delay": 3.5
        },
        "alarm": {
            "stop_bot": True,
            "volume": 100,
            "audio_file": "",
            "freq_high": 2000,
            "freq_low": 1500
        },
        "targets": {}
    }

    def __init__(self, filepath=CONFIG_FILE):
        self.filepath = filepath
        self.action_config = self.get_default_copy()

    def get_default_copy(self):
        return json.loads(json.dumps(self.DEFAULT_CONFIG))

    def load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r') as f:
                    loaded = json.load(f)

                for category in self.DEFAULT_CONFIG:
                    if category in loaded and isinstance(loaded[category], dict):
                        self.action_config[category].update(loaded[category])
                print(f"[*] Loaded custom config from {self.filepath}")
            except Exception as e:
                print(f"⚠️ Failed to load {self.filepath}, using defaults: {e}")

    def save(self):
        with open(self.filepath, 'w') as f:
            json.dump(self.action_config, f, indent=4)
        print(f"✅ Saved custom configuration to {self.filepath}")

    def reset(self):
        existing_targets = {}
        for k in self.action_config.get("targets", {}):
            existing_targets[k] = {"enabled": True, "action": "kill_1"}
        self.action_config = self.get_default_copy()
        self.action_config["targets"] = existing_targets
        self.save()


# ==========================================
# 3. AUDIO ALARM MANAGER (Single Responsibility)
# ==========================================
class AudioAlarmManager:
    MCI_ALIAS = "pokenexus_custom_alarm"

    def __init__(self):
        self.is_playing = False
        self._using_mci = False

    @staticmethod
    def _mci_send(command):
        try:
            return ctypes.windll.winmm.mciSendStringW(command, None, 0, 0)
        except Exception:
            return -1

    @staticmethod
    def _build_siren_wav_bytes(volume_pct, freq_high=2000, freq_low=1500):
        sample_rate = 44100
        tone_duration = 0.18
        t = np.linspace(0, tone_duration, int(sample_rate * tone_duration), endpoint=False)
        amp = max(0.0, min(1.0, float(volume_pct) / 100.0)) * 32767.0

        wave_high = (amp * np.sin(2 * np.pi * float(freq_high) * t)).astype(np.int16)
        wave_low = (amp * np.sin(2 * np.pi * float(freq_low) * t)).astype(np.int16)
        siren_samples = np.concatenate([wave_high, wave_low])

        buf = io.BytesIO()
        with wave.open(buf, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(siren_samples.tobytes())
        return buf.getvalue()

    def start(self, volume_pct=100, audio_file="", freq_high=2000, freq_low=1500):
        self.stop()
        self.is_playing = True
        audio_path = os.path.abspath(audio_file) if audio_file else ""

        if audio_path and os.path.exists(audio_path):
            self._mci_send(f"close {self.MCI_ALIAS}")
            res = self._mci_send(f'open "{audio_path}" type mpegvideo alias {self.MCI_ALIAS}')
            if res == 0:
                self._using_mci = True
                mci_vol = max(0, min(1000, int(float(volume_pct) * 10)))
                self._mci_send(f"setaudio {self.MCI_ALIAS} volume to {mci_vol}")
                self._mci_send(f"play {self.MCI_ALIAS} repeat")
                return
            else:
                print(f"⚠️ Could not open '{audio_file}' via MCI. Falling back to built-in siren.")

        self._using_mci = False
        siren_bytes = self._build_siren_wav_bytes(volume_pct, freq_high, freq_low)

        def _siren_loop():
            while self.is_playing:
                try:
                    winsound.PlaySound(siren_bytes, winsound.SND_MEMORY)
                except Exception:
                    time.sleep(0.3)

        threading.Thread(target=_siren_loop, daemon=True).start()

    def stop(self):
        self.is_playing = False
        if self._using_mci:
            self._mci_send(f"stop {self.MCI_ALIAS}")
            self._mci_send(f"close {self.MCI_ALIAS}")
            self._using_mci = False
        try:
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass


# ==========================================
# 4. MOVEMENT CONTROLLER (Single Responsibility)
# ==========================================
class MovementController:
    def __init__(self, left_bound=DEFAULT_BOUND_LEFT, right_bound=DEFAULT_BOUND_RIGHT):
        self.bound_left = left_bound
        self.bound_right = right_bound
        self.key_left = 'a'
        self.key_right = 'd'
        self.blocks_per_sec = DEFAULT_BLOCKS_PER_SEC
        self.current_pos = 0.0
        self.target_pos = 0.0
        self.currently_held_key = None
        self.last_tick_time = 0.0

    def configure(self, left_bound, right_bound, key_left='a', key_right='d', blocks_per_sec=DEFAULT_BLOCKS_PER_SEC):
        self.release()
        self.bound_left = float(left_bound)
        self.bound_right = float(right_bound)
        self.key_left = str(key_left).strip() or 'a'
        self.key_right = str(key_right).strip() or 'd'
        self.blocks_per_sec = max(0.1, float(blocks_per_sec))
        self.current_pos = max(self.bound_left, min(self.bound_right, self.current_pos))

    def adjust_bound(self, side, amount):
        if side == 'left':
            new_val = round(self.bound_left + amount, 1)
            if -50.0 <= new_val <= 50.0 and new_val < self.bound_right:
                self.bound_left = new_val
        elif side == 'right':
            new_val = round(self.bound_right + amount, 1)
            if -50.0 <= new_val <= 50.0 and new_val > self.bound_left:
                self.bound_right = new_val

    def get_bounds(self):
        return self.bound_left, self.bound_right

    def pick_new_destination(self):
        self.target_pos = random.uniform(self.bound_left, self.bound_right)

    def release(self):
        if self.currently_held_key:
            try:
                keyboard.release(self.currently_held_key)
            except Exception:
                pass
            self.currently_held_key = None

    def release_all_direction_keys(self):
        self.release()
        for k in (self.key_left, self.key_right):
            if k:
                try:
                    keyboard.release(k)
                except Exception:
                    pass

    def update_hold(self):
        now = time.time()
        delta_time = now - self.last_tick_time
        self.last_tick_time = now

        if self.currently_held_key:
            blocks_moved = delta_time * self.blocks_per_sec
            self.current_pos += blocks_moved if self.currently_held_key == self.key_right else -blocks_moved
            self.current_pos = max(self.bound_left, min(self.bound_right, self.current_pos))

        distance = self.target_pos - self.current_pos
        if abs(distance) < 0.2:
            self.release()
            return True

        direction = self.key_right if distance > 0 else self.key_left
        if self.currently_held_key != direction:
            self.release()
            try:
                keyboard.press(direction)
                self.currently_held_key = direction
            except ValueError as e:
                print(f"❌ Invalid movement key '{direction}': {e}")
                self.currently_held_key = None

        return False


# ==========================================
# 5. VISION SYSTEM (Single Responsibility)
# ==========================================
class VisionSystem:
    VALID_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.bmp')

    ACTION_BADGES = {
        "kill_1": "[M1]",
        "kill_2": "[M2]",
        "kill_3": "[M3]",
        "kill_4": "[M4]",
        "catch": "[CATCH]",
        "alert": "[ALERT]"
    }

    def __init__(self):
        # Active enabled templates: [(filename, img, action_code), ...]
        self.target_templates = []
        # All discovered image filenames in targets/: [filename, ...]
        self.discovered_targets = []
        self.reference_template = None
        self.rare_base_template = None
        self.rare_base_filename = None
        self.x_template = None
        self.x_filename = None

    @staticmethod
    def setup_folders():
        for folder in (DEBUG_FOLDER, CAPTURED_ROIS_FOLDER, TARGETS_FOLDER):
            if not os.path.exists(folder):
                os.makedirs(folder)

    def _find_and_load_single_image(self, base_name, flags=cv2.IMREAD_COLOR):
        for ext in self.VALID_EXTENSIONS + ('',):
            candidate = base_name + ext
            if os.path.exists(candidate) and os.path.isfile(candidate):
                img = cv2.imread(candidate, flags)
                if img is not None:
                    return img, candidate
        return None, None

    def get_system_anchor_image(self, allow_reference_fallback=True):
        search_names = [SYSTEM_REF_IMAGE_NAME]
        if allow_reference_fallback:
            search_names.append(os.path.splitext(REFERENCE_FRAME_IMAGE)[0])

        for base_name in search_names:
            img, path = self._find_and_load_single_image(base_name, flags=cv2.IMREAD_GRAYSCALE)
            if img is not None:
                return img, path
        return None, None

    def load_templates(self, oled: OledDisplay, targets_cfg=None):
        oled.send("Loading AI Vision...")
        self.target_templates.clear()
        self.discovered_targets.clear()

        if targets_cfg is None:
            targets_cfg = {}

        if os.path.exists(TARGETS_FOLDER):
            for filename in sorted(os.listdir(TARGETS_FOLDER), key=str.lower):
                if filename.lower().endswith(self.VALID_EXTENSIONS):
                    filepath = os.path.join(TARGETS_FOLDER, filename)
                    self.discovered_targets.append(filename)

                    if filename not in targets_cfg or not isinstance(targets_cfg[filename], dict):
                        targets_cfg[filename] = {"enabled": True, "action": "kill_1"}

                    entry = targets_cfg[filename]
                    is_enabled = bool(entry.get("enabled", True))
                    action_code = entry.get("action", "kill_1")
                    if action_code not in ConfigManager.VALID_ACTIONS:
                        action_code = "kill_1"
                        entry["action"] = action_code

                    if is_enabled:
                        img = cv2.imread(filepath)
                        if img is not None:
                            self.target_templates.append((filename, img, action_code))

        if os.path.exists(REFERENCE_FRAME_IMAGE):
            self.reference_template = cv2.imread(REFERENCE_FRAME_IMAGE)
            print(f"[*] Auto Grinder loaded base image: {REFERENCE_FRAME_IMAGE}")
        else:
            self.reference_template = None
            print(f"❌ CRITICAL ERROR: '{REFERENCE_FRAME_IMAGE}' missing! You must capture a new base image first.")

        self.rare_base_template, self.rare_base_filename = self._find_and_load_single_image(RARE_BASE_IMAGE_NAME)
        if self.rare_base_template is not None:
            print(f"[*] Loaded rare base image: {self.rare_base_filename}")
        else:
            print(f"[i] Optional '{RARE_BASE_IMAGE_NAME}' not found yet.")

        self.x_template, self.x_filename = self._find_and_load_single_image(X_CLICK_IMAGE_NAME)
        if self.x_template is not None:
            print(f"[*] Loaded click target image: {self.x_filename}")
        else:
            print(f"[i] Optional '{X_CLICK_IMAGE_NAME}' image not found yet.")

        total_count = len(self.discovered_targets)
        active_count = len(self.target_templates)
        print(f"[*] Target Roster: {active_count}/{total_count} images enabled for scanning.")

        if self.reference_template is None:
            oled.send("ERR: Base Img Missing")
        else:
            oled.send(f"Ready ({active_count}/{total_count} Tgts)")

    def detect_rare_base_image(self, frame, normal_ui_sim=0.0, threshold=45.0):
        if self.rare_base_template is None or frame is None:
            return False, 0.0, (0, 0)

        th, tw = self.rare_base_template.shape[:2]
        fh, fw = frame.shape[:2]

        if tw > fw or th > fh:
            return False, 0.0, (0, 0)

        res = cv2.matchTemplate(frame, self.rare_base_template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        rare_sim = max_val * 100.0

        is_detected = (rare_sim >= threshold) and (rare_sim > normal_ui_sim or rare_sim >= 75.0)
        return is_detected, rare_sim, max_loc

    def find_x_image(self, frame, offset=(0, 0), threshold=65.0):
        if self.x_template is None or frame is None:
            return False, 0.0, None

        th, tw = self.x_template.shape[:2]
        fh, fw = frame.shape[:2]

        if tw > fw or th > fh:
            return False, 0.0, None

        res = cv2.matchTemplate(frame, self.x_template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        x_sim = max_val * 100.0

        if x_sim >= threshold:
            center_x = int(offset[0]) + int(max_loc[0]) + (tw // 2)
            center_y = int(offset[1]) + int(max_loc[1]) + (th // 2)
            return True, x_sim, (center_x, center_y)

        return False, x_sim, None

    @staticmethod
    def find_multiscale_anchor(frame_gray, system_template_gray):
        th, tw = system_template_gray.shape[:2]

        def check_scale(scale_factor):
            rw, rh = int(tw * scale_factor), int(th * scale_factor)
            if rw <= 0 or rh <= 0 or rw > frame_gray.shape[1] or rh > frame_gray.shape[0]:
                return 0.0, None, (0, 0)
            resized_ref = cv2.resize(system_template_gray, (rw, rh), interpolation=cv2.INTER_NEAREST)
            result = cv2.matchTemplate(frame_gray, resized_ref, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            return max_val, max_loc, (rw, rh)

        best_sim, best_scale, best_loc, best_dims = 0.0, 1.0, None, (0, 0)
        coarse_winner_scale = 1.0

        for scale in np.linspace(0.4, 2.0, 25):
            sim, loc, dims = check_scale(scale)
            if sim > best_sim:
                best_sim, best_scale, best_loc, best_dims, coarse_winner_scale = sim, scale, loc, dims, scale

        for scale in np.linspace(coarse_winner_scale - 0.05, coarse_winner_scale + 0.05, 11):
            sim, loc, dims = check_scale(scale)
            if sim > best_sim:
                best_sim, best_scale, best_loc, best_dims = sim, scale, loc, dims

        return best_sim, best_scale, best_loc, best_dims

    def scan_targets(self, battle_frame):
        highest_sim = 0.0
        best_match_name = None
        best_match_action = None
        current_scan_memory = {}

        for name, template, action_code in self.target_templates:
            badge = self.ACTION_BADGES.get(action_code, "[TGT]")
            display_name = f"{badge} {name}"
            if template.shape[0] <= battle_frame.shape[0] and template.shape[1] <= battle_frame.shape[1]:
                res_target = cv2.matchTemplate(battle_frame, template, cv2.TM_CCOEFF_NORMED)
                _, max_val_target, _, _ = cv2.minMaxLoc(res_target)
                sim = max_val_target * 100
                current_scan_memory[display_name] = sim

                if sim > highest_sim:
                    highest_sim = sim
                    best_match_name = name
                    best_match_action = action_code
            else:
                current_scan_memory[display_name] = -1.0

        return highest_sim, best_match_name, best_match_action, current_scan_memory


# ==========================================
# 6. GUI & BOT COORDINATOR CLASS
# ==========================================
class AutoGrinderGUI:
    KILL_KEYS = ("kill_1", "kill_2", "kill_3", "kill_4")
    MOVE_LABELS = ("Move 1", "Move 2", "Move 3", "Move 4")

    ACTION_LABEL_TO_CODE = {
        "Move 1": "kill_1",
        "Move 2": "kill_2",
        "Move 3": "kill_3",
        "Move 4": "kill_4",
        "Catch": "catch",
        "Alert": "alert"
    }
    ACTION_CODE_TO_LABEL = {v: k for k, v in ACTION_LABEL_TO_CODE.items()}
    TARGET_ACTION_LABELS = ("Move 1", "Move 2", "Move 3", "Move 4", "Catch", "Alert")
    NEW_TARGET_ACTION_LABELS = ("Ask Me", "Move 1", "Move 2", "Move 3", "Move 4", "Catch", "Alert")

    def __init__(self, root):
        self.root = root
        self.root.title("PokeNexus Auto Grinder")
        self.root.geometry("420x660")
        self.root.resizable(False, False)
        self.root.attributes('-topmost', True)
        self.root.configure(padx=15, pady=15)

        # Subsystems
        self.config_mgr = ConfigManager()
        self.config_mgr.load()

        gen_cfg = self.action_config["general"]
        mov_cfg = self.action_config["movement"]

        self.oled = OledDisplay(port=gen_cfg.get("com_port", "COM3"), baud=gen_cfg.get("baud_rate", 9600))
        self.alarm_mgr = AudioAlarmManager()
        self.movement = MovementController(
            left_bound=mov_cfg.get("bound_left", DEFAULT_BOUND_LEFT),
            right_bound=mov_cfg.get("bound_right", DEFAULT_BOUND_RIGHT)
        )
        self.movement.configure(
            mov_cfg.get("bound_left", DEFAULT_BOUND_LEFT),
            mov_cfg.get("bound_right", DEFAULT_BOUND_RIGHT),
            mov_cfg.get("key_left", "a"),
            mov_cfg.get("key_right", "d"),
            mov_cfg.get("blocks_per_sec", DEFAULT_BLOCKS_PER_SEC)
        )
        self.vision = VisionSystem()

        # Bot State
        self.is_running = False
        self.bot_thread = None
        self.alarm_active = False
        self.MASTER_ROI = None
        self.BATTLE_ROI = None

        self.in_battle = False
        self.last_action_time = 0.0
        self.battle_start_time = 0.0
        self.has_swapped = False
        self.auto_captured_this_battle = False
        self.rare_base_notified = False
        self.last_scan_results = {}

        # Track interactive widgets to lock while bot is running
        self.all_entries = []
        self.lockable_widgets = []
        self._hotkey_hooks = []

        # Hotkey Hold State
        self._start_hold_active = False
        self._start_press_time = 0.0
        self._start_triggered_this_hold = False

        # Protection & UI Variables
        self.enable_stuck_alarm = tk.BooleanVar()
        self.enable_debug_screenshots = tk.BooleanVar()
        self.last_checked_frame = None
        self.last_screen_change_time = time.time()

        # Movement Variables
        self.bound_left_var = tk.StringVar()
        self.bound_right_var = tk.StringVar()
        self.move_left_key_var = tk.StringVar()
        self.move_right_key_var = tk.StringVar()
        self.blocks_per_sec_var = tk.StringVar()
        self.stop_pause_var = tk.StringVar()

        # Similarity Threshold Variables
        self.ui_lock_threshold = tk.DoubleVar()
        self.battle_ui_threshold = tk.DoubleVar()
        self.target_sim_threshold = tk.DoubleVar()
        self.unrecog_sim_threshold = tk.DoubleVar()
        self.rare_base_threshold = tk.DoubleVar()
        self.x_click_threshold = tk.DoubleVar()

        # Timings & Cooldown Variables
        self.start_delay_var = tk.StringVar()
        self.hold_start_sec_var = tk.StringVar()
        self.battle_spawn_wait_var = tk.StringVar()
        self.action_cooldown_var = tk.StringVar()
        self.anim_grace_var = tk.StringVar()
        self.stuck_timeout_var = tk.StringVar()

        # General / Hardware / Unrecognized Variables
        self.unrecognized_action = tk.StringVar()
        self.unrecog_kill_move_var = tk.StringVar()
        self.auto_capture_var = tk.BooleanVar()
        self.new_target_action_label_var = tk.StringVar()
        self.start_hotkey_var = tk.StringVar()
        self.stop_hotkey_var = tk.StringVar()
        self.com_port_var = tk.StringVar()
        self.baud_rate_var = tk.StringVar()

        # Action Macro Variables & Kill Tab State
        self.cust_vars = {}
        self.active_kill_tab = 1
        self.kill_tab_buttons = {}
        self.kill_slot_frames = {}

        # Per-Target Roster UI Variables: {filename: {"enabled": BooleanVar, "action": StringVar}}
        self.target_row_vars = {}
        self.roster_list_container = None
        self.roster_count_label = None

        self.init_customize_vars()
        self.sync_vars_from_config()

        # Setup folders & load templates
        self.vision.setup_folders()
        self.vision.load_templates(self.oled, self.action_config["targets"])
        self.config_mgr.save()

        # Frames
        self.main_frame = tk.Frame(self.root)
        self.properties_frame = tk.Frame(self.root)

        self.create_main_dashboard()
        self.create_properties_menu()

        self.main_frame.pack(fill="both", expand=True)
        self.root.focus_set()

        self._refresh_arduino_status_label()
        self._bind_hotkeys()

    @property
    def action_config(self):
        return self.config_mgr.action_config

    def _refresh_arduino_status_label(self):
        ard_status = f"Connected ({self.oled.port})" if self.oled.connected else f"Not Connected ({self.oled.port})"
        self.arduino_label.config(text=f"Arduino: {ard_status}")

    def _register_entry(self, parent, **kwargs):
        entry = tk.Entry(parent, **kwargs)
        entry.bind("<Return>", lambda _: self.root.focus_set())
        entry.bind("<Escape>", lambda _: self.root.focus_set())
        self.all_entries.append(entry)
        return entry

    def _set_entries_state(self, state):
        for entry in self.all_entries:
            try:
                entry.config(state=state)
            except Exception:
                pass
        for widget in self.lockable_widgets:
            try:
                widget.config(state=state)
            except Exception:
                pass

    # ========================================================
    # HOTKEYS (ADJUSTABLE START HOLD & STOP KEY)
    # ========================================================
    def _bind_hotkeys(self):
        for hook in self._hotkey_hooks:
            try:
                keyboard.unhook(hook)
            except Exception:
                pass
        self._hotkey_hooks.clear()

        start_key = self.action_config["general"].get("start_hotkey", "e").strip().lower() or "e"
        stop_key = self.action_config["general"].get("stop_hotkey", "q").strip().lower() or "q"

        try:
            self._hotkey_hooks.append(keyboard.on_press_key(start_key, lambda _: self.root.after(0, self._on_start_key_down)))
            self._hotkey_hooks.append(keyboard.on_release_key(start_key, lambda _: self.root.after(0, self._on_start_key_up)))
        except ValueError as e:
            print(f"❌ Invalid Start Hotkey '{start_key}': {e}")

        try:
            self._hotkey_hooks.append(keyboard.on_press_key(stop_key, lambda _: self.root.after(0, self.stop_bot)))
        except ValueError as e:
            print(f"❌ Invalid Stop Hotkey '{stop_key}': {e}")

        if hasattr(self, "start_btn"):
            hold_sec = self.action_config["timings"].get("hold_start_sec", 2.0)
            self.start_btn.config(text=f"▶ START (Hold {start_key.upper()} {hold_sec:.1f}s)")
        if hasattr(self, "stop_btn"):
            self.stop_btn.config(text=f"⏹ STOP BOT ({stop_key.upper()})")

    def _on_start_key_down(self):
        focused = self.root.focus_get()
        if isinstance(focused, tk.Entry):
            return
        if self.is_running or self.alarm_active or self._start_hold_active or self._start_triggered_this_hold:
            return
        hold_req = float(self.action_config["timings"].get("hold_start_sec", 2.0))
        if hold_req <= 0.0:
            self._start_triggered_this_hold = True
            self.start_bot()
            return
        start_key = self.action_config["general"].get("start_hotkey", "e").upper()
        self._start_hold_active = True
        self._start_press_time = time.time()
        self.set_status(f"Hold {start_key} to Start (0.0s / {hold_req:.1f}s)...", "#ff9800")
        self.root.after(50, self._check_start_hold)

    def _check_start_hold(self):
        if not self._start_hold_active:
            return
        start_key = self.action_config["general"].get("start_hotkey", "e").strip().lower() or "e"
        hold_req = float(self.action_config["timings"].get("hold_start_sec", 2.0))
        if not keyboard.is_pressed(start_key):
            self._on_start_key_up()
            return
        elapsed = time.time() - self._start_press_time
        if elapsed >= hold_req:
            self._start_hold_active = False
            self._start_triggered_this_hold = True
            self.start_bot()
        else:
            self.set_status(f"Hold {start_key.upper()} to Start ({elapsed:.1f}s / {hold_req:.1f}s)...", "#ff9800")
            self.root.after(50, self._check_start_hold)

    def _on_start_key_up(self):
        was_holding = self._start_hold_active
        self._start_hold_active = False
        self._start_triggered_this_hold = False
        if was_holding and not self.is_running and not self.alarm_active:
            self.set_status("IDLE", "gray")

    # ========================================================
    # SAFETY & RARE BASE HANDLERS
    # ========================================================
    def _check_stuck_screen(self, current_frame):
        if not self.enable_stuck_alarm.get():
            return

        current_time = time.time()
        gray_frame = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)
        timeout_sec = float(self.action_config["timings"].get("stuck_timeout", 300.0))

        if self.last_checked_frame is None or self.last_checked_frame.shape != gray_frame.shape:
            self.last_checked_frame = gray_frame
            self.last_screen_change_time = current_time
        else:
            diff = cv2.absdiff(self.last_checked_frame, gray_frame)
            changed_pixels = np.count_nonzero(diff > 15)

            if changed_pixels > 2000:
                self.last_checked_frame = gray_frame
                self.last_screen_change_time = current_time
            else:
                if (current_time - self.last_screen_change_time) > timeout_sec:
                    print(f"[WARNING] Screen has been static for over {timeout_sec:.0f}s!")
                    self.execute_alarm("STUCK SCREEN", 100.0)
                    self.last_screen_change_time = current_time

    def _handle_rare_base_detected(self, frame, rare_sim, offset=(0, 0)):
        self.movement.release()
        self.set_status("Rare Base Detected!", "#e91e63")
        self.ui_match_label.config(text=f"Rare Base Match: {rare_sim:.1f}%")
        self.oled.send_throttled(f"Rare Base: {rare_sim:.0f}%")

        if not self.rare_base_notified:
            print(f"\n🌟 DETECTED: {RARE_BASE_IMAGE_NAME} ({rare_sim:.1f}%)! Searching for '{X_CLICK_IMAGE_NAME}'...")
            self.rare_base_notified = True

        x_thresh = self.x_click_threshold.get()
        found_x, x_sim, click_coords = self.vision.find_x_image(frame, offset=offset, threshold=x_thresh)

        if not found_x and offset != (0, 0) and self.vision.x_template is not None:
            full_shot = pyautogui.screenshot()
            full_bgr = cv2.cvtColor(np.array(full_shot), cv2.COLOR_RGB2BGR)
            found_x, x_sim, click_coords = self.vision.find_x_image(full_bgr, offset=(0, 0), threshold=x_thresh)

        if found_x and click_coords is not None:
            cx, cy = click_coords
            self.target_sim_label.config(text=f"Clicking '{X_CLICK_IMAGE_NAME}' ({x_sim:.1f}%) at ({cx}, {cy})", fg="#e91e63")
            print(f"🖱️ Found '{X_CLICK_IMAGE_NAME}' ({x_sim:.1f}%) -> Clicking at ({cx}, {cy})")
            pyautogui.click(cx, cy)
            pyautogui.moveTo(150, 150)
            self.human_sleep(0.5, 0.05)
        else:
            self.target_sim_label.config(text=f"Detected: {RARE_BASE_IMAGE_NAME} ({rare_sim:.1f}%)", fg="#e91e63")

    # ========================================================
    # CONFIG VARIABLES & JSON PERSISTENCE
    # ========================================================
    def init_customize_vars(self):
        for action in self.KILL_KEYS + ("swap", "catch"):
            self.cust_vars[action] = {
                "pre_delay": tk.StringVar(),
                "key_1": tk.StringVar(),
                "mid_delay": tk.StringVar(),
                "mid_var": tk.StringVar(),
                "key_2": tk.StringVar(),
                "post_delay": tk.StringVar(),
            }
            if action in self.KILL_KEYS + ("catch",):
                self.cust_vars[action]["include_swap"] = tk.BooleanVar()

        self.cust_vars["alarm"] = {
            "stop_bot": tk.BooleanVar(),
            "volume": tk.DoubleVar(),
            "audio_file": tk.StringVar(),
            "freq_high": tk.StringVar(),
            "freq_low": tk.StringVar()
        }

    def sync_vars_from_config(self):
        # Movement
        mov = self.action_config["movement"]
        self.bound_left_var.set(f"{float(mov.get('bound_left', DEFAULT_BOUND_LEFT)):.1f}")
        self.bound_right_var.set(f"{float(mov.get('bound_right', DEFAULT_BOUND_RIGHT)):.1f}")
        self.move_left_key_var.set(str(mov.get("key_left", "a")))
        self.move_right_key_var.set(str(mov.get("key_right", "d")))
        self.blocks_per_sec_var.set(str(mov.get("blocks_per_sec", DEFAULT_BLOCKS_PER_SEC)))
        self.stop_pause_var.set(str(mov.get("stop_pause", 0.2)))

        # Thresholds
        thr = self.action_config["thresholds"]
        self.ui_lock_threshold.set(float(thr.get("ui_lock_sim", 40.0)))
        self.battle_ui_threshold.set(float(thr.get("battle_ui_sim", 50.0)))
        self.target_sim_threshold.set(float(thr.get("target_sim", 94.0)))
        self.unrecog_sim_threshold.set(float(thr.get("unrecog_sim", 30.0)))
        self.rare_base_threshold.set(float(thr.get("rare_base_sim", 45.0)))
        self.x_click_threshold.set(float(thr.get("x_click_sim", 65.0)))

        # Timings
        tim = self.action_config["timings"]
        self.start_delay_var.set(str(tim.get("start_delay", 3.0)))
        self.hold_start_sec_var.set(str(tim.get("hold_start_sec", 2.0)))
        self.battle_spawn_wait_var.set(str(tim.get("battle_spawn_wait", 1.7)))
        self.action_cooldown_var.set(str(tim.get("action_cooldown", 3.2)))
        self.anim_grace_var.set(str(tim.get("anim_grace_period", 2.5)))
        self.stuck_timeout_var.set(str(tim.get("stuck_timeout", 300.0)))

        # General
        gen = self.action_config["general"]
        self.unrecognized_action.set(str(gen.get("unrecognized_action", "ignore")))
        u_move = int(gen.get("unrecognized_kill_move", 1))
        if u_move not in (1, 2, 3, 4):
            u_move = 1
        self.unrecog_kill_move_var.set(f"Move {u_move}")
        self.auto_capture_var.set(bool(gen.get("auto_capture", False)))

        default_act = str(gen.get("new_target_default_action", "ask"))
        if default_act == "ask":
            self.new_target_action_label_var.set("Ask Me")
        else:
            self.new_target_action_label_var.set(self.ACTION_CODE_TO_LABEL.get(default_act, "Ask Me"))

        self.enable_stuck_alarm.set(bool(gen.get("enable_stuck_alarm", False)))
        self.enable_debug_screenshots.set(bool(gen.get("enable_debug_screenshots", False)))
        self.start_hotkey_var.set(str(gen.get("start_hotkey", "e")))
        self.stop_hotkey_var.set(str(gen.get("stop_hotkey", "q")))
        self.com_port_var.set(str(gen.get("com_port", "COM3")))
        self.baud_rate_var.set(str(gen.get("baud_rate", 9600)))

        # Actions (kill_1..kill_4, swap, catch)
        for action in self.KILL_KEYS + ("swap", "catch"):
            defaults = self.config_mgr.DEFAULT_CONFIG[action]
            cfg = self.action_config.get(action, defaults)
            for key, default_val in defaults.items():
                val = cfg.get(key, default_val)
                if key == "include_swap":
                    self.cust_vars[action][key].set(bool(val))
                else:
                    self.cust_vars[action][key].set(str(val))

        alarm_defaults = self.config_mgr.DEFAULT_CONFIG["alarm"]
        alarm_cfg = self.action_config.get("alarm", alarm_defaults)
        self.cust_vars["alarm"]["stop_bot"].set(bool(alarm_cfg.get("stop_bot", alarm_defaults["stop_bot"])))
        self.cust_vars["alarm"]["volume"].set(float(alarm_cfg.get("volume", alarm_defaults["volume"])))
        self.cust_vars["alarm"]["audio_file"].set(str(alarm_cfg.get("audio_file", alarm_defaults["audio_file"])))
        self.cust_vars["alarm"]["freq_high"].set(str(alarm_cfg.get("freq_high", alarm_defaults["freq_high"])))
        self.cust_vars["alarm"]["freq_low"].set(str(alarm_cfg.get("freq_low", alarm_defaults["freq_low"])))

    def _sync_target_roster_to_config(self):
        updated_targets = {}
        for filename in self.vision.discovered_targets:
            row_vars = self.target_row_vars.get(filename)
            if row_vars:
                enabled = bool(row_vars["enabled"].get())
                action_label = row_vars["action"].get()
                action_code = self.ACTION_LABEL_TO_CODE.get(action_label, "kill_1")
                updated_targets[filename] = {"enabled": enabled, "action": action_code}
            elif filename in self.action_config["targets"]:
                updated_targets[filename] = self.action_config["targets"][filename]
            else:
                updated_targets[filename] = {"enabled": True, "action": "kill_1"}

        self.action_config["targets"] = updated_targets

    def save_config(self, show_popup=True):
        self.root.focus_set()
        try:
            b_left = float(self.bound_left_var.get())
            b_right = float(self.bound_right_var.get())
            if b_left >= b_right:
                messagebox.showerror("Invalid Bounds", "Left Bound must be smaller than Right Bound!")
                return False

            k_left = self.move_left_key_var.get().strip() or "a"
            k_right = self.move_right_key_var.get().strip() or "d"
            bps = max(0.1, float(self.blocks_per_sec_var.get()))
            s_pause = max(0.0, float(self.stop_pause_var.get()))

            self.action_config["movement"] = {
                "bound_left": round(b_left, 2),
                "bound_right": round(b_right, 2),
                "key_left": k_left,
                "key_right": k_right,
                "blocks_per_sec": bps,
                "stop_pause": s_pause
            }

            self.action_config["thresholds"] = {
                "ui_lock_sim": float(self.ui_lock_threshold.get()),
                "battle_ui_sim": float(self.battle_ui_threshold.get()),
                "target_sim": float(self.target_sim_threshold.get()),
                "unrecog_sim": float(self.unrecog_sim_threshold.get()),
                "rare_base_sim": float(self.rare_base_threshold.get()),
                "x_click_sim": float(self.x_click_threshold.get())
            }

            self.action_config["timings"] = {
                "start_delay": max(0.0, float(self.start_delay_var.get())),
                "hold_start_sec": max(0.0, float(self.hold_start_sec_var.get())),
                "battle_spawn_wait": max(0.0, float(self.battle_spawn_wait_var.get())),
                "action_cooldown": max(0.0, float(self.action_cooldown_var.get())),
                "anim_grace_period": max(0.0, float(self.anim_grace_var.get())),
                "stuck_timeout": max(5.0, float(self.stuck_timeout_var.get()))
            }

            try:
                u_kill_move = int(self.unrecog_kill_move_var.get().replace("Move ", "").strip())
            except ValueError:
                u_kill_move = 1
            if u_kill_move not in (1, 2, 3, 4):
                u_kill_move = 1

            new_tgt_label = self.new_target_action_label_var.get()
            new_tgt_code = "ask" if new_tgt_label == "Ask Me" else self.ACTION_LABEL_TO_CODE.get(new_tgt_label, "ask")

            self.action_config["general"] = {
                "unrecognized_action": self.unrecognized_action.get(),
                "unrecognized_kill_move": u_kill_move,
                "auto_capture": bool(self.auto_capture_var.get()),
                "new_target_default_action": new_tgt_code,
                "enable_stuck_alarm": bool(self.enable_stuck_alarm.get()),
                "enable_debug_screenshots": bool(self.enable_debug_screenshots.get()),
                "start_hotkey": self.start_hotkey_var.get().strip().lower() or "e",
                "stop_hotkey": self.stop_hotkey_var.get().strip().lower() or "q",
                "com_port": self.com_port_var.get().strip() or "COM3",
                "baud_rate": int(float(self.baud_rate_var.get()))
            }

            for action in self.KILL_KEYS + ("swap", "catch"):
                v = self.cust_vars[action]
                updated = {
                    "pre_delay": float(v["pre_delay"].get()),
                    "key_1": v["key_1"].get().strip(),
                    "mid_delay": float(v["mid_delay"].get()),
                    "mid_var": float(v["mid_var"].get()),
                    "key_2": v["key_2"].get().strip(),
                    "post_delay": float(v["post_delay"].get())
                }
                if "include_swap" in v:
                    updated["include_swap"] = bool(v["include_swap"].get())
                self.action_config[action] = updated

            va = self.cust_vars["alarm"]
            self.action_config["alarm"] = {
                "stop_bot": bool(va["stop_bot"].get()),
                "volume": int(float(va["volume"].get())),
                "audio_file": va["audio_file"].get().strip(),
                "freq_high": int(float(va["freq_high"].get())),
                "freq_low": int(float(va["freq_low"].get()))
            }

            self._sync_target_roster_to_config()
            self.vision.load_templates(self.oled, self.action_config["targets"])
            self._update_roster_counter()

            self.movement.configure(b_left, b_right, k_left, k_right, bps)
            self._bind_hotkeys()
            self.config_mgr.save()

            if show_popup:
                messagebox.showinfo("Saved", f"All settings & target actions saved to '{CONFIG_FILE}'!")
            return True
        except ValueError:
            messagebox.showerror("Invalid Input", "All numeric bounds, delays, speeds, and frequency fields must be valid numbers!")
            return False

    def reset_to_defaults(self):
        self.root.focus_set()
        if messagebox.askyesno("Reset Defaults", "Restore all bounds, thresholds, timings, hotkeys, target assignments, and action macros to default values?"):
            self.config_mgr.reset()
            self.sync_vars_from_config()
            self.vision.load_templates(self.oled, self.action_config["targets"])
            self._rebuild_target_roster_ui()
            mov = self.action_config["movement"]
            self.movement.configure(
                mov["bound_left"], mov["bound_right"],
                mov["key_left"], mov["key_right"], mov["blocks_per_sec"]
            )
            self._bind_hotkeys()
            if hasattr(self, "_update_unrecog_rb_colors"):
                self._update_unrecog_rb_colors()
            messagebox.showinfo("Reset Complete", "Default values restored and saved!")

    # ========================================================
    # UI HELPER & SCREEN SWITCHING
    # ========================================================
    def show_properties(self):
        self.root.focus_set()
        self.main_frame.pack_forget()
        self.properties_frame.pack(fill="both", expand=True)

    def show_main(self):
        self.root.focus_set()
        self.properties_frame.pack_forget()
        self.main_frame.pack(fill="both", expand=True)

    def _create_scrollable_container(self, parent):
        canvas_frame = tk.Frame(parent)
        canvas_frame.pack(fill="both", expand=True)

        canvas = tk.Canvas(canvas_frame, highlightthickness=0)
        scrollbar = tk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        win_tag = f"win_{id(canvas)}"
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw", tags=win_tag)
        canvas.bind('<Configure>', lambda e: canvas.itemconfig(win_tag, width=e.width))

        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas_frame.bind('<Enter>', lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas_frame.bind('<Leave>', lambda e: canvas.unbind_all("<MouseWheel>"))

        return scrollable_frame

    # ========================================================
    # SCREEN 1: MAIN DASHBOARD
    # ========================================================
    def create_main_dashboard(self):
        self.main_frame.bind("<Button-1>", lambda _: self.root.focus_set())
        tk.Label(self.main_frame, text="PokeNexus Auto Grinder", font=("Segoe UI", 14, "bold")).pack(pady=(0, 8))

        self.status_frame = tk.LabelFrame(self.main_frame, text=" System Status ", font=("Segoe UI", 9, "bold"), padx=10, pady=10)
        self.status_frame.pack(fill="x", pady=5)
        self.status_label = tk.Label(self.status_frame, text="Status: IDLE", font=("Segoe UI", 10, "bold"), fg="gray")
        self.status_label.pack(anchor="w")
        self.arduino_label = tk.Label(self.status_frame, text="Arduino: Checking...", font=("Segoe UI", 9), fg="#555")
        self.arduino_label.pack(anchor="w", pady=(2, 0))

        self.telemetry_frame = tk.LabelFrame(self.main_frame, text=" Live Vision Metrics ", font=("Segoe UI", 9, "bold"), padx=10, pady=10)
        self.telemetry_frame.pack(fill="x", pady=5)
        self.ui_match_label = tk.Label(self.telemetry_frame, text="UI Frame Match:  0.0%", font=("Segoe UI", 9))
        self.ui_match_label.pack(anchor="w")
        self.target_sim_label = tk.Label(self.telemetry_frame, text="Target: None", font=("Segoe UI", 9, "bold"), fg="blue")
        self.target_sim_label.pack(anchor="w", pady=(2, 0))
        self.show_results_btn = tk.Button(self.telemetry_frame, text="📊 Show All Scan Results", font=("Segoe UI", 8), command=self.display_all_scan_results)
        self.show_results_btn.pack(anchor="w", pady=(10, 0))

        self.controls_frame = tk.Frame(self.main_frame)
        self.controls_frame.pack(fill="x", pady=12)

        btn_wrapper = tk.Frame(self.controls_frame)
        btn_wrapper.pack(fill="x")
        start_key = self.action_config["general"].get("start_hotkey", "e").upper()
        stop_key = self.action_config["general"].get("stop_hotkey", "q").upper()
        hold_sec = self.action_config["timings"].get("hold_start_sec", 2.0)

        self.start_btn = tk.Button(btn_wrapper, text=f"▶ START (Hold {start_key} {hold_sec:.1f}s)", font=("Segoe UI", 10, "bold"), bg="#4CAF50", fg="white", width=18, height=2, command=self.start_bot)
        self.start_btn.pack(side="left", padx=4)
        self.stop_btn = tk.Button(btn_wrapper, text=f"⏹ STOP BOT ({stop_key})", font=("Segoe UI", 10, "bold"), bg="#f44336", fg="white", width=15, height=2, state="disabled", command=self.stop_bot)
        self.stop_btn.pack(side="right", padx=4)

        tk.Button(self.main_frame, text="⚙️ Properties & Subsystems", font=("Segoe UI", 10, "bold"), pady=6, command=self.show_properties).pack(fill="x", pady=(10, 0))

    # ========================================================
    # TARGET ROSTER HELPERS (ENABLE/DISABLE & ACTION ASSIGNMENT)
    # ========================================================
    def _update_roster_counter(self):
        if not self.roster_count_label:
            return
        total = len(self.vision.discovered_targets)
        enabled = sum(1 for v in self.target_row_vars.values() if v["enabled"].get())
        self.roster_count_label.config(text=f"Selected to Read: {enabled} / {total} images in '{TARGETS_FOLDER}/'")

    def _style_action_option_menu(self, opt_widget, action_label):
        color_map = {
            "Move 1": "#b71c1c",
            "Move 2": "#c62828",
            "Move 3": "#d32f2f",
            "Move 4": "#e53935",
            "Catch": "#6a1b9a",
            "Alert": "#e65100"
        }
        opt_widget.config(fg=color_map.get(action_label, "black"), font=("Segoe UI", 7, "bold"))

    def _on_roster_change(self, opt_widget=None, action_var=None):
        if opt_widget is not None and action_var is not None:
            self._style_action_option_menu(opt_widget, action_var.get())
        self._update_roster_counter()
        if not self.is_running:
            self._sync_target_roster_to_config()
            self.vision.load_templates(self.oled, self.action_config["targets"])

    def _set_all_targets_enabled(self, state_bool):
        for v in self.target_row_vars.values():
            v["enabled"].set(state_bool)
        self._on_roster_change()

    def _refresh_target_roster_from_disk(self):
        self._sync_target_roster_to_config()
        self.vision.load_templates(self.oled, self.action_config["targets"])
        self._rebuild_target_roster_ui()

    def _rebuild_target_roster_ui(self):
        if self.roster_list_container is None:
            return

        old_children = set(self.roster_list_container.winfo_children())
        for child in list(old_children):
            for sub in child.winfo_children():
                if sub in self.lockable_widgets:
                    self.lockable_widgets.remove(sub)
            child.destroy()

        self.target_row_vars.clear()

        if not self.vision.discovered_targets:
            tk.Label(
                self.roster_list_container,
                text=f"No target images in '{TARGETS_FOLDER}/' yet.",
                font=("Segoe UI", 8, "italic"),
                fg="gray"
            ).pack(anchor="w", pady=4)
            self._update_roster_counter()
            return

        for filename in self.vision.discovered_targets:
            cfg_entry = self.action_config["targets"].get(filename, {"enabled": True, "action": "kill_1"})
            en_var = tk.BooleanVar(value=bool(cfg_entry.get("enabled", True)))
            action_code = cfg_entry.get("action", "kill_1")
            action_label = self.ACTION_CODE_TO_LABEL.get(action_code, "Move 1")
            act_var = tk.StringVar(value=action_label)

            self.target_row_vars[filename] = {"enabled": en_var, "action": act_var}

            row = tk.Frame(self.roster_list_container)
            row.pack(fill="x", pady=1)

            cb = tk.Checkbutton(row, variable=en_var, command=self._on_roster_change)
            cb.pack(side="left")
            self.lockable_widgets.append(cb)

            clean_name = os.path.splitext(filename)[0]
            tk.Label(row, text=clean_name, font=("Segoe UI", 8), anchor="w").pack(side="left", fill="x", expand=True, padx=(2, 4))

            opt = tk.OptionMenu(
                row,
                act_var,
                *self.TARGET_ACTION_LABELS,
                command=lambda _, w=None, v=act_var: None
            )
            opt.config(width=7, padx=2, pady=0)
            self._style_action_option_menu(opt, action_label)
            menu = opt["menu"]
            menu.delete(0, "end")
            for choice in self.TARGET_ACTION_LABELS:
                menu.add_command(
                    label=choice,
                    command=lambda val=choice, var=act_var, widget=opt: (var.set(val), self._on_roster_change(widget, var))
                )

            opt.pack(side="right")
            self.lockable_widgets.append(opt)

        if self.is_running:
            self._set_entries_state("disabled")

        self._update_roster_counter()

    # ========================================================
    # KILL MOVE TAB SWITCHER (MOVE 1 - MOVE 4)
    # ========================================================
    def _select_kill_tab(self, slot_num):
        self.active_kill_tab = slot_num
        for idx, btn in self.kill_tab_buttons.items():
            if idx == slot_num:
                btn.config(bg="#d32f2f", fg="white", relief="sunken")
            else:
                btn.config(bg="#f0f0f0", fg="black", relief="raised")

        for idx, frame in self.kill_slot_frames.items():
            if idx == slot_num:
                frame.pack(fill="x", pady=2)
            else:
                frame.pack_forget()

    # ========================================================
    # SCREEN 2: UNIFIED PROPERTIES & SUBSYSTEMS (SCROLLABLE)
    # ========================================================
    def create_properties_menu(self):
        tk.Button(self.properties_frame, text="🔙 Back to Main Dashboard", font=("Segoe UI", 9, "bold"), command=self.show_main).pack(fill="x", pady=(0, 6))
        tk.Label(self.properties_frame, text="Properties, Subsystems & Actions", font=("Segoe UI", 11, "bold")).pack(pady=(0, 4))

        # Pinned Save / Reset Bar
        top_save_bar = tk.Frame(self.properties_frame)
        top_save_bar.pack(fill="x", pady=(0, 6))
        tk.Button(top_save_bar, text="💾 Save All Settings", bg="#4CAF50", fg="white", font=("Segoe UI", 9, "bold"), command=lambda: self.save_config(show_popup=True)).pack(side="left", fill="x", expand=True, padx=(0, 3))
        tk.Button(top_save_bar, text="🔄 Reset Defaults", bg="#607D8B", fg="white", font=("Segoe UI", 9, "bold"), command=self.reset_to_defaults).pack(side="right", fill="x", expand=True, padx=(3, 0))

        scrollable_prop = self._create_scrollable_container(self.properties_frame)

        # ----------------------------------------------------
        # 1. TARGET POKÉMON ROSTER & ACTION ASSIGNMENT
        # ----------------------------------------------------
        roster_frame = tk.LabelFrame(scrollable_prop, text=" Target Pokémon Roster & Action Assignment ", font=("Segoe UI", 9, "bold"), fg="#1565C0", padx=10, pady=8)
        roster_frame.pack(fill="x", pady=5)

        roster_ctrl_row = tk.Frame(roster_frame)
        roster_ctrl_row.pack(fill="x", pady=(0, 4))

        btn_refresh = tk.Button(roster_ctrl_row, text="🔄 Refresh", font=("Segoe UI", 8), command=self._refresh_target_roster_from_disk)
        btn_refresh.pack(side="left", padx=(0, 4))
        btn_all = tk.Button(roster_ctrl_row, text="✅ Select All", font=("Segoe UI", 8), command=lambda: self._set_all_targets_enabled(True))
        btn_all.pack(side="left", padx=(0, 4))
        btn_none = tk.Button(roster_ctrl_row, text="⬜ Deselect All", font=("Segoe UI", 8), command=lambda: self._set_all_targets_enabled(False))
        btn_none.pack(side="left")

        self.lockable_widgets.extend([btn_refresh, btn_all, btn_none])

        self.roster_count_label = tk.Label(roster_frame, text="Selected to Read: 0 / 0 images", font=("Segoe UI", 8, "bold"), fg="#333")
        self.roster_count_label.pack(anchor="w", pady=(0, 4))

        self.roster_list_container = tk.Frame(roster_frame)
        self.roster_list_container.pack(fill="x")
        self._rebuild_target_roster_ui()

        # ----------------------------------------------------
        # 2. CUSTOMIZE KILL MOVES (MOVE 1 - MOVE 4)
        # ----------------------------------------------------
        kill_box = tk.LabelFrame(scrollable_prop, text=" Action: KILL Moves (Move 1 – Move 4) ", font=("Segoe UI", 9, "bold"), fg="red", padx=10, pady=8)
        kill_box.pack(fill="x", pady=5)

        tab_bar = tk.Frame(kill_box)
        tab_bar.pack(fill="x", pady=(0, 6))

        for slot_num in (1, 2, 3, 4):
            btn = tk.Button(
                tab_bar,
                text=f"Move {slot_num}",
                font=("Segoe UI", 8, "bold"),
                command=lambda s=slot_num: self._select_kill_tab(s)
            )
            btn.pack(side="left", fill="x", expand=True, padx=1)
            self.kill_tab_buttons[slot_num] = btn

        for slot_num in (1, 2, 3, 4):
            action_key = f"kill_{slot_num}"
            v = self.cust_vars[action_key]
            slot_frame = tk.Frame(kill_box)
            self.kill_slot_frames[slot_num] = slot_frame

            cb_swap = tk.Checkbutton(slot_frame, text=f"Include Swap before Move {slot_num}", variable=v["include_swap"], font=("Segoe UI", 8, "bold"))
            cb_swap.pack(anchor="w", pady=(0, 4))
            self.lockable_widgets.append(cb_swap)

            grid = tk.Frame(slot_frame)
            grid.pack(fill="x", pady=2)

            tk.Label(grid, text="Start Sleep (s):", font=("Segoe UI", 8)).grid(row=0, column=0, sticky="w", pady=2)
            self._register_entry(grid, textvariable=v["pre_delay"], width=8).grid(row=0, column=1, padx=5, pady=2)

            tk.Label(grid, text="1st Key:", font=("Segoe UI", 8)).grid(row=0, column=2, sticky="w", padx=(10, 0), pady=2)
            self._register_entry(grid, textvariable=v["key_1"], width=6).grid(row=0, column=3, padx=5, pady=2)

            tk.Label(grid, text="Mid Sleep (s):", font=("Segoe UI", 8)).grid(row=1, column=0, sticky="w", pady=2)
            self._register_entry(grid, textvariable=v["mid_delay"], width=8).grid(row=1, column=1, padx=5, pady=2)

            tk.Label(grid, text="Mid Variance:", font=("Segoe UI", 8)).grid(row=1, column=2, sticky="w", padx=(10, 0), pady=2)
            self._register_entry(grid, textvariable=v["mid_var"], width=6).grid(row=1, column=3, padx=5, pady=2)

            tk.Label(grid, text="End Sleep (s):", font=("Segoe UI", 8)).grid(row=2, column=0, sticky="w", pady=2)
            self._register_entry(grid, textvariable=v["post_delay"], width=8).grid(row=2, column=1, padx=5, pady=2)

            tk.Label(grid, text="2nd Key:", font=("Segoe UI", 8)).grid(row=2, column=2, sticky="w", padx=(10, 0), pady=2)
            self._register_entry(grid, textvariable=v["key_2"], width=6).grid(row=2, column=3, padx=5, pady=2)

        self._select_kill_tab(1)

        # ----------------------------------------------------
        # 3. CUSTOMIZE SWAP, CATCH & ALARM
        # ----------------------------------------------------
        def build_macro_section(title, color, action_key, swap_label=None):
            box = tk.LabelFrame(scrollable_prop, text=title, font=("Segoe UI", 9, "bold"), fg=color, padx=10, pady=8)
            box.pack(fill="x", pady=5)
            v = self.cust_vars[action_key]

            if swap_label and "include_swap" in v:
                cb = tk.Checkbutton(box, text=swap_label, variable=v["include_swap"], font=("Segoe UI", 8, "bold"))
                cb.pack(anchor="w", pady=(0, 4))
                self.lockable_widgets.append(cb)

            grid = tk.Frame(box)
            grid.pack(fill="x", pady=2)

            tk.Label(grid, text="Start Sleep (s):", font=("Segoe UI", 8)).grid(row=0, column=0, sticky="w", pady=2)
            self._register_entry(grid, textvariable=v["pre_delay"], width=8).grid(row=0, column=1, padx=5, pady=2)

            tk.Label(grid, text="1st Key:", font=("Segoe UI", 8)).grid(row=0, column=2, sticky="w", padx=(10, 0), pady=2)
            self._register_entry(grid, textvariable=v["key_1"], width=6).grid(row=0, column=3, padx=5, pady=2)

            tk.Label(grid, text="Mid Sleep (s):", font=("Segoe UI", 8)).grid(row=1, column=0, sticky="w", pady=2)
            self._register_entry(grid, textvariable=v["mid_delay"], width=8).grid(row=1, column=1, padx=5, pady=2)

            tk.Label(grid, text="Mid Variance:", font=("Segoe UI", 8)).grid(row=1, column=2, sticky="w", padx=(10, 0), pady=2)
            self._register_entry(grid, textvariable=v["mid_var"], width=6).grid(row=1, column=3, padx=5, pady=2)

            tk.Label(grid, text="End Sleep (s):", font=("Segoe UI", 8)).grid(row=2, column=0, sticky="w", pady=2)
            self._register_entry(grid, textvariable=v["post_delay"], width=8).grid(row=2, column=1, padx=5, pady=2)

            tk.Label(grid, text="2nd Key:", font=("Segoe UI", 8)).grid(row=2, column=2, sticky="w", padx=(10, 0), pady=2)
            self._register_entry(grid, textvariable=v["key_2"], width=6).grid(row=2, column=3, padx=5, pady=2)

        build_macro_section(" Action: SWAP (execute_swap) ", "#FF9800", "swap")
        build_macro_section(" Action: CATCH (execute_catch) ", "purple", "catch", "Include Swap (execute_swap) before Catch")

        # Alarm Customization
        alarm_box = tk.LabelFrame(scrollable_prop, text=" Action: ALARM (execute_alarm) ", font=("Segoe UI", 9, "bold"), fg="#b71c1c", padx=10, pady=8)
        alarm_box.pack(fill="x", pady=5)
        va = self.cust_vars["alarm"]

        tk.Checkbutton(alarm_box, text="Stop Bot When Alarm Triggers", variable=va["stop_bot"], font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 4))

        tk.Label(alarm_box, text="Alarm Volume (%):", font=("Segoe UI", 8, "bold")).pack(anchor="w")
        tk.Scale(alarm_box, variable=va["volume"], from_=0, to=100, orient="horizontal", tickinterval=25, resolution=1).pack(fill="x", pady=(0, 5))

        tk.Label(alarm_box, text="Custom Audio File (.mp3 / .wav) [Blank = Built-in Siren]:", font=("Segoe UI", 8)).pack(anchor="w")
        file_row = tk.Frame(alarm_box)
        file_row.pack(fill="x", pady=2)
        self._register_entry(file_row, textvariable=va["audio_file"], width=22).pack(side="left", fill="x", expand=True, padx=(0, 4))
        tk.Button(file_row, text="📂 Browse", font=("Segoe UI", 8), command=self._browse_alarm_audio).pack(side="left", padx=2)
        tk.Button(file_row, text="❌", font=("Segoe UI", 8), command=lambda: va["audio_file"].set("")).pack(side="left")

        freq_grid = tk.Frame(alarm_box)
        freq_grid.pack(fill="x", pady=4)
        tk.Label(freq_grid, text="Siren High Hz:", font=("Segoe UI", 8)).grid(row=0, column=0, sticky="w")
        self._register_entry(freq_grid, textvariable=va["freq_high"], width=7).grid(row=0, column=1, padx=5)
        tk.Label(freq_grid, text="Siren Low Hz:", font=("Segoe UI", 8)).grid(row=0, column=2, sticky="w", padx=(10, 0))
        self._register_entry(freq_grid, textvariable=va["freq_low"], width=7).grid(row=0, column=3, padx=5)

        tk.Button(alarm_box, text="🔊 Test Alarm (Save & Preview)", bg="#d32f2f", fg="white", font=("Segoe UI", 8, "bold"), command=self._test_alarm_from_ui).pack(fill="x", pady=(4, 0))

        # ----------------------------------------------------
        # 4. MOVEMENT BOUNDS & DIRECTION KEYS
        # ----------------------------------------------------
        mov_frame = tk.LabelFrame(scrollable_prop, text=" Movement Bounds & Direction Keys ", font=("Segoe UI", 9, "bold"), padx=10, pady=8)
        mov_frame.pack(fill="x", pady=5)

        bounds_row = tk.Frame(mov_frame)
        bounds_row.pack(fill="x", pady=2)

        tk.Label(bounds_row, text="Left:", font=("Segoe UI", 8)).pack(side="left")
        btn_l_minus = tk.Button(bounds_row, text="-", width=2, command=lambda: self.adjust_bound('left', -1.0))
        btn_l_minus.pack(side="left", padx=(4, 1))
        self._register_entry(bounds_row, textvariable=self.bound_left_var, width=5, justify="center", font=("Segoe UI", 8, "bold")).pack(side="left")
        btn_l_plus = tk.Button(bounds_row, text="+", width=2, command=lambda: self.adjust_bound('left', 1.0))
        btn_l_plus.pack(side="left", padx=(1, 12))

        tk.Label(bounds_row, text="Right:", font=("Segoe UI", 8)).pack(side="left")
        btn_r_minus = tk.Button(bounds_row, text="-", width=2, command=lambda: self.adjust_bound('right', -1.0))
        btn_r_minus.pack(side="left", padx=(4, 1))
        self._register_entry(bounds_row, textvariable=self.bound_right_var, width=5, justify="center", font=("Segoe UI", 8, "bold")).pack(side="left")
        btn_r_plus = tk.Button(bounds_row, text="+", width=2, command=lambda: self.adjust_bound('right', 1.0))
        btn_r_plus.pack(side="left", padx=(1, 0))

        self.lockable_widgets.extend([btn_l_minus, btn_l_plus, btn_r_minus, btn_r_plus])

        mov_grid = tk.Frame(mov_frame)
        mov_grid.pack(fill="x", pady=(6, 0))

        tk.Label(mov_grid, text="Move Left Key:", font=("Segoe UI", 8)).grid(row=0, column=0, sticky="w", pady=2)
        self._register_entry(mov_grid, textvariable=self.move_left_key_var, width=8).grid(row=0, column=1, padx=5, pady=2)

        tk.Label(mov_grid, text="Move Right Key:", font=("Segoe UI", 8)).grid(row=0, column=2, sticky="w", padx=(8, 0), pady=2)
        self._register_entry(mov_grid, textvariable=self.move_right_key_var, width=8).grid(row=0, column=3, padx=5, pady=2)

        tk.Label(mov_grid, text="Speed (blk/s):", font=("Segoe UI", 8)).grid(row=1, column=0, sticky="w", pady=2)
        self._register_entry(mov_grid, textvariable=self.blocks_per_sec_var, width=8).grid(row=1, column=1, padx=5, pady=2)

        tk.Label(mov_grid, text="Turn Pause (s):", font=("Segoe UI", 8)).grid(row=1, column=2, sticky="w", padx=(8, 0), pady=2)
        self._register_entry(mov_grid, textvariable=self.stop_pause_var, width=8).grid(row=1, column=3, padx=5, pady=2)

        # ----------------------------------------------------
        # 5. SIMILARITY THRESHOLDS (%)
        # ----------------------------------------------------
        thresh_frame = tk.LabelFrame(scrollable_prop, text=" Similarity Thresholds (%) ", font=("Segoe UI", 9, "bold"), padx=10, pady=8)
        thresh_frame.pack(fill="x", pady=5)

        def add_slider(parent, label_text, var, from_v, to_v, tick):
            tk.Label(parent, text=label_text, font=("Segoe UI", 8)).pack(anchor="w")
            tk.Scale(parent, variable=var, from_=from_v, to=to_v, orient="horizontal", tickinterval=tick, resolution=1.0).pack(fill="x", pady=(0, 4))

        add_slider(thresh_frame, "UI Lock Similarity (Hunting -> Lock UI):", self.ui_lock_threshold, 10, 100, 15)
        add_slider(thresh_frame, "Battle Active UI Similarity (Switch / Stay in Battle):", self.battle_ui_threshold, 10, 100, 15)
        add_slider(thresh_frame, "Recognized Target Threshold:", self.target_sim_threshold, 50, 100, 10)
        add_slider(thresh_frame, "Unrecognized Detection Minimum:", self.unrecog_sim_threshold, 10, 80, 10)
        add_slider(thresh_frame, "Rare Base Detection Similarity:", self.rare_base_threshold, 10, 100, 15)
        add_slider(thresh_frame, "Rare 'X' Click Similarity:", self.x_click_threshold, 20, 100, 20)

        # ----------------------------------------------------
        # 6. TIMINGS & COOLDOWNS
        # ----------------------------------------------------
        time_frame = tk.LabelFrame(scrollable_prop, text=" Timings & Cooldowns (Seconds) ", font=("Segoe UI", 9, "bold"), padx=10, pady=8)
        time_frame.pack(fill="x", pady=5)
        t_grid = tk.Frame(time_frame)
        t_grid.pack(fill="x")

        tk.Label(t_grid, text="Start Delay (s):", font=("Segoe UI", 8)).grid(row=0, column=0, sticky="w", pady=2)
        self._register_entry(t_grid, textvariable=self.start_delay_var, width=7).grid(row=0, column=1, padx=5, pady=2)

        tk.Label(t_grid, text="Hold Start (s):", font=("Segoe UI", 8)).grid(row=0, column=2, sticky="w", padx=(8, 0), pady=2)
        self._register_entry(t_grid, textvariable=self.hold_start_sec_var, width=7).grid(row=0, column=3, padx=5, pady=2)

        tk.Label(t_grid, text="Spawn Wait (s):", font=("Segoe UI", 8)).grid(row=1, column=0, sticky="w", pady=2)
        self._register_entry(t_grid, textvariable=self.battle_spawn_wait_var, width=7).grid(row=1, column=1, padx=5, pady=2)

        tk.Label(t_grid, text="Cooldown (s):", font=("Segoe UI", 8)).grid(row=1, column=2, sticky="w", padx=(8, 0), pady=2)
        self._register_entry(t_grid, textvariable=self.action_cooldown_var, width=7).grid(row=1, column=3, padx=5, pady=2)

        tk.Label(t_grid, text="Anim Grace (s):", font=("Segoe UI", 8)).grid(row=2, column=0, sticky="w", pady=2)
        self._register_entry(t_grid, textvariable=self.anim_grace_var, width=7).grid(row=2, column=1, padx=5, pady=2)

        tk.Label(t_grid, text="Stuck Timeout (s):", font=("Segoe UI", 8)).grid(row=2, column=2, sticky="w", padx=(8, 0), pady=2)
        self._register_entry(t_grid, textvariable=self.stuck_timeout_var, width=7).grid(row=2, column=3, padx=5, pady=2)

        # ----------------------------------------------------
        # 7. UNRECOGNIZED TARGET ACTION
        # ----------------------------------------------------
        action_frame = tk.LabelFrame(scrollable_prop, text=" Unrecognized Target Action ", font=("Segoe UI", 9, "bold"), padx=10, pady=8)
        action_frame.pack(fill="x", pady=5)

        ignore_rb = tk.Radiobutton(action_frame, text="Ignore", variable=self.unrecognized_action, value="ignore", font=("Segoe UI", 9, "bold"))

        kill_row = tk.Frame(action_frame)
        kill_rb = tk.Radiobutton(kill_row, text="Kill using:", variable=self.unrecognized_action, value="kill", font=("Segoe UI", 9, "bold"))
        kill_rb.pack(side="left")
        u_move_opt = tk.OptionMenu(kill_row, self.unrecog_kill_move_var, *self.MOVE_LABELS)
        u_move_opt.config(font=("Segoe UI", 8), padx=4, pady=0)
        u_move_opt.pack(side="left", padx=6)
        self.lockable_widgets.append(u_move_opt)

        catch_rb = tk.Radiobutton(action_frame, text="Catch", variable=self.unrecognized_action, value="catch", font=("Segoe UI", 9, "bold"))
        alarm_rb = tk.Radiobutton(action_frame, text="Alarm (execute_alarm)", variable=self.unrecognized_action, value="alarm", font=("Segoe UI", 9, "bold"))

        def update_rb_colors():
            selected = self.unrecognized_action.get()
            ignore_rb.config(fg="gray" if selected == "ignore" else "black")
            kill_rb.config(fg="red" if selected == "kill" else "black")
            catch_rb.config(fg="purple" if selected == "catch" else "black")
            alarm_rb.config(fg="#d32f2f" if selected == "alarm" else "black")

        self._update_unrecog_rb_colors = update_rb_colors

        ignore_rb.config(command=update_rb_colors)
        ignore_rb.pack(anchor="w", pady=(0, 2))

        kill_rb.config(command=update_rb_colors)
        kill_row.pack(anchor="w", pady=(0, 2))

        for rb in (catch_rb, alarm_rb):
            rb.config(command=update_rb_colors)
            rb.pack(anchor="w", pady=(0, 2))
        update_rb_colors()

        tk.Checkbutton(action_frame, text=f"Auto-Save Unrecognized Pokémon to '{TARGETS_FOLDER}/'", variable=self.auto_capture_var, font=("Segoe UI", 9, "bold"), fg="#2196F3").pack(anchor="w", pady=(6, 0))

        # ----------------------------------------------------
        # 8. SAFETY, HOTKEYS & HARDWARE
        # ----------------------------------------------------
        safety_frame = tk.LabelFrame(scrollable_prop, text=" Safety, Hotkeys & Hardware ", font=("Segoe UI", 9, "bold"), padx=10, pady=8)
        safety_frame.pack(fill="x", pady=5)
        tk.Checkbutton(safety_frame, text="Enable Stuck Screen Alarm", variable=self.enable_stuck_alarm, font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 2))
        tk.Checkbutton(safety_frame, text="Save Debug ROI Screenshots to SSD", variable=self.enable_debug_screenshots, font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 4))

        hw_grid = tk.Frame(safety_frame)
        hw_grid.pack(fill="x")

        tk.Label(hw_grid, text="Start Hotkey:", font=("Segoe UI", 8)).grid(row=0, column=0, sticky="w", pady=2)
        self._register_entry(hw_grid, textvariable=self.start_hotkey_var, width=8).grid(row=0, column=1, padx=5, pady=2)

        tk.Label(hw_grid, text="Stop Hotkey:", font=("Segoe UI", 8)).grid(row=0, column=2, sticky="w", padx=(8, 0), pady=2)
        self._register_entry(hw_grid, textvariable=self.stop_hotkey_var, width=8).grid(row=0, column=3, padx=5, pady=2)

        tk.Label(hw_grid, text="COM Port:", font=("Segoe UI", 8)).grid(row=1, column=0, sticky="w", pady=2)
        self._register_entry(hw_grid, textvariable=self.com_port_var, width=8).grid(row=1, column=1, padx=5, pady=2)

        tk.Label(hw_grid, text="Baud Rate:", font=("Segoe UI", 8)).grid(row=1, column=2, sticky="w", padx=(8, 0), pady=2)
        self._register_entry(hw_grid, textvariable=self.baud_rate_var, width=8).grid(row=1, column=3, padx=5, pady=2)

        tk.Button(safety_frame, text="🔌 Reconnect Arduino", font=("Segoe UI", 8), command=self._reconnect_arduino).pack(fill="x", pady=(4, 0))

        # ----------------------------------------------------
        # 9. FOLDER ACCESS
        # ----------------------------------------------------
        folder_frame = tk.LabelFrame(scrollable_prop, text=" Folder Access ", font=("Segoe UI", 9, "bold"), padx=10, pady=8)
        folder_frame.pack(fill="x", pady=5)

        tk.Button(folder_frame, text="📂 System / Base Image", command=lambda: self.open_folder(".")).pack(fill="x", pady=2)
        tk.Button(folder_frame, text=f"📂 Targets Folder ({TARGETS_FOLDER}/)", command=lambda: self.open_folder(TARGETS_FOLDER)).pack(fill="x", pady=2)
        tk.Button(folder_frame, text="📂 Debug ROIs", command=lambda: self.open_folder(DEBUG_FOLDER)).pack(fill="x", pady=2)

        # ----------------------------------------------------
        # 10. DATASET BUILDER
        # ----------------------------------------------------
        capture_frame = tk.LabelFrame(scrollable_prop, text=" Dataset Builder (3s Delay) ", font=("Segoe UI", 9, "bold"), padx=10, pady=8)
        capture_frame.pack(fill="x", pady=5)

        default_act_row = tk.Frame(capture_frame)
        default_act_row.pack(fill="x", pady=(0, 5))
        tk.Label(default_act_row, text="New Target Action:", font=("Segoe UI", 8, "bold")).pack(side="left")
        new_act_opt = tk.OptionMenu(default_act_row, self.new_target_action_label_var, *self.NEW_TARGET_ACTION_LABELS)
        new_act_opt.config(font=("Segoe UI", 8), padx=6, pady=0)
        new_act_opt.pack(side="left", padx=6)
        self.lockable_widgets.append(new_act_opt)

        tk.Button(capture_frame, text="📸 Capture New Base Image (Anchor)", bg="#4CAF50", fg="white", font=("Segoe UI", 9, "bold"), command=lambda: self.trigger_screenshot('base')).pack(fill="x", pady=2)
        tk.Button(capture_frame, text="📸 Capture Rare Base Image", bg="#E91E63", fg="white", font=("Segoe UI", 9, "bold"), command=lambda: self.trigger_screenshot('rare_base')).pack(fill="x", pady=2)
        tk.Button(capture_frame, text="📸 Capture 1st ROI (Master Box)", bg="#607D8B", fg="white", font=("Segoe UI", 9, "bold"), command=lambda: self.trigger_screenshot('master')).pack(fill="x", pady=2)
        tk.Button(capture_frame, text="📸 Capture 2nd ROI (Target Inject)", bg="#9C27B0", fg="white", font=("Segoe UI", 9, "bold"), command=lambda: self.trigger_screenshot('battle')).pack(fill="x", pady=2)

    def _reconnect_arduino(self):
        if self.save_config(show_popup=False):
            port = self.action_config["general"]["com_port"]
            baud = self.action_config["general"]["baud_rate"]
            ok = self.oled.connect(port, baud)
            self._refresh_arduino_status_label()
            if ok:
                messagebox.showinfo("Arduino", f"Connected to Arduino on {port} @ {baud}!")
            else:
                messagebox.showwarning("Arduino", f"Could not connect to {port} @ {baud}.")

    def _browse_alarm_audio(self):
        filepath = filedialog.askopenfilename(
            title="Select Custom Alarm Audio",
            filetypes=[("Audio Files", "*.mp3 *.wav"), ("All Files", "*.*")]
        )
        if filepath:
            self.cust_vars["alarm"]["audio_file"].set(filepath)

    def _test_alarm_from_ui(self):
        if self.save_config(show_popup=False):
            self.execute_alarm("TEST ALARM", 100.0, is_test=True)

    # ========================================================
    # DATASET BUILDER & SCREENSHOTTER
    # ========================================================
    def open_folder(self, folder_path):
        try:
            os.startfile(os.path.abspath(folder_path))
        except Exception:
            pass

    def trigger_screenshot(self, roi_type):
        anchor_img, _ = self.vision.get_system_anchor_image(allow_reference_fallback=(roi_type != 'base'))
        if anchor_img is None:
            messagebox.showerror(
                "Error",
                f"Missing '{SYSTEM_REF_IMAGE_NAME}.png' or '{SYSTEM_REF_IMAGE_NAME}.jpg'!\n"
                "The screenshotter requires this anchor image to locate the UI."
            )
            return
        selected_label = self.new_target_action_label_var.get()
        default_code = "ask" if selected_label == "Ask Me" else self.ACTION_LABEL_TO_CODE.get(selected_label, "ask")
        threading.Thread(target=self.execute_delayed_capture, args=(roi_type, default_code), daemon=True).start()

    def _reload_and_rebuild_on_main_thread(self):
        self.vision.load_templates(self.oled, self.action_config["targets"])
        self.config_mgr.save()
        self._rebuild_target_roster_ui()

    def prompt_save_action(self, image, prefix, timestamp, scan_time):
        top = tk.Toplevel(self.root)
        top.title("Assign Action & Save Target")
        top.geometry("380x130")
        top.attributes('-topmost', True)

        tk.Label(top, text=f"Save to '{TARGETS_FOLDER}/' with action:", font=("Segoe UI", 10, "bold")).pack(pady=(8, 6))

        row1 = tk.Frame(top)
        row1.pack(pady=2)
        row2 = tk.Frame(top)
        row2.pack(pady=4)

        def save_and_close(action_code):
            filename = f"{prefix}_{timestamp}.png"
            filepath = os.path.join(TARGETS_FOLDER, filename)
            cv2.imwrite(filepath, image)
            self.action_config["targets"][filename] = {"enabled": True, "action": action_code}
            label = self.ACTION_CODE_TO_LABEL.get(action_code, action_code)
            print(f"✅ Saved '{filename}' to '{TARGETS_FOLDER}/' with action [{label}] | {scan_time:.3f}s")
            self._reload_and_rebuild_on_main_thread()
            top.destroy()

        for m_idx in (1, 2, 3, 4):
            code = f"kill_{m_idx}"
            tk.Button(row1, text=f"Move {m_idx}", bg="#d32f2f", fg="white", font=("Segoe UI", 8, "bold"), width=8, command=lambda c=code: save_and_close(c)).pack(side="left", padx=3)

        tk.Button(row2, text="Catch", bg="#7b1fa2", fg="white", font=("Segoe UI", 8, "bold"), width=9, command=lambda: save_and_close("catch")).pack(side="left", padx=4)
        tk.Button(row2, text="Alert", bg="#ef6c00", fg="white", font=("Segoe UI", 8, "bold"), width=9, command=lambda: save_and_close("alert")).pack(side="left", padx=4)
        tk.Button(row2, text="Discard", font=("Segoe UI", 8), width=9, command=top.destroy).pack(side="left", padx=4)

    def _save_or_prompt_target(self, image, prefix, timestamp, action_code, scale_info="", scan_time=0.0):
        if action_code in ConfigManager.VALID_ACTIONS:
            filename = f"{prefix}_{timestamp}.png"
            filepath = os.path.join(TARGETS_FOLDER, filename)
            cv2.imwrite(filepath, image)
            self.action_config["targets"][filename] = {"enabled": True, "action": action_code}
            label = self.ACTION_CODE_TO_LABEL.get(action_code, action_code)
            if prefix == "AutoTarget":
                print(f"\n📸 AUTONOMOUS LEARNING: Saved '{filepath}' with action [{label}]")
            else:
                print(f"✅ Saved '{filepath}' with action [{label}]{scale_info} | {scan_time:.3f}s")
            self.root.after(0, self._reload_and_rebuild_on_main_thread)
        else:
            self.root.after(0, lambda img=image, pf=prefix, ts=timestamp, sc=scan_time: self.prompt_save_action(img, pf, ts, sc))

    def execute_delayed_capture(self, roi_type, action_code):
        print("\n[Screenshot Tool] Triggered. Bring game to front!")
        for i in range(3, 0, -1):
            print(f"Snapping in {i}...")
            winsound.Beep(1000, 200)
            time.sleep(0.8)

        winsound.Beep(1500, 400)
        print("📸 SNAP!")

        start_time = time.time()
        screenshot = pyautogui.screenshot()
        frame_color = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        frame_gray = cv2.cvtColor(frame_color, cv2.COLOR_BGR2GRAY)

        system_template_gray, anchor_used = self.vision.get_system_anchor_image(allow_reference_fallback=(roi_type != 'base'))
        if system_template_gray is None:
            print(f"❌ Missing '{SYSTEM_REF_IMAGE_NAME}' (.png/.jpg) anchor image!")
            return

        print(f"[*] Anchoring screenshot using: {anchor_used}")
        best_sim, best_scale, best_loc, best_dims = self.vision.find_multiscale_anchor(frame_gray, system_template_gray)

        if best_sim < 0.15:
            print(f"⚠️ Failed to find the battle UI! (Match: {best_sim * 100:.1f}%)")
            return

        base_x, base_y = int(best_loc[0]), int(best_loc[1])
        rw, rh = best_dims
        timestamp = int(time.time())
        scan_time = time.time() - start_time

        if roi_type == 'base':
            master_crop = frame_color[base_y:base_y + rh, base_x:base_x + rw]
            cv2.imwrite(REFERENCE_FRAME_IMAGE, master_crop)
            print(f"✅ Saved NEW Base Image to {REFERENCE_FRAME_IMAGE} | {scan_time:.3f}s")
            self.root.after(0, self._reload_and_rebuild_on_main_thread)

        elif roi_type == 'rare_base':
            master_crop = frame_color[base_y:base_y + rh, base_x:base_x + rw]
            cv2.imwrite(RARE_BASE_IMAGE_DEFAULT, master_crop)
            print(f"✅ Saved NEW Rare Base Image to {RARE_BASE_IMAGE_DEFAULT} | {scan_time:.3f}s")
            self.root.after(0, self._reload_and_rebuild_on_main_thread)

        elif roi_type == 'master':
            master_crop = frame_color[base_y:base_y + rh, base_x:base_x + rw]
            filename = os.path.join(CAPTURED_ROIS_FOLDER, f"1st_ROI_Master_{timestamp}.png")
            cv2.imwrite(filename, master_crop)
            print(f"✅ Saved 1st ROI: {best_scale:.2f}x Scale | {scan_time:.3f}s")

        elif roi_type == 'battle':
            bw, bh = rw // 2, rh // 2
            bx, by = base_x + bw, base_y
            battle_crop = frame_color[by:by + bh, bx:bx + bw]
            self._save_or_prompt_target(battle_crop, "ManualTarget", timestamp, action_code, f": {best_scale:.2f}x Scale", scan_time)

    # ========================================================
    # BOT CONTROLS & MACRO ACTIONS
    # ========================================================
    def display_all_scan_results(self):
        if not self.last_scan_results:
            messagebox.showinfo("Scan Results", "No scan data available yet.\nThe bot needs to enter a battle first to scan enabled targets.")
            return

        sorted_results = sorted(self.last_scan_results.items(), key=lambda item: item[1], reverse=True)
        top = tk.Toplevel(self.root)
        top.title("Similarity Scores (Active Roster)")
        top.geometry("320x320")
        top.attributes('-topmost', True)

        tk.Label(top, text="Similarity Scores", font=("Segoe UI", 11, "bold")).pack(pady=(5, 0))
        tk.Label(top, text="(Only enabled roster targets are scanned)", font=("Segoe UI", 8, "italic"), fg="gray").pack(pady=(0, 5))

        text_frame = tk.Frame(top)
        text_frame.pack(expand=True, fill="both", padx=10, pady=10)
        scrollbar = tk.Scrollbar(text_frame)
        scrollbar.pack(side="right", fill="y")
        txt = tk.Text(text_frame, font=("Consolas", 10), yscrollcommand=scrollbar.set)
        txt.pack(side="left", expand=True, fill="both")
        scrollbar.config(command=txt.yview)

        for name, sim in sorted_results:
            clean_name = os.path.splitext(name)[0]
            if sim < 0:
                txt.insert(tk.END, f"{clean_name:<18} : [SIZE ERROR]\n")
            else:
                txt.insert(tk.END, f"{clean_name:<18} : {sim:.1f}%\n")
        txt.config(state="disabled")

    def adjust_bound(self, side, amount):
        try:
            self.movement.bound_left = float(self.bound_left_var.get())
            self.movement.bound_right = float(self.bound_right_var.get())
        except ValueError:
            pass
        self.movement.adjust_bound(side, amount)
        self.bound_left_var.set(f"{self.movement.bound_left:.1f}")
        self.bound_right_var.set(f"{self.movement.bound_right:.1f}")

    def set_status(self, text, color):
        self.status_label.config(text=f"Status: {text}", fg=color)

    @staticmethod
    def human_sleep(base, variance):
        time.sleep(max(0.01, random.gauss(base, variance)))

    def _run_macro(self, action_key, start_oled_msg, end_oled_msg):
        cfg = self.action_config.get(action_key, self.config_mgr.DEFAULT_CONFIG[action_key])
        time.sleep(cfg["pre_delay"])
        self.oled.send(start_oled_msg)
        for key_field in ("key_1", "key_2"):
            key_val = str(cfg.get(key_field, "")).strip()
            if key_val:
                try:
                    keyboard.send(key_val)
                except ValueError as e:
                    print(f"❌ Invalid key '{key_val}' in {action_key} ({key_field}): {e}")
            if key_field == "key_1":
                self.human_sleep(cfg["mid_delay"], cfg["mid_var"])
        self.oled.send(end_oled_msg)
        time.sleep(cfg["post_delay"])

    def execute_kill(self, move_slot=1):
        if move_slot not in (1, 2, 3, 4):
            move_slot = 1
        self._run_macro(f"kill_{move_slot}", f"Action: Move {move_slot}", "Waiting turn...")

    def execute_swap(self):
        self._run_macro("swap", "Action: Swap", "Swapping...")

    def execute_catch(self):
        self._run_macro("catch", "Action: Catch", "Throwing ball...")

    def execute_alarm(self, target_name="Alert Target", highest_sim=100.0, is_test=False):
        cfg = self.action_config.get("alarm", self.config_mgr.DEFAULT_CONFIG["alarm"])
        if cfg.get("stop_bot", True) and not is_test:
            self.is_running = False
        self.oled.send(f"ALERT: {target_name[:13]}")
        self.root.after(0, lambda: self._show_alarm_modal(target_name, highest_sim, cfg))

    def _show_alarm_modal(self, target_name, sim, cfg):
        if self.alarm_active:
            return
        self.alarm_active = True
        self.set_status(f"ALERT ({target_name})", "red")
        self.start_btn.config(state="disabled")

        self.alarm_mgr.start(
            volume_pct=cfg.get("volume", 100),
            audio_file=cfg.get("audio_file", ""),
            freq_high=cfg.get("freq_high", 2000),
            freq_low=cfg.get("freq_low", 1500)
        )

        top = tk.Toplevel(self.root)
        top.title("🚨 TARGET ALERT!")
        top.geometry("340x180")
        top.attributes('-topmost', True)
        top.resizable(False, False)
        top.configure(bg="#ffebee", padx=15, pady=15)
        top.grab_set()

        tk.Label(
            top,
            text=f"🚨 EMERGENCY ALERT!\n{target_name} ({sim:.1f}%) found!",
            font=("Segoe UI", 12, "bold"),
            fg="#b71c1c",
            bg="#ffebee",
            justify="center"
        ).pack(pady=(5, 15))

        def dismiss_alarm():
            self.alarm_mgr.stop()
            self.alarm_active = False
            if not self.is_running:
                self.set_status("IDLE", "gray")
                self.start_btn.config(state="normal")
                self.oled.send("Bot Offline")
            if top.winfo_exists():
                top.destroy()

        top.protocol("WM_DELETE_WINDOW", dismiss_alarm)

        tk.Button(
            top,
            text="🔕 DISMISS & STOP ALARM",
            bg="#d32f2f",
            fg="white",
            font=("Segoe UI", 11, "bold"),
            height=2,
            command=dismiss_alarm
        ).pack(fill="x")

    def _walk_overworld_step(self):
        arrived = self.movement.update_hold()
        if arrived:
            pause_base = float(self.action_config["movement"].get("stop_pause", 0.2))
            if pause_base > 0:
                time.sleep(max(0.02, random.gauss(pause_base, pause_base * 0.25)))
            self.movement.pick_new_destination()
            self.movement.last_tick_time = time.time()

    def _execute_combat_decision(self, action_code, highest_sim, clean_name=None):
        if action_code in ("alert", "alarm"):
            label_name = clean_name if clean_name else "Unrecognized Pokemon"
            self.target_sim_label.config(text=f"Target: {label_name} ({highest_sim:.1f}%) [ALARM]", fg="red")
            print(f"\n🚨 ALARM TRIGGERED: {label_name} ({highest_sim:.1f}%)!")
            self.execute_alarm(label_name, highest_sim)
            self.last_action_time = time.time()
            self.movement.last_tick_time = time.time()
            return

        is_kill = action_code in self.KILL_KEYS
        move_slot = int(action_code.split("_")[1]) if is_kill else 1
        cfg_key = action_code if is_kill else "catch"
        cfg = self.action_config.get(cfg_key, self.config_mgr.DEFAULT_CONFIG.get(cfg_key, {}))

        if cfg.get("include_swap", False) and not self.has_swapped:
            self.target_sim_label.config(text=f"Swapping Tank... ({highest_sim:.1f}%)", fg="purple")
            if clean_name:
                if is_kill:
                    print(f"\n🔄 Swapping to tank before Move {move_slot} for: {clean_name}")
                else:
                    print(f"\n🔄 Swapping to tank for: {clean_name}")
            else:
                if is_kill:
                    print(f"\n🔄 Swapping to tank before Move {move_slot} for Unrecognized Pokemon ({highest_sim:.1f}%)")
                else:
                    print(f"\n🔄 Swapping to tank for Unrecognized Pokemon ({highest_sim:.1f}%)")

            self.oled.send_throttled("Tg: SWAPPING")
            self.execute_swap()
            self.has_swapped = True
            self.last_action_time = time.time()
            self.movement.last_tick_time = time.time()
            return

        if is_kill:
            if clean_name:
                self.target_sim_label.config(text=f"Target: {clean_name} ({highest_sim:.1f}%) [KILL M{move_slot}]", fg="blue")
                print(f"\n✅ Target detected (KILL - Move {move_slot}): {clean_name} ({highest_sim:.1f}%)")
                self.oled.send_throttled(f"Tg:{clean_name[:10]} M{move_slot}")
            else:
                self.target_sim_label.config(text=f"Killing Unrecognized [M{move_slot}] ({highest_sim:.1f}%)", fg="orange")
                print(f"\n⚠️ Unrecognized Pokemon ({highest_sim:.1f}%). Killing with Move {move_slot}!")
                self.oled.send_throttled(f"Tg: UNKNOWN M{move_slot}")
            self.execute_kill(move_slot=move_slot)

        elif action_code == "catch":
            if clean_name:
                self.target_sim_label.config(text=f"Target: {clean_name} ({highest_sim:.1f}%) [CATCH]", fg="purple")
                print(f"\n✨ Target detected (CATCH): {clean_name} ({highest_sim:.1f}%)")
                self.oled.send_throttled(f"Tg: {clean_name[:14]}")
            else:
                self.target_sim_label.config(text=f"Catching Unrecognized ({highest_sim:.1f}%)", fg="purple")
                print(f"\n✨ Unrecognized Pokemon ({highest_sim:.1f}%). Catching it!")
                self.oled.send_throttled("Tg: CATCHING")
            self.execute_catch()

        self.last_action_time = time.time()
        self.movement.last_tick_time = time.time()

    def start_bot(self):
        if not self.is_running and not self.alarm_active:
            self.root.focus_set()
            if not self.save_config(show_popup=False):
                return

            if self.vision.reference_template is None:
                messagebox.showerror("CRITICAL ERROR", f"Missing '{REFERENCE_FRAME_IMAGE}'!\n\nYou MUST use Properties & Subsystems to capture a new base image before the Auto Grinder can start.")
                return

            self.MASTER_ROI = None
            self.BATTLE_ROI = None

            self.in_battle = False
            self.last_action_time = 0.0
            self.has_swapped = False
            self.auto_captured_this_battle = False
            self.rare_base_notified = False

            self.last_checked_frame = None
            self.last_screen_change_time = time.time()

            self._set_entries_state("disabled")

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

        start_delay = float(self.action_config["timings"].get("start_delay", 3.0))
        stop_key = self.action_config["general"].get("stop_hotkey", "q").strip().lower() or "q"

        self.oled.send(f"Starting in {start_delay:.1f}s...")
        time.sleep(start_delay)
        self.movement.pick_new_destination()
        self.movement.last_tick_time = time.time()
        self.oled.last_update = time.time()
        self.oled.send("Bot Active")

        try:
            while self.is_running and not keyboard.is_pressed(stop_key):
                ui_lock_thresh = self.ui_lock_threshold.get()
                battle_ui_thresh = self.battle_ui_threshold.get()
                rare_thresh = self.rare_base_threshold.get()
                spawn_wait = float(self.action_config["timings"].get("battle_spawn_wait", 1.7))
                action_cd = float(self.action_config["timings"].get("action_cooldown", 3.2))
                anim_grace = float(self.action_config["timings"].get("anim_grace_period", 2.5))

                # ========================================================
                # PHASE 1: HUNTING (Strict 1.0x Scale)
                # ========================================================
                if self.MASTER_ROI is None:
                    self.set_status("Searching UI...", "#ff9800")
                    screenshot = pyautogui.screenshot()
                    full_screen_frame = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

                    self._check_stuck_screen(full_screen_frame)

                    th, tw = self.vision.reference_template.shape[:2]

                    if tw <= full_screen_frame.shape[1] and th <= full_screen_frame.shape[0]:
                        result = cv2.matchTemplate(full_screen_frame, self.vision.reference_template, cv2.TM_CCOEFF_NORMED)
                        _, best_sim, _, best_loc = cv2.minMaxLoc(result)
                    else:
                        best_sim = 0.0
                        best_loc = (0, 0)

                    ref_sim = best_sim * 100

                    rare_detected, rare_sim, _ = self.vision.detect_rare_base_image(
                        full_screen_frame, normal_ui_sim=ref_sim, threshold=rare_thresh
                    )
                    if rare_detected:
                        self._handle_rare_base_detected(full_screen_frame, rare_sim, offset=(0, 0))
                        continue
                    else:
                        self.rare_base_notified = False

                    self.ui_match_label.config(text=f"UI Frame Match:  {ref_sim:.1f}%")
                    self.oled.send_throttled(f"Hunt Sim: {ref_sim:.0f}%")

                    if ref_sim >= ui_lock_thresh:
                        self.movement.release()

                        base_x, base_y = int(best_loc[0]), int(best_loc[1])
                        bw, bh = tw // 2, th // 2
                        bx, by = base_x + bw, base_y

                        self.MASTER_ROI = (base_x, base_y, tw, th)
                        self.BATTLE_ROI = (bx, by, bw, bh)

                        print(f"\n[+] Locked UI ({ref_sim:.1f}% >= {ui_lock_thresh:.1f}%).")

                        master_crop = full_screen_frame[base_y:base_y + th, base_x:base_x + tw]
                        battle_crop = full_screen_frame[by:by + bh, bx:bx + bw]

                        if self.enable_debug_screenshots.get():
                            cv2.imwrite(os.path.join(DEBUG_FOLDER, "defined_master_roi.png"), master_crop)
                            cv2.imwrite(os.path.join(DEBUG_FOLDER, "defined_battle_roi.png"), battle_crop)

                        self.oled.send("Encounter Found!")
                        continue
                    else:
                        self._walk_overworld_step()
                        continue

                # ========================================================
                # PHASE 2: BATTLE
                # ========================================================
                else:
                    screenshot_master = pyautogui.screenshot(region=self.MASTER_ROI)
                    master_frame = cv2.cvtColor(np.array(screenshot_master), cv2.COLOR_RGB2BGR)

                    self._check_stuck_screen(master_frame)

                    res_ui = cv2.matchTemplate(master_frame, self.vision.reference_template, cv2.TM_CCOEFF_NORMED)
                    _, max_val_ui, _, _ = cv2.minMaxLoc(res_ui)
                    ui_sim = max_val_ui * 100

                    rare_detected, rare_sim, _ = self.vision.detect_rare_base_image(
                        master_frame, normal_ui_sim=ui_sim, threshold=rare_thresh
                    )
                    if rare_detected:
                        self._handle_rare_base_detected(
                            master_frame,
                            rare_sim,
                            offset=(self.MASTER_ROI[0], self.MASTER_ROI[1])
                        )
                        continue
                    else:
                        self.rare_base_notified = False

                    self.ui_match_label.config(text=f"UI Frame Match:  {ui_sim:.1f}%")

                    if ui_sim < battle_ui_thresh:
                        if self.in_battle and (time.time() - self.last_action_time < anim_grace):
                            self.target_sim_label.config(text="Animation Wait...", fg="orange")
                            continue

                        self.in_battle = False
                        self.last_action_time = 0.0
                        self.has_swapped = False
                        self.auto_captured_this_battle = False
                        self.set_status("Walking / Overworld", "gray")
                        self.target_sim_label.config(text="Target: None", fg="blue")
                        self.oled.send_throttled("Walking...")

                        self._walk_overworld_step()
                        continue

                    # --- IN BATTLE ---
                    if not self.in_battle:
                        self.in_battle = True
                        self.last_action_time = 0.0
                        self.has_swapped = False
                        self.auto_captured_this_battle = False
                        self.battle_start_time = time.time()
                        self.movement.release()

                    self.set_status("Active Battle", "#4CAF50")

                    if time.time() - self.last_action_time < action_cd:
                        self.target_sim_label.config(text="Action Cooldown...", fg="blue")
                        self.oled.send_throttled("Cooldown...")
                        continue

                    if time.time() - self.battle_start_time < spawn_wait:
                        self.target_sim_label.config(text="Waiting for Spawn...", fg="blue")
                        self.oled.send_throttled("Spawning...")
                        continue

                    screenshot_battle = pyautogui.screenshot(region=self.BATTLE_ROI)
                    battle_frame = cv2.cvtColor(np.array(screenshot_battle), cv2.COLOR_RGB2BGR)

                    highest_sim, best_match_name, best_match_action, current_scan_memory = self.vision.scan_targets(battle_frame)
                    self.last_scan_results = current_scan_memory

                    recog_threshold = self.target_sim_threshold.get()
                    unrecog_threshold = self.unrecog_sim_threshold.get()

                    if best_match_name and highest_sim >= recog_threshold:
                        clean_name = os.path.splitext(best_match_name)[0]
                        self._execute_combat_decision(
                            best_match_action,
                            highest_sim,
                            clean_name=clean_name
                        )
                        if not self.is_running:
                            break

                    else:
                        if highest_sim >= unrecog_threshold:
                            if self.auto_capture_var.get() and not self.auto_captured_this_battle:
                                self.auto_captured_this_battle = True
                                timestamp = int(time.time())
                                default_code = self.action_config["general"].get("new_target_default_action", "ask")
                                self._save_or_prompt_target(battle_frame, "AutoTarget", timestamp, default_code)

                            selected_action = self.unrecognized_action.get()
                            if selected_action == "kill":
                                u_move = int(self.action_config["general"].get("unrecognized_kill_move", 1))
                                self._execute_combat_decision(f"kill_{u_move}", highest_sim, clean_name=None)
                                if not self.is_running:
                                    break
                            elif selected_action in ("catch", "alarm"):
                                self._execute_combat_decision(selected_action, highest_sim, clean_name=None)
                                if not self.is_running:
                                    break
                            else:
                                self.target_sim_label.config(text=f"Target Ignored (<{int(recog_threshold)}%): {highest_sim:.1f}%", fg="blue")
                                self.oled.send_throttled("Ignoring Target...")

                        else:
                            self.target_sim_label.config(text=f"Target: Loading... ({highest_sim:.1f}%)", fg="blue")
                            self.oled.send_throttled("Loading Target...")

        except Exception as e:
            traceback.print_exc()
            self.root.after(0, lambda err=str(e): messagebox.showerror("Bot Error", f"Bot stopped due to an error:\n\n{err}"))
        finally:
            self.movement.release_all_direction_keys()
            self.is_running = False
            self.root.after(0, lambda: self._set_entries_state("normal"))
            self.stop_btn.config(state="disabled")
            if not self.alarm_active:
                self.set_status("IDLE", "gray")
                self.start_btn.config(state="normal")
                self.oled.send("Bot Offline")


if __name__ == "__main__":
    root = tk.Tk()
    app = AutoGrinderGUI(root)
    root.mainloop()