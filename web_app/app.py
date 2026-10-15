#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SMS Sender PRO - Wersja Webowa (FastAPI + Coolify Docker)
Obsługa 3 telefonów, trybu Turbo (5 kart zbalansowanych), zaawansowanego spintaxu,
bezpiecznej obfuscacji URL i ochrony modemu DSDS przed błędem Generic Failure.
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

DEFAULT_TEMPLATES = """{Dzień dobry | Witam serdecznie}! Tu Krzysztof. Wtorkowy poranek po weekendowym zamieszaniu to chyba wreszcie moment na spokojniejszą kawę. Dopytam krótko z ciekawości – czy macie już u siebie własny kalendarz do bezpośrednich rezerwacji online? Wdrażam w regionie proste systemy, dzięki którym turyści sami sprawdzają terminy i rezerwują z telefonu, a 100% kwoty zostaje u Was bez oddawania prowizji portalom. Podrzucić na spokojnie krótkie wideo z podglądem?
---
{Dzień dobry | Witam}! Krzysztof z tej strony. Złapałem chwilę we wtorkowe przedpołudnie, więc zapytam prosto z mostu. Czy goście mogą u Państwa zarezerwować i opłacić termin bezpośrednio przez telefon bez konieczności wcześniejszego dzwonienia? Wdrażam dla obiektów proste, bezobsługowe kalendarze działające 24/7 – cała wpłata wpada od razu na Państwa konto z pominięciem prowizji pośredników. Mogę podesłać szybkie demo do rzucenia okiem przy kawie?
---
{Dzień dobry | Cześć}! Z tej strony Krzysztof. Pora około południa we wtorek to zazwyczaj dobry moment, zanim od środy znowu zaczną się urywać telefony z pytaniami o weekend. Zastanawiałem się, czy macie już podpięty własny system rezerwacji na stronie? Uruchamiam proste kalendarze dla kwater, które same pilnują terminów i zdejmują ciągłe odpisywanie, a pełny zysk z pobytu zostaje u właściciela. Podesłać niezobowiązująco krótkie wideo, jak to działa w praktyce?
---
{Dzień dobry | Witam serdecznie}! Tu Krzysztof. Łapię w nieco spokojniejszym momencie we wtorek z szybkim pytaniem branżowym. Czy korzystacie już z własnego modułu do rezerwacji online, czy większość rezerwacji wciąż wpada przez portale pośredniczące? Wdrażam lokalnie proste narzędzia, które pozwalają turystom rezerwować nocleg bezpośrednio z telefonu, dzięki czemu nie oddajecie kilkunastu procent prowizji od każdej doby. Mogę podrzucić link do 2-minutowego demo?
---
{Dzień dobry | Cześć}! Krzysztof z tej strony. Krótka sprawa we wtorkowe przedpołudnie. Widzę po rynku, że coraz więcej osób szuka noclegów w biegu na telefonie i woli od razu kliknąć wolny termin oraz opłacić zadatek zamiast dzwonić. Buduję dla gospodarzy proste kalendarze rezerwacji bez zbędnych komplikacji – system przyjmuje wpłaty 24/7, a pieniądze trafiają prosto na Wasze konto. Podrzucić na spokojnie krótki podgląd do zerknięcia w wolnej chwili?
---
{Dzień dobry | Witam}! Tu Krzysztof. Wtorek koło południa, więc mam nadzieję, że poranne sprawy w obiekcie już ogarnięte i jest chwila wytchnienia. Dopytam z ciekawości – macie już na swojej stronie własny system do szybkich rezerwacji, czy wciąż potwierdzacie wszystko ręcznie przez telefon? Pomagam obiektom wdrażać przejrzyste kalendarze, które automatyzują rezerwacje online, a 100% zysku zostaje w Państwa kieszeni. Podesłać krótkie nagranie z prezentacją?
---
{Dzień dobry | Cześć}! Z tej strony Krzysztof. Korzystając z luźniejszego wtorkowego przedpołudnia, pozwolę sobie zadać jedno krótkie pytanie. Czy myśleliście o wpięciu własnego kalendarza rezerwacji online, żeby goście mogli rezerwować pobyty bezpośrednio i bez prowizji portali? Przygotowuję dla kwater niezależne strony z prostym systemem rezerwacji z telefonu. Mogę podesłać krótkie wideo poglądowe do rzucenia okiem w wolnej chwili?"""

# Dostępne karty SIM:
AVAILABLE_SIMS = [
    (1, 1, "Tel 1 – SIM 1"),
    (1, 2, "Tel 1 – SIM 2"),
    (2, 1, "Tel 2 – SIM 1"),
    (3, 1, "Tel 3 – SIM 1"),
    (3, 2, "Tel 3 – SIM 2"),
]

def build_interleaved_sequence(selected_sims: list) -> list[tuple[int, int]]:
    """
    Tworzy zoptymalizowaną sekwencję kart SIM, maksymalizując odstęp między SIM-ami tego samego telefonu.
    Przyjmuje elementy w formacie (dev, sim) lub 'dev_sim'.
    """
    normalized = []
    for item in selected_sims:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            normalized.append((int(item[0]), int(item[1])))
        elif isinstance(item, str) and "_" in item:
            parts = item.split("_")
            normalized.append((int(parts[0]), int(parts[1])))
    if not normalized:
        return []
    sim1 = [c for c in normalized if c[1] == 1]
    sim2 = [c for c in normalized if c[1] == 2]
    sim1.sort(key=lambda c: c[0])
    sim2.sort(key=lambda c: c[0])
    return sim1 + sim2

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
    "sms_template": DEFAULT_TEMPLATES,
    "current_index": 0,
    "sim_step": 0,
    "turbo_step": 0,
    "selected_sims": ["1_1", "1_2", "2_1", "3_1", "3_2"],
    "delay_min": 40.5,
    "delay_max": 90.5,
    "same_phone_min": 30.0,
    "same_phone_max": 45.0,
    "diff_phone_min": 3.0,
    "diff_phone_max": 6.0,
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
            s["logs"] = s["logs"][-50:]
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
            if not state.get("sms_template"):
                state["sms_template"] = DEFAULT_TEMPLATES
            if "selected_sims" not in s:
                dev_mode = s.get("device_mode", 4)
                if dev_mode == 4:
                    state["selected_sims"] = ["1_1", "1_2", "2_1", "3_1", "3_2"]
                elif dev_mode == 1:
                    state["selected_sims"] = ["1_1", "1_2"] if s.get("auto_switch") else ["1_1"]
                elif dev_mode == 2:
                    state["selected_sims"] = ["2_1"]
                elif dev_mode == 3:
                    state["selected_sims"] = ["3_1", "3_2"] if s.get("auto_switch") else ["3_1"]
            if "sim_step" not in s:
                state["sim_step"] = s.get("turbo_step", 0)
            # Przy restarcie serwera/kontenera w Coolify, jeśli był RUNNING, ustawiamy PAUSED
            if state.get("status") == "RUNNING":
                state["status"] = "PAUSED"
                _log(f"🔄 Wczytano stan po restarcie: wiersz {state['current_index'] + 1} (PAUZA)")
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
    if context is None:
        context = {}
        
    name = context.get("name", "").strip()
    city = context.get("city", "").strip()

    def replace_var(m):
        var_name = m.group(1).lower()
        fallback = m.group(2) if m.group(2) is not None else ""
        if var_name == "name":
            return name if name else fallback
        elif var_name == "city":
            return city if city else fallback
        return m.group(0)

    text = re.sub(r'\{(Name|City)(?::([^}]*))?\}', replace_var, text, flags=re.IGNORECASE)

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

    bracket_pattern = re.compile(r'\[([^\[\]]+)\]')
    while True:
        match = bracket_pattern.search(text)
        if not match:
            break
        options = match.group(1).split('|')
        choice = (options[0] if random.random() < 0.5 else "") if len(options) == 1 else random.choice(options)
        text = text[:match.start()] + choice + text[match.end():]

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

    lines = [re.sub(r'[ \t]{2,}', ' ', l).strip() for l in text.splitlines()]
    return "\n".join(lines)

def apply_obfuscation(text: str) -> str:
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
    # withDeliveryReport: False zapobiega blokowaniu modemu DSDS przez nasłuch ACK
    payload = {
        "textMessage": {"text": text},
        "phoneNumbers": [phone],
        "simNumber": sim_number,
        "withDeliveryReport": False
    }
    username, password = CREDENTIALS.get(device_number, CREDENTIALS[1])
    try:
        resp = requests.post(
            API_URL, json=payload, auth=HTTPBasicAuth(username, password), timeout=25
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
    templates_list = [t.strip() for t in state["sms_template"].split('---') if t.strip()]
    if not templates_list:
        templates_list = [t.strip() for t in DEFAULT_TEMPLATES.split('---') if t.strip()]
    total = len(lines)
    
    selected_sims = state.get("selected_sims", [])
    active_sequence = build_interleaved_sequence(selected_sims)
    if not active_sequence:
        _log("❌ Błąd: Nie wybrano żadnej karty SIM!")
        state["status"] = "IDLE"
        save_state()
        return

    seq_len = len(active_sequence)
    seq_desc = " -> ".join([f"Tel {d} (SIM {s})" for d, s in active_sequence])
    _log(f"🚀 Start wysyłki ({seq_len} kart: {seq_desc}): {total} wierszy.")

    sim_step = state.get("sim_step", state.get("turbo_step", 0))
    last_device_send_time: dict[int, float] = {}

    while state["current_index"] < total:
        if stop_event.is_set():
            _log("🛑 Wysyłka zatrzymana.")
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
        base_tpl = random.choice(templates_list)
        text_spun = resolve_spintax(base_tpl, {"name": parsed["name"], "city": parsed["city"]})
        final_text = apply_obfuscation(text_spun)

        current_dev, sim_to_use = active_sequence[sim_step % seq_len]

        # ── BEZPIECZNY ODSTĘP MODEMU DLA TEGO SAMEGO TELEFONU ──
        if current_dev in last_device_send_time:
            elapsed = time.time() - last_device_send_time[current_dev]
            same_min = float(state.get("same_phone_min", 3.0))
            same_max = float(state.get("same_phone_max", 4.0))
            required_wait = random.uniform(same_min, same_max)
            if elapsed < required_wait:
                wait_needed = required_wait - elapsed
                _log(f"  ⏳ Tel {current_dev}: modem odpoczywa (minęło {elapsed:.1f}s, czekam jeszcze {wait_needed:.1f}s na bezpieczne przełączenie SIM)...")
                steps = int(wait_needed * 10)
                for _ in range(steps):
                    if stop_event.is_set():
                        return
                    while not pause_event.is_set():
                        if stop_event.is_set():
                            return
                        time.sleep(0.3)
                    time.sleep(0.1)

        _log(f"  📤 Wiersz {i + 1}: Wysyłam do {phone} (Tel {current_dev}, SIM {sim_to_use})...")

        success, skip_wait = send_sms_request(phone, final_text, current_dev, sim_to_use)
        last_device_send_time[current_dev] = time.time()

        if success:
            _log(f"  ✅ Wysłano do {phone}")
        else:
            _log(f"  ❌ Błąd wysyłki do {phone} (Tel {current_dev}, SIM {sim_to_use})")

        state["current_index"] += 1
        sim_step += 1
        state["sim_step"] = sim_step
        state["turbo_step"] = sim_step % seq_len
        save_state()

        if state["current_index"] < total and not stop_event.is_set():
            if skip_wait:
                _log("  ⚡ Omijam czekanie (odrzucony numer)")
                time.sleep(0.5)
                continue

            # Czy zakończono pełny cykl wszystkich zaznaczonych kart?
            if sim_step % seq_len == 0:
                d_min = float(state.get("delay_min", 20.0))
                d_max = float(state.get("delay_max", 26.0))
                delay = random.uniform(d_min, d_max)
                _log(f"  ⏳ Pełny cykl kart zakończony ({seq_len} SMS). Długa pauza: {delay:.1f}s...")
            else:
                diff_min = float(state.get("diff_phone_min", 3.0))
                diff_max = float(state.get("diff_phone_max", 6.0))
                delay = random.uniform(diff_min, diff_max)
                next_dev, next_sim = active_sequence[sim_step % seq_len]
                _log(f"  ⚡ Następna karta -> Tel {next_dev} (SIM {next_sim}). Odstęp: {delay:.1f}s...")

            steps = int(delay * 10)
            for _ in range(steps):
                if stop_event.is_set():
                    return
                while not pause_event.is_set():
                    if stop_event.is_set():
                        return
                    time.sleep(0.3)
                time.sleep(0.1)

    state["status"] = "IDLE"
    _log("🏁 Kampania zakończona!")
    save_state()


# ──────────────────────────────────────────────
# ENDPOINTY API
# ──────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={"request": request})

@app.get("/api/state")
async def get_state():
    total_lines = len([l for l in state["csv"].splitlines() if l.strip()])
    return JSONResponse({
        "status": state["status"],
        "current_index": state["current_index"],
        "total_lines": total_lines,
        "sim_step": state.get("sim_step", 0),
        "turbo_step": state.get("turbo_step", 0),
        "selected_sims": state.get("selected_sims", ["1_1", "1_2", "2_1", "3_1", "3_2"]),
        "delay_min": state["delay_min"],
        "delay_max": state["delay_max"],
        "same_phone_min": state.get("same_phone_min", 30.0),
        "same_phone_max": state.get("same_phone_max", 45.0),
        "diff_phone_min": state.get("diff_phone_min", 3.0),
        "diff_phone_max": state.get("diff_phone_max", 6.0),
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
            try: state["delay_min"] = float(data["delay_min"])
            except ValueError: pass
        if "delay_max" in data:
            try: state["delay_max"] = float(data["delay_max"])
            except ValueError: pass
        if "same_phone_min" in data:
            try: state["same_phone_min"] = float(data["same_phone_min"])
            except ValueError: pass
        if "same_phone_max" in data:
            try: state["same_phone_max"] = float(data["same_phone_max"])
            except ValueError: pass
        if "diff_phone_min" in data:
            try: state["diff_phone_min"] = float(data["diff_phone_min"])
            except ValueError: pass
        if "diff_phone_max" in data:
            try: state["diff_phone_max"] = float(data["diff_phone_max"])
            except ValueError: pass
        if "selected_sims" in data and isinstance(data["selected_sims"], list):
            state["selected_sims"] = data["selected_sims"]
    save_state()
    return {"status": "ok"}

@app.post("/api/start")
async def start_campaign():
    global worker_thread
    if state["status"] == "RUNNING":
        return {"status": "already_running"}

    lines = [l for l in state["csv"].splitlines() if l.strip()]
    templates_list = [t.strip() for t in state["sms_template"].split('---') if t.strip()]
    if not lines or not templates_list:
        return {"status": "error", "message": "Brak danych CSV lub szablonów SMS."}

    if not state.get("selected_sims"):
        return {"status": "error", "message": "Zaznacz co najmniej jedną kartę SIM do wysyłki."}

    if state["status"] == "PAUSED":
        state["status"] = "RUNNING"
        pause_event.set()
        _log("▶ Wznowiono wysyłkę.")
        if worker_thread is None or not worker_thread.is_alive():
            worker_thread = threading.Thread(target=worker_loop, daemon=True)
            worker_thread.start()
        return {"status": "ok"}

    state["current_index"] = 0
    state["sim_step"] = 0
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
        state["sim_step"] = 0
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
        state["sim_step"] = 0
        state["turbo_step"] = 0
        state["csv"] = ""
        state["sms_template"] = DEFAULT_TEMPLATES
        state["logs"] = []
    if STATE_FILE.exists():
        STATE_FILE.unlink()
    _log("🗑 Dane wyczyszczone, przywrócono domyślne szablony.")
    return {"status": "ok"}

@app.post("/api/test_spintax")
async def test_spintax(request: Request):
    data = await request.json()
    template_raw = data.get("template", "").strip()
    templates_list = [t.strip() for t in template_raw.split('---') if t.strip()]
    if not templates_list:
        return {"status": "error", "message": "Brak szablonu SMS."}
    tpl = random.choice(templates_list)
    sample_context = {"name": data.get("name", "Jan"), "city": data.get("city", "Zakopane")}
    spun = resolve_spintax(tpl, sample_context)
    obfuscated = apply_obfuscation(spun)
    return {"status": "ok", "raw_template": tpl, "spun": spun, "final": obfuscated}