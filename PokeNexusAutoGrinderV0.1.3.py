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
REFERENCE_FRAME_IMAGE = 'reference_frame.png'

# 3. DEBUG FOLDER SETTINGS
DEBUG_FOLDER = 'debug'

# 4. DYNAMIC ROI TRACKERS
MASTER_ROI = None 
BATTLE_ROI = None 

# ==========================================
# INTERNAL STATE
# ==========================================
current_pos = 0.0
target_pos = 0.0
target_templates = []
rare_popup_template = None 
reference_template = None 

currently_held_key = None
last_tick_time = 0.0

def setup_debug_folder():
    """Ensures the debug folder exists on disk."""
    if not os.path.exists(DEBUG_FOLDER):
        os.makedirs(DEBUG_FOLDER)
        print(f"📁 Created folder: '{DEBUG_FOLDER}'")

def load_templates():
    global rare_popup_template, reference_template
    print("Loading vision templates...")
    
    # Load Common Targets
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
        
    # Load Rare Failsafe
    if os.path.exists(RARE_POPUP_IMAGE):
        rare_popup_template = cv2.imread(RARE_POPUP_IMAGE)
        if rare_popup_template is not None:
            print(f"✅ Loaded Failsafe: {RARE_POPUP_IMAGE}")
    else:
        print(f"⚠️ WARNING: Could not load '{RARE_POPUP_IMAGE}'. Rare check disabled.")
        
    # Load Reference Frame
    if os.path.exists(REFERENCE_FRAME_IMAGE):
        reference_template = cv2.imread(REFERENCE_FRAME_IMAGE)
        if reference_template is not None:
            print(f"✅ Loaded Reference Frame: {REFERENCE_FRAME_IMAGE}")
    else:
        print(f"❌ CRITICAL ERROR: Could not load '{REFERENCE_FRAME_IMAGE}'.")
        exit()

def human_sleep(base, variance):
    time.sleep(max(0.01, random.gauss(base, variance)))

def release_movement():
    """Instantly lets go of whatever movement key is currently being held."""
    global currently_held_key
    if currently_held_key:
        keyboard.release(currently_held_key)
        currently_held_key = None

def execute_kill():
    print("Executing Kill Sequence (1 -> 1)...")
    
    # --- FIRST PRESS: Select "Fight" ---
    keyboard.send('1') 
    human_sleep(0.10, 0.03)
    
    # --- SECOND PRESS: Select the first attack ---
    keyboard.send('1')
    
    print("Waiting for turn animation...")
    time.sleep(1.0)

def play_alarm():
    print("\n>>> ALARM: BOT PAUSED! <<<")
    print("Check the game, then press 'ENTER' here to acknowledge.")
    for _ in range(5):
        winsound.Beep(1500, 400)
        time.sleep(0.1)
    keyboard.wait('enter')

def pick_new_destination():
    global target_pos
    target_pos = random.uniform(BOUND_LEFT, BOUND_RIGHT)

def update_movement_hold():
    """Manages the continuous holding of the key and updates the map math."""
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
        return True # Destination Reached
        
    direction = 'd' if distance > 0 else 'a'
    
    if currently_held_key != direction:
        release_movement() # Let go of the old key first
        keyboard.press(direction)
        currently_held_key = direction
        
    return False # Still walking

# ==========================================
# MAIN LOOP
# ==========================================
if __name__ == "__main__":
    print("=======================================")
    print(" Auto Grinder V2.2 (Debug Enabled)")
    print(" Hold 'Q' to exit at any time.")
    print("=======================================")
    setup_debug_folder()
    load_templates()
    print("Turn on your game. Waiting 3 seconds...")
    time.sleep(3)
    pick_new_destination()
    
    last_tick_time = time.time()
    
    try:
        while not keyboard.is_pressed('q'):
            
            # ========================================================
            # PHASE 1: HUNTING (LOOKING FOR MASTER ROI)
            # ========================================================
            if MASTER_ROI is None:
                # Take a full-screen screenshot to find the UI
                screenshot = pyautogui.screenshot()
                full_screen_frame = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
                result = cv2.matchTemplate(full_screen_frame, reference_template, cv2.TM_CCOEFF_NORMED)
                _, ref_max_val, _, ref_max_loc = cv2.minMaxLoc(result)
                
                ref_sim = ref_max_val * 100
                print(f"[HUNTING] UI Match: {ref_sim:.1f}%        ", end='\r')
                
                if ref_sim >= 70.0:
                    release_movement()
                    
                    # 1. Calculate and lock the MASTER ROI (Full Frame)
                    th, tw = reference_template.shape[:2]
                    base_x, base_y = int(ref_max_loc[0]), int(ref_max_loc[1])
                    MASTER_ROI = (base_x, base_y, int(tw), int(th))
                    
                    # 2. Calculate and lock the BATTLE ROI (Top-Right Quadrant Coordinates on Screen)
                    BATTLE_ROI = (base_x + (tw // 2), base_y, tw // 2, th // 2)
                    
                    print(f"\n\n[+] Encounter Triggered!")
                    print(f"    -> Master ROI: {MASTER_ROI}")
                    print(f"    -> Battle ROI: {BATTLE_ROI}")
                    
                    # Short delay to allow Pokémon sprites and rare text to finish loading
                    time.sleep(1.0)
                    continue 
                else:
                    # Still hunting, keep updating movement
                    arrived = update_movement_hold()
                    if arrived:
                        time.sleep(max(0.05, random.gauss(0.2, 0.05)))
                        pick_new_destination()
                        last_tick_time = time.time() 
                    continue

            # ========================================================
            # PHASE 2: BATTLE & DECISION MAKING
            # ========================================================
            else:
                # 1. Take SCREENSHOT #1 using the Master ROI coordinates
                screenshot_master = pyautogui.screenshot(region=MASTER_ROI)
                master_frame = cv2.cvtColor(np.array(screenshot_master), cv2.COLOR_RGB2BGR)
                
                # Save Master ROI debug image
                cv2.imwrite(os.path.join(DEBUG_FOLDER, "master_roi.png"), master_frame)
                
                # 2. CHECK MASTER ROI FOR RARE POPUP FIRST
                rare_sim = 0.0
                if rare_popup_template is not None:
                    res_rare = cv2.matchTemplate(master_frame, rare_popup_template, cv2.TM_CCOEFF_NORMED)
                    _, max_val_rare, _, _ = cv2.minMaxLoc(res_rare)
                    rare_sim = max_val_rare * 100
                    
                if rare_sim >= 75.0:
                    print("\n" + "="*45)
                    print(f"🚨 RARE POKEMON DETECTED! ({rare_sim:.1f}%) 🚨")
                    print("="*45)
                    cv2.imwrite(os.path.join(DEBUG_FOLDER, "rare_detected.png"), master_frame)
                    play_alarm()
                    break # Stops script completely so you don't kill it
                
                # 3. NO RARE POPUP -> Take SCREENSHOT #2 using Battle ROI coordinates
                screenshot_battle = pyautogui.screenshot(region=BATTLE_ROI)
                battle_frame = cv2.cvtColor(np.array(screenshot_battle), cv2.COLOR_RGB2BGR)
                
                # Save Battle ROI debug image
                cv2.imwrite(os.path.join(DEBUG_FOLDER, "battle_roi.png"), battle_frame)
                
                # 4. SCAN BATTLE ROI FOR COMMON TARGETS
                highest_sim = 0.0
                best_match_name = None
                
                for name, template in target_templates:
                    th, tw = template.shape[:2]
                    if th <= battle_frame.shape[0] and tw <= battle_frame.shape[1]:
                        res_target = cv2.matchTemplate(battle_frame, template, cv2.TM_CCOEFF_NORMED)
                        _, max_val_target, _, _ = cv2.minMaxLoc(res_target)
                        sim = max_val_target * 100
                        
                        if sim > highest_sim:
                            highest_sim = sim
                            best_match_name = name

                print(f"[FIGHTING] Target Sim: {highest_sim:.1f}% | Rare Sim: {rare_sim:.1f}%      ", end='\r')
                
                # 5. EXECUTE DECISION
                if highest_sim >= 30.0:
                    print("\n✅ MATCHED: {} ({:.1f}%)".format(best_match_name, highest_sim))
                    execute_kill()
                    
                    # Reset BOTH ROIs back to None so it returns to Phase 1 (Hunting)
                    #MASTER_ROI = None 
                    #BATTLE_ROI = None
                    last_tick_time = time.time() 
                    
    finally:
        # Failsafe: drop all keys if you crash or close the script
        release_movement()
        keyboard.release('a')
        keyboard.release('d')
        print(f"\nBot shut down cleanly.")