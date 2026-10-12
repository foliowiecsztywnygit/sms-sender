#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SMS Sender PRO - Wersja Webowa (FastAPI + Coolify Docker)
Obsługa 3 telefonów, trybu Turbo (5 kart naprzemiennie), zaawansowanego spintaxu,
bezpiecznej obfuscacji URL i ciągłej pracy w tle z ochroną przed FUP.
"""

import json
import os
import re
import random
import time
import threading
import csv
import io
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

# ──────────────────────────────────────────────
# KONFIGURACJA DANYCH LOGOWANIA
# ──────────────────────────────────────────────
API_URL = "https://api.sms-gate.app/3rdparty/v1/messages"

# Słownik danych dostępowych do telefonów:
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

# Obsługa wolumenu danych pod Coolify
DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).resolve().parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = DATA_DIR / "sms_state.json"

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="SMS Sender PRO")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Stan aplikacji
state = {
    "csv": "",
    "sms_template": "",
    "current_index": 0,
    "turbo_step": 0,
    "device_mode": 4,      # 1=Tel1, 2=Tel2, 3=Tel3, 4=Turbo (5 kart)
    "current_sim": 1,      # 1 lub 2
    "auto_switch": False,  # Rotacja SIM dla trybu pojedynczego (Tel 1 i Tel 3)
    "delay_min": 40.5,
    "delay_max": 90.5,
    "status": "IDLE",      # IDLE, RUNNING, PAUSED
    "logs": []
}

worker_thread = None
stop_event = threading.Event()
pause_event = threading.Event()
pause_event.set()
state_lock = threading.Lock()

def _log(msg: str):
    with state_lock:
        state["logs"].append(msg)
        if len(state["logs"]) > 300:
            state["logs"] = state["logs"][-300:]

def save_state():
    with state_lock:
        try:
            s = state.copy()
            s["logs"] = s["logs"][-50:]  # Ostatnie 50 logów do trwałego zapisu
            STATE_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"Błąd zapisu stanu: {e}")

def load_state():
    if not STATE_FILE.exists():
        return
    try:
        s = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        with state_lock:
            state.update(s)
            # Przy restarcie serwera/kontenera w Coolify, jeśli był RUNNING, ustawiamy PAUSED
            if state.get("status") == "RUNNING":
                state["status"] = "PAUSED"
                _log(f"🔄 Wczytano stan po restarcie: wiersz {state['current_index'] + 1} (PAUZA - kliknij START)")
            elif state.get("current_index", 0) > 0:
                _log(f"🔄 Wczytano stan: zapisany wiersz {state['current_index'] + 1}")
    except Exception as e:
        print(f"Błąd odczytu stanu: {e}")

load_state()

# ──────────────────────────────────────────────
# PARSOWANIE CSV I NUMERÓW
# ──────────────────────────────────────────────
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

# ──────────────────────────────────────────────
# ZAAWANSOWANY SPINTAX I ANTY-SPAM
# ──────────────────────────────────────────────
def resolve_spintax(text: str, context: dict | None = None) -> str:
    """
    Zaawansowany parser spintax:
    - Zmienne: {Name}, {Name:Klient}, {City}, {City:Twojej okolicy}
    - Zagnieżdżony spintax: {Dzień dobry|{Cześć|Hej}}
    - Opcjonalne fragmenty: [tekst] (50% szans) oraz puste wybory {opcja|}
    - Unikalne identyfikatory anty-spamowe: {rand_num:MIN:MAX}, {rand_code:DŁUGOŚĆ}
    - Czyszczenie wielokrotnych spacji po pustych opcjach.
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

    # 2. Losowe kody i numery zapobiegające blokadom powtarzalnego tekstu
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

    # 3. Opcjonalne fragmenty [tekst] lub [opcja1|opcja2]
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

    # 5. Normalizacja spacji
    lines = [re.sub(r'[ \t]{2,}', ' ', l).strip() for l in text.splitlines()]
    return "\n".join(lines)

def apply_obfuscation(text: str) -> str:
    """
    Subtelna obfuskacja znaków z pełną ochroną adresów URL przed zniekształceniem.
    """
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

    for i, url in enumerate(urls):
        result = result.replace(f"__URL_{i}__", url)
    return result

# ──────────────────────────────────────────────
# WYSYŁKA SMS PRZEZ API
# ──────────────────────────────────────────────
def send_sms_request(phone: str, text: str, device_number: int, sim_number: int) -> tuple[bool, bool]:
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
            _log(f"    ⚠ HTTP {resp.status_code}: {resp.text[:150]}")
            skip_wait = (resp.status_code == 400)
            return False, skip_wait
    except requests.RequestException as e:
        _log(f"    ⚠ Wyjątek sieciowy: {e}")
        return False, False

# ──────────────────────────────────────────────
# PĘTLA ROBOCZA (BACKGROUND WORKER)
# ──────────────────────────────────────────────
def worker_loop():
    global state
    lines = [l for l in state["csv"].splitlines() if l.strip()]
    templates = [t.strip() for t in state["sms_template"].split('---') if t.strip()]
    total = len(lines)
    
    dev_mode = state["device_mode"]
    mode_str = "TURBO 5 KART (Tel 1 SIM 1 -> Tel 2 SIM 1 -> Tel 3 SIM 1 -> Tel 1 SIM 2 -> Tel 3 SIM 2)" if dev_mode == 4 else f"Tylko Telefon {dev_mode}"
    _log(f"🚀 Start wysyłki ({mode_str}): {total} wierszy.")

    turbo_step = state.get("turbo_step", 0)

    while state["current_index"] < total:
        if stop_event.is_set():
            _log("🛑 Wysyłka przerwana (TERMINACJA).")
            return

        while not pause_event.is_set():
            if stop_event.is_set():
                return
            time.sleep(0.3)

        i = state["current_index"]
        line = lines[i].strip()
        parsed = parse_csv_line(line)

        if parsed is None or not parsed["phone"]:
            reason = "brak telefonu" if parsed else "zbyt krótki wiersz"
            _log(f"  ⏭ Wiersz {i + 1}: Pominięto – {reason}")
            state["current_index"] += 1
            save_state()
            continue

        phone = parsed["phone"]
        base_tpl = random.choice(templates)
        text_spun = resolve_spintax(base_tpl, {"name": parsed["name"], "city": parsed["city"]})
        final_text = apply_obfuscation(text_spun)

        # Wybór urządzenia i karty SIM
        if dev_mode == 4:
            current_dev, sim_to_use = TURBO_SEQUENCE[turbo_step]
        else:
            current_dev = dev_mode
            sim_to_use = state["current_sim"] if current_dev in (1, 3) else 1

        _log(f"  📤 Wiersz {i + 1}: Wysyłam do {phone} (Tel {current_dev}, SIM {sim_to_use})...")

        success, skip_wait = send_sms_request(phone, final_text, current_dev, sim_to_use)

        if success:
            _log(f"  ✅ Wysłano do {phone}")
            # Rotacja SIM - tylko w trybie pojedynczego telefonu dla Tel 1 i Tel 3
            if state["auto_switch"] and current_dev in (1, 3) and dev_mode != 4:
                state["current_sim"] = 2 if state["current_sim"] == 1 else 1
        else:
            _log(f"  ❌ Błąd wysyłki do {phone}")

        state["current_index"] += 1
        save_state()

        if state["current_index"] < total and not stop_event.is_set():
            # Sekwencja trybu Turbo 5 kart
            if dev_mode == 4:
                turbo_step += 1
                if turbo_step < len(TURBO_SEQUENCE):
                    next_dev, next_sim = TURBO_SEQUENCE[turbo_step]
                    state["turbo_step"] = turbo_step
                    save_state()
                    _log(f"  ⚡ Tryb Turbo ({turbo_step}/5): Następny -> Tel {next_dev} (SIM {next_sim})...")
                    time.sleep(1.0)
                    continue
                else:
                    turbo_step = 0
                    state["turbo_step"] = 0
                    save_state()
                    # Po pełnym cyklu 5 kart przechodzimy do długiego odpoczynku sprzętu

            # Standardowe oczekiwanie na odpoczynek sprzętu / zapobieganie FUP
            if skip_wait:
                _log("  ⚡ Omijam długie czekanie (odrzucony numer)")
            else:
                d_min = float(state["delay_min"])
                d_max = float(state["delay_max"])
                delay = random.uniform(d_min, d_max)
                _log(f"  ⏳ Odpoczynek sprzętu. Czekam {delay:.1f}s...")
                steps = int(delay * 10)
                for _ in range(steps):
                    if stop_event.is_set():
                        return
                    time.sleep(0.1)

    state["status"] = "IDLE"
    _log("🏁 Kampania zakończona!")
    save_state()

# ──────────────────────────────────────────────
# ENDPOINTY API
# ──────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/api/state")
async def get_state():
    total_lines = len([l for l in state["csv"].splitlines() if l.strip()])
    return JSONResponse({
        "status": state["status"],
        "current_index": state["current_index"],
        "total_lines": total_lines,
        "turbo_step": state.get("turbo_step", 0),
        "device_mode": state["device_mode"],
        "current_sim": state["current_sim"],
        "auto_switch": state["auto_switch"],
        "delay_min": state["delay_min"],
        "delay_max": state["delay_max"],
        "csv": state["csv"],
        "sms_template": state["sms_template"],
        "logs": state["logs"]
    })

@app.post("/api/save_config")
async def save_config(request: Request):
    data = await request.json()
    with state_lock:
        if "csv" in data:
            state["csv"] = data["csv"]
        if "sms_template" in data:
            state["sms_template"] = data["sms_template"]
        if "delay_min" in data:
            try:
                state["delay_min"] = float(data["delay_min"])
            except ValueError:
                pass
        if "delay_max" in data:
            try:
                state["delay_max"] = float(data["delay_max"])
            except ValueError:
                pass
        if "device_mode" in data:
            state["device_mode"] = int(data["device_mode"])
        if "current_sim" in data:
            state["current_sim"] = int(data["current_sim"])
        if "auto_switch" in data:
            state["auto_switch"] = bool(data["auto_switch"])
    save_state()
    return {"status": "ok"}

@app.post("/api/start")
async def start_campaign():
    global worker_thread
    if state["status"] == "RUNNING":
        return {"status": "already_running"}

    lines = [l for l in state["csv"].splitlines() if l.strip()]
    templates = [t.strip() for t in state["sms_template"].split('---') if t.strip()]
    if not lines or not templates:
        return {"status": "error", "message": "Brak danych CSV lub szablonów SMS."}

    if state["status"] == "PAUSED":
        state["status"] = "RUNNING"
        pause_event.set()
        _log("▶ Wznowiono wysyłkę.")
        if worker_thread is None or not worker_thread.is_alive():
            worker_thread = threading.Thread(target=worker_loop, daemon=True)
            worker_thread.start()
        return {"status": "ok"}

    state["current_index"] = 0
    state["turbo_step"] = 0
    state["status"] = "RUNNING"
    stop_event.clear()
    pause_event.set()
    worker_thread = threading.Thread(target=worker_loop, daemon=True)
    worker_thread.start()
    return {"status": "ok"}

@app.post("/api/pause")
async def pause_campaign():
    if state["status"] == "RUNNING":
        state["status"] = "PAUSED"
        pause_event.clear()
        _log("⏸ Zapauzowano wysyłkę.")
        save_state()
    return {"status": "ok"}

@app.post("/api/terminate")
async def terminate_campaign():
    if state["status"] != "IDLE":
        stop_event.set()
        pause_event.set()
        state["status"] = "IDLE"
        state["current_index"] = 0
        state["turbo_step"] = 0
        save_state()
        _log("⏹ Terminacja – postęp zresetowany.")
    return {"status": "ok"}

@app.post("/api/clear")
async def clear_data():
    if state["status"] == "RUNNING":
        return {"status": "error", "message": "Najpierw zatrzymaj wysyłkę (TERMINACJA)."}
    stop_event.set()
    pause_event.set()
    with state_lock:
        state["status"] = "IDLE"
        state["current_index"] = 0
        state["turbo_step"] = 0
        state["csv"] = ""
        state["sms_template"] = ""
        state["logs"] = []
    if STATE_FILE.exists():
        STATE_FILE.unlink()
    _log("🗑 Dane wyczyszczone, plik stanu usunięty.")
    return {"status": "ok"}

@app.post("/api/test_spintax")
async def test_spintax(request: Request):
    """Pomocniczy test spintaxu z przykładowymi danymi bez wysyłki SMS."""
    data = await request.json()
    template_raw = data.get("template", "").strip()
    templates = [t.strip() for t in template_raw.split('---') if t.strip()]
    if not templates:
        return {"status": "error", "message": "Brak szablonu SMS."}
    tpl = random.choice(templates)
    sample_context = {"name": data.get("name", "Jan"), "city": data.get("city", "Warszawa")}
    spun = resolve_spintax(tpl, sample_context)
    obfuscated = apply_obfuscation(spun)
    return {"status": "ok", "raw_template": tpl, "spun": spun, "final": obfuscated}
