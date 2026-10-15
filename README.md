# SMS Sender PRO 🚀

Kompletny system do masowej i bezpiecznej wysyłki SMS przez bramki **SMS-gate.app**, zaprojektowany z myślą o unikaniu limitów FUP (Fair Use Policy) u operatorów telekomunikacyjnych oraz zaawansowanej personalizacji anty-spamowej.

Dostępny w dwóch wersjach:
1. **Desktopowa (Tkinter):** `sms_sender.py` do natywnego uruchamiania na Windows / Linux / macOS.
2. **Webowa (FastAPI + Docker):** w folderze `web_app/` przygotowana do wdrożenia w **Coolify** (działa w tle 24/7).

---

## ⚡ Główne Funkcje

- **Elastyczny wybór kart SIM (Checkboxy):**
  Możliwość bezpośredniego zaznaczenia dowolnych kart SIM spośród 5 dostępnych (Tel 1: SIM 1, SIM 2; Tel 2: SIM 1; Tel 3: SIM 1, SIM 2). Skrypt automatycznie optymalizuje kolejność, przeplatając urządzenia w bezpiecznym cyklu.
- **Inteligentna ochrona modemu (Per-Device Cooldown):**
  Gwarantowany, bezpieczny odstęp czasowy dla tego samego telefonu (pomiędzy SIM 1 a SIM 2, np. 30–45s). Zapobiega to kolizjom radiowym modemu w telefonach Dual SIM i gwarantuje 100% skuteczność wysyłki.
- **Konfigurowalne odstępy czasowe:**
  - Odstęp między różnymi telefonami (np. 3–6s)
  - Odstęp dla tego samego telefonu / między slotami SIM (np. 30–45s)
  - Długa pauza po pełnym cyklu zaznaczonych kart (np. 40–90s)
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
