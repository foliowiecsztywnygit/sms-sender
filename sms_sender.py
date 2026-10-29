#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SMS Sender – Masowa wysyłka SMS przez API sms-gate.app (Multi-Device + DualSIM + AntiSpam + Multi-Template)
Aplikacja desktopowa Tkinter z checkpointami, spintaxem, wyborem urządzenia (Tel 1-3 / Tryb Turbo x3) i opcją rotacji.
"""

import json
import os
import re
import random
import time
import threading
import csv
import io
import tkinter as tk
from tkinter import messagebox
from pathlib import Path
import requests
from requests.auth import HTTPBasicAuth

# ──────────────────────────────────────────────
# KONFIGURACJA DANYCH LOGOWANIA
# ──────────────────────────────────────────────
API_URL = os.environ.get("SMSGATE_API_URL", "https://smsgate-api.brosystems.pl/api/3rdparty/v1/messages")

# Słownik przechowujący dane dostępowe dla telefonów:
CREDENTIALS = {
    1: ("MYVTZQ", "eyjzqerafikelw"),   # Telefon 1 (Dual SIM)
    2: ("JTGQYJ", "9z9mmyzswkfdxm"),   # Telefon 2 (Dual SIM)
    3: ("DQZDJ-", "-xdgjpzxmurnns"),   # Telefon 3 (Dual SIM)
    4: ("69VQFK", "a33g_l_ml7vkw_"),   # Telefon 4 (Dual SIM)
    5: ("7V_QA7", "ulat1p8gnj27lb")    # Telefon 5 (Single SIM)
}

# Dostępne karty SIM w telefonach:
AVAILABLE_SIMS = [
    (1, 1, "Tel 1 – SIM 1"),
    (1, 2, "Tel 1 – SIM 2"),
    (2, 1, "Tel 2 – SIM 1"),
    (2, 2, "Tel 2 – SIM 2"),
    (3, 1, "Tel 3 – SIM 1"),
    (3, 2, "Tel 3 – SIM 2"),
    (4, 1, "Tel 4 – SIM 1"),
    (4, 2, "Tel 4 – SIM 2"),
    (5, 1, "Tel 5 – SIM 1"),
]

def build_interleaved_sequence(selected_sims: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """
    Tworzy zoptymalizowaną sekwencję kart SIM, maksymalizując odstęp między SIM-ami tego samego telefonu.
    Np. mając [(1, 1), (1, 2), (2, 1), (3, 1), (3, 2)], daje:
    [(1, 1), (2, 1), (3, 1), (1, 2), (3, 2)]
    """
    if not selected_sims:
        return []
    sim1 = [c for c in selected_sims if c[1] == 1]
    sim2 = [c for c in selected_sims if c[1] == 2]
    sim1.sort(key=lambda c: c[0])
    sim2.sort(key=lambda c: c[0])
    return sim1 + sim2
# ──────────────────────────────────────────────

STATE_FILE = Path(__file__).parent / "sms_state.json"

def extract_phone(row_text: str) -> str | None:
    text = re.sub(r'\.0\b', '', row_text)
    matches = re.finditer(r'\+?[\d\s\-]{9,20}', text)
    for match in matches:
        digits = re.sub(r'[\s\-]', '', match.group())
        if re.match(r'^\+?\d+$', digits):
            if digits.startswith('+48') and len(digits) == 12:
                return digits
            elif digits.startswith('48') and len(digits) == 11:
                return f"+{digits}"
            elif len(digits) == 9:
                return f"+48{digits}"
    return None

def parse_csv_line(line: str) -> dict | None:
    try:
        reader = csv.reader(io.StringIO(line.strip()))
        parts = next(reader)
    except StopIteration:
        return None
    except Exception:
        parts = [p.strip() for p in line.split(',')]
        
    if len(parts) < 2:
        return None
        
    name = parts[0].strip()
    city = parts[1].strip() if len(parts) > 1 and parts[1].strip() else (parts[2].strip() if len(parts) > 2 else "")
    
    phone = None
    for part in parts:
        text = re.sub(r'\.0$', '', part.strip())
        digits = re.sub(r'[\s\-]', '', text)
        if re.match(r'^\+?\d+$', digits):
            if digits.startswith('+48') and len(digits) == 12:
                phone = digits
                break
            elif digits.startswith('48') and len(digits) == 11:
                phone = f"+{digits}"
                break
            elif len(digits) == 9:
                phone = f"+48{digits}"
                break
                
    if not phone:
        phone = extract_phone(line)
        
    return {"name": name, "city": city, "phone": phone}

# --- ZAAWANSOWANE NARZĘDZIA ANTY-SPAMOWE & SPINTAX ---

def resolve_spintax(text: str, context: dict | None = None) -> str:
    """
    Zaawansowany parser spintax:
    - Obsługa zmiennych z domyślną wartością: {Name}, {Name:Klient}, {City}, {City:Twojej okolicy}
    - Zagnieżdżony spintax: {Dzień dobry|{Cześć|Hej}}
    - Opcjonalne warianty: [opcjonalny tekst] (50% szans) oraz puste opcje {tekst|}
    - Losowe identyfikatory anty-spamowe: {rand_num:MIN:MAX}, {rand_code:DŁUGOŚĆ}
    - Usuwanie zbędnych wielokrotnych spacji po pustych opcjach.
    """
    if context is None:
        context = {}
        
    name = context.get("name", "").strip()
    city = context.get("city", "").strip()

    # 1. Obsługa zmiennych {Name} i {City} (z opcją fallback {Name:Kliencie})
    def replace_var(m):
        var_name = m.group(1).lower()
        fallback = m.group(2) if m.group(2) is not None else ""
        if var_name == "name":
            return name if name else fallback
        elif var_name == "city":
            return city if city else fallback
        return m.group(0)

    text = re.sub(r'\{(Name|City)(?::([^}]*))?\}', replace_var, text, flags=re.IGNORECASE)

    # 2. Losowe kody i numery zapobiegające filtracji po powtarzalnym tekście
    def replace_rand_num(m):
        try:
            return str(random.randint(int(m.group(1)), int(m.group(2))))
        except Exception:
            return m.group(0)
    text = re.sub(r'\{rand_num:(\d+):(\d+)\}', replace_rand_num, text, flags=re.IGNORECASE)

    def replace_rand_code(m):
        try:
            length = int(m.group(1))
            chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
            return "".join(random.choice(chars) for _ in range(length))
        except Exception:
            return m.group(0)
    text = re.sub(r'\{rand_code:(\d+)\}', replace_rand_code, text, flags=re.IGNORECASE)

    # 3. Opcjonalne fragmenty w nawiasach kwadratowych [tekst] lub [opcja1|opcja2]
    bracket_pattern = re.compile(r'\[([^\[\]]+)\]')
    while True:
        match = bracket_pattern.search(text)
        if not match:
            break
        options = match.group(1).split('|')
        if len(options) == 1:
            choice = options[0] if random.random() < 0.5 else ""
        else:
            choice = random.choice(options)
        text = text[:match.start()] + choice + text[match.end():]

    # 4. Zagnieżdżony Spintax {opcja1|opcja2|{a|b}}
    pattern = re.compile(r'\{([^{}]+)\}')
    loops = 0
    while loops < 100:
        match = pattern.search(text)
        if not match:
            break
        options = match.group(1).split('|')
        choice = random.choice(options)
        text = text[:match.start()] + choice + text[match.end():]
        loops += 1

    # 5. Normalizacja spacji (usuwanie podwójnych spacji bez naruszania nowych linii)
    lines = [re.sub(r'[ \t]{2,}', ' ', l).strip() for l in text.splitlines()]
    return "\n".join(lines)

def apply_obfuscation(text: str) -> str:
    """
    Modyfikuje wybrane znaki diakrytyczne i interpunkcję, chroniąc adresy URL przed uszkodzeniem.
    """
    # Zabezpieczenie linków URL przed podmianą znaków
    url_pattern = re.compile(r'https?://[^\s]+')
    urls = []
    def save_url(m):
        urls.append(m.group(0))
        return f"__URL_{len(urls)-1}__"
    
    text_safe = url_pattern.sub(save_url, text)

    pl_chars = {
        'ą':'a', 'ć':'c', 'ę':'e', 'ł':'l', 'ń':'n', 'ó':'o', 'ś':'s', 'ż':'z', 'ź':'z',
        'Ą':'A', 'Ć':'C', 'Ę':'E', 'Ł':'L', 'Ń':'N', 'Ó':'O', 'Ś':'S', 'Ż':'Z', 'Ź':'Z'
    }
    chars = list(text_safe)
    for i in range(len(chars)):
        char = chars[i]
        if char in pl_chars and random.random() < 0.60:    
            chars[i] = pl_chars[char]
        elif char in [',', '.'] and random.random() < 0.30:  
            chars[i] = ''
        elif char == ' ' and random.random() < 0.05:       
            chars[i] = '  '
    result = "".join(chars)

    # Przywrócenie adresów URL
    for i, url in enumerate(urls):
        result = result.replace(f"__URL_{i}__", url)
    return result


class SMSSenderApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("SMS Sender PRO - Turbo 3 Devices & DualSIM AntiSpam")
        self.root.geometry("1100x880")
        self.root.minsize(1050, 800)
        self.root.configure(bg="#1e1e2e")

        self.current_index = 0
        self.sim_step = 0
        self.status = "IDLE"        
        self.worker_thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.pause_event.set() 

        self._build_ui()
        self._load_state()

    def _build_ui(self):
        style = {
            "fg": "#cdd6f4", "insertbackground": "#cdd6f4",
            "selectbackground": "#45475a", "font": ("Consolas", 10)
        }
        btn_style = {
            "font": ("Segoe UI", 10, "bold"), "relief": "flat", "cursor": "hand2",
            "activeforeground": "#1e1e2e", "bd": 0, "padx": 14, "pady": 6
        }

        # CSV
        tk.Label(self.root, text="📋  Dane CSV (wklej wiersze):", bg="#1e1e2e", fg="#89b4fa", font=("Segoe UI", 11, "bold"), anchor="w").pack(fill="x", padx=10, pady=(10, 2))
        csv_frame = tk.Frame(self.root, bg="#313244", bd=1, relief="solid")
        csv_frame.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        self.csv_text = tk.Text(csv_frame, height=8, wrap="none", **style, bg="#313244", bd=0, highlightthickness=0)
        csv_sb = tk.Scrollbar(csv_frame, command=self.csv_text.yview)
        self.csv_text.configure(yscrollcommand=csv_sb.set)
        csv_sb.pack(side="right", fill="y")
        self.csv_text.pack(fill="both", expand=True, padx=4, pady=4)

        # SZABLON SPINTAX
        tk.Label(self.root, text="✉️  Szablony SMS (oddzielaj kolejne wpisując '---' w nowej linii):", bg="#1e1e2e", fg="#89b4fa", font=("Segoe UI", 11, "bold"), anchor="w").pack(fill="x", padx=10, pady=(4, 2))
        sms_frame = tk.Frame(self.root, bg="#313244", bd=1, relief="solid")
        sms_frame.pack(fill="x", padx=10, pady=(0, 6))
        self.sms_text = tk.Text(sms_frame, height=7, wrap="word", **style, bg="#313244", bd=0, highlightthickness=0)
        self.sms_text.pack(fill="x", padx=4, pady=4)

        # USTAWIENIA CZASU
        settings_frame = tk.LabelFrame(
            self.root, text="⏱  Ustawienia Odstępów Czasowych (sekundy)",
            bg="#1e1e2e", fg="#89b4fa", font=("Segoe UI", 10, "bold"), bd=1, relief="solid"
        )
        settings_frame.pack(fill="x", padx=10, pady=(0, 6))

        times_row = tk.Frame(settings_frame, bg="#1e1e2e")
        times_row.pack(fill="x", padx=8, pady=4)

        # 1. Pauza po pełnym cyklu
        tk.Label(times_row, text="Długa pauza po pełnym cyklu:", bg="#1e1e2e", fg="#cdd6f4", font=("Segoe UI", 9, "bold")).pack(side="left")
        tk.Label(times_row, text="Min:", bg="#1e1e2e", fg="#a6adc8", font=("Segoe UI", 9)).pack(side="left", padx=(4, 2))
        self.delay_min_var = tk.StringVar(value="40.5")
        tk.Entry(times_row, textvariable=self.delay_min_var, width=5, font=("Consolas", 10), bg="#313244", fg="#cdd6f4", bd=1, relief="solid").pack(side="left", padx=2)
        tk.Label(times_row, text="Max:", bg="#1e1e2e", fg="#a6adc8", font=("Segoe UI", 9)).pack(side="left", padx=(4, 2))
        self.delay_max_var = tk.StringVar(value="90.5")
        tk.Entry(times_row, textvariable=self.delay_max_var, width=5, font=("Consolas", 10), bg="#313244", fg="#cdd6f4", bd=1, relief="solid").pack(side="left", padx=2)

        tk.Label(times_row, text="│", bg="#1e1e2e", fg="#45475a").pack(side="left", padx=8)

        # 2. Odstęp ten sam telefon (SIM1/SIM2)
        tk.Label(times_row, text="Ten sam telefon (SIM 1 ↔ SIM 2):", bg="#1e1e2e", fg="#f9e2af", font=("Segoe UI", 9, "bold")).pack(side="left")
        tk.Label(times_row, text="Min:", bg="#1e1e2e", fg="#a6adc8", font=("Segoe UI", 9)).pack(side="left", padx=(4, 2))
        self.same_phone_min_var = tk.StringVar(value="30.0")
        tk.Entry(times_row, textvariable=self.same_phone_min_var, width=5, font=("Consolas", 10), bg="#313244", fg="#cdd6f4", bd=1, relief="solid").pack(side="left", padx=2)
        tk.Label(times_row, text="Max:", bg="#1e1e2e", fg="#a6adc8", font=("Segoe UI", 9)).pack(side="left", padx=(4, 2))
        self.same_phone_max_var = tk.StringVar(value="45.0")
        tk.Entry(times_row, textvariable=self.same_phone_max_var, width=5, font=("Consolas", 10), bg="#313244", fg="#cdd6f4", bd=1, relief="solid").pack(side="left", padx=2)

        tk.Label(times_row, text="│", bg="#1e1e2e", fg="#45475a").pack(side="left", padx=8)

        # 3. Odstęp różne telefony
        tk.Label(times_row, text="Różne telefony:", bg="#1e1e2e", fg="#74c7ec", font=("Segoe UI", 9, "bold")).pack(side="left")
        tk.Label(times_row, text="Min:", bg="#1e1e2e", fg="#a6adc8", font=("Segoe UI", 9)).pack(side="left", padx=(4, 2))
        self.diff_phone_min_var = tk.StringVar(value="3.0")
        tk.Entry(times_row, textvariable=self.diff_phone_min_var, width=5, font=("Consolas", 10), bg="#313244", fg="#cdd6f4", bd=1, relief="solid").pack(side="left", padx=2)
        tk.Label(times_row, text="Max:", bg="#1e1e2e", fg="#a6adc8", font=("Segoe UI", 9)).pack(side="left", padx=(4, 2))
        self.diff_phone_max_var = tk.StringVar(value="6.0")
        tk.Entry(times_row, textvariable=self.diff_phone_max_var, width=5, font=("Consolas", 10), bg="#313244", fg="#cdd6f4", bd=1, relief="solid").pack(side="left", padx=2)

        # USTAWIENIA KART SIM
        sim_frame = tk.LabelFrame(
            self.root, text="📱  Karty SIM do wysyłki (zaznacz aktywne karty)",
            bg="#1e1e2e", fg="#89b4fa", font=("Segoe UI", 10, "bold"), bd=1, relief="solid"
        )
        sim_frame.pack(fill="x", padx=10, pady=(0, 6))

        sim_row = tk.Frame(sim_frame, bg="#1e1e2e")
        sim_row.pack(fill="x", padx=8, pady=4)

        self.sim_checkboxes: dict[tuple[int, int], tk.BooleanVar] = {}
        sim_defs = [
            (1, 1, "Tel 1 – SIM 1", "#74c7ec"),
            (1, 2, "Tel 1 – SIM 2", "#74c7ec"),
            (2, 1, "Tel 2 – SIM 1", "#f9e2af"),
            (2, 2, "Tel 2 – SIM 2", "#f9e2af"),
            (3, 1, "Tel 3 – SIM 1", "#a6e3a1"),
            (3, 2, "Tel 3 – SIM 2", "#a6e3a1"),
            (4, 1, "Tel 4 – SIM 1", "#fab387"),
            (4, 2, "Tel 4 – SIM 2", "#fab387"),
            (5, 1, "Tel 5 – SIM 1", "#cba6f7"),
        ]

        for dev, sim, label, col in sim_defs:
            var = tk.BooleanVar(value=True)
            self.sim_checkboxes[(dev, sim)] = var
            cb = tk.Checkbutton(
                sim_row, text=label, variable=var,
                bg="#1e1e2e", fg=col, selectcolor="#313244",
                activebackground="#1e1e2e", activeforeground=col,
                font=("Segoe UI", 10, "bold")
            )
            cb.pack(side="left", padx=6)

        btn_all = tk.Button(
            sim_row, text="Zaznacz wszystkie", font=("Segoe UI", 8, "bold"),
            bg="#45475a", fg="#cdd6f4", activebackground="#585b70",
            relief="flat", bd=0, padx=8, pady=2, cursor="hand2",
            command=self._select_all_sims
        )
        btn_all.pack(side="left", padx=(12, 4))

        btn_none = tk.Button(
            sim_row, text="Odznacz wszystkie", font=("Segoe UI", 8, "bold"),
            bg="#45475a", fg="#cdd6f4", activebackground="#585b70",
            relief="flat", bd=0, padx=8, pady=2, cursor="hand2",
            command=self._deselect_all_sims
        )
        btn_none.pack(side="left", padx=2)

        self.sim_info_label = tk.Label(
            sim_row, text="(Skrypt automatycznie przeplata karty i dba o bezpieczny odpoczynek modemu)",
            bg="#1e1e2e", fg="#a6adc8", font=("Segoe UI", 9)
        )
        self.sim_info_label.pack(side="left", padx=(10, 0))

        # PRZYCISKI
        btn_row = tk.Frame(self.root, bg="#1e1e2e")
        btn_row.pack(fill="x", padx=10, pady=6)

        self.btn_start = tk.Button(btn_row, text="▶  START", bg="#a6e3a1", fg="#1e1e2e", activebackground="#94e2d5", command=self._on_start, **btn_style)
        self.btn_start.pack(side="left", padx=(0, 6))
        self.btn_pause = tk.Button(btn_row, text="⏸  PAUZA", bg="#f9e2af", fg="#1e1e2e", activebackground="#f5c2e7", command=self._on_pause, **btn_style)
        self.btn_pause.pack(side="left", padx=(0, 6))
        self.btn_terminate = tk.Button(btn_row, text="⏹  TERMINACJA", bg="#f38ba8", fg="#1e1e2e", activebackground="#eba0ac", command=self._on_terminate, **btn_style)
        self.btn_terminate.pack(side="left", padx=(0, 6))
        self.btn_clear = tk.Button(btn_row, text="🗑  WYCZYŚĆ DANE", bg="#6c7086", fg="#cdd6f4", activebackground="#9399b2", command=self._on_clear, **btn_style)
        self.btn_clear.pack(side="left")

        # STATUS
        self.status_var = tk.StringVar(value="Status: IDLE | Gotowy do startu")
        tk.Label(self.root, textvariable=self.status_var, bg="#1e1e2e", fg="#f5e0dc", font=("Segoe UI", 12, "bold"), anchor="w").pack(fill="x", padx=10, pady=(4, 2))

        # LOG
        tk.Label(self.root, text="📝  Log zdarzeń:", bg="#1e1e2e", fg="#89b4fa", font=("Segoe UI", 11, "bold"), anchor="w").pack(fill="x", padx=10, pady=(4, 2))
        log_frame = tk.Frame(self.root, bg="#181825", bd=1, relief="solid")
        log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.log_text = tk.Text(log_frame, height=12, wrap="word", state="disabled", **style, bg="#181825", bd=0, highlightthickness=0)
        log_sb = tk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_sb.set)
        log_sb.pack(side="right", fill="y")
        self.log_text.pack(fill="both", expand=True, padx=4, pady=4)

    def _select_all_sims(self):
        for var in self.sim_checkboxes.values():
            var.set(True)

    def _deselect_all_sims(self):
        for var in self.sim_checkboxes.values():
            var.set(False)

    def _get_selected_sims(self) -> list[tuple[int, int]]:
        return [key for key, var in self.sim_checkboxes.items() if var.get()]

    def _log(self, msg: str):
        def _append():
            self.log_text.configure(state="normal")
            self.log_text.insert("end", f"{msg}\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        self.root.after(0, _append)

    def _update_status(self, sent: int, total: int, label: str):
        self.root.after(0, lambda: self.status_var.set(
            f"Wysłano {sent}/{total} | Status: {label}"
        ))

    def _save_state(self):
        selected_sims_keys = [f"{d}_{s}" for (d, s), var in self.sim_checkboxes.items() if var.get()]
        state = {
            "csv": self.csv_text.get("1.0", "end-1c"),
            "sms_template": self.sms_text.get("1.0", "end-1c"),
            "current_index": self.current_index,
            "sim_step": getattr(self, "sim_step", 0),
            "turbo_step": getattr(self, "sim_step", 0),
            "selected_sims": selected_sims_keys,
            "delay_min": self.delay_min_var.get(),
            "delay_max": self.delay_max_var.get(),
            "same_phone_min": self.same_phone_min_var.get(),
            "same_phone_max": self.same_phone_max_var.get(),
            "diff_phone_min": self.diff_phone_min_var.get(),
            "diff_phone_max": self.diff_phone_max_var.get(),
            "status": self.status,
        }
        try:
            STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as e:
            self._log(f"⚠ Błąd zapisu stanu: {e}")

    def _load_state(self):
        if not STATE_FILE.exists(): return
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return

        self.current_index = state.get("current_index", 0)
        self.sim_step = state.get("sim_step", state.get("turbo_step", 0))
        self.delay_min_var.set(str(state.get("delay_min", "40.5")))
        self.delay_max_var.set(str(state.get("delay_max", "90.5")))
        self.same_phone_min_var.set(str(state.get("same_phone_min", "30.0")))
        self.same_phone_max_var.set(str(state.get("same_phone_max", "45.0")))
        self.diff_phone_min_var.set(str(state.get("diff_phone_min", "3.0")))
        self.diff_phone_max_var.set(str(state.get("diff_phone_max", "6.0")))

        saved_sims = state.get("selected_sims")
        if saved_sims is not None and isinstance(saved_sims, list):
            saved_set = set(saved_sims)
            for (d, s), var in self.sim_checkboxes.items():
                var.set(f"{d}_{s}" in saved_set)
        else:
            dev_mode = state.get("device_mode", 4)
            if dev_mode == 4:
                for var in self.sim_checkboxes.values(): var.set(True)
            elif dev_mode == 1:
                self.sim_checkboxes[(1, 1)].set(True)
                self.sim_checkboxes[(1, 2)].set(state.get("auto_switch", False) or state.get("current_sim") == 2)
                self.sim_checkboxes[(2, 1)].set(False)
                self.sim_checkboxes[(3, 1)].set(False)
                self.sim_checkboxes[(3, 2)].set(False)
            elif dev_mode == 2:
                for k, var in self.sim_checkboxes.items(): var.set(k == (2, 1))
            elif dev_mode == 3:
                self.sim_checkboxes[(1, 1)].set(False)
                self.sim_checkboxes[(1, 2)].set(False)
                self.sim_checkboxes[(2, 1)].set(False)
                self.sim_checkboxes[(3, 1)].set(True)
                self.sim_checkboxes[(3, 2)].set(state.get("auto_switch", False) or state.get("current_sim") == 2)

        csv_data = state.get("csv", "")
        if csv_data:
            self.csv_text.delete("1.0", "end")
            self.csv_text.insert("1.0", csv_data)
        
        sms_tpl = state.get("sms_template", "")
        if sms_tpl:
            self.sms_text.delete("1.0", "end")
            self.sms_text.insert("1.0", sms_tpl)

        if self.current_index > 0:
            self.status = "PAUSED"
            lines = [l for l in csv_data.splitlines() if l.strip()]
            self._update_status(self.current_index, len(lines), "PAUZA (wznowiono)")
            self._log(f"🔄 Wczytano stan: kontynuacja od wiersza {self.current_index + 1}")
        else:
            self.status = "IDLE"
            self._log("📂 Wczytano poprzedni stan (od początku).")

    def _on_start(self):
        if self.status == "RUNNING": return

        csv_raw = self.csv_text.get("1.0", "end-1c").strip()
        sms_tpl_raw = self.sms_text.get("1.0", "end-1c").strip()

        if not csv_raw:
            messagebox.showwarning("Brak danych", "Wklej dane CSV do głównego okna.")
            return
        
        templates = [t.strip() for t in sms_tpl_raw.split('---') if t.strip()]
        if not templates:
            messagebox.showwarning("Brak szablonu", "Wpisz co najmniej jeden szablon SMS.")
            return
            
        selected_sims = self._get_selected_sims()
        if not selected_sims:
            messagebox.showwarning("Brak kart SIM", "Zaznacz co najmniej jedną kartę SIM z której będą wysyłane wiadomości.")
            return

        try:
            float(self.delay_min_var.get())
            float(self.delay_max_var.get())
            float(self.same_phone_min_var.get())
            float(self.same_phone_max_var.get())
            float(self.diff_phone_min_var.get())
            float(self.diff_phone_max_var.get())
        except ValueError:
            messagebox.showwarning("Błąd wartości", "Wszystkie opóźnienia muszą być liczbami (np. 30.0).")
            return

        if self.status == "PAUSED":
            self.pause_event.set()
            self.status = "RUNNING"
            self._log("▶ Wznowiono wysyłkę.")
            if self.worker_thread is None or not self.worker_thread.is_alive():
                self._start_worker(csv_raw, templates, selected_sims)
            return

        self.current_index = 0
        self.sim_step = 0
        self.stop_event.clear()
        self.pause_event.set()
        self.status = "RUNNING"
        self._start_worker(csv_raw, templates, selected_sims)

    def _start_worker(self, csv_raw: str, templates: list[str], selected_sims: list[tuple[int, int]]):
        lines = [l for l in csv_raw.splitlines() if l.strip()]
        delays = {
            "cycle_min": float(self.delay_min_var.get()),
            "cycle_max": float(self.delay_max_var.get()),
            "same_phone_min": float(self.same_phone_min_var.get()),
            "same_phone_max": float(self.same_phone_max_var.get()),
            "diff_phone_min": float(self.diff_phone_min_var.get()),
            "diff_phone_max": float(self.diff_phone_max_var.get()),
        }
        
        self.worker_thread = threading.Thread(
            target=self._send_loop, 
            args=(lines, templates, selected_sims, delays), 
            daemon=True
        )
        self.worker_thread.start()

    def _on_pause(self):
        if self.status != "RUNNING": return
        self.status = "PAUSED"
        self.pause_event.clear()
        self._log("⏸ Zapauzowano wysyłkę.")
        self._save_state()

    def _on_terminate(self):
        if self.status == "IDLE": return
        self.stop_event.set()
        self.pause_event.set() 
        self.status = "IDLE"
        self.current_index = 0
        self.sim_step = 0
        self._save_state()
        self._log("⏹ Terminacja – postęp zresetowany.")
        self._update_status(0, 0, "IDLE")

    def _on_clear(self):
        if self.status == "RUNNING":
            messagebox.showwarning("Uwaga", "Najpierw zatrzymaj wysyłkę (TERMINACJA).")
            return
        self.stop_event.set()
        self.pause_event.set()
        self.status = "IDLE"
        self.current_index = 0
        self.sim_step = 0

        self.csv_text.delete("1.0", "end")
        self.sms_text.delete("1.0", "end")
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self.status_var.set("Status: IDLE | Gotowy do startu")

        if STATE_FILE.exists():
            STATE_FILE.unlink()
        self._log("🗑 Dane wyczyszczone, plik stanu usunięty.")

    def _send_loop(self, lines: list[str], templates: list[str], selected_sims: list[tuple[int, int]], delays: dict[str, float]):
        total = len(lines)
        active_sequence = build_interleaved_sequence(selected_sims)
        if not active_sequence:
            self._log("❌ Błąd: Nie wybrano żadnej karty SIM!")
            return

        seq_len = len(active_sequence)
        seq_desc = " -> ".join([f"Tel {d} (SIM {s})" for d, s in active_sequence])
        self._log(f"🚀 Start wysyłki ({seq_len} kart: {seq_desc}): {total} wierszy.")

        i = self.current_index
        sim_step = getattr(self, "sim_step", 0)
        last_device_send_time: dict[int, float] = {}

        cycle_min = delays["cycle_min"]
        cycle_max = delays["cycle_max"]
        same_phone_min = delays["same_phone_min"]
        same_phone_max = delays["same_phone_max"]
        diff_phone_min = delays["diff_phone_min"]
        diff_phone_max = delays["diff_phone_max"]

        while i < total:
            if self.stop_event.is_set():
                self._log("🛑 Wysyłka przerwana (TERMINACJA).")
                return

            while not self.pause_event.is_set():
                if self.stop_event.is_set(): return
                self._update_status(i, total, "PAUZA")
                time.sleep(0.3)

            line = lines[i].strip()
            parsed = parse_csv_line(line)

            if parsed is None or not parsed["phone"]:
                reason = "brak telefonu" if parsed else "zbyt krótki wiersz"
                self._log(f"  ⏭ Wiersz {i + 1}: Pominięto – {reason}")
                i += 1
                self.current_index = i
                self._save_state()
                continue

            phone = parsed["phone"]
            
            base_tpl = random.choice(templates)
            text_spun = resolve_spintax(base_tpl, {"name": parsed["name"], "city": parsed["city"]})
            final_text = apply_obfuscation(text_spun)

            current_dev, sim_to_use = active_sequence[sim_step % seq_len]

            # ── BEZPIECZNY ODSTĘP MODEMU DLA TEGO SAMEGO TELEFONU ──
            if current_dev in last_device_send_time:
                elapsed = time.time() - last_device_send_time[current_dev]
                required_wait = random.uniform(same_phone_min, same_phone_max)
                if elapsed < required_wait:
                    wait_needed = required_wait - elapsed
                    self._log(f"  ⏳ Tel {current_dev}: modem odpoczywa (minęło {elapsed:.1f}s, czekam jeszcze {wait_needed:.1f}s na bezpieczne przełączenie SIM)...")
                    steps = int(wait_needed * 10)
                    for _ in range(steps):
                        if self.stop_event.is_set():
                            return
                        while not self.pause_event.is_set():
                            if self.stop_event.is_set(): return
                            self._update_status(i, total, "PAUZA")
                            time.sleep(0.3)
                        time.sleep(0.1)

            self._log(f"  📤 Wiersz {i + 1}: Wysyłam do {phone} (Tel {current_dev}, SIM {sim_to_use})...")
            self._update_status(i, total, "W TRAKCIE")

            success, skip_wait = self._send_sms(phone, final_text, current_dev, sim_to_use)
            last_device_send_time[current_dev] = time.time()
            
            if success:
                self._log(f"  ✅ Wysłano do {phone}")
            else:
                self._log(f"  ❌ Błąd wysyłki do {phone}")

            i += 1
            sim_step += 1
            self.current_index = i
            self.sim_step = sim_step
            self._save_state()
            self._update_status(i, total, "W TRAKCIE")

            if i < total and not self.stop_event.is_set():
                if skip_wait:
                    self._log("  ⚡ Omijam czekanie (odrzucony numer)")
                    time.sleep(0.5)
                    continue

                # Czy zakończono pełny cykl wszystkich zaznaczonych kart?
                if sim_step % seq_len == 0:
                    delay = random.uniform(cycle_min, cycle_max)
                    self._log(f"  ⏳ Pełny cykl kart zakończony ({seq_len} SMS). Długa pauza: {delay:.1f}s...")
                else:
                    delay = random.uniform(diff_phone_min, diff_phone_max)
                    next_dev, next_sim = active_sequence[sim_step % seq_len]
                    self._log(f"  ⚡ Następna karta -> Tel {next_dev} (SIM {next_sim}). Odstęp: {delay:.1f}s...")

                steps = int(delay * 10)
                for _ in range(steps):
                    if self.stop_event.is_set():
                        return
                    while not self.pause_event.is_set():
                        if self.stop_event.is_set(): return
                        self._update_status(i, total, "PAUZA")
                        time.sleep(0.3)
                    time.sleep(0.1)

        self.status = "IDLE"
        self._update_status(total, total, "ZAKOŃCZONO ✅")
        self._log("🏁 Kampania zakończona!")
        self._save_state()

    def _send_sms(self, phone: str, text: str, device_number: int, sim_number: int) -> tuple[bool, bool]:
        payload = {
            "textMessage": {"text": text},
            "phoneNumbers": [phone],
            "simNumber": sim_number,
            "withDeliveryReport": False
        }
        
        username, password = CREDENTIALS.get(device_number, CREDENTIALS[1])
        
        try:
            resp = requests.post(
                API_URL, json=payload, auth=HTTPBasicAuth(username, password), timeout=30
            )
            if resp.status_code in (200, 201, 202):
                return True, False
            else:
                self._log(f"    ⚠ HTTP {resp.status_code}: {resp.text[:150]}")
                skip_wait = (resp.status_code == 400)
                return False, skip_wait
        except requests.RequestException as e:
            self._log(f"    ⚠ Wyjątek: {e}")
            return False, False

def main():
    root = tk.Tk()
    app = SMSSenderApp(root)

    def on_close():
        if app.status == "RUNNING":
            app.status = "PAUSED"
        app._save_state()
        app.stop_event.set()
        app.pause_event.set()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()

if __name__ == "__main__":
    main()