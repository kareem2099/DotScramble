# 🚀 Advanced Image Privacy Studio Pro

A powerful, modular image privacy protection tool with advanced features including face detection, multiple effect types, batch processing, and real-time preview.

## 📁 Project Structure

```
privacy_studio_pro/
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
```

## ✨ Features

### Core Features
- **Multiple Detection Modes**
  - 🎭 Face Detection
  - 👁️ Eye Detection
  - 🧍 Full Body Detection
  - 🚗 License Plate Detection
  - 📝 Text Detection (OCR)
  - ✏️ Manual Selection
  - 🌍 Full Image

### Effects
- 🌫️ **Gaussian Blur** - Smooth blur effect
- 🔲 **Pixelation** - Classic pixel censoring
- ⬛ **Black Bar** - Solid black censoring
- 🎭 **Gradient Fade** - Artistic gradient effect
- 🔳 **Mosaic** - Mosaic tile effect
- ❄️ **Frosted Glass** - Glass-like blur
- 🎨 **Oil Paint** - Artistic painting effect

### Advanced Features
- ⚡ **Real-time Preview** - See effects instantly
- 📦 **Batch Processing** - Process multiple images
- ↶↷ **Undo/Redo** - Full history management
- 💾 **Presets** - Save and load effect settings
- 🔍 **Comparison View** - Compare before/after
- ⌨️ **Keyboard Shortcuts** - Fast workflow
- 🎨 **Opacity Control** - Blend effects
- 📊 **Image Info** - Display image details

## 🚀 Getting Started - Step by Step Installation

### 📋 Prerequisites

**Required:**
- **Python 3.8 or higher** (Python 3.9+ recommended)
- **4GB RAM minimum** (8GB recommended for large images)
- **Operating System:** Windows 10+, macOS 10.14+, Ubuntu 18.04+ or similar Linux

**Optional (for text detection):**
- Tesseract OCR engine

---

### 🪟 Windows Installation

#### Step 1: Install Python
1. Download Python from [python.org](https://python.org/downloads/)
2. Run the installer
3. **IMPORTANT:** Check "Add Python to PATH" during installation
4. Verify installation: Open Command Prompt and run `python --version`

#### Step 2: Download the Project
1. Visit the [GitHub repository](https://github.com/kareem2099/DotScramble)
2. Click the green **"Code"** button
3. Select **"Download ZIP"**
4. Extract the ZIP file to your desired location

#### Step 3: Install Dependencies
1. Open Command Prompt as Administrator
2. Navigate to the project folder:
```cmd
cd path\to\DotScramble
```
3. Install required packages:
```cmd
pip install -r requirements.txt
```

#### Step 4: Optional - Install Tesseract OCR (for text detection)
1. Download Tesseract from [GitHub releases](https://github.com/UB-Mannheim/tesseract/wiki)
2. Install the executable
3. Add Tesseract to your system PATH

#### Step 5: Run the Application
```cmd
python main.py
```

---

### 🍎 macOS Installation

#### Step 1: Install Python
1. Install Homebrew (if not already installed):
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```
2. Install Python:
```bash
brew install python
```
3. Verify: `python3 --version`

#### Step 2: Download the Project
1. Clone the repository:
```bash
git clone https://github.com/kareem2099/DotScramble.git
cd DotScramble
```
Or download ZIP from GitHub and extract.

#### Step 3: Install Dependencies
```bash
pip3 install -r requirements.txt
```

#### Step 4: Optional - Install Tesseract OCR
```bash
brew install tesseract
```

#### Step 5: Run the Application
```bash
python3 main.py
```

---

### 🐧 Linux Installation (Ubuntu/Debian)

#### Step 1: Install Python
```bash
# Update package list
sudo apt update

# Install Python and pip
sudo apt install python3 python3-pip python3-venv
```

#### Step 2: Download the Project
```bash
# Clone repository
git clone https://github.com/kareem2099/DotScramble.git
cd DotScramble
```

#### Step 3: Install Dependencies
```bash
pip3 install -r requirements.txt
```

#### Step 4: Optional - Install Tesseract OCR
```bash
sudo apt install tesseract-ocr tesseract-ocr-eng
```

#### Step 5: Run the Application
```bash
python3 main.py
```

---

### 🔧 Manual Installation (Advanced Users)

If you prefer to install dependencies individually:

#### Core Dependencies
```bash
pip install opencv-python>=4.8.0
pip install numpy>=1.24.0
pip install Pillow>=10.0.0
```

#### Optional Dependencies
```bash
# For text detection
pip install pytesseract>=0.3.10

# For advanced image processing (optional)
pip install scipy>=1.11.0
pip install scikit-image>=0.21.0
```

---

### ✅ Verification

After installation, test that everything works:

1. Run the application: `python main.py`
2. Load an image using the "📁 Load Image" button
3. Try different detection modes and effects
4. Save a processed image

---

### 🏗️ Building Standalone Executables (Optional)

For users who want to create executable files without requiring Python installation:

#### Using the Build Script
```bash
# Install PyInstaller (if not already installed)
pip install pyinstaller

# Run the local build (without obfuscation)
python build_local.py

# Or run the full build (with obfuscation)
python build.py
```

The executable will be created in the `release/` folder.

**Note:** Building executables requires additional dependencies like PyArmor for the full build.

---

### 🐛 Troubleshooting Installation

#### "python command not found"
- **Windows:** Reinstall Python and check "Add to PATH"
- **macOS/Linux:** Use `python3` instead of `python`

#### Import errors after installation
```bash
# Try reinstalling in a virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
```

#### Tesseract not found
- Ensure Tesseract is installed and in your PATH
- On Windows, you may need to restart your command prompt
- Check installation: `tesseract --version`

#### Permission errors
- Run commands as administrator/sudo when installing system packages
- Ensure you have write permissions in the project directory

#### Slow installation
- Use a faster internet connection
- Consider using `pip install --upgrade pip` first
- Some packages (like OpenCV) are large and may take time

---

### 🎯 Quick Start After Installation

1. **First Run:** Double-click the executable or run `python main.py`
2. **Load Image:** Click "📁 Load Image" button
3. **Choose Detection:** Select "🎭 Face" detection mode
4. **Pick Effect:** Choose "🌫️ Blur" effect
5. **Apply:** Click "✨ Apply Effect"
6. **Save:** Click "💾 Save Result"

**Tip:** Enable "🔴 Real-time Preview" for instant feedback when adjusting settings!

## 📖 Usage Guide

### Basic Workflow
1. **Load Image** - Click "📁 Load Image" or press `Ctrl+O`
2. **Select Detection Mode** - Choose how to detect regions
3. **Choose Effect** - Select your privacy effect
4. **Adjust Parameters** - Fine-tune strength, size, opacity
5. **Apply Effect** - Click "✨ Apply Effect" or press `Ctrl+P`
6. **Save Result** - Click "💾 Save Result" or press `Ctrl+S`

### Manual Selection
1. Select "✏️ Manual Selection" mode
2. Click and drag on the image to draw rectangles
3. Draw multiple regions as needed
4. Click "✨ Apply Effect" to process all regions
5. Use "🗑️ Clear Selections" to start over

### Real-time Preview
- Enable "🔴 Real-time Preview" checkbox
- Adjust any parameter to see instant results
- Great for finding the perfect settings

### Batch Processing
1. Click "📦 Batch Process" or press `Ctrl+B`
2. Select multiple images
3. Choose output folder
4. Configure settings
5. Start processing

### Presets
1. Configure your desired settings
2. Menu → Presets → Save Current Settings
3. Load saved presets anytime for consistent results

## ⌨️ Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+O` | Open Image |
| `Ctrl+S` | Save Result |
| `Ctrl+Z` | Undo |
| `Ctrl+Y` | Redo |
| `Ctrl+P` | Apply Effect |
| `Ctrl+D` | Clear Selections |
| `Ctrl+B` | Batch Process |

## 🎨 Effect Parameters

### Blur Strength
- Range: 15-199
- Higher = more blur
- Use odd numbers for best results

### Pixel Block Size
- Range: 5-50
- Higher = more censored
- Lower = more detail retained

### Opacity
- Range: 0-100%
- 100% = full effect
- Lower = blend with original

## 🔍 Detection Tips

### Face Detection
- Works best with front-facing faces
- Good lighting improves detection
- May miss faces at extreme angles

### License Plate
- Works with standard license plate sizes
- Best with high-resolution images
- Filters by aspect ratio (2:1 to 5:1)

### Text Detection
- Requires pytesseract installation
- Works best with clear, high-contrast text
- Adjust confidence threshold if needed

## 🛠️ Customization

### Adding New Effects
1. Open `image_processor.py`
2. Add method to `ImageProcessor` class:
```python
@staticmethod
def my_effect(image, x, y, w, h):
    region = image[y:y+h, x:x+w]
    # Your effect logic here
    return processed_region
```

3. Update `config.py` EFFECTS dictionary
4. Add to GUI effect selection

### Custom Presets
Edit `config.py` EFFECT_PRESETS:
```python
EFFECT_PRESETS = {
    'My Custom Preset': {
        'effect': 'blur',
        'blur_strength': 75,
        'opacity': 85
    }
}
```

## 📝 Code Organization

### config.py
- UI colors and styling
- Effect parameters and ranges
- Detection mode definitions
- File format support
- Keyboard shortcuts

### image_processor.py
- `ImageProcessor`: Effect implementations
- `DetectionEngine`: Detection algorithms
- All image manipulation functions

### batch_processor.py
- `BatchProcessor`: Batch operations
- Multi-threading support
- Progress tracking

### utils.py
- `HistoryManager`: Undo/redo
- `PresetManager`: Preset storage
- `ImageUtils`: Helper functions
- `ExportManager`: Save operations

### main_window.py
- `AdvancedPrivacyStudioPro`: Main GUI
- Event handlers
- UI components
- Integration logic

## 🐛 Troubleshooting

### Image won't load
- Check file format (JPG, PNG, BMP supported)
- Verify file isn't corrupted
- Check file permissions

### Detection not working
- Ensure OpenCV is properly installed
- Check image quality and lighting
- Try adjusting detection parameters

### Slow performance
- Reduce image size before processing
- Lower effect strength values
- Disable real-time preview
- Close other applications

### Text detection fails
- Install Tesseract OCR
- Check pytesseract PATH configuration
- Use high-resolution images

## 🚀 Performance Tips

1. **Batch Processing**: Process multiple images at once
2. **Lower Resolution**: Resize large images first
3. **Disable Preview**: Turn off real-time preview for complex operations
4. **Optimal Settings**: Use moderate effect strengths
5. **Close Unused Apps**: Free up system resources

## 📄 License

This project is provided as-is for educational and personal use.

## 🤝 Contributing

Feel free to fork, modify, and enhance! Some ideas:
- Additional detection algorithms
- More effect types
- Video processing support
- GPU acceleration
- Cloud processing integration
- Mobile app version

## 📞 Support

For issues or questions:
- Check the troubleshooting section
- Review the code comments
- Experiment with different settings

---

**Made with ❤️ for privacy protection**
