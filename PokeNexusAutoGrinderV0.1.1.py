import cv2
import numpy as np
import pyautogui
import time
import random
import keyboard
import winsound

# ==========================================
# CONFIGURATION
# ==========================================
# 1. MOVEMENT SETTINGS
SECONDS_PER_BLOCK = 1.0 / 7.0 
BOUND_LEFT = -9.0
BOUND_RIGHT = 9.0

# 2. VISION SETTINGS
TARGET_IMAGES = ['target_1.png', 'target_2.png', 'target_3.png']
RARE_POPUP_IMAGE = 'base_image_rare_pokemon.png' # <-- Your new failsafe image
BATTLE_REGION = (450, 150, 1000, 700) 

# ==========================================
# INTERNAL STATE
# ==========================================
current_pos = 0.0
target_pos = 0.0
target_templates = []
rare_popup_template = None # Track the new popup image

# Variables to track continuous holding
currently_held_key = None
last_tick_time = 0.0

def load_templates():
    global rare_popup_template
    print("Loading vision templates...")
    for photo_name in TARGET_IMAGES:
        img = cv2.imread(photo_name)
        if img is not None:
            target_templates.append((photo_name, img))
            print(f"✅ Loaded Target: {photo_name}")
            
    if not target_templates:
        print("❌ CRITICAL ERROR: No targets loaded.")
        exit()
        
    # Load the Rare Popup Template
    rare_popup_template = cv2.imread(RARE_POPUP_IMAGE)
    if rare_popup_template is not None:
        print(f"✅ Loaded Failsafe: {RARE_POPUP_IMAGE}")
    else:
        print(f"⚠️ WARNING: Could not load '{RARE_POPUP_IMAGE}'. Rare check disabled.")

def human_sleep(base, variance):
    time.sleep(max(0.01, random.gauss(base, variance)))

def release_movement():
    """Instantly lets go of whatever movement key is currently being held."""
    global currently_held_key
    if currently_held_key:
        keyboard.release(currently_held_key)
        currently_held_key = None

def check_rare_popup():
    """Checks the screen specifically for the rare popup."""
    if rare_popup_template is None:
        return 0.0
        
    screenshot = pyautogui.screenshot(region=BATTLE_REGION)
    frame = np.array(screenshot)
    target_img = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    
    th, tw = rare_popup_template.shape[:2]
    ih, iw = target_img.shape[:2]
    if th > ih or tw > iw:
        return 0.0
        
    result = cv2.matchTemplate(target_img, rare_popup_template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, _ = cv2.minMaxLoc(result)
    return max_val * 100

def get_highest_similarity():
    """Scans the screen and returns the highest match percentage found."""
    screenshot = pyautogui.screenshot(region=BATTLE_REGION)
    frame = np.array(screenshot)
    target_img = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    
    ih, iw = target_img.shape[:2]
    max_sim_found = 0.0
    best_match_name = None

    for name, template in target_templates:
        th, tw = template.shape[:2]
        if th > ih or tw > iw:
            continue
            
        result = cv2.matchTemplate(target_img, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(result)
        similarity_percent = max_val * 100
        
        if similarity_percent > max_sim_found:
            max_sim_found = similarity_percent
            best_match_name = name
            
    return max_sim_found, best_match_name

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
    print(" Auto Grinder with Rare Failsafe Starting...")
    print(" Hold 'Q' to exit at any time.")
    print("=======================================")
    load_templates()
    print("Turn on your game.")
    time.sleep(3)
    pick_new_destination()
    
    last_tick_time = time.time()
    
    try:
        while not keyboard.is_pressed('q'):
            
            # --- NEW FEATURE: CHECK RARE POPUP FIRST ---
            rare_sim = check_rare_popup()
            if rare_sim >= 75.0:
                release_movement()
                print("\n" + "="*45)
                print(f"🚨 RARE POKEMON DETECTED! ({rare_sim:.1f}%) 🚨")
                print("="*45)
                play_alarm()
                break # <-- Completely stops the code so you don't kill it
            
            # 1. READ SCREEN (For Normal Targets)
            highest_sim, match_name = get_highest_similarity()
            
            # Print live similarity tracker
            print(f"Live Target Sim: {highest_sim:.1f}% | Popup Sim: {rare_sim:.1f}%      ", end='\r')
            
            # 2. APPLY SIMPLE THRESHOLD LOGIC
            if highest_sim < 30.0:
                # No Pokemon. Keep holding the key and updating math.
                arrived = update_movement_hold()
                if arrived:
                    time.sleep(max(0.05, random.gauss(0.2, 0.05)))
                    pick_new_destination()
                    last_tick_time = time.time() 
                    
            else: #highest_sim >= 80.0:
                # Target matched! STOP WALKING INSTANTLY.
                release_movement()
                print("\n✅ MATCHED: {} ({:.1f}%)".format(match_name, highest_sim))
                execute_kill()
                last_tick_time = time.time() 
                
    finally:
        # Failsafe: drop all keys if you crash or close the script
        release_movement()
        keyboard.release('a')
        keyboard.release('d')
        print(f"\nBot shut down cleanly.")