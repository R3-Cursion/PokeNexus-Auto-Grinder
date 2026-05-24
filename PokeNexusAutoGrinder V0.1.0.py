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
BATTLE_REGION = (450, 150, 1000, 700) 

# ==========================================
# INTERNAL STATE
# ==========================================
current_pos = 0.0
target_pos = 0.0
target_templates = []

# Variables to track continuous holding
currently_held_key = None
last_tick_time = 0.0

def load_templates():
    print("Loading vision templates...")
    for photo_name in TARGET_IMAGES:
        img = cv2.imread(photo_name)
        if img is not None:
            target_templates.append((photo_name, img))
            print(f"✅ Loaded Target: {photo_name}")
    if not target_templates:
        print("❌ CRITICAL ERROR: No targets loaded.")
        exit()

def human_sleep(base, variance):
    time.sleep(max(0.01, random.gauss(base, variance)))

def release_movement():
    """Instantly lets go of whatever movement key is currently being held."""
    global currently_held_key
    if currently_held_key:
        keyboard.release(currently_held_key)
        currently_held_key = None

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
    # .send() fires a clean, instant keystroke without manual holds
    keyboard.send('1') 
    
    # Wait for the menu to slide up and load the moves.
    # If the second '1' is failing, INCREASE THIS NUMBER to 1.5 or 2.0
    time.sleep(0.1) 
    
    # --- SECOND PRESS: Select the first attack ---
    keyboard.send('1')
    
    print("Waiting for turn animation...")
    time.sleep(1.0)

def play_alarm():
    print("\n>>> UNKNOWN/RARE POKEMON DETECTED! <<<")
    print("Bot paused. Catch it, then press 'ENTER' here to resume.")
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
    
    # 1. Update map math based on how long the key was held since last check
    if currently_held_key:
        blocks_moved = delta_time / SECONDS_PER_BLOCK
        current_pos += blocks_moved if currently_held_key == 'd' else -blocks_moved
        current_pos = max(BOUND_LEFT, min(BOUND_RIGHT, current_pos))
        
    distance = target_pos - current_pos
    
    # 2. Check if we arrived
    if abs(distance) < 0.2: 
        release_movement()
        return True # Destination Reached
        
    # 3. Figure out which way to go
    direction = 'd' if distance > 0 else 'a'
    
    # 4. Press the key down and leave it down if we aren't already holding it
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
    print(" Smooth Hold Bot Starting...")
    print(" Hold 'Q' to exit at any time.")
    print("=======================================")
    load_templates()
    print("Turn on your game.")
    time.sleep(3)
    pick_new_destination()
    
    # Start the clock just before entering the loop (Syntax error fixed here)
    last_tick_time = time.time()
    
    try:
        while not keyboard.is_pressed('q'):
            
            # 1. READ SCREEN
            highest_sim, match_name = get_highest_similarity()
            
            # --- NEW FEATURE: Print live similarity tracker ---
            # Using end='\r' overwrites the same line to prevent spam
            print(f"Live Similarity: {highest_sim:.1f}%          ", end='\r')
            
            # 2. APPLY SIMPLE THRESHOLD LOGIC
            if highest_sim < 30.0:
                # No Pokemon. Keep holding the key and updating math.
                arrived = update_movement_hold()
                if arrived:
                    time.sleep(max(0.05, random.gauss(0.2, 0.05)))
                    pick_new_destination()
                    # Reset clock so the sleep time isn't counted as walking
                    last_tick_time = time.time() 
                    
            else: #highest_sim >= 80.0:
                # Target matched! STOP WALKING INSTANTLY.
                release_movement()
                # Print a blank line first to clear out the live tracker
                print("\n✅ MATCHED: {} ({:.1f}%)".format(match_name, highest_sim))
                execute_kill()
                # Reset the clock after the battle
                last_tick_time = time.time() 
                
            #/else:
                # Similarity is between 70 and 85 (Unknown/Rare Pokemon)
                #/release_movement() # STOP WALKING INSTANTLY.
                #/print(f"\n❌ UNKNOWN POKEMON ({highest_sim:.1f}%)")
                #/play_alarm()
                # Reset the clock after the alarm pause
                #/last_tick_time = time.time() 
                
    finally:
        # Failsafe: drop all keys if you crash or close the script
        release_movement()
        keyboard.release('a')
        keyboard.release('d')
        print(f"\nBot shut down cleanly. Final map coordinate: {current_pos:.1f}")
        