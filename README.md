# SMS Sender PRO – Samograj 24/7 🚀

Nowoczesny system do bezpiecznej i zautomatyzowanej wysyłki SMS przez bramki **SMS-gate.app**, zaprojektowany z myślą o unikaniu limitów FUP (Fair Use Policy) u operatorów oraz pełnej integracji z **Chatwoot**.

**Zasada działania:** Wrzucasz leady, zostawiasz działającą maszynę 24/7, a odpisujesz tylko na te wiadomości, które spłyną z odpowiedziami do Chatwoot.

---

## ⚡ Główne Funkcje Samograja

- **Autopilot 7 Dni w Tygodniu (Always-On):**
  Praca ciągła w tle (np. na VPS w Coolify / Docker). Po restarcie kontenera maszyna automatycznie kontynuuje pracę. Gdy skończą się kontakty, samograj czeka w gotowości i natychmiast rusza po dorzuceniu kolejnych leadów.
- **Gotowe szablony na każdy dzień tygodnia (Poniedziałek – Niedziela):**
  Zestawy po 7 wariantów na każdy z 7 dni tygodnia (49 szablonów ze spintaxem dopasowanych do poniedziałkowej kawy, środka tygodnia, piątkowego meldowania czy weekendu). Maszyna sama przełącza skrypt o północy.
- **Duże, bezpieczne odstępy czasowe:**
  Wysyłka pojedynczych SMS-ów (np. co 3–7 minut) rotacyjnie z kolejnych kart SIM. Gwarantowany odpoczynek modemu Dual SIM oraz konfigurowalny dzienny limit na kartę SIM.
- **Zarządzanie telefonami i kartami SIM na żywo:**
  Włączanie i wyłączanie kart SIM 1 kliknięciem bez przerywania pracy. Dodawanie i edycja nowych telefonów z loginem/hasłem bezpośrednio z panelu WWW.
- **Kolejka leadów i automatyczna blokada duplikatów:**
  Możliwość dorzucania kolejnych plików lub wklejania CSV w trakcie pracy maszyny. Pomyślnie wysłane numery trafiają do trwałej bazy i nigdy nie są wysyłane powtórnie.
- **Harmonogram godzinowy (Europe/Warsaw):**
  Automatyczna przerwa nocna w wyznaczonych godzinach (np. 09:00–17:30 w tygodniu i 10:00–16:00 w weekendy) i samoczynne wznawianie rano.

---

## 🚀 Wdrożenie w Coolify

1. W Coolify utwórz nową aplikację z repozytorium GitHub.
2. Wykryje automatycznie `docker-compose.yml` lub `Dockerfile`.
3. Wolumen `sms_data` zapewnia zachowanie bazy wysłanych numerów, kolejki i konfiguracji telefonów.
4. Port: `8000`.
