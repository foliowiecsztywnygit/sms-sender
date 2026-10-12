# SMS Sender PRO - Web App (Coolify / Docker)

Aplikacja webowa do masowej wysyłki SMS przez bramki SMS-gate (3 telefony, tryb Turbo z przeplataniem 5 kart SIM, zaawansowany spintax, ochrona przed FUP).

## 🚀 Wdrożenie w Coolify

1. W panelu Coolify dodaj nowy projekt -> **Application** -> Wybierz repozytorium Git (lub Dockerfile / Docker Compose).
2. Jeśli używasz **Docker Compose**:
   - Wskaż plik `docker-compose.yml`.
   - Port: `8000`.
   - Wolumen `sms_data` zostanie automatycznie zamontowany w `/app/data`, dzięki czemu postęp i konfiguracja (`sms_state.json`) nie przepadną przy restartach czy aktualizacjach kontenera.
3. Jeśli używasz **Dockerfile**:
   - Wskaż folder `web_app`.
   - Port: `8000`.
   - Zdefiniuj Persistent Storage (np. `/app/data`).

## 💻 Uruchomienie lokalne

```bash
cd web_app
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```
Otwórz w przeglądarce: `http://localhost:8000`

## ⚙️ Kluczowe Cechy

- **Tryb Turbo (5 kart)**: Wysyła w cyklu: Tel 1 (SIM 1) -> Tel 2 (SIM 1) -> Tel 3 (SIM 1) -> Tel 1 (SIM 2) -> Tel 3 (SIM 2) z odstępem 1.0s, po czym następuje długa pauza (np. 180s - 600s), co idealnie rozkłada wysyłkę na cały dzień i chroni przed łamaniem FUP u operatorów.
- **Trwała praca w tle**: Proces działa w procesie uvicorn/fastapi bez względu na to, czy przeglądarka jest otwarta czy zamknięta.
- **Zaawansowany Spintax**:
  - Zmienne z wartością domyślną: `{Name:Kliencie}`, `{City:Twojej okolicy}`
  - Opcjonalne wstawki: `[tekst]` (50% losowej obecności) oraz `{opcja1|}`
  - Losowe kody anty-spamowe: `{rand_code:5}`, `{rand_num:10:99}`
  - Zagnieżdżone warianty: `{Dzień dobry|{Cześć|Hej}}`
  - Ochrona linków URL w tekście przed obfuskacją.
- **Wygląd i funkcjonalność**: Dokładne 1:1 odwzorowanie natywnego interfejsu desktopowego Tkinter (ciemny motyw Catppuccin Mocha), bez zbędnych atrap czy zaślepek.
