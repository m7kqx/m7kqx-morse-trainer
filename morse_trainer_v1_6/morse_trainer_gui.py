#!/usr/bin/env python3
"""
Morse Trainer GUI - v1.6
Target: Raspberry Pi OS (800x480 / 1024x600 HDMI LCDs), Linux, macOS.
Hardware: Open CW Keyer mk2 (K3NG firmware) USB Serial.
"""

import os
import sys
import json
import time
import random
import queue
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

# Dynamic asset & profile paths
BASE_PATH = getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)
USER_DATA_DIR = Path.home() / ".morse_trainer"
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

import serial
import serial.tools.list_ports

# Standard ITU Morse Dictionary
ITU_MORSE = {
    "A": ".-", "B": "-...", "C": "-.-.", "D": "-..", "E": ".", "F": "..-.",
    "G": "--.", "H": "....", "I": "..", "J": ".---", "K": "-.-", "L": ".-..",
    "M": "--", "N": "-.", "O": "---", "P": ".--.", "Q": "--.-", "R": ".-.",
    "S": "...", "T": "-", "U": "..-", "V": "...-", "W": ".--", "X": "-..-",
    "Y": "-.--", "Z": "--..", "1": ".----", "2": "..---", "3": "...--",
    "4": "....-", "5": ".....", "6": "-....", "7": "--...", "8": "---..",
    "9": "----.", "0": "-----", "/": "-..-.", "?": "..--..", "=": "-...-",
    ",": "--..--", ".": ".-.-.-", "-": "-....-", "+": ".-.-.", "@": ".--.-."
}

# Fallback vocabulary banks
FALLBACK_2_LTR = ["CQ", "DE", "UR", "HR", "HW", "FB", "ES", "TU", "SK"]
FALLBACK_3_LTR = ["RST", "5NN", "QTH", "RIG", "ANT", "PWR", "QSO", "QSL", "QRZ"]
FALLBACK_4_LTR = ["NAME", "HERE", "TEMP", "WATT", "BEAM", "WIRE"]
FALLBACK_NAMES = ["CHRIS", "DAISY", "JACOB", "JOHN", "PAUL", "MARK", "DAVE"]
FALLBACK_QSO   = ["CQ CQ CQ DE M7KQX", "UR RST 5NN 5NN", "HW CPY? K"]

try:
    import word_banks
    if hasattr(word_banks, "ITU_MORSE"):
        ITU_MORSE.update(word_banks.ITU_MORSE)
    BANK_2 = getattr(word_banks, "WORDS_2", FALLBACK_2_LTR)
    BANK_3 = getattr(word_banks, "WORDS_3", FALLBACK_3_LTR)
    BANK_4 = getattr(word_banks, "WORDS_4", FALLBACK_4_LTR)
    BANK_NAMES = getattr(word_banks, "NAMES", FALLBACK_NAMES)
    BANK_QSO = getattr(word_banks, "QSO", FALLBACK_QSO)
except ImportError:
    BANK_2, BANK_3, BANK_4, BANK_NAMES, BANK_QSO = FALLBACK_2_LTR, FALLBACK_3_LTR, FALLBACK_4_LTR, FALLBACK_NAMES, FALLBACK_QSO

class SerialWorker(threading.Thread):
    """Non-blocking background thread for USB-Serial keyer communications."""
    def __init__(self, data_queue: queue.Queue, status_queue: queue.Queue):
        super().__init__(daemon=True)
        self.data_queue = data_queue
        self.status_queue = status_queue
        self.serial_conn = None
        self.running = True
        self._lock = threading.Lock()

    def connect(self, port_name: str, baudrate: int, stopbits: int):
        self.disconnect()
        with self._lock:
            try:
                self.serial_conn = serial.Serial(
                    port=port_name, baudrate=baudrate, bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE, stopbits=stopbits, timeout=0.05
                )
                mode_str = "CLI" if baudrate == 115200 else "WK2"
                self.status_queue.put(("CONNECTED", f"Connected: {port_name} ({mode_str} @ {baudrate})"))
            except Exception as err:
                self.serial_conn = None
                self.status_queue.put(("ERROR", f"Serial open failed: {err}"))

    def disconnect(self):
        with self._lock:
            if self.serial_conn and self.serial_conn.is_open:
                try:
                    self.serial_conn.close()
                except Exception:
                    pass
            self.serial_conn = None
            self.status_queue.put(("DISCONNECTED", "Hardware Disconnected"))

    def run(self):
        while self.running:
            with self._lock:
                conn = self.serial_conn
                is_active = conn is not None and conn.is_open
            if is_active:
                try:
                    in_waiting = conn.in_waiting
                    if in_waiting > 0:
                        raw_data = conn.read(in_waiting)
                        decoded = raw_data.decode("ascii", errors="ignore")
                        if decoded:
                            self.data_queue.put(decoded)
                    else:
                        time.sleep(0.01)
                except Exception as err:
                    self.status_queue.put(("ERROR", f"Rx Disconnect: {err}"))
                    self.disconnect()
            else:
                time.sleep(0.08)

    def stop(self):
        self.running = False
        self.disconnect()


class MorseTrainerApp(tk.Tk):
    """Main Application Controller managing workflow frames."""
    
    PALETTE = {
        "bg_main": "#121212", "bg_surface": "#1E1E1E", "bg_control": "#282828",
        "accent_cyan": "#00E5FF", "accent_amber": "#FFB300", "accent_green": "#00E676",
        "accent_red": "#FF5252", "text_primary": "#FFFFFF", "text_secondary": "#A0A0A0",
        "border": "#333333"
    }

    KOCH_SEQUENCE = "KMURESNAPTLOI234567890YZXWVFGBCDJ"

    def __init__(self):
        super().__init__()
        self.title("DIY Morse Trainer v1.6")
        self.geometry("800x480")
        self.minsize(800, 480)
        self.configure(bg=self.PALETTE["bg_main"])

        self._init_ttk_styles()

        # Shared State & Queues
        self.active_profile = None
        self.profile_data = {}
        self.data_queue = queue.Queue()
        self.status_queue = queue.Queue()
        self.worker = SerialWorker(self.data_queue, self.status_queue)
        self.worker.start()

        # Frame Container
        self.container = tk.Frame(self, bg=self.PALETTE["bg_main"])
        self.container.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        self.frames = {}
        for F in (ProfileManagerFrame, MainMenuFrame, TrainingFrame):
            page_name = F.__name__
            frame = F(parent=self.container, controller=self)
            self.frames[page_name] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        self.show_frame("ProfileManagerFrame")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _init_ttk_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "TCombobox", fieldbackground=self.PALETTE["bg_control"],
            background=self.PALETTE["border"], foreground=self.PALETTE["text_primary"],
            darkcolor=self.PALETTE["border"], lightcolor=self.PALETTE["border"]
        )

    def show_frame(self, page_name, mode_id=None):
        frame = self.frames[page_name]
        if page_name == "ProfileManagerFrame":
            frame.refresh_profile_list()
        elif page_name == "MainMenuFrame":
            frame.on_show()
        elif page_name == "TrainingFrame":
            frame.on_show(mode_id)
        frame.tkraise()

    def load_profile_data(self, profile_name):
        self.active_profile = profile_name
        filepath = USER_DATA_DIR / f"{profile_name}.json"
        if filepath.exists():
            with open(filepath, 'r') as f:
                self.profile_data = json.load(f)
        else:
            self.profile_data = {
                "name": profile_name, "koch_level": 2, "wpm_char": 20, "wpm_eff": 12,
                "session_len": 10, "score_correct": 0, "score_total": 0
            }
            self.save_profile_data()

    def save_profile_data(self):
        if not self.active_profile:
            return
        filepath = USER_DATA_DIR / f"{self.active_profile}.json"
        with open(filepath, 'w') as f:
            json.dump(self.profile_data, f, indent=4)

    def _on_close(self):
        self.worker.stop()
        self.destroy()


class SharedHeader(tk.Frame):
    """Reusable header component matching the CLI output."""
    def __init__(self, parent, controller, show_profile=False):
        super().__init__(parent, bg=controller.PALETTE["bg_surface"])
        self.controller = controller
        
        header_text = "DIY MORSE TRAINER - v1.6\nCreated by Christopher Webster (M7KQX)\nhttps://www.m7kqx.co.uk"
        tk.Label(self, text=header_text, font=("DejaVu Sans Mono", 10), bg=controller.PALETTE["bg_surface"], fg=controller.PALETTE["text_secondary"], justify=tk.CENTER).pack(pady=(10, 0))
        
        self.profile_lbl = tk.Label(self, text="", font=("DejaVu Sans Mono", 10, "bold"), bg=controller.PALETTE["bg_surface"], fg=controller.PALETTE["accent_cyan"])
        if show_profile:
            self.profile_lbl.pack(pady=(5, 10))
        else:
            tk.Label(self, text="PROFILE SELECT", font=("DejaVu Sans Mono", 10, "bold"), bg=controller.PALETTE["bg_surface"], fg=controller.PALETTE["accent_amber"]).pack(pady=(5, 10))

        tk.Frame(self, height=1, bg=controller.PALETTE["border"]).pack(fill=tk.X, padx=20)

    def update_profile(self):
        pd = self.controller.profile_data
        if pd:
            self.profile_lbl.config(text=f"Active Profile: {pd.get('name', 'UNKNOWN')}")


class ProfileManagerFrame(tk.Frame):
    """Workflow Stage 1: Select, Create, or Delete User Profiles."""
    def __init__(self, parent, controller):
        super().__init__(parent, bg=controller.PALETTE["bg_main"])
        self.controller = controller

        SharedHeader(self, controller, show_profile=False).pack(fill=tk.X)

        list_frame = tk.Frame(self, bg=controller.PALETTE["bg_main"])
        list_frame.pack(fill=tk.BOTH, expand=True, padx=40, pady=20)

        self.listbox = tk.Listbox(
            list_frame, font=("DejaVu Sans Mono", 16), bg=controller.PALETTE["bg_control"],
            fg=controller.PALETTE["text_primary"], selectbackground=controller.PALETTE["accent_amber"],
            selectforeground=controller.PALETTE["bg_main"], bd=0, highlightthickness=1
        )
        self.listbox.pack(fill=tk.BOTH, expand=True)
        self.listbox.bind('<Double-1>', lambda e: self.load_selected())

        btn_frame = tk.Frame(self, bg=controller.PALETTE["bg_main"])
        btn_frame.pack(fill=tk.X, padx=40, pady=(0, 20))

        tk.Button(btn_frame, text="[N] CREATE NEW", font=("DejaVu Sans Mono", 10, "bold"), bg=controller.PALETTE["bg_control"], fg=controller.PALETTE["accent_cyan"], command=self.create_profile, relief=tk.FLAT, padx=10, pady=10).pack(side=tk.LEFT)
        tk.Button(btn_frame, text="[D] DELETE", font=("DejaVu Sans Mono", 10, "bold"), bg=controller.PALETTE["bg_control"], fg=controller.PALETTE["accent_red"], command=self.delete_profile, relief=tk.FLAT, padx=10, pady=10).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="[Q] QUIT", font=("DejaVu Sans Mono", 10, "bold"), bg=controller.PALETTE["bg_control"], fg=controller.PALETTE["text_secondary"], command=controller._on_close, relief=tk.FLAT, padx=10, pady=10).pack(side=tk.LEFT)
        tk.Button(btn_frame, text="SELECT ❯", font=("DejaVu Sans Mono", 12, "bold"), bg=controller.PALETTE["accent_green"], fg=controller.PALETTE["bg_main"], activebackground=controller.PALETTE["accent_cyan"], command=self.load_selected, relief=tk.FLAT, padx=20, pady=10).pack(side=tk.RIGHT)

    def refresh_profile_list(self):
        self.listbox.delete(0, tk.END)
        for f in USER_DATA_DIR.glob("*.json"):
            self.listbox.insert(tk.END, f.stem)

    def create_profile(self):
        new_name = simpledialog.askstring("New Profile", "Enter Callsign or Name:", parent=self)
        if new_name:
            new_name = "".join(c for c in new_name if c.isalnum() or c in "-_").upper()
            if new_name:
                self.controller.load_profile_data(new_name)
                self.controller.show_frame("MainMenuFrame")

    def delete_profile(self):
        selection = self.listbox.curselection()
        if not selection:
            return
        profile_name = self.listbox.get(selection[0])
        if messagebox.askyesno("Confirm", f"Delete profile '{profile_name}'?", parent=self):
            filepath = USER_DATA_DIR / f"{profile_name}.json"
            if filepath.exists():
                os.remove(filepath)
            self.refresh_profile_list()

    def load_selected(self):
        selection = self.listbox.curselection()
        if not selection:
            messagebox.showinfo("Select Profile", "Please select a profile.", parent=self)
            return
        profile_name = self.listbox.get(selection[0])
        self.controller.load_profile_data(profile_name)
        self.controller.show_frame("MainMenuFrame")


class MainMenuFrame(tk.Frame):
    """Workflow Stage 2: Main Menu replacing CLI."""
    def __init__(self, parent, controller):
        super().__init__(parent, bg=controller.PALETTE["bg_main"])
        self.controller = controller
        
        self.header = SharedHeader(self, controller, show_profile=True)
        self.header.pack(fill=tk.X)

        # 2 Column Grid for Modes
        grid_frame = tk.Frame(self, bg=controller.PALETTE["bg_main"])
        grid_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        modes = [
            ("[1] Koch Practice Set", 1), ("[2] 2-Letter Words", 2),
            ("[3] 3-Letter Words", 3), ("[4] 4-Letter Words", 4),
            ("[5] Common Operator Names", 5), ("[6] Core QSO Vocabulary", 6),
            ("[7] Practice Weak Skills", 7), ("[8] Head Copy Trainer", 8)
        ]

        for i, (text, mode_id) in enumerate(modes):
            r, c = divmod(i, 2)
            btn = tk.Button(
                grid_frame, text=text, font=("DejaVu Sans Mono", 11, "bold"), anchor="w",
                bg=controller.PALETTE["bg_surface"], fg=controller.PALETTE["text_primary"],
                activebackground=controller.PALETTE["accent_cyan"], relief=tk.FLAT, padx=15, pady=12,
                command=lambda m=mode_id: self.controller.show_frame("TrainingFrame", m)
            )
            btn.grid(row=r, column=c, sticky="nsew", padx=5, pady=5)
            grid_frame.grid_columnconfigure(c, weight=1)
            grid_frame.grid_rowconfigure(r, weight=1)

        tk.Frame(self, height=1, bg=controller.PALETTE["border"]).pack(fill=tk.X, padx=20)

        # Settings Ribbon
        settings_frame = tk.Frame(self, bg=controller.PALETTE["bg_main"])
        settings_frame.pack(fill=tk.X, padx=20, pady=10)

        self.speed_btn = tk.Button(settings_frame, text="[S] Speed: --/-- WPM", font=("DejaVu Sans Mono", 9), bg=controller.PALETTE["bg_control"], fg=controller.PALETTE["accent_amber"], relief=tk.FLAT, command=self.set_speed)
        self.speed_btn.pack(side=tk.LEFT, padx=5)

        tk.Button(settings_frame, text="[P] Switch Profiles", font=("DejaVu Sans Mono", 9), bg=controller.PALETTE["bg_control"], fg=controller.PALETTE["text_secondary"], relief=tk.FLAT, command=lambda: controller.show_frame("ProfileManagerFrame")).pack(side=tk.LEFT, padx=5)
        tk.Button(settings_frame, text="[R] Reset Progress", font=("DejaVu Sans Mono", 9), bg=controller.PALETTE["bg_control"], fg=controller.PALETTE["accent_red"], relief=tk.FLAT, command=self.reset_progress).pack(side=tk.LEFT, padx=5)
        tk.Button(settings_frame, text="[Q] Save & Exit", font=("DejaVu Sans Mono", 9, "bold"), bg=controller.PALETTE["border"], fg=controller.PALETTE["text_primary"], relief=tk.FLAT, command=controller._on_close).pack(side=tk.RIGHT, padx=5)

    def on_show(self):
        self.header.update_profile()
        pd = self.controller.profile_data
        self.speed_btn.config(text=f"[S] Speed: {pd.get('wpm_char', 20)}/{pd.get('wpm_eff', 12)} WPM | Len: {pd.get('session_len', 10)}")

    def set_speed(self):
        # Quick modal for WPM adjustments on Pi touch screen
        pd = self.controller.profile_data
        new_char = simpledialog.askinteger("Speed", "Character WPM (5-60):", initialvalue=pd.get("wpm_char", 20), parent=self)
        if new_char:
            pd["wpm_char"] = max(5, min(60, new_char))
        new_eff = simpledialog.askinteger("Speed", "Effective/Farnsworth WPM (5-60):", initialvalue=pd.get("wpm_eff", 12), parent=self)
        if new_eff:
            pd["wpm_eff"] = max(5, min(60, new_eff))
        self.controller.save_profile_data()
        self.on_show()

    def reset_progress(self):
        if messagebox.askyesno("Reset", "Reset all statistics and Koch level back to 2?", parent=self):
            pd = self.controller.profile_data
            pd["koch_level"] = 2
            pd["score_correct"] = 0
            pd["score_total"] = 0
            self.controller.save_profile_data()
            messagebox.showinfo("Reset", "Profile progress reset.", parent=self)


class TrainingFrame(tk.Frame):
    """Workflow Stage 3: Main Training UI."""
    def __init__(self, parent, controller):
        super().__init__(parent, bg=controller.PALETTE["bg_main"])
        self.controller = controller
        self.mode_id = 1
        
        # State Variables
        self.current_target = tk.StringVar(value="")
        self.target_dotrep = tk.StringVar(value="")
        self.rx_stream_text = tk.StringVar(value="")
        self.current_echo_buffer = tk.StringVar(value="")
        self.status_message = tk.StringVar(value="Hardware Disconnected")
        
        self.score_correct = 0
        self.score_total = 0

        self._build_interface()
        self._refresh_serial_ports()
        self.after(20, self._poll_queues)

    def on_show(self, mode_id):
        self.mode_id = mode_id
        pd = self.controller.profile_data
        
        self.score_correct = pd.get("score_correct", 0)
        self.score_total = pd.get("score_total", 0)
        
        mode_titles = {
            1: "Koch Single Character", 2: "2-Letter Words", 3: "3-Letter Words", 
            4: "4-Letter Words", 5: "Operator Names", 6: "QSO Vocabulary", 
            7: "Weak Skills", 8: "Head Copy (Echo)"
        }
        self.lbl_mode_hdr.config(text=f"MODE {mode_id}: {mode_titles.get(mode_id, 'Training')}")
        
        self._update_score_ui()
        self._load_next_target()

    def _build_interface(self):
        pal = self.controller.PALETTE

        # 1. Top Bar: Hardware & Navigation
        top_bar = tk.Frame(self, bg=pal["bg_surface"], height=44)
        top_bar.pack(side=tk.TOP, fill=tk.X, padx=6, pady=(6, 2))

        tk.Button(top_bar, text="❮ MENU", font=("DejaVu Sans", 8, "bold"), bg=pal["bg_control"], fg=pal["accent_amber"], bd=0, relief=tk.FLAT, command=lambda: self.controller.show_frame("MainMenuFrame")).pack(side=tk.LEFT, padx=6, pady=6)
        self.combo_port = ttk.Combobox(top_bar, width=12, state="readonly")
        self.combo_port.pack(side=tk.LEFT, padx=3, pady=6)
        tk.Button(top_bar, text="⟳", font=("DejaVu Sans", 10, "bold"), bg=pal["bg_control"], fg=pal["text_primary"], bd=0, command=self._refresh_serial_ports).pack(side=tk.LEFT, padx=2, pady=6)

        self.combo_protocol = ttk.Combobox(top_bar, width=14, state="readonly", values=["115200 (CLI)", "1200 (WK2)", "9600 (WK2)"])
        self.combo_protocol.current(0)
        self.combo_protocol.pack(side=tk.LEFT, padx=(10,3), pady=6)

        self.btn_conn = tk.Button(top_bar, text="CONNECT", font=("DejaVu Sans", 9, "bold"), bg=pal["accent_cyan"], fg=pal["bg_main"], bd=0, padx=12, command=self._toggle_connection)
        self.btn_conn.pack(side=tk.LEFT, padx=8, pady=6)
        
        self.lbl_mode_hdr = tk.Label(top_bar, text="MODE: ---", font=("DejaVu Sans", 10, "bold"), bg=pal["bg_surface"], fg=pal["text_primary"])
        self.lbl_mode_hdr.pack(side=tk.RIGHT, padx=15)

        # 2. Main Stage: Flashcard & Receiver
        stage = tk.Frame(self, bg=pal["bg_main"])
        stage.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=6, pady=2)

        # Target Card
        self.target_card = tk.Frame(stage, bg=pal["bg_surface"], bd=1, relief=tk.FLAT)
        self.target_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 3))
        tk.Label(self.target_card, text="SEND TARGET", font=("DejaVu Sans", 9, "bold"), bg=pal["bg_surface"], fg=pal["text_secondary"]).pack(anchor=tk.NW, padx=12, pady=(6, 0))
        self.lbl_target = tk.Label(self.target_card, textvariable=self.current_target, font=("DejaVu Sans Mono", 54, "bold"), bg=pal["bg_surface"], fg=pal["accent_amber"], wraplength=350)
        self.lbl_target.pack(expand=True)
        self.lbl_dotrep = tk.Label(self.target_card, textvariable=self.target_dotrep, font=("DejaVu Sans Mono", 18, "bold"), bg=pal["bg_surface"], fg=pal["accent_cyan"], wraplength=350)
        self.lbl_dotrep.pack(pady=(0, 10))

        # RX Card
        rx_card = tk.Frame(stage, bg=pal["bg_surface"], bd=1, relief=tk.FLAT)
        rx_card.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(3, 0))
        tk.Label(rx_card, text="DECODED PADDLE STREAM", font=("DejaVu Sans", 9, "bold"), bg=pal["bg_surface"], fg=pal["text_secondary"]).pack(anchor=tk.NW, padx=12, pady=(6, 0))
        self.lbl_echo_entry = tk.Label(rx_card, textvariable=self.current_echo_buffer, font=("DejaVu Sans Mono", 36, "bold"), bg=pal["bg_surface"], fg=pal["text_primary"], wraplength=350)
        self.lbl_echo_entry.pack(expand=True)
        self.lbl_rx_history = tk.Label(rx_card, textvariable=self.rx_stream_text, font=("DejaVu Sans Mono", 12), bg=pal["bg_surface"], fg=pal["text_secondary"], anchor=tk.CENTER)
        self.lbl_rx_history.pack(fill=tk.X, padx=10, pady=(0, 10))

        # 3. Telemetry
        telemetry = tk.Frame(self, bg=pal["bg_surface"], height=36)
        telemetry.pack(side=tk.TOP, fill=tk.X, padx=6, pady=2)
        self.lbl_score = tk.Label(telemetry, text="SCORE: 0 / 0", font=("DejaVu Sans Mono", 10, "bold"), bg=pal["bg_surface"], fg=pal["text_primary"])
        self.lbl_score.pack(side=tk.LEFT, padx=14, pady=5)
        self.lbl_acc = tk.Label(telemetry, text="ACCURACY: ---%", font=("DejaVu Sans Mono", 10, "bold"), bg=pal["bg_surface"], fg=pal["accent_green"])
        self.lbl_acc.pack(side=tk.LEFT, padx=14, pady=5)
        tk.Button(telemetry, text="SKIP ❯", font=("DejaVu Sans", 8, "bold"), bg=pal["bg_control"], fg=pal["text_primary"], bd=0, padx=8, command=self._load_next_target).pack(side=tk.RIGHT, padx=8, pady=5)

        # 4. Status
        bottom = tk.Frame(self, bg=pal["bg_main"], height=20)
        bottom.pack(side=tk.BOTTOM, fill=tk.X, padx=6, pady=(0, 2))
        self.lbl_status = tk.Label(bottom, textvariable=self.status_message, font=("DejaVu Sans", 8), bg=pal["bg_main"], fg=pal["text_secondary"], anchor=tk.W)
        self.lbl_status.pack(side=tk.LEFT, fill=tk.X)

    def _refresh_serial_ports(self):
        ports = serial.tools.list_ports.comports()
        self.combo_port["values"] = [p.device for p in ports]
        if self.combo_port["values"]:
            self.combo_port.current(0)
        else:
            self.combo_port.set("")

    def _toggle_connection(self):
        worker = self.controller.worker
        pal = self.controller.PALETTE
        if worker.serial_conn and worker.serial_conn.is_open:
            worker.disconnect()
            self.btn_conn.configure(text="CONNECT", bg=pal["accent_cyan"], fg=pal["bg_main"])
        else:
            port = self.combo_port.get()
            if not port:
                messagebox.showwarning("Serial Connection", "No serial port selected.", parent=self)
                return
            proto = self.combo_protocol.get()
            baud = 115200 if "115200" in proto else (1200 if "1200" in proto else 9600)
            stopbits = serial.STOPBITS_ONE if baud == 115200 else serial.STOPBITS_TWO
            worker.connect(port, baud, stopbits)
            self.btn_conn.configure(text="DISCONNECT", bg=pal["accent_red"], fg=pal["text_primary"])

    def _generate_dotrep(self, text: str) -> str:
        return " ".join(ITU_MORSE.get(c, "") for c in text.upper() if c in ITU_MORSE)

    def _load_next_target(self):
        self.current_echo_buffer.set("")
        pd = self.controller.profile_data
        lvl = pd.get("koch_level", 2)
        seq = self.controller.KOCH_SEQUENCE

        if self.mode_id == 1:
            target = random.choice(seq[:lvl])
        elif self.mode_id == 2:
            target = random.choice(BANK_2)
        elif self.mode_id == 3:
            target = random.choice(BANK_3)
        elif self.mode_id == 4:
            target = random.choice(BANK_4)
        elif self.mode_id == 5:
            target = random.choice(BANK_NAMES)
        elif self.mode_id == 6:
            target = random.choice(BANK_QSO)
        elif self.mode_id == 7:
            # Fallback for weak skills if metrics engine not fully wired
            target = random.choice(seq[:lvl]) 
        else:
            target = "FREE"

        self.current_target.set(target)
        self.target_dotrep.set(self._generate_dotrep(target) if target != "FREE" else "[Head Copy / Free Echo Mode]")
        self.lbl_target.configure(fg=self.controller.PALETTE["accent_amber"])

    def _evaluate_entry(self):
        expected = self.current_target.get().upper().strip()
        entered = self.current_echo_buffer.get().upper().strip()
        pal = self.controller.PALETTE

        if not expected or expected == "FREE":
            return

        self.score_total += 1
        if entered == expected:
            self.score_correct += 1
            self.lbl_target.configure(fg=pal["accent_green"])
            self.after(160, self._load_next_target)
        else:
            self.lbl_target.configure(fg=pal["accent_red"])
            self.after(350, lambda: self.lbl_target.configure(fg=pal["accent_amber"]))
            self.current_echo_buffer.set("")

        # Save stats instantly
        self.controller.profile_data["score_correct"] = self.score_correct
        self.controller.profile_data["score_total"] = self.score_total
        self._update_score_ui()

    def _update_score_ui(self):
        acc = (self.score_correct / self.score_total * 100) if self.score_total > 0 else 0.0
        self.lbl_score.configure(text=f"SCORE: {self.score_correct} / {self.score_total}")
        self.lbl_acc.configure(text=f"ACCURACY: {acc:.1f}%")

    def _poll_queues(self):
        worker = self.controller.worker
        pal = self.controller.PALETTE

        # Rx Data
        while not worker.data_queue.empty():
            incoming = worker.data_queue.get_nowait()
            self.rx_stream_text.set((self.rx_stream_text.get() + incoming)[-40:])

            target = self.current_target.get().upper()

            for char in incoming:
                c = char.upper()
                if c in ("\r", "\n", " "):
                    if len(self.current_echo_buffer.get()) > 0:
                        self._evaluate_entry()
                    continue

                if c.isalnum() or c in "/?.,=-+@":
                    buf = self.current_echo_buffer.get() + c
                    self.current_echo_buffer.set(buf)
                    if self.mode_id == 1 or (len(buf) == len(target) and target != "FREE"):
                        self._evaluate_entry()

        # Status Updates
        while not worker.status_queue.empty():
            msg_type, msg = worker.status_queue.get_nowait()
            self.status_message.set(f"[{msg_type}] {msg}")
            if msg_type == "ERROR":
                self.lbl_status.configure(fg=pal["accent_red"])
            elif msg_type == "CONNECTED":
                self.lbl_status.configure(fg=pal["accent_green"])
            else:
                self.lbl_status.configure(fg=pal["text_secondary"])

        self.after(20, self._poll_queues)


if __name__ == "__main__":
    app = MorseTrainerApp()
    app.mainloop()
