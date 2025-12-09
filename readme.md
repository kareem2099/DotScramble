Here is the updated README.md. I have added a new "📥 Download & Run" section at the very top (before the technical installation).

I also updated the links to point to your specific repository (kareem2099/DotScramble) and added specific instructions for Linux/macOS permissions based on the executables we just built.

Markdown

# 🚀 Advanced Image Privacy Studio Pro (DotScramble)

A powerful, modular image privacy protection tool with advanced features including face detection, multiple effect types, batch processing, and real-time preview.

## 📥 Download & Run (Recommended)

**No Python installation required!** You can download the standalone executable for your system.

1. Go to the **[Latest Releases Page](https://github.com/kareem2099/DotScramble/releases/latest)**.
2. Download the file for your operating system:

### 🪟 Windows
1. Download `DotScramble-windows.exe`.
2. Double-click to launch.
> **Note:** If Windows SmartScreen appears ("Windows protected your PC"), click **"More info"** and then **"Run anyway"**.

### 🐧 Linux
1. Download `DotScramble-linux`.
2. Open your terminal in the downloads folder.
3. Give it permission to run:
   ```bash
   chmod +x DotScramble-linux
Run the app:

Bash

./DotScramble-linux
🍎 macOS
Download DotScramble-macos.

Open your terminal.

Give it permission to run:

Bash

chmod +x DotScramble-macos
Important: To bypass the "Unidentified Developer" warning, Right-click the file in Finder and select Open, then confirm.

📁 Project Structure
DotScramble/
│
├── main.py                    # Application entry point
├── config.py                  # Configuration settings
│
├── core/
│   ├── image_processor.py     # Image processing effects
│   ├── batch_processor.py     # Batch processing functionality
│   └── utils.py               # Utility functions
│
├── gui/
│   ├── main_window.py         # Main GUI window (Part 1 & 2)
│   └── batch_window.py        # Batch processing window
│
├── presets.json              # Saved effect presets (auto-generated)
├── backups/                  # Image backups (auto-created)
└── requirements.txt          # Python dependencies
✨ Features
Core Features
Multiple Detection Modes

🎭 Face Detection

👁️ Eye Detection

🧍 Full Body Detection

🚗 License Plate Detection

📝 Text Detection (OCR)

✏️ Manual Selection

🌍 Full Image

Effects
🌫️ Gaussian Blur - Smooth blur effect

🔲 Pixelation - Classic pixel censoring

⬛ Black Bar - Solid black censoring

🎭 Gradient Fade - Artistic gradient effect

🔳 Mosaic - Mosaic tile effect

❄️ Frosted Glass - Glass-like blur

🎨 Oil Paint - Artistic painting effect

Advanced Features
⚡ Real-time Preview - See effects instantly

📦 Batch Processing - Process multiple images

↶↷ Undo/Redo - Full history management

💾 Presets - Save and load effect settings

🔍 Comparison View - Compare before/after

⌨️ Keyboard Shortcuts - Fast workflow

🎨 Opacity Control - Blend effects

📊 Image Info - Display image details

🔧 Development Setup (Source Code)
If you want to run the code manually or contribute:

Requirements
Bash

pip install opencv-python
pip install numpy
pip install Pillow
pip install pytesseract  # Optional, for text detection
Setup
Clone the repository:

Bash

git clone [https://github.com/kareem2099/DotScramble.git](https://github.com/kareem2099/DotScramble.git)
Install dependencies:

Bash

pip install -r requirements.txt
Run the application:

Bash

python main.py
📖 Usage Guide
Basic Workflow
Load Image - Click "📁 Load Image" or press Ctrl+O

Select Detection Mode - Choose how to detect regions

Choose Effect - Select your privacy effect

Adjust Parameters - Fine-tune strength, size, opacity

Apply Effect - Click "✨ Apply Effect" or press Ctrl+P

Save Result - Click "💾 Save Result" or press Ctrl+S

Manual Selection
Select "✏️ Manual Selection" mode

Click and drag on the image to draw rectangles

Draw multiple regions as needed

Click "✨ Apply Effect" to process all regions

Use "🗑️ Clear Selections" to start over

Real-time Preview
Enable "🔴 Real-time Preview" checkbox

Adjust any parameter to see instant results

Great for finding the perfect settings

Batch Processing
Click "📦 Batch Process" or press Ctrl+B

Select multiple images

Choose output folder

Configure settings

Start processing

Presets
Configure your desired settings

Menu → Presets → Save Current Settings

Load saved presets anytime for consistent results

⌨️ Keyboard Shortcuts
Shortcut	Action
Ctrl+O	Open Image
Ctrl+S	Save Result
Ctrl+Z	Undo
Ctrl+Y	Redo
Ctrl+P	Apply Effect
Ctrl+D	Clear Selections
Ctrl+B	Batch Process

Export to Sheets

🎨 Effect Parameters
Blur Strength
Range: 15-199

Higher = more blur

Use odd numbers for best results

Pixel Block Size
Range: 5-50

Higher = more censored

Lower = more detail retained

Opacity
Range: 0-100%

100% = full effect

Lower = blend with original

🔍 Detection Tips
Face Detection
Works best with front-facing faces

Good lighting improves detection

May miss faces at extreme angles

License Plate
Works with standard license plate sizes

Best with high-resolution images

Filters by aspect ratio (2:1 to 5:1)

Text Detection
Requires pytesseract installation

Works best with clear, high-contrast text

Adjust confidence threshold if needed

🛠️ Customization
Adding New Effects
Open core/image_processor.py

Add method to ImageProcessor class:

Python

@staticmethod
def my_effect(image, x, y, w, h):
    region = image[y:y+h, x:x+w]
    # Your effect logic here
    return processed_region
Update config.py EFFECTS dictionary

Add to GUI effect selection

📝 Code Organization
config.py: UI colors, effect parameters, settings.

core/: Contains logic for effects, batch processing, and utilities.

gui/: Contains the PyQT/Tkinter window logic.

📄 License
This project is provided as-is for educational and personal use.

🤝 Contributing
Feel free to fork, modify, and enhance! Some ideas:

Additional detection algorithms

More effect types

Video processing support

GPU acceleration

📞 Support
For issues or questions:

Check the troubleshooting section

Review the code comments

Experiment with different settings

Made with ❤️ for privacy protection
