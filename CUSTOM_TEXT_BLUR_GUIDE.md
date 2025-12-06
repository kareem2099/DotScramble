# 📝 Custom Text Blurring - User Guide

## 🎯 Overview

The **Targeted Text** feature allows you to blur specific words or phrases in your images. This is perfect for:
- Censoring sensitive information (passwords, emails, names)
- Hiding specific text while keeping other text visible
- Redacting confidential data in documents
- Removing unwanted text from screenshots

---

## 🚀 Quick Start

### Step 1: Load Your Image
1. Click **📁 Load Image** or press `Ctrl+O`
2. Select an image containing text

### Step 2: Select "Targeted Text" Mode
1. In the **🎯 Detection Mode** section
2. Select **✍️ Targeted Text**
3. A text input field will appear below

### Step 3: Enter the Word to Blur
1. Type the word you want to blur in the text field
2. Example: Type "password" to blur all instances of "password"
3. The search is **case-insensitive** by default (finds "Password", "PASSWORD", "password")

### Step 4: Choose Your Effect
1. Select an effect from **🎨 Effect Type**:
   - 🌫️ **Blur** - Smooth blur (recommended)
   - 🔲 **Pixelation** - Pixel blocks
   - ⬛ **Black Bar** - Solid black censoring

### Step 5: Apply
1. Click **✨ Apply Effect** or press `Ctrl+P`
2. Wait for processing (OCR takes a few seconds)
3. The app will blur all instances of your target word

### Step 6: Save
1. Click **💾 Save Result** or press `Ctrl+S`
2. Choose save location and format

---

## 📖 Detailed Usage

### Text Input Options

**Partial Match (Default)**
- Type: `"pass"`
- Finds: "password", "passport", "bypass", etc.
- Use for: Catching variations of a word

**Exact Words**
- Type the complete word: `"confidential"`
- Finds: Only "confidential" (not "confidentially")

**Multiple Instances**
- The tool automatically finds ALL occurrences in the image
- No need to select each one manually

### Best Practices

✅ **DO:**
- Use high-quality images for better text detection
- Ensure text is clear and readable
- Use simple words without special characters
- Adjust blur strength for better coverage

❌ **DON'T:**
- Use very small text (< 12px) - harder to detect
- Use heavily compressed images
- Expect OCR to work on stylized/artistic fonts
- Use symbols or special characters

---

## 🔧 Advanced Settings

### OCR Confidence Threshold
The default confidence is **50%** (editable in `text_detector.py`)

```python
# In text_detector.py, line ~30
confidence_threshold=50  # Range: 0-100
```

- **Higher value (70-90)**: Fewer false positives, might miss some text
- **Lower value (30-50)**: Catches more text, may include noise

### Case Sensitivity
Currently **case-insensitive** by default. To make it case-sensitive:

```python
# In main_window.py, process_image() method
regions = self.text_detector.detect_specific_word(
    self.processed_image, 
    word,
    case_sensitive=True  # Add this parameter
)
```

### Exact Match Mode
To match whole words only (not partial):

```python
regions = self.text_detector.detect_specific_word(
    self.processed_image, 
    word,
    exact_match=True  # Add this parameter
)
```

---

## 🐛 Troubleshooting

### ❌ "Tesseract not found" Error

**Windows:**
1. Download: https://github.com/UB-Mannheim/tesseract/wiki
2. Install to: `C:\Program Files\Tesseract-OCR`
3. Add to PATH or update `text_detector.py`:
   ```python
   pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
   ```

**Linux:**
```bash
sudo apt-get update
sudo apt-get install tesseract-ocr
pip install pytesseract
```

**macOS:**
```bash
brew install tesseract
pip install pytesseract
```

### ❌ "Word not found" but it's clearly there

**Solutions:**
1. **Check image quality** - Enhance contrast
2. **Try different spelling** - "Email" vs "email"
3. **Use partial match** - Type "mail" instead of "email"
4. **Check text size** - Zoom in if text is too small
5. **Lower confidence threshold** in code

### ⚠️ OCR is slow

**Normal behavior:**
- First detection: 2-5 seconds (loading models)
- Subsequent detections: 1-3 seconds
- Large images: Up to 10 seconds

**Speed tips:**
- Disable real-time preview
- Use smaller images
- Process regions manually if you know exact locations

### ⚠️ Blurred area doesn't cover entire word

**Solutions:**
1. Increase padding in `text_detector.py`:
   ```python
   padding = 10  # Default is 8, try 12-15
   ```
2. Use higher blur strength
3. Use Pixelation effect (larger blocks)

---

## 💡 Examples

### Example 1: Redacting Emails
```
Image text: "Contact: john@example.com"
Type in field: "@"
Result: Blurs "john@example.com"
```

### Example 2: Hiding Names
```
Image text: "Hello John Smith"
Type in field: "john"
Result: Blurs "John" (case-insensitive)
```

### Example 3: Censoring Passwords
```
Image text: "Password: MySecret123"
Type in field: "mysecret"
Result: Blurs "MySecret123"
```

---

## 🎨 Effect Recommendations

| Use Case | Recommended Effect | Settings |
|----------|-------------------|----------|
| Documents | Black Bar | Opacity: 100% |
| Screenshots | Gaussian Blur | Strength: 51-75 |
| Social Media | Pixelation | Block Size: 15-20 |
| Legal Documents | Black Bar | Opacity: 100% |
| Personal Photos | Frosted Glass | Strength: 41 |

---

## 🔐 Privacy & Security

✅ **Privacy Features:**
- All processing happens **locally** on your computer
- No data is sent to any server
- No internet connection required
- Original images are backed up in `backups/` folder

⚠️ **Important:**
- Always verify blur coverage before sharing
- Use comparison view to check results
- Test with sensitive data on non-critical images first

---

## 📞 Support

### Installation Issues
See [SETUP.md](SETUP.md) for detailed installation instructions

### Feature Requests
Want exact match by default? Multiple words? Let us know!

### Logging
Check `logs/privacy_studio.log` for detailed OCR results

---

## 🎓 Technical Details

### How It Works

1. **Image Preprocessing**
   - Convert to grayscale
   - Apply Gaussian blur
   - Adaptive thresholding
   - Enhance contrast

2. **OCR Processing**
   - Tesseract OCR scans image
   - Returns text + bounding boxes + confidence
   - Filters by confidence threshold

3. **Text Matching**
   - Case-insensitive comparison
   - Substring matching (partial)
   - Returns all matching regions

4. **Effect Application**
   - Adds padding around text
   - Applies selected effect
   - Blends with opacity setting

### Dependencies
- **pytesseract**: Python wrapper for Tesseract
- **Tesseract OCR**: Actual OCR engine
- **OpenCV**: Image processing
- **NumPy**: Array operations

---

## 🚀 Tips for Best Results

1. **Image Quality Matters**
   - Use high resolution (min 1024px wide)
   - Ensure good lighting/contrast
   - Avoid motion blur

2. **Text Requirements**
   - Clear, standard fonts work best
   - Minimum text size: ~14px
   - Horizontal text is most reliable

3. **Testing**
   - Test on sample image first
   - Use "Compare" view to verify
   - Adjust blur strength as needed

4. **Performance**
   - First run is slower (loads models)
   - Disable real-time preview for better speed
   - Close other apps to free RAM

---

**Happy Blurring! 🎉**

For more information, check the main [README.md](README.md)