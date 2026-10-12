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
API_URL = "https://api.sms-gate.app/3rdparty/v1/messages"

# Słownik przechowujący dane dostępowe dla telefonów:
CREDENTIALS = {
    1: ("AQWXKB", "rxjcknnvrkwd1s"),  # Telefon 1 (Dual SIM)
    2: ("HAIUXA", "gcbxfmsi4lqens"),  # Telefon 2 (Single SIM)
    3: ("QL5Z7O", "4jzbmvhv6tpbmd")   # Telefon 3 (Dual SIM)
}

# Sekwencja Turbo 5 kart: Tel 1 (SIM 1) -> Tel 2 (SIM 1) -> Tel 3 (SIM 1) -> Tel 1 (SIM 2) -> Tel 3 (SIM 2)
TURBO_SEQUENCE = [
    (1, 1),  # Tel 1, SIM 1
    (2, 1),  # Tel 2, SIM 1
    (3, 1),  # Tel 3, SIM 1
    (1, 2),  # Tel 1, SIM 2
    (3, 2),  # Tel 3, SIM 2
]
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
        self.turbo_step = 0
        self.current_sim = 1        
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
        settings_frame = tk.Frame(self.root, bg="#1e1e2e")
        settings_frame.pack(fill="x", padx=10, pady=4)
        
        tk.Label(settings_frame, text="⏱ Długie Opóźnienie (sekundy) - Min:", bg="#1e1e2e", fg="#cdd6f4", font=("Segoe UI", 10)).pack(side="left")
        self.delay_min_var = tk.StringVar(value="40.5")
        tk.Entry(settings_frame, textvariable=self.delay_min_var, width=6, font=("Consolas", 10), bg="#313244", fg="#cdd6f4", bd=1, relief="solid").pack(side="left", padx=5)
        
        tk.Label(settings_frame, text="Max:", bg="#1e1e2e", fg="#cdd6f4", font=("Segoe UI", 10)).pack(side="left", padx=(10, 0))
        self.delay_max_var = tk.StringVar(value="90.5")
        tk.Entry(settings_frame, textvariable=self.delay_max_var, width=6, font=("Consolas", 10), bg="#313244", fg="#cdd6f4", bd=1, relief="solid").pack(side="left", padx=5)

        # USTAWIENIA URZĄDZENIA I SIM
        hardware_frame = tk.Frame(self.root, bg="#1e1e2e")
        hardware_frame.pack(fill="x", padx=10, pady=4)
        
        # Sekcja telefonu
        device_row = tk.Frame(hardware_frame, bg="#1e1e2e")
        device_row.pack(fill="x", pady=(0, 5))
        tk.Label(device_row, text="📲 Tryb Pracy:", bg="#1e1e2e", fg="#cdd6f4", font=("Segoe UI", 10, "bold"), width=12, anchor="w").pack(side="left")
        self.device_mode_var = tk.IntVar(value=4)
        tk.Radiobutton(device_row, text="Tel 1 (DualSIM)", variable=self.device_mode_var, value=1, bg="#1e1e2e", fg="#74c7ec", selectcolor="#313244", activebackground="#1e1e2e", activeforeground="#74c7ec", font=("Segoe UI", 10)).pack(side="left", padx=2)
        tk.Radiobutton(device_row, text="Tel 2 (1 SIM)", variable=self.device_mode_var, value=2, bg="#1e1e2e", fg="#74c7ec", selectcolor="#313244", activebackground="#1e1e2e", activeforeground="#74c7ec", font=("Segoe UI", 10)).pack(side="left", padx=2)
        tk.Radiobutton(device_row, text="Tel 3 (DualSIM)", variable=self.device_mode_var, value=3, bg="#1e1e2e", fg="#74c7ec", selectcolor="#313244", activebackground="#1e1e2e", activeforeground="#74c7ec", font=("Segoe UI", 10)).pack(side="left", padx=2)
        tk.Radiobutton(device_row, text="🚀 WSZYSTKIE (Turbo 5 kart: 1->2->3->1->3->Pauza)", variable=self.device_mode_var, value=4, bg="#1e1e2e", fg="#f38ba8", selectcolor="#313244", activebackground="#1e1e2e", activeforeground="#f38ba8", font=("Segoe UI", 10, "bold")).pack(side="left", padx=(10, 0))

        # Sekcja SIM
        sim_row = tk.Frame(hardware_frame, bg="#1e1e2e")
        sim_row.pack(fill="x")
        tk.Label(sim_row, text="📱 Karty SIM:", bg="#1e1e2e", fg="#cdd6f4", font=("Segoe UI", 10, "bold"), width=12, anchor="w").pack(side="left")
        self.sim_var = tk.IntVar(value=1)
        self.sim1_rb = tk.Radiobutton(sim_row, text="Start SIM 1", variable=self.sim_var, value=1, bg="#1e1e2e", fg="#a6e3a1", selectcolor="#313244", activebackground="#1e1e2e", activeforeground="#a6e3a1", font=("Segoe UI", 10))
        self.sim1_rb.pack(side="left", padx=5)
        self.sim2_rb = tk.Radiobutton(sim_row, text="Start SIM 2", variable=self.sim_var, value=2, bg="#1e1e2e", fg="#a6e3a1", selectcolor="#313244", activebackground="#1e1e2e", activeforeground="#a6e3a1", font=("Segoe UI", 10))
        self.sim2_rb.pack(side="left", padx=5)
        self.auto_switch_var = tk.BooleanVar(value=False)
        self.switch_cb = tk.Checkbutton(sim_row, text="Rotacja SIM po wysłanym SMS (Tel 1 & Tel 3 - DualSIM)", variable=self.auto_switch_var, bg="#1e1e2e", fg="#f9e2af", selectcolor="#313244", activebackground="#1e1e2e", activeforeground="#f9e2af", font=("Segoe UI", 10))
        self.switch_cb.pack(side="left", padx=(30, 0))
        self.sim_hint_label = tk.Label(sim_row, text="(W Turbo leci sekwencja wszystkich 5 kart)", bg="#1e1e2e", fg="#a6adc8", font=("Segoe UI", 9))
        self.sim_hint_label.pack(side="left", padx=(10, 0))

        def _on_device_mode_change(*_):
            mode = self.device_mode_var.get()
            st = "disabled" if mode in (2, 4) else "normal"
            self.sim1_rb.configure(state=st)
            self.sim2_rb.configure(state=st)
            self.switch_cb.configure(state=st)
            if mode == 4:
                self.sim_hint_label.configure(text="(W Turbo sekwencja automatycznie używa 5 kart)")
            elif mode == 2:
                self.sim_hint_label.configure(text="(Tel 2 posiada tylko 1 kartę SIM)")
            else:
                self.sim_hint_label.configure(text=f"(Aktywne dla Tel {mode} - Dual SIM)")

        self.device_mode_var.trace_add("write", _on_device_mode_change)
        _on_device_mode_change()

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
        state = {
            "csv": self.csv_text.get("1.0", "end-1c"),
            "sms_template": self.sms_text.get("1.0", "end-1c"),
            "current_index": self.current_index,
            "turbo_step": self.turbo_step,
            "device_mode": self.device_mode_var.get(),
            "current_sim": self.current_sim,
            "auto_switch": self.auto_switch_var.get(),
            "delay_min": self.delay_min_var.get(),
            "delay_max": self.delay_max_var.get(),
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
        self.turbo_step = state.get("turbo_step", 0)
        self.device_mode_var.set(state.get("device_mode", 4))
        self.current_sim = state.get("current_sim", 1)
        self.sim_var.set(self.current_sim)
        self.auto_switch_var.set(state.get("auto_switch", False))
        self.delay_min_var.set(state.get("delay_min", "40.5"))
        self.delay_max_var.set(state.get("delay_max", "90.5"))

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
            
        try:
            float(self.delay_min_var.get())
            float(self.delay_max_var.get())
        except ValueError:
            messagebox.showwarning("Błąd wartości", "Opóźnienia muszą być liczbami (np. 40.5).")
            return

        if self.status == "PAUSED":
            self.pause_event.set()
            self.status = "RUNNING"
            self.current_sim = self.sim_var.get()
            self._log("▶ Wznowiono wysyłkę.")
            if self.worker_thread is None or not self.worker_thread.is_alive():
                self._start_worker(csv_raw, templates)
            return

        self.current_index = 0
        self.turbo_step = 0
        self.current_sim = self.sim_var.get() 
        self.stop_event.clear()
        self.pause_event.set()
        self.status = "RUNNING"
        self._start_worker(csv_raw, templates)

    def _start_worker(self, csv_raw: str, templates: list[str]):
        lines = [l for l in csv_raw.splitlines() if l.strip()]
        d_min = float(self.delay_min_var.get())
        d_max = float(self.delay_max_var.get())
        auto_switch = self.auto_switch_var.get()
        dev_mode = self.device_mode_var.get()
        
        self.worker_thread = threading.Thread(
            target=self._send_loop, 
            args=(lines, templates, d_min, d_max, auto_switch, dev_mode), 
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
        self.turbo_step = 0
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
        self.turbo_step = 0

        self.csv_text.delete("1.0", "end")
        self.sms_text.delete("1.0", "end")
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self.status_var.set("Status: IDLE | Gotowy do startu")

        if STATE_FILE.exists():
            STATE_FILE.unlink()
        self._log("🗑 Dane wyczyszczone, plik stanu usunięty.")

    def _send_loop(self, lines: list[str], templates: list[str], d_min: float, d_max: float, auto_switch: bool, device_mode: int):
        total = len(lines)
        
        mode_str = "TURBO 5 KART (Tel 1 SIM 1 -> Tel 2 SIM 1 -> Tel 3 SIM 1 -> Tel 1 SIM 2 -> Tel 3 SIM 2)" if device_mode == 4 else f"Tylko Telefon {device_mode}"
        self._log(f"🚀 Start wysyłki ({mode_str}): {total} wierszy.")

        i = self.current_index
        turbo_step = getattr(self, "turbo_step", 0)

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

            # Wybór urządzenia i karty SIM
            if device_mode == 4:
                current_dev, sim_to_use = TURBO_SEQUENCE[turbo_step]
            else:
                current_dev = device_mode
                sim_to_use = self.current_sim if current_dev in (1, 3) else 1

            self._log(f"  📤 Wiersz {i + 1}: Wysyłam do {phone} (Tel {current_dev}, SIM {sim_to_use})...")
            self._update_status(i, total, "W TRAKCIE")

            success, skip_wait = self._send_sms(phone, final_text, current_dev, sim_to_use)
            
            if success:
                self._log(f"  ✅ Wysłano do {phone}")
                # Rotacja SIM - tylko w trybie pojedynczego telefonu dla Tel 1 i Tel 3
                if auto_switch and current_dev in (1, 3) and device_mode != 4:
                    self.current_sim = 2 if self.current_sim == 1 else 1
                    self.root.after(0, lambda: self.sim_var.set(self.current_sim))
            else:
                self._log(f"  ❌ Błąd wysyłki do {phone}")

            i += 1
            self.current_index = i
            self._save_state()
            self._update_status(i, total, "W TRAKCIE")

            if i < total and not self.stop_event.is_set():
                
                # Sekwencja trybu Turbo 5 kart (1 -> 2 -> 3 -> 1 -> 3 -> długa pauza)
                if device_mode == 4:
                    turbo_step += 1
                    if turbo_step < len(TURBO_SEQUENCE):
                        next_dev, next_sim = TURBO_SEQUENCE[turbo_step]
                        self.turbo_step = turbo_step
                        self._save_state()
                        self._log(f"  ⚡ Tryb Turbo ({turbo_step}/5): Następny -> Tel {next_dev} (SIM {next_sim})...")
                        time.sleep(1.0)
                        continue
                    else:
                        turbo_step = 0
                        self.turbo_step = 0
                        self._save_state()
                        # Po pełnym cyklu 5 kart przechodzimy do długiego odpoczynku sprzętu

                # Standardowe oczekiwanie
                if skip_wait:
                    self._log("  ⚡ Omijam długie czekanie (odrzucony numer)")
                else:
                    delay = random.uniform(d_min, d_max)
                    self._log(f"  ⏳ Odpoczynek sprzętu. Czekam {delay:.1f}s...")
                    steps = int(delay * 10)
                    for _ in range(steps):
                        if self.stop_event.is_set():
                            return
                        time.sleep(0.1)

        self.status = "IDLE"
        self._update_status(total, total, "ZAKOŃCZONO ✅")
        self._log("🏁 Kampania zakończona!")
        self._save_state()

    def _send_sms(self, phone: str, text: str, device_number: int, sim_number: int) -> tuple[bool, bool]:
        payload = {
            "textMessage": {"text": text},
            "phoneNumbers": [phone],
            "simNumber": sim_number
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