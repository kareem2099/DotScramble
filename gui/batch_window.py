"""
Batch Processing Window for Advanced Privacy Studio Pro (PySide6 version)
Handles batch image processing with progress tracking
"""
import os
import threading
import time
import logging
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QProgressBar, QRadioButton, QButtonGroup, QFrame,
    QGridLayout, QFileDialog, QMessageBox, QGroupBox
)
from PySide6.QtCore import Qt, QObject, Signal

from src.config import COLORS, SUPPORTED_FORMATS, BLUR_RANGE, PIXEL_RANGE, OPACITY_RANGE
from core.batch_processor import BatchProcessor
from src.managers.localization_manager import get_locale_manager


class BatchSignals(QObject):
    """Signals for thread-safe UI updates from the processing worker thread"""
    progress = Signal(int, int, dict)
    error = Signal(str, str)
    complete = Signal()


class BatchWindow(QDialog):
    """Batch processing window with file management and progress tracking"""
    
    FREE_FILE_LIMIT = 3  # Free tier cap
    
    def __init__(self, parent, batch_processor, license_manager):
        super().__init__(parent)
        self.batch_processor = batch_processor
        self.license_manager = license_manager
        self.selected_files = []
        self.processing = False
        self.logger = logging.getLogger(__name__)
        self.locale_manager = get_locale_manager()
        
        # Get active colors from parent or default
        if parent and hasattr(parent, 'colors'):
            self.colors = parent.colors
        else:
            self.colors = COLORS
        
        self.setWindowTitle("📦 Batch Processing - Privacy Studio Pro")
        self.setMinimumSize(900, 650)
        self.resize(900, 650)

        # Thread signals
        self.signals = BatchSignals()
        self.signals.progress.connect(self.on_progress)
        self.signals.error.connect(self.on_error)
        self.signals.complete.connect(self.on_complete)
        
        # UI State variables
        self.current_progress = 0
        self.total_files = 0
        self.failed_count = 0
        self.start_time = None
        
        self.create_widgets()
        
    def _is_max(self):
        """Check if the current user has the Max plan."""
        return self.license_manager.is_max_activated

    def create_widgets(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header
        header = QFrame()
        header.setObjectName("DialogHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 15, 20, 15)
        
        title_lbl = QLabel("📦 Batch Image Processing")
        title_lbl.setObjectName("DialogTitle")
        header_layout.addWidget(title_lbl)
        main_layout.addWidget(header)

        # Content Frame
        content_frame = QWidget()
        content_layout = QVBoxLayout(content_frame)
        content_layout.setContentsMargins(20, 15, 20, 15)
        content_layout.setSpacing(10)

        # File List Section
        file_group = QGroupBox("📁 Selected Files")
        file_layout = QVBoxLayout(file_group)
        file_layout.setContentsMargins(10, 10, 10, 10)
        
        self.file_listbox = QListWidget()
        file_layout.addWidget(self.file_listbox, 1)

        # File list buttons row
        fl_buttons = QHBoxLayout()
        self.add_btn = QPushButton("➕ Add Files")
        self.add_btn.clicked.connect(self.add_files)
        fl_buttons.addWidget(self.add_btn)

        self.add_folder_btn = QPushButton("📂 Add Folder")
        self.add_folder_btn.clicked.connect(self.add_folder)
        fl_buttons.addWidget(self.add_folder_btn)

        self.remove_btn = QPushButton("➖ Remove Selected")
        self.remove_btn.clicked.connect(self.remove_selected)
        fl_buttons.addWidget(self.remove_btn)

        self.clear_btn = QPushButton("🗑️ Clear All")
        self.clear_btn.setObjectName("del_preset_btn")
        self.clear_btn.clicked.connect(self.clear_all)
        fl_buttons.addWidget(self.clear_btn)

        fl_buttons.addStretch(1)

        self.file_count_label = QLabel("Files: 0")
        self.file_count_label.setObjectName("FileCountLabel")
        fl_buttons.addWidget(self.file_count_label)
        file_layout.addLayout(fl_buttons)

        content_layout.addWidget(file_group, 1)

        # Settings Section
        settings_row = QHBoxLayout()
        
        # Left side: Detection Modes
        detect_group = QGroupBox("🎯 Detection Mode")
        detect_layout = QVBoxLayout(detect_group)
        self.detect_button_group = QButtonGroup(self)
        
        detection_modes = [
            ("face", "detection.face"), 
            ("eye", "detection.eye"), 
            ("body", "detection.body"),
            ("license_plate", "detection.license_plate"), 
            ("text", "detection.text"), 
            ("full", "detection.full")
        ]
        
        for i, (val, key) in enumerate(detection_modes):
            lbl_text = self.locale_manager.get(key)
            rb = QRadioButton(lbl_text)
            rb.setProperty("mode_val", val)
            self.detect_button_group.addButton(rb, i)
            detect_layout.addWidget(rb)
            if val == "face":
                rb.setChecked(True)
                
        settings_row.addWidget(detect_group, 1)

        # Right side: Effect Types
        effects_group = QGroupBox("🎨 Effect Type")
        effects_layout = QVBoxLayout(effects_group)
        self.effects_button_group = QButtonGroup(self)
        
        effects = [
            ("blur", "🌫️ Gaussian Blur"),
            ("pixelation", "🔲 Pixelation"),
            ("black_bar", "⬛ Black Bar"),
            ("gradient", "🎭 Gradient Fade"),
            ("mosaic", "🔳 Mosaic"),
            ("glass", "❄️ Frosted Glass"),
            ("oil_paint", "🎨 Oil Paint")
        ]
        
        for i, (val, label) in enumerate(effects):
            rb = QRadioButton(label)
            rb.setProperty("effect_val", val)
            self.effects_button_group.addButton(rb, i)
            effects_layout.addWidget(rb)
            if val == "blur":
                rb.setChecked(True)

        settings_row.addWidget(effects_group, 1)
        content_layout.addLayout(settings_row)

        # Progress Section
        progress_group = QGroupBox("📊 Progress")
        progress_layout = QVBoxLayout(progress_group)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Ready to process")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        progress_layout.addWidget(self.status_label)

        stats_row = QHBoxLayout()
        self.processed_label = QLabel("Processed: 0/0")
        self.processed_label.setObjectName("SuccessLabel")
        stats_row.addWidget(self.processed_label)

        self.failed_label = QLabel("Failed: 0")
        self.failed_label.setObjectName("FailedLabel")
        stats_row.addWidget(self.failed_label)
        
        stats_row.addStretch(1)

        self.time_label = QLabel("Time: 0s")
        self.time_label.setObjectName("TimeLabel")
        stats_row.addWidget(self.time_label)
        progress_layout.addLayout(stats_row)
        
        content_layout.addWidget(progress_group)

        # Action Buttons
        actions_row = QHBoxLayout()
        self.start_btn = QPushButton("▶️ Start Processing")
        self.start_btn.setObjectName("primary_action")
        self.start_btn.clicked.connect(self.start_processing)
        actions_row.addWidget(self.start_btn)

        self.stop_btn = QPushButton("⏹️ Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_processing)
        actions_row.addWidget(self.stop_btn)

        actions_row.addStretch(1)

        self.close_btn = QPushButton("❌ Close")
        self.close_btn.clicked.connect(self.close)
        actions_row.addWidget(self.close_btn)
        
        content_layout.addLayout(actions_row)
        
        main_layout.addWidget(content_frame, 1)

    def _check_free_limit(self, newly_added: int) -> int:
        """Enforce the free-tier file cap."""
        if self._is_max():
            return 0
        
        total = len(self.selected_files)
        if total <= self.FREE_FILE_LIMIT:
            return 0
        
        # Trim excess files
        excess = total - self.FREE_FILE_LIMIT
        self.selected_files = self.selected_files[:self.FREE_FILE_LIMIT]
        
        # Sync listbox
        self.file_listbox.clear()
        for f in self.selected_files:
            self.file_listbox.addItem(f"📄 {os.path.basename(f)}")
        
        QMessageBox.warning(
            self,
            "Free Plan Limit",
            f"Free plan is limited to {self.FREE_FILE_LIMIT} images per batch.\n\n"
            f"{excess} file(s) were removed.\n\n"
            "Upgrade to Max to process unlimited images."
        )
        return excess

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Images",
            os.path.expanduser("~"),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp *.tiff *.tif)"
        )
        
        if files:
            added_count = 0
            for file in files:
                if file not in self.selected_files:
                    self.selected_files.append(file)
                    self.file_listbox.addItem(f"📄 {os.path.basename(file)}")
                    added_count += 1
            
            removed = self._check_free_limit(added_count)
            added_count = max(0, added_count - removed)
            self.update_file_count()
            if added_count > 0:
                self.status_label.setText(f"Added {added_count} file(s)")

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            supported_exts = ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp']
            added_count = 0
            
            for file in Path(folder).glob('*'):
                if file.suffix.lower() in supported_exts:
                    file_path = str(file)
                    if file_path not in self.selected_files:
                        self.selected_files.append(file_path)
                        self.file_listbox.addItem(f"📄 {file.name}")
                        added_count += 1
            
            removed = self._check_free_limit(added_count)
            added_count = max(0, added_count - removed)
            self.update_file_count()
            if added_count > 0:
                self.status_label.setText(f"Added {added_count} file(s) from folder")
            else:
                QMessageBox.information(self, "Info", "No valid images found in folder")

    def remove_selected(self):
        selected_items = self.file_listbox.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "Info", "Please select files to remove")
            return
            
        for item in selected_items:
            row = self.file_listbox.row(item)
            self.file_listbox.takeItem(row)
            if row < len(self.selected_files):
                del self.selected_files[row]
                
        self.update_file_count()
        self.status_label.setText(f"Removed {len(selected_items)} file(s)")

    def clear_all(self):
        if not self.selected_files:
            return
        reply = QMessageBox.question(
            self, "Confirm", "Clear all files from list?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.selected_files = []
            self.file_listbox.clear()
            self.update_file_count()
            self.status_label.setText("Cleared all files")

    def update_file_count(self):
        count = len(self.selected_files)
        self.file_count_label.setText(f"Files: {count}")

    def start_processing(self):
        if not self.selected_files:
            QMessageBox.warning(self, "Warning", "No files selected!")
            return
            
        output_dir = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if not output_dir:
            return
            
        valid_files, invalid_files = self.batch_processor.validate_input_files(self.selected_files)
        
        if invalid_files:
            msg = f"Found {len(invalid_files)} invalid file(s):\n\n"
            msg += "\n".join(invalid_files[:5])
            if len(invalid_files) > 5:
                msg += f"\n... and {len(invalid_files) - 5} more"
            msg += f"\n\nProcess {len(valid_files)} valid file(s)?"
            
            reply = QMessageBox.question(
                self, "Invalid Files", msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # Read active radio values
        sel_mode_btn = self.detect_button_group.checkedButton()
        mode_val = sel_mode_btn.property("mode_val") if sel_mode_btn else "face"
        
        sel_effect_btn = self.effects_button_group.checkedButton()
        effect_val = sel_effect_btn.property("effect_val") if sel_effect_btn else "blur"

        settings = {
            'detection_mode': mode_val,
            'effect_type': effect_val,
            'is_pro': self._is_max(),
            'effect_params': {
                'blur_strength': BLUR_RANGE['default'],
                'pixel_size': PIXEL_RANGE['default'],
                'opacity': OPACITY_RANGE['default']
            }
        }

        self.processing = True
        self.total_files = len(valid_files)
        self.current_progress = 0
        self.failed_count = 0
        self.start_time = time.time()
        
        self.update_ui_state(processing=True)
        self.progress_bar.setValue(0)
        self.processed_label.setText(f"Processed: 0/{self.total_files}")
        self.failed_label.setText("Failed: 0")

        def process_worker():
            def progress_cb(current, total, result):
                self.signals.progress.emit(current, total, result)
                
            def error_cb(file_path, error_msg):
                self.signals.error.emit(file_path, error_msg)
                
            self.batch_processor.process_batch(
                valid_files,
                output_dir,
                settings,
                progress_callback=progress_cb,
                error_callback=error_cb,
                is_cancelled=lambda: not self.processing
            )
            
            self.signals.complete.emit()

        thread = threading.Thread(target=process_worker, daemon=True)
        thread.start()

    def stop_processing(self):
        reply = QMessageBox.question(
            self, "Confirm", "Stop processing?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.processing = False
            self.status_label.setText("Processing stopped by user")
            self.update_ui_state(processing=False)

    def on_progress(self, current, total, result):
        if not self.processing:
            return
        self.current_progress = current
        progress = int((current / total) * 100)
        self.progress_bar.setValue(progress)
        self.processed_label.setText(f"Processed: {current}/{total}")
        self.status_label.setText(f"Processing: {os.path.basename(result['input_path'])}")
        if self.start_time:
            elapsed = int(time.time() - self.start_time)
            self.time_label.setText(f"Time: {elapsed}s")

    def on_error(self, file_path, error_msg):
        self.failed_count += 1
        self.failed_label.setText(f"Failed: {self.failed_count}")
        self.logger.error(f"Failed to process {file_path}: {error_msg}")

    def on_complete(self):
        self.processing = False
        self.update_ui_state(processing=False)
        
        success_count = self.current_progress - self.failed_count
        
        msg = f"Batch processing complete!\n\n"
        msg += f"✅ Successful: {success_count}\n"
        msg += f"❌ Failed: {self.failed_count}\n"
        msg += f"📊 Total: {self.total_files}"
        
        QMessageBox.information(self, "Complete", msg)
        self.status_label.setText("Processing complete!")

    def update_ui_state(self, processing):
        self.add_btn.setEnabled(not processing)
        self.add_folder_btn.setEnabled(not processing)
        self.remove_btn.setEnabled(not processing)
        self.clear_btn.setEnabled(not processing)
        self.start_btn.setEnabled(not processing)
        self.close_btn.setEnabled(not processing)
        self.stop_btn.setEnabled(processing)

    def closeEvent(self, event):
        if self.processing:
            reply = QMessageBox.question(
                self, "Confirm", "Processing in progress. Close anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.processing = False
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
