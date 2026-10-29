#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SMS Sender PRO – SAMOGRAJ 24/7 (Autopilot 7 Dni w Tygodniu)
Wersja Webowa (FastAPI + Coolify Docker)

Funkcje Samograja:
- Praca ciągła 7 dni w tygodniu (Always-On) z automatycznym startem po restarcie kontenera
- Osobne, kontekstowe zestawy szablonów SMS (ze spintaxem) na każdy dzień tygodnia (Poniedziałek – Niedziela)
- Harmonogram godzinowy (czas polski Europe/Warsaw) z automatyczną przerwą nocną i wznowieniem rano
- Płynna wysyłka pojedynczych SMS-ów z dużymi, bezpiecznymi odstępami oraz dziennymi limitami na kartę SIM
- Zarządzanie telefonami i kartami SIM w czasie rzeczywistym (włącz/wyłącz SIM 1 kliknięciem, dodawanie/edycja/usuwanie telefonów w locie)
- Kolejka leadów z dorzucaniem w locie ("Dorzuć do kolejki") i trwałą bazą wysłanych numerów (ochrona przed duplikatami)
- Wszystkie parametry zmieniane na żywo w trakcie działania maszyny bez konieczności restartu
"""

import csv
import io
import json
import os
import random
import re
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from requests.auth import HTTPBasicAuth

# ──────────────────────────────────────────────
# STali I KONFIGURACJA PODSTAWOWA
# ──────────────────────────────────────────────
API_URL = os.environ.get("SMSGATE_API_URL", "https://smsgate-api.brosystems.pl/api/3rdparty/v1/messages")

try:
    PL_TZ = ZoneInfo("Europe/Warsaw")
except Exception:
    PL_TZ = None

DAY_NAMES_PL = {
    0: "Poniedziałek",
    1: "Wtorek",
    2: "Środa",
    3: "Czwartek",
    4: "Piątek",
    5: "Sobota",
    6: "Niedziela",
}

DEFAULT_DEVICES = [
    {
        "id": 1,
        "name": "Telefon 1 (Dual SIM)",
        "username": "MYVTZQ",
        "password": "eyjzqerafikelw",
        "sims": [
            {"slot": 1, "enabled": True, "label": "Tel 1 – SIM 1"},
            {"slot": 2, "enabled": True, "label": "Tel 1 – SIM 2"},
        ],
    },
    {
        "id": 2,
        "name": "Telefon 2 (Dual SIM)",
        "username": "JTGQYJ",
        "password": "9z9mmyzswkfdxm",
        "sims": [
            {"slot": 1, "enabled": True, "label": "Tel 2 – SIM 1"},
            {"slot": 2, "enabled": True, "label": "Tel 2 – SIM 2"},
        ],
    },
    {
        "id": 3,
        "name": "Telefon 3 (Dual SIM)",
        "username": "DQZDJ-",
        "password": "-xdgjpzxmurnns",
        "sims": [
            {"slot": 1, "enabled": True, "label": "Tel 3 – SIM 1"},
            {"slot": 2, "enabled": True, "label": "Tel 3 – SIM 2"},
        ],
    },
    {
        "id": 4,
        "name": "Telefon 4 (Dual SIM)",
        "username": "69VQFK",
        "password": "a33g_l_ml7vkw_",
        "sims": [
            {"slot": 1, "enabled": True, "label": "Tel 4 – SIM 1"},
            {"slot": 2, "enabled": True, "label": "Tel 4 – SIM 2"},
        ],
    },
    {
        "id": 5,
        "name": "Telefon 5 (Single SIM)",
        "username": "7V_QA7",
        "password": "ulat1p8gnj27lb",
        "sims": [
            {"slot": 1, "enabled": True, "label": "Tel 5 – SIM 1"},
            {"slot": 2, "enabled": False, "label": "Tel 5 – SIM 2"},
        ],
    },
]

# ──────────────────────────────────────────────
# GOTOWE SZABLONY NA 7 DNI TYGODNIA (PON – NIEDZ)
# ──────────────────────────────────────────────
DEFAULT_DAILY_TEMPLATES = {
    # 0 = PONIEDZIAŁEK
    "0": """{Dzień dobry | Witam serdecznie}! Tu Krzysztof. Poniedziałkowy poranek po weekendowych wyjazdach gości to zazwyczaj dobra chwila na spokojną kawę i podsumowanie tygodnia. Dopytam krótko z ciekawości – czy macie już u siebie własny kalendarz do bezpośrednich rezerwacji online? Wdrażam w regionie proste systemy, dzięki którym turyści sami sprawdzają terminy i rezerwują z telefonu, a 100% kwoty zostaje u Was bez prowizji dla portali. Podrzucić krótkie wideo z podglądem?
---
{Dzień dobry | Witam}! Krzysztof z tej strony. Startujemy z nowym tygodniem, więc łapię w poniedziałek z krótkim pytaniem. Czy goście mogą u Państwa zarezerwować i opłacić termin bezpośrednio przez telefon bez konieczności wcześniejszego dzwonienia? Wdrażam dla obiektów proste, bezobsługowe kalendarze działające 24/7 – cała wpłata wpada od razu na Państwa konto bez pośredników. Mogę podesłać szybkie demo do rzucenia okiem przy poniedziałkowej kawie?
---
{Dzień dobry | Cześć}! Z tej strony Krzysztof. W poniedziałek po weekendowym ruchu wreszcie można chwilę odetchnąć, zanim znów zaczną dzwonić telefony o kolejne terminy. Zastanawiałem się, czy macie już podpięty własny system rezerwacji na stronie? Uruchamiam proste kalendarze dla kwater, które same pilnują grafiku i zdejmują ciągłe odpisywanie, a pełny zysk zostaje u właściciela. Podesłać niezobowiązująco krótkie wideo, jak to działa w praktyce?
---
{Dzień dobry | Witam serdecznie}! Tu Krzysztof. Odzywam się na początku tygodnia z szybkim pytaniem branżowym. Czy korzystacie już z własnego modułu do rezerwacji online, czy większość rezerwacji wciąż wpada przez portale pobierające prowizję? Wdrażam lokalnie proste narzędzia, które pozwalają turystom rezerwować nocleg bezpośrednio ze smartfona, dzięki czemu nie oddajecie kilkunastu procent od każdej doby. Mogę podrzucić link do 2-minutowego demo?
---
{Dzień dobry | Cześć}! Krzysztof z tej strony. Krótka sprawa na start tygodnia w poniedziałek. Widzę po rynku, że po weekendzie sporo osób od razu szuka na telefonie noclegów na kolejne wyjazdy i woli kliknąć wolny termin oraz wpłacić zadatek bez dzwonienia. Buduję dla gospodarzy proste kalendarze rezerwacji – system przyjmuje wpłaty 24/7 prosto na Wasze konto. Podrzucić na spokojnie krótki podgląd do zerknięcia w wolnej chwili?
---
{Dzień dobry | Witam}! Tu Krzysztof. Poniedziałek to dobry moment na usprawnienia przed kolejnym szczytem, stąd krótkie pytanie – macie już na swojej stronie własny system do szybkich rezerwacji, czy wciąż potwierdzacie wszystko ręcznie przez telefon? Pomagam obiektom wdrażać przejrzyste kalendarze, które automatyzują rezerwacje online, a 100% zysku zostaje w Państwa kieszeni. Podesłać krótkie nagranie z prezentacją?
---
{Dzień dobry | Cześć}! Z tej strony Krzysztof. Korzystając z poniedziałkowego rozruchu w nowym tygodniu, pozwolę sobie zadać jedno pytanie. Czy myśleliście o wpięciu własnego kalendarza rezerwacji online, żeby goście mogli rezerwować pobyty bezpośrednio i bez prowizji portali? Przygotowuję dla kwater niezależne strony z prostym systemem rezerwacji z telefonu. Mogę podesłać krótkie wideo poglądowe do rzucenia okiem?""",

    # 1 = WTOREK
    "1": """{Dzień dobry | Witam serdecznie}! Tu Krzysztof. Wtorkowy poranek po weekendowym zamieszaniu to chyba wreszcie moment na spokojniejszą kawę. Dopytam krótko z ciekawości – czy macie już u siebie własny kalendarz do bezpośrednich rezerwacji online? Wdrażam w regionie proste systemy, dzięki którym turyści sami sprawdzają terminy i rezerwują z telefonu, a 100% kwoty zostaje u Was bez oddawania prowizji portalom. Podrzucić na spokojnie krótkie wideo z podglądem?
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
{Dzień dobry | Cześć}! Z tej strony Krzysztof. Korzystając z luźniejszego wtorkowego przedpołudnia, pozwolę sobie zadać jedno krótkie pytanie. Czy myśleliście o wpięciu własnego kalendarza rezerwacji online, żeby goście mogli rezerwować pobyty bezpośrednio i bez prowizji portali? Przygotowuję dla kwater niezależne strony z prostym systemem rezerwacji z telefonu. Mogę podesłać krótkie wideo poglądowe do rzucenia okiem w wolnej chwili?""",

    # 2 = ŚRODA
    "2": """{Dzień dobry | Witam serdecznie}! Tu Krzysztof. Mamy środek tygodnia, więc łapię w środę z krótkim pytaniem, zanim zacznie się główne zamieszanie przed weekendem. Czy macie już u siebie własny kalendarz do bezpośrednich rezerwacji online? Wdrażam w regionie proste systemy, dzięki którym turyści sami sprawdzają wolne dni i rezerwują z telefonu, a 100% kwoty zostaje u Was bez prowizji dla portali. Podrzucić krótkie wideo z podglądem?
---
{Dzień dobry | Witam}! Krzysztof z tej strony. Odzywam się w środę przy kawie z szybkim pytaniem. Czy goście mogą u Państwa zarezerwować i opłacić pobyt bezpośrednio przez telefon bez wcześniejszego dzwonienia? Wdrażam dla obiektów proste, bezobsługowe kalendarze działające 24/7 – cała wpłata trafia od razu na Państwa konto bez pośredników. Mogę podesłać szybkie demo do rzucenia okiem w wolnej chwili?
---
{Dzień dobry | Cześć}! Z tej strony Krzysztof. Środa to zazwyczaj moment, kiedy zaczynają się pierwsze telefony z pytaniami o nadchodzący weekend. Zastanawiałem się, czy macie już podpięty własny system rezerwacji online? Uruchamiam proste kalendarze dla kwater, które same pilnują dostępności i zdejmują z głowy ciągłe odpisywanie, a pełny zysk zostaje u właściciela. Podesłać niezobowiązująco krótkie wideo, jak to działa?
---
{Dzień dobry | Witam serdecznie}! Tu Krzysztof. Łapię w środku tygodnia z krótkim pytaniem branżowym. Czy korzystacie już z własnego modułu do rezerwacji online, czy większość rezerwacji nadal wpada przez portale pośredniczące? Wdrażam lokalnie proste narzędzia, które pozwalają turystom rezerwować nocleg bezpośrednio ze smartfona, dzięki czemu nie oddajecie kilkunastu procent prowizji. Mogę podrzucić link do 2-minutowego demo?
---
{Dzień dobry | Cześć}! Krzysztof z tej strony. Krótka sprawa w środowe przedpołudnie. W połowie tygodnia najwięcej osób planuje wyjazdy na telefonie i woli od razu kliknąć wolny termin oraz wpłacić zadatek zamiast dzwonić. Buduję dla gospodarzy proste kalendarze rezerwacji – system przyjmuje wpłaty 24/7 prosto na Wasze konto. Podrzucić na spokojnie krótki podgląd do zerknięcia?
---
{Dzień dobry | Witam}! Tu Krzysztof. Środek tygodnia w pełni, mam nadzieję, że chwila na spokojną kawę się znajdzie. Dopytam z ciekawości – macie już na swojej stronie własny system do szybkich rezerwacji, czy wciąż potwierdzacie terminy ręcznie przez telefon? Pomagam obiektom wdrażać przejrzyste kalendarze, które automatyzują rezerwacje online, a 100% zysku zostaje u Państwa. Podesłać krótkie nagranie z prezentacją?
---
{Dzień dobry | Cześć}! Z tej strony Krzysztof. Korzystając ze środowego rytmu pracy, pozwolę sobie zadać jedno krótkie pytanie. Czy myśleliście o wpięciu własnego kalendarza rezerwacji online, żeby goście mogli rezerwować pobyty bezpośrednio i bez prowizji portali? Przygotowuję dla kwater niezależne strony z prostym systemem rezerwacji z telefonu. Mogę podesłać krótkie wideo poglądowe?""",

    # 3 = CZWARTEK
    "3": """{Dzień dobry | Witam serdecznie}! Tu Krzysztof. Czwartek to zazwyczaj ostatni spokojniejszy moment przed weekendowym najazdem gości, więc dopytam krótko z ciekawości – czy macie już u siebie własny kalendarz do bezpośrednich rezerwacji online? Wdrażam w regionie proste systemy, dzięki którym turyści sami sprawdzają terminy i rezerwują z telefonu, a 100% kwoty zostaje u Was bez prowizji dla portali. Podrzucić krótkie wideo z podglądem?
---
{Dzień dobry | Witam}! Krzysztof z tej strony. Łapię w czwartek z szybkim pytaniem, zanim ruszą pełne przygotowania na weekend. Czy goście mogą u Państwa zarezerwować i opłacić termin bezpośrednio przez telefon bez konieczności dzwonienia? Wdrażam dla obiektów proste, bezobsługowe kalendarze działające 24/7 – cała wpłata wpada od razu na Państwa konto bez pośredników. Mogę podesłać szybkie demo do rzucenia okiem?
---
{Dzień dobry | Cześć}! Z tej strony Krzysztof. W czwartek pewnie telefony o wolne miejsca na weekend dzwonią już coraz częściej. Zastanawiałem się, czy macie już podpięty własny system rezerwacji na stronie? Uruchamiam proste kalendarze dla kwater, które same pilnują terminów i przyjmują zadatki, dzięki czemu nie trzeba wisieć na telefonie, a pełny zysk zostaje u właściciela. Podesłać niezobowiązująco krótkie wideo, jak to działa?
---
{Dzień dobry | Witam serdecznie}! Tu Krzysztof. Odzywam się w czwartek z szybkim pytaniem branżowym. Czy korzystacie już z własnego modułu do rezerwacji online, czy większość rezerwacji wciąż wpada przez portale pośredniczące? Wdrażam lokalnie proste narzędzia, które pozwalają turystom rezerwować nocleg bezpośrednio z telefonu, bez oddawania kilkunastu procent prowizji od każdej doby. Mogę podrzucić link do 2-minutowego demo?
---
{Dzień dobry | Cześć}! Krzysztof z tej strony. Krótka sprawa w czwartkowe przedpołudnie. Przed samym weekendem mnóstwo osób szuka noclegów na ostatnią chwilę w telefonie i woli od razu kliknąć wolny termin oraz opłacić zadatek zamiast dzwonić. Buduję dla gospodarzy proste kalendarze rezerwacji – system przyjmuje wpłaty 24/7 prosto na Wasze konto. Podrzucić na spokojnie krótki podgląd do zerknięcia w wolnej chwili?
---
{Dzień dobry | Witam}! Tu Krzysztof. Czwartek w pełni, pewnie przygotowania obiektu na jutrzejszych gości idą pełną parą. Dopytam krótko – macie już na swojej stronie własny system do szybkich rezerwacji, czy wciąż potwierdzacie wszystko ręcznie przez telefon? Pomagam obiektom wdrażać przejrzyste kalendarze, które automatyzują rezerwacje online, a 100% zysku zostaje w Państwa kieszeni. Podesłać krótkie nagranie z prezentacją?
---
{Dzień dobry | Cześć}! Z tej strony Krzysztof. Zanim zacznie się weekendowy ruch, pozwolę sobie w czwartek zadać jedno krótkie pytanie. Czy myśleliście o wpięciu własnego kalendarza rezerwacji online, żeby goście mogli rezerwować pobyty bezpośrednio i bez prowizji portali? Przygotowuję dla kwater niezależne strony z prostym systemem rezerwacji z telefonu. Mogę podesłać krótkie wideo poglądowe do rzucenia okiem?""",

    # 4 = PIĄTEK
    "4": """{Dzień dobry | Witam serdecznie}! Tu Krzysztof. Piątek to początek weekendowego ruchu, więc nie zajmuję dużo czasu – dopytam tylko krótko: czy macie już u siebie własny kalendarz do bezpośrednich rezerwacji online? Wdrażam w regionie proste systemy, dzięki którym turyści sami sprawdzają terminy i rezerwują z telefonu, a 100% kwoty zostaje u Was bez oddawania prowizji portalom. Podrzucić krótkie wideo do zerknięcia w wolnej chwili?
---
{Dzień dobry | Witam}! Krzysztof z tej strony. Wiem, że w piątek przyjazdów gości potrafi być sporo, więc zapytam jednym zdaniem. Czy turyści mogą u Państwa zarezerwować i opłacić termin bezpośrednio przez telefon bez wcześniejszego dzwonienia? Wdrażam dla obiektów proste, bezobsługowe kalendarze działające 24/7 – cała wpłata wpada od razu na Państwa konto bez pośredników. Mogę podesłać szybkie demo na spokojniejszy moment?
---
{Dzień dobry | Cześć}! Z tej strony Krzysztof. W piątek przy kwaterowaniu gości trudno odbierać każdy telefon z pytaniem o wolne terminy na kolejne tygodnie. Zastanawiałem się, czy macie już podpięty własny system rezerwacji na stronie? Uruchamiam proste kalendarze dla kwater, które same pilnują grafiku i przyjmują rezerwacje 24/7, a pełny zysk zostaje u właściciela. Podesłać niezobowiązująco krótkie wideo, jak to działa w praktyce?
---
{Dzień dobry | Witam serdecznie}! Tu Krzysztof. Łapię w piątek z krótkim pytaniem branżowym. Czy korzystacie już z własnego modułu do rezerwacji online, czy większość rezerwacji wciąż wpada przez portale pośredniczące? Wdrażam lokalnie proste narzędzia, które pozwalają turystom rezerwować nocleg bezpośrednio z telefonu, dzięki czemu nie oddajecie kilkunastu procent prowizji od każdej doby. Mogę podrzucić link do 2-minutowego demo?
---
{Dzień dobry | Cześć}! Krzysztof z tej strony. Krótka piątkowa wiadomość. W weekendy ludzie najczęściej przeglądają oferty noclegów na smartfonach i wolą od razu kliknąć wolny termin oraz wpłacić zadatek zamiast dzwonić. Buduję dla gospodarzy proste kalendarze rezerwacji – system przyjmuje wpłaty 24/7 prosto na Wasze konto. Podrzucić na spokojnie krótki podgląd do zerknięcia po piątkowym zamieszaniu?
---
{Dzień dobry | Witam}! Tu Krzysztof. Piątek w pełni, więc życzę udanego weekendu z gośćmi i dopytam przy okazji – macie już na swojej stronie własny system do szybkich rezerwacji, czy wciąż potwierdzacie wszystko ręcznie przez telefon? Pomagam obiektom wdrażać przejrzyste kalendarze, które automatyzują rezerwacje online, a 100% zysku zostaje w Państwa kieszeni. Podesłać krótkie nagranie z prezentacją?
---
{Dzień dobry | Cześć}! Z tej strony Krzysztof. Na koniec tygodnia roboczego pozwolę sobie zadać jedno krótkie pytanie. Czy myśleliście o wpięciu własnego kalendarza rezerwacji online, żeby goście mogli rezerwować pobyty bezpośrednio i bez prowizji portali? Przygotowuję dla kwater niezależne strony z prostym systemem rezerwacji z telefonu. Mogę podesłać krótkie wideo poglądowe do rzucenia okiem w wolnej chwili?""",

    # 5 = SOBOTA
    "5": """{Dzień dobry | Witam serdecznie}! Tu Krzysztof. Piszę krótko w sobotę, żeby nie przeszkadzać telefonem w trakcie weekendu. Dopytam tylko z ciekawości – czy macie już u siebie własny kalendarz do bezpośrednich rezerwacji online? Wdrażam w regionie proste systemy, dzięki którym turyści sami sprawdzają terminy i rezerwują z telefonu, a 100% kwoty zostaje u Was bez prowizji dla portali. Podrzucić krótkie wideo do zerknięcia w wolnej chwili?
---
{Dzień dobry | Witam}! Krzysztof z tej strony. Sobotnie przedpołudnie to czas, kiedy wielu turystów planuje kolejne wyjazdy z telefonu, dlatego zapytam krótko: czy goście mogą u Państwa zarezerwować i opłacić termin bezpośrednio online bez dzwonienia? Wdrażam dla obiektów proste, bezobsługowe kalendarze działające 24/7 – cała wpłata trafia od razu na Państwa konto bez pośredników. Mogę podesłać szybkie demo do rzucenia okiem?
---
{Dzień dobry | Cześć}! Z tej strony Krzysztof. W sobotę każdy woli odpocząć od ciągłego odbierania telefonów z pytaniami o wolne terminy. Zastanawiałem się, czy macie już podpięty własny system rezerwacji na stronie? Uruchamiam proste kalendarze dla kwater, które same pilnują terminów przez cały weekend i przyjmują zadatki, a pełny zysk zostaje u właściciela. Podesłać niezobowiązująco krótkie wideo, jak to działa?
---
{Dzień dobry | Witam serdecznie}! Tu Krzysztof. Odzywam się w sobotę z krótkim pytaniem branżowym na spokojną chwilę. Czy korzystacie już z własnego modułu do rezerwacji online, czy większość weekendowych rezerwacji wpada przez portale pośredniczące? Wdrażam lokalnie proste narzędzia, które pozwalają turystom rezerwować nocleg bezpośrednio ze smartfona, bez oddawania kilkunastu procent prowizji. Mogę podrzucić link do 2-minutowego demo?
---
{Dzień dobry | Cześć}! Krzysztof z tej strony. Krótka sobotnia sprawa. Statystyki pokazują, że w weekendy najwięcej rodzin szuka noclegów na kolejne tygodnie i woli od razu kliknąć wolny termin w telefonie niż dzwonić. Buduję dla gospodarzy proste kalendarze rezerwacji – system sam przyjmuje wpłaty 24/7 prosto na Wasze konto. Podrzucić na spokojnie krótki podgląd do zerknięcia przy weekendowej kawie?
---
{Dzień dobry | Witam}! Tu Krzysztof. Spokojnej soboty życzę i przy okazji dopytam krótko – macie już na swojej stronie własny system do szybkich rezerwacji, czy wciąż potwierdzacie wszystko ręcznie przez telefon? Pomagam obiektom wdrażać przejrzyste kalendarze, które automatyzują rezerwacje online również w weekendy, a 100% zysku zostaje u Państwa. Podesłać krótkie nagranie z prezentacją?
---
{Dzień dobry | Cześć}! Z tej strony Krzysztof. Korzystając z soboty, zostawiam krótką wiadomość do odczytania w wolnej chwili. Czy myśleliście o wpięciu własnego kalendarza rezerwacji online, żeby goście mogli rezerwować pobyty bezpośrednio i bez prowizji portali? Przygotowuję dla kwater niezależne strony z prostym systemem rezerwacji z telefonu. Mogę podesłać krótkie wideo poglądowe?""",

    # 6 = NIEDZIELA
    "6": """{Dzień dobry | Witam serdecznie}! Tu Krzysztof. Piszę spokojnie SMS-em w niedzielę, żeby nie zawracać głowy telefonem w weekend. Dopytam krótko na nowy tydzień – czy macie już u siebie własny kalendarz do bezpośrednich rezerwacji online? Wdrażam w regionie proste systemy, dzięki którym turyści sami sprawdzają terminy i rezerwują z telefonu, a 100% kwoty zostaje u Was bez prowizji dla portali. Podrzucić krótkie wideo do zerknięcia w wolnej chwili?
---
{Dzień dobry | Witam}! Krzysztof z tej strony. Niedziela po wymeldowaniach gości to często moment, kiedy turyści szukają noclegów na kolejne tygodnie. Zapytam krótko: czy goście mogą u Państwa zarezerwować i opłacić termin bezpośrednio przez telefon bez dzwonienia? Wdrażam dla obiektów proste, bezobsługowe kalendarze działające 24/7 – cała wpłata trafia od razu na Państwa konto. Mogę podesłać szybkie demo do rzucenia okiem?
---
{Dzień dobry | Cześć}! Z tej strony Krzysztof. W niedzielne popołudnie najwięcej osób siedzi z telefonem i planuje kolejne wyjazdy. Zastanawiałem się, czy macie już podpięty własny system rezerwacji na stronie, który sam przyjmuje rezerwacje, gdy Wy odpoczywacie? Uruchamiam proste kalendarze dla kwater, które zdejmują ciągłe odpisywanie, a pełny zysk zostaje u właściciela. Podesłać niezobowiązująco krótkie wideo, jak to działa?
---
{Dzień dobry | Witam serdecznie}! Tu Krzysztof. Zostawiam krótkie pytanie w niedzielę do odczytania w dogodnej chwili. Czy korzystacie już z własnego modułu do rezerwacji online, czy większość rezerwacji wciąż wpada przez portale pośredniczące? Wdrażam lokalnie proste narzędzia, które pozwalają turystom rezerwować nocleg bezpośrednio z telefonu, bez oddawania kilkunastu procent prowizji. Mogę podrzucić link do 2-minutowego demo?
---
{Dzień dobry | Cześć}! Krzysztof z tej strony. Krótka niedzielna wiadomość przed startem nowego tygodnia. Coraz więcej gości szuka noclegów w niedzielę wieczorem na smartfonie i woli od razu kliknąć wolny termin oraz wpłacić zadatek zamiast czekać z telefonem do poniedziałku. Buduję dla gospodarzy proste kalendarze rezerwacji działające 24/7. Podrzucić na spokojnie krótki podgląd do zerknięcia?
---
{Dzień dobry | Witam}! Tu Krzysztof. Spokojnej niedzieli życzę! Dopytam przy okazji na spokojnie – macie już na swojej stronie własny system do szybkich rezerwacji, czy wciąż potwierdzacie wszystko ręcznie przez telefon? Pomagam obiektom wdrażać przejrzyste kalendarze, które automatyzują rezerwacje online 7 dni w tygodniu, a 100% zysku zostaje w Państwa kieszeni. Podesłać krótkie nagranie z prezentacją?
---
{Dzień dobry | Cześć}! Z tej strony Krzysztof. Zostawiam niezobowiązującą wiadomość w niedzielę. Czy myśleliście o wpięciu własnego kalendarza rezerwacji online, żeby goście mogli rezerwować pobyty bezpośrednio i bez prowizji portali? Przygotowuję dla kwater niezależne strony z prostym systemem rezerwacji z telefonu. Mogę podesłać krótkie wideo poglądowe do rzucenia okiem w wolnej chwili?""",
}


# ──────────────────────────────────────────────
# ŚCIEŻKI DANYCH (TRWAŁY WOLUMEN COOLIFY)
# ──────────────────────────────────────────────
DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).resolve().parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = DATA_DIR / "sms_state.json"
SENT_NUMBERS_FILE = DATA_DIR / "sent_numbers.json"

BASE_DIR = Path(__file__).resolve().parent


def now_pl() -> datetime:
    if PL_TZ is not None:
        return datetime.now(PL_TZ)
    return datetime.now()


# ──────────────────────────────────────────────
# STAN APLIKACJI I BAZA WYSŁANYCH NUMERÓW
# ──────────────────────────────────────────────
state = {
    "status": "IDLE",               # IDLE, RUNNING, PAUSED
    "worker_phase": "IDLE",         # IDLE, SENDING, WAITING_INTERVAL, NIGHT_SLEEP, WAITING_FOR_LEADS, DAILY_LIMIT_REACHED, NO_ACTIVE_SIM
    "worker_phase_detail": "Gotowy do pracy",
    "next_send_at": 0.0,            # Timestamp kolejnej wysyłki (do odliczania na żywo)
    "csv_queue": "",                # Kolejka oczekujących wierszy CSV (linia 1 = następny do wysyłki)
    "daily_templates": DEFAULT_DAILY_TEMPLATES.copy(),
    "devices": json.loads(json.dumps(DEFAULT_DEVICES)),
    "sim_step": 0,
    # Odstępy czasowe (domyślnie duże odstępy dla samograja: 180s - 420s = 3 - 7 minut między SMS)
    "interval_min": 180.0,
    "interval_max": 420.0,
    "same_phone_cooldown": 45.0,
    "daily_limit_per_sim": 50,      # 0 = brak limitu
    # Harmonogram dobowy i tygodniowy
    "schedule_enabled": True,
    "workdays_start": "09:00",
    "workdays_end": "17:30",
    "weekend_start": "10:00",
    "weekend_end": "16:00",
    "active_days": [0, 1, 2, 3, 4, 5, 6],
    # Opcje anty-spam i duplikaty
    "obfuscation_enabled": True,
    "skip_duplicates": True,
    "smart_greeting_enabled": True,  # Automatyczny dobór: Dzień dobry (w dzień) / Dobry wieczór (od 17:00)
    # Statystyki dzienne i całkowite
    "stats_date": "",
    "sent_today_total": 0,
    "sent_today_per_sim": {},       # np. {"1_1": 12, "1_2": 11}
    "sent_total_all_time": 0,
    "failed_today": 0,
    "last_sent_info": None,         # {"time": ..., "phone": ..., "name": ..., "sim": ...}
    "logs": [],
}

sent_numbers_set: set[str] = set()

worker_thread: threading.Thread | None = None
stop_event = threading.Event()
skip_wait_event = threading.Event()
state_lock = threading.RLock()


def _log(msg: str):
    ts = now_pl().strftime("%H:%M:%S")
    entry = f"[{ts}] {msg}"
    with state_lock:
        state["logs"].append(entry)
        if len(state["logs"]) > 400:
            state["logs"] = state["logs"][-400:]


def load_sent_numbers():
    global sent_numbers_set
    if not SENT_NUMBERS_FILE.exists():
        sent_numbers_set = set()
        return
    try:
        data = json.loads(SENT_NUMBERS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            sent_numbers_set = set(str(x) for x in data)
        elif isinstance(data, dict) and "numbers" in data:
            sent_numbers_set = set(str(x) for x in data["numbers"])
    except Exception as e:
        print(f"Błąd odczytu sent_numbers.json: {e}")


def save_sent_numbers():
    try:
        with state_lock:
            nums = sorted(sent_numbers_set)
        SENT_NUMBERS_FILE.write_text(
            json.dumps({"count": len(nums), "numbers": nums}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        print(f"Błąd zapisu sent_numbers.json: {e}")


def check_and_roll_daily_stats():
    today_str = now_pl().strftime("%Y-%m-%d")
    with state_lock:
        if state.get("stats_date") != today_str:
            old_date = state.get("stats_date")
            state["stats_date"] = today_str
            state["sent_today_total"] = 0
            state["sent_today_per_sim"] = {}
            state["failed_today"] = 0
            if old_date:
                _log(f"📅 Nowy dzień ({today_str} – {DAY_NAMES_PL[now_pl().weekday()]})! Zresetowano dzienne liczniki kart SIM.")
                save_state()


def save_state():
    with state_lock:
        try:
            s = state.copy()
            s["logs"] = s["logs"][-120:]
            STATE_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"Błąd zapisu stanu: {e}")


def load_state():
    load_sent_numbers()
    if not STATE_FILE.exists():
        state["stats_date"] = now_pl().strftime("%Y-%m-%d")
        return
    try:
        s = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        with state_lock:
            # Migracja ze starszej wersji sms_state.json (jeśli istniała)
            if "csv_queue" not in s and "csv" in s:
                old_lines = [l for l in s.get("csv", "").splitlines() if l.strip()]
                old_idx = int(s.get("current_index", 0))
                s["csv_queue"] = "\n".join(old_lines[old_idx:])

            if "interval_min" not in s and "delay_min" in s:
                # Jeśli ktoś miał stare ustawienia, ale przechodzi na samograj, zachowajmy sensowne minimum lub domyślne 180-420
                pass

            for k, v in s.items():
                if k in state:
                    state[k] = v

            # Upewnij się, że wszystkie 7 dni tygodnia mają szablony
            if not isinstance(state.get("daily_templates"), dict):
                state["daily_templates"] = DEFAULT_DAILY_TEMPLATES.copy()
            else:
                for day_idx in range(7):
                    dk = str(day_idx)
                    if not state["daily_templates"].get(dk, "").strip():
                        state["daily_templates"][dk] = DEFAULT_DAILY_TEMPLATES[dk]

            # Migracja / walidacja listy urządzeń
            if not state.get("devices") or not isinstance(state["devices"], list):
                state["devices"] = json.loads(json.dumps(DEFAULT_DEVICES))
                if "selected_sims" in s and isinstance(s["selected_sims"], list):
                    sel = set(s["selected_sims"])
                    for dev in state["devices"]:
                        for sim in dev["sims"]:
                            sim["enabled"] = f"{dev['id']}_{sim['slot']}" in sel

            check_and_roll_daily_stats()
            if state["sent_total_all_time"] < len(sent_numbers_set):
                state["sent_total_all_time"] = len(sent_numbers_set)

            q_len = len([l for l in state["csv_queue"].splitlines() if l.strip()])
            _log(f"🔄 Wczytano stan systemu (W kolejce: {q_len} leadów | Status: {state['status']})")
    except Exception as e:
        print(f"Błąd odczytu stanu: {e}")


# ──────────────────────────────────────────────
# PARSOWANIE CSV I NUMERÓW TELEFONU
# ──────────────────────────────────────────────
def extract_phone(row_text: str) -> str | None:
    text = re.sub(r"\.0\b", "", row_text)
    matches = re.finditer(r"\+?[\d\s\-]{9,20}", text)
    for match in matches:
        digits = re.sub(r"[\s\-]", "", match.group())
        if re.match(r"^\+?\d+$", digits):
            if digits.startswith("+48") and len(digits) == 12:
                return digits
            elif digits.startswith("48") and len(digits) == 11:
                return f"+{digits}"
            elif len(digits) == 9:
                return f"+48{digits}"
    return None


def parse_csv_line(line: str) -> dict | None:
    raw = line.strip()
    if not raw:
        return None
    try:
        reader = csv.reader(io.StringIO(raw))
        parts = next(reader)
    except StopIteration:
        return None
    except Exception:
        parts = [p.strip() for p in raw.split(",")]

    if not parts:
        return None

    # Obsługa sytuacji, gdy ktoś wklei sam numer telefonu w linii
    if len(parts) == 1:
        phone = extract_phone(parts[0])
        if phone:
            return {"name": "", "city": "", "phone": phone}
        return None

    name = parts[0].strip()
    city = (
        parts[1].strip()
        if len(parts) > 1 and parts[1].strip()
        else (parts[2].strip() if len(parts) > 2 else "")
    )

    phone = None
    for part in parts:
        text = re.sub(r"\.0$", "", part.strip())
        digits = re.sub(r"[\s\-]", "", text)
        if re.match(r"^\+?\d+$", digits):
            if digits.startswith("+48") and len(digits) == 12:
                phone = digits
                break
            elif digits.startswith("48") and len(digits) == 11:
                phone = f"+{digits}"
                break
            elif len(digits) == 9:
                phone = f"+48{digits}"
                break

    if not phone:
        phone = extract_phone(raw)

    # Jeśli w polu city przypadkiem złapał się sam numer telefonu, wyczyść city
    if city and extract_phone(city) == phone and re.sub(r"[\s\-\+]", "", city).isdigit():
        city = ""

    return {"name": name, "city": city, "phone": phone}


# ──────────────────────────────────────────────
# INTELIGENTNE POWITANIA I ADAPTACJA DO PORY DNIA
# ──────────────────────────────────────────────
DAYS_STEMS = {
    "poniedziałek": ("poniedziałkowy", "poniedziałkowe", "poniedziałkowym"),
    "wtorek": ("wtorkowy", "wtorkowe", "wtorkowym"),
    "środa": ("środowy", "środowe", "środowym"),
    "czwartek": ("czwartkowy", "czwartkowe", "czwartkowym"),
    "piątek": ("piątkowy", "piątkowe", "piątkowym"),
    "sobota": ("sobotni", "sobotnie", "sobotnim"),
    "niedziela": ("niedzielny", "niedzielne", "niedzielnym"),
}

def get_time_of_day_context(dt: datetime | None = None) -> dict:
    if dt is None:
        dt = now_pl()
    hour = dt.hour
    minute = dt.minute
    total_min = hour * 60 + minute

    # Rano: do 12:00, Popołudnie: 12:00 - 17:00, Wieczór: od 17:00
    if total_min < 12 * 60:
        greetings = ["Dzień dobry", "Witam serdecznie", "Witam", "Cześć"]
        pora_dnia = "przedpołudnie"
        pora_opis = "poranek"
    elif total_min < 17 * 60:
        greetings = ["Dzień dobry", "Witam serdecznie", "Witam", "Cześć"]
        pora_dnia = "popołudnie"
        pora_opis = "popołudnie"
    else:
        # Od 17:00 (wieczór)
        greetings = ["Dobry wieczór", "Witam serdecznie", "Witam", "Cześć"]
        pora_dnia = "wieczór"
        pora_opis = "wieczór"

    return {
        "dt": dt,
        "hour": hour,
        "is_evening": total_min >= 17 * 60,
        "is_afternoon": 12 * 60 <= total_min < 17 * 60,
        "greetings": greetings,
        "greeting": random.choice(greetings),
        "pora_dnia": pora_dnia,
        "pora_opis": pora_opis,
    }


def adapt_time_of_day(text: str, dt: datetime | None = None) -> str:
    """
    Automatycznie dostosowuje powitania i kontekstowe pory dnia w tekście:
    - Od 17:00: zamienia 'Dzień dobry' na 'Dobry wieczór' oraz 'poranek'/'przedpołudnie' na 'wieczór'.
    - Przed 17:00: zamienia ewentualny 'Dobry wieczór' na 'Dzień dobry'.
    - W godzinach popołudniowych (12:00-17:00): zamienia zwroty poranne na 'popołudnie'.
    """
    tod = get_time_of_day_context(dt)
    is_evening = tod["is_evening"]
    is_afternoon = tod["is_afternoon"]

    def _replace_keep_case(pattern: str, replacement: str, string: str) -> str:
        def _cb(m):
            matched = m.group(0)
            rep = replacement
            if matched and matched[0].isupper():
                rep = rep[0].upper() + rep[1:]
            return rep
        return re.sub(pattern, _cb, string, flags=re.IGNORECASE)

    # 1. Adaptacja bezpośrednich powitań
    if is_evening:
        text = _replace_keep_case(r"\b[Dd]zień dobry\b", "Dobry wieczór", text)
    else:
        text = _replace_keep_case(r"\b[Dd]obry wieczór\b", "Dzień dobry", text)

    # 2. Zwroty z dniami tygodnia (np. wtorkowy poranek -> wtorkowy wieczór)
    for _, (masc, neut, _) in DAYS_STEMS.items():
        if is_evening:
            text = _replace_keep_case(rf"\b{masc}\s+poranek\b", f"{masc} wieczór", text)
            text = _replace_keep_case(rf"\bwe?\s+{neut}\s+przedpołudnie\b", f"w ten {masc} wieczór", text)
            text = _replace_keep_case(rf"\b{neut}\s+przedpołudnie\b", f"{masc} wieczór", text)
            text = _replace_keep_case(rf"\b{neut}\s+popołudnie\b", f"{masc} wieczór", text)
        elif is_afternoon:
            text = _replace_keep_case(rf"\b{masc}\s+poranek\b", f"{neut} popołudnie", text)
            text = _replace_keep_case(rf"\bwe?\s+{neut}\s+przedpołudnie\b", f"w {neut} popołudnie", text)
            text = _replace_keep_case(rf"\b{neut}\s+przedpołudnie\b", f"{neut} popołudnie", text)

    if is_evening:
        text = _replace_keep_case(r"\b(o|około|koło)\s+południa\b", "wieczorem", text)
        text = _replace_keep_case(r"\bwe?\s+przedpołudnie\b", "wieczorem", text)
        text = _replace_keep_case(r"\bporann(e|ych)\s+sprawy\b", "dzisiejsze sprawy", text)
        text = _replace_keep_case(r"\bporanną kawę\b", "wieczorną herbatę", text)
        text = _replace_keep_case(r"\bprzy kawie\b", "wieczorem", text)
    elif is_afternoon:
        text = _replace_keep_case(r"\bporann(e|ych)\s+sprawy\b", "dzisiejsze sprawy", text)
        text = _replace_keep_case(r"\bporanną kawę\b", "popołudniową kawę", text)

    return text


# ──────────────────────────────────────────────
# ZAAWANSOWANY SPINTAX I BEZPIECZNA OBFUSKACJA
# ──────────────────────────────────────────────
def resolve_spintax(text: str, context: dict | None = None) -> str:
    if context is None:
        context = {}

    name = context.get("name", "").strip()
    city = context.get("city", "").strip()
    dt = context.get("dt") or now_pl()
    tod = get_time_of_day_context(dt)

    def replace_var(m):
        var_name = m.group(1).lower()
        fallback = m.group(2) if m.group(2) is not None else ""
        if var_name == "name":
            return name if name else fallback
        elif var_name == "city":
            return city if city else fallback
        return m.group(0)

    text = re.sub(r"\{(Name|City)(?::([^}]*))?\}", replace_var, text, flags=re.IGNORECASE)

    # Dynamiczne tagi pory dnia i powitania: {Powitanie}, {Greeting}, {Pora_dnia}, {Pora_opis}
    text = re.sub(r"\{(Powitanie|Greeting)\}", lambda m: tod["greeting"], text, flags=re.IGNORECASE)
    text = re.sub(r"\{(Pora_dnia|Time_of_day)\}", lambda m: tod["pora_dnia"], text, flags=re.IGNORECASE)
    text = re.sub(r"\{(Pora_opis)\}", lambda m: tod["pora_opis"], text, flags=re.IGNORECASE)

    def replace_rand_num(m):
        try:
            return str(random.randint(int(m.group(1)), int(m.group(2))))
        except Exception:
            return m.group(0)

    text = re.sub(r"\{rand_num:(\d+):(\d+)\}", replace_rand_num, text, flags=re.IGNORECASE)

    def replace_rand_code(m):
        try:
            length = int(m.group(1))
            chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
            return "".join(random.choice(chars) for _ in range(length))
        except Exception:
            return m.group(0)

    text = re.sub(r"\{rand_code:(\d+)\}", replace_rand_code, text, flags=re.IGNORECASE)

    bracket_pattern = re.compile(r"\[([^\[\]]+)\]")
    while True:
        match = bracket_pattern.search(text)
        if not match:
            break
        options = match.group(1).split("|")
        choice = (
            (options[0] if random.random() < 0.5 else "")
            if len(options) == 1
            else random.choice(options)
        )
        text = text[: match.start()] + choice + text[match.end() :]

    pattern = re.compile(r"\{([^{}]+)\}")
    loops = 0
    while loops < 100:
        match = pattern.search(text)
        if not match:
            break
        options = [opt.strip() for opt in match.group(1).split("|")]
        choice = random.choice(options)
        text = text[: match.start()] + choice + text[match.end() :]
        loops += 1

    lines = [re.sub(r"[ \t]{2,}", " ", l).strip() for l in text.splitlines()]
    result = "\n".join(lines)

    # Automatyczna adaptacja powitań i pory dnia (jeśli opcja włączona)
    smart_greeting = context.get("smart_greeting", state.get("smart_greeting_enabled", True))
    if smart_greeting:
        result = adapt_time_of_day(result, dt)

    return result


def apply_obfuscation(text: str) -> str:
    url_pattern = re.compile(r"https?://[^\s]+")
    urls = []

    def save_url(m):
        urls.append(m.group(0))
        return f"__URL_{len(urls)-1}__"

    text_safe = url_pattern.sub(save_url, text)

    pl_chars = {
        "ą": "a", "ć": "c", "ę": "e", "ł": "l", "ń": "n", "ó": "o", "ś": "s", "ż": "z", "ź": "z",
        "Ą": "A", "Ć": "C", "Ę": "E", "Ł": "L", "Ń": "N", "Ó": "O", "Ś": "S", "Ż": "Z", "Ź": "Z",
    }
    chars = list(text_safe)
    for i in range(len(chars)):
        char = chars[i]
        if char in pl_chars and random.random() < 0.60:
            chars[i] = pl_chars[char]
        elif char in [",", "."] and random.random() < 0.30:
            chars[i] = ""
        elif char == " " and random.random() < 0.05:
            chars[i] = "  "
    result = "".join(chars)

    for i, url in enumerate(urls):
        result = result.replace(f"__URL_{i}__", url)
    return result


# ──────────────────────────────────────────────
# ROTACJA KART SIM I HARMONOGRAM
# ──────────────────────────────────────────────
def get_interleaved_sims(devices: list[dict], check_daily_limit: bool = True) -> tuple[list[dict], bool]:
    """
    Zwraca przeplecioną listę aktywnych kart SIM:
    najpierw slot 1 każdego telefonu, potem slot 2 każdego telefonu.
    Drugi element krotki oznacza, czy są włączone karty, ale wszystkie zablokowane przez limit dzienny.
    """
    enabled_sims = []
    for dev in devices:
        for sim in dev.get("sims", []):
            if sim.get("enabled"):
                enabled_sims.append({
                    "device_id": int(dev["id"]),
                    "device_name": dev.get("name", f"Tel {dev['id']}"),
                    "username": dev["username"],
                    "password": dev["password"],
                    "slot": int(sim["slot"]),
                    "label": sim.get("label", f"Tel {dev['id']} – SIM {sim['slot']}"),
                    "key": f"{dev['id']}_{sim['slot']}",
                })

    if not enabled_sims:
        return [], False

    slot1 = sorted([s for s in enabled_sims if s["slot"] == 1], key=lambda x: x["device_id"])
    slot2 = sorted([s for s in enabled_sims if s["slot"] == 2], key=lambda x: x["device_id"])
    other = sorted([s for s in enabled_sims if s["slot"] not in (1, 2)], key=lambda x: (x["slot"], x["device_id"]))
    interleaved = slot1 + slot2 + other

    if not check_daily_limit:
        return interleaved, False

    limit = int(state.get("daily_limit_per_sim", 0) or 0)
    if limit <= 0:
        return interleaved, False

    sent_per_sim = state.get("sent_today_per_sim", {})
    available = [s for s in interleaved if int(sent_per_sim.get(s["key"], 0)) < limit]
    if not available and interleaved:
        return [], True
    return available, False


def parse_hhmm(val: str, default_mins: int) -> int:
    try:
        parts = val.strip().split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        return default_mins


def check_schedule_window() -> tuple[bool, str]:
    """
    Sprawdza czy aktualny czas w Polsce (Europe/Warsaw) mieści się w oknie wysyłki.
    Zwraca (czy_otwarte, komunikat_statusu).
    """
    with state_lock:
        if not state.get("schedule_enabled", True):
            return True, "Harmonogram 24/7 (bez przerwy nocnej)"
        active_days = state.get("active_days", [0, 1, 2, 3, 4, 5, 6])
        w_start = state.get("workdays_start", "09:00")
        w_end = state.get("workdays_end", "17:30")
        wk_start = state.get("weekend_start", "10:00")
        wk_end = state.get("weekend_end", "16:00")

    dt = now_pl()
    weekday = dt.weekday()
    day_name = DAY_NAMES_PL.get(weekday, "")

    if weekday not in active_days:
        return False, f"Dzisiejszy dzień ({day_name}) jest wyłączony w harmonogramie"

    is_weekend = weekday in (5, 6)
    start_str = wk_start if is_weekend else w_start
    end_str = wk_end if is_weekend else w_end

    start_mins = parse_hhmm(start_str, 9 * 60)
    end_mins = parse_hhmm(end_str, 17 * 60 + 30)
    curr_mins = dt.hour * 60 + dt.minute

    if start_mins <= curr_mins < end_mins:
        return True, f"W oknie godzinowym ({start_str} – {end_str})"
    else:
        return False, f"Przerwa nocna / poza oknem ({start_str} – {end_str}, teraz {dt.strftime('%H:%M')})"


# ──────────────────────────────────────────────
# WYSYŁKA SMS PRZEZ API SMS-GATE.APP
# ──────────────────────────────────────────────
def send_sms_request(phone: str, text: str, sim_info: dict) -> tuple[bool, bool, str]:
    payload = {
        "textMessage": {"text": text},
        "phoneNumbers": [phone],
        "simNumber": sim_info["slot"],
        "withDeliveryReport": False,
    }
    try:
        resp = requests.post(
            API_URL,
            json=payload,
            auth=HTTPBasicAuth(sim_info["username"], sim_info["password"]),
            timeout=25,
        )
        if resp.status_code in (200, 201, 202):
            return True, False, "OK"
        else:
            err_msg = f"HTTP {resp.status_code}: {resp.text[:150]}"
            _log(f"    ⚠ {err_msg}")
            skip_wait = resp.status_code == 400
            return False, skip_wait, err_msg
    except requests.RequestException as e:
        err_msg = f"Wyjątek sieciowy: {e}"
        _log(f"    ⚠ {err_msg}")
        return False, False, err_msg


# ──────────────────────────────────────────────
# GŁÓWNA PĘTLA SAMOGRAJA 24/7 (BACKGROUND WORKER)
# ──────────────────────────────────────────────
def worker_loop():
    _log("🤖 Samograj 24/7 uruchomiony – czuwam nad kolejką i harmonogramem.")
    last_device_send_time: dict[int, float] = {}
    last_phase_logged = ""

    while not stop_event.is_set():
        check_and_roll_daily_stats()

        with state_lock:
            current_status = state.get("status", "IDLE")

        if current_status != "RUNNING":
            with state_lock:
                state["worker_phase"] = "PAUSED" if current_status == "PAUSED" else "IDLE"
                state["worker_phase_detail"] = "Wstrzymano ręcznie (PAUZA)" if current_status == "PAUSED" else "Wyłączony"
                state["next_send_at"] = 0.0
            time.sleep(0.5)
            continue

        # 1. Sprawdź okno godzinowe i dzień tygodnia
        in_window, sched_reason = check_schedule_window()
        if not in_window:
            with state_lock:
                state["worker_phase"] = "NIGHT_SLEEP"
                state["worker_phase_detail"] = f"🌙 {sched_reason}"
                state["next_send_at"] = 0.0
            if last_phase_logged != "NIGHT_SLEEP":
                _log(f"🌙 Samograj przechodzi w tryb czuwania: {sched_reason}. Wznowię automatycznie.")
                last_phase_logged = "NIGHT_SLEEP"
            time.sleep(2.0)
            continue

        # 2. Sprawdź, czy są leady w kolejce
        with state_lock:
            raw_lines = [l for l in state.get("csv_queue", "").splitlines() if l.strip()]

        if not raw_lines:
            with state_lock:
                state["worker_phase"] = "WAITING_FOR_LEADS"
                state["worker_phase_detail"] = "📭 Kolejka pusta – dorzuć leady, a samograj od razu ruszy"
                state["next_send_at"] = 0.0
            if last_phase_logged != "WAITING_FOR_LEADS":
                _log("📭 Kolejka leadów jest pusta. Samograj czuwa – dorzuć nowe leady w dowolnym momencie.")
                last_phase_logged = "WAITING_FOR_LEADS"
            time.sleep(1.5)
            continue

        # 3. Sprawdź aktywne karty SIM i limity dzienne (na żywo w każdej iteracji!)
        with state_lock:
            active_sims, all_hit_daily_limit = get_interleaved_sims(state["devices"], check_daily_limit=True)

        if not active_sims:
            if all_hit_daily_limit:
                with state_lock:
                    state["worker_phase"] = "DAILY_LIMIT_REACHED"
                    state["worker_phase_detail"] = "🛑 Wszystkie aktywne karty SIM osiągnęły dzienny limit. Wznowienie o północy."
                    state["next_send_at"] = 0.0
                if last_phase_logged != "DAILY_LIMIT_REACHED":
                    _log("🛑 Wszystkie włączone karty SIM osiągnęły dzisiejszy limit SMS. Czekam do północy (lub zwiększ limit / włącz kolejną kartę SIM).")
                    last_phase_logged = "DAILY_LIMIT_REACHED"
                time.sleep(2.0)
                continue
            else:
                with state_lock:
                    state["worker_phase"] = "NO_ACTIVE_SIM"
                    state["worker_phase_detail"] = "⚠️ Brak włączonej karty SIM – kliknij kartę SIM, aby włączyć"
                    state["next_send_at"] = 0.0
                if last_phase_logged != "NO_ACTIVE_SIM":
                    _log("⚠️ Żadna karta SIM nie jest aktywna! Włącz co najmniej jedną kartę SIM w panelu.")
                    last_phase_logged = "NO_ACTIVE_SIM"
                time.sleep(1.5)
                continue

        # 4. Pobierz pierwszy lead z góry kolejki
        first_line = raw_lines[0].strip()
        parsed = parse_csv_line(first_line)

        if parsed is None or not parsed["phone"]:
            reason = "brak poprawnego numeru" if parsed else "nieprawidłowy format wiersza"
            _log(f"  ⏭ Pominięto wiersz ({first_line[:45]}...) – {reason}")
            with state_lock:
                curr_q = [l for l in state.get("csv_queue", "").splitlines() if l.strip()]
                if curr_q and curr_q[0].strip() == first_line:
                    curr_q.pop(0)
                    state["csv_queue"] = "\n".join(curr_q)
                    save_state()
            continue

        phone = parsed["phone"]

        # Sprawdź duplikat w historii wysłanych
        with state_lock:
            skip_dups = state.get("skip_duplicates", True)
            already_sent = phone in sent_numbers_set

        if skip_dups and already_sent:
            _log(f"  ⏭ Pominięto duplikat: {phone} ({parsed.get('name') or 'brak nazwy'}) – był już wysłany wcześniej")
            with state_lock:
                curr_q = [l for l in state.get("csv_queue", "").splitlines() if l.strip()]
                if curr_q and curr_q[0].strip() == first_line:
                    curr_q.pop(0)
                    state["csv_queue"] = "\n".join(curr_q)
                    save_state()
            continue

        # 5. Wybierz szablon na dzisiejszy dzień tygodnia (0=Pon ... 6=Niedz)
        dt_now = now_pl()
        weekday_key = str(dt_now.weekday())
        day_label = DAY_NAMES_PL.get(dt_now.weekday(), "Dzisiaj")

        with state_lock:
            day_raw_tpl = state.get("daily_templates", {}).get(weekday_key, "")
            if not day_raw_tpl.strip():
                day_raw_tpl = DEFAULT_DAILY_TEMPLATES.get(weekday_key, DEFAULT_DAILY_TEMPLATES["1"])
            templates_list = [t.strip() for t in day_raw_tpl.split("---") if t.strip()]
            obfuscate = state.get("obfuscation_enabled", True)
            sim_step = int(state.get("sim_step", 0))

        base_tpl = random.choice(templates_list)
        text_spun = resolve_spintax(base_tpl, {"name": parsed["name"], "city": parsed["city"], "dt": dt_now})
        final_text = apply_obfuscation(text_spun) if obfuscate else text_spun

        sim_info = active_sims[sim_step % len(active_sims)]
        current_dev = sim_info["device_id"]

        # 6. Bezpieczny cooldown tego samego modemu Dual SIM (jeśli ten sam telefon wysyłał przed chwilą)
        if current_dev in last_device_send_time:
            elapsed = time.time() - last_device_send_time[current_dev]
            with state_lock:
                cooldown_req = float(state.get("same_phone_cooldown", 45.0))
            if elapsed < cooldown_req:
                wait_needed = cooldown_req - elapsed
                _log(f"  ⏳ {sim_info['device_name']}: odpoczynek modemu Dual SIM ({wait_needed:.0f}s)...")
                end_cd = time.time() + wait_needed
                while time.time() < end_cd and not stop_event.is_set():
                    if state.get("status") != "RUNNING" or skip_wait_event.is_set():
                        break
                    with state_lock:
                        state["worker_phase"] = "WAITING_INTERVAL"
                        state["worker_phase_detail"] = f"Odpoczynek modemu {sim_info['device_name']} ({max(0, int(end_cd - time.time()))}s)"
                        state["next_send_at"] = end_cd
                    time.sleep(0.3)

        if stop_event.is_set() or state.get("status") != "RUNNING":
            continue

        # 7. Wysyłka wiadomości SMS
        last_phase_logged = "SENDING"
        lead_desc = f"{phone}" + (f" ({parsed['name']})" if parsed.get("name") else "")
        with state_lock:
            state["worker_phase"] = "SENDING"
            state["worker_phase_detail"] = f"📤 Wysyłanie do {lead_desc} przez {sim_info['label']}..."
            state["next_send_at"] = 0.0

        _log(f"📤 [{day_label}] Wysyłam do {lead_desc} -> {sim_info['label']}...")
        success, skip_wait, err_detail = send_sms_request(phone, final_text, sim_info)
        last_device_send_time[current_dev] = time.time()

        with state_lock:
            # Usuń przetworzony wiersz z początku kolejki
            curr_q = [l for l in state.get("csv_queue", "").splitlines() if l.strip()]
            if curr_q and curr_q[0].strip() == first_line:
                curr_q.pop(0)
                state["csv_queue"] = "\n".join(curr_q)
            elif first_line in curr_q:
                curr_q.remove(first_line)
                state["csv_queue"] = "\n".join(curr_q)

            state["sim_step"] = sim_step + 1

            if success:
                sent_numbers_set.add(phone)
                state["sent_today_total"] = int(state.get("sent_today_total", 0)) + 1
                state["sent_total_all_time"] = max(int(state.get("sent_total_all_time", 0)) + 1, len(sent_numbers_set))
                sim_key = sim_info["key"]
                per_sim = state.get("sent_today_per_sim", {})
                per_sim[sim_key] = int(per_sim.get(sim_key, 0)) + 1
                state["sent_today_per_sim"] = per_sim
                state["last_sent_info"] = {
                    "time": now_pl().strftime("%H:%M:%S"),
                    "phone": phone,
                    "name": parsed.get("name", ""),
                    "city": parsed.get("city", ""),
                    "sim_label": sim_info["label"],
                    "day_name": day_label,
                }
                remaining_count = len(curr_q)
                _log(f"✅ Wysłano do {phone} ({sim_info['label']} – dziś z tej karty: {per_sim[sim_key]}). Pozostało w kolejce: {remaining_count}")
            else:
                state["failed_today"] = int(state.get("failed_today", 0)) + 1
                _log(f"❌ Błąd wysyłki do {phone} ({sim_info['label']}): {err_detail}")

            save_state()

        if success:
            save_sent_numbers()

        # 8. Odczekaj duży, bezpieczny odstęp przed kolejnym SMS-em (z dynamiczną reakcją na zmiany w UI!)
        with state_lock:
            remaining_q = [l for l in state.get("csv_queue", "").splitlines() if l.strip()]

        if not remaining_q or skip_wait:
            if skip_wait:
                _log("⚡ Omijam przerwę po odrzuconym numerze.")
            time.sleep(0.5)
            continue

        with state_lock:
            imin = max(1.0, float(state.get("interval_min", 180.0)))
            imax = max(imin, float(state.get("interval_max", 420.0)))

        delay = random.uniform(imin, imax)
        start_wait = time.time()
        target_end = start_wait + delay
        skip_wait_event.clear()

        with state_lock:
            next_sims, _ = get_interleaved_sims(state["devices"], check_daily_limit=True)
            next_sim_label = next_sims[state["sim_step"] % len(next_sims)]["label"] if next_sims else "kolejna karta"

        mins_fmt = f"{delay/60:.1f} min ({delay:.0f}s)" if delay >= 60 else f"{delay:.0f}s"
        _log(f"⏳ Odstęp przed kolejnym SMS: {mins_fmt} (Następnie: {next_sim_label})...")

        while time.time() < target_end and not stop_event.is_set():
            if skip_wait_event.is_set():
                skip_wait_event.clear()
                _log("⚡ Ręcznie pominięto odliczanie – wysyłam następny SMS teraz!")
                break

            with state_lock:
                if state.get("status") != "RUNNING":
                    break
                # Jeśli użytkownik w locie zmniejszył maksymalny odstęp w UI, skróć bieżące czekanie!
                live_max = max(1.0, float(state.get("interval_max", 420.0)))
                if (target_end - time.time()) > live_max:
                    target_end = time.time() + live_max

                rem_sec = max(0, int(target_end - time.time()))
                if rem_sec >= 60:
                    rem_str = f"{rem_sec // 60}m {rem_sec % 60:02d}s"
                else:
                    rem_str = f"{rem_sec}s"
                state["worker_phase"] = "WAITING_INTERVAL"
                state["worker_phase_detail"] = f"⏳ Następny SMS za {rem_str} (przez {next_sim_label})"
                state["next_send_at"] = target_end

            # Jeśli w trakcie czekania wybiła godzina nocnej przerwy, przerwij odliczanie i przejdź w tryb nocny
            in_win_now, _ = check_schedule_window()
            if not in_win_now:
                break

            time.sleep(0.4)


def ensure_worker_running():
    global worker_thread
    if worker_thread is None or not worker_thread.is_alive():
        stop_event.clear()
        worker_thread = threading.Thread(target=worker_loop, daemon=True)
        worker_thread.start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_state()
    ensure_worker_running()
    yield
    stop_event.set()


app = FastAPI(title="SMS Sender PRO – Samograj 24/7", lifespan=lifespan)
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# ──────────────────────────────────────────────
# ENDPOINTY API (WSZYSTKO ZMIENIANE W LOCIE)
# ──────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={"request": request})


@app.get("/api/state")
async def get_state():
    check_and_roll_daily_stats()
    dt = now_pl()
    weekday = dt.weekday()
    in_window, sched_reason = check_schedule_window()

    with state_lock:
        q_lines = [l for l in state.get("csv_queue", "").splitlines() if l.strip()]
        next_lead_preview = None
        if q_lines:
            p = parse_csv_line(q_lines[0])
            if p:
                next_lead_preview = p
            else:
                next_lead_preview = {"name": q_lines[0][:30], "city": "", "phone": "Błędny wiersz"}

        active_sims, all_hit_limit = get_interleaved_sims(state["devices"], check_daily_limit=True)
        rem_sec = max(0, int(state.get("next_send_at", 0) - time.time())) if state.get("next_send_at", 0) > 0 else 0

        return JSONResponse({
            "status": state["status"],
            "worker_phase": state.get("worker_phase", "IDLE"),
            "worker_phase_detail": state.get("worker_phase_detail", ""),
            "countdown_sec": rem_sec,
            "server_time": dt.strftime("%H:%M:%S"),
            "server_date": dt.strftime("%Y-%m-%d"),
            "current_weekday": weekday,
            "current_weekday_name": DAY_NAMES_PL.get(weekday, ""),
            "in_schedule_window": in_window,
            "schedule_status_text": sched_reason,
            "queue_count": len(q_lines),
            "next_lead": next_lead_preview,
            "csv_queue": state.get("csv_queue", ""),
            "daily_templates": state.get("daily_templates", DEFAULT_DAILY_TEMPLATES),
            "devices": state.get("devices", DEFAULT_DEVICES),
            "active_sequence_labels": [s["label"] for s in active_sims],
            "all_sims_hit_daily_limit": all_hit_limit,
            "interval_min": state.get("interval_min", 180.0),
            "interval_max": state.get("interval_max", 420.0),
            "same_phone_cooldown": state.get("same_phone_cooldown", 45.0),
            "daily_limit_per_sim": state.get("daily_limit_per_sim", 50),
            "schedule_enabled": state.get("schedule_enabled", True),
            "workdays_start": state.get("workdays_start", "09:00"),
            "workdays_end": state.get("workdays_end", "17:30"),
            "weekend_start": state.get("weekend_start", "10:00"),
            "weekend_end": state.get("weekend_end", "16:00"),
            "active_days": state.get("active_days", [0, 1, 2, 3, 4, 5, 6]),
            "obfuscation_enabled": state.get("obfuscation_enabled", True),
            "skip_duplicates": state.get("skip_duplicates", True),
            "smart_greeting_enabled": state.get("smart_greeting_enabled", True),
            "sent_today_total": state.get("sent_today_total", 0),
            "sent_today_per_sim": state.get("sent_today_per_sim", {}),
            "sent_total_all_time": state.get("sent_total_all_time", len(sent_numbers_set)),
            "sent_history_unique_count": len(sent_numbers_set),
            "failed_today": state.get("failed_today", 0),
            "last_sent_info": state.get("last_sent_info"),
            "logs": state.get("logs", []),
        })


@app.post("/api/save_config")
async def save_config(request: Request):
    """Zapisuje zmiany konfiguracji w czasie rzeczywistym (w trakcie działania samograja)."""
    data = await request.json()
    with state_lock:
        if "csv_queue" in data:
            state["csv_queue"] = data["csv_queue"]
        if "daily_templates" in data and isinstance(data["daily_templates"], dict):
            for k, v in data["daily_templates"].items():
                state["daily_templates"][str(k)] = str(v)
        if "interval_min" in data:
            try:
                state["interval_min"] = max(1.0, float(data["interval_min"]))
            except ValueError:
                pass
        if "interval_max" in data:
            try:
                state["interval_max"] = max(state["interval_min"], float(data["interval_max"]))
            except ValueError:
                pass
        if "same_phone_cooldown" in data:
            try:
                state["same_phone_cooldown"] = max(0.0, float(data["same_phone_cooldown"]))
            except ValueError:
                pass
        if "daily_limit_per_sim" in data:
            try:
                state["daily_limit_per_sim"] = max(0, int(float(data["daily_limit_per_sim"])))
            except ValueError:
                pass
        if "schedule_enabled" in data:
            state["schedule_enabled"] = bool(data["schedule_enabled"])
        if "workdays_start" in data:
            state["workdays_start"] = str(data["workdays_start"])
        if "workdays_end" in data:
            state["workdays_end"] = str(data["workdays_end"])
        if "weekend_start" in data:
            state["weekend_start"] = str(data["weekend_start"])
        if "weekend_end" in data:
            state["weekend_end"] = str(data["weekend_end"])
        if "active_days" in data and isinstance(data["active_days"], list):
            state["active_days"] = [int(d) for d in data["active_days"] if str(d).isdigit()]
        if "obfuscation_enabled" in data:
            state["obfuscation_enabled"] = bool(data["obfuscation_enabled"])
        if "skip_duplicates" in data:
            state["skip_duplicates"] = bool(data["skip_duplicates"])
        if "smart_greeting_enabled" in data:
            state["smart_greeting_enabled"] = bool(data["smart_greeting_enabled"])

    save_state()
    return {"status": "ok"}


@app.post("/api/leads/append")
async def append_leads(request: Request):
    """
    Dorzuca nowe leady na koniec kolejki w trakcie działania samograja,
    automatycznie odfiltrowując błędne wiersze oraz duplikaty!
    """
    data = await request.json()
    raw_new = data.get("csv", "").strip()
    if not raw_new:
        return {"status": "error", "message": "Wklej wiersze CSV do dodania."}

    new_lines = [l.strip() for l in raw_new.splitlines() if l.strip()]
    added = []
    skipped_dups = 0
    skipped_invalid = 0

    with state_lock:
        existing_lines = [l.strip() for l in state.get("csv_queue", "").splitlines() if l.strip()]
        existing_phones = set()
        for el in existing_lines:
            p = parse_csv_line(el)
            if p and p.get("phone"):
                existing_phones.add(p["phone"])

        skip_dups = state.get("skip_duplicates", True)

        for line in new_lines:
            # Pomiń nagłówek CSV jeśli występuje
            if line.lower().startswith(("nazwa,", "name,", "firma,", "obiekt,")) and not extract_phone(line):
                continue
            parsed = parse_csv_line(line)
            if not parsed or not parsed.get("phone"):
                skipped_invalid += 1
                continue
            ph = parsed["phone"]
            if ph in existing_phones or (skip_dups and ph in sent_numbers_set):
                skipped_dups += 1
                continue
            existing_phones.add(ph)
            added.append(line)

        if added:
            all_q = existing_lines + added
            state["csv_queue"] = "\n".join(all_q)
            save_state()

    msg = f"➕ Dorzucono {len(added)} nowych leadów do kolejki"
    if skipped_dups or skipped_invalid:
        msg += f" (pominięto: {skipped_dups} duplikatów, {skipped_invalid} bez numeru)"
    _log(msg)

    return {
        "status": "ok",
        "added": len(added),
        "skipped_duplicates": skipped_dups,
        "skipped_invalid": skipped_invalid,
        "message": msg,
    }


@app.post("/api/sim/toggle")
async def toggle_sim(request: Request):
    """Włącza lub wyłącza wybraną kartę SIM w czasie rzeczywistym."""
    data = await request.json()
    dev_id = int(data.get("device_id", 0))
    slot = int(data.get("slot", 1))
    enabled = data.get("enabled")

    changed_label = None
    new_state = False
    with state_lock:
        for dev in state["devices"]:
            if int(dev["id"]) == dev_id:
                for sim in dev.get("sims", []):
                    if int(sim["slot"]) == slot:
                        sim["enabled"] = bool(enabled) if enabled is not None else not sim.get("enabled", False)
                        new_state = sim["enabled"]
                        changed_label = sim.get("label", f"Tel {dev_id} – SIM {slot}")
                        break

    if changed_label:
        icon = "🟢 Włączono" if new_state else "⚪ Wyłączono"
        _log(f"{icon} w locie kartę: {changed_label}")
        save_state()
        return {"status": "ok", "enabled": new_state}
    return {"status": "error", "message": "Nie znaleziono karty SIM."}


@app.post("/api/device/save")
async def save_device(request: Request):
    """Dodaje nowy telefon lub aktualizuje istniejący w czasie rzeczywistym."""
    data = await request.json()
    dev_id = data.get("id")
    name = str(data.get("name", "")).strip()
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", "")).strip()
    sim1_enabled = bool(data.get("sim1_enabled", True))
    sim2_enabled = bool(data.get("sim2_enabled", False))

    if not username or not password:
        return {"status": "error", "message": "Podaj login i hasło z aplikacji SMS-Gate na telefonie."}

    with state_lock:
        if dev_id is not None and str(dev_id).isdigit():
            dev_id = int(dev_id)
            for dev in state["devices"]:
                if int(dev["id"]) == dev_id:
                    dev["name"] = name or f"Telefon {dev_id}"
                    dev["username"] = username
                    dev["password"] = password
                    dev["sims"] = [
                        {"slot": 1, "enabled": sim1_enabled, "label": f"Tel {dev_id} – SIM 1"},
                        {"slot": 2, "enabled": sim2_enabled, "label": f"Tel {dev_id} – SIM 2"},
                    ]
                    _log(f"📱 Zaktualizowano dane urządzenia: {dev['name']} (ID {dev_id})")
                    save_state()
                    return {"status": "ok", "device": dev}

        existing_ids = [int(d["id"]) for d in state["devices"]] if state["devices"] else [0]
        new_id = max(existing_ids) + 1
        new_dev = {
            "id": new_id,
            "name": name or f"Telefon {new_id}",
            "username": username,
            "password": password,
            "sims": [
                {"slot": 1, "enabled": sim1_enabled, "label": f"Tel {new_id} – SIM 1"},
                {"slot": 2, "enabled": sim2_enabled, "label": f"Tel {new_id} – SIM 2"},
            ],
        }
        state["devices"].append(new_dev)
        _log(f"➕ Dodano nowy telefon w locie: {new_dev['name']} (Login: {username})")
        save_state()
        return {"status": "ok", "device": new_dev}


@app.post("/api/device/delete")
async def delete_device(request: Request):
    """Usuwa telefon z listy urządzeń w czasie rzeczywistym."""
    data = await request.json()
    dev_id = int(data.get("device_id", 0))
    with state_lock:
        before = len(state["devices"])
        state["devices"] = [d for d in state["devices"] if int(d["id"]) != dev_id]
        if len(state["devices"]) < before:
            _log(f"🗑 Usunięto telefon ID {dev_id} z rotacji.")
            save_state()
            return {"status": "ok"}
    return {"status": "error", "message": "Nie znaleziono telefonu."}


@app.post("/api/device/test")
async def test_device_sms(request: Request):
    """Wysyła pojedynczy SMS testowy z wybranego telefonu i slotu SIM."""
    data = await request.json()
    dev_id = int(data.get("device_id", 1))
    slot = int(data.get("slot", 1))
    raw_phone = str(data.get("phone", "")).strip()
    phone = extract_phone(raw_phone)
    if not phone:
        return {"status": "error", "message": "Podaj poprawny 9-cyfrowy numer telefonu do testu."}

    target_sim = None
    with state_lock:
        for dev in state["devices"]:
            if int(dev["id"]) == dev_id:
                target_sim = {
                    "device_id": dev_id,
                    "device_name": dev["name"],
                    "username": dev["username"],
                    "password": dev["password"],
                    "slot": slot,
                    "label": f"Tel {dev_id} – SIM {slot}",
                }
                break

    if not target_sim:
        return {"status": "error", "message": "Nie znaleziono wybranego telefonu."}

    test_text = data.get("text") or f"Test polaczenia SMS Sender PRO ({target_sim['label']}) - godz. {now_pl().strftime('%H:%M:%S')}"
    _log(f"🧪 Wysyłam SMS testowy do {phone} przez {target_sim['label']}...")
    ok, _, detail = send_sms_request(phone, test_text, target_sim)
    if ok:
        _log(f"✅ SMS testowy na {phone} ({target_sim['label']}) wysłany pomyślnie!")
        return {"status": "ok", "message": f"Wysłano SMS testowy z {target_sim['label']} na {phone}!"}
    else:
        return {"status": "error", "message": f"Błąd wysyłki testowej: {detail}"}


@app.post("/api/start")
async def start_autopilot():
    ensure_worker_running()
    with state_lock:
        active_sims, _ = get_interleaved_sims(state["devices"], check_daily_limit=False)
        if not active_sims:
            return {"status": "error", "message": "Włącz co najmniej jedną kartę SIM przed uruchomieniem samograja."}
        state["status"] = "RUNNING"
        save_state()
    _log("▶ SAMOGRAJ WŁĄCZONY (tryb pracy ciągłej 7 dni w tygodniu).")
    return {"status": "ok"}


@app.post("/api/pause")
async def pause_autopilot():
    with state_lock:
        state["status"] = "PAUSED"
        state["worker_phase"] = "PAUSED"
        state["worker_phase_detail"] = "Wstrzymano ręcznie (PAUZA)"
        state["next_send_at"] = 0.0
        save_state()
    _log("⏸ Samograj wstrzymany (PAUZA).")
    return {"status": "ok"}


@app.post("/api/skip_wait")
async def skip_current_wait():
    """Natychmiast przerywa odliczanie między SMS-ami i wysyła kolejną wiadomość."""
    skip_wait_event.set()
    return {"status": "ok"}


@app.post("/api/reset_daily_counters")
async def reset_daily_counters():
    with state_lock:
        state["sent_today_total"] = 0
        state["sent_today_per_sim"] = {}
        state["failed_today"] = 0
        save_state()
    _log("🔄 Zresetowano dzisiejsze liczniki wysłanych SMS-ów dla wszystkich kart SIM.")
    return {"status": "ok"}


@app.post("/api/clear_queue")
async def clear_queue():
    with state_lock:
        state["csv_queue"] = ""
        save_state()
    _log("🗑 Wyczyszczono kolejkę oczekujących leadów.")
    return {"status": "ok"}


@app.post("/api/clear_sent_history")
async def clear_sent_history():
    global sent_numbers_set
    with state_lock:
        sent_numbers_set.clear()
        save_sent_numbers()
    _log("🗑 Wyczyszczono bazę historii wysłanych numerów (ochrona przed duplikatami zresetowana).")
    return {"status": "ok"}


@app.post("/api/restore_default_templates")
async def restore_default_templates(request: Request):
    data = await request.json()
    day_key = str(data.get("day", "all"))
    with state_lock:
        if day_key == "all":
            state["daily_templates"] = DEFAULT_DAILY_TEMPLATES.copy()
            _log("🔄 Przywrócono domyślne szablony SMS dla wszystkich 7 dni tygodnia.")
        elif day_key in DEFAULT_DAILY_TEMPLATES:
            state["daily_templates"][day_key] = DEFAULT_DAILY_TEMPLATES[day_key]
            _log(f"🔄 Przywrócono domyślne szablony SMS na {DAY_NAMES_PL.get(int(day_key), 'wybrany dzień')}.")
        save_state()
    return {"status": "ok", "daily_templates": state["daily_templates"]}


@app.post("/api/test_spintax")
async def test_spintax(request: Request):
    data = await request.json()
    day_key = str(data.get("day", now_pl().weekday()))
    template_raw = data.get("template")
    if template_raw is None:
        template_raw = state.get("daily_templates", {}).get(day_key, DEFAULT_DAILY_TEMPLATES.get(day_key, ""))

    templates_list = [t.strip() for t in str(template_raw).split("---") if t.strip()]
    if not templates_list:
        return {"status": "error", "message": "Brak szablonów SMS w tym dniu."}

    tpl = random.choice(templates_list)
    test_dt = now_pl()
    if "hour" in data and str(data["hour"]).isdigit():
        try:
            test_dt = test_dt.replace(hour=int(data["hour"]), minute=int(data.get("minute", 0)))
        except ValueError:
            pass

    tod = get_time_of_day_context(test_dt)
    sample_context = {
        "name": data.get("name", "Willa Panorama"),
        "city": data.get("city", "Zakopane"),
        "dt": test_dt,
        "smart_greeting": bool(data.get("smart_greeting", state.get("smart_greeting_enabled", True))),
    }
    spun = resolve_spintax(tpl, sample_context)
    obfuscated = apply_obfuscation(spun) if state.get("obfuscation_enabled", True) else spun
    return {
        "status": "ok",
        "variants_count": len(templates_list),
        "raw_template": tpl,
        "spun": spun,
        "final": obfuscated,
        "char_count": len(obfuscated),
        "simulated_time": test_dt.strftime("%H:%M"),
        "is_evening": tod["is_evening"],
        "pora_dnia": tod["pora_dnia"],
    }