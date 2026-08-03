#include <Arduino.h>
#include <U8g2lib.h>
#include <Wire.h>

// Initialize the 1.3" OLED. 
// NOTE: Most 1.3" OLEDs use the SH1106 controller. If your display looks 
// garbled or has a line of static on the edge, change "SH1106" to "SSD1306".
U8G2_SH1106_128X64_NONAME_1_HW_I2C u8g2(U8G2_R0, /* reset=*/ U8X8_PIN_NONE);

// Set up the terminal bounds
const int MAX_LINES = 6;
String consoleLines[MAX_LINES];

void setup() {
  // 1. Start Serial to listen to Python (MUST be 9600 to match)
  Serial.begin(9600);
  
  // 2. Start the OLED
  u8g2.begin();
  
  // 3. Set a clean, monospace terminal font 
  // (6x10 allows exactly 21 characters per line and 6 lines vertically)
  u8g2.setFont(u8g2_font_6x10_tf); 
  
  // 4. Fill the array with blank strings to prevent garbage data
  for (int i = 0; i < MAX_LINES; i++) {
    consoleLines[i] = "";
  }
  
  // 5. Show boot message
  consoleLines[5] = "Waiting for PC...";
  updateScreen();
}

void loop() {
  // Check if Python has sent new text over the USB cable
  if (Serial.available() > 0) {
    
    // Read the text until the newline character
    String incomingText = Serial.readStringUntil('\n');
    
    // Clean up any hidden whitespace or Windows carriage returns (\r)
    incomingText.trim(); 

    // Only update if Python actually sent text (ignores empty blank lines)
    if (incomingText.length() > 0) {
      
      // Auto-Scroll Math: Shift all old lines UP by one position
      for (int i = 0; i < MAX_LINES - 1; i++) {
        consoleLines[i] = consoleLines[i + 1];
      }
      
      // Insert the brand new text at the very bottom of the list
      consoleLines[MAX_LINES - 1] = incomingText;
      
      // Draw the new state to the OLED
      updateScreen();
    }
  }
}

void updateScreen() {
  // Using Page Buffer mode (_1_) to protect Arduino RAM
  u8g2.firstPage();
  do {
    // Loop through our array and draw all 6 lines
    for (int i = 0; i < MAX_LINES; i++) {
      
      // Y-coordinate math: line 0 is at y=10, line 1 is at y=20, etc.
      int y_pos = (i + 1) * 10; 
      
      u8g2.setCursor(0, y_pos);
      u8g2.print(consoleLines[i]);
    }
  } while (u8g2.nextPage());
}