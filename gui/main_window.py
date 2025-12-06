"""
Main GUI Window for Advanced Privacy Studio Pro
"""
import cv2
import numpy as np
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from PIL import Image, ImageTk
import os

# Import custom modules
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from config import *
from core.image_processor import ImageProcessor, DetectionEngine
from core.batch_processor import BatchProcessor
from core.utils import HistoryManager, PresetManager, ImageUtils, ExportManager, format_timestamp
from core.image_picker import ImagePicker
from gui.batch_window import BatchWindow
from core.text_detector import TextDetector

class AdvancedPrivacyStudioPro:
    def __init__(self, root):
        self.root = root
        self.root.title("🚀 Advanced Image Privacy Studio Pro")
        self.root.geometry("1400x900")
        self.root.configure(bg=COLORS['bg_dark'])
        
        # Core components
        self.image_processor = ImageProcessor()
        self.detection_engine = DetectionEngine()
        self.text_detector = TextDetector()
        self.batch_processor = BatchProcessor(self.image_processor, self.detection_engine)
        self.history_manager = HistoryManager(MAX_HISTORY)
        self.preset_manager = PresetManager()
        self.image_utils = ImageUtils()
        
        # Variables
        self.original_image = None
        self.processed_image = None
        self.preview_image = None
        self.image_path = None

        # Variable for the user input
        self.target_word_var = tk.StringVar()
        
        # UI Variables
        self.detection_mode = tk.StringVar(value="face")
        self.effect_type = tk.StringVar(value="blur")
        self.blur_strength = tk.IntVar(value=BLUR_RANGE['default'])
        self.pixel_size = tk.IntVar(value=PIXEL_RANGE['default'])
        self.opacity = tk.IntVar(value=OPACITY_RANGE['default'])
        self.edge_blur = tk.IntVar(value=EDGE_BLUR_RANGE['default'])
        self.real_time_preview = tk.BooleanVar(value=False)
        
        # Drawing
        self.drawing_regions = []
        self.drawing = False
        self.start_x = None
        self.start_y = None
        self.current_rect = None
        
        # Display
        self.display_scale = 1.0
        self.display_offset = (0, 0)
        
        self.create_menu_bar()
        self.create_widgets()
        self.bind_shortcuts()
        
    def create_menu_bar(self):
        """Create application menu bar"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # File Menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Open Image", command=self.load_image, accelerator="Ctrl+O")
        file_menu.add_command(label="Save Result", command=self.save_image, accelerator="Ctrl+S")
        file_menu.add_command(label="Save As Comparison", command=self.save_comparison)
        file_menu.add_separator()
        file_menu.add_command(label="Batch Process", command=self.open_batch_window, accelerator="Ctrl+B")
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        
        # Edit Menu
        edit_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Edit", menu=edit_menu)
        edit_menu.add_command(label="Undo", command=self.undo, accelerator="Ctrl+Z")
        edit_menu.add_command(label="Redo", command=self.redo, accelerator="Ctrl+Y")
        edit_menu.add_separator()
        edit_menu.add_command(label="Clear Selections", command=self.clear_regions, accelerator="Ctrl+D")
        edit_menu.add_command(label="Reset Image", command=self.reset_image)
        
        # Presets Menu
        presets_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Presets", menu=presets_menu)
        presets_menu.add_command(label="Save Current Settings", command=self.save_preset)
        presets_menu.add_command(label="Load Preset", command=self.load_preset)
        presets_menu.add_command(label="Manage Presets", command=self.manage_presets)
        
        # Help Menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="Donate", command=self.show_donate)
        help_menu.add_command(label="About", command=self.show_about)
        help_menu.add_command(label="Shortcuts", command=self.show_shortcuts)
    
    def create_widgets(self):
        """Create main GUI widgets"""
        # Header
        header = tk.Frame(self.root, bg=COLORS['bg_medium'], height=70)
        header.pack(fill="x", pady=(0, 10))
        
        title = tk.Label(header, text="🚀 Advanced Image Privacy Studio Pro", 
                        font=("Helvetica", 24, "bold"),
                        bg=COLORS['bg_medium'], fg=COLORS['accent_cyan'])
        title.pack(side="left", padx=20, pady=15)
        
        # Real-time preview checkbox
        preview_check = tk.Checkbutton(
            header,
            text="🔴 Real-time Preview",
            variable=self.real_time_preview,
            command=self.toggle_preview,
            font=("Helvetica", 11),
            bg=COLORS['bg_medium'],
            fg=COLORS['text_white'],

            selectcolor=COLORS['bg_light'],
            # 🔥 REMOVE WHITE BORDER (focus / highlight)
            highlightthickness=0,
            highlightbackground=COLORS['bg_medium'],
            highlightcolor=COLORS['bg_medium'],
            bd=0,
            borderwidth=0,

            activebackground=COLORS['bg_medium'],
            activeforeground=COLORS['accent_green']
            )
        preview_check.pack(side="right", padx=20)
        
        # Main container
        main_container = tk.Frame(self.root, bg=COLORS['bg_dark'])
        main_container.pack(fill="both", expand=True, padx=15, pady=10)
        
        # Create left panel (controls)
        self.create_left_panel(main_container)
        
        # Create right panel (image display)
        self.create_right_panel(main_container)
        
        # Status bar
        self.create_status_bar()
        
    def create_radio(self, parent, text, variable, value, command=None):
        """Unified styled Radiobutton"""
        return tk.Radiobutton(
            parent,
            text=text,
            variable=variable,
            value=value,
            command=command,
            **RADIO_BASE,     # from config (font/bg/fg)
            **RADIO_STYLE     # remove highlight + active colors
        )

    def create_left_panel(self, parent):
        """Create left control panel"""
        left_panel = tk.Frame(parent, bg=COLORS['bg_medium'], width=350)
        left_panel.pack(side="left", fill="y",  padx=(0, 15))
        left_panel.pack_propagate(False)
        
        # Scrollable frame
        canvas_scroll = tk.Canvas(left_panel, bg=COLORS['bg_medium'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(left_panel, orient="vertical", command=canvas_scroll.yview)
        scrollable_frame = tk.Frame(canvas_scroll, bg=COLORS['bg_medium'])
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas_scroll.configure(scrollregion=canvas_scroll.bbox("all"))
        )
        
        canvas_scroll.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas_scroll.configure(yscrollcommand=scrollbar.set)
        
        canvas_scroll.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Enable mousewheel scrolling on Linux/Windows
        def _on_mousewheel(event):
            canvas_scroll.yview_scroll(int(-1*(event.delta/120)), "units")

        canvas_scroll.bind_all("<MouseWheel>", _on_mousewheel)

        canvas_scroll.bind_all("<Button-4>", lambda e: canvas_scroll.yview_scroll(-1, "units"))
        canvas_scroll.bind_all("<Button-5>", lambda e: canvas_scroll.yview_scroll(1, "units"))

        
        # Controls title
        tk.Label(scrollable_frame, text="⚙️ Controls", 
                font=("Helvetica", 18, "bold"),
                bg=COLORS['bg_medium'], fg=COLORS['accent_cyan']).pack(pady=15)
        
        # Load button
        self.load_btn = self.create_button(scrollable_frame, "📁 Load Image", 
                                           self.load_image, COLORS['bg_light'])
        self.load_btn.pack(pady=10, padx=20, fill="x")
        
        self.add_separator(scrollable_frame)
        
        # Effect type section
        self.create_effect_section(scrollable_frame)
        
        self.add_separator(scrollable_frame)
        
        # Detection mode section
        self.create_detection_section(scrollable_frame)
        
        self.add_separator(scrollable_frame)
        
        # Effect parameters
        self.create_parameters_section(scrollable_frame)
        
        self.add_separator(scrollable_frame)
        
        # Action buttons
        self.create_action_buttons(scrollable_frame)
        
        # Info
        tk.Label(scrollable_frame, 
                text="💡 Tip: Enable real-time preview\nfor instant results!",
                font=("Helvetica", 9, "italic"),
                bg=COLORS['bg_medium'], fg=COLORS['text_gray'],
                justify="center").pack(side="bottom", pady=20)
    
    def create_effect_section(self, parent):
        """Create effect type selection section"""
        tk.Label(parent, text="🎨 Effect Type:", 
                font=("Helvetica", 13, "bold"),
                bg=COLORS['bg_medium'], fg=COLORS['text_white']).pack(pady=(10, 5))
        
        effect_frame = tk.Frame(parent, bg=COLORS['bg_medium'])
        effect_frame.pack(pady=5, padx=20, fill="x")
        
        from config import EFFECT_LIST
        
        for text, value in EFFECT_LIST:
            rb = self.create_radio(
                effect_frame,
                text,
                self.effect_type,
                value,
                command=self.on_effect_change,
                )
            rb.pack(anchor="w", pady=3)
    
    def create_detection_section(self, parent):
        """Create detection mode section"""
        tk.Label(parent, text="🎯 Detection Mode:",
                font=("Helvetica", 13, "bold"),
                bg=COLORS['bg_medium'], fg=COLORS['text_white']).pack(pady=(10, 5))

        mode_frame = tk.Frame(parent, bg=COLORS['bg_medium'])
        mode_frame.pack(pady=5, padx=20, fill="x")

        self.mode_frame = mode_frame

        from config import DETECTION_LIST

        # Make sure "target_text" is in your config, or add it manually here:
        rb = self.create_radio(
            mode_frame,
            "✍️ Targeted Text",
            self.detection_mode,
            "target_text",
            command=self.on_detection_change,
            )
        rb.pack(anchor="w", pady=3)

        # Create the Input Field
        self.text_input_frame = tk.Frame(mode_frame, bg=COLORS['bg_medium'])

        tk.Label(
            self.text_input_frame,
            text="Type Word to blur:",
                font=("Helvetica", 10, "bold"),
                bg=COLORS['bg_medium'],
                fg=COLORS['text_white']).pack(pady=(10, 5), anchor="w")

        self.word_entry = tk.Entry(
            self.text_input_frame,
            textvariable=self.target_word_var,
            bg=COLORS['bg_dark'],
            fg="white", insertbackground="white")
        self.word_entry.pack(fill="x", pady=5)

        for text, value in DETECTION_LIST:
            rb = self.create_radio(
                mode_frame,
                text,
                self.detection_mode,
                value,
                command=self.on_detection_change,
                )
            rb.pack(anchor="w", pady=3)
    
    def create_parameters_section(self, parent):
        """Create effect parameters section"""
        self.params_frame = tk.Frame(parent, bg=COLORS['bg_medium'])
        self.params_frame.pack(pady=10, padx=20, fill="x")
        
        # Blur strength
        self.blur_param = self.create_slider(self.params_frame, "Blur Strength", 
                                             self.blur_strength, 
                                             BLUR_RANGE['min'], BLUR_RANGE['max'], 
                                             COLORS['accent_cyan'])
        
        # Pixel size
        self.pixel_param = self.create_slider(self.params_frame, "Pixel Block Size", 
                                              self.pixel_size, 
                                              PIXEL_RANGE['min'], PIXEL_RANGE['max'], 
                                              COLORS['accent_pink'])
        
        # Opacity
        self.opacity_param = self.create_slider(self.params_frame, "Effect Opacity (%)", 
                                                self.opacity, 
                                                OPACITY_RANGE['min'], OPACITY_RANGE['max'], 
                                                COLORS['accent_green'])
        self.opacity_param.pack(fill="x", pady=5)
        
        # Show appropriate parameters
        self.update_parameter_visibility()
    
    def create_slider(self, parent, label_text, variable, min_val, max_val, color):
        """Create a labeled slider"""
        frame = tk.Frame(parent, bg=COLORS['bg_medium'])
        
        tk.Label(frame, text=label_text, 
                font=("Helvetica", 11, "bold"),
                bg=COLORS['bg_medium'], fg=COLORS['text_white']).pack(pady=(5, 2))
        
        value_label = tk.Label(frame, textvariable=variable,
                              font=("Helvetica", 10),
                              bg=COLORS['bg_medium'], fg=color)
        value_label.pack()
        
        slider = tk.Scale(frame, from_=min_val, to=max_val, 
                         resolution=1 if 'Pixel' in label_text or 'Opacity' in label_text else 2,
                         variable=variable,
                         orient="horizontal",
                         bg=COLORS['bg_light'], fg=COLORS['text_white'],
                         troughcolor=COLORS['bg_dark'],
                         highlightthickness=0,
                         length=280,
                         command=lambda x: self.on_parameter_change())
        slider.pack(pady=5)
        
        return frame
    
    def create_action_buttons(self, parent):
        """Create action buttons"""
        # Process button
        self.process_btn = self.create_button(parent, "✨ Apply Effect", 
                                              self.process_image, 
                                              COLORS['accent_red'],
                                              state="disabled")
        self.process_btn.pack(pady=15, padx=20, fill="x")
        
        # Undo/Redo frame
        undo_frame = tk.Frame(parent, bg=COLORS['bg_medium'])
        undo_frame.pack(pady=5, padx=20, fill="x")
        
        self.undo_btn = self.create_button(undo_frame, "↶ Undo", 
                                           self.undo, 
                                           COLORS['accent_orange'],
                                           state="disabled")
        self.undo_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        self.redo_btn = self.create_button(undo_frame, "↷ Redo", 
                                           self.redo, 
                                           COLORS['accent_orange'],
                                           state="disabled")
        self.redo_btn.pack(side="right", fill="x", expand=True, padx=(5, 0))
        
        # Other buttons
        self.clear_btn = self.create_button(parent, "🗑️ Clear Selections", 
                                            self.clear_regions, 
                                            COLORS['accent_purple'])
        self.clear_btn.pack(pady=5, padx=20, fill="x")
        
        self.save_btn = self.create_button(parent, "💾 Save Result", 
                                           self.save_image, 
                                           COLORS['accent_green'],
                                           state="disabled")
        self.save_btn.pack(pady=5, padx=20, fill="x")
        
        # Batch process button
        batch_btn = self.create_button(parent, "📦 Batch Process", 
                                       self.open_batch_window, 
                                       COLORS['bg_light'])
        batch_btn.pack(pady=5, padx=20, fill="x")
    
    """
Main GUI Window - Part 2 (Implementation Methods)
Add this to the AdvancedPrivacyStudioPro class
"""

    def create_right_panel(self, parent):
        """Create right image display panel"""
        right_panel = tk.Frame(parent, bg=COLORS['bg_medium'])
        right_panel.pack(side="right", fill="both", expand=True)
        
        # Toolbar
        toolbar = tk.Frame(right_panel, bg=COLORS['bg_light'], height=50)
        toolbar.pack(fill="x", padx=10, pady=(10, 5))
        
        tk.Label(toolbar, text="🖼️ Image Canvas", 
                font=("Helvetica", 14, "bold"),
                bg=COLORS['bg_light'], fg=COLORS['text_white']).pack(side="left", padx=15, pady=10)
        
        # View buttons
        view_frame = tk.Frame(toolbar, bg=COLORS['bg_light'])
        view_frame.pack(side="right", padx=15)
        
        self.create_small_button(view_frame, "Original", 
                                 lambda: self.switch_view('original')).pack(side="left", padx=2)
        self.create_small_button(view_frame, "Processed", 
                                 lambda: self.switch_view('processed')).pack(side="left", padx=2)
        self.create_small_button(view_frame, "Compare", 
                                 lambda: self.switch_view('compare')).pack(side="left", padx=2)
        
        # Canvas
        self.canvas = tk.Canvas(right_panel, bg=COLORS['canvas_bg'], 
                               highlightthickness=2,
                               highlightbackground=COLORS['accent_cyan'])
        self.canvas.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Bind events
        self.canvas.bind("<Button-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.canvas.bind("<MouseWheel>", self.on_zoom)
    
    def create_status_bar(self):
        """Create status bar"""
        status_bar = tk.Frame(self.root, bg=COLORS['bg_medium'], height=35)
        status_bar.pack(fill="x", side="bottom")
        
        self.status_label = tk.Label(status_bar, text="Ready to load image...",
                                     font=("Helvetica", 10),
                                     bg=COLORS['bg_medium'], fg=COLORS['text_gray'])
        self.status_label.pack(side="left", padx=20, pady=8)
        
        self.info_label = tk.Label(status_bar, text="",
                                   font=("Helvetica", 9),
                                   bg=COLORS['bg_medium'], fg=COLORS['text_gray'])
        self.info_label.pack(side="right", padx=20, pady=8)
    
    # Helper methods
    def create_button(self, parent, text, command, bg_color, state="normal"):
        """Create styled button"""
        return tk.Button(parent, text=text,
                        command=command,
                        font=("Helvetica", 11, "bold"),
                        bg=bg_color, fg=COLORS['text_white'],
                        activebackground=bg_color,
                        cursor="hand2",
                        relief="flat",
                        padx=15, pady=10,
                        state=state)
    
    def create_small_button(self, parent, text, command):
        """Create small button"""
        return tk.Button(parent, text=text,
                        command=command,
                        font=("Helvetica", 9),
                        bg=COLORS['bg_dark'], fg=COLORS['text_white'],
                        activebackground=COLORS['bg_light'],
                        cursor="hand2",
                        relief="flat",
                        padx=10, pady=5)
    
    def add_separator(self, parent):
        """Add separator line"""
        ttk.Separator(parent, orient="horizontal").pack(fill="x", pady=12, padx=20)
    
    def bind_shortcuts(self):
        """Bind keyboard shortcuts"""
        self.root.bind(SHORTCUTS['load'], lambda e: self.load_image())
        self.root.bind(SHORTCUTS['save'], lambda e: self.save_image())
        self.root.bind(SHORTCUTS['undo'], lambda e: self.undo())
        self.root.bind(SHORTCUTS['redo'], lambda e: self.redo())
        self.root.bind(SHORTCUTS['process'], lambda e: self.process_image())
        self.root.bind(SHORTCUTS['clear'], lambda e: self.clear_regions())
        self.root.bind(SHORTCUTS['batch'], lambda e: self.open_batch_window())
    
    # Core functionality
    def load_image(self):
        """Load image from file"""
        # file_path = filedialog.askopenfilename(
        #     title="Select Image",
        #     filetypes=SUPPORTED_FORMATS
        # )
        from core.image_picker import ImagePicker

        picker = ImagePicker(self.root)
        file_path = picker.open()

        if not file_path:
            return
        
        if file_path:
            self.image_path = file_path
            self.original_image = cv2.imread(file_path)
            
            if self.original_image is None:
                messagebox.showerror("Error", "Could not load image!")
                return
            
            self.processed_image = self.original_image.copy()
            self.drawing_regions = []
            self.history_manager.clear()
            
            self.display_image(self.original_image)
            self.process_btn.config(state="normal")
            
            # Update info
            info = self.image_utils.get_image_info(self.original_image)
            self.status_label.config(text=f"Loaded: {os.path.basename(file_path)}")
            self.info_label.config(text=f"{info['width']}x{info['height']} | {info['size_kb']} KB")
            self.update_buttons()
    
    def display_image(self, cv_image):
        """Display image on canvas"""
        if cv_image is None:
            return
        
        rgb_image = cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB)
        
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        
        if canvas_width <= 1:
            canvas_width = 900
            canvas_height = 700
        
        resized, scale = self.image_utils.resize_for_display(
            rgb_image, canvas_width, canvas_height
        )
        
        pil_image = Image.fromarray(resized)
        self.photo = ImageTk.PhotoImage(pil_image)
        
        self.canvas.delete("all")
        new_w, new_h = resized.shape[1], resized.shape[0]
        x = (canvas_width - new_w) // 2
        y = (canvas_height - new_h) // 2
        self.canvas.create_image(x, y, anchor="nw", image=self.photo)
        
        self.display_scale = scale
        self.display_offset = (x, y)
    
    def process_image(self):
        """Process image with current settings"""
        if self.original_image is None:
            return
        
        # Save to history
        if self.processed_image is not None:
            self.history_manager.save_state(self.processed_image)
        
        mode = self.detection_mode.get()
        effect = self.effect_type.get()
        
        self.processed_image = self.processed_image.copy()
        
        try:
            # Detect regions
            if mode == "face":
                regions = self.detection_engine.detect_faces(self.processed_image)
            elif mode == "eye":
                regions = self.detection_engine.detect_eyes(self.processed_image)
            elif mode == "body":
                regions = self.detection_engine.detect_full_body(self.processed_image)
            elif mode == "license_plate":
                regions = self.detection_engine.detect_license_plates(self.processed_image)
            elif mode == "text":
                regions = self.detection_engine.detect_text(self.processed_image)
            elif mode == "target_text":
                word = self.target_word_var.get()
                if not word:
                    messagebox.showwarning("Wait!", "Please type the word you want to blur.")
                    return

                regions = self.text_detector.detect_specific_word(self.processed_image, word)

                if not regions:
                    messagebox.showinfo("Info", f"Could not find the word '{word}' in this image.")
                    return
            elif mode == "manual":
                if not self.drawing_regions:
                    messagebox.showinfo("Info", "Draw regions on the image first!")
                    return
                regions = self.drawing_regions
            elif mode == "full":
                h, w = self.processed_image.shape[:2]
                regions = [(0, 0, w, h)]
            else:
                return
            
            # Apply effect to each region
            for (x, y, w, h) in regions:
                self.apply_effect_to_region(x, y, w, h, effect)
            
            self.display_image(self.processed_image)
            self.save_btn.config(state="normal")
            self.status_label.config(text=f"Processed {len(regions)} region(s)")
            self.update_buttons()
            
        except Exception as e:
            messagebox.showerror("Error", f"Processing failed: {str(e)}")
    
    def apply_effect_to_region(self, x, y, w, h, effect):
        """Apply selected effect to region"""
        original_region = self.original_image[y:y+h, x:x+w]
        
        if effect == "blur":
            strength = self.blur_strength.get()
            result = self.image_processor.gaussian_blur(self.processed_image, x, y, w, h, strength)
        elif effect == "pixelation":
            pixel_size = self.pixel_size.get()
            result = self.image_processor.pixelate(self.processed_image, x, y, w, h, pixel_size)
        elif effect == "black_bar":
            result = self.image_processor.black_bar(self.processed_image, x, y, w, h)
        elif effect == "gradient":
            result = self.image_processor.gradient_fade(self.processed_image, x, y, w, h)
        elif effect == "mosaic":
            result = self.image_processor.mosaic_effect(self.processed_image, x, y, w, h)
        elif effect == "glass":
            result = self.image_processor.frosted_glass(self.processed_image, x, y, w, h)
        elif effect == "oil_paint":
            result = self.image_processor.oil_paint(self.processed_image, x, y, w, h)
        else:
            return
        
        # Apply opacity
        opacity = self.opacity.get()
        if opacity < 100:
            result = self.image_processor.apply_opacity(original_region, result, opacity)
        
        self.processed_image[y:y+h, x:x+w] = result
    
    def save_image(self):
        """Save processed image"""
        if self.processed_image is None:
            return
        
        file_path = filedialog.asksaveasfilename(
            defaultextension=".jpg",
            filetypes=SAVE_FORMATS
        )
        
        if file_path:
            cv2.imwrite(file_path, self.processed_image)
            messagebox.showinfo("Success", f"Image saved successfully!")
            self.status_label.config(text=f"Saved: {os.path.basename(file_path)}")
    
    def save_comparison(self):
        """Save side-by-side comparison"""
        if self.original_image is None or self.processed_image is None:
            return
        
        file_path = filedialog.asksaveasfilename(
            defaultextension=".jpg",
            filetypes=SAVE_FORMATS
        )
        
        if file_path:
            ExportManager.export_comparison(self.original_image, self.processed_image, file_path)
            messagebox.showinfo("Success", "Comparison saved!")
    
    # Event handlers
    def on_effect_change(self):
        """Handle effect type change"""
        self.update_parameter_visibility()
        if self.real_time_preview.get():
            self.process_image()

    def on_detection_change(self):
        """Handle detection mode change"""
        self.update_parameter_visibility()
        if self.real_time_preview.get():
            self.process_image()

    def on_parameter_change(self):
        """Handle parameter change"""
        if self.real_time_preview.get() and self.original_image is not None:
            self.process_image()
    
    def update_parameter_visibility(self):
        """Show/hide parameters based on effect"""
        self.blur_param.pack_forget()
        self.pixel_param.pack_forget()

        # Toggle Text Input
        self.text_input_frame.pack_forget()

        if self.detection_mode.get() == "target_text":
            self.text_input_frame.pack(anchor="w", padx=20, pady=5)

        effect = self.effect_type.get()
        if effect in ["blur", "glass"]:
            self.blur_param.pack(fill="x", pady=5)
        elif effect == "pixelation":
            self.pixel_param.pack(fill="x", pady=5)
    
    def toggle_preview(self):
        """Toggle real-time preview"""
        if self.real_time_preview.get():
            self.status_label.config(text="Real-time preview enabled")
        else:
            self.status_label.config(text="Real-time preview disabled")
    
    # Mouse events for manual selection
    def on_mouse_down(self, event):
        """Handle mouse down"""
        if self.detection_mode.get() == "manual" and self.original_image is not None:
            self.drawing = True
            self.start_x = event.x
            self.start_y = event.y
    
    def on_mouse_drag(self, event):
        """Handle mouse drag"""
        if self.drawing:
            self.canvas.delete("current_rect")
            self.current_rect = self.canvas.create_rectangle(
                self.start_x, self.start_y, event.x, event.y,
                outline=COLORS['accent_cyan'], width=3, tags="current_rect"
            )
    
    def on_mouse_up(self, event):
        """Handle mouse up"""
        if self.drawing:
            self.drawing = False
            x1 = int((self.start_x - self.display_offset[0]) / self.display_scale)
            y1 = int((self.start_y - self.display_offset[1]) / self.display_scale)
            x2 = int((event.x - self.display_offset[0]) / self.display_scale)
            y2 = int((event.y - self.display_offset[1]) / self.display_scale)
            
            x, w = (x1, x2-x1) if x2 > x1 else (x2, x1-x2)
            y, h = (y1, y2-y1) if y2 > y1 else (y2, y1-y2)
            
            if w > 10 and h > 10:
                self.drawing_regions.append((x, y, w, h))
                self.status_label.config(text=f"Added region ({len(self.drawing_regions)} total)")
    
    def on_zoom(self, event):
        """Handle zoom with mouse wheel"""
        """Handle zoom with mouse wheel"""
        if self.original_image is None:
            return
        
        # Determine direction
        scale_multiplier = 1.0

        # Windows/Linux uses event.delta, MacOS uses event.num
        if event.num == 4 or event.delta > 0:
            scale_multiplier = 1.1  # Zoom in
        elif event.num == 5 or event.delta < 0:
            scale_multiplier = 0.9  # Zoom out

        # Apply limit to zoom
        new_scale = self.display_scale * scale_multiplier
        if 0.1 < new_scale < 5.0:
            self.display_scale = new_scale

            # Refresh Display
            if self.processed_image is not None:
                self.display_image(self.processed_image)
            else:
                self.display_image(self.original_image)

            # Show zoom level in status bar
            self.status_label.config(text=f"Zoom: {int(self.display_scale * 100)}%")

    # Additional methods
    def undo(self):
        """Undo last operation"""
        prev_image = self.history_manager.undo()
        if prev_image is not None:
            self.history_manager.add_to_redo(self.processed_image)
            self.processed_image = prev_image
            self.display_image(self.processed_image)
            self.status_label.config(text="Undo successful")
            self.update_buttons()
    
    def redo(self):
        """Redo last undone operation"""
        next_image = self.history_manager.redo()
        if next_image is not None:
            self.history_manager.save_state(self.processed_image)
            self.processed_image = next_image
            self.display_image(self.processed_image)
            self.status_label.config(text="Redo successful")
            self.update_buttons()
    
    def clear_regions(self):
        """Clear all manual selections"""
        self.drawing_regions = []
        self.canvas.delete("current_rect")
        if self.original_image is not None:
            self.display_image(self.processed_image)
        self.status_label.config(text="Cleared all selections")
    
    def reset_image(self):
        """Reset to original image"""
        if self.original_image is not None:
            self.processed_image = self.original_image.copy()
            self.display_image(self.processed_image)
            self.drawing_regions = []
            self.history_manager.clear()
            self.status_label.config(text="Image reset to original")
            self.update_buttons()
    
    def switch_view(self, view_type):
        """Switch between different views"""
        if view_type == 'original' and self.original_image is not None:
            self.display_image(self.original_image)
            self.status_label.config(text="Viewing Original Image")
        
        elif view_type == 'processed' and self.processed_image is not None:
            self.display_image(self.processed_image)
            self.status_label.config(text="Viewing Processed Image")
        elif view_type == 'compare':
            if self.original_image is None and self.processed_image is None:
                return
            # Ensure images are the same size for concatenation
            h1, w1 = self.original_image.shape[:2]
            h2, w2 = self.processed_image.shape[:2]

            # Resize processed to match original if needed (though they should be same)
            proc_img_resized = self.processed_image
            if (h1, w1) != (h2, w2):
                proc_img_resized = cv2.resize(self.processed_image, (w1, h1))

                # Add a divider line
            divider = np.ones((h1, 10, 3), dtype=np.uint8) * 255  # white line
            divider[:] = [255, 255, 255]  # white line

            # Stack horizontally
            comparison_image = np.hstack((self.original_image, divider, proc_img_resized))
            self.display_image(comparison_image)
            self.status_label.config(text="Viewing Comparison Image")
            pass
    
    def update_buttons(self):
        """Update button states"""
        if self.history_manager.can_undo():
            self.undo_btn.config(state="normal")
        else:
            self.undo_btn.config(state="disabled")
        
        if self.history_manager.can_redo():
            self.redo_btn.config(state="normal")
        else:
            self.redo_btn.config(state="disabled")
    
    # Preset methods
    def save_preset(self):
        """Save current settings as preset"""
        name = simpledialog.askstring("Save Preset", "Enter preset name:")
        if name:
            settings = {
                'effect_type': self.effect_type.get(),
                'detection_mode': self.detection_mode.get(),
                'blur_strength': self.blur_strength.get(),
                'pixel_size': self.pixel_size.get(),
                'opacity': self.opacity.get()
            }
            self.preset_manager.add_preset(name, settings)
            messagebox.showinfo("Success", f"Preset '{name}' saved!")
    
    def load_preset(self):
        """Load preset"""
        presets = self.preset_manager.get_all_presets()
        if not presets:
            messagebox.showinfo("Info", "No presets available")
            return
        
        # Create simple selection dialog
        # Implementation needed
        pass
    
    def manage_presets(self):
        """Open preset management window"""
        # Implementation needed
        pass
    
    def open_batch_window(self):
        """Open batch processing window"""
        # Create batch window (separate implementation needed)
        BatchWindow(self.root, self.batch_processor)
    
    def show_donate(self):
        """Show donation dialog with clickable buttons"""
        import webbrowser

        # Create custom donation dialog
        donate_window = tk.Toplevel(self.root)
        donate_window.title("Support the Developer")
        donate_window.geometry("400x300")
        donate_window.configure(bg=COLORS['bg_medium'])
        donate_window.resizable(False, False)
        donate_window.transient(self.root)
        donate_window.grab_set()

        # Center the window
        donate_window.geometry("+{}+{}".format(
            self.root.winfo_x() + (self.root.winfo_width() // 2) - 200,
            self.root.winfo_y() + (self.root.winfo_height() // 2) - 150
        ))

        # Title
        title_label = tk.Label(donate_window,
                             text="Support the Developer",
                             font=("Helvetica", 16, "bold"),
                             bg=COLORS['bg_medium'],
                             fg=COLORS['accent_cyan'])
        title_label.pack(pady=15)

        # Message
        msg_label = tk.Label(donate_window,
                           text="Thank you for considering supporting this project!\n"
                                "Choose your preferred donation platform:",
                           font=("Helvetica", 10),
                           bg=COLORS['bg_medium'],
                           fg=COLORS['text_white'],
                           justify="center")
        msg_label.pack(pady=10)

        # Button frame
        button_frame = tk.Frame(donate_window, bg=COLORS['bg_medium'])
        button_frame.pack(pady=10, padx=20, fill="x")

        # PayPal button
        paypal_btn = tk.Button(button_frame,
                             text="💳 PayPal",
                             command=lambda: self.open_url("https://paypal.me/freerave1"),
                             font=("Helvetica", 11, "bold"),
                             bg="#0070ba", fg="white",
                             activebackground="#005ea6",
                             cursor="hand2",
                             relief="flat",
                             padx=15, pady=8)
        paypal_btn.pack(fill="x", pady=3)

        # Buy Me a Coffee button
        bmc_btn = tk.Button(button_frame,
                          text="☕ Buy Me a Coffee",
                          command=lambda: self.open_url("https://buymeacoffee.com/freerave"),
                          font=("Helvetica", 11, "bold"),
                          bg="#ffdd00", fg="black",
                          activebackground="#ffcc00",
                          cursor="hand2",
                          relief="flat",
                          padx=15, pady=8)
        bmc_btn.pack(fill="x", pady=3)

        # Ko-fi button
        kofi_btn = tk.Button(button_frame,
                           text="🎨 Ko-fi",
                           command=lambda: self.open_url("https://ko-fi.com/freerave"),
                           font=("Helvetica", 11, "bold"),
                           bg="#ff5e5b", fg="white",
                           activebackground="#ff4742",
                           cursor="hand2",
                           relief="flat",
                           padx=15, pady=8)
        kofi_btn.pack(fill="x", pady=3)

        # GitHub Sponsors button
        github_btn = tk.Button(button_frame,
                             text="⭐ GitHub Sponsors",
                             command=lambda: self.open_url("https://github.com/sponsors/kareem2099"),
                             font=("Helvetica", 11, "bold"),
                             bg="#24292e", fg="white",
                             activebackground="#1b1f23",
                             cursor="hand2",
                             relief="flat",
                             padx=15, pady=8)
        github_btn.pack(fill="x", pady=3)

        # Close button
        close_btn = tk.Button(donate_window,
                            text="Close",
                            command=donate_window.destroy,
                            font=("Helvetica", 10),
                            bg=COLORS['bg_light'], fg=COLORS['text_white'],
                            activebackground=COLORS['bg_dark'],
                            cursor="hand2",
                            relief="flat",
                            padx=20, pady=5)
        close_btn.pack(pady=15)

    def open_url(self, url):
        """Open URL in default browser"""
        import webbrowser
        try:
            webbrowser.open(url)
        except:
            messagebox.showerror("Error", "Could not open browser. Please visit:\n" + url)

    def show_about(self):
        """Show about dialog"""
        messagebox.showinfo("About",
            "Advanced Image Privacy Studio Pro\nVersion 1.0.0\n\n"
            "Powerful image privacy protection tool with advanced features\n\n"
            "Support the developer:\n"
            "• PayPal: https://paypal.me/freerave1\n"
            "• Buy Me a Coffee: https://buymeacoffee.com/freerave\n"
            "• Ko-fi: https://ko-fi.com/freerave\n\n"
            "Made with ❤️ by FreeRave")

    def show_shortcuts(self):
        """Show keyboard shortcuts"""
        shortcuts_text = "\n".join([f"{key}: {value}" for key, value in SHORTCUTS.items()])
        messagebox.showinfo("Keyboard Shortcuts", shortcuts_text)
