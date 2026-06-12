"""
Main GUI Window for Advanced Privacy Studio Pro
"""
import cv2
import numpy as np
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from PIL import Image, ImageTk
import os
import logging

logger = logging.getLogger(__name__)
# Import custom modules
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# MVC Imports (New Structure)
from src.config import *
from src.models.image_processor import ImageProcessor
from src.models.detection_engine import DetectionEngine
from src.managers.theme_manager import ThemeManager
from src.managers.localization_manager import get_locale_manager
from src.managers.rtl_manager import get_rtl_manager
# from src.utils.image_utils import ImageUtil

from core.batch_processor import BatchProcessor
from core.utils import HistoryManager, PresetManager, ImageUtils, ExportManager, format_timestamp
from core.image_picker import ImagePicker
from gui.batch_window import BatchWindow
from core.text_detector import TextDetector
from core.auto_updater import AutoUpdater
from src.managers.auth_server import LocalAuthManager

from src.managers.database_manager import init_database_manager, get_db_manager
from src.managers.license_manager import LicenseManager
from core.metadata_spoofer import (
    spoof as _spoof_metadata,
    spoof_custom as _spoof_custom,
    read_exif_fields,
    PROFILES as SPOOF_PROFILES,
)
from gui.metadata_dialog import MetadataCustomizerDialog
from gui.metadata_report import MetadataReportDialog

class AdvancedPrivacyStudioPro:
    def __init__(self, root):
        self.root = root
        
        # Initialize Managers (so we can use them immediately)
        self.locale_manager = get_locale_manager()
        self.theme_manager = ThemeManager(self.root)
        self.rtl_manager = get_rtl_manager(self)
        self.db_manager = init_database_manager()
        self.license_manager = LicenseManager(self.db_manager)
        
        # Use Locale Manager to set the title
        # Now self.locale_manager exists and is ready to use
        self.update_window_title()
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
        self.main_container = None  # Reference for RTL Manager
        self.original_exif_bytes = None  # Raw EXIF bytes captured at load time

        # Variable for the user input
        self.target_word_var = tk.StringVar()
        
        # Initialize UI StringVars
        self.init_ui_strings()
        
        # UI Variables
        self.detection_mode = tk.StringVar(value="face")
        self.effect_type = tk.StringVar(value="blur")
        self.blur_strength = tk.IntVar(value=BLUR_RANGE['default'])
        self.pixel_size = tk.IntVar(value=PIXEL_RANGE['default'])
        self.opacity = tk.IntVar(value=OPACITY_RANGE['default'])
        self.edge_blur = tk.IntVar(value=EDGE_BLUR_RANGE['default'])
        self.real_time_preview = tk.BooleanVar(value=False)
        self.language_var = tk.StringVar(value="en")  # Language selection variable
        self.scrub_exif = tk.BooleanVar(value=False)  # Max-only: strip EXIF on save
        self.spoof_metadata = tk.BooleanVar(value=False)
        self.spoof_profile   = tk.StringVar(value="troll")
        self.custom_field_actions: dict | None = None   # set by dialog
        
        
        # Drawing
        self.drawing_regions = []
        self.drawing = False
        self.start_x = None
        self.start_y = None
        self.current_rect = None
        
        # Display
        self.display_scale = 1.0
        self.display_offset = (0, 0)

        # Auto-updater
        self.auto_updater = AutoUpdater(self.root)

        # Track app launch
        self.db_manager.increment_stat('app_launches')
        
        # IMPORTANT: Create menu bar and widgets BEFORE restoring window state
        # This ensures the menu bar exists when the window is maximized
        self.create_menu_bar()
        self.create_widgets()
        self.bind_shortcuts()
        
        # Restore window state AFTER creating UI elements
        self.restore_window_state()

        # Trigger automatic silent update check after UI loads
        if UPDATE_CONFIG['auto_check']:
            # Wait 3 seconds for UI to load, then check silently in background
            # Fixed: This function must exist below with the same name
            self.root.after(3000, lambda: self.auto_updater.check_for_updates_silently(self.on_update_ready))
        
        # Bind window state events to handle maximize/fullscreen
        # Note: Only using Map event to avoid excessive refreshing
        self.root.bind('<Map>', self.on_window_state_change)
        
        # Restore user settings from database
        self.restore_user_settings()
        
        # Enable Drag & Drop (missing piece)
        try:
            self.root.drop_target_register('DND_Files')
            self.root.dnd_bind('<<Drop>>', self.on_drop)
        except Exception as e:
            print(f"⚠️ Drag & Drop setup skipped: {e}")
            
    def update_window_title(self):
        title = self.locale_manager.get("app.title")
        if self.license_manager.is_max_activated:
            title += " (PRO)"
        self.root.title(title)
        
    def init_ui_strings(self):
        """Initialize all tk.StringVar objects for UI localization."""
        _ = self.locale_manager.get
        
        # Simple key-to-variable mapping for single labels/buttons
        self.ui_strings = {
            "ui.header.title": tk.StringVar(value=_("ui.header.title")),
            "ui.header.preview": tk.StringVar(value=_("ui.header.preview")),
            "ui.controls.title": tk.StringVar(value=_("ui.controls.title")),
            "ui.controls.load_image": tk.StringVar(value=_("ui.controls.load_image")),
            "ui.controls.effect_type": tk.StringVar(value=_("ui.controls.effect_type")),
            "ui.controls.detection_mode": tk.StringVar(value=_("ui.controls.detection_mode")),
            "ui.controls.target_text": tk.StringVar(value=_("ui.controls.target_text")),
            "ui.controls.blur_strength": tk.StringVar(value=_("ui.controls.blur_strength")),
            "ui.controls.pixel_size": tk.StringVar(value=_("ui.controls.pixel_size")),
            "ui.controls.opacity": tk.StringVar(value=_("ui.controls.opacity")),
            "ui.controls.apply_effect": tk.StringVar(value=_("ui.controls.apply_effect")),
            "ui.controls.undo": tk.StringVar(value=_("ui.controls.undo")),
            "ui.controls.redo": tk.StringVar(value=_("ui.controls.redo")),
            "ui.controls.clear_selections": tk.StringVar(value=_("ui.controls.clear_selections")),
            "ui.controls.save_result": tk.StringVar(value=_("ui.controls.save_result")),
            "ui.controls.batch_process": tk.StringVar(value=_("ui.controls.batch_process")),
            "ui.controls.tip": tk.StringVar(value=_("ui.controls.tip")),
            "ui.buttons.load": tk.StringVar(value=_("ui.buttons.load")),
            "ui.buttons.apply": tk.StringVar(value=_("ui.buttons.apply")),
            "ui.buttons.save": tk.StringVar(value=_("ui.buttons.save")),
            "ui.buttons.reset": tk.StringVar(value=_("ui.buttons.reset"))
        }

        # Lists for radio buttons
        self.effect_keys = [
            "effects.blur", "effects.pixelation", "effects.black_bar",
            "effects.gradient", "effects.mosaic", "effects.glass", "effects.oil_paint"
        ]
        self.effect_strings = [tk.StringVar(value=_(k)) for k in self.effect_keys]

        self.detection_keys = [
            "detection.face", "detection.eye", "detection.body",
            "detection.license_plate", "detection.text", "detection.manual", "detection.full"
        ]
        self.detection_strings = [tk.StringVar(value=_(k)) for k in self.detection_keys]

    def create_menu_bar(self):
        """Create application menu bar — geometry-safe rebuild.

        Destroying and recreating a tk.Menu causes X11 to issue a new
        ConfigureNotify that grows the root window by ~33 px (the menubar
        height).  In a maximized window that pushes the status-bar row
        below the visible screen edge.  We lock the root geometry before
        the rebuild and restore it immediately afterwards so the window
        manager cannot grant a new size.
        """
        # ── snapshot current geometry so we can restore it after rebuild ──
        self.root.update_idletasks()
        _geo_before = self.root.geometry()   # e.g. "1920x979+0+0"

        # If menubar exists, destroy it before recreating
        if hasattr(self, 'menubar') and self.menubar:
            self.menubar.destroy()

        menubar = tk.Menu(self.root)
        # Store menubar reference for refresh operations
        self.menubar = menubar
        self.root.config(menu=menubar)
        _ = self.locale_manager.get
        
        # File Menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label=_("menu.file"), menu=file_menu)
        file_menu.add_command(label=_("menu.file_items.open_image"), command=self.load_image, accelerator="Ctrl+O")
        
        # Open Recent submenu
        recent_menu = tk.Menu(file_menu, tearoff=0)
        file_menu.add_cascade(label=_("menu.file_items.open_recent"), menu=recent_menu)
        
        # Populate recent files
        recent_files = self.db_manager.get_recent_files(5)
        if recent_files:
            for file_info in recent_files:
                file_path = file_info['path']
                file_name = os.path.basename(file_path)
                recent_menu.add_command(
                    label=file_name,
                    command=lambda p=file_path: self.load_image_from_path(p)
                )
            recent_menu.add_separator()
            recent_menu.add_command(label=_("menu.file_items.clear_history"), command=self.clear_recent_history)
        else:
            recent_menu.add_command(label=_("menu.file_items.no_recent"), state="disabled")
        
        file_menu.add_separator()
        file_menu.add_command(label=_("menu.file_items.save_result"), command=self.save_image, accelerator="Ctrl+S")
        file_menu.add_command(label=_("menu.file_items.save_comparison"), command=self.save_comparison)
        file_menu.add_separator()
        file_menu.add_command(label=_("menu.file_items.open_exports"), command=self.open_exports_folder)
        file_menu.add_separator()
        file_menu.add_command(label=_("menu.file_items.batch_process"), command=self.open_batch_window, accelerator="Ctrl+B")
        file_menu.add_separator()
        file_menu.add_command(label=_("menu.file_items.exit"), command=self.on_close)
        
        # Edit Menu
        edit_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label=_("menu.edit"), menu=edit_menu)
        edit_menu.add_command(label=_("menu.edit_items.undo"), command=self.undo, accelerator="Ctrl+Z")
        edit_menu.add_command(label=_("menu.edit_items.redo"), command=self.redo, accelerator="Ctrl+Y")
        edit_menu.add_separator()
        edit_menu.add_command(label=_("menu.edit_items.clear_selections"), command=self.clear_regions, accelerator="Ctrl+D")
        edit_menu.add_command(label=_("menu.edit_items.reset_image"), command=self.reset_image)
        
        # Presets Menu
        presets_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label=_("menu.presets"), menu=presets_menu)
        presets_menu.add_command(label=_("menu.presets_items.save_settings"), command=self.save_preset)
        presets_menu.add_command(label=_("menu.presets_items.load_preset"), command=self.load_preset)
        presets_menu.add_command(label=_("menu.presets_items.manage_presets"), command=self.manage_presets)
        
        # View Menu
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label=_("menu.view"), menu=view_menu)
        
        # Theme submenu
        theme_menu = tk.Menu(view_menu, tearoff=0)
        view_menu.add_cascade(label=_("menu.view_items.themes"), menu=theme_menu)
        
        # Add theme options
        for theme_name, theme_key in self.theme_manager.get_theme_names():
            theme_menu.add_command(
                label=theme_name,
                command=lambda k=theme_key: self.change_theme(k)
            )
        
        # Language submenu
        lang_menu = tk.Menu(view_menu, tearoff=0)
        view_menu.add_cascade(label=_("menu.view_items.language"), menu=lang_menu)
        
        # Add language options
        self.add_language_menu_items(lang_menu)
        
        # Help Menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label=_("menu.help"), menu=help_menu)
        
        if self.license_manager.is_max_activated:
            help_menu.add_command(label="⭐️ PRO Activated", state="disabled")
        else:
            help_menu.add_command(label="⭐️ Upgrade to Pro", command=self.show_activation_dialog)
            
        help_menu.add_separator()
        help_menu.add_command(label=_("menu.help_items.check_updates"), command=self.check_for_updates)
        help_menu.add_separator()
        help_menu.add_command(label=_("menu.help_items.open_app_data"), command=self.open_app_data_folder)
        help_menu.add_separator()
        help_menu.add_command(label=_("menu.help_items.donate"), command=self.show_donate)
        help_menu.add_command(label=_("menu.help_items.about"), command=self.show_about)
        help_menu.add_command(label=_("menu.help_items.shortcuts"), command=self.show_shortcuts)

        # ── restore geometry: undo any root-window growth caused by Menu rebuild ──
        self.root.update_idletasks()
        _geo_after = self.root.geometry()
        if _geo_after != _geo_before:
            self.root.geometry(_geo_before)
    
    def create_widgets(self):
        """Create main GUI widgets"""

        # --- Root-level layout uses GRID (not pack) ---
        # Grid explicitly assigns fixed/expandable rows so the status bar
        # in row 2 ALWAYS keeps its height, even in maximized windows.
        self.root.grid_rowconfigure(0, weight=0)   # header   – fixed
        self.root.grid_rowconfigure(1, weight=1)   # content  – expandable
        self.root.grid_rowconfigure(2, weight=0)   # status   – fixed
        self.root.grid_columnconfigure(0, weight=1)

        # Row 0 – Header
        header = tk.Frame(self.root, bg=COLORS['bg_medium'], height=70)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 0))
        header.grid_propagate(False)

        title = tk.Label(header, textvariable=self.ui_strings["ui.header.title"],
                        font=("Helvetica", 24, "bold"),
                        bg=COLORS['bg_medium'], fg=COLORS['accent_cyan'],
                        anchor=self.get_text_anchor("w"),
                        justify=self.get_text_justify("left"))
        title.pack(side=self.get_pack_side("left"), padx=20, pady=15)

        preview_check = tk.Checkbutton(
            header,
            textvariable=self.ui_strings["ui.header.preview"],
            variable=self.real_time_preview,
            command=self.toggle_preview,
            font=("Helvetica", 11),
            bg=COLORS['bg_medium'],
            fg=COLORS['text_white'],
            selectcolor=COLORS['bg_light'],
            highlightthickness=0,
            highlightbackground=COLORS['bg_medium'],
            highlightcolor=COLORS['bg_medium'],
            bd=0,
            borderwidth=0,
            activebackground=COLORS['bg_medium'],
            activeforeground=COLORS['accent_green']
        )
        preview_check.pack(side=self.get_pack_side("right"), padx=20)

        # Row 2 – Status bar (create BEFORE main_container so it always exists)
        self.create_status_bar()

        # Row 1 – Main content container
        main_container = tk.Frame(self.root, bg=COLORS['bg_dark'])
        main_container.grid(row=1, column=0, sticky="nsew", padx=15, pady=10)

        # IMPORTANT: Store reference for RTL Manager
        self.main_container = main_container

        # Configure inner grid layout – 2 columns
        main_container.grid_columnconfigure(0, weight=0)  # Control panel (fixed)
        main_container.grid_columnconfigure(1, weight=1)  # Canvas (expandable)
        main_container.grid_rowconfigure(0, weight=1)

        # Create panels
        if self.is_rtl:
            self.create_left_panel_grid(main_container, column=1)
            self.create_right_panel_grid(main_container, column=0)
        else:
            self.create_left_panel_grid(main_container, column=0)
            self.create_right_panel_grid(main_container, column=1)
        
    def create_radio(self, parent, textvariable, variable, value, command=None):
        """Unified styled Radiobutton"""
        return tk.Radiobutton(
            parent,
            textvariable=textvariable,
            variable=variable,
            value=value,
            command=command,
            **RADIO_BASE,
            **RADIO_STYLE
        )

    def create_left_panel(self, parent):
        """Create left control panel"""
        left_panel = tk.Frame(parent, bg=COLORS['bg_medium'], width=350)
        # Pack on appropriate side based on RTL
        pack_side = self.get_pack_side("left")
        padx = (0, 15) if pack_side == "left" else (15, 0)
        
        print(f"🔍 [DEBUG] Creating left_panel: pack_side={pack_side}, RTL={self.is_rtl}")
        
        left_panel.pack(side=pack_side, fill="y", padx=padx)
        left_panel.pack_propagate(False)
        
        # Store reference for debugging
        self.left_panel = left_panel
        
        print(f"✅ [DEBUG] left_panel packed: width={left_panel.winfo_reqwidth()}")
        
        # Scrollable frame
        canvas_scroll = tk.Canvas(left_panel, bg=COLORS['bg_medium'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(left_panel, orient="vertical", command=canvas_scroll.yview)
        scrollable_frame = tk.Frame(canvas_scroll, bg=COLORS['bg_medium'])
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas_scroll.configure(scrollregion=canvas_scroll.bbox("all"))
        )
        
        controls_window_id = canvas_scroll.create_window((0, 0), window=scrollable_frame, anchor="nw")
        
        # Ensure frame fills canvas width
        canvas_scroll.bind(
            "<Configure>",
            lambda e: canvas_scroll.itemconfig(controls_window_id, width=e.width)
        )
        
        canvas_scroll.configure(yscrollcommand=scrollbar.set)
        
        # Pack canvas and scrollbar with RTL-aware sides
        canvas_side = self.get_pack_side("left")
        scrollbar_side = self.get_pack_side("right")
        canvas_scroll.pack(side=canvas_side, fill="both", expand=True)
        scrollbar.pack(side=scrollbar_side, fill="y")

        # Enable mousewheel scrolling on Linux/Windows
        def _on_mousewheel(event):
            canvas_scroll.yview_scroll(int(-1*(event.delta/120)), "units")

        canvas_scroll.bind_all("<MouseWheel>", _on_mousewheel)
        canvas_scroll.bind_all("<Button-4>", lambda e: canvas_scroll.yview_scroll(-1, "units"))
        canvas_scroll.bind_all("<Button-5>", lambda e: canvas_scroll.yview_scroll(1, "units"))

        self.add_controls_to_panel(scrollable_frame)
    
    def create_left_panel_grid(self, parent, column):
        """Create left control panel using grid layout"""
        left_panel = tk.Frame(parent, bg=COLORS['bg_medium'], width=350)
        
        # Determine padding based on column position
        padx = (0, 15) if column == 0 else (15, 0)
        
        print(f"🔍 [DEBUG] Creating left_panel_grid: column={column}, RTL={self.is_rtl}")
        
        # Use grid instead of pack
        left_panel.grid(row=0, column=column, sticky="ns", padx=padx)
        left_panel.grid_propagate(False)
        
        # Store reference
        self.left_panel = left_panel
        
        print(f"✅ [DEBUG] left_panel_grid placed in column {column}")
        
        # Scrollable frame
        canvas_scroll = tk.Canvas(left_panel, bg=COLORS['bg_medium'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(left_panel, orient="vertical", command=canvas_scroll.yview)
        self.scrollable_controls_frame = tk.Frame(canvas_scroll, bg=COLORS['bg_medium'])
        
        self.scrollable_controls_frame.bind(
            "<Configure>",
            lambda e: canvas_scroll.configure(scrollregion=canvas_scroll.bbox("all"))
        )
        
        self.controls_window_id = canvas_scroll.create_window((0, 0), window=self.scrollable_controls_frame, anchor="nw")
        
        # Ensure frame fills canvas width
        canvas_scroll.bind(
            "<Configure>",
            lambda e: canvas_scroll.itemconfig(self.controls_window_id, width=e.width)
        )
        
        canvas_scroll.configure(yscrollcommand=scrollbar.set)
        
        canvas_side = self.get_pack_side("left")
        scrollbar_side = self.get_pack_side("right")
        canvas_scroll.pack(side=canvas_side, fill="both", expand=True)
        scrollbar.pack(side=scrollbar_side, fill="y")
        
        def _on_mousewheel(event):
            canvas_scroll.yview_scroll(int(-1*(event.delta/120)), "units")
        
        canvas_scroll.bind_all("<MouseWheel>", _on_mousewheel)
        canvas_scroll.bind_all("<Button-4>", lambda e: canvas_scroll.yview_scroll(-1, "units"))
        canvas_scroll.bind_all("<Button-5>", lambda e: canvas_scroll.yview_scroll(1, "units"))
        
        # Add all control sections (same as create_left_panel)
        self.add_controls_to_panel(self.scrollable_controls_frame)
    
    def add_controls_to_panel(self, parent):
        """Add all control widgets to the scrollable frame"""
        # Controls title
        tk.Label(parent, textvariable=self.ui_strings["ui.controls.title"], 
                font=("Helvetica", 18, "bold"),
                bg=COLORS['bg_medium'], fg=COLORS['accent_cyan']).pack(pady=15)
        
        # Load button
        self.load_btn = self.create_button(parent, self.ui_strings["ui.controls.load_image"], 
                                           self.load_image, COLORS['bg_light'])
        self.load_btn.pack(pady=10, padx=20, fill="x")
        
        self.add_separator(parent)
        
        # Effect type section
        self.create_effect_section(parent)
        
        self.add_separator(parent)
        
        # Detection mode section
        self.create_detection_section(parent)
        
        self.add_separator(parent)
        
        # Effect parameters
        self.create_parameters_section(parent)
        
        self.add_separator(parent)
        
        # Action buttons
        self.create_action_buttons(parent)
        
        self.add_separator(parent)
        
        # EXIF Scrubbing section (Max feature)
        self.create_exif_section(parent)
        
        # Info
        tk.Label(parent, 
                textvariable=self.ui_strings["ui.controls.tip"],
                font=("Helvetica", 9, "italic"),
                bg=COLORS['bg_medium'], fg=COLORS['text_gray'],
                justify="center").pack(side="bottom", pady=20)
    
    def create_effect_section(self, parent):
        """Create effect type selection section"""
        
        tk.Label(parent, textvariable=self.ui_strings["ui.controls.effect_type"], 
                font=("Helvetica", 13, "bold"),
                bg=COLORS['bg_medium'], fg=COLORS['text_white']).pack(pady=(10, 5))
        
        effect_frame = tk.Frame(parent, bg=COLORS['bg_medium'])
        effect_frame.pack(pady=5, padx=20, fill="x")
        
        for i, (key, value) in enumerate(zip(self.effect_keys, ["blur", "pixelation", "black_bar", "gradient", "mosaic", "glass", "oil_paint"])):
            rb = self.create_radio(
                effect_frame,
                self.effect_strings[i],
                self.effect_type,
                value,
                command=self.on_effect_change,
                )
            rb.pack(anchor=self.get_text_anchor("w"), pady=3)
    
    def create_detection_section(self, parent):
        """Create detection mode section"""

        tk.Label(parent, textvariable=self.ui_strings["ui.controls.detection_mode"], 
                font=("Helvetica", 13, "bold"),
                bg=COLORS['bg_medium'], fg=COLORS['text_white']).pack(pady=(10, 5))

        mode_frame = tk.Frame(parent, bg=COLORS['bg_medium'])
        mode_frame.pack(pady=5, padx=20, fill="x")

        self.mode_frame = mode_frame

        rb = self.create_radio(
            mode_frame,
            self.ui_strings["ui.controls.target_text"],
            self.detection_mode,
            "target_text",
            command=self.on_detection_change,
            )
        rb.pack(anchor=self.get_text_anchor("w"), pady=3)

        # Create the Input Field
        self.text_input_frame = tk.Frame(mode_frame, bg=COLORS['bg_medium'])

        tk.Label(
            self.text_input_frame,
            textvariable=self.ui_strings["ui.controls.target_text"],
                font=("Helvetica", 10, "bold"),
                bg=COLORS['bg_medium'],
                fg=COLORS['text_white']).pack(pady=(10, 5), anchor=self.get_text_anchor("w"))

        self.word_entry = tk.Entry(
            self.text_input_frame,
            textvariable=self.target_word_var,
            bg=COLORS['bg_dark'],
            fg="white", insertbackground="white")
        self.word_entry.pack(fill="x", pady=5)
        
        # Set text direction for input field based on RTL state
        self.update_input_field_direction()

        for i, (key, value) in enumerate(zip(self.detection_keys, ["face", "eye", "body", "license_plate", "text", "manual", "full"])):
            rb = self.create_radio(
                mode_frame,
                self.detection_strings[i],
                self.detection_mode,
                value,
                command=self.on_detection_change,
                )
            rb.pack(anchor=self.get_text_anchor("w"), pady=3)
    
    def create_parameters_section(self, parent):
        """Create effect parameters section"""

        self.params_frame = tk.Frame(parent, bg=COLORS['bg_medium'])
        self.params_frame.pack(pady=10, padx=20, fill="x")
        
        self.blur_param = self.create_slider(self.params_frame, self.ui_strings["ui.controls.blur_strength"], 
                                             self.blur_strength, 
                                             BLUR_RANGE['min'], BLUR_RANGE['max'], 
                                             COLORS['accent_cyan'], resolution=2)
        
        self.pixel_param = self.create_slider(self.params_frame, self.ui_strings["ui.controls.pixel_size"], 
                                              self.pixel_size, 
                                              PIXEL_RANGE['min'], PIXEL_RANGE['max'], 
                                              COLORS['accent_pink'], resolution=1)
        
        self.opacity_param = self.create_slider(self.params_frame, self.ui_strings["ui.controls.opacity"], 
                                                self.opacity, 
                                                OPACITY_RANGE['min'], OPACITY_RANGE['max'], 
                                                COLORS['accent_green'], resolution=1)
        self.opacity_param.pack(fill="x", pady=5)
        
        self.update_parameter_visibility()
    
    def create_slider(self, parent, textvariable, variable, min_val, max_val, color, resolution=1):
        """Create a labeled slider"""
        frame = tk.Frame(parent, bg=COLORS['bg_medium'])
        
        tk.Label(frame, textvariable=textvariable, 
                font=("Helvetica", 11, "bold"),
                bg=COLORS['bg_medium'], fg=COLORS['text_white']).pack(pady=(5, 2))
        
        value_label = tk.Label(frame, textvariable=variable,
                              font=("Helvetica", 10),
                              bg=COLORS['bg_medium'], fg=color)
        value_label.pack()
        
        slider = tk.Scale(frame, from_=min_val, to=max_val, 
                         resolution=resolution,
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
        
        self.process_btn = self.create_button(parent, self.ui_strings["ui.controls.apply_effect"], 
                                              self.process_image, 
                                              COLORS['accent_red'],
                                              state="disabled")
        self.process_btn.pack(pady=15, padx=20, fill="x")
        
        undo_frame = tk.Frame(parent, bg=COLORS['bg_medium'])
        undo_frame.pack(pady=5, padx=20, fill="x")
        
        self.undo_btn = self.create_button(undo_frame, self.ui_strings["ui.controls.undo"], 
                                           self.undo, 
                                           COLORS['accent_orange'],
                                           state="disabled")
        self.undo_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        self.redo_btn = self.create_button(undo_frame, self.ui_strings["ui.controls.redo"], 
                                           self.redo, 
                                           COLORS['accent_orange'],
                                           state="disabled")
        self.redo_btn.pack(side="right", fill="x", expand=True, padx=(5, 0))
        
        self.clear_btn = self.create_button(parent, self.ui_strings["ui.controls.clear_selections"], 
                                            self.clear_regions, 
                                            COLORS['accent_purple'])
        self.clear_btn.pack(pady=5, padx=20, fill="x")
        
        self.save_btn = self.create_button(parent, self.ui_strings["ui.controls.save_result"], 
                                           self.save_image, 
                                           COLORS['accent_green'],
                                           state="disabled")
        self.save_btn.pack(pady=5, padx=20, fill="x")
        
        batch_btn = self.create_button(parent, self.ui_strings["ui.controls.batch_process"], 
                                       self.open_batch_window, 
                                       COLORS['bg_light'])
        batch_btn.pack(pady=5, padx=20, fill="x")
    
    def create_exif_section(self, parent):
        """Privacy section — EXIF Scrubbing + Metadata Spoofing (Max tier)."""
        is_max = self.license_manager.is_max_activated

        section_frame = tk.Frame(parent, bg=COLORS['bg_medium'])
        section_frame.pack(pady=10, padx=20, fill="x")
        self.exif_section_frame = section_frame

        # ── Section header ────────────────────────────────────────────────
        title_color = COLORS['accent_cyan'] if is_max else COLORS['text_gray']
        icon = "🛡️" if is_max else "🔒"
        tk.Label(
            section_frame,
            text=f"{icon} Privacy — Metadata",
            font=("Helvetica", 11, "bold"),
            bg=COLORS['bg_medium'],
            fg=title_color,
            anchor="w",
        ).pack(anchor="w", pady=(0, 6))

        # ── Block 1: Scrub EXIF ───────────────────────────────────────────
        scrub_row = tk.Frame(section_frame, bg=COLORS['bg_medium'])
        scrub_row.pack(fill="x")

        cb_scrub = tk.Checkbutton(
            scrub_row,
            text="Strip all EXIF on save",
            variable=self.scrub_exif,
            command=self._on_scrub_toggled,
            font=("Helvetica", 10),
            bg=COLORS['bg_medium'],
            fg=COLORS['text_white'] if is_max else COLORS['text_gray'],
            selectcolor=COLORS['bg_light'],
            activebackground=COLORS['bg_medium'],
            state="normal" if is_max else "disabled",
            bd=0,
            highlightthickness=0,
        )
        cb_scrub.pack(side="left", anchor="w")

        if not is_max:
            lbl = tk.Label(
                scrub_row,
                text="  ⭐ Max",
                font=("Helvetica", 9, "italic"),
                bg=COLORS['bg_medium'],
                fg=COLORS['accent_orange'],
                cursor="hand2",
            )
            lbl.pack(side="left")
            lbl.bind("<Button-1>", lambda _: self.show_activation_dialog())

        tk.Label(
            section_frame,
            text="Permanently removes GPS, camera & device tags.",
            font=("Helvetica", 8, "italic"),
            bg=COLORS['bg_medium'],
            fg=COLORS['text_gray'],
            wraplength=280,
            justify="left",
        ).pack(anchor="w", pady=(2, 8))



        # ── Divider ───────────────────────────────────────────────────────
        tk.Frame(section_frame, bg=COLORS['bg_light'], height=1).pack(fill="x", pady=4)

        # ── Block 2: Spoof Metadata ───────────────────────────────────────
        spoof_row = tk.Frame(section_frame, bg=COLORS['bg_medium'])
        spoof_row.pack(fill="x", pady=(6, 0))

        cb_spoof = tk.Checkbutton(
            spoof_row,
            text="Inject fake metadata on save",
            variable=self.spoof_metadata,
            command=self._on_spoof_toggled,
            font=("Helvetica", 10),
            bg=COLORS['bg_medium'],
            fg=COLORS['text_white'] if is_max else COLORS['text_gray'],
            selectcolor=COLORS['bg_light'],
            activebackground=COLORS['bg_medium'],
            state="normal" if is_max else "disabled",
            bd=0,
            highlightthickness=0,
        )
        cb_spoof.pack(side="left", anchor="w")

        if not is_max:
            lbl2 = tk.Label(
                spoof_row,
                text="  ⭐ Max",
                font=("Helvetica", 9, "italic"),
                bg=COLORS['bg_medium'],
                fg=COLORS['accent_orange'],
                cursor="hand2",
            )
            lbl2.pack(side="left")
            lbl2.bind("<Button-1>", lambda _: self.show_activation_dialog())

        # ── Profile picker (shown only when spoof is checked) ─────────────
        self.spoof_profile_frame = tk.Frame(section_frame, bg=COLORS['bg_medium'])
        # Note: packed/unpacked dynamically by _on_spoof_toggled

        profile_labels = {
            "ghost":  "👻 Ghost  — Nokia in Antarctica, year 2000",
            "troll":  "🌊 Troll  — Random ocean, vintage camera",
            "artist": "🎨 Artist — Hides GPS, keeps copyright",
        }
        for val, label in profile_labels.items():
            rb = tk.Radiobutton(
                self.spoof_profile_frame,
                text=label,
                variable=self.spoof_profile,
                value=val,
                font=("Helvetica", 9),
                bg=COLORS['bg_medium'],
                fg=COLORS['text_white'],
                selectcolor=COLORS['bg_dark'],
                activebackground=COLORS['bg_medium'],
                state="normal" if is_max else "disabled",
                bd=0,
                highlightthickness=0,
                command=self._on_profile_radio_changed,
            )
            rb.pack(anchor="w", pady=1)

        # ── Custom profile radio + button ─────────────────────────────
        custom_rb = tk.Radiobutton(
            self.spoof_profile_frame,
            text="⚙️  Custom  — per-field control",
            variable=self.spoof_profile,
            value="custom",
            font=("Helvetica", 9),
            bg=COLORS['bg_medium'],
            fg=COLORS['text_white'],
            selectcolor=COLORS['bg_dark'],
            activebackground=COLORS['bg_medium'],
            state="normal" if is_max else "disabled",
            bd=0,
            highlightthickness=0,
            command=self._on_profile_radio_changed,
        )
        custom_rb.pack(anchor="w", pady=1)

        self.customize_btn = tk.Button(
            self.spoof_profile_frame,
            text="⚙️  Open Metadata Editor…",
            command=self._open_metadata_customizer,
            font=("Helvetica", 9, "bold"),
            bg=COLORS['bg_dark'],
            fg=COLORS['accent_cyan'],
            activebackground=COLORS['bg_light'],
            relief="flat",
            cursor="hand2",
            padx=10, pady=4,
            state="normal" if is_max else "disabled",
        )
        self.customize_btn.pack_forget()   # hidden until "Custom" is picked

        tk.Label(
            section_frame,
            text="Replaces real metadata with plausible decoys.",
            font=("Helvetica", 8, "italic"),
            bg=COLORS['bg_medium'],
            fg=COLORS['text_gray'],
            wraplength=280,
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

        # Restore profile frame visibility if already checked
        if self.spoof_metadata.get() and is_max:
            self.spoof_profile_frame.pack(fill="x", padx=10, pady=(4, 0))

    def _on_scrub_toggled(self):
        """Called when scrub checkbox changes. Scrub and spoof are mutually exclusive."""
        if not self.license_manager.is_max_activated:
            self.scrub_exif.set(False)
            self.show_activation_dialog()
            return

        if self.scrub_exif.get():
            # Scrub ON → force spoof OFF
            self.spoof_metadata.set(False)
            self._hide_spoof_profile_frame()
            self.status_label.config(text="EXIF scrubbing: ON")
        else:
            self.status_label.config(text="EXIF scrubbing: OFF")

    def _on_spoof_toggled(self):
        """Called when spoof checkbox changes. Scrub and spoof are mutually exclusive."""
        if not self.license_manager.is_max_activated:
            self.spoof_metadata.set(False)
            self.show_activation_dialog()
            return

        if self.spoof_metadata.get():
            # Spoof ON → force scrub OFF, show profile picker
            self.scrub_exif.set(False)
            self._show_spoof_profile_frame()
            self.status_label.config(text="Metadata spoofing: ON")
        else:
            self._hide_spoof_profile_frame()
            self.status_label.config(text="Metadata spoofing: OFF")

    def _show_spoof_profile_frame(self):
        if hasattr(self, 'spoof_profile_frame'):
            self.spoof_profile_frame.pack(fill="x", padx=10, pady=(4, 0))

    def _hide_spoof_profile_frame(self):
        if hasattr(self, 'spoof_profile_frame'):
            self.spoof_profile_frame.pack_forget()

    def _on_profile_radio_changed(self):
        """Show/hide the 'Open Metadata Editor' button based on selected profile."""
        if hasattr(self, 'customize_btn'):
            if self.spoof_profile.get() == "custom":
                self.customize_btn.pack(anchor="w", pady=(4, 0), padx=4)
            else:
                self.customize_btn.pack_forget()

    def _open_metadata_customizer(self):
        """Open the per-field metadata editor dialog, pre-filled with current image EXIF."""
        current_exif = {}
        if hasattr(self, 'image_path') and self.image_path:
            try:
                current_exif = read_exif_fields(self.image_path)
            except Exception as e:
                print(f"Could not read EXIF for pre-fill: {e}")

        dlg = MetadataCustomizerDialog(self.root, current_exif=current_exif)

        if dlg.result is not None:
            self.custom_field_actions = dlg.result
            actions = [f"{k}:{v if isinstance(v, str) else 'custom'}"
                       for k, v in dlg.result.items()]
            self.status_label.config(
                text="Custom metadata: " + " | ".join(actions[:4]) +
                     (" …" if len(actions) > 4 else "")
            )
        else:
            # User cancelled — revert to troll if no actions were saved yet
            if self.spoof_profile.get() == "custom" and not self.custom_field_actions:
                self.spoof_profile.set("troll")
                if hasattr(self, 'customize_btn'):
                    self.customize_btn.pack_forget()


    def create_right_panel(self, parent):
        """Create right image display panel"""
        print(f"🔍 [DEBUG] Creating right_panel: pack_side={self.get_pack_side('right')}, RTL={self.is_rtl}")
        
        right_panel = tk.Frame(parent, bg=COLORS['bg_medium'])
        right_panel.pack(side=self.get_pack_side("right"), fill="both", expand=True)
        
        # Store reference
        self.right_panel = right_panel
        
        print(f"✅ [DEBUG] right_panel packed")
        
        # Toolbar
        toolbar = tk.Frame(right_panel, bg=COLORS['bg_light'], height=50)
        toolbar.pack(fill="x", padx=10, pady=10)
        toolbar.pack_propagate(False)
        
        # Toolbar buttons (using separate variable names to avoid conflicts)
        side = self.get_pack_side("left")
        self.toolbar_load_btn = self.create_small_button(toolbar, textvariable=self.ui_strings["ui.buttons.load"], command=self.load_image)
        self.toolbar_load_btn.pack(side=side, padx=5)
        
        self.toolbar_process_btn = self.create_small_button(toolbar, textvariable=self.ui_strings["ui.buttons.apply"], command=self.process_image)
        self.toolbar_process_btn.pack(side=side, padx=5)
        self.toolbar_process_btn.config(state="disabled")
        
        self.toolbar_save_btn = self.create_small_button(toolbar, textvariable=self.ui_strings["ui.controls.save_result"], command=self.save_image)
        self.toolbar_save_btn.pack(side=side, padx=5)
        self.toolbar_save_btn.config(state="disabled")
        
        self.toolbar_clear_btn = self.create_small_button(toolbar, textvariable=self.ui_strings["ui.buttons.reset"], command=self.clear_regions)
        self.toolbar_clear_btn.pack(side=side, padx=5)
        
        self.toolbar_undo_btn = self.create_small_button(toolbar, textvariable=self.ui_strings["ui.controls.undo"], command=self.undo)
        self.toolbar_undo_btn.pack(side=side, padx=5)
        
        self.toolbar_redo_btn = self.create_small_button(toolbar, textvariable=self.ui_strings["ui.controls.redo"], command=self.redo)
        self.toolbar_redo_btn.pack(side=side, padx=5)
        
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
        self.canvas.bind("<Configure>", self.on_canvas_resize)
    
    def create_right_panel_grid(self, parent, column):
        """Create right image display panel using grid layout"""
        print(f"🔍 [DEBUG] Creating right_panel_grid: column={column}, RTL={self.is_rtl}")
        
        right_panel = tk.Frame(parent, bg=COLORS['bg_medium'])
        right_panel.grid(row=0, column=column, sticky="nsew")
        
        # Store reference
        self.right_panel = right_panel
        
        print(f"✅ [DEBUG] right_panel_grid placed in column {column}")
        
        # Toolbar
        toolbar = tk.Frame(right_panel, bg=COLORS['bg_light'], height=50)
        toolbar.pack(fill="x", padx=10, pady=10)
        toolbar.pack_propagate(False)
        
        # Toolbar buttons (using separate variable names to avoid conflicts)
        self.toolbar_load_btn = self.create_small_button(toolbar, textvariable=self.ui_strings["ui.buttons.load"], command=self.load_image)
        self.toolbar_load_btn.pack(side="left", padx=5)
        
        self.toolbar_process_btn = self.create_small_button(toolbar, textvariable=self.ui_strings["ui.buttons.apply"], command=self.process_image)
        self.toolbar_process_btn.pack(side="left", padx=5)
        self.toolbar_process_btn.config(state="disabled")
        
        self.toolbar_save_btn = self.create_small_button(toolbar, textvariable=self.ui_strings["ui.controls.save_result"], command=self.save_image)
        self.toolbar_save_btn.pack(side="left", padx=5)
        self.toolbar_save_btn.config(state="disabled")
        
        self.toolbar_clear_btn = self.create_small_button(toolbar, textvariable=self.ui_strings["ui.buttons.reset"], command=self.clear_regions)
        self.toolbar_clear_btn.pack(side="left", padx=5)
        
        self.toolbar_undo_btn = self.create_small_button(toolbar, textvariable=self.ui_strings["ui.controls.undo"], command=self.undo)
        self.toolbar_undo_btn.pack(side="left", padx=5)
        
        self.toolbar_redo_btn = self.create_small_button(toolbar, textvariable=self.ui_strings["ui.controls.redo"], command=self.redo)
        self.toolbar_redo_btn.pack(side="left", padx=5)
        
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
        self.canvas.bind("<Configure>", self.on_canvas_resize)
    
    
    def create_status_bar(self):
        """Create status bar — placed in root grid row 2 (fixed height)."""

        _ = self.locale_manager.get

        status_bar = tk.Frame(self.root, bg=COLORS['bg_medium'], height=35)
        status_bar.grid_propagate(False)   # keep fixed height in grid
        # Grid row 2 = always visible, weight=0 guarantees fixed height
        status_bar.grid(row=2, column=0, sticky="ew")
        self.status_bar = status_bar

        self.status_label = tk.Label(status_bar, text=_("ui.status.ready"),
                                     font=("Helvetica", 10),
                                     bg=COLORS['bg_medium'], fg=COLORS['text_gray'],
                                     anchor=self.get_text_anchor("w"),
                                     justify=self.get_text_justify("left"))
        self.status_label.pack(side=self.get_pack_side("left"), padx=20, pady=8)

        # Update ready button (hidden by default)
        self.update_btn = tk.Button(status_bar,
                                  text="⬇️ Update Ready (Restart)",
                                  command=self.apply_update,
                                  bg=COLORS['accent_green'],
                                  fg="white",
                                  font=("Helvetica", 9, "bold"),
                                  relief="flat",
                                  cursor="hand2",
                                  padx=10, pady=4)
        # Don't pack it yet - will be shown when update is ready

        self.info_label = tk.Label(status_bar, text="",
                                   font=("Helvetica", 9),
                                   bg=COLORS['bg_medium'], fg=COLORS['text_gray'],
                                   anchor=self.get_text_anchor("e"),
                                   justify=self.get_text_justify("right"))
        self.info_label.pack(side=self.get_pack_side("right"), padx=20, pady=8)
    
    # Helper methods
    def create_button(self, parent, textvariable, command, bg_color, state="normal"):
        return tk.Button(parent, textvariable=textvariable,
                        command=command,
                        font=("Helvetica", 11, "bold"),
                        bg=bg_color, fg=COLORS['text_white'],
                        activebackground=bg_color,
                        cursor="hand2",
                        relief="flat",
                        padx=15, pady=10,
                        state=state)
    
    def create_small_button(self, parent, text=None, textvariable=None, command=None):
        btn = tk.Button(parent,
                        command=command,
                        font=("Helvetica", 9),
                        bg=COLORS['bg_dark'], fg=COLORS['text_white'],
                        activebackground=COLORS['bg_light'],
                        cursor="hand2",
                        relief="flat",
                        padx=10, pady=5)
        if textvariable:
            btn.config(textvariable=textvariable)
        elif text:
            btn.config(text=text)
        return btn
    
    def add_separator(self, parent):
        ttk.Separator(parent, orient="horizontal").pack(fill="x", pady=12, padx=20)
    
    def bind_shortcuts(self):
        self.root.bind(SHORTCUTS['load'], lambda e: self.load_image())
        self.root.bind(SHORTCUTS['save'], lambda e: self.save_image())
        self.root.bind(SHORTCUTS['undo'], lambda e: self.undo())
        self.root.bind(SHORTCUTS['redo'], lambda e: self.redo())
        self.root.bind(SHORTCUTS['process'], lambda e: self.process_image())
        self.root.bind(SHORTCUTS['clear'], lambda e: self.clear_regions())
        self.root.bind(SHORTCUTS['batch'], lambda e: self.open_batch_window())
    
    # RTL Layout Helper Methods
    def get_pack_side(self, default_side="left"):
        """Return appropriate pack side based on RTL state."""
        if not self.is_rtl:
            return default_side
        # Flip sides for RTL
        side_map = {"left": "right", "right": "left", "top": "top", "bottom": "bottom"}
        return side_map.get(default_side, default_side)
    
    def get_text_anchor(self, default="w"):
        """Return appropriate text anchor based on RTL state."""
        if not self.is_rtl:
            return default
        # Flip anchors for RTL
        anchor_map = {
            "w": "e", "e": "w",
            "nw": "ne", "ne": "nw",
            "sw": "se", "se": "sw",
            "n": "n", "s": "s", "center": "center"
        }
        return anchor_map.get(default, default)
    
    def get_text_justify(self, default="left"):
        """Return appropriate text justification based on RTL state."""
        if not self.is_rtl:
            return default
        # Flip justification for RTL
        justify_map = {"left": "right", "right": "left", "center": "center"}
        return justify_map.get(default, default)
    
    # Core functionality
    def load_image(self):
        from core.image_picker import ImagePicker
        picker = ImagePicker(self.root)
        file_path = picker.open()

        if not file_path: 
            return
        
        # Try to load the image
        try:
            self.image_path = file_path
            # Support non-Latin/Arabic characters in file path (cross-platform)
            loaded_image = cv2.imdecode(np.fromfile(file_path, dtype=np.uint8), cv2.IMREAD_COLOR)
            
            # CRITICAL: Check if image loaded successfully
            if loaded_image is None:
                messagebox.showerror("Error", 
                    f"Could not load image!\n\n"
                    f"File: {os.path.basename(file_path)}\n\n"
                    "Possible reasons:\n"
                    "• File is corrupted\n"
                    "• Unsupported format\n"
                    "• File path contains special characters"
                )
                self.original_image = None
                self.processed_image = None
                return
            
            # CRITICAL: Check if image is empty
            if loaded_image.size == 0:
                messagebox.showerror("Error", "Loaded image is empty!")
                self.original_image = None
                self.processed_image = None
                return
            
            # Capture raw EXIF bytes via Pillow (before cv2 strips them)
            self.original_exif_bytes = None
            try:
                pil_img = Image.open(file_path)
                if 'exif' in pil_img.info:
                    self.original_exif_bytes = pil_img.info['exif']
            except Exception:
                self.original_exif_bytes = None
            
            # Set images only if loading succeeded
            self.original_image = loaded_image
            self.processed_image = self.original_image.copy()
            self.drawing_regions = []
            self.history_manager.clear()
            
            self.display_image(self.original_image)
            self.process_btn.config(state="normal")
            
            info = self.image_utils.get_image_info(self.original_image)
            self.status_label.config(text=f"Loaded: {os.path.basename(file_path)}")
            self.info_label.config(text=f"{info['width']}x{info['height']} | {info['size_kb']} KB")
            self.restore_button_states()
            
        except Exception as e:
            messagebox.showerror("Loading Error",
                f"Failed to load image:\n{str(e)}"
            )
            self.original_image = None
            self.processed_image = None
            self.status_label.config(text="Failed to load image")
    
    def display_image(self, cv_image):
        """Display image on canvas with proper validation and error handling"""
        
        # Check if image exists
        if cv_image is None:
            print("ERROR: cv_image is None")
            return
        
        # Check if image is empty
        if cv_image.size == 0:
            print("ERROR: cv_image is None")
            return
        
        # Convert to RGB
        try:
            rgb_image = cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB)
        except cv2.error as e:
            print(f"ERROR: Could not convert to RGB: {e}")
            messagebox.showerror("Display Error", f"Could not convert image: {e}")
            return
        
        #  Force canvas to update its size
        self.canvas.update_idletasks()
        
        #  Get actual canvas dimensions
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        
        #  Handle initial canvas size (before first update)
        if canvas_width <= 1 or canvas_height <= 1:
            # Force canvas to update
            self.root.update_idletasks()
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            
            # If still too small, use default values
            if canvas_width <= 1 or canvas_height <= 1:
                canvas_width = 900
                canvas_height = 700
                print(f"Using default canvas size: {canvas_width}x{canvas_height}")
        
        # Resize image to fit canvas
        try:
            resized, scale = self.image_utils.resize_for_display(
                rgb_image, canvas_width, canvas_height
            )
            print(f"Image resized to: {resized.shape[1]}x{resized.shape[0]}, scale: {scale}")
        except Exception as e:
            print(f"ERROR: Could not resize image: {e}")
            messagebox.showerror("Display Error", f"Could not resize: {e}")
            return
        
        # Convert to PIL Image
        try:
            pil_image = Image.fromarray(resized)
            self.photo = ImageTk.PhotoImage(pil_image)
        except Exception as e:
            print(f"ERROR: Could not create PhotoImage: {e}")
            messagebox.showerror("Display Error", f"Could not create image: {e}")
            return
        
        # Clear canvas first
        self.canvas.delete("all")
        
        # Calculate centered position
        new_w, new_h = resized.shape[1], resized.shape[0]
        x = (canvas_width - new_w) // 2
        y = (canvas_height - new_h) // 2
        
        # Ensure position is valid
        x = max(0, x)
        y = max(0, y)

        print(f"Placing image at position: ({x}, {y})")  
        
        # Create image on canvas
        try:
            self.canvas.create_image(x, y, anchor="nw", image=self.photo, tags="main_image")
            print("✅ Image displayed successfully")
        except Exception as e:
            print(f"ERROR: Could not display image on canvas: {e}")
            messagebox.showerror("Display Error", f"Could not display: {e}")
            return
        
        # Store display parameters
        self.display_scale = scale
        self.display_offset = (x, y)
        
        # Force canvas update
        self.canvas.update_idletasks()
    
    def process_image(self):
        if self.original_image is None: return
        
        if self.processed_image is not None:
            self.history_manager.save_state(self.processed_image)
        
        mode = self.detection_mode.get()
        effect = self.effect_type.get()
        self.processed_image = self.processed_image.copy()
        
        try:
            is_pro = self.license_manager.is_max_activated
            regions      = []   # list of (x,y,w,h) — FREE
            pro_regions  = []   # list of dicts     — PRO AI

            if mode == "face":
                if is_pro:
                    pro_regions = self.detection_engine.detect_faces_pro(self.processed_image)
                    if not pro_regions:  # fallback if mediapipe not installed
                        regions = self.detection_engine.detect_faces(self.processed_image)
                else:
                    regions = self.detection_engine.detect_faces(self.processed_image)

            elif mode == "eye":
                if is_pro:
                    pro_regions = self.detection_engine.detect_eyes_pro(self.processed_image)
                    if not pro_regions:
                        regions = self.detection_engine.detect_eyes(self.processed_image)
                else:
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

            # ── Apply FREE rectangle regions ─────────────────────────────────
            for (x, y, w, h) in regions:
                self.apply_effect_to_region(x, y, w, h, effect)

            # ── Apply PRO AI polygon / rotated-rect regions ───────────────────
            effect_kwargs = dict(
                strength   = self.blur_strength.get(),
                pixel_size = self.pixel_size.get(),
                opacity    = self.opacity.get(),
            )
            for det in pro_regions:
                if det["type"] == "polygon":
                    self.processed_image = self.image_processor.apply_effect_to_polygon(
                        self.processed_image, det["points"], effect, **effect_kwargs
                    )
                elif det["type"] == "rotated_rect":
                    self.processed_image = self.image_processor.apply_effect_rotated(
                        self.processed_image,
                        det["center"], det["size"], det["angle"],
                        effect, **effect_kwargs
                    )

            total = len(regions) + len(pro_regions)
            badge = " ✨ AI" if pro_regions else ""
            self.display_image(self.processed_image)
            self.save_btn.config(state="normal")
            self.status_label.config(text=f"Processed {total} region(s){badge}")
            self.update_buttons()

        except Exception as e:
            messagebox.showerror("Error", f"Processing failed: {str(e)}")
    
    def apply_effect_to_region(self, x, y, w, h, effect):
        """Apply effect to region with comprehensive error handling"""
        if self.original_image is None: return

        # Use the new static method from the MVC model
        try:
            self.processed_image = ImageProcessor.apply_effect_to_region(
                self.processed_image, 
                x, y, w, h, 
                effect_type=effect,
                strength=self.blur_strength.get(),
                pixel_size=self.pixel_size.get(),
                opacity=self.opacity.get()
            )
        except Exception as e:
            print(f"Error applying effect: {e}")
    
    def _ask_save_filename(self):
        """Cross-platform native-looking save dialog."""
        import sys, subprocess, shutil
        from tkinter import filedialog
        if sys.platform.startswith('linux') and shutil.which('zenity'):
            try:
                # Use zenity for a native GTK dialog on Linux
                cmd = [
                    'zenity', '--file-selection', '--save', 
                    '--confirm-overwrite',
                    '--title=Save Processed Image',
                    '--file-filter=JPEG Images (High Quality) | *.jpg *.jpeg',
                    '--file-filter=PNG Images (Lossless) | *.png',
                    '--file-filter=All Files | *'
                ]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    path = result.stdout.strip()
                    if not path.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp', '.tiff')):
                        path += '.jpg'
                    return path
                return ""
            except Exception as e:
                print(f"Zenity failed, falling back to tkinter: {e}")
        
        # Fallback to tkinter
        return filedialog.asksaveasfilename(defaultextension=".jpg", filetypes=SAVE_FORMATS)

    def save_image(self):
        if self.processed_image is None: return
        file_path = self._ask_save_filename()
        if not file_path:
            return
        # ── EXIF / metadata handling ──────────────────────────────────────────
        # Priority:  scrub  >  spoof  >  restore original
        is_max       = self.license_manager.is_max_activated
        should_scrub = is_max and self.scrub_exif.get()
        should_spoof = is_max and self.spoof_metadata.get() and not should_scrub

        # ── 1. Metadata Report Dialog (Confirmation) ──────────────────────────
        report_mode = "restore"
        report_profile = None
        report_actions = None

        if should_scrub:
            report_mode = "scrub"
        elif should_spoof:
            report_mode = "spoof"
            report_profile = self.spoof_profile.get()
            if report_profile == "custom":
                report_actions = self.custom_field_actions or {}

        report_dlg = MetadataReportDialog(
            self.root,
            mode=report_mode,
            profile=report_profile,
            field_actions=report_actions,
            filename=os.path.basename(file_path)
        )

        if not report_dlg.confirmed:
            return

        # ── 2. Write the processed image (cv2 strips EXIF by default) ─────────
        # Support non-Latin/Arabic characters in file path (cross-platform)
        is_success, im_buf_arr = cv2.imencode(os.path.splitext(file_path)[1], self.processed_image)
        if is_success:
            im_buf_arr.tofile(file_path)
        else:
            cv2.imwrite(file_path, self.processed_image)

        if should_scrub:
            # File already clean (cv2.imwrite strips EXIF) — nothing to do.
            pass

        elif should_spoof:
            ext = os.path.splitext(file_path)[1].lower()
            profile = self.spoof_profile.get()

            if profile == "custom" and self.custom_field_actions:
                # Per-field custom control via MetadataCustomizerDialog
                if ext in ('.jpg', '.jpeg', '.png'):
                    try:
                        _spoof_custom(
                            file_path,
                            file_path,
                            field_actions=self.custom_field_actions,
                        )
                    except Exception as e:
                        print(f"Metadata custom warning: {e}")
                else:
                    if self.original_exif_bytes:
                        try:
                            pil_img = Image.open(file_path)
                            pil_img.save(file_path, exif=self.original_exif_bytes)
                        except Exception as e:
                            print(f"EXIF restore warning: {e}")

            elif ext in ('.jpg', '.jpeg', '.png'):
                # Standard named profile (ghost / troll / artist)
                try:
                    _spoof_metadata(
                        file_path,
                        file_path,
                        profile=profile,
                    )
                except Exception as e:
                    print(f"Metadata spoof warning: {e}")
            else:
                # Unsupported format — restore original silently
                if self.original_exif_bytes:
                    try:
                        pil_img = Image.open(file_path)
                        pil_img.save(file_path, exif=self.original_exif_bytes)
                    except Exception as e:
                        print(f"EXIF restore warning: {e}")

        else:
            # Default: put original EXIF back so metadata isn't silently lost.
            if self.original_exif_bytes:
                try:
                    pil_img = Image.open(file_path)
                    pil_img.save(file_path, exif=self.original_exif_bytes)
                except Exception as e:
                    print(f"EXIF restore warning: {e}")
        # ─────────────────────────────────────────────────────────────────────
        
        messagebox.showinfo("Success", "Image saved successfully!")
        self.status_label.config(text=f"Saved: {os.path.basename(file_path)}")
    
    def save_comparison(self):
        if self.original_image is None or self.processed_image is None: return
        file_path = self._ask_save_filename()
        if file_path:
            ExportManager.export_comparison(self.original_image, self.processed_image, file_path)
            messagebox.showinfo("Success", "Comparison saved!")

    def update_parameter_visibility(self):
        self.blur_param.pack_forget()
        self.pixel_param.pack_forget()
        self.text_input_frame.pack_forget()

        if self.detection_mode.get() == "target_text":
            self.text_input_frame.pack(anchor=self.get_text_anchor("w"), padx=20, pady=5)

        effect = self.effect_type.get()
        if effect in ["blur", "glass"]:
            self.blur_param.pack(fill="x", pady=5)
        elif effect == "pixelation":
            self.pixel_param.pack(fill="x", pady=5)


    def on_mouse_down(self, event):
        if self.detection_mode.get() == "manual" and self.original_image is not None:
            self.drawing = True
            self.start_x = event.x
            self.start_y = event.y
    
    def on_mouse_drag(self, event):
        if self.drawing:
            self.canvas.delete("current_rect")
            self.current_rect = self.canvas.create_rectangle(
                self.start_x, self.start_y, event.x, event.y,
                outline=COLORS['accent_cyan'], width=3, tags="current_rect"
            )
    
    def on_mouse_up(self, event):
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
        if self.original_image is None: return
        scale_multiplier = 1.0
        if event.num == 4 or event.delta > 0: scale_multiplier = 1.1
        elif event.num == 5 or event.delta < 0: scale_multiplier = 0.9
        
        new_scale = self.display_scale * scale_multiplier
        if 0.1 < new_scale < 5.0:
            self.display_scale = new_scale
            if self.processed_image is not None: self.display_image(self.processed_image)
            else: self.display_image(self.original_image)
            self.status_label.config(text=f"Zoom: {int(self.display_scale * 100)}%")

    def on_canvas_resize(self, event=None):
        """Handle canvas resize events"""
        if self.processed_image is not None:
            # Redisplay the current image when canvas is resized
            self.display_image(self.processed_image)
        elif self.original_image is not None:
            self.display_image(self.original_image)

    def undo(self):
        prev_image = self.history_manager.undo()
        if prev_image is not None:
            self.history_manager.add_to_redo(self.processed_image)
            self.processed_image = prev_image
            self.display_image(self.processed_image)
            self.status_label.config(text="Undo successful")
            self.update_buttons()
    
    def redo(self):
        next_image = self.history_manager.redo()
        if next_image is not None:
            self.history_manager.save_state(self.processed_image)
            self.processed_image = next_image
            self.display_image(self.processed_image)
            self.status_label.config(text="Redo successful")
            self.update_buttons()
    
    def clear_regions(self):
        self.drawing_regions = []
        self.canvas.delete("current_rect")
        if self.original_image is not None: self.display_image(self.processed_image)
        self.status_label.config(text="Cleared all selections")
    
    def reset_image(self):
        if self.original_image is not None:
            self.processed_image = self.original_image.copy()
            self.display_image(self.processed_image)
            self.drawing_regions = []
            self.history_manager.clear()
            self.status_label.config(text="Image reset to original")
            self.update_buttons()
    
    def switch_view(self, view_type):
        if view_type == 'original' and self.original_image is not None:
            self.display_image(self.original_image)
            self.status_label.config(text="Viewing Original Image")
        elif view_type == 'processed' and self.processed_image is not None:
            self.display_image(self.processed_image)
            self.status_label.config(text="Viewing Processed Image")
        elif view_type == 'compare':
            if self.original_image is None and self.processed_image is None: return
            h1, w1 = self.original_image.shape[:2]
            h2, w2 = self.processed_image.shape[:2]
            proc_img_resized = self.processed_image
            if (h1, w1) != (h2, w2):
                proc_img_resized = cv2.resize(self.processed_image, (w1, h1))
            divider = np.ones((h1, 10, 3), dtype=np.uint8) * 255
            comparison_image = np.hstack((self.original_image, divider, proc_img_resized))
            self.display_image(comparison_image)
            self.status_label.config(text="Viewing Comparison Image")
            
    def restore_button_states(self):
        """Restore button states for both left panel AND toolbar buttons"""
        try:
            # State for process/clear buttons
            state = "normal" if self.original_image is not None else "disabled"
            
            # Left panel buttons
            if hasattr(self, 'process_btn') and self.process_btn: 
                self.process_btn.config(state=state)
            if hasattr(self, 'clear_btn') and self.clear_btn: 
                self.clear_btn.config(state=state)
            
            # Toolbar buttons
            if hasattr(self, 'toolbar_process_btn') and self.toolbar_process_btn: 
                self.toolbar_process_btn.config(state=state)
            
            # State for save button
            save_state = "normal" if self.processed_image is not None else "disabled"
            
            # Left panel save button
            if hasattr(self, 'save_btn') and self.save_btn: 
                self.save_btn.config(state=save_state)
            
            # Toolbar save button
            if hasattr(self, 'toolbar_save_btn') and self.toolbar_save_btn: 
                self.toolbar_save_btn.config(state=save_state)
            
            self.update_buttons()
            
        except Exception as e:
            print(f"⚠️ Error restoring states: {e}")

    def update_buttons(self):
        # Update left panel buttons
        if self.history_manager.can_undo(): 
            if hasattr(self, 'undo_btn') and self.undo_btn: self.undo_btn.config(state="normal")
        else: 
            if hasattr(self, 'undo_btn') and self.undo_btn: self.undo_btn.config(state="disabled")
        
        if self.history_manager.can_redo(): 
            if hasattr(self, 'redo_btn') and self.redo_btn: self.redo_btn.config(state="normal")
        else: 
            if hasattr(self, 'redo_btn') and self.redo_btn: self.redo_btn.config(state="disabled")
        
        # Update toolbar buttons
        if self.history_manager.can_undo(): 
            if hasattr(self, 'toolbar_undo_btn') and self.toolbar_undo_btn: self.toolbar_undo_btn.config(state="normal")
        else: 
            if hasattr(self, 'toolbar_undo_btn') and self.toolbar_undo_btn: self.toolbar_undo_btn.config(state="disabled")
        
        if self.history_manager.can_redo(): 
            if hasattr(self, 'toolbar_redo_btn') and self.toolbar_redo_btn: self.toolbar_redo_btn.config(state="normal")
        else: 
            if hasattr(self, 'toolbar_redo_btn') and self.toolbar_redo_btn: self.toolbar_redo_btn.config(state="disabled")
    
    def save_preset(self):
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
        presets = self.preset_manager.get_all_presets()
        if not presets:
            messagebox.showinfo("Info", "No presets available")
            return
        # Implementation for preset loading dialog would go here
    
    def manage_presets(self):
        pass
    
    def open_batch_window(self):
        BatchWindow(self.root, self.batch_processor, self.license_manager)
        
    def show_activation_dialog(self):
        """Start the seamless local auth flow and open the browser."""
        
        # Create a "Waiting for browser..." dialog
        dialog = tk.Toplevel(self.root)
        dialog.title("Activating DotScramble Pro")
        dialog.geometry("400x200")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center the dialog
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 400) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 200) // 2
        dialog.geometry(f"+{x}+{y}")
        
        ttk.Label(dialog, text="Waiting for authentication...", font=("Arial", 12, "bold")).pack(pady=(30, 10))
        ttk.Label(dialog, text="Please complete the activation in your browser.\nThis window will close automatically.", justify=tk.CENTER).pack(pady=10)
        
        progress = ttk.Progressbar(dialog, mode="indeterminate", length=250)
        progress.pack(pady=10)
        progress.start()
        
        # Fallback button if browser flow fails
        def fallback_to_manual():
            if hasattr(self, 'auth_manager') and self.auth_manager:
                self.auth_manager.stop()
            dialog.destroy()
            self._show_manual_activation_dialog()
            
        ttk.Button(dialog, text="Enter Key Manually", command=fallback_to_manual).pack(pady=(10, 0))
        
        # Setup the callback
        def on_auth_success(key):
            # This is called from the background thread, so we must schedule the UI updates on the main thread
            self.root.after(0, lambda: self._handle_auth_callback(dialog, key))
            
        # Start the local server
        self.auth_manager = LocalAuthManager(callback=on_auth_success)
        try:
            port, state = self.auth_manager.start()
            
            # Handle dialog close manually to clean up server
            def on_close():
                self.auth_manager.stop()
                dialog.destroy()
            dialog.protocol("WM_DELETE_WINDOW", on_close)
            
            # Open the browser
            auth_url = f"{AUTH_BASE_URL}/en/dashboard/dotscramble/auth?port={port}&state={state}"
            import webbrowser
            webbrowser.open(auth_url)
            
        except Exception as e:
            logger.error(f"Failed to start local auth server: {e}")
            fallback_to_manual()

    def _handle_auth_callback(self, dialog, key):
        """Called on the main thread when the local server receives a key."""
        dialog.destroy()
        self.status_label.config(text="Activating...")
        self.root.update()
        
        success, message = self.license_manager.verify_and_activate(key)
        if success:
            messagebox.showinfo("Success", message, parent=self.root)
            self.update_window_title()
            self.create_menu_bar()
            if hasattr(self, 'exif_section_frame') and self.exif_section_frame.winfo_exists():
                parent = self.exif_section_frame.master
                self.exif_section_frame.destroy()
                self.create_exif_section(parent)
            self.status_label.config(text="DotScramble Pro Activated!")
        else:
            messagebox.showerror("Activation Failed", message, parent=self.root)
            self.status_label.config(text="Activation failed.")

    def _show_manual_activation_dialog(self):
        """The old manual copy-paste flow as a fallback."""
        key = simpledialog.askstring(
            "Activate Pro",
            "Enter your DotSuite API Key to unlock DotScramble Pro:",
            parent=self.root
        )
        if key:
            self.status_label.config(text="Activating...")
            self.root.update()
            
            success, message = self.license_manager.verify_and_activate(key)
            if success:
                messagebox.showinfo("Success", message, parent=self.root)
                self.update_window_title()
                # Reload menu bar to show "PRO Activated"
                self.create_menu_bar()
                # Refresh the EXIF section so the checkbox becomes active immediately
                if hasattr(self, 'exif_section_frame') and self.exif_section_frame.winfo_exists():
                    parent = self.exif_section_frame.master
                    self.exif_section_frame.destroy()
                    self.create_exif_section(parent)
                self.status_label.config(text="DotScramble Pro Activated!")
            else:
                messagebox.showerror("Activation Failed", message, parent=self.root)
                self.status_label.config(text="Activation failed.")
    
    def show_donate(self):
        import webbrowser
        donate_window = tk.Toplevel(self.root)
        donate_window.title("Support the Developer")
        donate_window.geometry("400x300")
        donate_window.configure(bg=COLORS['bg_medium'])
        donate_window.resizable(False, False)
        donate_window.transient(self.root)
        donate_window.grab_set()
        
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 200
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 150
        donate_window.geometry(f"+{x}+{y}")

        tk.Label(donate_window, text="Support the Developer",
                font=("Helvetica", 16, "bold"), bg=COLORS['bg_medium'], fg=COLORS['accent_cyan']).pack(pady=15)
        tk.Label(donate_window, text="Thank you for considering supporting this project!\nChoose your preferred donation platform:",
                font=("Helvetica", 10), bg=COLORS['bg_medium'], fg=COLORS['text_white'], justify="center").pack(pady=10)

        button_frame = tk.Frame(donate_window, bg=COLORS['bg_medium'])
        button_frame.pack(pady=10, padx=20, fill="x")

        tk.Button(button_frame, text="💳 PayPal", command=lambda: self.open_url("https://paypal.me/freerave1"),
                  font=("Helvetica", 11, "bold"), bg="#0070ba", fg="white").pack(fill="x", pady=3)
        tk.Button(button_frame, text="☕ Buy Me a Coffee", command=lambda: self.open_url("https://buymeacoffee.com/freerave"),
                  font=("Helvetica", 11, "bold"), bg="#ffdd00", fg="black").pack(fill="x", pady=3)
        tk.Button(button_frame, text="🎨 Ko-fi", command=lambda: self.open_url("https://ko-fi.com/freerave"),
                  font=("Helvetica", 11, "bold"), bg="#ff5e5b", fg="white").pack(fill="x", pady=3)
        tk.Button(button_frame, text="⭐ GitHub Sponsors", command=lambda: self.open_url("https://github.com/sponsors/kareem2099"),
                  font=("Helvetica", 11, "bold"), bg="#24292e", fg="white").pack(fill="x", pady=3)
        
        tk.Button(donate_window, text="Close", command=donate_window.destroy,
                  font=("Helvetica", 10), bg=COLORS['bg_light'], fg=COLORS['text_white']).pack(pady=15)

    def open_url(self, url):
        import webbrowser
        try: webbrowser.open(url)
        except: messagebox.showerror("Error", "Could not open browser. Please visit:\n" + url)

    def show_about(self):
        messagebox.showinfo("About",
            f"DotScramble\nVersion {APP_VERSION}\n\n"
            "Privacy Protection for the Digital Age\n\n"
            "Support the developer:\n"
            "• PayPal: https://paypal.me/freerave1\n"
            "• Buy Me a Coffee: https://buymeacoffee.com/freerave\n"
            "• Ko-fi: https://ko-fi.com/freerave\n\n"
            "Made with ❤️ by FreeRave")

    def show_shortcuts(self):
        shortcuts_text = "\n".join([f"{key}: {value}" for key, value in SHORTCUTS.items()])
        messagebox.showinfo("Keyboard Shortcuts", shortcuts_text)

    def check_for_updates(self):
        self.auto_updater.check_for_updates(silent=False)

    def open_exports_folder(self):
        import webbrowser
        try: webbrowser.open(str(DIRS['exports']))
        except Exception as e: messagebox.showerror("Error", f"Could not open exports folder: {e}")

    def open_app_data_folder(self):
        import webbrowser
        try:
            from src.config import SYSTEM_DIR
            webbrowser.open(str(SYSTEM_DIR))
        except Exception as e: messagebox.showerror("Error", f"Could not open app data folder: {e}")

    # Fixed: Changed name from show_update_button to on_update_ready
    def on_update_ready(self):
        """Show the update ready button when download completes"""
        self.root.after(0, lambda: self.update_btn.pack(side="right", padx=10, pady=2))
        self.root.after(0, lambda: messagebox.showinfo("Update Ready",
            "A new update has been downloaded in the background.\n"
            "You can restart anytime using the button in the status bar."))

    def apply_update(self):
        """Apply the ready update when user clicks the button"""
        if messagebox.askyesno("Restart Application",
                            "Application will close to apply the update. Continue?"):
            self.auto_updater.apply_pending_update()

    def change_theme(self, theme_key):
        """Change the application theme"""
        self._debug_status_bar("BEFORE theme change")
        self.theme_manager.apply_theme(theme_key, self)
        self._debug_status_bar("AFTER  theme change")
    
    def restore_user_settings(self):
        """Restore user settings from database on startup."""
        try:
            # Restore language first (before other UI elements)
            last_language = self.db_manager.get_last_used_language()
            self.language_var.set(last_language)
            
            # Initialize localization with saved language
            loc_mgr = get_locale_manager()
            if loc_mgr.set_language(last_language):
                # Apply RTL layout if needed
                self.apply_rtl_layout(last_language)
                # Update UI text
                self.update_ui_text()
                print(f"✅ Language restored: {last_language}")
            
            # Restore theme
            last_theme = self.db_manager.get_last_used_theme()
            self.theme_manager.apply_theme(last_theme, self)
            
            # Restore effect settings
            effect_settings = self.db_manager.get_last_effect_settings()
            self.effect_type.set(effect_settings.get('effect_type', 'blur'))
            self.detection_mode.set(effect_settings.get('detection_mode', 'face'))
            self.blur_strength.set(effect_settings.get('blur_strength', 51))
            self.pixel_size.set(effect_settings.get('pixel_size', 15))
            self.opacity.set(effect_settings.get('opacity', 100))
            
            # Restore real-time preview preference
            real_time = self.db_manager.get_real_time_preview_enabled()
            self.real_time_preview.set(real_time)
            
            # Update UI based on restored settings
            self.update_parameter_visibility()
            
            print("✅ User settings restored from database")
            
        except Exception as e:
            print(f"⚠️ Could not restore user settings: {e}")
    
    def on_effect_change(self):
        self.update_parameter_visibility()
        # Save effect settings to database
        self.save_current_effect_settings()
        if self.real_time_preview.get(): self.process_image()

    def on_detection_change(self):
        mode = self.detection_mode.get()
        # FREE users: face detection uses Haar; PRO uses MediaPipe AI
        # These modes are fully blocked for FREE users:
        pro_only_modes = ['target_text', 'text', 'body', 'license_plate']

        if mode in pro_only_modes and not self.license_manager.is_max_activated:
            mode_display = mode.replace('_', ' ').title()
            messagebox.showinfo(
                "Pro Feature",
                f"The '{mode_display}' detection mode is a Pro feature.\n\n"
                f"Upgrade to DotScramble Pro for advanced AI models.",
                parent=self.root
            )
            self.detection_mode.set("face")
            mode = "face"

        # Check if PRO user selected face/eye and model needs to be downloaded
        if mode in ["face", "eye"] and self.license_manager.is_max_activated:
            from src.models.detection_engine import is_model_downloaded
            if not is_model_downloaded():
                self.prompt_download_ai_model()

        self.update_parameter_visibility()
        self.save_current_effect_settings()
        if self.real_time_preview.get() and self.original_image is not None: self.process_image()

    def prompt_download_ai_model(self):
        """Prompt the user to download the MediaPipe face landmarker model."""
        if not messagebox.askyesno(
            "AI Model Required",
            "This PRO feature requires downloading an AI model file (~8MB).\n\n"
            "Would you like to download it now?",
            parent=self.root
        ):
            return

        # Create progress window
        dl_win = tk.Toplevel(self.root)
        dl_win.title("Downloading AI Model")
        dl_win.geometry("300x120")
        dl_win.resizable(False, False)
        dl_win.transient(self.root)
        dl_win.grab_set()

        # Center the window
        dl_win.update_idletasks()
        w = dl_win.winfo_width()
        h = dl_win.winfo_height()
        extra_x = (self.root.winfo_width() - w) // 2
        extra_y = (self.root.winfo_height() - h) // 2
        dl_win.geometry(f"+{self.root.winfo_x() + extra_x}+{self.root.winfo_y() + extra_y}")

        label = tk.Label(dl_win, text="Downloading face_landmarker.task...", pady=10)
        label.pack()
        progress = ttk.Progressbar(dl_win, length=250, mode="determinate")
        progress.pack(pady=5)

        import threading
        def download_thread():
            from src.models.detection_engine import download_model_file

            def update_progress(percentage):
                self.root.after(0, lambda: progress.configure(value=percentage))

            success = download_model_file(update_progress)
            
            def on_finish():
                dl_win.destroy()
                if success:
                    messagebox.showinfo("Success", "AI Model downloaded successfully! PRO features are now active.", parent=self.root)
                    if self.real_time_preview.get() and self.original_image is not None:
                        self.process_image()
                else:
                    messagebox.showerror("Download Failed", "Failed to download the AI model. Please check your internet connection.", parent=self.root)

            self.root.after(0, on_finish)

        threading.Thread(target=download_thread, daemon=True).start()

    def on_parameter_change(self):
        # Save effect settings to database
        self.save_current_effect_settings()
        if self.real_time_preview.get() and self.original_image is not None: self.process_image()
    
    def save_current_effect_settings(self):
        """Save current effect parameters to database."""
        settings = {
            'effect_type': self.effect_type.get(),
            'detection_mode': self.detection_mode.get(),
            'blur_strength': self.blur_strength.get(),
            'pixel_size': self.pixel_size.get(),
            'opacity': self.opacity.get()
        }
        try:
            self.db_manager.save_last_effect_settings(settings)
        except Exception as e:
            print(f"⚠️ Could not save effect settings: {e}")
    
    def toggle_preview(self):
        enabled = self.real_time_preview.get()
        # Save preference to database
        try:
            self.db_manager.save_real_time_preview_enabled(enabled)
        except Exception as e:
            print(f"⚠️ Could not save preview preference: {e}")
        
        if enabled:
            self.status_label.config(text="Real-time preview enabled")
        else:
            self.status_label.config(text="Real-time preview disabled")
    
    def on_window_state_change(self, event=None):
        """Handle window state changes (map/unmap events)."""
        # Only refresh menu bar if window state actually changed (minimize/maximize)
        # Check if window is maximized
        try:
            is_maximized = self.root.attributes('-zoomed')
        except:
            try:
                is_maximized = self.root.state() == 'zoomed'
            except:
                is_maximized = False
        
        # Track previous state to avoid unnecessary refreshes
        if not hasattr(self, '_last_maximized_state'):
            self._last_maximized_state = False
        
        # Only refresh if state changed
        if is_maximized != self._last_maximized_state:
            self._last_maximized_state = is_maximized
            self.root.after(150, self.refresh_menu_bar)
    
    def refresh_menu_bar(self):
        """Refresh menu bar reference (safe — no geometry thrashing)."""
        try:
            if hasattr(self, 'menubar') and self.menubar:
                # Just re-set the menubar directly — never hide/show it.
                # Using config(menu='') causes a full pack geometry recalculation
                # which collapses side='bottom' frames behind expand=True widgets.
                self.root.config(menu=self.menubar)
        except Exception as e:
            print(f"⚠️ Could not refresh menu bar: {e}")
    
    def restore_window_state(self):
        """Restore window size and position from database."""
        try:
            state = self.db_manager.get_window_state()
            
            # Set window size and position
            width = state.get('width', 1400)
            height = state.get('height', 900)
            x = state.get('x', 100)
            y = state.get('y', 100)
            
            # Apply geometry
            self.root.geometry(f"{width}x{height}+{x}+{y}")
            
            # Handle maximized state
            maximized = state.get('maximized', False)
            if maximized:
                try:
                    # Try Linux/Unix method first
                    self.root.attributes('-zoomed', True)
                except:
                    # Fallback to Windows method
                    try:
                        self.root.state('zoomed')
                    except:
                        pass
                
                # Force menu bar refresh after maximizing
                self.root.after(200, self.refresh_menu_bar)
            
            print(f"✅ Window state restored: {width}x{height}+{x}+{y} (maximized: {maximized})")
            
        except Exception as e:
            print(f"⚠️ Could not restore window state: {e}")
    
    def on_close(self):
        """Save application state before closing."""
        try:
            # Check if window is maximized
            try:
                is_maximized = self.root.attributes('-zoomed')
            except:
                try:
                    is_maximized = self.root.state() == 'zoomed'
                except:
                    is_maximized = False
            
            if is_maximized:
                # Save maximized state
                self.db_manager.save_setting('window_state', {'maximized': True}, 'window')
            else:
                # Save window dimensions and position
                width = self.root.winfo_width()
                height = self.root.winfo_height()
                x = self.root.winfo_x()
                y = self.root.winfo_y()
                
                self.db_manager.save_window_state(width, height, x, y, False)
            
            print("💾 Application state saved before closing")
            
        except Exception as e:
            print(f"⚠️ Error saving application state: {e}")
        
        # Close database and destroy window
        try:
            self.db_manager.close()
        except:
            pass
        
        self.root.destroy()
    
    @property
    def is_rtl(self):
        """Get RTL state from RTL Manager"""
        if hasattr(self, 'rtl_manager') and self.rtl_manager:
            return self.rtl_manager.is_rtl
        return False
    
    def load_image_from_path(self, file_path):
        """Load image from a specific path (for recent files menu)."""
        if not file_path or not os.path.exists(file_path):
            messagebox.showerror("Error", "File not found!")
            return
        
        # Add to recent files
        self.db_manager.add_recent_file(file_path)
        
        # Load the image
        self.image_path = file_path
        # Support non-Latin/Arabic characters in file path (cross-platform)
        loaded_image = cv2.imdecode(np.fromfile(file_path, dtype=np.uint8), cv2.IMREAD_COLOR)
        
        if loaded_image is None:
            messagebox.showerror("Error", f"Could not load image: {os.path.basename(file_path)}")
            return
        
        if loaded_image.size == 0:
            messagebox.showerror("Error", "Loaded image is empty!")
            return
        
        self.original_image = loaded_image
        self.processed_image = self.original_image.copy()
        self.drawing_regions = []
        self.history_manager.clear()
        
        self.display_image(self.original_image)
        self.process_btn.config(state="normal")
        
        info = self.image_utils.get_image_info(self.original_image)
        self.status_label.config(text=f"Loaded: {os.path.basename(file_path)}")
        self.info_label.config(text=f"{info['width']}x{info['height']} | {info['size_kb']} KB")
        self.update_buttons()
        
        # Refresh recent files menu
        self.create_menu_bar()
    
    def clear_recent_history(self):
        """Clear recent files history."""
        if messagebox.askyesno("Clear History", "Are you sure you want to clear recent files history?"):
            self.db_manager.clear_recent_files()
            # Refresh menu
            self.create_menu_bar()
    
    def on_drop(self, event):
        """Handle drag and drop events."""
        try:
            # Get the file path from the drag and drop event
            file_path = event.data
            
            # Clean up the file path (remove braces if present)
            if file_path.startswith('{') and file_path.endswith('}'):
                file_path = file_path[1:-1]
            
            # Load the image from the dropped file
            self.load_image_from_path(file_path)
            
        except Exception as e:
            messagebox.showerror("Error", f"Could not load dropped file: {str(e)}")
    
    def add_language_menu_items(self, lang_menu):
        """Add language selection items to the language menu."""
        # Get localization manager
        loc_mgr = get_locale_manager()
        
        # Get supported languages
        languages = loc_mgr.get_language_list()
        
        # Create radio buttons for each language
        for lang in languages:
            lang_code = lang['code']
            display_name = f"{lang['name']} ({lang['native_name']})"
            
            lang_menu.add_radiobutton(
                label=display_name,
                variable=self.language_var,  # Use the dedicated language variable
                value=lang_code,
                command=lambda code=lang_code: self.change_language(code)
            )
    
    def change_language(self, language_code):
        """Change the application language."""
        loc_mgr = get_locale_manager()

        if loc_mgr.set_language(language_code):
            self.db_manager.save_last_used_language(language_code)

            self._debug_status_bar(f"BEFORE apply_rtl_layout ({language_code})")
            self.apply_rtl_layout(language_code)
            self._debug_status_bar(f"AFTER  apply_rtl_layout")

            self.update_ui_text()
            self._debug_status_bar(f"AFTER  update_ui_text")

            current_theme = self.theme_manager.get_current_theme_key()
            self.theme_manager.apply_theme(current_theme, self)
            self._debug_status_bar(f"AFTER  apply_theme")

            print(f"Language changed to: {language_code}")

    def _debug_status_bar(self, label=""):
        """Print status bar dimensions and grid info for debugging."""
        try:
            sb = self.status_bar
            self.root.update_idletasks()
            h   = sb.winfo_height()
            w   = sb.winfo_width()
            y   = sb.winfo_y()
            vis = sb.winfo_viewable()
            gi  = sb.grid_info()
            rh  = self.root.winfo_height()
            print(f"[STATUS BAR] {label}")
            print(f"  size={w}x{h}  y={y}  viewable={vis}  root_h={rh}")
            print(f"  grid_info={gi}")
        except Exception as e:
            print(f"[STATUS BAR] {label} — ERROR: {e}")
    
    def apply_rtl_layout(self, language_code):
        """Apply RTL layout for Arabic language."""
        loc_mgr = get_locale_manager()
        
        # Set the language first to check RTL status
        if loc_mgr.set_language(language_code):
            new_rtl_state = loc_mgr.is_rtl()
            
            # Use RTL Manager to handle the layout changes
            self.rtl_manager.set_rtl_state(new_rtl_state)
    
    
    def update_button_references(self):
        """Update button references after panel recreation.
        (No longer needed as panels are never rebuilt, but kept for compatibility)"""
        pass
    
    def update_input_field_direction(self):
        """Update text direction for input fields based on RTL state."""
        if hasattr(self, 'word_entry'):
            # For Entry widgets, we can't directly set text direction
            # But we can set the justify property to align text properly
            if self.is_rtl:
                self.word_entry.config(justify="right")
                # Set font to support Arabic text
                self.word_entry.config(font=("Helvetica", 10))
            else:
                self.word_entry.config(justify="left")
                # Set font for LTR text
                self.word_entry.config(font=("Helvetica", 10))
    
    def update_ui_text(self):
        """Update all UI text by updating StringVars."""
        loc_mgr = get_locale_manager()
        
        # 1. Update window title
        self.root.title(loc_mgr.get("app.title"))
        
        # 2. Update Status Bar if it's currently showing default ready text
        try:
            if hasattr(self, 'status_label') and self.status_label.winfo_exists():
                current = self.status_label.cget("text")
                if "Ready" in current or "جاهز" in current:
                    self.status_label.config(text=loc_mgr.get("ui.status.ready"))
        except: pass
        
        # 3. Update all static UI StringVars
        for key, var in self.ui_strings.items():
            var.set(loc_mgr.get(key))
            
        # 4. Update RadioButton lists
        for i, key in enumerate(self.effect_keys):
            self.effect_strings[i].set(loc_mgr.get(key))
            
        for i, key in enumerate(self.detection_keys):
            self.detection_strings[i].set(loc_mgr.get(key))
            
        # 5. Adjust input field direction
        self.update_input_field_direction()

        # 6. Rebuild Menu Bar (tk.Menu doesn't support textvariable).
        # Deferred via after(0) so this runs after the current layout pass
        # has settled — avoids geometry conflicts with RTL panel switching.
        self.root.after(0, self.create_menu_bar)