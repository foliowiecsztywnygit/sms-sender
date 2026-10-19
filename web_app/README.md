# SMS Sender PRO – Samograj 24/7 🚀

System do w pełni bezobsługowej, inteligentnej wysyłki SMS działający w trybie **Autopilota 24/7 (7 dni w tygodniu)**.
Zaprojektowany z myślą o prostym modelu: **Dajesz leady, zostawiasz działającą maszynę, a odpisujesz tylko tym kontaktom, które wlecą z odpowiedzią do Chatwoot**.

---

## ⚡ Jak działa Samograj 24/7?

1. **Praca ciągła 7 dni w tygodniu (Always-On):**
   - Samograj działa w tle bez przerwy. Nawet gdy kolejka leadów się skończy, maszyna nie wyłącza się, lecz przechodzi w stan czuwania.
   - Gdy wkleisz i dorzucisz nowe kontakty, samograj **od razu automatycznie rusza dalej**.
   - Po restarcie serwera lub kontenera w Coolify, samograj automatycznie wznawia pracę bez klikania START.

2. **Dedykowane szablony na 7 dni tygodnia (Poniedziałek – Niedziela):**
   - Przygotowane **po 7 wariantów na każdy dzień tygodnia** (łącznie 49 gotowych szablonów ze spintaxem) dopasowanych kontekstowo do danego dnia (np. poniedziałkowa kawa po weekendzie, piątkowe kwaterowanie gości, sobotnie planowanie wyjazdów).
   - O północy czasu polskiego (`Europe/Warsaw`) maszyna **automatycznie przełącza zestaw szablonów na właściwy dzień tygodnia**.
   - Wygodne zakładki w panelu WWW pozwalają edytować treść każdego dnia w locie.

3. **Duże, bezpieczne odstępy (Anti-FUP & Anti-Spam):**
   - Zamiast agresywnych serii zapychających telefony, samograj wysyła **płynne pojedyncze SMS-y z dużym odstępem** (domyślnie losowo co **3 – 7 minut** między wiadomościami, z kolejnej karty SIM w rotacji).
   - Opcjonalny dzienny limit wiadomości na pojedynczą kartę SIM (np. 50 SMS/dzień).
   - Gwarantowany cooldown modemu Dual SIM (np. 45s dla tego samego telefonu).

4. **Zarządzanie telefonami i kartami SIM na żywo (Hot-Plug):**
   - 1 kliknięciem włączasz lub wyłączasz dowolną kartę SIM (SIM 1 / SIM 2) z rotacji – zmiana działa natychmiast bez resetowania procesu!
   - Dodawaj nowe telefony (login, hasło z aplikacji SMS-Gate, wybór slotów SIM) bezpośrednio z panelu WWW.
   - Przycisk `🧪 Test` na każdym slocie pozwala natychmiast sprawdzić czy dany telefon i karta wysyłają wiadomości.

5. **Inteligentna kolejka leadów i ochrona przed duplikatami:**
   - Przycisk **"➕ Dorzuć do kolejki"** pozwala wklejać kolejne paczki kontaktów CSV w trakcie działania.
   - Samograj zapisuje każdy pomyślnie wysłany numer w trwałej bazie `sent_numbers.json` – duplikaty są **automatycznie pomijane**, więc nigdy nie wyślesz oferty dwa razy do tego samego obiektu.

6. **Harmonogram godzinowy (Europe/Warsaw):**
   - Możliwość zdefiniowania okna godzinowego (np. 09:00 – 17:30 w dni robocze, 10:00 – 16:00 w weekendy).
   - Poza oknem godzinowym samograj przechodzi w tryb **automatycznej przerwy nocnej** i sam wznawia wysyłkę rano.

---

## 🚀 Uruchomienie w Coolify

1. W Coolify dodaj aplikację wskazując repozytorium GitHub.
2. Wolumen `sms_data` jest montowany do `/app/data` – stan kolejki, historia wysłanych i konfiguracja telefonów są w 100% trwałe między aktualizacjami i restartami.
3. Port aplikacji: `8000`.

## 💻 Uruchomienie lokalne

```bash
cd web_app
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```
Otwórz w przeglądarce: `http://localhost:8000`
