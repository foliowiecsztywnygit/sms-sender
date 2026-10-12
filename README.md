# SMS Sender PRO 🚀

Kompletny system do masowej i bezpiecznej wysyłki SMS przez bramki **SMS-gate.app**, zaprojektowany z myślą o unikaniu limitów FUP (Fair Use Policy) u operatorów telekomunikacyjnych oraz zaawansowanej personalizacji anty-spamowej.

Dostępny w dwóch wersjach:
1. **Desktopowa (Tkinter):** `sms_sender.py` do natywnego uruchamiania na Windows / Linux / macOS.
2. **Webowa (FastAPI + Docker):** w folderze `web_app/` przygotowana do wdrożenia w **Coolify** (działa w tle 24/7).

---

## ⚡ Główne Funkcje

- **Tryb Turbo (5 kart SIM):**
  Wysyłka sekwencyjna przeplatana po telefonach:
  $$\text{Tel 1 (SIM 1)} \longrightarrow \text{Tel 2 (SIM 1)} \longrightarrow \text{Tel 3 (SIM 1)} \longrightarrow \text{Tel 1 (SIM 2)} \longrightarrow \text{Tel 3 (SIM 2)}$$
  Z krótkim (1.0s) odstępem między urządzeniami, a po 5 SMS-ach następuje długa pauza (np. 180s - 600s), co idealnie rozkłada kampanię na cały dzień.
- **Wybór pojedynczych urządzeń:** Tel 1 (Dual SIM), Tel 2 (1 SIM), Tel 3 (Dual SIM) z obsługą wyboru i automatycznej rotacji SIM 1 / SIM 2.
- **Zaawansowany Spintax:**
  - Dynamiczne zmienne z wartościami domyślnymi: `{Name:Kliencie}`, `{City:Twojej okolicy}`
  - Zagnieżdżone warianty: `{Dzień dobry|{Cześć|Hej}}`
  - Wstawki opcjonalne: `[opcjonalny tekst]` (50% losowej obecności) oraz `{wariant|}`
  - Unikalne identyfikatory anty-spamowe: `{rand_code:5}`, `{rand_num:10:99}`
- **Bezpieczna Obfuskacja:** Subtelna podmiana polskich znaków diakrytycznych i interpunkcji, z **ochroną adresów URL** (`http://`, `https://`) przed ich uszkodzeniem.
- **Trwałość stanu:** Postęp i stan kampanii zapisywany po każdym SMS-ie w `sms_state.json`.

---

## 🚀 Wdrożenie w Coolify (1 kliknięcie)

1. W Coolify utwórz nowy projekt / zasób -> **Application** -> **Public/Private GitHub Repository**.
2. Wklej URL repozytorium: `https://github.com/foliowiecsztywnygit/sms-sender.git`.
3. Coolify automatycznie wykryje plik `docker-compose.yml`.
4. Kliknij **Deploy**.
5. Port aplikacji: `8000`. Wolumen `sms_data` dba o zachowanie bazy i postępu między restartami kontenera.
