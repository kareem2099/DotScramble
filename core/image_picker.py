import os
import cv2
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
from config import COLORS

class ImagePicker:
    def __init__(self, parent):
        self.parent = parent
        self.selected_path = None
        self.current_folder = os.path.expanduser("~") 

    def open(self, initial_dir=None):
        """Open custom image picker with spacious layout."""
        if initial_dir and os.path.exists(initial_dir):
            self.current_folder = initial_dir

        # Create Window
        self.window = tk.Toplevel(self.parent)
        self.window.title("File Browser - Select Image")
        self.window.geometry("1100x700")
        self.window.configure(bg=COLORS['bg_dark'])
        self.window.transient(self.parent)
        self.window.grab_set()

        # --- 1. CONFIGURATION (The Spacing Magic) ---
        style = ttk.Style()
        # 'rowheight' adds the space you asked for (30px per item)
        style.configure("Picker.Treeview", 
                        background=COLORS['bg_light'], 
                        foreground="white", 
                        fieldbackground=COLORS['bg_light'],
                        rowheight=35,  
                        font=("Helvetica", 11))
        
        # Highlight color
        style.map("Picker.Treeview", 
                  background=[('selected', COLORS['accent_cyan'])],
                  foreground=[('selected', 'black')])

        # --- 2. TOP BAR ---
        top_bar = tk.Frame(self.window, bg=COLORS['bg_medium'], height=40)
        top_bar.pack(fill="x", padx=5, pady=5)

        btn_up = tk.Button(top_bar, text="⬆️ Up", command=self.go_up,
                           bg=COLORS['bg_light'], fg="white", relief="flat")
        btn_up.pack(side="left", padx=5)

        self.path_var = tk.StringVar(value=self.current_folder)
        self.entry_path = tk.Entry(top_bar, textvariable=self.path_var, 
                                   bg=COLORS['bg_dark'], fg="white", 
                                   insertbackground="white", font=("Consolas", 11))
        self.entry_path.pack(side="left", padx=10, fill="x", expand=True)
        self.entry_path.bind("<Return>", self.on_path_enter)

        btn_go = tk.Button(top_bar, text="Go", command=self.on_path_enter,
                           bg=COLORS['accent_cyan'], fg="black", relief="flat")
        btn_go.pack(side="left", padx=5)

        # --- 3. MAIN LAYOUT ---
        main_frame = tk.Frame(self.window, bg=COLORS['bg_dark'])
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # Sidebar
        sidebar = tk.Frame(main_frame, bg=COLORS['bg_medium'], width=150)
        sidebar.pack(side="left", fill="y", padx=(0, 5))
        sidebar.pack_propagate(False)

        tk.Label(sidebar, text="Quick Access", bg=COLORS['bg_medium'], 
                 fg=COLORS['accent_cyan'], font=("Helvetica", 10, "bold")).pack(pady=10)

        home = os.path.expanduser("~")
        shortcuts = [
            ("🏠 Home", home),
            ("🖥️ Desktop", os.path.join(home, "Desktop")),
            ("📥 Downloads", os.path.join(home, "Downloads")),
            ("🖼️ Pictures", os.path.join(home, "Pictures")),
            ("💿 Root", "/")
        ]

        for name, path in shortcuts:
            tk.Button(sidebar, text=name, anchor="w",
                      command=lambda p=path: self.load_folder(p),
                      bg=COLORS['bg_dark'], fg="white", relief="flat", padx=10)\
                      .pack(fill="x", pady=2, padx=5)

        # Split View
        paned = tk.PanedWindow(main_frame, orient="horizontal", bg=COLORS['bg_dark'], sashwidth=4)
        paned.pack(side="left", fill="both", expand=True)

        # --- FILE LIST (Changed to Treeview for Spacing) ---
        list_frame = tk.Frame(paned, bg=COLORS['bg_medium'])
        
        # We use Treeview instead of Listbox to support 'rowheight'
        self.tree = ttk.Treeview(list_frame, show="tree", 
                                 style="Picker.Treeview", selectmode="browse")
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        
        paned.add(list_frame)

        # Preview Area
        preview_frame = tk.Frame(paned, bg=COLORS['bg_dark'])
        self.preview_label = tk.Label(preview_frame, text="No Image Selected", 
                                      bg=COLORS['bg_dark'], fg=COLORS['text_gray'])
        self.preview_label.place(relx=0.5, rely=0.4, anchor="center")
        
        btn_select = tk.Button(preview_frame, text="✅ Open Image", 
                               command=self.confirm_selection,
                               bg=COLORS['accent_green'], fg="white",
                               font=("Helvetica", 12, "bold"), padx=20, pady=10)
        btn_select.pack(side="bottom", pady=20)
        
        paned.add(preview_frame)

        # Bindings
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<Double-Button-1>", self.on_double_click)
        self.window.protocol("WM_DELETE_WINDOW", self.window.destroy)

        self.load_folder(self.current_folder)
        self.parent.wait_window(self.window)
        return self.selected_path

    def load_folder(self, path):
        if not os.path.exists(path): return

        try:
            items = sorted(os.listdir(path))
        except PermissionError:
            messagebox.showerror("Error", "Access Denied")
            return

        # Clear existing
        for item in self.tree.get_children():
            self.tree.delete(item)

        self.current_folder = path
        self.path_var.set(path)

        # Add Parent Directory option
        parent = os.path.dirname(path)
        if parent and parent != path:
            # We store the full path in 'values' so we don't have to parse text later
            self.tree.insert("", tk.END, text="📁 .. (Parent Directory)", values=(parent, "dir"))

        valid_exts = ('.jpg', '.jpeg', '.png', '.bmp', '.webp', '.tiff')

        # Insert Folders
        for item in items:
            full_path = os.path.join(path, item)
            if not item.startswith('.') and os.path.isdir(full_path):
                self.tree.insert("", tk.END, text=f"📁 {item}", values=(full_path, "dir"))

        # Insert Files
        for item in items:
            if item.lower().endswith(valid_exts):
                full_path = os.path.join(path, item)
                self.tree.insert("", tk.END, text=f"🖼️ {item}", values=(full_path, "file"))

    def on_select(self, event):
        selected_id = self.tree.selection()
        if not selected_id: return

        # Get the full path we stored in 'values'
        item_values = self.tree.item(selected_id[0])['values']
        if not item_values: return # Should not happen

        full_path, item_type = item_values[0], item_values[1]

        if item_type == "dir":
            self.preview_label.config(image='', text=f"Folder: {os.path.basename(full_path)}")
            return

        # Load Preview
        try:
            img = cv2.imread(full_path)
            if img is not None:
                img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                h, w = img.shape[:2]
                max_size = 400
                scale = min(max_size/w, max_size/h)
                new_w, new_h = int(w*scale), int(h*scale)
                img = cv2.resize(img, (new_w, new_h))
                photo = ImageTk.PhotoImage(Image.fromarray(img))
                self.preview_label.config(image=photo, text="")
                self.preview_label.image = photo
        except Exception:
            pass

    def on_double_click(self, event):
        selected_id = self.tree.selection()
        if not selected_id: return

        item_values = self.tree.item(selected_id[0])['values']
        full_path, item_type = item_values[0], item_values[1]

        if item_type == "dir":
            self.load_folder(full_path)
        else:
            self.selected_path = full_path
            self.window.destroy()

    def confirm_selection(self):
        selected_id = self.tree.selection()
        if not selected_id: return

        item_values = self.tree.item(selected_id[0])['values']
        full_path, item_type = item_values[0], item_values[1]

        if item_type == "dir":
            self.load_folder(full_path)
        else:
            self.selected_path = full_path
            self.window.destroy()

    def go_up(self):
        parent = os.path.dirname(self.current_folder)
        if parent and parent != self.current_folder:
            self.load_folder(parent)

    def on_path_enter(self, event=None):
        path = self.path_var.get()
        if os.path.isdir(path):
            self.load_folder(path)