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

## 🔧 Installation

### Requirements
```bash
pip install opencv-python
pip install numpy
pip install Pillow
pip install pytesseract  # Optional, for text detection
```

### Setup
1. Clone or download the project
2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the application:
```bash
python main.py
```

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