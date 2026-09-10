# THE REEL ARCHIVE
# Timeline uses ORIGINAL RELEASE DATE only.
# PRINT DATE remains a separate field.

import os
import shutil
import sqlite3
import subprocess
import random
import tempfile
import tkinter as tk
import pygame
from tkinter import ttk, filedialog, messagebox
from datetime import datetime
import re
import math
import sys
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "film_vault.db")
IMAGE_DIR = os.path.join(BASE_DIR, "film_images")
os.makedirs(IMAGE_DIR, exist_ok=True)

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    from reportlab.pdfgen import canvas as pdf_canvas
    from reportlab.lib.units import inch
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


BG = "#0b0b0b"
BG_2 = "#111111"
PANEL = "#151515"
PANEL_2 = "#1b1b1b"
GOLD = "#c8a45d"
GOLD_LIGHT = "#e1c27a"
TEXT = "#eeeeee"
TEXT_MUTED = "#b7b7b7"
TEXT_DIM = "#777777"
BORDER = "#292929"
RED = "#b85c5c"
GREEN = "#79a66a"
HOVER = "#1d1d1d"
INPUT_BG = "#202020"

# Pygame Reel Runner settings
WIDTH = 1100
HEIGHT = 650
FPS = 60
SCORE_FILE = os.path.join(BASE_DIR, "reel_runner_high_score.json")
BLACK = "#000000"


# Supported film formats for the public Film Vault edition.
FILM_FORMATS = [
    "8MM",
    "SUPER 8",
    "SINGLE 8",
    "9.5MM",
    "16MM",
    "SUPER 16",
    "ULTRA 16",
    "17.5MM",
    "28MM",
    "35MM",
    "35MM 3D",
    "65MM",
    "70MM",
    "70MM 5-PERF",
    "70MM 8-PERF",
    "70MM 3D",
    "IMAX 15/70",
    "OTHER FILM"
]


# ============================================================
# DATABASE
# ============================================================

def initialize_database():
    connection = sqlite3.connect(DB_FILE)
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS films (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            original_title TEXT,
            format TEXT,
            film_stock TEXT,
            print_date TEXT,
            film_length TEXT,
            runtime TEXT,
            sound TEXT,
            country TEXT,
            condition TEXT,
            vinegar_syndrome TEXT,
            shrunken TEXT,
            needs_repair TEXT,
            projectable TEXT,
            splices TEXT,
            notes TEXT,
            main_image TEXT,
            additional_images TEXT,
            created_at TEXT,
            updated_at TEXT,
            raw_video TEXT DEFAULT '',
            restored_video TEXT DEFAULT '',
            release_date TEXT DEFAULT ''
        )
    """)

    columns = {
        row[1]
        for row in cursor.execute("PRAGMA table_info(films)").fetchall()
    }

    if "raw_video" not in columns:
        cursor.execute(
            "ALTER TABLE films ADD COLUMN raw_video TEXT DEFAULT ''"
        )

    if "restored_video" not in columns:
        cursor.execute(
            "ALTER TABLE films ADD COLUMN restored_video TEXT DEFAULT ''"
        )

    # NEW:
    # This is the actual date/year the film was released.
    # It is deliberately separate from print_date.
    if "release_date" not in columns:
        cursor.execute(
            "ALTER TABLE films ADD COLUMN release_date TEXT DEFAULT ''"
        )

    # FILM PROVENANCE
    provenance_columns = {
        "acquired_from": "TEXT DEFAULT ''",
        "previous_owner": "TEXT DEFAULT ''",
        "purchase_date": "TEXT DEFAULT ''",
        "purchase_price": "TEXT DEFAULT ''",
        "source_website": "TEXT DEFAULT ''",
        "provenance_notes": "TEXT DEFAULT ''"
    }

    for column_name, definition in provenance_columns.items():
        if column_name not in columns:
            cursor.execute(
                f"ALTER TABLE films ADD COLUMN {column_name} {definition}"
            )

    connection.commit()
    connection.close()


# ============================================================
# VLC
# ============================================================

def find_vlc():
    possible = [
        shutil.which("vlc"),
        r"C:\Program Files\VideoLAN\VLC\vlc.exe",
        r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
        os.path.expandvars(
            r"%LOCALAPPDATA%\Programs\VideoLAN\VLC\vlc.exe"
        )
    ]

    for path in possible:
        if path and os.path.isfile(path):
            return path

    return None


def open_video_in_vlc(path):
    if not path:
        messagebox.showinfo(
            "No Digital Copy",
            "No video location has been assigned to this version."
        )
        return

    path = os.path.abspath(
        os.path.expanduser(str(path).strip())
    )

    if not os.path.isfile(path):
        messagebox.showerror(
            "Video Not Found",
            "The saved video location could not be found:\n\n"
            + path +
            "\n\nYou can update the location in Edit Film."
        )
        return

    vlc = find_vlc()

    if not vlc:
        messagebox.showerror(
            "VLC Not Found",
            "VLC could not be found on this computer."
        )
        return

    try:
        subprocess.Popen(
            [
                vlc,
                "--no-one-instance",
                "--started-from-file",
                path
            ],
            cwd=os.path.dirname(vlc),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception as error:
        messagebox.showerror(
            "Could Not Play Video",
            str(error)
        )


# ============================================================
# HELPERS
# ============================================================

def extract_year(value):
    if not value:
        return None

    matches = re.findall(
        r"\b(18\d{2}|19\d{2}|20\d{2}|21\d{2})\b",
        str(value)
    )

    if not matches:
        return None

    return int(matches[0])


def timeline_date_key(value):
    if not value:
        return (9999, 12, 31)

    text = str(value).strip()

    year = extract_year(text)

    if year is None:
        return (9999, 12, 31)

    month = 1
    day = 1

    match = re.search(
        r"\b\d{4}[-/](\d{1,2})(?:[-/](\d{1,2}))?",
        text
    )

    if match:
        try:
            month = max(1, min(12, int(match.group(1))))
        except Exception:
            month = 1

        if match.group(2):
            try:
                day = max(1, min(31, int(match.group(2))))
            except Exception:
                day = 1

    return (year, month, day)


# ============================================================
# MAIN APPLICATION
# ============================================================

class InAppPage(tk.Frame):
    """A full-screen in-app page that replaces the old Toplevel dialogs."""
    def __init__(self, app, title=""):
        super().__init__(app, bg=BG)
        self.app = app
        self.page_title = title
        self._closed = False
        self.place(x=0, y=0, relwidth=1, relheight=1)
        self.lift()
        self._back_button = tk.Button(
            self,
            text="← BACK",
            command=self.go_back,
            bg=PANEL_2,
            fg=TEXT,
            activebackground=GOLD,
            activeforeground="#080808",
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Helvetica", 9, "bold"),
            padx=16,
            pady=8
        )
        self._back_button.place(relx=1.0, x=-24, y=18, anchor="ne")
        self._back_button.lift()

        # Keep every in-app page responsive when the main window is resized.
        # Navigation remains pinned to the page instead of using fixed
        # window coordinates.
        self.bind("<Configure>", self._responsive_page, add="+")
        self.bind("<Escape>", lambda e: self.go_back())

    def _responsive_page(self, event=None):
        # Keep the back button visible at the top-right as the page changes
        # size.  Child widgets using pack(fill="both", expand=True) naturally
        # follow the available page size.
        if hasattr(self, "_back_button") and self._back_button.winfo_exists():
            self._back_button.place_configure(relx=1.0, x=-24, y=18, anchor="ne")
            self._back_button.lift()

    # Compatibility methods used by the old dialog code.
    def title(self, value=None):
        if value is not None:
            self.page_title = value
        return self.page_title

    def geometry(self, *args, **kwargs):
        return None

    def minsize(self, *args, **kwargs):
        # In-app pages inherit the main window size; do not allow a page to
        # demand a smaller virtual size than the main responsive layout.
        return None

    def resizable(self, *args, **kwargs):
        return None

    def transient(self, *args, **kwargs):
        return None

    def grab_set(self, *args, **kwargs):
        return None

    def grab_release(self, *args, **kwargs):
        return None

    def protocol(self, name, func):
        # WM_DELETE_WINDOW is represented by the in-app BACK behavior.
        if name == "WM_DELETE_WINDOW":
            self._close_callback = func

    def go_back(self):
        """Return to the requested root page. Most pages always return to the main menu.
        Film view/editor pages may explicitly request the Database as their return target.
        """
        target = getattr(self, "return_target", "menu")
        app = self.app
        app._navigating_back = True
        try:
            # Close every stacked in-app page so BACK never lands on another page.
            for page in list(getattr(app, "_page_stack", [])):
                if page is not self and getattr(page, "winfo_exists", lambda: False)():
                    try:
                        page.destroy()
                    except Exception:
                        pass
            self.destroy()
        finally:
            app._navigating_back = False

        if target == "database":
            if hasattr(app, "close_start_menu"):
                app.close_start_menu()
            app.lift()
            if hasattr(app, "refresh_archive"):
                app.refresh_archive()
        else:
            app.show_start_menu()

    def destroy(self):
        if self._closed:
            return
        self._closed = True
        callback = getattr(self, "_close_callback", None)
        try:
            super().destroy()
        finally:
            if hasattr(self.app, "_page_stack") and self in self.app._page_stack:
                self.app._page_stack.remove(self)
            if callback and callback is not self.destroy:
                try:
                    callback()
                except Exception:
                    pass
            # Normal destruction does not decide navigation.  The BACK button
            # explicitly chooses the destination; this prevents nested pages from
            # unexpectedly reappearing when the user presses BACK.
            if getattr(self.app, "_navigating_back", False):
                return
            if hasattr(self.app, "_page_stack") and self.app._page_stack:
                self.app._page_stack[-1].lift()
            elif hasattr(self.app, "start_menu") and self.app.start_menu.winfo_exists():
                self.app.start_menu.lift()


class FilmVault(tk.Tk):

    def __init__(self):
        super().__init__()

        self.title("The Reel Archive")
        self.geometry("1250x820")
        # Keep the archive large enough that the responsive layouts never
        # clip their navigation or primary controls.
        self.minsize(1050, 720)
        self.configure(bg=BG)

        self.films = []
        self.image_cache = {}
        self._page_stack = []
        self._navigating_back = False

        self.search_var = tk.StringVar()
        self.format_var = tk.StringVar(value="ALL FORMATS")

        self.search_var.trace_add(
            "write",
            lambda *args: self.refresh_archive()
        )

        self.format_var.trace_add(
            "write",
            lambda *args: self.refresh_archive()
        )

        self.load_films()
        self.build_ui()
        self.refresh_archive()


    def new_page(self, title=""):
        page = InAppPage(self, title)
        self._page_stack.append(page)
        page.lift()
        page._back_button.lift()
        return page


    # ========================================================
    # LOAD FILMS
    # ========================================================

    def load_films(self):
        connection = sqlite3.connect(DB_FILE)
        cursor = connection.cursor()

        cursor.execute("""
            SELECT
                id,
                title,
                original_title,
                format,
                film_stock,
                print_date,
                film_length,
                runtime,
                sound,
                country,
                condition,
                vinegar_syndrome,
                shrunken,
                needs_repair,
                projectable,
                splices,
                notes,
                main_image,
                additional_images,
                created_at,
                updated_at,
                raw_video,
                restored_video,
                release_date,
                acquired_from,
                previous_owner,
                purchase_date,
                purchase_price,
                source_website,
                provenance_notes
            FROM films
            ORDER BY title COLLATE NOCASE ASC
        """)

        self.films = cursor.fetchall()
        connection.close()


    # ========================================================
    # UI
    # ========================================================

    def build_ui(self):

        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=30, pady=(24, 8))

        title_frame = tk.Frame(header, bg=BG)
        title_frame.pack(side="left")

        tk.Label(
            title_frame,
            text="THE",
            bg=BG,
            fg=GOLD,
            font=("Helvetica", 19, "bold")
        ).pack(anchor="w")

        tk.Label(
            title_frame,
            text="REEL ARCHIVE",
            bg=BG,
            fg=TEXT,
            font=("Helvetica", 32, "bold")
        ).pack(anchor="w")

        tk.Label(
            title_frame,
            text="8MM  •  SUPER 8  •  9.5MM  •  16MM  •  35MM  •  70MM  •  IMAX",
            bg=BG,
            fg=TEXT_MUTED,
            font=("Helvetica", 10, "bold")
        ).pack(anchor="w", pady=(2, 0))

        reel_canvas = tk.Canvas(
            header,
            width=100,
            height=100,
            bg=BG,
            highlightthickness=0
        )
        reel_canvas.pack(side="right", padx=15)

        reel_canvas.create_oval(
            10, 10, 90, 90,
            outline=GOLD,
            width=3
        )

        reel_canvas.create_oval(
            38, 38, 62, 62,
            outline=GOLD_LIGHT,
            width=3
        )

        for angle in range(0, 360, 60):
            x1 = 50 + math.cos(math.radians(angle)) * 17
            y1 = 50 + math.sin(math.radians(angle)) * 17
            x2 = 50 + math.cos(math.radians(angle)) * 31
            y2 = 50 + math.sin(math.radians(angle)) * 31

            reel_canvas.create_line(
                x1, y1, x2, y2,
                fill=GOLD,
                width=5
            )

        controls = tk.Frame(self, bg=BG)
        controls.pack(fill="x", padx=30, pady=(12, 12))

        search_frame = tk.Frame(
            controls,
            bg=PANEL_2,
            highlightbackground=BORDER,
            highlightthickness=1
        )
        search_frame.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(0, 10)
        )

        tk.Label(
            search_frame,
            text="⌕",
            bg=PANEL_2,
            fg=GOLD,
            font=("Helvetica", 18)
        ).pack(side="left", padx=(12, 5))

        tk.Entry(
            search_frame,
            textvariable=self.search_var,
            bg=PANEL_2,
            fg=TEXT,
            insertbackground=GOLD,
            relief="flat",
            bd=0,
            font=("Helvetica", 11)
        ).pack(
            side="left",
            fill="x",
            expand=True,
            pady=11
        )

        self.format_combo = ttk.Combobox(
            controls,
            textvariable=self.format_var,
            values=["ALL FORMATS"],
            state="readonly",
            width=14
        )
        self.format_combo.pack(side="left", padx=(0, 10))
        self.update_format_filter()

        tk.Button(
            controls,
            text="← BACK TO MENU",
            bg=PANEL_2,
            fg=TEXT,
            activebackground=GOLD,
            activeforeground="#080808",
            relief="flat",
            bd=0,
            font=("Helvetica", 9, "bold"),
            padx=14,
            pady=10,
            cursor="hand2",
            command=self.show_menu_from_database
        ).pack(side="right", padx=(0, 10))

        tk.Button(
            controls,
            text="+ ADD FILM",
            bg=GOLD,
            fg="#080808",
            activebackground=GOLD_LIGHT,
            relief="flat",
            bd=0,
            font=("Helvetica", 10, "bold"),
            padx=18,
            pady=10,
            cursor="hand2",
            command=lambda: self.open_add_dialog(return_target="database")
        ).pack(side="right")

        self.stats_frame = tk.Frame(self, bg=BG)
        self.stats_frame.pack(
            fill="x",
            padx=30,
            pady=(0, 12)
        )

        archive_container = tk.Frame(self, bg=BG)
        archive_container.pack(
            fill="both",
            expand=True,
            padx=30,
            pady=(0, 25)
        )

        self.archive_canvas = tk.Canvas(
            archive_container,
            bg=BG,
            highlightthickness=0
        )

        scrollbar = ttk.Scrollbar(
            archive_container,
            orient="vertical",
            command=self.archive_canvas.yview
        )

        self.archive_canvas.configure(
            yscrollcommand=scrollbar.set
        )

        self.archive_canvas.pack(
            side="left",
            fill="both",
            expand=True
        )

        scrollbar.pack(side="right", fill="y")

        self.archive_canvas.bind(
            "<Button-1>",
            self.archive_click
        )

        self.archive_canvas.bind(
            "<Motion>",
            self.archive_motion
        )

        self.archive_canvas.bind(
            "<MouseWheel>",
            self.archive_mousewheel
        )

        # IMPORTANT: show the in-app warning synchronously before the Tk mainloop
        # starts. This prevents the main menu from appearing first.
        self.show_start_warning()


    def show_start_warning(self):
        """Show the required software warning before the main menu."""
        if hasattr(self, "start_warning") and self.start_warning.winfo_exists():
            self.start_warning.lift()
            return

        self.start_warning = tk.Frame(self, bg=BG)
        self.start_warning.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.start_warning.grid_rowconfigure(0, weight=1)
        self.start_warning.grid_columnconfigure(0, weight=1)

        outer = tk.Frame(
            self.start_warning,
            bg=BG,
            highlightbackground=GOLD,
            highlightthickness=1
        )
        outer.grid(row=0, column=0, sticky="nsew", padx=45, pady=45)
        outer.grid_rowconfigure(3, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        header = tk.Frame(outer, bg=BG)
        header.grid(row=0, column=0, sticky="ew", padx=35, pady=(45, 20))

        tk.Label(
            header, text="THE", bg=BG, fg=GOLD,
            font=("Helvetica", 20, "bold")
        ).pack()
        tk.Label(
            header, text="REEL ARCHIVE", bg=BG, fg=TEXT,
            font=("Helvetica", 38, "bold")
        ).pack()
        tk.Label(
            header, text="IMPORTANT NOTICE", bg=BG, fg=GOLD_LIGHT,
            font=("Helvetica", 13, "bold")
        ).pack(pady=(12, 0))

        notice = tk.Frame(
            outer, bg=PANEL_2,
            highlightbackground=BORDER, highlightthickness=1
        )
        notice.grid(row=1, column=0, sticky="nsew", padx=70, pady=(0, 20))
        notice.grid_columnconfigure(0, weight=1)
        notice.grid_rowconfigure(0, weight=1)

        warning_text = (
            "The Reel Archive is FREE software and is provided as-is. "
            "Please obtain it only from my official release pages or authorized distribution channels.\n\n"
            "DO NOT PIRATE OR DISTRIBUTE UNAUTHORIZED COPIES.\n"
            "Do not copy, re-upload, sell, crack, modify, or redistribute The Reel Archive without my consent.\n\n"
            "WHAT IF YOU COPY AND DISTRIBUTE MY SOFTWARE WITHOUT MY CONSENT?\n"
            "Unauthorized distribution may result in takedown requests, copyright or platform reports, "
            "removal of the unauthorized copy, account penalties, and, where applicable, legal action or "
            "other remedies available under copyright law.\n\n"
            "I am not responsible for viruses, malware, corrupted files, or other damage caused by unofficial "
            "or modified copies."
        )

        warning_label = tk.Label(
            notice, text=warning_text, bg=PANEL_2, fg=TEXT_MUTED,
            font=("Helvetica", 11), justify="center", wraplength=900,
            padx=35, pady=30
        )
        warning_label.grid(row=0, column=0, sticky="nsew")

        continue_button = tk.Button(
            outer,
            text="I UNDERSTAND — CONTINUE",
            command=self.accept_start_warning,
            bg=PANEL_2, fg=TEXT,
            activebackground=GOLD, activeforeground="#080808",
            relief="flat", bd=0, cursor="hand2",
            font=("Helvetica", 12, "bold"),
            padx=28, pady=14
        )
        continue_button.grid(row=2, column=0, pady=(0, 15))

        tk.Label(
            outer,
            text="The main menu will open after you continue.",
            bg=BG, fg=TEXT_DIM,
            font=("Helvetica", 9)
        ).grid(row=3, column=0, sticky="s", pady=(0, 25))

        self.start_warning.bind("<Configure>",
            lambda event: self._resize_start_warning(event, warning_label),
            add="+"
        )
        self.start_warning.bind("<Escape>", lambda event: self.destroy())
        self.start_warning.lift()

    def _resize_start_warning(self, event, warning_label):
        try:
            width = max(420, self.start_warning.winfo_width() - 180)
            warning_label.configure(wraplength=min(1000, width))
        except tk.TclError:
            pass

    def accept_start_warning(self):
        if hasattr(self, "start_warning") and self.start_warning.winfo_exists():
            self.start_warning.destroy()
        self.show_start_menu()

    def _start_menu_image_path(self, film):
        try:
            path = film[17]
        except (IndexError, TypeError):
            return None
        if not path:
            return None
        if not os.path.isabs(path):
            path = os.path.join(BASE_DIR, path)
        return path if os.path.isfile(path) else None

    def _prepare_start_menu_background_images(self):
        """Build faded thumbnail images from films that have cover art."""
        if not PIL_AVAILABLE:
            return []

        paths = []
        seen = set()
        for film in self.films:
            path = self._start_menu_image_path(film)
            if path and path not in seen:
                seen.add(path)
                paths.append(path)

        if not paths:
            return []

        # A little randomness keeps the streams from looking too uniform.
        random.shuffle(paths)
        paths = paths[:32]

        prepared = []
        for path in paths:
            try:
                image = Image.open(path).convert("RGBA")
                image.thumbnail((105, 135), Image.LANCZOS)

                # Fade the artwork so the menu remains readable and the effect
                # feels more like a subtle Matrix-style background.
                alpha = image.getchannel("A").point(lambda value: int(value * 0.30))
                image.putalpha(alpha)

                prepared.append(ImageTk.PhotoImage(image))
            except Exception:
                continue

        return prepared

    def _start_menu_background_tick(self):
        if not hasattr(self, "start_bg_canvas") or not self.start_bg_canvas.winfo_exists():
            return

        try:
            width = max(1, self.start_bg_canvas.winfo_width())
            height = max(1, self.start_bg_canvas.winfo_height())

            # One picture per stream. All streams use the same speed, so their
            # vertical spacing stays fixed and pictures cannot catch up.
            for stream in getattr(self, "_start_bg_streams", []):
                stream["y"] += stream["speed"]

                if stream["y"] > height + 160:
                    # Choose artwork that is not currently visible elsewhere.
                    used = {
                        other["photo_index"]
                        for other in self._start_bg_streams
                        if other is not stream
                    }
                    choices = [
                        i for i in range(len(self._start_bg_photos))
                        if i not in used
                    ]
                    if not choices:
                        choices = list(range(len(self._start_bg_photos)))

                    stream["photo_index"] = random.choice(choices)
                    self.start_bg_canvas.itemconfigure(
                        stream["item"],
                        image=self._start_bg_photos[stream["photo_index"]]
                    )

                    highest = min(
                        (other["y"] for other in self._start_bg_streams
                         if other is not stream),
                        default=-200
                    )
                    stream["y"] = min(-170, highest - stream["safe_gap"])

                self.start_bg_canvas.coords(
                    stream["item"], stream["x"], stream["y"]
                )

            self._start_bg_after_id = self.after(35, self._start_menu_background_tick)
        except tk.TclError:
            pass

    def _stop_start_menu_background(self):
        after_id = getattr(self, "_start_bg_after_id", None)
        if after_id:
            try:
                self.after_cancel(after_id)
            except Exception:
                pass
        self._start_bg_after_id = None

        canvas = getattr(self, "start_bg_canvas", None)
        if canvas is not None:
            try:
                canvas.destroy()
            except Exception:
                pass
        self.start_bg_canvas = None
        self._start_bg_streams = []
        self._start_bg_photos = []

    def _start_menu_background_resize(self, event=None):
        if not hasattr(self, "start_bg_canvas") or not self.start_bg_canvas.winfo_exists():
            return
        try:
            self.start_bg_canvas.configure(width=max(1, self.winfo_width()), height=max(1, self.winfo_height()))
        except tk.TclError:
            pass

    def _build_start_menu_background(self):
        self._stop_start_menu_background()

        self.start_bg_canvas = tk.Canvas(
            self.start_menu,
            bg="#080808",
            highlightthickness=0,
            bd=0
        )
        self.start_bg_canvas.place(relx=0, rely=0, relwidth=1, relheight=1)

        self._start_bg_photos = self._prepare_start_menu_background_images()
        self._start_bg_streams = []

        if not self._start_bg_photos:
            return

        width = max(900, self.winfo_width())
        height = max(650, self.winfo_height())

        # Only create one stream for each unique picture. This prevents
        # duplicate artwork from appearing on screen at the same time.
        stream_count = min(
            len(self._start_bg_photos),
            max(6, min(11, width // 135))
        )

        column_width = width / stream_count
        speed = 1.35
        safe_gap = 185
        spacing = max(safe_gap, (height + 900) / stream_count)

        photo_indices = list(range(len(self._start_bg_photos)))
        random.shuffle(photo_indices)

        for column in range(stream_count):
            x = int((column + 0.5) * column_width)
            y = -height - 250 + column * spacing
            photo_index = photo_indices[column]

            item_id = self.start_bg_canvas.create_image(
                x,
                y,
                image=self._start_bg_photos[photo_index],
                anchor="center"
            )

            self._start_bg_streams.append({
                "x": x,
                "y": y,
                "speed": speed,
                "safe_gap": safe_gap,
                "photo_index": photo_index,
                "item": item_id,
            })

        self.start_bg_canvas.bind(
            "<Configure>", self._start_menu_background_resize, add="+"
        )
        self._start_bg_after_id = self.after(35, self._start_menu_background_tick)

    def show_start_menu(self):
        if hasattr(self, "start_menu") and self.start_menu.winfo_exists():
            self.start_menu.lift()
            if hasattr(self, "start_bg_canvas") and self.start_bg_canvas.winfo_exists():
                    return

        self.start_menu = tk.Frame(self, bg=BG)
        self.start_menu.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.start_menu.lift()

        # Faded falling film artwork forms the animated background.
        self._build_start_menu_background()

        # Keep the menu in a centered cinematic panel so the falling artwork
        # remains visible around it.
        outer = tk.Frame(
            self.start_menu,
            bg=BG,
            highlightbackground=BORDER,
            highlightthickness=1
        )
        outer.place(relx=0.5, rely=0.5, relwidth=0.66, relheight=0.78, anchor="center")
        outer.grid_rowconfigure(3, weight=1)
        outer.grid_columnconfigure(0, weight=1)
        outer.grid_columnconfigure(1, weight=1)

        header = tk.Frame(outer, bg=BG)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=24, pady=(34, 8))

        tk.Label(
            header, text="THE", bg=BG, fg=GOLD,
            font=("Helvetica", 18, "bold")
        ).pack()
        tk.Label(
            header, text="REEL ARCHIVE", bg=BG, fg=TEXT,
            font=("Helvetica", 34, "bold")
        ).pack()
        tk.Label(
            header, text="FILM COLLECTION & ARCHIVE", bg=BG, fg=TEXT_MUTED,
            font=("Helvetica", 10, "bold")
        ).pack(pady=(0, 2))

        buttons = tk.Frame(outer, bg=BG)
        buttons.grid(row=1, column=0, columnspan=2, sticky="ew", padx=65, pady=(22, 8))
        buttons.grid_columnconfigure(0, weight=1)
        buttons.grid_columnconfigure(1, weight=1)

        menu_items = [
            ("DATABASE", self.close_start_menu),
            ("GAMES", self.start_menu_games),
            ("CREDITS", self.start_menu_credits),
            ("SETTINGS", self.start_menu_settings),
        ]
        for i, (label, command) in enumerate(menu_items):
            r, c = divmod(i, 2)
            btn = tk.Button(
                buttons, text=label, command=command,
                bg=PANEL_2, fg=TEXT,
                activebackground=GOLD, activeforeground="#080808",
                relief="flat", bd=0, cursor="hand2",
                font=("Helvetica", 11, "bold"),
                padx=18, pady=13
            )
            btn.grid(row=r, column=c, sticky="ew", padx=6, pady=5)

        tk.Frame(outer, bg=BG).grid(
            row=2, column=0, columnspan=2, sticky="nsew"
        )

        credits = tk.Frame(outer, bg=BG)
        credits.grid(row=3, column=0, columnspan=2, sticky="s", padx=20, pady=(4, 22))
        tk.Label(
            credits, text="Made by Jack Moorehead • Helped by ChatGPT",
            bg=BG, fg=TEXT_MUTED, font=("Helvetica", 9, "bold")
        ).pack()
        tk.Label(
            credits,
            text="Thank you for using The Reel Archive and helping preserve the magic of film!",
            bg=BG, fg=GOLD, font=("Helvetica", 9, "italic"),
            wraplength=900, justify="center"
        ).pack(pady=(3, 0))

        # Always keep the menu panel above the animated background canvas.
        outer.lift()
        self.start_menu.lift()

        self.start_menu.bind("<Escape>", lambda event: self.destroy())

    def close_start_menu(self):
        self._stop_start_menu_background()
        if hasattr(self, "start_menu") and self.start_menu.winfo_exists():
            self.start_menu.destroy()

    def show_menu_from_database(self):
        self.show_start_menu()

    def start_menu_games(self):
        self.close_start_menu()
        self.open_film_fun_menu(return_to_menu=True)

    def start_menu_credits(self):
        win = self.new_page()
        win.title("The Reel Archive — Credits")
        win.configure(bg=BG)
        tk.Label(win, text="THE", bg=BG, fg=GOLD, font=("Helvetica", 16, "bold")).pack(pady=(28, 0))
        tk.Label(win, text="REEL ARCHIVE", bg=BG, fg=TEXT, font=("Helvetica", 28, "bold")).pack()
        tk.Label(win, text="CREDITS", bg=BG, fg=TEXT_MUTED, font=("Helvetica", 10, "bold")).pack(pady=(0, 24))

        tk.Label(win, text="Made by Jack Moorehead", bg=BG, fg=TEXT, font=("Helvetica", 14, "bold")).pack(pady=5)
        tk.Label(win, text="Helped by ChatGPT", bg=BG, fg=GOLD, font=("Helvetica", 12)).pack(pady=5)
        tk.Label(
            win,
            text="Thank you for using The Reel Archive\nand helping preserve the magic of film!",
            bg=BG, fg=TEXT_MUTED, font=("Helvetica", 11), justify="center"
        ).pack(pady=24)


    def start_menu_settings(self):
        win = self.new_page()
        win.title("The Reel Archive — Settings")
        win.configure(bg=BG)
        tk.Label(win, text="SETTINGS", bg=BG, fg=GOLD, font=("Helvetica", 22, "bold")).pack(pady=(30, 20))
        tk.Label(
            win,
            text="The Reel Archive uses the cinematic black-and-gold archive theme.\nYour film database is stored locally and is not reset by changing app options.",
            bg=BG, fg=TEXT_MUTED, font=("Helvetica", 10), justify="center", wraplength=430
        ).pack(pady=15)


    def button(self, parent, text, command):
        return tk.Button(
            parent,
            text=text,
            bg=PANEL_2,
            fg=TEXT,
            activebackground="#292929",
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            font=("Helvetica", 9, "bold"),
            padx=16,
            pady=10,
            cursor="hand2",
            command=command
        )


    # ========================================================
    # FILTER
    # ========================================================

    def update_format_filter(self):
        """Show only film formats that actually exist in the database."""
        if not hasattr(self, "format_combo"):
            return

        present_formats = []
        seen = set()

        for film in self.films:
            value = str(film[3] or "").strip()
            if not value:
                continue

            key = value.upper()
            if key not in seen:
                seen.add(key)
                present_formats.append(value)

        # Sort by the master format order, while still allowing custom/
        # legacy values stored in the database to appear at the end.
        order = {name.upper(): index for index, name in enumerate(FILM_FORMATS)}
        present_formats.sort(key=lambda x: (order.get(x.upper(), len(FILM_FORMATS)), x.upper()))

        values = ["ALL FORMATS"] + present_formats
        current = self.format_var.get()

        self.format_combo["values"] = values

        # If a format was deleted and is no longer present, return to ALL.
        if current not in values:
            self.format_var.set("ALL FORMATS")


    def get_filtered_films(self):
        search = self.search_var.get().strip().lower()
        selected = self.format_var.get().strip().upper()

        results = []

        for film in self.films:

            if selected != "ALL FORMATS":
                if str(film[3] or "").strip().upper() != selected:
                    continue

            if search:
                searchable = " ".join(
                    str(v or "") for v in film
                ).lower()

                if search not in searchable:
                    continue

            results.append(film)

        return results


    # ========================================================
    # STATS
    # ========================================================

    def refresh_stats(self):

        for widget in self.stats_frame.winfo_children():
            widget.destroy()

        films = self.get_filtered_films()

        stats = [
            (
                "TOTAL FILMS",
                len(films)
            ),
            (
                "8MM",
                sum(
                    str(f[3]).upper() == "8MM"
                    for f in films
                )
            ),
            (
                "SUPER 8",
                sum(
                    str(f[3]).upper() == "SUPER 8"
                    for f in films
                )
            ),
            (
                "16MM",
                sum(
                    str(f[3]).upper() == "16MM"
                    for f in films
                )
            ),
            (
                "SOUND",
                sum(
                    str(f[8]).upper()
                    in ("YES", "SOUND", "TRUE", "1")
                    for f in films
                )
            ),
            (
                "NEEDS REPAIR",
                sum(
                    str(f[13]).upper()
                    in ("YES", "TRUE", "1")
                    for f in films
                )
            )
        ]

        for label, value in stats:

            box = tk.Frame(
                self.stats_frame,
                bg=PANEL,
                highlightbackground=BORDER,
                highlightthickness=1
            )

            box.pack(
                side="left",
                fill="x",
                expand=True,
                padx=(0, 6)
            )

            tk.Label(
                box,
                text=label,
                bg=PANEL,
                fg=TEXT_DIM,
                font=("Helvetica", 8, "bold")
            ).pack(pady=(9, 1))

            tk.Label(
                box,
                text=str(value),
                bg=PANEL,
                fg=GOLD_LIGHT,
                font=("Helvetica", 18, "bold")
            ).pack(pady=(0, 9))


    # ========================================================
    # ARCHIVE
    # ========================================================

    def refresh_archive(self):

        self.update_format_filter()
        self.refresh_stats()

        canvas = self.archive_canvas
        canvas.delete("all")

        films = self.get_filtered_films()

        width = max(canvas.winfo_width(), 900)
        y = 8

        if not films:

            empty_messages = [
                "NO ONE BUT US CHICKENS",
                "THE FILM CABINET IS SILENT",
                "NOT A SINGLE FRAME IN SIGHT",
                "WELL, THAT'S A WHOLE LOT OF NOTHING",
                "THE PROJECTOR IS READY. THE FILMS ARE NOT.",
                "THE VAULT HAS GONE AWOL",
                "NO FILMS HERE — TRY ANOTHER FILTER",
                "THE SCREEN IS EMPTY, JACK",
                "ALL QUIET ON THE FILM FRONT",
                "NOTHING BUT DUST AND SPLICING TAPE",
                "THE REEL IS EMPTY",
                "SORRY, FOLKS — NO PICTURES TONIGHT"
            ]

            message = random.choice(empty_messages)

            canvas.create_text(
                width // 2,
                160,
                text=message,
                fill=TEXT_DIM,
                font=("Helvetica", 16, "bold"),
                width=max(width - 100, 500),
                justify="center"
            )

            canvas.create_text(
                width // 2,
                205,
                text="Try another format or clear the filters.",
                fill=TEXT_DIM,
                font=("Helvetica", 10)
            )

            canvas.configure(
                scrollregion=(0, 0, width, 250)
            )

            return

        for film in films:

            film_id = film[0]
            tag = f"filmrow:{film_id}"
            row_height = 205

            canvas.create_rectangle(
                4,
                y,
                width - 8,
                y + row_height,
                fill=PANEL,
                outline=BORDER,
                tags=(tag,)
            )

            # COVER

            image_x = 20
            image_y = y + 15
            image_w = 165
            image_h = 175

            image_path = film[17]

            if image_path and PIL_AVAILABLE:

                try:
                    path = image_path

                    if not os.path.isabs(path):
                        path = os.path.join(BASE_DIR, path)

                    if os.path.isfile(path):

                        key = (path, image_w, image_h)

                        if key not in self.image_cache:

                            image = Image.open(path)
                            image.thumbnail((image_w, image_h))

                            self.image_cache[key] = ImageTk.PhotoImage(
                                image
                            )

                        canvas.create_image(
                            image_x + image_w / 2,
                            image_y + image_h / 2,
                            image=self.image_cache[key],
                            tags=(tag,)
                        )

                    else:
                        self.cover_placeholder(
                            canvas,
                            image_x,
                            image_y,
                            image_w,
                            image_h,
                            tag
                        )

                except Exception:
                    self.cover_placeholder(
                        canvas,
                        image_x,
                        image_y,
                        image_w,
                        image_h,
                        tag
                    )

            else:
                self.cover_placeholder(
                    canvas,
                    image_x,
                    image_y,
                    image_w,
                    image_h,
                    tag
                )

            # TITLE

            canvas.create_text(
                215,
                y + 25,
                text=str(film[1] or "UNTITLED").upper(),
                anchor="w",
                fill=TEXT,
                font=("Helvetica", 17, "bold"),
                tags=(tag,)
            )

            if film[2]:

                canvas.create_text(
                    215,
                    y + 52,
                    text="ORIGINAL: " + str(film[2]),
                    anchor="w",
                    fill=TEXT_MUTED,
                    font=("Helvetica", 9),
                    tags=(tag,)
                )

            metadata = [
                ("FORMAT", film[3]),
                ("STOCK", film[4]),
                ("RELEASED", film[23]),
                ("PRINT DATE", film[5]),
                ("LENGTH", film[6]),
                ("RUNTIME", film[7]),
                ("SOUND", film[8]),
                ("COUNTRY", film[9])
            ]

            for i, (label, value) in enumerate(metadata):

                col = i % 4
                row = i // 4

                x = 215 + col * 170
                yy = y + 82 + row * 25

                canvas.create_text(
                    x,
                    yy,
                    text=label + ":",
                    anchor="w",
                    fill=TEXT_DIM,
                    font=("Helvetica", 7, "bold"),
                    tags=(tag,)
                )

                canvas.create_text(
                    x + 60,
                    yy,
                    text=str(value or "—"),
                    anchor="w",
                    fill=TEXT_MUTED,
                    font=("Helvetica", 8),
                    tags=(tag,)
                )

            statuses = []

            if str(film[14]).upper() in ("YES", "TRUE", "1"):
                statuses.append(("PROJECTABLE", GREEN))

            if str(film[13]).upper() in ("YES", "TRUE", "1"):
                statuses.append(("NEEDS REPAIR", RED))

            if str(film[11]).upper() == "YES":
                statuses.append(("VINEGAR", RED))

            if str(film[12]).upper() == "YES":
                statuses.append(("SHRUNKEN", RED))

            sx = 215

            for status, color in statuses:

                canvas.create_text(
                    sx,
                    y + 151,
                    text="● " + status,
                    anchor="w",
                    fill=color,
                    font=("Helvetica", 8, "bold"),
                    tags=(tag,)
                )

                sx += 125

            if film[21]:
                canvas.create_text(
                    720,
                    y + 25,
                    text="RAW",
                    anchor="w",
                    fill=GOLD,
                    font=("Helvetica", 8, "bold"),
                    tags=(tag,)
                )

            if film[22]:
                canvas.create_text(
                    720,
                    y + 47,
                    text="RESTORED",
                    anchor="w",
                    fill=GREEN,
                    font=("Helvetica", 8, "bold"),
                    tags=(tag,)
                )

            canvas.create_text(
                width - 155,
                y + 158,
                text="EDIT",
                fill=GOLD_LIGHT,
                font=("Helvetica", 9, "bold"),
                tags=(f"edit:{film_id}",)
            )

            canvas.create_text(
                width - 80,
                y + 158,
                text="VIEW →",
                fill=TEXT,
                font=("Helvetica", 9, "bold"),
                tags=(f"view:{film_id}",)
            )

            y += row_height + 10

        canvas.configure(
            scrollregion=(0, 0, width, y + 10)
        )


    def cover_placeholder(self, canvas, x, y, w, h, tag):

        canvas.create_rectangle(
            x, y, x+w, y+h,
            fill="#080808",
            outline=BORDER,
            tags=(tag,)
        )

        canvas.create_text(
            x+w/2,
            y+h/2,
            text="NO\nCOVER",
            fill=TEXT_DIM,
            font=("Helvetica", 11, "bold"),
            justify="center",
            tags=(tag,)
        )


    def archive_mousewheel(self, event):
        self.archive_canvas.yview_scroll(
            int(-1 * (event.delta / 120)),
            "units"
        )


    def archive_motion(self, event):

        current = self.archive_canvas.find_withtag("current")

        if current:
            tags = self.archive_canvas.gettags(current[0])

            if any(
                tag.startswith(("edit:", "view:"))
                for tag in tags
            ):
                self.archive_canvas.config(cursor="hand2")
                return

        self.archive_canvas.config(cursor="")


    def archive_click(self, event):

        current = self.archive_canvas.find_withtag("current")

        if not current:
            return

        for tag in self.archive_canvas.gettags(current[0]):

            if tag.startswith("edit:"):
                self.open_edit_dialog(
                    int(tag.split(":", 1)[1])
                )
                return

            if tag.startswith("view:"):
                self.open_view_dialog(
                    int(tag.split(":", 1)[1]), return_target="database"
                )
                return


    # ========================================================
    # RANDOM
    # ========================================================

    def open_random_film(self):

        films = self.get_filtered_films()

        if not films:
            messagebox.showinfo(
                "Random Film",
                "There are no films available."
            )
            return

        self.open_view_dialog(
            random.choice(films)[0], return_target="menu"
        )


    # ========================================================
    # FILM FUN MENU
    # ========================================================

    def open_film_fun_menu(self, return_to_menu=False):
        menu = self.new_page()
        menu.return_to_menu = return_to_menu
        menu.title("Film Vault — Film Fun")
        menu.configure(bg=BG)
        tk.Label(
            menu,
            text="🎬 FILM FUN",
            bg=BG,
            fg=GOLD_LIGHT,
            font=("Helvetica", 24, "bold")
        ).pack(pady=(25, 5))

        tk.Label(
            menu,
            text="Choose something to do with your collection",
            bg=BG,
            fg=TEXT_MUTED,
            font=("Helvetica", 10, "bold")
        ).pack(pady=(0, 12))

        # The game list is deliberately scrollable and expands with the main
        # window, so every game remains reachable at different window sizes.
        list_frame = tk.Frame(menu, bg=BG)
        list_frame.pack(fill="both", expand=True, padx=18, pady=(0, 5))

        canvas = tk.Canvas(
            list_frame,
            bg=BG,
            highlightthickness=0,
            bd=0
        )
        scrollbar = tk.Scrollbar(
            list_frame,
            orient="vertical",
            command=canvas.yview
        )
        scroll_frame = tk.Frame(canvas, bg=BG)

        scroll_frame.bind(
            "<Configure>",
            lambda event: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        window_id = canvas.create_window(
            (0, 0),
            window=scroll_frame,
            anchor="nw"
        )

        def resize_scroll_frame(event):
            canvas.itemconfigure(window_id, width=event.width)

        canvas.bind("<Configure>", resize_scroll_frame)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        options = [
            ("🎲 RANDOM FILM", self.open_random_film),
            ("🎰 FILM SLOT MACHINE", self.open_slot_machine),
            ("🎞 TIMELINE", self.open_collection_timeline),
            ("🕵️ MYSTERY FILM", self.open_mystery_film),
            ("🏆 FILM AWARDS", self.open_film_awards),
            ("🎬 DOUBLE FEATURE", self.open_double_feature),
            ("🪦 FILM HANGMAN", self.open_film_hangman),
            ("🕵️ FILM DETECTIVE", self.open_film_detective),
            ("🔤 FILM WORD SCRAMBLE", self.open_film_word_scramble),
            ("🎯 FILM HIGHER OR LOWER", self.open_film_higher_lower),
            ("🕳️ MISSING FILM", self.open_missing_film),
            ("🧠 FILM TRIVIA", self.open_film_trivia),
            ("🕹️ REEL RUNNER", self.open_reel_runner),
            ("📊 VAULT STATISTICS", self.open_collection_statistics),
        ]

        for label, command in options:
            self.button(
                scroll_frame,
                label,
                lambda command=command: (menu.destroy(), command())
            ).pack(fill="x", padx=32, pady=4)

        # Windows mouse-wheel support.
        def wheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind("<Enter>", lambda event: canvas.bind_all("<MouseWheel>", wheel))
        canvas.bind("<Leave>", lambda event: canvas.unbind_all("<MouseWheel>"))

        menu.bind("<Escape>", lambda event: menu.go_back())


    # ========================================================
    # FILM DETECTIVE
    # ========================================================

    def open_film_detective(self):
        films = self.get_filtered_films()
        if not films:
            messagebox.showinfo("Film Detective", "NO ONE BUT US CHICKENS\n\nThere are no films available in the current selection.")
            return

        window = self.new_page()
        window.title("Film Vault — Film Detective")
        window.geometry("900x700")
        window.minsize(760, 600)
        window.configure(bg=BG)
        window.transient(self)
        window.grab_set()

        state = {"film": random.choice(films), "clues": [], "index": 0, "finished": False}
        clues_frame = tk.Frame(window, bg=BG)
        clues_frame.pack(fill="both", expand=True, padx=35, pady=20)

        tk.Label(window, text="🕵️ FILM DETECTIVE", bg=BG, fg=GOLD_LIGHT, font=("Helvetica", 28, "bold")).pack(pady=(25, 3))
        tk.Label(window, text="IDENTIFY THE MYSTERY FILM", bg=BG, fg=TEXT_MUTED, font=("Helvetica", 11, "bold")).pack()
        case_label = tk.Label(window, text="CASE #" + str(random.randint(10,999)), bg=BG, fg=GOLD, font=("Helvetica", 10, "bold"))
        case_label.pack(pady=(5,10))
        clue_box = tk.Frame(clues_frame, bg="#111111", highlightbackground=GOLD, highlightthickness=1)
        clue_box.pack(fill="both", expand=True)
        status = tk.Label(clue_box, text="🔎 BEGIN YOUR INVESTIGATION", bg="#111111", fg=GOLD_LIGHT, font=("Helvetica", 18, "bold"))
        status.pack(pady=25)
        clue_text = tk.Label(clue_box, text="No clues revealed yet.", bg="#111111", fg="white", font=("Helvetica", 15), justify="left")
        clue_text.pack(anchor="w", padx=45, pady=10)
        result = tk.Label(window, text="", bg=BG, fg=GOLD_LIGHT, font=("Helvetica", 16, "bold"))
        result.pack(pady=8)

        def make_clues():
            f=state["film"]
            def val(i, fallback="UNKNOWN"):
                return str(f[i] or fallback).strip()
            clues=[("FORMAT",val(3)),("ORIGINAL RELEASE",val(23)),("FILM STOCK",val(4)),("FILM LENGTH",val(6)),("RUNTIME",val(7)),("SOUND",val(8)),("COUNTRY",val(9)),("SPLICES",val(15))]
            return [(a,b) for a,b in clues if b and b.upper() != "UNKNOWN"]

        def refresh():
            lines=[]
            for i,(name,value) in enumerate(state["clues"][:state["index"]]):
                lines.append(f"{i+1}. {name}: {value}")
            clue_text.config(text="\n\n".join(lines) if lines else "No clues revealed yet.\n\nClick REVEAL CLUE to begin.")
            if state["finished"]:
                result.config(text="🎬 THE FILM WAS: " + str(state["film"][1]), fg=GOLD_LIGHT)
                reveal_btn.config(state="disabled")
                guess_entry.config(state="disabled")
                view_btn.pack(side="left", padx=5)
            else:
                result.config(text=f"Clues revealed: {state['index']} / {len(state['clues'])}")

        def reveal_clue():
            if state["finished"]: return
            if state["index"] < len(state["clues"]):
                state["index"] += 1
                refresh()
            else:
                state["finished"] = True
                refresh()

        def guess():
            if state["finished"]: return
            guess_text=guess_entry.get().strip().casefold()
            if not guess_text: return
            if guess_text == str(state["film"][1]).strip().casefold():
                state["finished"] = True
                result.config(text="🎉 CASE SOLVED!", fg=GOLD_LIGHT)
                refresh()
            else:
                result.config(text="❌ WRONG FILM — REVEAL ANOTHER CLUE", fg="white")
            guess_entry.delete(0,"end")

        def new_case():
            state["film"]=random.choice(films)
            state["clues"]=make_clues()
            state["index"]=0
            state["finished"]=False
            reveal_btn.config(state="normal")
            guess_entry.config(state="normal")
            view_btn.pack_forget()
            refresh()

        state["clues"]=make_clues()
        controls=tk.Frame(window,bg=BG)
        controls.pack(fill="x",padx=35,pady=(0,25))
        reveal_btn=self.button(controls,"🔎 REVEAL CLUE",reveal_clue)
        reveal_btn.pack(side="left",padx=5)
        guess_entry=tk.Entry(controls,bg="#111111",fg="white",insertbackground="white",font=("Helvetica",13),width=28)
        guess_entry.pack(side="left",padx=8,ipady=7)
        self.button(controls,"GUESS",guess).pack(side="left",padx=5)
        view_btn=self.button(controls,"🎞 VIEW FILM",lambda:self.open_view_dialog(state["film"][0], return_target="menu"))
        view_btn.pack_forget()
        guess_entry.bind("<Return>",lambda e:guess())
        window.bind("<Escape>",lambda e:window.go_back())
        refresh()


    # ========================================================
    # FILM HANGMAN
    # ========================================================

    def open_film_hangman(self):
        films = self.get_filtered_films()

        if not films:
            messagebox.showinfo(
                "Film Hangman",
                "NO ONE BUT US CHICKENS\n\nThere are no films available in the current selection."
            )
            return

        window = self.new_page()
        window.title("Film Vault — Film Hangman")
        window.geometry("980x760")
        window.minsize(850, 650)
        window.configure(bg=BG)
        window.transient(self)
        window.grab_set()

        state = {
            "film": random.choice(films),
            "guessed": set(),
            "wrong": 0,
            "over": False,
            "wins": 0,
            "losses": 0,
        }
        max_wrong = 6

        header = tk.Frame(window, bg=BG)
        header.pack(fill="x", padx=30, pady=(22, 5))

        tk.Label(
            header,
            text="🪦 FILM HANGMAN",
            bg=BG,
            fg=GOLD_LIGHT,
            font=("Helvetica", 25, "bold")
        ).pack()

        tk.Label(
            header,
            text="Guess the title from your own film collection",
            bg=BG,
            fg=TEXT_MUTED,
            font=("Helvetica", 10, "bold")
        ).pack(pady=(3, 0))

        status = tk.Label(
            window,
            text="",
            bg=BG,
            fg=TEXT,
            font=("Helvetica", 11, "bold")
        )
        status.pack(pady=(8, 4))

        drawing = tk.Canvas(
            window,
            width=330,
            height=270,
            bg=PANEL,
            highlightthickness=1,
            highlightbackground=BORDER
        )
        drawing.pack(pady=8)

        clue_frame = tk.Frame(window, bg=BG)
        clue_frame.pack(fill="x", padx=35, pady=(5, 0))

        word_label = tk.Label(
            clue_frame,
            text="",
            bg=BG,
            fg=GOLD_LIGHT,
            font=("Courier New", 22, "bold")
        )
        word_label.pack(pady=(5, 8))

        clue_label = tk.Label(
            clue_frame,
            text="",
            bg=BG,
            fg=TEXT_MUTED,
            font=("Helvetica", 10)
        )
        clue_label.pack()

        keyboard = tk.Frame(window, bg=BG)
        keyboard.pack(pady=12)

        action_frame = tk.Frame(window, bg=BG)
        action_frame.pack(fill="x", padx=35, pady=(0, 18))

        def title_text():
            return str(state["film"][1] or "UNTITLED FILM").strip()

        def normalize_title():
            return title_text().upper()

        def display_word():
            title = normalize_title()
            chars = []
            for char in title:
                if char.isalpha() or char.isdigit():
                    chars.append(char if char in state["guessed"] else "_")
                elif char == " ":
                    chars.append("  ")
                else:
                    chars.append(char)
            return " ".join(chars)

        def solved():
            title = normalize_title()
            needed = {c for c in title if c.isalpha() or c.isdigit()}
            return needed.issubset(state["guessed"])

        def draw_hangman():
            drawing.delete("all")
            drawing.create_line(55, 235, 275, 235, fill=GOLD, width=5)
            drawing.create_line(105, 235, 105, 35, fill=GOLD, width=5)
            drawing.create_line(105, 35, 220, 35, fill=GOLD, width=5)
            drawing.create_line(220, 35, 220, 65, fill=GOLD, width=5)

            wrong = state["wrong"]
            if wrong >= 1:
                drawing.create_oval(190, 65, 250, 125, outline=TEXT, width=4)
            if wrong >= 2:
                drawing.create_line(220, 125, 220, 190, fill=TEXT, width=4)
            if wrong >= 3:
                drawing.create_line(220, 140, 180, 165, fill=TEXT, width=4)
            if wrong >= 4:
                drawing.create_line(220, 140, 260, 165, fill=TEXT, width=4)
            if wrong >= 5:
                drawing.create_line(220, 190, 185, 225, fill=TEXT, width=4)
            if wrong >= 6:
                drawing.create_line(220, 190, 255, 225, fill=TEXT, width=4)

        def set_button_state():
            for child in keyboard.winfo_children():
                letter = child.cget("text")
                if letter in state["guessed"]:
                    child.configure(state="disabled")
                else:
                    child.configure(state="normal" if not state["over"] else "disabled")

        def update_screen():
            word_label.configure(text=display_word())
            draw_hangman()
            status.configure(
                text=f"WRONG GUESSES: {state['wrong']} / {max_wrong}    •    WINS: {state['wins']}    •    LOSSES: {state['losses']}"
            )
            set_button_state()

        def finish(win):
            state["over"] = True
            if win:
                state["wins"] += 1
                clue_label.configure(
                    text="🎉 FILM IDENTIFIED!  " + title_text(),
                    fg=GOLD_LIGHT
                )
            else:
                state["losses"] += 1
                word_label.configure(text=normalize_title())
                clue_label.configure(
                    text="💀 THE FILM GOT AWAY!  The answer was: " + title_text(),
                    fg=RED
                )

            # Only now, after the game has ended, is the actual film record
            # available. This prevents opening the answer as a cheat.
            view_button.pack(side="left", padx=4)
            set_button_state()

        def guess(letter):
            if state["over"] or letter in state["guessed"]:
                return

            state["guessed"].add(letter)
            if letter not in normalize_title():
                state["wrong"] += 1

            if solved():
                update_screen()
                finish(True)
                return

            if state["wrong"] >= max_wrong:
                update_screen()
                finish(False)
                return

            clue_label.configure(
                text="Correct!" if letter in normalize_title() else "Wrong guess!",
                fg=GREEN if letter in normalize_title() else RED
            )
            update_screen()

        def new_game():
            state["film"] = random.choice(films)
            state["guessed"] = set()
            state["wrong"] = 0
            state["over"] = False
            view_button.pack_forget()
            clue_label.configure(text="Guess a letter.", fg=TEXT_MUTED)
            update_screen()

        def reveal():
            if state["over"]:
                return
            state["losses"] += 1
            word_label.configure(text=normalize_title())
            clue_label.configure(
                text="REVEALED: " + title_text(),
                fg=GOLD_LIGHT
            )
            finish(False)

        def show_hint():
            film = state["film"]
            hints = []
            if film[3]:
                hints.append("Format: " + str(film[3]))
            if film[23]:
                hints.append("Release: " + str(film[23]))
            if film[7]:
                hints.append("Runtime: " + str(film[7]))
            if film[8]:
                hints.append("Sound: " + str(film[8]))
            if film[4]:
                hints.append("Stock: " + str(film[4]))
            if film[9]:
                hints.append("Country: " + str(film[9]))

            clue_label.configure(
                text="HINT — " + (" • ".join(hints[:2]) if hints else "No additional clues available."),
                fg=GOLD_LIGHT
            )

        letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        for index, letter in enumerate(letters):
            tk.Button(
                keyboard,
                text=letter,
                width=4,
                height=1,
                bg=PANEL_2,
                fg=TEXT,
                activebackground=HOVER,
                activeforeground=GOLD_LIGHT,
                relief="flat",
                bd=0,
                font=("Helvetica", 10, "bold"),
                command=lambda letter=letter: guess(letter)
            ).grid(row=index // 13, column=index % 13, padx=2, pady=3)

        self.button(action_frame, "💡 HINT", show_hint).pack(side="left", padx=4)
        self.button(action_frame, "🔓 REVEAL FILM", reveal).pack(side="left", padx=4)
        self.button(action_frame, "🎬 NEW FILM", new_game).pack(side="left", padx=4)
        view_button = self.button(
            action_frame,
            "👁 VIEW FILM",
            lambda: self.open_view_dialog(state["film"][0], return_target="menu")
        )
        # The answer must remain inaccessible while the game is active.
        # VIEW FILM is revealed only after the game ends.
        view_button.pack_forget()


        def keypress(event):
            key = event.keysym.upper()
            if len(key) == 1 and key in letters:
                guess(key)
            elif key == "ESCAPE":
                window.go_back()

        window.bind("<Key>", keypress)
        window.focus_force()
        update_screen()


    # ========================================================
    # FILM WORD SCRAMBLE
    # ========================================================

    def open_film_word_scramble(self):
        films = self.get_filtered_films()

        if not films:
            messagebox.showinfo(
                "Film Word Scramble",
                "NO ONE BUT US CHICKENS\n\nThere are no films available in the current selection."
            )
            return

        window = self.new_page()
        window.title("Film Vault — Film Word Scramble")
        window.geometry("900x680")
        window.minsize(760, 600)
        window.configure(bg=BG)
        window.transient(self)
        window.grab_set()

        state = {"film": None, "scramble": "", "solved": False, "revealed": False,
                 "wins": 0, "losses": 0, "attempts": 0}

        tk.Label(window, text="🔤 FILM WORD SCRAMBLE", bg=BG, fg=GOLD_LIGHT,
                 font=("Helvetica", 26, "bold")).pack(pady=(25, 4))
        tk.Label(window, text="Unscramble a title from your film collection",
                 bg=BG, fg=TEXT_MUTED, font=("Helvetica", 10, "bold")).pack(pady=(0, 18))

        score = tk.Label(window, text="WINS: 0    LOSSES: 0", bg=BG, fg=TEXT,
                         font=("Helvetica", 11, "bold"))
        score.pack(pady=(0, 12))

        scramble_label = tk.Label(window, text="", bg=PANEL, fg=GOLD_LIGHT,
                                  font=("Courier New", 27, "bold"), padx=25, pady=22,
                                  wraplength=780, justify="center")
        scramble_label.pack(fill="x", padx=45, pady=10)

        hint_label = tk.Label(window, text="", bg=BG, fg=TEXT_MUTED,
                              font=("Helvetica", 11), wraplength=760, justify="center")
        hint_label.pack(pady=15)

        entry_frame = tk.Frame(window, bg=BG)
        entry_frame.pack(pady=5)
        guess_entry = tk.Entry(entry_frame, bg=INPUT_BG, fg=TEXT, insertbackground=TEXT,
                               font=("Helvetica", 16), width=38, relief="flat")
        guess_entry.pack(side="left", padx=6, ipady=8)

        action_frame = tk.Frame(window, bg=BG)
        action_frame.pack(pady=18)

        view_button = None

        def title_text():
            return str(state["film"][1] or "UNTITLED FILM").strip()

        def scramble_title(title):
            import re
            groups = re.findall(r"[A-Za-z0-9]+|[^A-Za-z0-9]+", title.upper())
            letters = list("".join(c for c in title.upper() if c.isalnum()))
            if len(letters) < 3:
                return title.upper()
            original = "".join(letters)
            for _ in range(100):
                random.shuffle(letters)
                result = " ".join(letters)
                if result.replace(" ", "") != original:
                    return result
            return result

        def metadata_hint():
            film = state["film"]
            parts = []
            fmt = str(film[3] or "").strip()
            year = self.get_release_year(film[23]) if len(film) > 23 else None
            runtime = str(film[7] or "").strip()
            sound = str(film[8] or "").strip()
            if fmt: parts.append("FORMAT: " + fmt)
            if year: parts.append("RELEASE: " + str(year))
            if runtime: parts.append("RUNTIME: " + runtime)
            if sound: parts.append("SOUND: " + sound)
            return "   •   ".join(parts) if parts else "No metadata clues available."

        def finish(won=False, revealed=False):
            state["solved"] = True
            state["revealed"] = revealed
            if won: state["wins"] += 1
            elif not revealed: state["losses"] += 1
            score.config(text=f"WINS: {state['wins']}    LOSSES: {state['losses']}")
            scramble_label.config(text=title_text(), fg=GOLD_LIGHT)
            hint_label.config(text=("🎉 CASE SOLVED!" if won else "THE ANSWER WAS REVEALED."))
            guess_entry.config(state="disabled")
            guess_button.config(state="disabled")
            reveal_button.config(state="disabled")
            view_button.config(state="normal")

        def guess():
            if state["solved"]:
                return
            answer = title_text().casefold()
            guess = guess_entry.get().strip().casefold()
            if not guess:
                return
            state["attempts"] += 1
            guess_entry.delete(0, "end")
            if guess == answer:
                finish(won=True)
            else:
                hint_label.config(text="❌ NOT QUITE — TRY AGAIN\n\n" + metadata_hint())

        def reveal():
            if not state["solved"]:
                finish(revealed=True)

        def new_round():
            state["film"] = random.choice(films)
            state["scramble"] = scramble_title(title_text())
            state["solved"] = False
            state["revealed"] = False
            state["attempts"] = 0
            scramble_label.config(text=state["scramble"], fg=GOLD_LIGHT)
            hint_label.config(text="Unscramble the title. Need help? Use HINT.")
            guess_entry.config(state="normal")
            guess_button.config(state="normal")
            reveal_button.config(state="normal")
            view_button.config(state="disabled")
            guess_entry.delete(0, "end")
            guess_entry.focus_set()

        guess_button = self.button(action_frame, "GUESS", guess)
        guess_button.pack(side="left", padx=5)
        hint_button = self.button(action_frame, "💡 HINT", lambda: hint_label.config(text=metadata_hint()))
        hint_button.pack(side="left", padx=5)
        reveal_button = self.button(action_frame, "REVEAL FILM", reveal)
        reveal_button.pack(side="left", padx=5)
        view_button = self.button(action_frame, "VIEW FILM", lambda: self.open_view_dialog(state["film"][0], return_target="menu"))
        view_button.pack(side="left", padx=5)
        new_button = self.button(action_frame, "NEW FILM", new_round)
        new_button.pack(side="left", padx=5)
        guess_entry.bind("<Return>", lambda event: guess())
        window.bind("<Escape>", lambda event: window.go_back())
        new_round()


    # ========================================================
    # REEL RUNNER — PYGAME EDITION
    # ========================================================

    def open_reel_runner(self):
        """Launch the built-in Pygame arcade version in its own window."""
        try:
            subprocess.Popen(
                [sys.executable, os.path.abspath(__file__), "--reel-runner"],
                cwd=BASE_DIR,
                creationflags=0
            )
        except Exception as exc:
            messagebox.showerror(
                "Reel Runner",
                f"Could not start the Pygame game.\n\n{exc}"
            )

    # ========================================================
    # FILM TRIVIA
    # ========================================================

    def open_film_trivia(self):
        films = self.get_filtered_films()

        if len(films) < 4:
            messagebox.showinfo(
                "Film Trivia",
                "You need at least 4 films in the current collection/filter to play trivia."
            )
            return

        window = self.new_page()
        window.title("Film Vault — Film Trivia")
        window.geometry("760x650")
        window.minsize(680, 580)
        window.configure(bg=BG)
        window.transient(self)
        window.grab_set()

        state = {
            "score": 0,
            "streak": 0,
            "round": 0,
            "film": None,
            "correct": None,
            "answered": False,
            "wins": 0,
            "questions": 0,
        }

        tk.Label(
            window, text="🧠 FILM TRIVIA", bg=BG, fg=GOLD_LIGHT,
            font=("Helvetica", 26, "bold")
        ).pack(pady=(24, 3))

        tk.Label(
            window,
            text="How well do you know your own film collection?",
            bg=BG, fg=TEXT_MUTED, font=("Helvetica", 11, "bold")
        ).pack()

        score_label = tk.Label(
            window, text="SCORE: 0    STREAK: 0    QUESTION: 0",
            bg=BG, fg=TEXT, font=("Helvetica", 12, "bold")
        )
        score_label.pack(pady=(14, 12))

        category_label = tk.Label(
            window, text="", bg=PANEL, fg=GOLD_LIGHT,
            font=("Helvetica", 12, "bold"), padx=18, pady=10
        )
        category_label.pack(fill="x", padx=40, pady=(0, 10))

        question_label = tk.Label(
            window, text="", bg=BG, fg=TEXT,
            font=("Helvetica", 18, "bold"), wraplength=650,
            justify="center"
        )
        question_label.pack(pady=(8, 16))

        choices_frame = tk.Frame(window, bg=BG)
        choices_frame.pack(fill="x", padx=70, pady=4)

        result_label = tk.Label(
            window, text="", bg=BG, fg=TEXT_MUTED,
            font=("Helvetica", 12, "bold"), wraplength=650,
            justify="center"
        )
        result_label.pack(pady=15)

        action_frame = tk.Frame(window, bg=BG)
        action_frame.pack(fill="x", padx=70, pady=(5, 18))

        next_btn = None
        view_btn = None
        choice_buttons = []

        def title_of(film):
            return str(film[1] or "UNTITLED FILM").strip() or "UNTITLED FILM"

        def parse_number(value):
            text = str(value or "").replace(",", "")
            match = re.search(r"-?\d+(?:\.\d+)?", text)
            return float(match.group(0)) if match else None

        def clear_choices():
            for child in choices_frame.winfo_children():
                child.destroy()
            choice_buttons.clear()

        def update_score():
            score_label.config(
                text=f"SCORE: {state['score']}    STREAK: {state['streak']}    QUESTION: {state['round']}"
            )

        def show_film():
            if state["film"] is not None:
                self.open_film_editor(state["film"][0])

        def answer(selected):
            if state["answered"]:
                return

            state["answered"] = True
            state["questions"] += 1

            for button in choice_buttons:
                button.config(state="disabled")

            if selected[0] == state["correct"][0]:
                state["score"] += 1
                state["streak"] += 1
                result_label.config(
                    text=f"✓ CORRECT!  +1\nSTREAK: {state['streak']}",
                    fg=GREEN
                )
            else:
                state["streak"] = 0
                result_label.config(
                    text=f"✗ WRONG!\nThe answer was: {title_of(state['correct'])}",
                    fg=RED
                )

            update_score()
            next_btn.config(state="normal")
            view_btn.config(state="normal")

        def make_question():
            current = self.get_filtered_films()
            if len(current) < 4:
                messagebox.showinfo(
                    "Film Trivia",
                    "There are not enough films available to continue."
                )
                window.destroy()
                return

            clear_choices()
            state["round"] += 1
            state["answered"] = False
            state["film"] = random.choice(current)
            state["correct"] = state["film"]
            next_btn.config(state="disabled")
            view_btn.config(state="disabled")
            result_label.config(text="Choose an answer.", fg=TEXT_MUTED)
            update_score()

            possible = []
            question = ""
            question_type = random.choice([
                "format", "sound", "country", "release", "length",
                "runtime", "splices", "stock", "print_date"
            ])

            if question_type == "format":
                value = str(state["film"][3] or "").strip()
                if not value:
                    question_type = "sound"
                else:
                    question = f"Which film is in {value.upper()} format?"
                    possible = [f for f in current if str(f[3] or "").strip().lower() == value.lower()]

            if question_type == "sound":
                value = str(state["film"][8] or "").strip()
                if not value:
                    question_type = "country"
                else:
                    question = f"Which film has this sound status: {value.upper()}?"
                    possible = [f for f in current if str(f[8] or "").strip().lower() == value.lower()]

            if question_type == "country":
                value = str(state["film"][9] or "").strip()
                if not value:
                    question_type = "stock"
                else:
                    question = f"Which film has country code / country listed as {value.upper()}?"
                    possible = [f for f in current if str(f[9] or "").strip().lower() == value.lower()]

            if question_type == "stock":
                value = str(state["film"][4] or "").strip()
                if not value:
                    question_type = "release"
                else:
                    question = f"Which film uses {value.upper()} film stock?"
                    possible = [f for f in current if str(f[4] or "").strip().lower() == value.lower()]

            if question_type == "release":
                year = self.get_release_year(state["film"][23])
                if year is None:
                    question_type = "print_date"
                else:
                    question = f"Which film was released in {year}?"
                    possible = [f for f in current if self.get_release_year(f[23]) == year]

            if question_type == "print_date":
                value = str(state["film"][5] or "").strip()
                if not value:
                    question_type = "splices"
                else:
                    question = f"Which film has this print date: {value}?"
                    possible = [f for f in current if str(f[5] or "").strip().lower() == value.lower()]

            if question_type == "length":
                value = parse_number(state["film"][6])
                if value is None:
                    question_type = "runtime"
                else:
                    question = f"Which film is listed as approximately {state['film'][6]} of film?"
                    possible = [f for f in current if parse_number(f[6]) == value]

            if question_type == "runtime":
                value = parse_number(state["film"][7])
                if value is None:
                    question_type = "splices"
                else:
                    question = f"Which film has a runtime of approximately {state['film'][7]}?"
                    possible = [f for f in current if parse_number(f[7]) == value]

            if question_type == "splices":
                value = parse_number(state["film"][15])
                if value is None:
                    question_type = "format"
                else:
                    question = f"Which film has {int(value) if value.is_integer() else value:g} splice(s)?"
                    possible = [f for f in current if parse_number(f[15]) == value]

            if not possible:
                possible = [state["film"]]

            # Pick the correct film plus three different distractors.
            distractors = [f for f in current if f[0] != state["correct"][0]]
            random.shuffle(distractors)
            options = [state["correct"]]
            for film in distractors:
                if film[0] not in [x[0] for x in options]:
                    options.append(film)
                if len(options) == 4:
                    break
            random.shuffle(options)

            # If metadata produced a question, use it. Otherwise fall back
            # to a title-identification question so every round is playable.
            if not question:
                question = f"Which film is titled {title_of(state['correct'])}?"

            category_label.config(text="YOUR FILM VAULT • TRIVIA")
            question_label.config(text=question)

            for index, film in enumerate(options):
                button = self.button(
                    choices_frame,
                    f"{chr(65 + index)}.  {title_of(film)}",
                    lambda film=film: answer(film)
                )
                button.pack(fill="x", pady=5)
                choice_buttons.append(button)

        next_btn = self.button(action_frame, "NEXT QUESTION", make_question)
        next_btn.pack(side="left", expand=True, fill="x", padx=5)
        view_btn = self.button(action_frame, "VIEW FILM", show_film)
        view_btn.pack(side="left", expand=True, fill="x", padx=5)

        window.bind("<Return>", lambda event: make_question() if state["answered"] else None)
        window.bind("<Escape>", lambda event: window.go_back())

        make_question()


    # ========================================================
    # MISSING FILM
    # ========================================================

    def open_missing_film(self):
        films = self.get_filtered_films()

        if len(films) < 4:
            messagebox.showinfo(
                "Missing Film",
                "You need at least 4 films in the current collection/filter to play."
            )
            return

        window = self.new_page()
        window.title("Film Vault — Missing Film")
        window.geometry("620x600")
        window.configure(bg=BG)
        window.transient(self)
        window.grab_set()

        state = {"round": 0, "score": 0, "level": 4, "missing": None,
                 "active": False, "revealed": False}

        tk.Label(window, text="🕳️ MISSING FILM", bg=BG, fg=GOLD_LIGHT,
                 font=("Helvetica", 25, "bold")).pack(pady=(22, 3))
        tk.Label(window, text="Memorize the films. One will disappear.",
                 bg=BG, fg=TEXT_MUTED, font=("Helvetica", 11, "bold")).pack()

        status = tk.Label(window, bg=BG, fg=TEXT, font=("Helvetica", 12, "bold"))
        status.pack(pady=(14, 4))
        instruction = tk.Label(window, bg=BG, fg=TEXT_MUTED,
                               font=("Helvetica", 11), wraplength=540)
        instruction.pack(pady=(0, 10))

        board = tk.Frame(window, bg=BG)
        board.pack(fill="both", expand=True, padx=28, pady=8)

        buttons = []
        action_frame = tk.Frame(window, bg=BG)
        action_frame.pack(fill="x", padx=28, pady=(4, 18))

        def clear_board():
            for child in board.winfo_children():
                child.destroy()
            buttons.clear()

        def show_reveal():
            state["active"] = False
            state["revealed"] = True
            missing = state["missing"]
            status.config(text=f"THE MISSING FILM WAS: {missing[1]}", fg=GOLD_LIGHT)
            instruction.config(text="Round over. Start the next round when you're ready.")
            for b in buttons:
                b.config(state="disabled")
            next_btn.config(state="normal")

        def answer(film):
            if not state["active"]:
                return
            state["active"] = False
            state["revealed"] = True
            for b in buttons:
                b.config(state="disabled")
            if film[0] == state["missing"][0]:
                state["score"] += 1
                status.config(text=f"✓ CORRECT!  +1   SCORE: {state['score']}", fg=GREEN)
            else:
                status.config(text=f"✗ NOT QUITE — THE MISSING FILM WAS {state['missing'][1]}", fg=RED)
            instruction.config(text="You found it! Start the next round to keep going." if film[0] == state["missing"][0] else "Better luck next round!")
            next_btn.config(state="normal")

        def start_round():
            all_films = self.get_filtered_films()
            if len(all_films) < 4:
                messagebox.showinfo("Missing Film", "Not enough films remain for another round.")
                window.destroy()
                return

            state["round"] += 1
            state["level"] = min(12, 3 + state["round"])
            count = min(state["level"], len(all_films))
            chosen = random.sample(all_films, count)
            state["missing"] = random.choice(chosen)
            state["active"] = False
            state["revealed"] = False
            clear_board()
            next_btn.config(state="disabled")
            view_btn.config(state="disabled")
            status.config(text=f"ROUND {state['round']}   •   SCORE: {state['score']}   •   {count} FILMS", fg=TEXT)
            instruction.config(text="MEMORIZE THESE FILMS — they disappear in 5 seconds!")

            cols = 2 if count <= 6 else 3
            for i, film in enumerate(chosen):
                card = tk.Frame(board, bg=PANEL, highlightbackground=BORDER,
                                highlightthickness=1)
                card.grid(row=i // cols, column=i % cols, sticky="nsew", padx=7, pady=7)
                board.grid_columnconfigure(i % cols, weight=1)
                board.grid_rowconfigure(i // cols, weight=1)
                tk.Label(card, text=film[1], bg=PANEL, fg=GOLD_LIGHT,
                         font=("Helvetica", 12, "bold"), wraplength=230,
                         justify="center").pack(expand=True, fill="both", padx=10, pady=18)

            def reveal_choices():
                clear_board()
                instruction.config(text="WHICH FILM IS MISSING?")
                missing = state["missing"]
                choices = [f for f in chosen if f[0] != missing[0]] + [missing]
                random.shuffle(choices)
                for i, film in enumerate(choices):
                    b = self.button(board, film[1], lambda f=film: answer(f))
                    b.grid(row=i // cols, column=i % cols, sticky="ew", padx=7, pady=7, ipady=10)
                    buttons.append(b)
                state["active"] = True

            window.after(5000, reveal_choices)

        def view_missing():
            if state["missing"] and state["revealed"]:
                self.open_view_dialog(state["missing"][0])

        next_btn = self.button(action_frame, "▶ NEXT ROUND", start_round)
        next_btn.pack(side="left", expand=True, fill="x", padx=4)
        view_btn = self.button(action_frame, "🎞 VIEW MISSING FILM", view_missing)
        view_btn.config(state="disabled")
        view_btn.pack(side="left", expand=True, fill="x", padx=4)
        # Make the revealed state allow viewing the actual film, without making
        # it possible to cheat during the memory portion.
        original_answer = answer
        def answer_and_unlock(film):
            original_answer(film)
            view_btn.config(state="normal")
        answer = answer_and_unlock

        start_round()
        window.bind("<Escape>", lambda event: window.go_back())


    # ========================================================
    # FILM HIGHER OR LOWER
    # ========================================================

    def open_film_higher_lower(self):
        films = self.get_filtered_films()

        if len(films) < 2:
            messagebox.showinfo(
                "Film Higher or Lower",
                "NOT ENOUGH FILMS\n\nYou need at least two films in the current selection to play."
            )
            return

        window = self.new_page()
        window.title("Film Vault — Film Higher or Lower")
        window.geometry("980x700")
        window.minsize(800, 600)
        window.configure(bg=BG)
        window.transient(self)
        window.grab_set()

        state = {"left": None, "right": None, "category": None, "left_value": None,
                 "right_value": None, "score": 0, "streak": 0, "round": 0,
                 "finished": False}

        tk.Label(window, text="🎯 FILM HIGHER OR LOWER", bg=BG, fg=GOLD_LIGHT,
                 font=("Helvetica", 27, "bold")).pack(pady=(25, 3))
        tk.Label(window, text="Which film has MORE — or LESS — of the selected statistic?",
                 bg=BG, fg=TEXT_MUTED, font=("Helvetica", 10, "bold")).pack(pady=(0, 12))

        score_label = tk.Label(window, text="SCORE: 0    STREAK: 0    ROUND: 0",
                               bg=BG, fg=TEXT, font=("Helvetica", 11, "bold"))
        score_label.pack(pady=(0, 18))

        question_label = tk.Label(window, text="", bg=PANEL, fg=GOLD_LIGHT,
                                  font=("Helvetica", 18, "bold"), padx=20, pady=16,
                                  wraplength=850, justify="center")
        question_label.pack(fill="x", padx=45, pady=8)

        cards = tk.Frame(window, bg=BG)
        cards.pack(fill="both", expand=True, padx=35, pady=18)

        left_frame = tk.Frame(cards, bg=PANEL, bd=1, relief="solid")
        left_frame.pack(side="left", fill="both", expand=True, padx=(0, 12))
        right_frame = tk.Frame(cards, bg=PANEL, bd=1, relief="solid")
        right_frame.pack(side="left", fill="both", expand=True, padx=(12, 0))

        left_title = tk.Label(left_frame, text="", bg=PANEL, fg=TEXT,
                              font=("Helvetica", 20, "bold"), wraplength=350,
                              justify="center")
        left_title.pack(pady=(35, 20), padx=20)
        right_title = tk.Label(right_frame, text="", bg=PANEL, fg=TEXT,
                               font=("Helvetica", 20, "bold"), wraplength=350,
                               justify="center")
        right_title.pack(pady=(35, 20), padx=20)

        left_sub = tk.Label(left_frame, text="FILM A", bg=PANEL, fg=TEXT_MUTED,
                            font=("Helvetica", 10, "bold"))
        left_sub.pack(pady=(0, 18))
        right_sub = tk.Label(right_frame, text="FILM B", bg=PANEL, fg=TEXT_MUTED,
                             font=("Helvetica", 10, "bold"))
        right_sub.pack(pady=(0, 18))

        left_button = self.button(left_frame, "CHOOSE THIS FILM", lambda: choose("left"))
        left_button.pack(fill="x", padx=45, pady=(15, 35))
        right_button = self.button(right_frame, "CHOOSE THIS FILM", lambda: choose("right"))
        right_button.pack(fill="x", padx=45, pady=(15, 35))

        result_label = tk.Label(window, text="", bg=BG, fg=TEXT_MUTED,
                                font=("Helvetica", 12, "bold"), wraplength=850,
                                justify="center")
        result_label.pack(pady=(0, 12))

        controls = tk.Frame(window, bg=BG)
        controls.pack(pady=(0, 18))

        view_left = self.button(controls, "VIEW LEFT FILM",
                                lambda: self.open_view_dialog(state["left"][0]))
        view_right = self.button(controls, "VIEW RIGHT FILM",
                                 lambda: self.open_view_dialog(state["right"][0]))
        view_left.pack_forget()
        view_right.pack_forget()
        next_button.pack_forget()
        categories = [
            ("RELEASE YEAR", lambda f: self.get_release_year(f[23]) if len(f) > 23 else None, False, "older"),
            ("FILM LENGTH", lambda f: self._hl_number(f[6]), True, "longer"),
            ("RUNTIME", lambda f: self._hl_number(f[7]), True, "longer"),
            ("NUMBER OF SPLICES", lambda f: self._hl_number(f[15]), True, "more"),
            ("PURCHASE PRICE", lambda f: self._hl_number(f[27]), True, "more"),
        ]

        def value_text(value):
            if value is None:
                return "UNKNOWN"
            if isinstance(value, float):
                return f"{value:g}"
            return str(value)

        def finish(choice):
            state["finished"] = True
            lv = state["left_value"]
            rv = state["right_value"]
            cat, _, higher, direction = state["category"]

            if higher:
                correct = (choice == "left" and lv > rv) or (choice == "right" and rv > lv)
            else:
                correct = (choice == "left" and lv < rv) or (choice == "right" and rv < lv)

            left_text = value_text(lv)
            right_text = value_text(rv)
            if correct:
                state["score"] += 1
                state["streak"] += 1
                result_label.config(text=f"✅ CORRECT!  {left_title.cget('text')}: {left_text}    •    {right_title.cget('text')}: {right_text}", fg=GREEN)
            else:
                state["streak"] = 0
                result_label.config(text=f"❌ WRONG!  {left_title.cget('text')}: {left_text}    •    {right_title.cget('text')}: {right_text}", fg=RED)

            score_label.config(text=f"SCORE: {state['score']}    STREAK: {state['streak']}    ROUND: {state['round']}")
            left_button.config(state="disabled")
            right_button.config(state="disabled")
            next_button.pack(side="left", padx=5)
            view_left.pack(side="left", padx=5)
            view_right.pack(side="left", padx=5)

        def choose(side):
            if state["finished"]:
                return
            finish(side)

        def new_round():
            if len(films) < 2:
                return
            state["left"], state["right"] = random.sample(films, 2)

            # Find a category where both films have usable, different values.
            possible = categories[:]
            random.shuffle(possible)
            selected = None
            for item in possible:
                cat, getter, higher, direction = item
                lv = getter(state["left"])
                rv = getter(state["right"])
                if lv is not None and rv is not None and lv != rv:
                    selected = (cat, getter, higher, direction)
                    state["left_value"] = lv
                    state["right_value"] = rv
                    break

            if selected is None:
                # Fall back to a category with any usable values.
                for item in possible:
                    cat, getter, higher, direction = item
                    lv = getter(state["left"])
                    rv = getter(state["right"])
                    if lv is not None and rv is not None:
                        selected = (cat, getter, higher, direction)
                        state["left_value"] = lv
                        state["right_value"] = rv
                        break

            if selected is None:
                messagebox.showinfo("Film Higher or Lower", "These films do not have enough numeric metadata for a comparison.")
                return

            state["category"] = selected
            state["finished"] = False
            state["round"] += 1
            cat, _, higher, direction = selected

            if direction == "older":
                prompt = f"Which film was released EARLIER?  •  {cat}"
            elif direction == "longer":
                prompt = f"Which film has MORE?  •  {cat}"
            else:
                prompt = f"Which film has MORE?  •  {cat}"

            question_label.config(text=prompt)
            left_title.config(text=str(state["left"][1] or "UNTITLED FILM"))
            right_title.config(text=str(state["right"][1] or "UNTITLED FILM"))
            result_label.config(text="Make your choice!", fg=TEXT_MUTED)
            left_button.config(state="normal")
            right_button.config(state="normal")
            view_left.pack_forget()
            view_right.pack_forget()
            next_button.pack_forget()
            score_label.config(text=f"SCORE: {state['score']}    STREAK: {state['streak']}    ROUND: {state['round']}")

        window.bind("<Escape>", lambda event: window.go_back())
        new_round()


    def _hl_number(self, value):
        """Convert common Film Vault numeric fields to a comparable number."""
        if value is None:
            return None
        text = str(value).strip().replace(",", "")
        if not text:
            return None
        import re
        match = re.search(r"-?\\d+(?:\\.\\d+)?", text)
        if not match:
            return None
        try:
            return float(match.group(0))
        except ValueError:
            return None


    # ========================================================
    # DOUBLE FEATURE
    # ========================================================

    def open_double_feature(self):

        films = self.get_filtered_films()

        if not films:
            messagebox.showinfo(
                "Double Feature",
                "NO ONE BUT US CHICKENS\n\nThere are no films available in the current selection."
            )
            return

        if len(films) == 1:
            first = second = films[0]
        else:
            first, second = random.sample(films, 2)

        window = self.new_page()
        window.title("Film Vault — Double Feature")
        window.geometry("1000x720")
        window.configure(bg=BG)
        window.transient(self)

        header = tk.Frame(window, bg=BG)
        header.pack(fill="x", padx=30, pady=(25, 8))

        tk.Label(
            header,
            text="🎬 TONIGHT'S DOUBLE FEATURE",
            bg=BG,
            fg=GOLD_LIGHT,
            font=("Helvetica", 22, "bold")
        ).pack()

        tk.Label(
            header,
            text="A SPECIAL PRESENTATION FROM THE REEL ARCHIVE",
            bg=BG,
            fg=TEXT_MUTED,
            font=("Helvetica", 10, "bold")
        ).pack(pady=(5, 0))

        body = tk.Frame(window, bg=BG)
        body.pack(fill="both", expand=True, padx=30, pady=15)

        def film_card(parent, number, film):
            card = tk.Frame(
                parent,
                bg=PANEL,
                highlightbackground=BORDER,
                highlightthickness=1
            )
            card.pack(side="left", fill="both", expand=True, padx=8)

            tk.Label(
                card,
                text=f"FEATURE {number}",
                bg=PANEL,
                fg=GOLD,
                font=("Helvetica", 12, "bold")
            ).pack(pady=(22, 12))

            title = str(film[1] or "UNTITLED FILM")
            tk.Label(
                card,
                text=title,
                bg=PANEL,
                fg=TEXT,
                font=("Helvetica", 19, "bold"),
                wraplength=390,
                justify="center"
            ).pack(padx=20, pady=8)

            original = str(film[2] or "").strip()
            if original and original.casefold() != title.casefold():
                tk.Label(
                    card,
                    text=f"Original title: {original}",
                    bg=PANEL,
                    fg=TEXT_MUTED,
                    font=("Helvetica", 10),
                    wraplength=390,
                    justify="center"
                ).pack(padx=20, pady=(0, 12))

            details = []
            if film[3]: details.append(str(film[3]))
            if film[6]: details.append(f"{film[6]} ft")
            if film[7]: details.append(str(film[7]))
            if film[8]: details.append(str(film[8]))
            if film[23]: details.append(str(film[23]))

            tk.Label(
                card,
                text=" • ".join(details) if details else "NO DETAILS RECORDED",
                bg=PANEL,
                fg=GOLD_LIGHT,
                font=("Helvetica", 11, "bold"),
                wraplength=390,
                justify="center"
            ).pack(padx=20, pady=15)

            notes = str(film[16] or "").strip()
            if notes:
                tk.Label(
                    card,
                    text=notes,
                    bg=PANEL,
                    fg=TEXT_MUTED,
                    font=("Helvetica", 9),
                    wraplength=390,
                    justify="center"
                ).pack(padx=25, pady=10)

            self.button(
                card,
                "VIEW FILM",
                lambda fid=film[0]: self.open_view_dialog(fid)
            ).pack(pady=(18, 25))

        film_card(body, 1, first)

        middle = tk.Frame(body, bg=BG, width=120)
        middle.pack(side="left", fill="y")
        middle.pack_propagate(False)
        tk.Label(
            middle,
            text="★\n\nINTERMISSION",
            bg=BG,
            fg=GOLD,
            font=("Helvetica", 10, "bold"),
            justify="center",
            wraplength=110
        ).pack(expand=True)

        film_card(body, 2, second)

        footer = tk.Frame(window, bg=BG)
        footer.pack(fill="x", padx=30, pady=(5, 25))

        self.button(
            footer,
            "🎲 ANOTHER DOUBLE FEATURE",
            lambda: (window.destroy(), self.open_double_feature())
        ).pack(side="left")

        window.bind("<Escape>", lambda event: window.go_back())


    # ========================================================
    # MYSTERY FILM
    # ========================================================

    def get_release_year(self, value):
        text = str(value or "").strip()

        if not text:
            return None

        match = re.search(r"\b(18|19|20)\d{2}\b", text)

        if not match:
            return None

        return int(match.group(0))


    def open_mystery_film(self):
        films = self.get_filtered_films()

        if not films:
            messagebox.showinfo(
                "Mystery Film",
                "There are no films available in the current selection."
            )
            return

        film = random.choice(films)

        window = self.new_page()
        window.title("Mystery Film")
        window.geometry("900x680")
        window.minsize(700, 580)
        window.configure(bg=BG)

        clue_index = [0]
        revealed = [False]

        clues = []

        release_year = self.get_release_year(
            film[23] if len(film) > 23 else ""
        )

        if film[3]:
            clues.append(("FORMAT", str(film[3])))

        if release_year:
            clues.append(("ORIGINAL RELEASE", str(release_year)))

        if film[4]:
            clues.append(("FILM STOCK", str(film[4])))

        if film[6]:
            clues.append(("FILM LENGTH", str(film[6])))

        if film[7]:
            clues.append(("RUNTIME", str(film[7])))

        if film[8]:
            sound = str(film[8]).strip()

            if sound.upper() in ("YES", "TRUE", "1", "SOUND"):
                sound = "SOUND"
            elif sound.upper() in ("NO", "FALSE", "0", "SILENT"):
                sound = "SILENT"

            clues.append(("SOUND", sound))

        if film[9]:
            clues.append(("COUNTRY", str(film[9])))

        if film[15] not in ("", None):
            clues.append(("SPLICES", str(film[15])))

        if not clues:
            clues.append(("VAULT NUMBER", f"#{film[0]}"))

        header = tk.Frame(window, bg=BG, height=105)
        header.pack(fill="x")

        tk.Label(
            header,
            text="🕵️",
            bg=BG,
            fg=GOLD_LIGHT,
            font=("Helvetica", 30)
        ).pack(pady=(18, 0))

        tk.Label(
            header,
            text="CLASSIFIED FILM",
            bg=BG,
            fg=GOLD_LIGHT,
            font=("Helvetica", 20, "bold")
        ).pack()

        tk.Label(
            header,
            text="IDENTIFY THE FILM",
            bg=BG,
            fg=TEXT_DIM,
            font=("Helvetica", 9, "bold")
        ).pack(pady=(2, 0))

        main = tk.Frame(
            window,
            bg=PANEL,
            highlightbackground=BORDER,
            highlightthickness=1
        )
        main.pack(fill="both", expand=True, padx=35, pady=(10, 20))

        title_label = tk.Label(
            main,
            text="???",
            bg=PANEL,
            fg=GOLD_LIGHT,
            font=("Helvetica", 34, "bold")
        )
        title_label.pack(pady=(35, 5))

        subtitle_label = tk.Label(
            main,
            text="THE TITLE IS CLASSIFIED",
            bg=PANEL,
            fg=TEXT_DIM,
            font=("Helvetica", 9, "bold")
        )
        subtitle_label.pack()

        separator = tk.Frame(main, bg=BORDER, height=1)
        separator.pack(fill="x", padx=55, pady=25)

        clue_counter = tk.Label(
            main,
            text=f"CLUE 0 OF {len(clues)}",
            bg=PANEL,
            fg=TEXT_DIM,
            font=("Helvetica", 9, "bold")
        )
        clue_counter.pack(pady=(0, 8))

        clue_name = tk.Label(
            main,
            text="NO CLUES REVEALED",
            bg=PANEL,
            fg=GOLD,
            font=("Helvetica", 11, "bold")
        )
        clue_name.pack(pady=(5, 3))

        clue_value = tk.Label(
            main,
            text="Click NEXT CLUE to begin.",
            bg=PANEL,
            fg=TEXT,
            font=("Helvetica", 18, "bold"),
            wraplength=700
        )
        clue_value.pack(pady=(0, 30))

        def reveal_film():
            revealed[0] = True

            title = str(
                film[1] or
                film[2] or
                "UNTITLED FILM"
            )

            original = str(film[2] or "").strip()

            title_label.config(text=title, fg=GOLD_LIGHT)

            if original and original.lower() != title.lower():
                subtitle_label.config(
                    text=f"ORIGINAL TITLE: {original}",
                    fg=TEXT_MUTED
                )
            else:
                subtitle_label.config(
                    text="MYSTERY SOLVED",
                    fg=GREEN
                )

            clue_name.config(text="FILM IDENTIFIED")
            clue_value.config(text=title, fg=GOLD_LIGHT)
            clue_counter.config(text=f"REVEALED • VAULT #{film[0]}")

            next_button.config(state="disabled")
            reveal_button.config(state="disabled")
            view_button.config(state="normal")

        def next_clue():
            if revealed[0]:
                return

            if clue_index[0] >= len(clues):
                reveal_film()
                return

            name, value = clues[clue_index[0]]
            clue_index[0] += 1

            clue_counter.config(
                text=f"CLUE {clue_index[0]} OF {len(clues)}"
            )
            clue_name.config(text=name)
            clue_value.config(text=value)

            if clue_index[0] >= len(clues):
                next_button.config(text="ALL CLUES SHOWN")

        button_bar = tk.Frame(window, bg=BG)
        button_bar.pack(fill="x", padx=35, pady=(0, 25))

        next_button = tk.Button(
            button_bar,
            text="NEXT CLUE",
            bg=GOLD,
            fg="#111111",
            activebackground=GOLD_LIGHT,
            activeforeground="#111111",
            relief="flat",
            bd=0,
            font=("Helvetica", 10, "bold"),
            padx=20,
            pady=11,
            cursor="hand2",
            command=next_clue
        )
        next_button.pack(side="left", padx=(0, 8))

        reveal_button = tk.Button(
            button_bar,
            text="REVEAL FILM",
            bg=PANEL_2,
            fg=TEXT,
            activebackground="#292929",
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            font=("Helvetica", 10, "bold"),
            padx=20,
            pady=11,
            cursor="hand2",
            command=reveal_film
        )
        reveal_button.pack(side="left", padx=(0, 8))

        view_button = tk.Button(
            button_bar,
            text="VIEW FILM",
            bg=PANEL_2,
            fg=TEXT,
            activebackground="#292929",
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            font=("Helvetica", 10, "bold"),
            padx=20,
            pady=11,
            cursor="hand2",
            state="disabled",
            command=lambda: self.open_view_dialog(film[0], return_target="menu")
        )
        view_button.pack(side="left", padx=(0, 8))

        another_button = tk.Button(
            button_bar,
            text="ANOTHER MYSTERY",
            bg=PANEL_2,
            fg=TEXT,
            activebackground="#292929",
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            font=("Helvetica", 10, "bold"),
            padx=20,
            pady=11,
            cursor="hand2",
            command=lambda: (window.destroy(), self.open_mystery_film())
        )
        another_button.pack(side="left", padx=(0, 8))

        window.bind("<Escape>", lambda event: window.go_back())
        window.bind("<space>", lambda event: next_clue())
        window.bind("<Return>", lambda event: reveal_film())

        window.transient(self)
        window.grab_set()
        window.focus_force()


    # ========================================================
    # TIMELINE
    # ========================================================

    def open_collection_timeline(self):

        films = self.get_filtered_films()

        if not films:
            messagebox.showinfo(
                "Collection Timeline",
                "There are no films available."
            )
            return

        dated = []
        unknown = []

        for film in films:

            # IMPORTANT:
            # film[23] = ORIGINAL RELEASE DATE.
            # film[5] = PRINT DATE and is NOT used here.
            if extract_year(film[23]) is None:
                unknown.append(film)
            else:
                dated.append(film)

        dated.sort(
            key=lambda film: (
                timeline_date_key(film[23]),
                str(film[1] or "").lower()
            )
        )

        unknown.sort(
            key=lambda film:
            str(film[1] or "").lower()
        )

        window = self.new_page()
        window.title("Film Collection Timeline")
        window.geometry("1050x750")
        window.minsize(800, 600)
        window.configure(bg=BG)
        window.transient(self)

        header = tk.Frame(window, bg=BG)
        header.pack(
            fill="x",
            padx=30,
            pady=(25, 10)
        )

        tk.Label(
            header,
            text="🎞 COLLECTION TIMELINE",
            bg=BG,
            fg=GOLD_LIGHT,
            font=("Helvetica", 25, "bold")
        ).pack(anchor="w")

        tk.Label(
            header,
            text="THE ORIGINAL RELEASE HISTORY OF YOUR FILM COLLECTION",
            bg=BG,
            fg=TEXT_MUTED,
            font=("Helvetica", 9, "bold")
        ).pack(anchor="w", pady=(3, 0))

        summary = tk.Frame(window, bg=BG)
        summary.pack(
            fill="x",
            padx=30,
            pady=(10, 18)
        )

        if dated:
            earliest = extract_year(dated[0][23])
            latest = extract_year(dated[-1][23])
        else:
            earliest = "—"
            latest = "—"

        for label, value in [
            ("EARLIEST RELEASE", earliest),
            ("LATEST RELEASE", latest),
            ("DATED FILMS", len(dated)),
            ("UNKNOWN", len(unknown))
        ]:

            box = tk.Frame(
                summary,
                bg=PANEL,
                highlightbackground=BORDER,
                highlightthickness=1
            )

            box.pack(
                side="left",
                fill="x",
                expand=True,
                padx=(0, 7)
            )

            tk.Label(
                box,
                text=label,
                bg=PANEL,
                fg=TEXT_DIM,
                font=("Helvetica", 8, "bold")
            ).pack(pady=(9, 1))

            tk.Label(
                box,
                text=str(value),
                bg=PANEL,
                fg=GOLD_LIGHT,
                font=("Helvetica", 17, "bold")
            ).pack(pady=(0, 9))

        container = tk.Frame(window, bg=BG)
        container.pack(
            fill="both",
            expand=True,
            padx=30,
            pady=(0, 20)
        )

        canvas = tk.Canvas(
            container,
            bg=BG,
            highlightthickness=0
        )

        scrollbar = ttk.Scrollbar(
            container,
            orient="vertical",
            command=canvas.yview
        )

        canvas.configure(
            yscrollcommand=scrollbar.set
        )

        canvas.pack(
            side="left",
            fill="both",
            expand=True
        )

        scrollbar.pack(side="right", fill="y")

        canvas.bind(
            "<MouseWheel>",
            lambda event:
            canvas.yview_scroll(
                int(-1 * (event.delta / 120)),
                "units"
            )
        )

        width = 960
        timeline_x = 105
        y = 45
        item_height = 120
        current_year = None

        for film in dated:

            year = extract_year(film[23])

            if year != current_year:

                current_year = year

                canvas.create_oval(
                    timeline_x - 12,
                    y - 12,
                    timeline_x + 12,
                    y + 12,
                    fill=GOLD,
                    outline=GOLD_LIGHT,
                    width=2
                )

                canvas.create_text(
                    timeline_x,
                    y - 34,
                    text=str(year),
                    fill=GOLD_LIGHT,
                    font=("Helvetica", 16, "bold"),
                    anchor="center"
                )

            tag = f"timeline:{film[0]}"

            row_x1 = timeline_x + 50
            row_x2 = width - 30
            row_y1 = y - 45
            row_y2 = y + 70

            canvas.create_line(
                timeline_x + 12,
                y,
                row_x1,
                y,
                fill=GOLD,
                width=2,
                tags=(tag,)
            )

            canvas.create_rectangle(
                row_x1,
                row_y1,
                row_x2,
                row_y2,
                fill=PANEL,
                outline=BORDER,
                tags=(tag,)
            )

            title_x = row_x1 + 18

            canvas.create_text(
                title_x,
                row_y1 + 19,
                text=str(film[1] or "UNTITLED").upper(),
                fill=TEXT,
                font=("Helvetica", 13, "bold"),
                anchor="w",
                tags=(tag,)
            )

            # THIS IS THE DATE THAT DRIVES THE TIMELINE.
            canvas.create_text(
                title_x,
                row_y1 + 44,
                text="RELEASED: " + str(film[23]),
                fill=GOLD_LIGHT,
                font=("Helvetica", 9, "bold"),
                anchor="w",
                tags=(tag,)
            )

            canvas.create_text(
                title_x,
                row_y1 + 66,
                text=(
                    str(film[3] or "UNKNOWN")
                    + "   •   "
                    + str(film[4] or "STOCK UNKNOWN")
                ),
                fill=TEXT_MUTED,
                font=("Helvetica", 9),
                anchor="w",
                tags=(tag,)
            )

            extra = []

            if film[6]:
                extra.append(str(film[6]) + " FT")

            if film[7]:
                extra.append(str(film[7]))

            if film[8]:
                extra.append(str(film[8]))

            if extra:
                canvas.create_text(
                    title_x,
                    row_y1 + 87,
                    text="   •   ".join(extra),
                    fill=TEXT_DIM,
                    font=("Helvetica", 8),
                    anchor="w",
                    tags=(tag,)
                )

            # Print date is shown only as additional information.
            if film[5]:
                canvas.create_text(
                    row_x2 - 15,
                    row_y1 + 43,
                    text="PRINT: " + str(film[5]),
                    fill=TEXT_DIM,
                    font=("Helvetica", 8),
                    anchor="e",
                    tags=(tag,)
                )

            canvas.create_text(
                row_x2 - 15,
                row_y1 + 20,
                text="VIEW →",
                fill=GOLD_LIGHT,
                font=("Helvetica", 8, "bold"),
                anchor="e",
                tags=(tag,)
            )

            y += item_height

        if unknown:

            y += 30

            canvas.create_oval(
                timeline_x - 12,
                y - 12,
                timeline_x + 12,
                y + 12,
                fill=TEXT_DIM,
                outline=TEXT_MUTED,
                width=2
            )

            canvas.create_text(
                timeline_x,
                y - 34,
                text="UNKNOWN",
                fill=TEXT_MUTED,
                font=("Helvetica", 14, "bold"),
                anchor="center"
            )

            y += 20

            for film in unknown:

                tag = f"timeline:{film[0]}"

                row_x1 = timeline_x + 50
                row_x2 = width - 30
                row_y1 = y
                row_y2 = y + 90

                canvas.create_line(
                    timeline_x + 12,
                    row_y1 + 45,
                    row_x1,
                    row_y1 + 45,
                    fill=BORDER,
                    width=2,
                    tags=(tag,)
                )

                canvas.create_rectangle(
                    row_x1,
                    row_y1,
                    row_x2,
                    row_y2,
                    fill=PANEL,
                    outline=BORDER,
                    tags=(tag,)
                )

                canvas.create_text(
                    row_x1 + 18,
                    row_y1 + 24,
                    text=str(film[1] or "UNTITLED").upper(),
                    fill=TEXT,
                    font=("Helvetica", 11, "bold"),
                    anchor="w",
                    tags=(tag,)
                )

                canvas.create_text(
                    row_x1 + 18,
                    row_y1 + 48,
                    text="ORIGINAL RELEASE DATE UNKNOWN",
                    fill=TEXT_MUTED,
                    font=("Helvetica", 9),
                    anchor="w",
                    tags=(tag,)
                )

                canvas.create_text(
                    row_x2 - 15,
                    row_y1 + 24,
                    text="VIEW →",
                    fill=GOLD_LIGHT,
                    font=("Helvetica", 8, "bold"),
                    anchor="e",
                    tags=(tag,)
                )

                y += 105

        if not dated and not unknown:

            canvas.create_text(
                width / 2,
                150,
                text="NO TIMELINE DATA",
                fill=TEXT_DIM,
                font=("Helvetica", 15, "bold")
            )

        canvas.configure(
            scrollregion=(0, 0, width, y + 50)
        )

        def timeline_motion(event):

            current = canvas.find_withtag("current")

            if current:
                if any(
                    t.startswith("timeline:")
                    for t in canvas.gettags(current[0])
                ):
                    canvas.config(cursor="hand2")
                    return

            canvas.config(cursor="")

        def timeline_click(event):

            current = canvas.find_withtag("current")

            if not current:
                return

            for tag in canvas.gettags(current[0]):

                if tag.startswith("timeline:"):

                    self.open_view_dialog(
                        int(tag.split(":", 1)[1]), return_target="menu"
                    )
                    return

        canvas.bind("<Motion>", timeline_motion)
        canvas.bind("<Button-1>", timeline_click)

        window.bind(
            "<Escape>",
            lambda event: window.go_back()
        )


    # ========================================================
    # VIEW FILM
    # ========================================================

    def open_view_dialog(self, film_id, return_target="menu"):


        film = next(
            (f for f in self.films if f[0] == film_id),
            None
        )

        if film is None:
            return

        window = self.new_page()
        window.return_target = return_target or ("database" if len(self._page_stack) == 1 else "menu")
        window.title("View Film")
        window.geometry("800x800")
        window.minsize(650, 600)
        window.configure(bg=BG)

        outer = tk.Frame(window, bg=BG)
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(
            outer,
            bg=BG,
            highlightthickness=0
        )

        scrollbar = ttk.Scrollbar(
            outer,
            orient="vertical",
            command=canvas.yview
        )

        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        content = tk.Frame(canvas, bg=BG)

        canvas_window = canvas.create_window(
            (0, 0),
            window=content,
            anchor="nw"
        )

        def resize(event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(
                canvas_window,
                width=canvas.winfo_width()
            )

        content.bind("<Configure>", resize)
        canvas.bind("<Configure>", resize)

        canvas.bind(
            "<MouseWheel>",
            lambda event:
            canvas.yview_scroll(
                int(-1 * (event.delta / 120)),
                "units"
            )
        )

        tk.Label(
            content,
            text=str(film[1] or "UNTITLED").upper(),
            bg=BG,
            fg=TEXT,
            font=("Helvetica", 25, "bold"),
            wraplength=700
        ).pack(pady=(25, 4), padx=30)

        if film[2]:
            tk.Label(
                content,
                text="ORIGINAL TITLE: " + str(film[2]),
                bg=BG,
                fg=TEXT_MUTED,
                font=("Helvetica", 10)
            ).pack(pady=(0, 18))

        cover = tk.Frame(
            content,
            bg=PANEL,
            highlightbackground=BORDER,
            highlightthickness=1
        )
        cover.pack(padx=30, pady=5)

        shown = False

        if film[17] and PIL_AVAILABLE:

            try:
                path = film[17]

                if not os.path.isabs(path):
                    path = os.path.join(BASE_DIR, path)

                if os.path.isfile(path):

                    image = Image.open(path)
                    image.thumbnail((350, 350))

                    photo = ImageTk.PhotoImage(image)

                    label = tk.Label(
                        cover,
                        image=photo,
                        bg=PANEL
                    )

                    label.image = photo
                    label.pack(padx=15, pady=15)

                    shown = True

            except Exception:
                pass

        if not shown:

            tk.Label(
                cover,
                text="🎞\n\nNO COVER IMAGE",
                bg=PANEL,
                fg=TEXT_DIM,
                font=("Helvetica", 14, "bold"),
                width=28,
                height=10
            ).pack(padx=15, pady=15)

        info = tk.Frame(
            content,
            bg=PANEL,
            highlightbackground=BORDER,
            highlightthickness=1
        )

        info.pack(fill="x", padx=30, pady=15)

        fields = [
            ("VAULT NUMBER", film[0]),
            ("TITLE", film[1]),
            ("ORIGINAL TITLE", film[2]),
            ("ORIGINAL RELEASE DATE", film[23]),
            ("FORMAT", film[3]),
            ("FILM STOCK", film[4]),
            ("PRINT DATE", film[5]),
            ("FILM LENGTH", film[6]),
            ("RUNTIME", film[7]),
            ("SOUND", film[8]),
            ("COUNTRY", film[9]),
            ("CONDITION", film[10]),
            ("VINEGAR SYNDROME", film[11]),
            ("SHRUNKEN", film[12]),
            ("NEEDS REPAIR", film[13]),
            ("PROJECTABLE", film[14]),
            ("SPLICES", film[15])
        ]

        for label, value in fields:

            row = tk.Frame(info, bg=PANEL)
            row.pack(fill="x", padx=15, pady=4)

            tk.Label(
                row,
                text=label,
                bg=PANEL,
                fg=TEXT_DIM,
                font=("Helvetica", 8, "bold"),
                width=25,
                anchor="w"
            ).pack(side="left")

            tk.Label(
                row,
                text=str(value or "—"),
                bg=PANEL,
                fg=TEXT,
                font=("Helvetica", 9),
                anchor="w"
            ).pack(side="left", fill="x", expand=True)

        if film[16]:

            tk.Label(
                content,
                text="NOTES",
                bg=BG,
                fg=GOLD_LIGHT,
                font=("Helvetica", 11, "bold")
            ).pack(anchor="w", padx=30, pady=(8, 5))

            tk.Label(
                content,
                text=str(film[16]),
                bg=PANEL,
                fg=TEXT_MUTED,
                justify="left",
                anchor="nw",
                wraplength=700,
                padx=15,
                pady=15
            ).pack(fill="x", padx=30, pady=(0, 15))

        # ====================================================
        # FILM PROVENANCE
        # ====================================================
        provenance_values = [
            ("ACQUIRED FROM", film[24]),
            ("PREVIOUS OWNER", film[25]),
            ("PURCHASE DATE", film[26]),
            ("PURCHASE PRICE", film[27]),
            ("SOURCE / WEBSITE", film[28]),
            ("PROVENANCE NOTES", film[29])
        ]

        if any(str(v or "").strip() for _, v in provenance_values):
            tk.Label(
                content,
                text="FILM PROVENANCE",
                bg=BG,
                fg=GOLD_LIGHT,
                font=("Helvetica", 11, "bold")
            ).pack(anchor="w", padx=30, pady=(8, 5))

            provenance = tk.Frame(
                content,
                bg=PANEL,
                highlightbackground=BORDER,
                highlightthickness=1
            )
            provenance.pack(fill="x", padx=30, pady=(0, 15))

            for label, value_text in provenance_values:
                row = tk.Frame(provenance, bg=PANEL)
                row.pack(fill="x", padx=15, pady=4)
                tk.Label(
                    row, text=label, bg=PANEL, fg=TEXT_DIM,
                    font=("Helvetica", 8, "bold"), width=25, anchor="w"
                ).pack(side="left")
                tk.Label(
                    row, text=str(value_text or "—"), bg=PANEL, fg=TEXT,
                    font=("Helvetica", 9), anchor="w", justify="left",
                    wraplength=500
                ).pack(side="left", fill="x", expand=True)

        digital = tk.Frame(
            content,
            bg=PANEL,
            highlightbackground=BORDER,
            highlightthickness=1
        )

        digital.pack(fill="x", padx=30, pady=20)

        tk.Label(
            digital,
            text="DIGITAL VERSIONS",
            bg=PANEL,
            fg=GOLD_LIGHT,
            font=("Helvetica", 11, "bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))

        if film[21]:

            row = tk.Frame(digital, bg=PANEL)
            row.pack(fill="x", padx=15, pady=5)

            tk.Label(
                row,
                text="RAW / GRINDHOUSE",
                bg=PANEL,
                fg=TEXT,
                font=("Helvetica", 9, "bold")
            ).pack(side="left")

            tk.Button(
                row,
                text="▶ WATCH RAW",
                bg=GOLD,
                fg="#080808",
                relief="flat",
                bd=0,
                padx=14,
                pady=7,
                command=lambda: open_video_in_vlc(film[21])
            ).pack(side="right")

        else:

            tk.Label(
                digital,
                text="NO RAW DIGITAL COPY",
                bg=PANEL,
                fg=TEXT_DIM,
                font=("Helvetica", 9, "bold")
            ).pack(anchor="w", padx=15, pady=5)

        if film[22]:

            row = tk.Frame(digital, bg=PANEL)
            row.pack(fill="x", padx=15, pady=12)

            tk.Label(
                row,
                text="RESTORED VERSION",
                bg=PANEL,
                fg=TEXT,
                font=("Helvetica", 9, "bold")
            ).pack(side="left")

            tk.Button(
                row,
                text="▶ WATCH RESTORED",
                bg=GREEN,
                fg="#080808",
                relief="flat",
                bd=0,
                padx=14,
                pady=7,
                command=lambda: open_video_in_vlc(film[22])
            ).pack(side="right")

        else:

            tk.Label(
                digital,
                text="NO RESTORED DIGITAL COPY",
                bg=PANEL,
                fg=TEXT_DIM,
                font=("Helvetica", 9, "bold")
            ).pack(anchor="w", padx=15, pady=5)

        buttons = tk.Frame(content, bg=BG)
        buttons.pack(pady=25)

        tk.Button(
            buttons,
            text="EDIT FILM",
            bg=GOLD,
            fg="#080808",
            relief="flat",
            bd=0,
            padx=25,
            pady=10,
            command=lambda: (
                getattr(window, "return_target", "menu"),
                window.destroy(),
                self.open_edit_dialog(film_id, return_target=getattr(window, "return_target", "menu"))
            )
        ).pack(side="left", padx=5)

        tk.Button(
            buttons,
            text="🎟 PRINT TICKET",
            bg=PANEL_2,
            fg=GOLD_LIGHT,
            relief="flat",
            bd=0,
            padx=20,
            pady=10,
            command=lambda: self.print_film_ticket(film_id)
        ).pack(side="left", padx=5)

        tk.Button(
            buttons,
            text="DELETE",
            bg=PANEL_2,
            fg=RED,
            relief="flat",
            bd=0,
            padx=20,
            pady=10,
            command=lambda: (
                window.destroy(),
                self.delete_film(film_id)
            )
        ).pack(side="left", padx=5)

        window.bind(
            "<Escape>",
            lambda event: window.go_back()
        )


    # ========================================================
    # EDITOR
    # ========================================================

    def open_add_dialog(self, return_target=None):
        self.open_film_editor(None, return_target=return_target)


    def open_edit_dialog(self, film_id, return_target=None):
        self.open_film_editor(film_id, return_target=return_target)


    def open_film_editor(self, film_id, return_target=None):

        existing = next(
            (f for f in self.films if f[0] == film_id),
            None
        )

        window = self.new_page()
        window.return_target = return_target or ("database" if not self._page_stack[:-1] else "menu")
        window.title(
            "Edit Film" if existing else "Add Film"
        )
        window.geometry("760x800")
        window.minsize(650, 600)
        window.configure(bg=BG)
        window.transient(self)

        outer = tk.Frame(window, bg=BG)
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(
            outer,
            bg=BG,
            highlightthickness=0
        )

        scrollbar = ttk.Scrollbar(
            outer,
            orient="vertical",
            command=canvas.yview
        )

        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        form = tk.Frame(canvas, bg=BG)

        form_window = canvas.create_window(
            (0, 0),
            window=form,
            anchor="nw"
        )

        def configure_form(event=None):
            canvas.configure(
                scrollregion=canvas.bbox("all")
            )
            canvas.itemconfigure(
                form_window,
                width=canvas.winfo_width()
            )

        form.bind("<Configure>", configure_form)
        canvas.bind("<Configure>", configure_form)

        canvas.bind(
            "<MouseWheel>",
            lambda event:
            canvas.yview_scroll(
                int(-1 * (event.delta / 120)),
                "units"
            )
        )

        tk.Label(
            form,
            text="EDIT FILM" if existing else "ADD FILM",
            bg=BG,
            fg=GOLD_LIGHT,
            font=("Helvetica", 24, "bold")
        ).pack(pady=(25, 20))

        fields = {}

        def entry(label, value="", multiline=False):

            tk.Label(
                form,
                text=label,
                bg=BG,
                fg=TEXT_MUTED,
                font=("Helvetica", 8, "bold")
            ).pack(
                anchor="w",
                padx=30,
                pady=(8, 3)
            )

            if multiline:

                widget = tk.Text(
                    form,
                    bg=PANEL_2,
                    fg=TEXT,
                    insertbackground=GOLD,
                    relief="flat",
                    height=5,
                    wrap="word"
                )

                widget.insert("1.0", value or "")

            else:

                widget = tk.Entry(
                    form,
                    bg=PANEL_2,
                    fg=TEXT,
                    insertbackground=GOLD,
                    relief="flat"
                )

                widget.insert(0, value or "")

            widget.pack(
                fill="x",
                padx=30,
                pady=(0, 3),
                ipady=7
            )

            fields[label] = widget

        def combo(label, values, value=""):

            # EDIT MODE: show exactly what is stored for this film.
            # Do not replace a saved choice with a generic default.
            # Matching is case-insensitive only so values such as "yes"
            # still select the existing YES option without changing the
            # actual database value until the user saves.
            value_text = "" if value is None else str(value).strip()
            normalized = {str(v).strip().upper(): v for v in values}

            if existing is not None:
                if value_text.upper() in normalized:
                    combo_value = normalized[value_text.upper()]
                else:
                    # Preserve an unusual/blank saved value rather than
                    # inventing a different selection.
                    combo_value = value_text
            else:
                # Defaults apply only to a brand-new film.
                if value_text.upper() in normalized:
                    combo_value = normalized[value_text.upper()]
                else:
                    combo_value = values[0]

            tk.Label(
                form,
                text=label,
                bg=BG,
                fg=TEXT_MUTED,
                font=("Helvetica", 8, "bold")
            ).pack(
                anchor="w",
                padx=30,
                pady=(8, 3)
            )

            widget = ttk.Combobox(
                form,
                values=values,
                state="readonly"
            )

            widget.set(combo_value)

            widget.pack(
                fill="x",
                padx=30,
                pady=(0, 3)
            )

            fields[label] = widget

        def value(label):

            widget = fields[label]

            if isinstance(widget, tk.Text):
                return widget.get(
                    "1.0",
                    "end"
                ).strip()

            return widget.get().strip()

        old = existing

        entry("TITLE", old[1] if old else "")
        entry("ORIGINAL TITLE", old[2] if old else "")

        combo(
            "FORMAT",
            FILM_FORMATS,
            old[3] if old else "8MM"
        )

        entry("FILM STOCK", old[4] if old else "")

        # NEW FIELD:
        # This is the actual release date/year.
        entry(
            "ORIGINAL RELEASE DATE",
            old[23] if old else ""
        )

        # Print date remains its own separate field.
        entry(
            "PRINT DATE",
            old[5] if old else ""
        )

        entry("FILM LENGTH", old[6] if old else "")
        entry("RUNTIME", old[7] if old else "")

        combo(
            "SOUND",
            ["YES", "NO", "UNKNOWN"],
            old[8] if old else "UNKNOWN"
        )

        entry("COUNTRY", old[9] if old else "")
        entry("CONDITION", old[10] if old else "")

        combo(
            "VINEGAR SYNDROME",
            ["YES", "NO", "UNKNOWN"],
            old[11] if old else "UNKNOWN"
        )

        combo(
            "SHRUNKEN",
            ["YES", "NO", "UNKNOWN"],
            old[12] if old else "UNKNOWN"
        )

        combo(
            "NEEDS REPAIR",
            ["YES", "NO"],
            old[13] if old else "NO"
        )

        combo(
            "PROJECTABLE",
            ["YES", "NO"],
            old[14] if old else "YES"
        )

        entry("SPLICES", old[15] if old else "")
        entry("NOTES", old[16] if old else "", True)
        entry("MAIN IMAGE", old[17] if old else "")
        entry("ADDITIONAL IMAGES", old[18] if old else "")
        entry("RAW VIDEO", old[21] if old else "")
        entry("RESTORED VIDEO", old[22] if old else "")

        # ====================================================
        # FILM PROVENANCE
        # ====================================================
        tk.Label(
            form,
            text="FILM PROVENANCE",
            bg=BG,
            fg=GOLD_LIGHT,
            font=("Helvetica", 13, "bold")
        ).pack(anchor="w", padx=30, pady=(25, 5))

        entry("ACQUIRED FROM", old[24] if old else "")
        entry("PREVIOUS OWNER", old[25] if old else "")
        entry("PURCHASE DATE", old[26] if old else "")
        entry("PURCHASE PRICE", old[27] if old else "")
        entry("SOURCE / WEBSITE", old[28] if old else "")
        entry("PROVENANCE NOTES", old[29] if old else "", True)

        # Keep the action buttons OUTSIDE the scrolling form so they are
        # always visible and clickable, even when the form is long.
        buttons = tk.Frame(outer, bg=BG)
        buttons.pack(side="bottom", fill="x", pady=(8, 12))

        def save():

            title = value("TITLE")

            if not title:
                messagebox.showwarning(
                    "Missing Title",
                    "Please enter a film title.",
                    parent=window
                )
                return

            now = datetime.now().isoformat(
                timespec="seconds"
            )

            vals = [
                title,
                value("ORIGINAL TITLE"),
                value("FORMAT"),
                value("FILM STOCK"),
                value("PRINT DATE"),
                value("FILM LENGTH"),
                value("RUNTIME"),
                value("SOUND"),
                value("COUNTRY"),
                value("CONDITION"),
                value("VINEGAR SYNDROME"),
                value("SHRUNKEN"),
                value("NEEDS REPAIR"),
                value("PROJECTABLE"),
                value("SPLICES"),
                value("NOTES"),
                value("MAIN IMAGE"),
                value("ADDITIONAL IMAGES"),
                value("RAW VIDEO"),
                value("RESTORED VIDEO"),
                value("ORIGINAL RELEASE DATE"),
                value("ACQUIRED FROM"),
                value("PREVIOUS OWNER"),
                value("PURCHASE DATE"),
                value("PURCHASE PRICE"),
                value("SOURCE / WEBSITE"),
                value("PROVENANCE NOTES")
            ]

            connection = sqlite3.connect(DB_FILE)
            cursor = connection.cursor()

            if existing:

                cursor.execute("""
                    UPDATE films SET
                        title=?,
                        original_title=?,
                        format=?,
                        film_stock=?,
                        print_date=?,
                        film_length=?,
                        runtime=?,
                        sound=?,
                        country=?,
                        condition=?,
                        vinegar_syndrome=?,
                        shrunken=?,
                        needs_repair=?,
                        projectable=?,
                        splices=?,
                        notes=?,
                        main_image=?,
                        additional_images=?,
                        raw_video=?,
                        restored_video=?,
                        release_date=?,
                        acquired_from=?,
                        previous_owner=?,
                        purchase_date=?,
                        purchase_price=?,
                        source_website=?,
                        provenance_notes=?,
                        updated_at=?
                    WHERE id=?
                """, (
                    vals[0],
                    vals[1],
                    vals[2],
                    vals[3],
                    vals[4],
                    vals[5],
                    vals[6],
                    vals[7],
                    vals[8],
                    vals[9],
                    vals[10],
                    vals[11],
                    vals[12],
                    vals[13],
                    vals[14],
                    vals[15],
                    vals[16],
                    vals[17],
                    vals[18],
                    vals[19],
                    vals[20],
                    vals[21],
                    vals[22],
                    vals[23],
                    vals[24],
                    vals[25],
                    vals[26],
                    now,
                    existing[0]
                ))

            else:

                cursor.execute("""
                    INSERT INTO films (
                        title,
                        original_title,
                        format,
                        film_stock,
                        print_date,
                        film_length,
                        runtime,
                        sound,
                        country,
                        condition,
                        vinegar_syndrome,
                        shrunken,
                        needs_repair,
                        projectable,
                        splices,
                        notes,
                        main_image,
                        additional_images,
                        created_at,
                        updated_at,
                        raw_video,
                        restored_video,
                        release_date,
                        acquired_from,
                        previous_owner,
                        purchase_date,
                        purchase_price,
                        source_website,
                        provenance_notes
                    )
                    VALUES (
                        ?,?,?,?,?,?,?,?,?,?,
                        ?,?,?,?,?,?,?,?,?,?,
                        ?,?,?,?,?,?,?,?,?
                    )
                """, (
                    vals[0],
                    vals[1],
                    vals[2],
                    vals[3],
                    vals[4],
                    vals[5],
                    vals[6],
                    vals[7],
                    vals[8],
                    vals[9],
                    vals[10],
                    vals[11],
                    vals[12],
                    vals[13],
                    vals[14],
                    vals[15],
                    vals[16],
                    vals[17],
                    now,
                    now,
                    vals[18],
                    vals[19],
                    vals[20],
                    vals[21],
                    vals[22],
                    vals[23],
                    vals[24],
                    vals[25],
                    vals[26]
                ))

            try:
                connection.commit()
            except Exception as error:
                connection.rollback()
                connection.close()
                messagebox.showerror(
                    "Could Not Save Film",
                    "The film could not be saved.\n\n" + str(error),
                    parent=window
                )
                return

            connection.close()

            try:
                self.load_films()
                self.image_cache.clear()
                self.refresh_archive()
            except Exception as error:
                messagebox.showerror(
                    "Saved With Refresh Error",
                    "The film was saved, but the archive could not refresh.\n\n" + str(error),
                    parent=window
                )
                return

            window.destroy()

        tk.Button(
            buttons,
            text="CANCEL",
            bg=PANEL_2,
            fg=TEXT_MUTED,
            relief="flat",
            bd=0,
            padx=25,
            pady=10,
            command=window.go_back
        ).pack(side="left", padx=5)

        tk.Button(
            buttons,
            text="SAVE FILM",
            bg=GOLD,
            fg="#080808",
            activebackground=GOLD_LIGHT,
            relief="flat",
            bd=0,
            font=("Helvetica", 10, "bold"),
            padx=30,
            pady=10,
            command=save
        ).pack(side="left", padx=5)

        window.bind(
            "<Escape>",
            lambda event: window.go_back()
        )


    # ========================================================
    # FILM AWARDS
    # ========================================================

    def open_film_awards(self):
        films = self.get_filtered_films()

        if not films:
            messagebox.showinfo(
                "Film Awards",
                "There are no films available in the current selection."
            )
            return

        def year_value(value):
            return extract_year(value)

        def number_value(value):
            if value is None:
                return None
            match = re.search(r"\d+(?:\.\d+)?", str(value).replace(",", ""))
            return float(match.group(0)) if match else None

        def completeness(film):
            fields = [film[1], film[2], film[3], film[4], film[5], film[6],
                      film[7], film[8], film[9], film[10], film[14], film[15],
                      film[23]]
            return sum(bool(str(v or "").strip()) for v in fields)

        awards = []

        dated = [(f, year_value(f[23])) for f in films if year_value(f[23]) is not None]
        if dated:
            oldest = min(dated, key=lambda x: x[1])
            newest = max(dated, key=lambda x: x[1])
            awards.append(("🏆", "OLDEST FILM", oldest[0], f"Original release: {oldest[1]}"))
            awards.append(("🆕", "MOST RECENT RELEASE", newest[0], f"Original release: {newest[1]}"))

        lengths = [(f, number_value(f[6])) for f in films if number_value(f[6]) is not None]
        if lengths:
            winner = max(lengths, key=lambda x: x[1])
            awards.append(("📏", "LONGEST FILM", winner[0], f"Film length: {winner[0][6]}"))

        runtimes = [(f, number_value(f[7])) for f in films if number_value(f[7]) is not None]
        if runtimes:
            winner = max(runtimes, key=lambda x: x[1])
            awards.append(("⏱️", "LONGEST RUNTIME", winner[0], f"Runtime: {winner[0][7]}"))

        prints = [(f, year_value(f[5])) for f in films if year_value(f[5]) is not None]
        if prints:
            winner = min(prints, key=lambda x: x[1])
            awards.append(("📜", "OLDEST PRINT", winner[0], f"Print date: {winner[0][5]}"))

        splices = [(f, number_value(f[15])) for f in films if number_value(f[15]) is not None]
        if splices:
            winner = max(splices, key=lambda x: x[1])
            awards.append(("✂️", "MOST SPLICED FILM", winner[0], f"Splices: {winner[0][15]}"))

        for fmt, icon, name in [
            ("8MM", "8️⃣", "8MM CHAMPION"),
            ("SUPER 8", "🎞️", "SUPER 8 CHAMPION"),
            ("16MM", "🎥", "16MM CHAMPION")
        ]:
            matches = [f for f in films if str(f[3] or "").upper() == fmt]
            if matches:
                winner = max(matches, key=lambda f: (year_value(f[23]) or 0, completeness(f)))
                awards.append((icon, name, winner, f"Best release-era entry: {f'{year_value(winner[23])}' if year_value(winner[23]) else 'Release date unknown'}"))

        sound = [f for f in films if str(f[8] or "").strip().upper() in ("YES", "TRUE", "1", "SOUND")]
        if sound:
            winner = max(sound, key=completeness)
            awards.append(("🔊", "SOUND CHAMPION", winner, "Best documented sound print"))

        repair = [f for f in films if str(f[13] or "").strip().upper() in ("YES", "TRUE", "1")]
        if repair:
            winner = max(repair, key=completeness)
            awards.append(("🔧", "NEEDS SOME LOVE", winner, "Marked as needing repair"))

        vinegar = [f for f in films if str(f[11] or "").strip().upper() in ("YES", "TRUE", "1")]
        if vinegar:
            winner = max(vinegar, key=completeness)
            awards.append(("🍷", "VINEGAR SURVIVOR", winner, "Marked with vinegar syndrome"))

        documented = max(films, key=completeness)
        awards.append(("📋", "BEST DOCUMENTED FILM", documented, f"Metadata fields completed: {completeness(documented)} / 13"))

        presented = max(films, key=lambda f: (bool(f[17]), len(str(f[18] or "").strip())))
        image_count = 1 if presented[17] else 0
        if presented[18]:
            image_count += len([x for x in str(presented[18]).split("|") if x.strip()])
        awards.append(("🖼️", "BEST PRESENTED FILM", presented, f"Cover/additional images: {image_count}"))

        digital = [f for f in films if f[21] or f[22]]
        if digital:
            winner = max(digital, key=lambda f: (bool(f[21]) + bool(f[22]), completeness(f)))
            copies = []
            if winner[21]: copies.append("RAW")
            if winner[22]: copies.append("RESTORED")
            awards.append(("💾", "DIGITAL READY", winner, "Digital copies: " + " + ".join(copies)))

        champion = max(films, key=lambda f: (
            completeness(f), bool(f[17]), bool(f[21]) + bool(f[22]),
            year_value(f[23]) or 9999
        ))
        awards.append(("👑", "VAULT CHAMPION", champion, "Highest overall vault profile"))

        window = self.new_page()
        window.title("Film Awards")
        window.geometry("1100x800")
        window.minsize(850, 650)
        window.configure(bg=BG)
        window.transient(self)

        tk.Label(window, text="🏆 FILM AWARDS", bg=BG, fg=GOLD_LIGHT,
                 font=("Helvetica", 28, "bold")).pack(pady=(25, 3))
        tk.Label(window, text="THE BEST OF YOUR FILM VAULT", bg=BG, fg=TEXT_MUTED,
                 font=("Helvetica", 10, "bold")).pack(pady=(0, 18))

        canvas = tk.Canvas(window, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(window, orient="vertical", command=canvas.yview)
        content = tk.Frame(canvas, bg=BG)
        canvas_window = canvas.create_window((0, 0), window=content, anchor="nw")

        def resize(event):
            canvas.itemconfigure(canvas_window, width=event.width)
        canvas.bind("<Configure>", resize)
        content.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True, padx=(25, 0), pady=(0, 20))
        scrollbar.pack(side="right", fill="y", padx=(0, 20), pady=(0, 20))

        columns = 2
        for i, (icon, award, film, detail) in enumerate(awards):
            card = tk.Frame(content, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
            card.grid(row=i // columns, column=i % columns, sticky="nsew", padx=8, pady=8)
            content.grid_columnconfigure(i % columns, weight=1)

            tk.Label(card, text=icon, bg=PANEL, fg=GOLD_LIGHT, font=("Segoe UI Emoji", 25)).pack(pady=(15, 2))
            tk.Label(card, text=award, bg=PANEL, fg=GOLD_LIGHT, font=("Helvetica", 12, "bold")).pack()
            tk.Label(card, text=str(film[1] or film[2] or "UNTITLED").upper(), bg=PANEL,
                     fg=TEXT, font=("Helvetica", 16, "bold"), wraplength=430, justify="center").pack(pady=(10, 4))
            tk.Label(card, text=detail, bg=PANEL, fg=TEXT_MUTED, font=("Helvetica", 9),
                     wraplength=430, justify="center").pack(pady=(0, 15))
            self.button(card, "VIEW FILM", lambda fid=film[0]: self.open_view_dialog(fid, return_target="menu")).pack(pady=(0, 15))

        window.bind("<Escape>", lambda event: window.go_back())

    # ========================================================
    # DELETE
    # ========================================================

    def delete_film(self, film_id):

        film = next(
            (f for f in self.films if f[0] == film_id),
            None
        )

        if film is None:
            return

        if not messagebox.askyesno(
            "Delete Film",
            "Delete this film from the vault?\n\n"
            + str(film[1] or "UNTITLED"),
            parent=self
        ):
            return

        connection = sqlite3.connect(DB_FILE)
        connection.execute(
            "DELETE FROM films WHERE id=?",
            (film_id,)
        )
        connection.commit()
        connection.close()

        self.load_films()
        self.image_cache.clear()
        self.refresh_archive()


    # ========================================================
    # SLOT MACHINE
    # ========================================================

    def open_slot_machine(self):

        films = self.get_filtered_films()

        if not films:
            messagebox.showinfo(
                "Film Slot Machine",
                "There are no films available."
            )
            return

        window = self.new_page()
        window.title("Film Slot Machine")
        window.geometry("850x520")
        window.configure(bg=BG)
        window.transient(self)

        tk.Label(
            window,
            text="🎰 FILM SLOT MACHINE",
            bg=BG,
            fg=GOLD_LIGHT,
            font=("Helvetica", 26, "bold")
        ).pack(pady=(28, 4))

        tk.Label(
            window,
            text="LET THE REELS DECIDE",
            bg=BG,
            fg=TEXT_MUTED,
            font=("Helvetica", 10, "bold")
        ).pack(pady=(0, 22))

        machine = tk.Frame(
            window,
            bg=PANEL,
            highlightbackground=GOLD,
            highlightthickness=2
        )
        machine.pack(
            padx=35,
            fill="x"
        )

        reels = tk.Frame(machine, bg=PANEL)
        reels.pack(
            padx=25,
            pady=28,
            fill="x"
        )

        labels = []

        for _ in range(3):

            frame = tk.Frame(
                reels,
                bg="#080808",
                highlightbackground=BORDER,
                highlightthickness=2
            )
            frame.pack(
                side="left",
                expand=True,
                fill="both",
                padx=8
            )

            label = tk.Label(
                frame,
                text="READY",
                bg="#080808",
                fg=GOLD_LIGHT,
                font=("Helvetica", 17, "bold"),
                wraplength=210,
                justify="center"
            )

            label.pack(
                expand=True,
                fill="both",
                padx=12,
                pady=30
            )

            labels.append(label)

        result = tk.Label(
            window,
            text="PRESS SPIN",
            bg=BG,
            fg=TEXT,
            font=("Helvetica", 13, "bold")
        )
        result.pack(pady=(22, 12))

        buttons = tk.Frame(window, bg=BG)
        buttons.pack()

        spin = tk.Button(
            buttons,
            text="🎰 SPIN",
            bg=GOLD,
            fg="#080808",
            relief="flat",
            bd=0,
            font=("Helvetica", 12, "bold"),
            padx=30,
            pady=12
        )
        spin.pack(side="left", padx=7)

        current = {"film": None}

        view = self.button(buttons, "VIEW FILM", lambda: self.open_view_dialog(current["film"][0], return_target="menu"))
        view.configure(state="disabled")
        view.pack(side="left", padx=7)

        def spin_now():

            spin.config(state="disabled")
            view.config(state="disabled")

            winners = [
                random.choice(films),
                random.choice(films),
                random.choice(films)
            ]

            durations = [1000, 1500, 2000]

            def animate(index, elapsed):

                if elapsed >= durations[index]:

                    labels[index].config(
                        text=str(
                            winners[index][1] or "UNTITLED"
                        ).upper()
                    )

                    if index == 2:

                        current["film"] = winners[1]

                        result.config(
                            text="★ THE REELS HAVE CHOSEN ★\n"
                            + str(
                                winners[1][1] or "UNTITLED"
                            ).upper(),
                            fg=GOLD_LIGHT
                        )

                        spin.config(state="normal")
                        view.config(state="normal")

                    return

                labels[index].config(
                    text=str(
                        random.choice(films)[1] or "UNTITLED"
                    ).upper()
                )

                window.after(
                    70,
                    lambda:
                    animate(index, elapsed + 70)
                )

            for i in range(3):
                animate(i, 0)

        def view_winner():

            if current["film"]:
                window.destroy()
                self.open_view_dialog(
                    current["film"][0]
                )

        spin.config(command=spin_now)
        view.config(command=view_winner)

        window.bind(
            "<Escape>",
            lambda event: window.go_back()
        )


    # ========================================================
    # PRINT TICKET
    # ========================================================

    def _create_ticket_pdf(self, film, path):

        if not REPORTLAB_AVAILABLE:
            raise RuntimeError("ReportLab is not installed.")

        pdf = pdf_canvas.Canvas(
            path,
            pagesize=(8.5 * inch, 4.2 * inch)
        )

        width = 8.5 * inch
        height = 4.2 * inch

        pdf.setFillColorRGB(0.06, 0.06, 0.06)
        pdf.rect(0, 0, width, height, fill=1, stroke=0)

        pdf.setStrokeColorRGB(0.78, 0.64, 0.36)
        pdf.setLineWidth(2)
        pdf.rect(
            18,
            18,
            width - 36,
            height - 36,
            fill=0,
            stroke=1
        )

        pdf.setFillColorRGB(0.88, 0.76, 0.48)
        pdf.setFont("Helvetica-Bold", 20)
        pdf.drawString(
            38,
            height - 55,
            "THE REEL ARCHIVE"
        )

        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(
            38,
            height - 78,
            "ADMIT ONE"
        )

        pdf.setFont("Helvetica-Bold", 15)
        pdf.drawString(
            38,
            height - 112,
            str(film[1] or "UNTITLED")[:55]
        )

        info = [
            ("ORIGINAL TITLE", film[2]),
            ("FORMAT", film[3]),
            ("SOUND", film[8]),
            ("LENGTH", film[6]),
            ("RUNTIME", film[7]),
            ("RELEASE DATE", film[23]),
            ("PRINT DATE", film[5]),
            ("COUNTRY", film[9]),
            ("VAULT NUMBER", film[0])
        ]

        y = height - 145

        for label, value in info:

            pdf.setFillColorRGB(0.45, 0.45, 0.45)
            pdf.setFont("Helvetica-Bold", 7)
            pdf.drawString(38, y, label)

            pdf.setFillColorRGB(0.85, 0.85, 0.85)
            pdf.setFont("Helvetica", 9)
            pdf.drawString(
                125,
                y,
                str(value or "—")[:40]
            )

            y -= 18

        pdf.setFillColorRGB(0.88, 0.76, 0.48)
        pdf.setFont("Helvetica-Bold", 10)

        pdf.drawCentredString(
            width - 80,
            height / 2 + 15,
            "FILM"
        )

        pdf.drawCentredString(
            width - 80,
            height / 2 - 2,
            "VAULT"
        )

        pdf.showPage()
        pdf.save()


    def print_film_ticket(self, film_id):

        if not REPORTLAB_AVAILABLE:
            messagebox.showerror(
                "ReportLab Required",
                "Install ReportLab with:\n\npip install reportlab"
            )
            return

        film = next(
            (f for f in self.films if f[0] == film_id),
            None
        )

        if film is None:
            return

        window = self.new_page()
        window.title("Film Ticket")
        window.geometry("720x470")
        window.configure(bg=BG)

        tk.Label(
            window,
            text="🎟 FILM TICKET",
            bg=BG,
            fg=GOLD_LIGHT,
            font=("Helvetica", 22, "bold")
        ).pack(pady=(22, 10))

        preview = tk.Frame(
            window,
            bg="#0f0f0f",
            highlightbackground=GOLD,
            highlightthickness=2
        )
        preview.pack(
            fill="x",
            padx=35,
            pady=10
        )

        tk.Label(
            preview,
            text="THE REEL ARCHIVE",
            bg="#0f0f0f",
            fg=GOLD_LIGHT,
            font=("Helvetica", 18, "bold")
        ).pack(pady=(15, 2))

        tk.Label(
            preview,
            text="ADMIT ONE",
            bg="#0f0f0f",
            fg=TEXT_MUTED,
            font=("Helvetica", 8, "bold")
        ).pack()

        tk.Label(
            preview,
            text=str(film[1] or "UNTITLED").upper(),
            bg="#0f0f0f",
            fg=TEXT,
            font=("Helvetica", 15, "bold"),
            wraplength=550
        ).pack(pady=12)

        tk.Label(
            preview,
            text=(
                "FORMAT: " + str(film[3] or "—")
                + "     SOUND: " + str(film[8] or "—")
                + "     RELEASE: " + str(film[23] or "—")
                + "\n"
                "PRINT: " + str(film[5] or "—")
                + "     LENGTH: " + str(film[6] or "—")
                + "     VAULT #: " + str(film[0])
            ),
            bg="#0f0f0f",
            fg=TEXT_MUTED,
            font=("Helvetica", 8),
            justify="center"
        ).pack(pady=(0, 17))

        buttons = tk.Frame(window, bg=BG)
        buttons.pack(pady=15)

        def save_pdf():

            filename = (
                str(film[1] or "film")
                .replace("/", "_")
                .replace("\\", "_")
                + "_ticket.pdf"
            )

            path = filedialog.asksaveasfilename(
                parent=window,
                title="Save Film Ticket",
                initialfile=filename,
                defaultextension=".pdf",
                filetypes=[("PDF files", "*.pdf")]
            )

            if not path:
                return

            try:
                self._create_ticket_pdf(film, path)

                messagebox.showinfo(
                    "Ticket Saved",
                    "Film ticket saved successfully.",
                    parent=window
                )

            except Exception as error:
                messagebox.showerror(
                    "Could Not Save Ticket",
                    str(error),
                    parent=window
                )

        def print_ticket():

            try:

                temp = tempfile.NamedTemporaryFile(
                    delete=False,
                    suffix=".pdf"
                )

                path = temp.name
                temp.close()

                self._create_ticket_pdf(film, path)

                if os.name == "nt":
                    os.startfile(path, "print")

                    messagebox.showinfo(
                        "Printing",
                        "The ticket was sent to the default printer.",
                        parent=window
                    )

                else:
                    messagebox.showinfo(
                        "Print",
                        "PDF created at:\n\n" + path,
                        parent=window
                    )

            except Exception as error:

                messagebox.showerror(
                    "Could Not Print",
                    str(error),
                    parent=window
                )

        tk.Button(
            buttons,
            text="🎟 PRINT TICKET",
            bg=GOLD,
            fg="#080808",
            relief="flat",
            bd=0,
            padx=20,
            pady=10,
            command=print_ticket
        ).pack(side="left", padx=5)

        tk.Button(
            buttons,
            text="SAVE AS PDF",
            bg=PANEL_2,
            fg=TEXT,
            relief="flat",
            bd=0,
            padx=20,
            pady=10,
            command=save_pdf
        ).pack(side="left", padx=5)

        window.bind(
            "<Escape>",
            lambda event: window.go_back()
        )


    # COLLECTION STATISTICS
    # ========================================================

    def open_collection_statistics(self):

        films = self.get_filtered_films()

        if not films:
            messagebox.showinfo(
                "Vault Statistics",
                "There are no films in the current collection/filter.",
                parent=self
            )
            return

        window = self.new_page()
        window.title("The Reel Archive — Collection Statistics")
        window.geometry("1120x820")
        window.minsize(900, 650)
        window.configure(bg=BG)
        window.transient(self)

        tk.Label(
            window,
            text="📊 COLLECTION STATISTICS",
            bg=BG,
            fg=GOLD_LIGHT,
            font=("Helvetica", 25, "bold")
        ).pack(pady=(25, 3))

        tk.Label(
            window,
            text=("A COMPLETE STATISTICAL LOOK AT " +
                  ("YOUR CURRENT FILTER" if len(films) != len(self.films)
                   else "YOUR FILM VAULT")),
            bg=BG,
            fg=TEXT_MUTED,
            font=("Helvetica", 10, "bold")
        ).pack(pady=(0, 18))

        outer = tk.Frame(window, bg=BG)
        outer.pack(fill="both", expand=True, padx=25, pady=(0, 15))

        canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        content = tk.Frame(canvas, bg=BG)
        canvas_window = canvas.create_window((0, 0), window=content, anchor="nw")

        def resize(event):
            canvas.itemconfigure(canvas_window, width=event.width)

        canvas.bind("<Configure>", resize)
        content.bind(
            "<Configure>",
            lambda event: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def safe_int(value):
            try:
                text = str(value or "").replace(",", "").strip()
                if not text:
                    return 0
                return int(float(text))
            except Exception:
                return 0

        def parse_minutes(value):
            text = str(value or "").strip().lower()
            if not text:
                return 0
            try:
                if ":" in text:
                    parts = text.split(":")
                    if len(parts) == 2:
                        return int(parts[0]) * 60 + int(float(parts[1]))
                    if len(parts) == 3:
                        return int(parts[0]) * 60 + int(parts[1]) + int(float(parts[2])) / 60
                import re as _re
                h = _re.search(r"(\d+(?:\.\d+)?)\s*h", text)
                m = _re.search(r"(\d+(?:\.\d+)?)\s*m", text)
                total = (float(h.group(1)) * 60 if h else 0) + (float(m.group(1)) if m else 0)
                if total:
                    return int(total)
                return int(float(text))
            except Exception:
                return 0

        def year_from(value):
            match = re.search(r"\b(18|19|20|21)\d{2}\b", str(value or ""))
            return int(match.group(0)) if match else None

        total = len(films)
        formats = {"8MM": 0, "SUPER 8": 0, "16MM": 0}
        sounds = {"YES": 0, "NO": 0, "UNKNOWN": 0}
        vinegar = {"YES": 0, "NO": 0, "UNKNOWN": 0}
        shrunken = {"YES": 0, "NO": 0, "UNKNOWN": 0}
        repair = {"YES": 0, "NO": 0}
        projectable = {"YES": 0, "NO": 0}
        decades = {}
        total_feet = 0
        total_minutes = 0
        total_splices = 0
        total_spent = 0.0
        spent_count = 0
        documented = 0
        digital_ready = 0

        for film in films:
            fmt = str(film[3] or "").strip().upper()
            if fmt in formats:
                formats[fmt] += 1

            sound = str(film[8] or "UNKNOWN").strip().upper()
            if sound not in sounds:
                sound = "UNKNOWN"
            sounds[sound] += 1

            vs = str(film[11] or "UNKNOWN").strip().upper()
            if vs not in vinegar:
                vs = "UNKNOWN"
            vinegar[vs] += 1

            shr = str(film[12] or "UNKNOWN").strip().upper()
            if shr not in shrunken:
                shr = "UNKNOWN"
            shrunken[shr] += 1

            rep = str(film[13] or "NO").strip().upper()
            repair["YES" if rep == "YES" else "NO"] += 1

            proj = str(film[14] or "YES").strip().upper()
            projectable["YES" if proj == "YES" else "NO"] += 1

            feet = safe_int(film[6])
            total_feet += feet
            total_minutes += parse_minutes(film[7])
            total_splices += safe_int(film[15])

            release_year = year_from(film[23])
            if release_year:
                decade = (release_year // 10) * 10
                decades[decade] = decades.get(decade, 0) + 1

            price_text = str(film[27] or "").replace("$", "").replace(",", "").strip()
            try:
                if price_text:
                    total_spent += float(price_text)
                    spent_count += 1
            except Exception:
                pass

            fields = [film[1], film[2], film[3], film[4], film[5], film[6],
                      film[7], film[8], film[9], film[10], film[11], film[12],
                      film[13], film[14], film[15], film[16], film[23],
                      film[24], film[25], film[26], film[27], film[28], film[29]]
            if sum(1 for x in fields if str(x or "").strip()) >= 8:
                documented += 1

            if str(film[21] or "").strip() or str(film[22] or "").strip():
                digital_ready += 1

        def pct(value):
            return (value / total * 100) if total else 0

        avg_feet = total_feet / total if total else 0
        avg_splices = total_splices / total if total else 0
        avg_minutes = total_minutes / total if total else 0
        longest_film = max((f for f in films if safe_int(f[6]) > 0), key=lambda f: safe_int(f[6]), default=None)
        longest_runtime = max((f for f in films if parse_minutes(f[7]) > 0), key=lambda f: parse_minutes(f[7]), default=None)
        release_years = [(year_from(f[23]), f) for f in films if year_from(f[23])]
        oldest = min(release_years, key=lambda x: x[0], default=(None, None))
        newest = max(release_years, key=lambda x: x[0], default=(None, None))

        def name(film):
            return str(film[1] or film[2] or "UNTITLED")

        def add_card(row, col, title, value, detail=""):
            card = tk.Frame(content, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
            card.grid(row=row, column=col, sticky="nsew", padx=8, pady=8)
            tk.Label(card, text=title, bg=PANEL, fg=TEXT_MUTED,
                     font=("Helvetica", 9, "bold")).pack(anchor="w", padx=18, pady=(15, 2))
            tk.Label(card, text=value, bg=PANEL, fg=GOLD_LIGHT,
                     font=("Helvetica", 22, "bold"), wraplength=430).pack(anchor="w", padx=18)
            if detail:
                tk.Label(card, text=detail, bg=PANEL, fg=TEXT,
                         font=("Helvetica", 9), wraplength=430,
                         justify="left").pack(anchor="w", padx=18, pady=(3, 15))
            else:
                tk.Frame(card, bg=PANEL, height=15).pack()

        content.grid_columnconfigure(0, weight=1)
        content.grid_columnconfigure(1, weight=1)

        add_card(0, 0, "TOTAL FILMS", f"{total:,}", "Films represented by the current archive filter.")
        add_card(0, 1, "TOTAL FOOTAGE", f"{total_feet:,} ft", f"Average: {avg_feet:,.0f} ft per film")
        add_card(1, 0, "TOTAL RUNTIME", f"{total_minutes // 60}h {total_minutes % 60}m", f"Average: {avg_minutes:.1f} minutes per film")
        add_card(1, 1, "TOTAL SPLICES", f"{total_splices:,}", f"Average: {avg_splices:.1f} splices per film")
        add_card(2, 0, "PURCHASE COST", f"${total_spent:,.2f}", f"Based on {spent_count} films with a recorded purchase price")
        add_card(2, 1, "DOCUMENTATION", f"{pct(documented):.0f}%", f"{documented} of {total} films have substantial catalog documentation")
        add_card(3, 0, "DIGITAL READY", f"{pct(digital_ready):.0f}%", f"{digital_ready} film(s) have a raw or restored digital copy assigned")
        add_card(3, 1, "PROJECTABLE", f"{projectable['YES']} / {total}", f"{pct(projectable['YES']):.0f}% currently marked projectable")

        # Format breakdown
        section = tk.Frame(content, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        section.grid(row=4, column=0, columnspan=2, sticky="ew", padx=8, pady=8)
        tk.Label(section, text="FORMAT BREAKDOWN", bg=PANEL, fg=GOLD_LIGHT,
                 font=("Helvetica", 13, "bold")).pack(anchor="w", padx=18, pady=(15, 8))

        for label, value in formats.items():
            line = tk.Frame(section, bg=PANEL)
            line.pack(fill="x", padx=18, pady=5)
            tk.Label(line, text=label, bg=PANEL, fg=TEXT, width=10,
                     anchor="w", font=("Helvetica", 10, "bold")).pack(side="left")
            bar = tk.Frame(line, bg=PANEL_2, height=18)
            bar.pack(side="left", fill="x", expand=True, padx=10)
            fill = tk.Frame(bar, bg=GOLD, height=18)
            fill.place(relwidth=(value / total if total else 0), relheight=1)
            tk.Label(line, text=f"{value}  ({pct(value):.0f}%)", bg=PANEL,
                     fg=TEXT_MUTED, width=16, anchor="e").pack(side="right")
        tk.Frame(section, bg=PANEL, height=10).pack()

        # Condition breakdown
        section2 = tk.Frame(content, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        section2.grid(row=5, column=0, columnspan=2, sticky="ew", padx=8, pady=8)
        tk.Label(section2, text="COLLECTION CONDITION", bg=PANEL, fg=GOLD_LIGHT,
                 font=("Helvetica", 13, "bold")).pack(anchor="w", padx=18, pady=(15, 8))
        condition_text = (
            f"Sound: YES {sounds['YES']}  •  NO {sounds['NO']}  •  UNKNOWN {sounds['UNKNOWN']}\n"
            f"Vinegar Syndrome: YES {vinegar['YES']}  •  NO {vinegar['NO']}  •  UNKNOWN {vinegar['UNKNOWN']}\n"
            f"Shrunken: YES {shrunken['YES']}  •  NO {shrunken['NO']}  •  UNKNOWN {shrunken['UNKNOWN']}\n"
            f"Needs Repair: YES {repair['YES']}  •  NO {repair['NO']}\n"
            f"Projectable: YES {projectable['YES']}  •  NO {projectable['NO']}"
        )
        tk.Label(section2, text=condition_text, bg=PANEL, fg=TEXT,
                 font=("Helvetica", 10), justify="left").pack(anchor="w", padx=18, pady=(0, 18))

        # Milestones
        section3 = tk.Frame(content, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        section3.grid(row=6, column=0, columnspan=2, sticky="ew", padx=8, pady=8)
        tk.Label(section3, text="COLLECTION MILESTONES", bg=PANEL, fg=GOLD_LIGHT,
                 font=("Helvetica", 13, "bold")).pack(anchor="w", padx=18, pady=(15, 8))

        oldest_text = f"{name(oldest[1])} ({oldest[0]})" if oldest[1] else "—"
        newest_text = f"{name(newest[1])} ({newest[0]})" if newest[1] else "—"
        longest_text = f"{name(longest_film)} ({safe_int(longest_film[6]):,} ft)" if longest_film else "—"
        runtime_text = f"{name(longest_runtime)} ({parse_minutes(longest_runtime[7]) // 60}h {parse_minutes(longest_runtime[7]) % 60}m)" if longest_runtime else "—"

        milestone_text = (
            f"OLDEST RELEASE: {oldest_text}\n"
            f"MOST RECENT RELEASE: {newest_text}\n"
            f"LONGEST FILM: {longest_text}\n"
            f"LONGEST RUNTIME: {runtime_text}"
        )
        tk.Label(section3, text=milestone_text, bg=PANEL, fg=TEXT,
                 font=("Helvetica", 10), justify="left", wraplength=950).pack(anchor="w", padx=18, pady=(0, 18))

        # Release decades
        if decades:
            section4 = tk.Frame(content, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
            section4.grid(row=7, column=0, columnspan=2, sticky="ew", padx=8, pady=8)
            tk.Label(section4, text="FILMS BY RELEASE DECADE", bg=PANEL, fg=GOLD_LIGHT,
                     font=("Helvetica", 13, "bold")).pack(anchor="w", padx=18, pady=(15, 8))
            for decade in sorted(decades):
                value = decades[decade]
                line = tk.Frame(section4, bg=PANEL)
                line.pack(fill="x", padx=18, pady=4)
                tk.Label(line, text=f"{decade}s", bg=PANEL, fg=TEXT, width=8,
                         anchor="w", font=("Helvetica", 10, "bold")).pack(side="left")
                bar = tk.Frame(line, bg=PANEL_2, height=16)
                bar.pack(side="left", fill="x", expand=True, padx=10)
                fill = tk.Frame(bar, bg=GOLD, height=16)
                fill.place(relwidth=(value / max(decades.values()) if decades else 0), relheight=1)
                tk.Label(line, text=f"{value}", bg=PANEL, fg=TEXT_MUTED,
                         width=6, anchor="e").pack(side="right")
            tk.Frame(section4, bg=PANEL, height=10).pack()

        window.bind("<Escape>", lambda event: window.go_back())

    # ========================================================
    # FILM AWARDS
    # ========================================================

    def open_film_awards(self):
        films = self.get_filtered_films()

        if not films:
            messagebox.showinfo(
                "Film Awards",
                "There are no films available in the current selection."
            )
            return

        def year_value(value):
            return extract_year(value)

        def number_value(value):
            if value is None:
                return None
            match = re.search(r"\d+(?:\.\d+)?", str(value).replace(",", ""))
            return float(match.group(0)) if match else None

        def completeness(film):
            fields = [film[1], film[2], film[3], film[4], film[5], film[6],
                      film[7], film[8], film[9], film[10], film[14], film[15],
                      film[23]]
            return sum(bool(str(v or "").strip()) for v in fields)

        awards = []

        dated = [(f, year_value(f[23])) for f in films if year_value(f[23]) is not None]
        if dated:
            oldest = min(dated, key=lambda x: x[1])
            newest = max(dated, key=lambda x: x[1])
            awards.append(("🏆", "OLDEST FILM", oldest[0], f"Original release: {oldest[1]}"))
            awards.append(("🆕", "MOST RECENT RELEASE", newest[0], f"Original release: {newest[1]}"))

        lengths = [(f, number_value(f[6])) for f in films if number_value(f[6]) is not None]
        if lengths:
            winner = max(lengths, key=lambda x: x[1])
            awards.append(("📏", "LONGEST FILM", winner[0], f"Film length: {winner[0][6]}"))

        runtimes = [(f, number_value(f[7])) for f in films if number_value(f[7]) is not None]
        if runtimes:
            winner = max(runtimes, key=lambda x: x[1])
            awards.append(("⏱️", "LONGEST RUNTIME", winner[0], f"Runtime: {winner[0][7]}"))

        prints = [(f, year_value(f[5])) for f in films if year_value(f[5]) is not None]
        if prints:
            winner = min(prints, key=lambda x: x[1])
            awards.append(("📜", "OLDEST PRINT", winner[0], f"Print date: {winner[0][5]}"))

        splices = [(f, number_value(f[15])) for f in films if number_value(f[15]) is not None]
        if splices:
            winner = max(splices, key=lambda x: x[1])
            awards.append(("✂️", "MOST SPLICED FILM", winner[0], f"Splices: {winner[0][15]}"))

        for fmt, icon, name in [
            ("8MM", "8️⃣", "8MM CHAMPION"),
            ("SUPER 8", "🎞️", "SUPER 8 CHAMPION"),
            ("16MM", "🎥", "16MM CHAMPION")
        ]:
            matches = [f for f in films if str(f[3] or "").upper() == fmt]
            if matches:
                winner = max(matches, key=lambda f: (year_value(f[23]) or 0, completeness(f)))
                awards.append((icon, name, winner, f"Best release-era entry: {f'{year_value(winner[23])}' if year_value(winner[23]) else 'Release date unknown'}"))

        sound = [f for f in films if str(f[8] or "").strip().upper() in ("YES", "TRUE", "1", "SOUND")]
        if sound:
            winner = max(sound, key=completeness)
            awards.append(("🔊", "SOUND CHAMPION", winner, "Best documented sound print"))

        repair = [f for f in films if str(f[13] or "").strip().upper() in ("YES", "TRUE", "1")]
        if repair:
            winner = max(repair, key=completeness)
            awards.append(("🔧", "NEEDS SOME LOVE", winner, "Marked as needing repair"))

        vinegar = [f for f in films if str(f[11] or "").strip().upper() in ("YES", "TRUE", "1")]
        if vinegar:
            winner = max(vinegar, key=completeness)
            awards.append(("🍷", "VINEGAR SURVIVOR", winner, "Marked with vinegar syndrome"))

        documented = max(films, key=completeness)
        awards.append(("📋", "BEST DOCUMENTED FILM", documented, f"Metadata fields completed: {completeness(documented)} / 13"))

        presented = max(films, key=lambda f: (bool(f[17]), len(str(f[18] or "").strip())))
        image_count = 1 if presented[17] else 0
        if presented[18]:
            image_count += len([x for x in str(presented[18]).split("|") if x.strip()])
        awards.append(("🖼️", "BEST PRESENTED FILM", presented, f"Cover/additional images: {image_count}"))

        digital = [f for f in films if f[21] or f[22]]
        if digital:
            winner = max(digital, key=lambda f: (bool(f[21]) + bool(f[22]), completeness(f)))
            copies = []
            if winner[21]: copies.append("RAW")
            if winner[22]: copies.append("RESTORED")
            awards.append(("💾", "DIGITAL READY", winner, "Digital copies: " + " + ".join(copies)))

        champion = max(films, key=lambda f: (
            completeness(f), bool(f[17]), bool(f[21]) + bool(f[22]),
            year_value(f[23]) or 9999
        ))
        awards.append(("👑", "VAULT CHAMPION", champion, "Highest overall vault profile"))

        window = self.new_page()
        window.title("Film Awards")
        window.geometry("1100x800")
        window.minsize(850, 650)
        window.configure(bg=BG)
        window.transient(self)

        tk.Label(window, text="🏆 FILM AWARDS", bg=BG, fg=GOLD_LIGHT,
                 font=("Helvetica", 28, "bold")).pack(pady=(25, 3))
        tk.Label(window, text="THE BEST OF YOUR FILM VAULT", bg=BG, fg=TEXT_MUTED,
                 font=("Helvetica", 10, "bold")).pack(pady=(0, 18))

        canvas = tk.Canvas(window, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(window, orient="vertical", command=canvas.yview)
        content = tk.Frame(canvas, bg=BG)
        canvas_window = canvas.create_window((0, 0), window=content, anchor="nw")

        def resize(event):
            canvas.itemconfigure(canvas_window, width=event.width)
        canvas.bind("<Configure>", resize)
        content.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True, padx=(25, 0), pady=(0, 20))
        scrollbar.pack(side="right", fill="y", padx=(0, 20), pady=(0, 20))

        columns = 2
        for i, (icon, award, film, detail) in enumerate(awards):
            card = tk.Frame(content, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
            card.grid(row=i // columns, column=i % columns, sticky="nsew", padx=8, pady=8)
            content.grid_columnconfigure(i % columns, weight=1)

            tk.Label(card, text=icon, bg=PANEL, fg=GOLD_LIGHT, font=("Segoe UI Emoji", 25)).pack(pady=(15, 2))
            tk.Label(card, text=award, bg=PANEL, fg=GOLD_LIGHT, font=("Helvetica", 12, "bold")).pack()
            tk.Label(card, text=str(film[1] or film[2] or "UNTITLED").upper(), bg=PANEL,
                     fg=TEXT, font=("Helvetica", 16, "bold"), wraplength=430, justify="center").pack(pady=(10, 4))
            tk.Label(card, text=detail, bg=PANEL, fg=TEXT_MUTED, font=("Helvetica", 9),
                     wraplength=430, justify="center").pack(pady=(0, 15))
            self.button(card, "VIEW FILM", lambda fid=film[0]: self.open_view_dialog(fid, return_target="menu")).pack(pady=(0, 15))

        window.bind("<Escape>", lambda event: window.go_back())

    # ========================================================
    # DELETE
    # ========================================================

    def delete_film(self, film_id):

        film = next(
            (f for f in self.films if f[0] == film_id),
            None
        )

        if film is None:
            return

        if not messagebox.askyesno(
            "Delete Film",
            "Delete this film from the vault?\n\n"
            + str(film[1] or "UNTITLED"),
            parent=self
        ):
            return

        connection = sqlite3.connect(DB_FILE)
        connection.execute(
            "DELETE FROM films WHERE id=?",
            (film_id,)
        )
        connection.commit()
        connection.close()

        self.load_films()
        self.image_cache.clear()
        self.refresh_archive()


    # ========================================================
    # SLOT MACHINE
    # ========================================================

    def open_slot_machine(self):

        films = self.get_filtered_films()

        if not films:
            messagebox.showinfo(
                "Film Slot Machine",
                "There are no films available."
            )
            return

        window = self.new_page()
        window.title("Film Slot Machine")
        window.geometry("850x520")
        window.configure(bg=BG)
        window.transient(self)

        tk.Label(
            window,
            text="🎰 FILM SLOT MACHINE",
            bg=BG,
            fg=GOLD_LIGHT,
            font=("Helvetica", 26, "bold")
        ).pack(pady=(28, 4))

        tk.Label(
            window,
            text="LET THE REELS DECIDE",
            bg=BG,
            fg=TEXT_MUTED,
            font=("Helvetica", 10, "bold")
        ).pack(pady=(0, 22))

        machine = tk.Frame(
            window,
            bg=PANEL,
            highlightbackground=GOLD,
            highlightthickness=2
        )
        machine.pack(
            padx=35,
            fill="x"
        )

        reels = tk.Frame(machine, bg=PANEL)
        reels.pack(
            padx=25,
            pady=28,
            fill="x"
        )

        labels = []

        for _ in range(3):

            frame = tk.Frame(
                reels,
                bg="#080808",
                highlightbackground=BORDER,
                highlightthickness=2
            )
            frame.pack(
                side="left",
                expand=True,
                fill="both",
                padx=8
            )

            label = tk.Label(
                frame,
                text="READY",
                bg="#080808",
                fg=GOLD_LIGHT,
                font=("Helvetica", 17, "bold"),
                wraplength=210,
                justify="center"
            )

            label.pack(
                expand=True,
                fill="both",
                padx=12,
                pady=30
            )

            labels.append(label)

        result = tk.Label(
            window,
            text="PRESS SPIN",
            bg=BG,
            fg=TEXT,
            font=("Helvetica", 13, "bold")
        )
        result.pack(pady=(22, 12))

        buttons = tk.Frame(window, bg=BG)
        buttons.pack()

        spin = tk.Button(
            buttons,
            text="🎰 SPIN",
            bg=GOLD,
            fg="#080808",
            relief="flat",
            bd=0,
            font=("Helvetica", 12, "bold"),
            padx=30,
            pady=12
        )
        spin.pack(side="left", padx=7)

        current = {"film": None}

        view = self.button(buttons, "VIEW FILM", lambda: self.open_view_dialog(current["film"][0], return_target="menu"))
        view.configure(state="disabled")
        view.pack(side="left", padx=7)

        def spin_now():

            spin.config(state="disabled")
            view.config(state="disabled")

            winners = [
                random.choice(films),
                random.choice(films),
                random.choice(films)
            ]

            durations = [1000, 1500, 2000]

            def animate(index, elapsed):

                if elapsed >= durations[index]:

                    labels[index].config(
                        text=str(
                            winners[index][1] or "UNTITLED"
                        ).upper()
                    )

                    if index == 2:

                        current["film"] = winners[1]

                        result.config(
                            text="★ THE REELS HAVE CHOSEN ★\n"
                            + str(
                                winners[1][1] or "UNTITLED"
                            ).upper(),
                            fg=GOLD_LIGHT
                        )

                        spin.config(state="normal")
                        view.config(state="normal")

                    return

                labels[index].config(
                    text=str(
                        random.choice(films)[1] or "UNTITLED"
                    ).upper()
                )

                window.after(
                    70,
                    lambda:
                    animate(index, elapsed + 70)
                )

            for i in range(3):
                animate(i, 0)

        def view_winner():

            if current["film"]:
                window.destroy()
                self.open_view_dialog(
                    current["film"][0]
                )

        spin.config(command=spin_now)
        view.config(command=view_winner)

        window.bind(
            "<Escape>",
            lambda event: window.go_back()
        )


    # ========================================================
    # PRINT TICKET
    # ========================================================

    def _create_ticket_pdf(self, film, path):

        if not REPORTLAB_AVAILABLE:
            raise RuntimeError("ReportLab is not installed.")

        pdf = pdf_canvas.Canvas(
            path,
            pagesize=(8.5 * inch, 4.2 * inch)
        )

        width = 8.5 * inch
        height = 4.2 * inch

        pdf.setFillColorRGB(0.06, 0.06, 0.06)
        pdf.rect(0, 0, width, height, fill=1, stroke=0)

        pdf.setStrokeColorRGB(0.78, 0.64, 0.36)
        pdf.setLineWidth(2)
        pdf.rect(
            18,
            18,
            width - 36,
            height - 36,
            fill=0,
            stroke=1
        )

        pdf.setFillColorRGB(0.88, 0.76, 0.48)
        pdf.setFont("Helvetica-Bold", 20)
        pdf.drawString(
            38,
            height - 55,
            "THE REEL ARCHIVE"
        )

        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(
            38,
            height - 78,
            "ADMIT ONE"
        )

        pdf.setFont("Helvetica-Bold", 15)
        pdf.drawString(
            38,
            height - 112,
            str(film[1] or "UNTITLED")[:55]
        )

        info = [
            ("ORIGINAL TITLE", film[2]),
            ("FORMAT", film[3]),
            ("SOUND", film[8]),
            ("LENGTH", film[6]),
            ("RUNTIME", film[7]),
            ("RELEASE DATE", film[23]),
            ("PRINT DATE", film[5]),
            ("COUNTRY", film[9]),
            ("VAULT NUMBER", film[0])
        ]

        y = height - 145

        for label, value in info:

            pdf.setFillColorRGB(0.45, 0.45, 0.45)
            pdf.setFont("Helvetica-Bold", 7)
            pdf.drawString(38, y, label)

            pdf.setFillColorRGB(0.85, 0.85, 0.85)
            pdf.setFont("Helvetica", 9)
            pdf.drawString(
                125,
                y,
                str(value or "—")[:40]
            )

            y -= 18

        pdf.setFillColorRGB(0.88, 0.76, 0.48)
        pdf.setFont("Helvetica-Bold", 10)

        pdf.drawCentredString(
            width - 80,
            height / 2 + 15,
            "FILM"
        )

        pdf.drawCentredString(
            width - 80,
            height / 2 - 2,
            "VAULT"
        )

        pdf.showPage()
        pdf.save()


    def print_film_ticket(self, film_id):

        if not REPORTLAB_AVAILABLE:
            messagebox.showerror(
                "ReportLab Required",
                "Install ReportLab with:\n\npip install reportlab"
            )
            return

        film = next(
            (f for f in self.films if f[0] == film_id),
            None
        )

        if film is None:
            return

        window = self.new_page()
        window.title("Film Ticket")
        window.geometry("720x470")
        window.configure(bg=BG)

        tk.Label(
            window,
            text="🎟 FILM TICKET",
            bg=BG,
            fg=GOLD_LIGHT,
            font=("Helvetica", 22, "bold")
        ).pack(pady=(22, 10))

        preview = tk.Frame(
            window,
            bg="#0f0f0f",
            highlightbackground=GOLD,
            highlightthickness=2
        )
        preview.pack(
            fill="x",
            padx=35,
            pady=10
        )

        tk.Label(
            preview,
            text="THE REEL ARCHIVE",
            bg="#0f0f0f",
            fg=GOLD_LIGHT,
            font=("Helvetica", 18, "bold")
        ).pack(pady=(15, 2))

        tk.Label(
            preview,
            text="ADMIT ONE",
            bg="#0f0f0f",
            fg=TEXT_MUTED,
            font=("Helvetica", 8, "bold")
        ).pack()

        tk.Label(
            preview,
            text=str(film[1] or "UNTITLED").upper(),
            bg="#0f0f0f",
            fg=TEXT,
            font=("Helvetica", 15, "bold"),
            wraplength=550
        ).pack(pady=12)

        tk.Label(
            preview,
            text=(
                "FORMAT: " + str(film[3] or "—")
                + "     SOUND: " + str(film[8] or "—")
                + "     RELEASE: " + str(film[23] or "—")
                + "\n"
                "PRINT: " + str(film[5] or "—")
                + "     LENGTH: " + str(film[6] or "—")
                + "     VAULT #: " + str(film[0])
            ),
            bg="#0f0f0f",
            fg=TEXT_MUTED,
            font=("Helvetica", 8),
            justify="center"
        ).pack(pady=(0, 17))

        buttons = tk.Frame(window, bg=BG)
        buttons.pack(pady=15)

        def save_pdf():

            filename = (
                str(film[1] or "film")
                .replace("/", "_")
                .replace("\\", "_")
                + "_ticket.pdf"
            )

            path = filedialog.asksaveasfilename(
                parent=window,
                title="Save Film Ticket",
                initialfile=filename,
                defaultextension=".pdf",
                filetypes=[("PDF files", "*.pdf")]
            )

            if not path:
                return

            try:
                self._create_ticket_pdf(film, path)

                messagebox.showinfo(
                    "Ticket Saved",
                    "Film ticket saved successfully.",
                    parent=window
                )

            except Exception as error:
                messagebox.showerror(
                    "Could Not Save Ticket",
                    str(error),
                    parent=window
                )

        def print_ticket():

            try:

                temp = tempfile.NamedTemporaryFile(
                    delete=False,
                    suffix=".pdf"
                )

                path = temp.name
                temp.close()

                self._create_ticket_pdf(film, path)

                if os.name == "nt":
                    os.startfile(path, "print")

                    messagebox.showinfo(
                        "Printing",
                        "The ticket was sent to the default printer.",
                        parent=window
                    )

                else:
                    messagebox.showinfo(
                        "Print",
                        "PDF created at:\n\n" + path,
                        parent=window
                    )

            except Exception as error:

                messagebox.showerror(
                    "Could Not Print",
                    str(error),
                    parent=window
                )

        tk.Button(
            buttons,
            text="🎟 PRINT TICKET",
            bg=GOLD,
            fg="#080808",
            relief="flat",
            bd=0,
            padx=20,
            pady=10,
            command=print_ticket
        ).pack(side="left", padx=5)

        tk.Button(
            buttons,
            text="SAVE AS PDF",
            bg=PANEL_2,
            fg=TEXT,
            relief="flat",
            bd=0,
            padx=20,
            pady=10,
            command=save_pdf
        ).pack(side="left", padx=5)

        window.bind(
            "<Escape>",
            lambda event: window.go_back()
        )


# ============================================================
# BUILT-IN PYGAME REEL RUNNER
# ============================================================

def load_titles():
    try:
        conn = sqlite3.connect(DB_FILE)
        rows = conn.execute("SELECT title FROM films WHERE TRIM(COALESCE(title,'')) <> ''").fetchall()
        conn.close()
        titles = [r[0].strip() for r in rows if r[0] and r[0].strip()]
        return titles
    except Exception:
        return []


def load_high_score():
    try:
        with open(SCORE_FILE, "r", encoding="utf-8") as f:
            return int(json.load(f).get("high_score", 0))
    except Exception:
        return 0


def save_high_score(value):
    try:
        with open(SCORE_FILE, "w", encoding="utf-8") as f:
            json.dump({"high_score": int(value)}, f, indent=2)
    except Exception:
        pass


def reel_surface(size, color=GOLD_LIGHT):
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    c = size // 2
    pygame.draw.circle(surf, color, (c, c), c - 3, 3)
    pygame.draw.circle(surf, color, (c, c), 5, 2)
    r = max(7, size // 4)
    for ang in (0, math.pi / 2, math.pi, math.pi * 1.5):
        x = c + int(math.cos(ang) * r)
        y = c + int(math.sin(ang) * r)
        pygame.draw.circle(surf, color, (x, y), max(3, size // 14), 2)
    return surf


def draw_text(screen, font, text, pos, color=TEXT, center=False):
    img = font.render(text, True, color)
    rect = img.get_rect(center=pos) if center else img.get_rect(topleft=pos)
    screen.blit(img, rect)
    return rect


def run_builtin_reel_runner():
    pygame.init()
    pygame.display.set_caption("The Reel Archive — Reel Runner")
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()

    font_big = pygame.font.SysFont("arial", 42, bold=True)
    font_title = pygame.font.SysFont("arial", 26, bold=True)
    font = pygame.font.SysFont("arial", 20, bold=True)
    font_small = pygame.font.SysFont("arial", 15, bold=True)
    font_tiny = pygame.font.SysFont("arial", 13)

    # Epilepsy / photosensitivity warning shown before gameplay.
    warning_title = font_big.render("PHOTOSENSITIVITY WARNING", True, GOLD)
    warning_lines = [
        "REEL RUNNER contains flashing lights, rapidly changing images,",
        "moving patterns, and other visual effects that may trigger",
        "seizures or other reactions in people with photosensitive epilepsy",
        "or other light sensitivities.",
        "",
        "If you have photosensitive epilepsy, or experience dizziness,",
        "vision changes, headaches, disorientation, or discomfort,",
        "STOP PLAYING IMMEDIATELY.",
        "",
        "PLAY AT YOUR OWN DISCRETION.",
        "",
        "ENTER / SPACE  Continue     ESC  Exit Game"
    ]
    warning_wait = True
    while warning_wait:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return 0
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    warning_wait = False
                elif event.key == pygame.K_ESCAPE:
                    pygame.quit()
                    return 0
        screen.fill(BLACK)
        screen.blit(warning_title, warning_title.get_rect(center=(WIDTH // 2, 115)))
        y = 190
        for line in warning_lines:
            surf = font.render(line, True, TEXT)
            screen.blit(surf, surf.get_rect(center=(WIDTH // 2, y)))
            y += 38
        pygame.display.flip()
        clock.tick(FPS)

    titles = load_titles()
    high_score = load_high_score()

    state = "menu"
    score = 0
    lives = 3
    level = 1
    distance = 0.0
    combo = 0
    player_x = 180.0
    player_y = 0.0
    player_vy = 0.0
    ground_y = HEIGHT - 125
    invulnerable = 0.0
    spawn_timer = 0.0
    objects = []
    particles = []
    current_title = random.choice(titles) if titles else "YOUR NEXT FILM"
    banner_timer = 0.0
    paused = False
    flash_timer = 0.0

    def reset():
        nonlocal score, lives, level, distance, combo, player_x, player_y, player_vy
        nonlocal invulnerable, spawn_timer, objects, particles, state, current_title, banner_timer, paused, flash_timer
        score = 0
        lives = 3
        level = 1
        distance = 0.0
        combo = 0
        player_x = 180.0
        player_y = ground_y - 28
        player_vy = 0.0
        invulnerable = 0.0
        spawn_timer = 0.8
        objects = []
        particles = []
        current_title = random.choice(titles) if titles else "YOUR NEXT FILM"
        banner_timer = 2.5
        paused = False
        flash_timer = 0.0
        state = "playing"

    def add_particles(x, y, count=10):
        for _ in range(count):
            ang = random.uniform(0, math.tau)
            speed = random.uniform(35, 150)
            particles.append({
                "x": x, "y": y,
                "vx": math.cos(ang) * speed,
                "vy": math.sin(ang) * speed,
                "life": random.uniform(.3, .8),
            })

    def spawn(kind=None):
        if kind is None:
            # Collectibles are common; enemies become more varied as levels rise.
            choices = ["reel", "can", "splice", "scissors", "broken_reel"]
            weights = [48, 13, 15, 13, 11]
            if level >= 4:
                choices += ["projector_enemy", "flying_reel"]
                weights += [7, 7]
            kind = random.choices(choices, weights=weights)[0]

        x = WIDTH + random.randint(30, 170)
        if kind == "reel":
            y = ground_y - random.choice([38, 68, 98, 128])
            radius = 18
        elif kind == "can":
            y = ground_y - 36
            radius = 27
        elif kind == "splice":
            y = ground_y - 29
            radius = 25
        elif kind == "scissors":
            y = ground_y - 30
            radius = 27
        elif kind == "broken_reel":
            y = ground_y - 34
            radius = 26
        elif kind == "projector_enemy":
            y = ground_y - 68
            radius = 38
        else:  # flying_reel
            y = ground_y - random.choice([115, 155, 195])
            radius = 22

        objects.append({
            "kind": kind,
            "x": float(x),
            "y": float(y),
            "r": radius,
            "spin": random.random() * math.tau,
            "phase": random.random() * math.tau,
        })

    def player_rect():
        return pygame.Rect(int(player_x - 21), int(player_y - 21), 42, 42)

    def object_rect(obj):
        r = obj["r"]
        return pygame.Rect(int(obj["x"] - r), int(obj["y"] - r), int(r * 2), int(r * 2))

    def jump():
        nonlocal player_vy
        if state == "playing" and not paused and player_y >= ground_y - 30:
            player_vy = -700

    running = True
    while running:
        dt = min(clock.tick(FPS) / 1000.0, 0.033)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if state == "playing":
                        state = "menu"
                        objects.clear()
                    else:
                        running = False
                elif event.key in (pygame.K_SPACE, pygame.K_UP, pygame.K_w):
                    if state in ("menu", "gameover"):
                        reset()
                    else:
                        jump()
                elif event.key == pygame.K_RETURN:
                    if state in ("menu", "gameover"):
                        reset()
                elif event.key == pygame.K_p and state == "playing":
                    paused = not paused

        keys = pygame.key.get_pressed()

        if state == "playing" and not paused:
            speed = 315 + (level - 1) * 27
            level = 1 + score // 300
            distance += speed * dt
            score += int(11 * dt * level)
            invulnerable = max(0.0, invulnerable - dt)
            banner_timer = max(0.0, banner_timer - dt)
            flash_timer = max(0.0, flash_timer - dt)

            if keys[pygame.K_LEFT] or keys[pygame.K_a]:
                player_x -= 360 * dt
            if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
                player_x += 360 * dt
            player_x = max(75, min(WIDTH - 235, player_x))

            player_vy += 1800 * dt
            player_y += player_vy * dt
            if player_y >= ground_y - 28:
                player_y = ground_y - 28
                player_vy = 0

            spawn_timer -= dt
            if spawn_timer <= 0:
                spawn()
                base = max(.36, 1.02 - level * .042)
                spawn_timer = random.uniform(base * .72, base * 1.18)

            pbox = player_rect()
            kept = []
            for obj in objects:
                obj["x"] -= speed * dt
                obj["spin"] += dt * (5.5 + level * .15)
                if obj["kind"] == "flying_reel":
                    obj["y"] += math.sin(distance * .012 + obj["phase"]) * 18 * dt
                if obj["kind"] == "projector_enemy":
                    obj["y"] += math.sin(distance * .01 + obj["phase"]) * 12 * dt

                if obj["x"] < -120:
                    continue

                if pbox.colliderect(object_rect(obj)):
                    kind = obj["kind"]
                    if kind == "reel":
                        score += 50 + combo * 3
                        combo += 1
                        add_particles(obj["x"], obj["y"], 8)
                    elif kind == "can":
                        score += 140 + combo * 5
                        combo += 2
                        add_particles(obj["x"], obj["y"], 15)
                    elif kind in ("splice", "scissors", "broken_reel", "projector_enemy", "flying_reel"):
                        if invulnerable <= 0:
                            lives -= 1
                            combo = 0
                            invulnerable = 1.35
                            flash_timer = .25
                            score = max(0, score - 100)
                            add_particles(player_x, player_y, 22)
                            if lives <= 0:
                                state = "gameover"
                                if score > high_score:
                                    high_score = score
                                    save_high_score(high_score)
                                break
                    continue
                kept.append(obj)
            objects = kept

            for part in particles[:]:
                part["life"] -= dt
                part["x"] += part["vx"] * dt
                part["y"] += part["vy"] * dt
                part["vy"] += 390 * dt
                if part["life"] <= 0:
                    particles.remove(part)

        # ---------- DRAW ----------
        screen.fill(BLACK)

        # Scrolling cinema wall.
        for y in range(105, ground_y - 18, 54):
            pygame.draw.line(screen, (15, 15, 15), (0, y), (WIDTH, y), 1)
        wall_scroll = (distance * .18) % 150
        for x in range(-150, WIDTH + 180, 150):
            xx = int(x - wall_scroll)
            pygame.draw.rect(screen, (20, 20, 20), (xx, 110, 112, 62), 2)
            pygame.draw.rect(screen, (11, 11, 11), (xx + 7, 117, 98, 48))

        # Giant moving film frames behind the player.
        frame_scroll = (distance * .32) % 205
        for x in range(-205, WIDTH + 210, 205):
            xx = int(x - frame_scroll)
            pygame.draw.rect(screen, (24, 24, 24), (xx, 205, 170, 116), 3)
            pygame.draw.rect(screen, (12, 12, 12), (xx + 10, 215, 150, 96), 1)
            for hx in (xx + 12, xx + 151):
                for hy in (211, 315):
                    pygame.draw.rect(screen, (34, 34, 34), (hx, hy, 22, 8))

        # Header.
        pygame.draw.rect(screen, PANEL, (0, 0, WIDTH, 86))
        pygame.draw.line(screen, GOLD, (0, 85), (WIDTH, 85), 2)
        draw_text(screen, font_title, "🕹 REEL RUNNER", (28, 17), GOLD_LIGHT)
        draw_text(screen, font_small, "FILM VAULT ARCADE", (30, 50), TEXT_DIM)
        draw_text(screen, font, f"SCORE  {score:06d}", (360, 23), TEXT)
        draw_text(screen, font, f"LEVEL  {level}", (580, 23), GOLD_LIGHT)
        draw_text(screen, font, f"LIVES  {'♥ ' * lives}", (710, 23), TEXT)
        draw_text(screen, font_small, f"HIGH SCORE  {high_score:06d}", (875, 53), GOLD_LIGHT)

        # Ground is a giant scrolling film strip.
        pygame.draw.rect(screen, (10, 10, 10), (0, ground_y, WIDTH, HEIGHT - ground_y))
        ground_scroll = (distance * .72) % 104
        for x in range(-104, WIDTH + 120, 104):
            xx = int(x - ground_scroll)
            pygame.draw.rect(screen, (31, 31, 31), (xx, ground_y + 12, 72, 62), 2)
            pygame.draw.rect(screen, (22, 22, 22), (xx + 8, ground_y + 20, 56, 46), 1)
            pygame.draw.rect(screen, (42, 42, 42), (xx + 13, ground_y + 8, 18, 9))
            pygame.draw.rect(screen, (42, 42, 42), (xx + 43, ground_y + 8, 18, 9))
            pygame.draw.rect(screen, (42, 42, 42), (xx + 13, ground_y + 69, 18, 9))
            pygame.draw.rect(screen, (42, 42, 42), (xx + 43, ground_y + 69, 18, 9))
        pygame.draw.line(screen, GOLD, (0, ground_y), (WIDTH, ground_y), 2)

        # Projector at the end of the visible film world.
        px = WIDTH - 95
        pygame.draw.rect(screen, (15, 15, 15), (px - 45, ground_y - 115, 82, 88), 3)
        pygame.draw.circle(screen, GOLD, (px - 5, ground_y - 90), 27, 3)
        pygame.draw.circle(screen, GOLD, (px - 5, ground_y - 90), 9, 2)
        pygame.draw.circle(screen, GOLD, (px + 30, ground_y - 57), 16, 2)
        draw_text(screen, font_tiny, "PROJECTOR", (px - 45, ground_y - 19), TEXT_DIM)

        # Objects / enemies.
        for obj in objects:
            x, y, r, kind = int(obj["x"]), int(obj["y"]), obj["r"], obj["kind"]
            if kind == "reel":
                screen.blit(reel_surface(2 * r + 4), (x - r - 2, y - r - 2))
            elif kind == "can":
                pygame.draw.rect(screen, (45, 45, 45), (x - 27, y - 22, 54, 44), 3)
                pygame.draw.circle(screen, TEXT_MUTED, (x - 15, y), 11, 2)
                pygame.draw.circle(screen, TEXT_MUTED, (x + 15, y), 11, 2)
                draw_text(screen, font_tiny, "FILM", (x, y), TEXT, True)
            elif kind == "splice":
                pts = [(x - 26, y - 15), (x - 8, y - 15), (x, y - 7), (x + 8, y - 15),
                       (x + 26, y - 15), (x + 26, y + 15), (x + 8, y + 15),
                       (x, y + 7), (x - 8, y + 15), (x - 26, y + 15)]
                pygame.draw.polygon(screen, (42, 42, 42), pts)
                pygame.draw.polygon(screen, TEXT_MUTED, pts, 2)
                draw_text(screen, font, "✂", (x, y - 1), TEXT, True)
            elif kind == "scissors":
                pygame.draw.circle(screen, RED, (x - 9, y - 7), 8, 2)
                pygame.draw.circle(screen, RED, (x + 9, y + 7), 8, 2)
                pygame.draw.line(screen, RED, (x - 3, y - 1), (x + 25, y - 23), 4)
                pygame.draw.line(screen, RED, (x + 3, y + 1), (x - 25, y + 23), 4)
                draw_text(screen, font_tiny, "CUT!", (x, y + 31), RED, True)
            elif kind == "broken_reel":
                pygame.draw.circle(screen, RED, (x, y), 24, 3)
                pygame.draw.line(screen, RED, (x - 18, y - 18), (x + 18, y + 18), 4)
                pygame.draw.line(screen, RED, (x + 18, y - 18), (x - 18, y + 18), 4)
                draw_text(screen, font_tiny, "JAM", (x, y + 31), RED, True)
            elif kind == "projector_enemy":
                pygame.draw.rect(screen, (35, 35, 35), (x - 38, y - 35, 76, 70), 3)
                pygame.draw.circle(screen, RED, (x, y), 22, 3)
                pygame.draw.circle(screen, RED, (x, y), 7, 2)
                pygame.draw.rect(screen, RED, (x + 34, y - 5, 15, 10))
                draw_text(screen, font_tiny, "HOT LAMP", (x, y + 47), RED, True)
            elif kind == "flying_reel":
                screen.blit(reel_surface(2 * r + 4, RED), (x - r - 2, y - r - 2))
                draw_text(screen, font_tiny, "ENEMY", (x, y + 28), RED, True)

        # Player.
        if invulnerable <= 0 or int(invulnerable * 14) % 2 == 0:
            player = reel_surface(58, GOLD_LIGHT)
            screen.blit(player, (int(player_x - 29), int(player_y - 29)))

        for part in particles:
            pygame.draw.circle(screen, GOLD_LIGHT, (int(part["x"]), int(part["y"])), 3)

        if banner_timer > 0 and state == "playing":
            panel = pygame.Rect(24, 100, 390, 62)
            pygame.draw.rect(screen, PANEL, panel)
            pygame.draw.rect(screen, GOLD, panel, 1)
            draw_text(screen, font_tiny, "COLLECTION REEL", (40, 112), GOLD_LIGHT)
            short = current_title if len(current_title) <= 34 else current_title[:31] + "..."
            draw_text(screen, font_small, short, (40, 134), TEXT)

        if combo >= 2 and state == "playing":
            draw_text(screen, font, f"REEL STREAK x{combo}", (WIDTH // 2, 112), GOLD_LIGHT, True)

        if flash_timer > 0:
            flash = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            flash.fill((130, 0, 0, 45))
            screen.blit(flash, (0, 0))

        # Menu / pause / game over.
        if state == "menu":
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 205))
            screen.blit(overlay, (0, 0))
            draw_text(screen, font_big, "REEL RUNNER", (WIDTH // 2, 165), GOLD_LIGHT, True)
            draw_text(screen, font, "RUN THE REEL. SURVIVE THE FILM STRIP.", (WIDTH // 2, 215), TEXT, True)
            draw_text(screen, font_small, "SPACE / ENTER  START", (WIDTH // 2, 278), GOLD_LIGHT, True)
            draw_text(screen, font_small, "A / D or ← / →  MOVE", (WIDTH // 2, 306), TEXT_MUTED, True)
            draw_text(screen, font_small, "SPACE / W / ↑  JUMP", (WIDTH // 2, 334), TEXT_MUTED, True)
            draw_text(screen, font_small, "P  PAUSE     ESC  EXIT", (WIDTH // 2, 362), TEXT_MUTED, True)
            draw_text(screen, font_tiny, "Collect reels + film cans. Avoid scissors, jams and projectors.", (WIDTH // 2, 405), TEXT_DIM, True)
            draw_text(screen, font_small, f"HIGH SCORE: {high_score:06d}", (WIDTH // 2, 455), GOLD_LIGHT, True)

        elif paused:
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 185))
            screen.blit(overlay, (0, 0))
            draw_text(screen, font_big, "PAUSED", (WIDTH // 2, 280), GOLD_LIGHT, True)
            draw_text(screen, font, "PRESS P TO CONTINUE", (WIDTH // 2, 330), TEXT, True)

        elif state == "gameover":
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 210))
            screen.blit(overlay, (0, 0))
            draw_text(screen, font_big, "FILM LOST!", (WIDTH // 2, 195), GOLD_LIGHT, True)
            draw_text(screen, font, f"FINAL SCORE  {score:06d}", (WIDTH // 2, 245), TEXT, True)
            draw_text(screen, font, f"LEVEL REACHED  {level}", (WIDTH // 2, 278), TEXT, True)
            if score >= high_score and score > 0:
                draw_text(screen, font, "★ NEW HIGH SCORE ★", (WIDTH // 2, 318), GOLD_LIGHT, True)
            else:
                draw_text(screen, font, f"HIGH SCORE  {high_score:06d}", (WIDTH // 2, 318), GOLD_LIGHT, True)
            draw_text(screen, font_small, "ENTER / SPACE  PLAY AGAIN", (WIDTH // 2, 365), TEXT, True)
            draw_text(screen, font_small, "ESC  RETURN TO FILM VAULT", (WIDTH // 2, 392), TEXT_MUTED, True)

        pygame.display.flip()

    pygame.quit()
    return 0

# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    if "--reel-runner" in sys.argv:
        raise SystemExit(run_builtin_reel_runner())
    initialize_database()

    app = FilmVault()
    app.mainloop()
