import cv2
import numpy as np
import pyautogui
import time
import random
import keyboard
import winsound
import os

# ==========================================
# CONFIGURATION
# ==========================================
# 1. MOVEMENT SETTINGS
SECONDS_PER_BLOCK = 1.0 / 7.0 
BOUND_LEFT = -9.0
BOUND_RIGHT = 9.0

# 2. VISION SETTINGS
TARGET_IMAGES = ['target_1.png', 'target_2.png', 'target_3.png']
RARE_POPUP_IMAGE = 'base_image_rare_pokemon.png'

# 3. DYNAMIC ROI SETTINGS
BATTLE_REGION = None 

# ==========================================
# INTERNAL STATE
# ==========================================
current_pos = 0.0
target_pos = 0.0
target_templates = []
rare_popup_template = None 

currently_held_key = None
last_tick_time = 0.0

def load_templates():
    global rare_popup_template
    print("Loading vision templates...")
    for photo_name in TARGET_IMAGES:
        if os.path.exists(photo_name):
            img = cv2.imread(photo_name)
            if img is not None:
                target_templates.append((photo_name, img))
                print(f"✅ Loaded Target: {photo_name}")
        else:
            print(f"⚠️ Warning: {photo_name} not found.")
            
    if not target_templates:
        print("❌ CRITICAL ERROR: No targets loaded.")
        exit()
        
    if os.path.exists(RARE_POPUP_IMAGE):
        rare_popup_template = cv2.imread(RARE_POPUP_IMAGE)
        if rare_popup_template is not None:
            print(f"✅ Loaded Failsafe: {RARE_POPUP_IMAGE}")
    else:
        print(f"⚠️ WARNING: Could not load '{RARE_POPUP_IMAGE}'. Rare check disabled.")

def human_sleep(base, variance):
    time.sleep(max(0.01, random.gauss(base, variance)))

def release_movement():
    global currently_held_key
    if currently_held_key:
        keyboard.release(currently_held_key)
        currently_held_key = None

def check_rare_popup():
    if rare_popup_template is None:
        return 0.0, (0, 0), (0, 0)
        
    if BATTLE_REGION is not None:
        screenshot = pyautogui.screenshot(region=BATTLE_REGION)
    else:
        screenshot = pyautogui.screenshot()
        
    frame = np.array(screenshot)
    target_img = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    
    th, tw = rare_popup_template.shape[:2]
    ih, iw = target_img.shape[:2]
    if th > ih or tw > iw:
        return 0.0, (0, 0), (0, 0)
        
    result = cv2.matchTemplate(target_img, rare_popup_template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    
    return max_val * 100, max_loc, (tw, th)

def get_highest_similarity():
    if BATTLE_REGION is not None:
        screenshot = pyautogui.screenshot(region=BATTLE_REGION)
    else:
        screenshot = pyautogui.screenshot()
        
    frame = np.array(screenshot)
    target_img = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    
    ih, iw = target_img.shape[:2]
    max_sim_found = 0.0
    best_match_name = None
    best_match_loc = (0, 0)
    best_template_size = (0, 0)

    for name, template in target_templates:
        th, tw = template.shape[:2]
        if th > ih or tw > iw:
            continue
            
        result = cv2.matchTemplate(target_img, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        similarity_percent = max_val * 100
        
        if similarity_percent > max_sim_found:
            max_sim_found = similarity_percent
            best_match_name = name
            best_match_loc = max_loc
            best_template_size = (tw, th)
            
    return max_sim_found, best_match_name, best_match_loc, best_template_size

def execute_kill():
    print("Executing Kill Sequence (1 -> 1)...")
    keyboard.send('1') 
    human_sleep(0.10, 0.03)
    keyboard.send('1')
    print("Waiting for turn animation...")
    time.sleep(1.0)

def play_alarm():
    print("\n>>> ALARM: RARE POKEMON DETECTED! <<<")
    while not keyboard.is_pressed('q'):
        winsound.Beep(1500, 400)
        time.sleep(0.1)

def pick_new_destination():
    global target_pos
    target_pos = random.uniform(BOUND_LEFT, BOUND_RIGHT)

def update_movement_hold():
    global current_pos, last_tick_time, currently_held_key
    
    now = time.time()
    delta_time = now - last_tick_time
    last_tick_time = now
    
    if currently_held_key:
        blocks_moved = delta_time / SECONDS_PER_BLOCK
        current_pos += blocks_moved if currently_held_key == 'd' else -blocks_moved
        current_pos = max(BOUND_LEFT, min(BOUND_RIGHT, current_pos))
        
    distance = target_pos - current_pos
    
    if abs(distance) < 0.2: 
        release_movement()
        return True 
        
    direction = 'd' if distance > 0 else 'a'
    
    if currently_held_key != direction:
        release_movement() 
        keyboard.press(direction)
        currently_held_key = direction
        
    return False 

# ==========================================
# MAIN LOOP
# ==========================================
if __name__ == "__main__":
    print("=======================================")
    print(" Auto Grinder Starting...")
    print(" Hold 'Q' to exit at any time.")
    print("=======================================")
    load_templates()
    print("Turn on your game. Waiting 3 seconds...")
    time.sleep(3)
    pick_new_destination()
    
    last_tick_time = time.time()
    
    try:
        while not keyboard.is_pressed('q'):
            
            # 1. Read screen for rare popup
            rare_sim, rare_loc, rare_size = check_rare_popup()
            if rare_sim >= 75.0:
                release_movement()
                
                # Setup ROI if Rare encountered first
                if BATTLE_REGION is None:
                    tw, th = rare_size
                    start_x = rare_loc[0]
                    start_y = rare_loc[1]
                    
                    BATTLE_REGION = (int(start_x), int(start_y), tw, th)
                    print(f"\n[+] ROI Dynamically locked at: {BATTLE_REGION} (Size: {tw}x{th})")
                    
                    print("[+] Saving 'debug_roi_crop.png' to verify the exact crop...")
                    debug_screenshot = pyautogui.screenshot(region=BATTLE_REGION)
                    debug_frame = cv2.cvtColor(np.array(debug_screenshot), cv2.COLOR_RGB2BGR)
                    cv2.imwrite("debug_roi_crop.png", debug_frame)
                    
                print("\n" + "="*45)
                print(f"🚨 RARE POKEMON DETECTED! ({rare_sim:.1f}%) 🚨")
                print("="*45)
                play_alarm()
                break 
            
            # 2. Read screen for normal targets
            highest_sim, match_name, match_loc, match_size = get_highest_similarity()
            
            roi_status = "FULL SCREEN" if BATTLE_REGION is None else "ROI ACTIVE"
            print(f"[{roi_status}] Live Sim: {highest_sim:.1f}% | Popup Sim: {rare_sim:.1f}%      ", end='\r')
            
            if highest_sim < 30.0:
                arrived = update_movement_hold()
                if arrived:
                    time.sleep(max(0.05, random.gauss(0.2, 0.05)))
                    pick_new_destination()
                    last_tick_time = time.time() 
                    
            else: 
                release_movement()
                
                # Setup ROI if Normal target encountered first
                if BATTLE_REGION is None:
                    print("\n\n[+] First Pokemon Encountered! Defining Region of Interest (ROI)...")
                    
                    tw, th = match_size
                    start_x = match_loc[0]
                    start_y = match_loc[1]
                    
                    BATTLE_REGION = (int(start_x), int(start_y), tw, th)
                    print(f"[+] ROI Successfully Locked at: {BATTLE_REGION} (Size: {tw}x{th})")
                    
                    print("[+] Saving 'debug_roi_crop.png' to verify the exact crop...")
                    debug_screenshot = pyautogui.screenshot(region=BATTLE_REGION)
                    debug_frame = cv2.cvtColor(np.array(debug_screenshot), cv2.COLOR_RGB2BGR)
                    cv2.imwrite("debug_roi_crop.png", debug_frame)
                
                print("\n✅ MATCHED: {} ({:.1f}%)".format(match_name, highest_sim))
                execute_kill()
                last_tick_time = time.time() 
                
    finally:
        release_movement()
        keyboard.release('a')
        keyboard.release('d')
        print(f"\nBot shut down cleanly.")