"""
Batch Processing Window for Advanced Privacy Studio Pro
Handles batch image processing with progress tracking
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import threading
from pathlib import Path
import logging

# Import custom modules
from src.config import COLORS, SUPPORTED_FORMATS, BLUR_RANGE, PIXEL_RANGE, OPACITY_RANGE
from core.batch_processor import BatchProcessor
from src.managers.localization_manager import get_locale_manager

class BatchWindow:
    """Batch processing window with file management and progress tracking"""
    
    FREE_FILE_LIMIT = 3  # Free tier cap
    
    def __init__(self, parent, batch_processor, license_manager):
        """
        Initialize batch processing window
        
        Args:
            parent: Parent tkinter window
            batch_processor: Instance of BatchProcessor
            license_manager: Instance of LicenseManager (for tier checks)
        """
        self.parent = parent
        self.batch_processor = batch_processor
        self.license_manager = license_manager
        self.selected_files = []
        self.processing = False
        self.logger = logging.getLogger(__name__)
        self.locale_manager = get_locale_manager()
        
        # Create window
        self.window = tk.Toplevel(parent)
        self.window.title("📦 Batch Processing - Privacy Studio Pro")
        self.window.geometry("900x650")
        self.window.configure(bg=COLORS['bg_dark'])
        
        # Make window modal
        self.window.transient(parent)
        self.window.grab_set()
        
        # Settings
        self.detection_mode = tk.StringVar(value="face")
        self.effect_type = tk.StringVar(value="blur")
        self.blur_strength = tk.IntVar(value=BLUR_RANGE['default'])
        self.pixel_size = tk.IntVar(value=PIXEL_RANGE['default'])
        self.opacity = tk.IntVar(value=OPACITY_RANGE['default'])
        
        # Processing state
        self.current_progress = 0
        self.total_files = 0
        
        self.init_ui_strings()
        
        self.create_widgets()
        
        # Bind window close
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)

    def init_ui_strings(self):
        """Initialize tk.StringVar objects for localized text"""
        _ = self.locale_manager.get
        
        self.detection_keys = [
            "detection.face", "detection.eye", "detection.body",
            "detection.license_plate", "detection.text", "detection.full"
        ]
        self.detection_strings = [tk.StringVar(value=_(k)) for k in self.detection_keys]
        
        # Batch window uses a slightly different effect list (hardcoded strings mixed with emojis)
        # We will keep the hardcoded ones as they are or create StringVars for them if needed.
        # But to match main_window, let's just make the detection modes Reactive.
    
    def create_widgets(self):
        """Create all GUI widgets"""
        # Header
        header = tk.Frame(self.window, bg=COLORS['bg_medium'], height=60)
        header.pack(fill="x", pady=(0, 10))
        
        tk.Label(header, text="📦 Batch Image Processing", 
                font=("Helvetica", 20, "bold"),
                bg=COLORS['bg_medium'], fg=COLORS['accent_cyan']).pack(pady=15)
        
        # Main container
        main_container = tk.Frame(self.window, bg=COLORS['bg_dark'])
        main_container.pack(fill="both", expand=True, padx=15, pady=10)
        
        # Create sections
        self.create_file_list_section(main_container)
        self.create_settings_section(main_container)
        self.create_progress_section(main_container)
        self.create_action_buttons(main_container)
    
    def create_file_list_section(self, parent):
        """Create file list section"""
        list_frame = tk.LabelFrame(parent, text="📁 Selected Files", 
                                   font=("Helvetica", 12, "bold"),
                                   bg=COLORS['bg_medium'], fg=COLORS['text_white'],
                                   relief="groove", bd=2)
        list_frame.pack(fill="both", expand=True, pady=(0, 10))
        
        # File list with scrollbar
        list_container = tk.Frame(list_frame, bg=COLORS['bg_medium'])
        list_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        scrollbar_y = tk.Scrollbar(list_container)
        scrollbar_y.pack(side="right", fill="y")
        
        scrollbar_x = tk.Scrollbar(list_container, orient="horizontal")
        scrollbar_x.pack(side="bottom", fill="x")
        
        self.file_listbox = tk.Listbox(list_container,
                                       bg=COLORS['bg_light'],
                                       fg=COLORS['text_white'],
                                       font=("Courier", 10),
                                       selectmode=tk.EXTENDED,
                                       yscrollcommand=scrollbar_y.set,
                                       xscrollcommand=scrollbar_x.set)
        self.file_listbox.pack(side="left", fill="both", expand=True)
        
        scrollbar_y.config(command=self.file_listbox.yview)
        scrollbar_x.config(command=self.file_listbox.xview)
        
        # File management buttons
        btn_frame = tk.Frame(list_frame, bg=COLORS['bg_medium'])
        btn_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        self.add_btn = self.create_button(btn_frame, "➕ Add Files", 
                                          self.add_files, 
                                          COLORS['accent_green'])
        self.add_btn.pack(side="left", padx=5)
        
        self.add_folder_btn = self.create_button(btn_frame, "📂 Add Folder", 
                                                 self.add_folder, 
                                                 COLORS['accent_cyan'])
        self.add_folder_btn.pack(side="left", padx=5)
        
        self.remove_btn = self.create_button(btn_frame, "➖ Remove Selected", 
                                             self.remove_selected, 
                                             COLORS['accent_orange'])
        self.remove_btn.pack(side="left", padx=5)
        
        self.clear_btn = self.create_button(btn_frame, "🗑️ Clear All", 
                                            self.clear_all, 
                                            COLORS['accent_red'])
        self.clear_btn.pack(side="left", padx=5)
        
        # File count label
        self.file_count_label = tk.Label(btn_frame, text="Files: 0",
                                        font=("Helvetica", 10, "bold"),
                                        bg=COLORS['bg_medium'], 
                                        fg=COLORS['accent_cyan'])
        self.file_count_label.pack(side="right", padx=10)
    
    def create_settings_section(self, parent):
        """Create settings section"""

        _ = self.locale_manager.get

        settings_frame = tk.LabelFrame(parent, text=_("ui.controls.effect_type"), 
                                       font=("Helvetica", 12, "bold"),
                                       bg=COLORS['bg_medium'], 
                                       fg=COLORS['text_white'],
                                       relief="groove", bd=2)
        settings_frame.pack(fill="x", pady=(0, 10))
        
        # Create two columns
        left_col = tk.Frame(settings_frame, bg=COLORS['bg_medium'])
        left_col.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        
        right_col = tk.Frame(settings_frame, bg=COLORS['bg_medium'])
        right_col.pack(side="right", fill="both", expand=True, padx=10, pady=10)
        
        # Detection mode
        tk.Label(left_col, text="Detection Mode:", 
                font=("Helvetica", 10, "bold"),
                bg=COLORS['bg_medium'], fg=COLORS['text_white']).pack(anchor="w", pady=(0, 5))
        
        detection_modes = [
            "face",
            "eye",
            "body",
            "license_plate",
            "text",
            "full"
        ]
        
        for i, value in enumerate(detection_modes):
            rb = tk.Radiobutton(left_col, textvariable=self.detection_strings[i],
                               variable=self.detection_mode, value=value,
                               font=("Helvetica", 9),
                               bg=COLORS['bg_medium'], fg=COLORS['text_white'],
                               selectcolor=COLORS['bg_light'],
                               activebackground=COLORS['bg_medium'])
            rb.pack(anchor="w", pady=2)
        
        # Effect type
        tk.Label(right_col, text="Effect Type:", 
                font=("Helvetica", 10, "bold"),
                bg=COLORS['bg_medium'], fg=COLORS['text_white']).pack(anchor="w", pady=(0, 5))
        
        effects = [
            ("🌫️ Gaussian Blur", "blur"),
            ("🔲 Pixelation", "pixelation"),
            ("⬛ Black Bar", "black_bar"),
            ("🎭 Gradient Fade", "gradient"),
            ("🔳 Mosaic", "mosaic"),
            ("❄️ Frosted Glass", "glass"),
            ("🎨 Oil Paint", "oil_paint")
        ]
        
        for text, value in effects:
            rb = tk.Radiobutton(right_col, text=text,
                               variable=self.effect_type, value=value,
                               font=("Helvetica", 9),
                               bg=COLORS['bg_medium'], fg=COLORS['text_white'],
                               selectcolor=COLORS['bg_light'],
                               activebackground=COLORS['bg_medium'])
            rb.pack(anchor="w", pady=2)
    
    def create_progress_section(self, parent):
        """Create progress tracking section"""
        progress_frame = tk.LabelFrame(parent, text="📊 Progress", 
                                       font=("Helvetica", 12, "bold"),
                                       bg=COLORS['bg_medium'], 
                                       fg=COLORS['text_white'],
                                       relief="groove", bd=2)
        progress_frame.pack(fill="x", pady=(0, 10))
        
        inner_frame = tk.Frame(progress_frame, bg=COLORS['bg_medium'])
        inner_frame.pack(fill="x", padx=10, pady=10)
        
        # Progress bar
        self.progress_bar = ttk.Progressbar(inner_frame, 
                                           mode='determinate',
                                           length=400)
        self.progress_bar.pack(fill="x", pady=5)
        
        # Status label
        self.status_label = tk.Label(inner_frame, 
                                     text="Ready to process",
                                     font=("Helvetica", 10),
                                     bg=COLORS['bg_medium'], 
                                     fg=COLORS['text_white'])
        self.status_label.pack(pady=5)
        
        # Stats frame
        stats_frame = tk.Frame(inner_frame, bg=COLORS['bg_medium'])
        stats_frame.pack(fill="x", pady=5)
        
        self.processed_label = tk.Label(stats_frame, text="Processed: 0/0",
                                       font=("Helvetica", 9),
                                       bg=COLORS['bg_medium'], 
                                       fg=COLORS['accent_green'])
        self.processed_label.pack(side="left", padx=10)
        
        self.failed_label = tk.Label(stats_frame, text="Failed: 0",
                                     font=("Helvetica", 9),
                                     bg=COLORS['bg_medium'], 
                                     fg=COLORS['accent_red'])
        self.failed_label.pack(side="left", padx=10)
        
        self.time_label = tk.Label(stats_frame, text="Time: 0s",
                                   font=("Helvetica", 9),
                                   bg=COLORS['bg_medium'], 
                                   fg=COLORS['accent_cyan'])
        self.time_label.pack(side="right", padx=10)
    
    def create_action_buttons(self, parent):
        """Create action buttons"""
        btn_frame = tk.Frame(parent, bg=COLORS['bg_dark'])
        btn_frame.pack(fill="x", pady=10)
        
        self.start_btn = self.create_button(btn_frame, "▶️ Start Processing", 
                                            self.start_processing, 
                                            COLORS['accent_green'],
                                            width=20)
        self.start_btn.pack(side="left", padx=5)
        
        self.stop_btn = self.create_button(btn_frame, "⏹️ Stop", 
                                           self.stop_processing, 
                                           COLORS['accent_red'],
                                           width=15,
                                           state="disabled")
        self.stop_btn.pack(side="left", padx=5)
        
        self.close_btn = self.create_button(btn_frame, "❌ Close", 
                                            self.on_close, 
                                            COLORS['bg_light'],
                                            width=15)
        self.close_btn.pack(side="right", padx=5)
    
    def create_button(self, parent, text, command, bg_color, width=None, state="normal"):
        """Create styled button"""
        btn = tk.Button(parent, text=text,
                       command=command,
                       font=("Helvetica", 10, "bold"),
                       bg=bg_color, fg=COLORS['text_white'],
                       activebackground=bg_color,
                       cursor="hand2",
                       relief="flat",
                       padx=15, pady=8,
                       state=state)
        if width:
            btn.config(width=width)
        return btn
    
    # File management methods
    def _is_max(self):
        """Check if the current user has the Max plan."""
        return self.license_manager.is_max_activated

    def _check_free_limit(self, newly_added: int) -> int:
        """Enforce the free-tier file cap.
        
        Returns the number of files that were removed due to the cap.
        Shows an upgrade prompt if the cap is exceeded.
        """
        if self._is_max():
            return 0
        
        total = len(self.selected_files)
        if total <= self.FREE_FILE_LIMIT:
            return 0
        
        # Trim excess files
        excess = total - self.FREE_FILE_LIMIT
        self.selected_files = self.selected_files[:self.FREE_FILE_LIMIT]
        
        # Sync listbox
        self.file_listbox.delete(0, tk.END)
        for f in self.selected_files:
            self.file_listbox.insert(tk.END, f"\U0001f4c4 {os.path.basename(f)}")
        
        messagebox.showwarning(
            "Free Plan Limit",
            f"Free plan is limited to {self.FREE_FILE_LIMIT} images per batch.\n\n"
            f"{excess} file(s) were removed.\n\n"
            "Upgrade to Max to process unlimited images.",
            parent=self.window,
        )
        return excess

    def add_files(self):
        """Add files to processing list"""
        files = filedialog.askopenfilenames(
            title="Select Images",
            filetypes=SUPPORTED_FORMATS
        )
        
        if files:
            added_count = 0
            for file in files:
                if file not in self.selected_files:
                    self.selected_files.append(file)
                    self.file_listbox.insert(tk.END, f"📄 {os.path.basename(file)}")
                    added_count += 1
            
            removed = self._check_free_limit(added_count)
            added_count = max(0, added_count - removed)
            self.update_file_count()
            if added_count > 0:
                self.status_label.config(text=f"Added {added_count} file(s)")
    
    def add_folder(self):
        """Add all images from a folder"""
        folder = filedialog.askdirectory(title="Select Folder")
        
        if folder:
            supported_exts = ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff']
            added_count = 0
            
            for file in Path(folder).glob('*'):
                if file.suffix.lower() in supported_exts:
                    file_path = str(file)
                    if file_path not in self.selected_files:
                        self.selected_files.append(file_path)
                        self.file_listbox.insert(tk.END, f"📄 {file.name}")
                        added_count += 1
            
            removed = self._check_free_limit(added_count)
            added_count = max(0, added_count - removed)
            self.update_file_count()
            if added_count > 0:
                self.status_label.config(text=f"Added {added_count} file(s) from folder")
            else:
                messagebox.showinfo("Info", "No valid images found in folder", parent=self.window)
    
    def remove_selected(self):
        """Remove selected files from list"""
        selected_indices = self.file_listbox.curselection()
        
        if not selected_indices:
            messagebox.showinfo("Info", "Please select files to remove", parent=self.window)
            return
        
        # Remove in reverse order to maintain indices
        for index in reversed(selected_indices):
            del self.selected_files[index]
            self.file_listbox.delete(index)
        
        self.update_file_count()
        self.status_label.config(text=f"Removed {len(selected_indices)} file(s)")
    
    def clear_all(self):
        """Clear all files from list"""
        if not self.selected_files:
            return
        
        if messagebox.askyesno("Confirm", "Clear all files from list?", parent=self.window):
            self.selected_files = []
            self.file_listbox.delete(0, tk.END)
            self.update_file_count()
            self.status_label.config(text="Cleared all files")
    
    def update_file_count(self):
        """Update file count label"""
        count = len(self.selected_files)
        self.file_count_label.config(text=f"Files: {count}")
    
    # Processing methods
    def start_processing(self):
        """Start batch processing"""
        if not self.selected_files:
            messagebox.showwarning("Warning", "No files selected!", parent=self.window)
            return
        
        # Select output directory
        output_dir = filedialog.askdirectory(title="Select Output Folder")
        if not output_dir:
            return
        
        # Validate files
        valid_files, invalid_files = self.batch_processor.validate_input_files(
            self.selected_files
        )
        
        if invalid_files:
            msg = f"Found {len(invalid_files)} invalid file(s):\n\n"
            msg += "\n".join(invalid_files[:5])
            if len(invalid_files) > 5:
                msg += f"\n... and {len(invalid_files) - 5} more"
            msg += f"\n\nProcess {len(valid_files)} valid file(s)?"
            
            if not messagebox.askyesno("Invalid Files", msg, parent=self.window):
                return
        
        # Prepare settings
        settings = {
            'detection_mode': self.detection_mode.get(),
            'effect_type': self.effect_type.get(),
            'is_pro': self._is_max(),
            'effect_params': {
                'blur_strength': self.blur_strength.get(),
                'pixel_size': self.pixel_size.get(),
                'opacity': self.opacity.get()
            }
        }
        
        # Start processing in thread
        self.processing = True
        self.total_files = len(valid_files)
        self.current_progress = 0
        self.failed_count = 0
        self.start_time = None
        
        self.update_ui_state(processing=True)
        
        def process_worker():
            import time
            self.start_time = time.time()
            
            self.batch_processor.process_batch(
                valid_files,
                output_dir,
                settings,
                progress_callback=self.on_progress,
                error_callback=self.on_error,
                is_cancelled=lambda: not self.processing
            )
            
            # Processing complete
            self.window.after(0, self.on_complete)
        
        thread = threading.Thread(target=process_worker, daemon=True)
        thread.start()
    
    def stop_processing(self):
        """Stop batch processing"""
        if messagebox.askyesno("Confirm", "Stop processing?", parent=self.window):
            self.processing = False
            self.status_label.config(text="Processing stopped by user")
            self.update_ui_state(processing=False)
    
    def on_progress(self, current, total, result):
        """Handle progress update"""
        if not self.processing:
            return
        
        def update_ui():
            if not self.processing:
                return
            self.current_progress = current
            progress = (current / total) * 100
            self.progress_bar.config(value=progress)
            self.processed_label.config(text=f"Processed: {current}/{total}")
            self.status_label.config(text=f"Processing: {os.path.basename(result['input_path'])}")
            if self.start_time:
                import time
                elapsed = int(time.time() - self.start_time)
                self.time_label.config(text=f"Time: {elapsed}s")

        self.window.after(0, update_ui)
    
    def on_error(self, file_path, error_msg):
        """Handle processing error"""
        def update_ui_error():
            self.failed_count += 1
            self.failed_label.config(text=f"Failed: {self.failed_count}")
        self.window.after(0, update_ui_error)
        self.logger.error(f"Failed to process {file_path}: {error_msg}")
    
    def on_complete(self):
        """Handle processing completion"""
        self.processing = False
        self.update_ui_state(processing=False)
        
        success_count = self.current_progress - self.failed_count
        
        msg = f"Batch processing complete!\n\n"
        msg += f"✅ Successful: {success_count}\n"
        msg += f"❌ Failed: {self.failed_count}\n"
        msg += f"📊 Total: {self.total_files}"
        
        messagebox.showinfo("Complete", msg, parent=self.window)
        self.status_label.config(text="Processing complete!")
    
    def update_ui_state(self, processing):
        """Update UI state during processing"""
        state = "disabled" if processing else "normal"
        
        self.add_btn.config(state=state)
        self.add_folder_btn.config(state=state)
        self.remove_btn.config(state=state)
        self.clear_btn.config(state=state)
        self.start_btn.config(state=state)
        self.close_btn.config(state=state)
        
        self.stop_btn.config(state="normal" if processing else "disabled")
    
    def on_close(self):
        """Handle window close"""
        if self.processing:
            if not messagebox.askyesno("Confirm", "Processing in progress. Close anyway?", parent=self.window):
                return
            self.processing = False
        
        self.window.destroy()
