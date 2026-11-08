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
# Składnia {PORA: rano (do 12:00) | popołudnie (12:00-17:00) | wieczór (od 17:00)}
# gwarantuje brak oksymoronów (np. brak "wieczornej kawy" czy "poranka" wieczorem).
# ──────────────────────────────────────────────
TEMPLATES_VERSION = 6

DEFAULT_DAILY_TEMPLATES = {
    # 0 = PONIEDZIAŁEK
    "0": """{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Tu Krzysztof | Krzysztof z tej strony | Z tej strony Krzysztof}. {Czy w Państwa obiekcie | Czy u Państwa w obiekcie | Czy w Państwa kwaterze} {goście mogą już | turyści mogą już | macie już opcję, by} {rezerwować pobyty bezpośrednio z telefonu | opłacać rezerwacje online ze smartfona | rezerwować wolne terminy prosto z komórki}? {Turyści sami sprawdzają grafik i płacą zadatek BLIKiem | Gość klika termin i opłaca pobyt w 30 sekund | Zdejmuje to z głowy ciągłe telefony o wolne terminy}, a {100% zysku zostaje u Was | pełna kwota trafia do Was bez prowizji portali | cały zysk zostaje w Państwa kieszeni bez pośredników}. {Mogę przygotować | Podesłać | Przygotować} {darmowe demo wizualne | bezpłatny podgląd}, jak {wyglądałoby to | działałoby to} u Państwa?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Tu Krzysztof | Krzysztof z tej strony}. {Na start tygodnia krótko: | Nowy tydzień i proste pytanie: | Krótka sprawa na początek tygodnia:} {pomagam obiektom noclegowym | pomagam właścicielom kwater | wdrażam dla gospodarzy} {uniezależnić się od prowizji portali | bezpośrednie kalendarze rezerwacji na telefon | automatyczne rezerwacje bez pośredników}. {Goście rezerwują i wpłacają zadatki w kilkadziesiąt sekund | Płatności BLIK 24/7 wpadają bezpośrednio na Wasze konto | Koniec z ręcznym sprawdzaniem grafiku i podawaniem numeru konta}. {Podesłać bezpłatne demo wizualne | Mogę przygotować darmowy podgląd}, jak {prezentowałoby się to | wyglądałoby to} {dla Państwa | dla Państwa obiektu}?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Z tej strony Krzysztof | Tu Krzysztof | Krzysztof z tej strony}. {Zamiast tracić czas na odpisywanie „czy termin wolny” | Zamiast wisieć na telefonie w poniedziałek | Zamiast oddawać kilkanaście procent prowizji portalom}: {wdrażam dla kwater | tworzę dla obiektów | uruchamiam dla gospodarzy} {proste kalendarze rezerwacji online na smartfony | bezobsługowe moduły rezerwacji z BLIKiem | niezależne systemy rezerwacji 24/7}. {Turyści sami rezerwują i płacą zadatek | Pieniądze natychmiast trafiają na Państwa konto | Gość rezerwuje w 30 sekund bez dzwonienia}. {Przygotować darmowe demo | Podesłać bezpłatny podgląd} {dla Państwa | u Państwa | pod Państwa obiekt}?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Tu Krzysztof | Krzysztof z tej strony}. {W poniedziałek prosto do rzeczy: | Krótkie pytanie na start tygodnia: | Konkretnie na początek tygodnia:} czy {w Państwa obiekcie | u Państwa | w Państwa domkach} {macie już | działa już | macie wdrożony} {własny kalendarz rezerwacji na telefonie | bezpośredni moduł rezerwacji 24/7 | system rezerwacji z BLIKiem bez pośredników}? {100% kwoty zostaje w Państwa kieszeni | Zdejmujecie z głowy prowizje portali | Goście nie muszą dzwonić, by zarezerwować}. {Mogę podesłać | Przygotować | Podesłać} {darmowe demo wizualne | bezpłatną wizualizację}, jak {działałoby to | wyglądałoby to} u Państwa?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Krzysztof z tej strony | Tu Krzysztof | Z tej strony Krzysztof}. {Większość turystów szuka noclegów na telefonie i woli od razu opłacić termin | Klienci coraz rzadziej dzwonią, wolą kliknąć termin i zapłacić BLIKiem | Poniedziałek to czas, kiedy ludzie planują kolejne wyjazdy na telefonach}. {Wdrażam dla kwater | Tworzę dla obiektów | Buduję dla gospodarzy} {proste kalendarze bez pośredników | bezpośrednie moduły rezerwacji 24/7 | niezależne kalendarze na smartfony}. {Podesłać darmowe demo wizualne | Mogę przygotować bezpłatny podgląd | Przygotować darmowe demo} {dla Państwa | u Państwa | pod Państwa obiekt}?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Tu Krzysztof | Z tej strony Krzysztof}. {Czy w Państwa obiekcie | Czy u Państwa | Czy w Państwa kwaterze} {posiada już | ma już | korzysta już z} {bezpośrednich rezerwacji online na smartfonie | własnego kalendarza na telefonie z BLIKiem | automatycznych zadatków 24/7 bez portali}? {Pełna kwota za pobyt trafia prosto do Was | Oszczędzacie na prowizjach i nie odbieracie telefonów po nocach | Gość sam wybiera termin i wpłaca zadatek w 30 sekund}. {Podesłać bezpłatne demo | Mogę podesłać krótkie demo wizualne}, jak {wyglądałoby to | działałoby to} u Państwa?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Krzysztof z tej strony | Tu Krzysztof}. {PORA: W poniedziałek | W poniedziałkowe popołudnie | W poniedziałkowy wieczór} {krótko i konkretnie: | prosto do sedna: | krótka sprawa:} {pomagam gospodarzom | tworzę dla kwater | wdrażam dla obiektów noclegowych} {własne moduły rezerwacji z telefonu | bezpośrednie kalendarze z BLIKiem 24/7 | proste systemy bez prowizji portali}. {Mogę przygotować darmowe demo | Podesłać bezpłatny podgląd wizualny | Przygotować darmowe demo}, jak {prezentowałoby się to | wyglądałoby to} {dla Państwa | dla Państwa obiektu}?""",

    # 1 = WTOREK
    "1": """{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Tu Krzysztof | Krzysztof z tej strony | Z tej strony Krzysztof}. {Czy w Państwa obiekcie | Czy u Państwa w obiekcie | Czy w Państwa kwaterze} {goście mogą już rezerwować | turyści mogą rezerwować | macie już opcję rezerwacji} {bezpośrednio na smartfonie | przez prosty kalendarz z płatnością BLIK | online 24/7 z telefonu}? {Turyści sami sprawdzają grafik i płacą zadatek | Zdejmuje to z głowy telefony o wolne pokoje | Gość rezerwuje w kilkadziesiąt sekund}, a {100% kwoty zostaje u Was bez prowizji portali | pełny zysk trafia do Was bez pośredników | nie oddajecie kilkunastu procent portalom}. {Podesłać darmowe demo wizualne | Mogę przygotować bezpłatny podgląd}, jak {wyglądałoby to | działałoby to} u Państwa?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Krzysztof z tej strony | Tu Krzysztof}. {PORA: We wtorek | We wtorkowe popołudnie | We wtorkowy wieczór} {krótko i konkretnie: | prosto do celu: | konkretne pytanie:} {pomagam gospodarzom | tworzę dla kwater | wdrażam dla obiektów} {niezależne kalendarze rezerwacji na telefon | bezpośrednie systemy rezerwacji z BLIKiem | automatyczne moduły rezerwacji bez portali}. {Turyści rezerwują i opłacają pobyt w 30 sekund bezpośrednio na Wasze konto | Płatności 24/7 wpadają prosto do Was | Koniec z ręcznym sprawdzaniem terminów}. {Mogę przygotować darmowe demo wizualne | Podesłać bezpłatny podgląd} {dla Państwa | u Państwa | pod Państwa obiekt}?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Tu Krzysztof | Z tej strony Krzysztof | Krzysztof z tej strony}. {Zamiast wisieć na telefonie i ciągle odpisywać na wiadomości | Zamiast oddawać prowizję portalom rezerwacyjnym | Zamiast ręcznie pilnować wpłat zadatków}: {uruchamiam dla kwater | buduję dla obiektów | wdrażam dla gospodarzy} {własne moduły rezerwacji z telefonu | bezobsługowe kalendarze z BLIKiem 24/7 | proste systemy bez pośredników}. {Gość sam klika wolny termin i płaci zadatek | Pieniądze od razu trafiają na Państwa konto | Kalendarz sam pilnuje grafiku}. {Przygotować bezpłatne demo | Podesłać darmowy podgląd}, jak {działałoby to | wyglądałoby to} u Państwa?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Krzysztof z tej strony | Tu Krzysztof}. {Turyści coraz częściej rezerwują noclegi w biegu na telefonie i oczekują natychmiastowej rezerwacji | Klienci wolą od razu kliknąć termin i zapłacić BLIKiem niż dzwonić | Większość osób planuje pobyty na smartfonie bez czekania na telefon zwrotny}. {Wdrażam dla obiektów | Tworzę dla kwater | Uruchamiam dla gospodarzy} {proste narzędzia rezerwacji 24/7 bez pośredników | bezpośrednie kalendarze na telefon | niezależne systemy rezerwacji z BLIKiem}. {Podesłać darmowe demo wizualne | Mogę przygotować bezpłatny podgląd} {dla Państwa | u Państwa | pod Państwa obiekt}?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Tu Krzysztof | Krzysztof z tej strony}. {Czy Państwa obiekt | Czy u Państwa | Czy Wasza kwatera} {posiada już | ma już | korzysta już z} {bezpośredniego kalendarza rezerwacji online na telefon | własnego systemu rezerwacji z BLIKiem 24/7 | modułu rezerwacji bez prowizji portali}? {Zyskujecie 100% ceny pobytu | Oszczędzacie na prowizjach i zyskujecie święty spokój | Goście rezerwują wygodnie z telefonu w 30 sekund}. {Mogę podesłać darmowe demo | Podesłać bezpłatny podgląd wizualny}, jak {wyglądałoby to | prezentowałoby się to} u Państwa?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Z tej strony Krzysztof | Tu Krzysztof}. {Pomagam gospodarzom zautomatyzować rezerwacje noclegów: | Ułatwiam właścicielom kwater przyjmowanie rezerwacji: | Proste rozwiązanie dla obiektów noclegowych:} {gość sam wybiera wolny pokój i płaci zadatek z telefonu | turyści sami rezerwują i wpłacają zadatki BLIKiem 24/7 | gość klika termin i płaci w 30 sekund}, a {100% kwoty wpada na Państwa konto bez prowizji | cały zysk zostaje u Was bez pośredników | nie oddajecie ani procenta portalom}. {Przygotować darmowe demo | Podesłać bezpłatny podgląd} {dla Państwa | u Państwa | pod Państwa obiekt}?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Krzysztof z tej strony | Tu Krzysztof}. {PORA: We wtorek | We wtorkowe popołudnie | We wtorkowy wieczór} {prosto do sedna: | krótka sprawa: | konkretnie:} {wdrażam dla kwater | buduję dla obiektów | tworzę dla gospodarzy} {kalendarze rezerwacji z telefonu bez prowizji portali (płatności 24/7) | bezpośrednie moduły rezerwacji z BLIKiem na smartfony | proste systemy bezobsługowych rezerwacji}. {Mogę przygotować darmowe demo | Podesłać bezpłatny podgląd wizualny}, jak {wyglądałoby to | działałoby to} {dla Państwa | dla Państwa obiektu}?""",

    # 2 = ŚRODA
    "2": """{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Tu Krzysztof | Krzysztof z tej strony | Z tej strony Krzysztof}. {W połowie tygodnia zaczyna się fala zapytań o kolejne terminy | W środku tygodnia turyści najintensywniej planują wyjazdy na telefonach | Środa to czas wzmożonych poszukiwań noclegów na smartfonie}. {Wdrażam dla kwater | Tworzę dla obiektów | Uruchamiam dla gospodarzy} {bezpośrednie kalendarze na telefon – goście rezerwują 24/7 z BLIKiem | proste moduły rezerwacji online bez pośredników | niezależne systemy rezerwacji z płatnościami z telefonu}, a {100% kwoty zostaje u Was bez prowizji | pełny zysk trafia prosto na Państwa konto | nie oddajecie kilkunastu procent portalom}. {Podesłać darmowe demo wizualne | Mogę przygotować bezpłatny podgląd} {dla Państwa | u Państwa | pod Państwa obiekt}?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Krzysztof z tej strony | Tu Krzysztof}. {Pomagam obiektom noclegowym | Pomagam gospodarzom | Wdrażam dla kwater} {uruchomić bezobsługowy kalendarz rezerwacji na telefon | bezpośrednie rezerwacje online ze smartfona | własny system rezerwacji z BLIKiem 24/7}. {Turyści rezerwują w 30 sekund i płacą zadatek bez oddawania prowizji portalom | Goście sami sprawdzają grafik i wpłacają zadatki | Pieniądze od razu trafiają na Wasze konto bez pośredników}. {Mogę przygotować darmowe demo wizualne | Podesłać bezpłatne demo}, jak {działałoby to | wyglądałoby to} u Państwa?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Tu Krzysztof | Z tej strony Krzysztof | Krzysztof z tej strony}. {PORA: W środę | W środowe popołudnie | W środowy wieczór} {krótko i rzeczowo: | prosto do sedna: | konkretne pytanie:} {wdrażam systemy bezpośrednich rezerwacji z telefonu | tworzę dla kwater proste kalendarze na smartfony | uruchamiam moduły rezerwacji z płatnością BLIK}. {Zdejmują z głowy ciągłe telefony, a cały zysk zostaje w Państwa kieszeni | Koniec z odbieraniem telefonów po nocach o wolne terminy | 100% ceny pobytu trafia bezpośrednio do Was}. {Podesłać darmowe demo wizualne | Przygotować bezpłatny podgląd} {dla Państwa | u Państwa | pod Państwa obiekt}?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Z tej strony Krzysztof | Tu Krzysztof}. {Zamiast oddawać prowizję portalom | Zamiast tracić czas na odpisywanie na wiadomości „czy macie wolne” | Zamiast ręcznie podawać numer konta do zadatków}: {uruchamiam dla kwater | buduję dla gospodarzy | wdrażam dla obiektów} {niezależne kalendarze na smartfony | bezpośrednie systemy rezerwacji 24/7 z BLIKiem | proste moduły online bez pośredników}. {Turyści sami rezerwują i wpłacają zadatki bezpośrednio na Wasze konto | Gość rezerwuje w kilkadziesiąt sekund, a zysk zostaje u Was | Pełna kwota trafia od razu do Państwa}. {Przygotować bezpłatne demo | Podesłać darmowy podgląd}, jak {wyglądałoby to | prezentowałoby się to} u Państwa?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Krzysztof z tej strony | Tu Krzysztof}. {Czy w Państwa obiekcie | Czy u Państwa w kwaterze | Czy w Państwa domkach} {goście mogą już | turyści mogą już | macie już wdrożoną opcję, by} {kliknąć wolny termin i wpłacić zadatek BLIKiem z telefonu | zarezerwować pobyt bezpośrednio z telefonu 24/7 | opłacić rezerwację online bez pośredników}? {Buduję dla gospodarzy proste kalendarze na komórkę | Wdrażam systemy bez prowizji portali | Tworzę bezobsługowe moduły rezerwacji}. {Mogę podesłać darmowe demo wizualne | Podesłać bezpłatny podgląd} {dla Państwa | u Państwa | pod Państwa obiekt}?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Tu Krzysztof | Z tej strony Krzysztof}. {Koniec z traceniem czasu na wiadomości „czy termin wolny” | Zdejmuję z głowy ciągłe telefony o wolne pokoje | Ułatwiam gospodarzom bezpośrednie rezerwacje}: {gość sam sprawdza grafik na telefonie i płaci zadatek | turysta rezerwuje online w 30 sekund o dowolnej porze | system sam pilnuje grafiku i przyjmuje wpłaty z BLIKiem}, a {100% kwoty trafia do Państwa bez pośredników | cały zysk zostaje w Państwa kieszeni bez prowizji portali | pieniądze wpadają od ręki na Wasze konto}. {Podesłać darmowe demo | Przygotować bezpłatną wizualizację}, jak {działałoby to | wyglądałoby to} u Państwa?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Krzysztof z tej strony | Tu Krzysztof}. {PORA: W środę | W środowe popołudnie | W środowy wieczór} {konkretna sprawa: | krótko i na temat: | proste pytanie:} {pomagam właścicielom noclegów | wdrażam dla kwater | pomagam gospodarzom} {uruchomić własny system rezerwacji z telefonu z pominięciem prowizji portali | bezobsługowy kalendarz rezerwacji z BLIKiem | bezpośrednie rezerwacje online 24/7}. {Przygotować darmowe demo wizualne | Mogę przygotować bezpłatny podgląd} {dla Państwa | u Państwa | pod Państwa obiekt}?""",

    # 3 = CZWARTEK
    "3": """{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Tu Krzysztof | Krzysztof z tej strony | Z tej strony Krzysztof}. {Zamiast wisieć na telefonie przed weekendem: | Przed nadchodzącym weekendem krótka sprawa: | Przed weekendową falą pytań o wolne terminy:} {wdrażam dla obiektów noclegowych | tworzę dla kwater | uruchamiam dla gospodarzy} {kalendarze rezerwacji na telefon | proste moduły online z płatnościami BLIK | bezobsługowe systemy rezerwacji 24/7}. {Goście rezerwują z komórki, a 100% kwoty zostaje u Państwa bez prowizji | Turyści sami sprawdzają grafik i płacą zadatek w 30 sekund | Zdejmuje to z głowy ciągłe odbieranie telefonów}. {Podesłać darmowe demo wizualne | Mogę przygotować bezpłatny podgląd} {dla Państwa | u Państwa | pod Państwa obiekt}?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Krzysztof z tej strony | Tu Krzysztof}. {PORA: W czwartek | W czwartkowe popołudnie | W czwartkowy wieczór} {krótko i do rzeczy: | konkretnie: | prosto do celu:} {pomagam gospodarzom zautomatyzować rezerwacje noclegów | wdrażam dla kwater niezależne kalendarze na smartfony | tworzę bezpośrednie moduły rezerwacji z BLIKiem}. {Turyści rezerwują i płacą z telefonu w 30 sekund bezpośrednio do Was | Płatności zadatków trafiają prosto na Wasze konto | Koniec z ręcznym podawaniem numeru konta}. {Mogę przygotować darmowe demo | Podesłać bezpłatny podgląd}, jak {wyglądałoby to | działałoby to} u Państwa?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Tu Krzysztof | Z tej strony Krzysztof | Krzysztof z tej strony}. {Uruchamiam dla kwater | Wdrażam dla gospodarzy | Buduję dla obiektów} {moduły rezerwacji online na telefon | bezobsługowe kalendarze z BLIKiem | bezpośrednie systemy bez prowizji portali}. {Kalendarz sam pilnuje grafiku i przyjmuje zadatki, dzięki czemu nie trzeba wisieć na telefonie | Turyści sami sprawdzają wolne pokoje i płacą zadatek o każdej porze | System działa 24/7, a pieniądze trafiają prosto do Was}, a {pełny zysk zostaje u Was | 100% kwoty trafia do Państwa kieszeni | oszczędzacie na prowizjach pośredników}. {Podesłać bezpłatne demo wizualne | Przygotować darmowe demo} {dla Państwa | u Państwa | pod Państwa obiekt}?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Z tej strony Krzysztof | Tu Krzysztof}. {Przed weekendem turyści szukają noclegów na telefonach i wolą od razu kliknąć termin oraz wpłacić zadatek | Klienci coraz rzadziej dzwonią z pytaniem o grafik – chcą kliknąć i zapłacić BLIKiem | W czwartki najwięcej osób szuka noclegów na ostatnią chwilę prosto ze smartfona}. {Wdrażam niezależne kalendarze 24/7 bez prowizji pośredników | Buduję dla kwater bezpośrednie narzędzia rezerwacji | Tworzę proste kalendarze na telefon}. {Przygotować darmowe demo | Podesłać bezpłatny podgląd}, jak {wyglądałoby to | prezentowałoby się to} u Państwa?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Krzysztof z tej strony | Tu Krzysztof}. {Buduję dla właścicieli kwater i domków | Wdrażam dla obiektów noclegowych | Przygotowuję dla gospodarzy} {proste kalendarze rezerwacji na telefon | bezpośrednie moduły z płatnościami BLIK | niezależne systemy rezerwacji 24/7}. {System działa całą dobę, a wpłaty trafiają prosto na Wasze konto bez prowizji portali | Turyści rezerwują w 30 sekund z telefonu bez dzwonienia | Zyskujecie pełną kwotę bez oddawania prowizji pośrednikom}. {Mogę podesłać darmowe demo wizualne | Podesłać bezpłatny podgląd} {dla Państwa | u Państwa | pod Państwa obiekt}?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Tu Krzysztof | Z tej strony Krzysztof}. {Czy w Państwa obiekcie | Czy u Państwa | Czy w Państwa kwaterze} {goście mają już opcję, by | goście mogą już | turyści mogą już} {rezerwować pobyty bezpośrednio z telefonu bez dzwonienia | opłacić zadatek BLIKiem w 30 sekund przez smartfon | sprawdzić grafik i zapłacić online 24/7}? {100% kwoty zostaje u Państwa | Oszczędzacie na prowizjach i nie musicie odbierać setek telefonów | Pieniądze wpadają od ręki na Wasze konto}. {Podesłać darmowe demo przygotowane pod Państwa obiekt | Przygotować bezpłatny podgląd wizualny}?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Krzysztof z tej strony | Tu Krzysztof}. {PORA: W czwartek | W czwartkowe popołudnie | W czwartkowy wieczór} {prosto do sedna: | krótka sprawa: | konkretnie:} {wdrażam kalendarze rezerwacji online na telefon | uruchamiam dla kwater systemy bezpośrednich rezerwacji | tworzę moduły z BLIKiem bez pośredników}, dzięki którym {100% kwoty za pobyt trafia bezpośrednio do Państwa | goście rezerwują w 30 sekund, a zysk zostaje u Was | nie oddajecie ani grosza prowizji portalom}. {Przygotować darmowe demo wizualne | Mogę podesłać bezpłatny podgląd} {dla Państwa | u Państwa | pod Państwa obiekt}?""",

    # 4 = PIĄTEK
    "4": """{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Tu Krzysztof | Krzysztof z tej strony | Z tej strony Krzysztof}. {W weekendowym ruchu trudno odbierać każdy telefon o kolejne terminy | W piątkowym zamieszaniu nie ma czasu na ciągłe odpisywanie o grafik | Przed weekendem gospodarze mają urwanie głowy z telefonami}. {Wdrażam kalendarze rezerwacji na smartfony | Uruchamiam proste systemy rezerwacji 24/7 z BLIKiem | Buduję bezpośrednie moduły rezerwacji bez pośredników} – {goście sami rezerwują i wpłacają zadatki, a 100% wpłat trafia do Państwa bez prowizji | turyści sami sprawdzają wolne dni i płacą zadatek ze smartfona | system sam przyjmuje rezerwacje, a zysk zostaje u Was}. {Podesłać darmowe demo wizualne | Mogę przygotować bezpłatny podgląd} {dla Państwa | u Państwa | pod Państwa obiekt}?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Krzysztof z tej strony | Tu Krzysztof}. {Pomagam obiektom turystycznym | Wdrażam dla gospodarzy | Pomagam właścicielom kwater} {uniezależnić się od prowizji portali i zautomatyzować grafik | bezpośrednie moduły rezerwacji z telefonu | proste kalendarze 24/7 z płatnościami BLIK}. {Turyści sami wybierają wolne dni i płacą zadatek przez smartfon w 30 sekund | Gość rezerwuje o każdej porze bez dzwonienia, a pieniądze trafiają do Was | Koniec z ręcznym podawaniem numeru konta i sprawdzaniem grafiku}. {Mogę przygotować darmowe demo wizualne | Podesłać bezpłatny podgląd} {dla Państwa | u Państwa | pod Państwa obiekt}?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Tu Krzysztof | Z tej strony Krzysztof | Krzysztof z tej strony}. {Uruchamiam dla kwater i domków | Wdrażam dla obiektów noclegowych | Buduję dla gospodarzy} {bezpośrednie kalendarze rezerwacji 24/7 na telefon | proste moduły online z płatnością BLIK | niezależne systemy bez prowizji pośredników}. {Zdejmują z głowy ciągłe odbieranie telefonów w weekend, a pełny zysk z pobytów zostaje u właściciela | Turyści rezerwują sami, a 100% wpłat trafia od ręki na Wasze konto | Kalendarz sam pilnuje grafiku i zadatków bez prowizji}. {Przygotować bezpłatne demo | Podesłać darmowy podgląd}, jak {wyglądałoby to | działałoby to} u Państwa?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Z tej strony Krzysztof | Tu Krzysztof}. {PORA: W piątek | W piątkowe popołudnie | W piątkowy wieczór} {krótko i na temat: | krótka sprawa: | konkretnie:} {turyści planujący wyjazdy wolą kliknąć termin i opłacić pobyt z telefonu bez czekania | klienci szukają noclegów ze smartfona i wolą od razu wpłacić zadatek BLIKiem | większość osób rezerwuje wyjazdy z telefonu w biegu}. {Wdrażam kalendarze z BLIKiem bez pośredników | Tworzę proste narzędzia rezerwacji 24/7 | Buduję niezależne kalendarze na telefon}. {Podesłać darmowe demo wizualne | Mogę przygotować bezpłatny podgląd} {dla Państwa | u Państwa | pod Państwa obiekt}?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Krzysztof z tej strony | Tu Krzysztof}. {Buduję dla gospodarzy bezobsługowe kalendarze rezerwacji na telefon | Wdrażam dla kwater bezpośrednie systemy rezerwacji ze smartfona | Uruchamiam proste moduły z BLIKiem dla obiektów}. {System przyjmuje wpłaty 24/7 bezpośrednio na Państwa konto, bez oddawania prowizji portalom | Goście rezerwują w 30 sekund, a 100% kwoty trafia do Waszej kieszeni | Koniec z wiszeniem na telefonie o wolne terminy}. {Mogę podesłać darmowe demo wizualne | Przygotować bezpłatny podgląd}, jak {wyglądałoby to | prezentowałoby się to} u Państwa?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Tu Krzysztof | Z tej strony Krzysztof}. {Czy w Państwa obiekcie | Czy u Państwa | Czy w Państwa kwaterze} {goście mogą już | turyści mogą już | macie już u siebie opcję, by} {rezerwować pobyt bezpośrednio z telefonu bez dzwonienia | wpłacać zadatki BLIKiem online 24/7 | sprawdzić wolne pokoje i zarezerwować ze smartfona}? {Gość sam sprawdza grafik i płaci zadatek, a 100% zysku zostaje w Państwa kieszeni | Pełna kwota trafia prosto do Was bez prowizji portali | Zyskujecie spokój od telefonów w weekend}. {Podesłać darmowe demo przygotowane pod Państwa obiekt | Przygotować bezpłatną wizualizację}?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Krzysztof z tej strony | Tu Krzysztof}. {PORA: W piątek | W piątkowe popołudnie | W piątkowy wieczór} {krótka sprawa: | prosto do rzeczy: | krótko i konkretnie:} {wdrażam dla właścicieli noclegów własne moduły rezerwacji z telefonu bez oddawania prowizji pośrednikom | pomagam kwaterom uruchomić bezpośrednie rezerwacje z BLIKiem | buduję proste systemy rezerwacji 24/7 bez portali}. {Przygotować darmowe demo wizualne | Mogę podesłać bezpłatny podgląd} {dla Państwa | u Państwa | pod Państwa obiekt}?""",

    # 5 = SOBOTA
    "5": """{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Tu Krzysztof | Krzysztof z tej strony | Z tej strony Krzysztof}. {W weekendy turyści najczęściej szukają kolejnych wyjazdów w telefonie i wolą od razu zarezerwować termin online | W sobotę turyści masowo przeglądają noclegi na smartfonach | Weekend to czas, kiedy rodziny siadają do telefonów i planują urlopy}. {Wdrażam kalendarze na telefon – goście rezerwują 24/7 z BLIKiem | Tworzę proste moduły rezerwacji ze smartfona | Uruchamiam bezobsługowe kalendarze bez pośredników}, a {100% zysku zostaje u Was bez prowizji portali | cała kwota trafia prosto na Państwa konto | nie oddajecie ani grosza prowizji portalom}. {Podesłać darmowe demo wizualne | Mogę przygotować bezpłatny podgląd} {dla Państwa | u Państwa | pod Państwa obiekt}?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Krzysztof z tej strony | Tu Krzysztof}. {PORA: W sobotę | W sobotnie popołudnie | W sobotni wieczór} {krótko i konkretnie: | prosto do sedna: | konkretne pytanie:} {pomagam gospodarzom uruchomić rezerwacje bezpośrednie z telefonu | wdrażam dla kwater proste systemy rezerwacji z BLIKiem | buduję niezależne moduły rezerwacji bez portali}. {Turyści rezerwują i opłacają pobyt w 30 sekund bezpośrednio na Wasze konto | Goście sami sprawdzają grafik i płacą zadatek o dowolnej porze | Pieniądze wpadają od ręki na Państwa konto}. {Mogę przygotować darmowe demo | Podesłać bezpłatny podgląd wizualny} {dla Państwa | u Państwa | pod Państwa obiekt}?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Tu Krzysztof | Z tej strony Krzysztof | Krzysztof z tej strony}. {Uruchamiam dla kwater i domków | Wdrażam dla gospodarzy | Buduję dla obiektów} {bezobsługowe kalendarze rezerwacji online | bezpośrednie moduły na smartfony z BLIKiem | proste systemy rezerwacji 24/7}. {Zamiast ciągle odbierać telefony o wolne terminy w weekend, system sam przyjmuje rezerwacje i zadatki, a cały zysk zostaje u Was | Turyści rezerwują sami na telefonie, a 100% wpłat trafia do Waszej kieszeni | Zdejmuje to z głowy ciągłe telefony i odpisywanie na wiadomości}. {Podesłać bezpłatne demo wizualne | Przygotować darmowe demo} {dla Państwa | u Państwa | pod Państwa obiekt}?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Z tej strony Krzysztof | Tu Krzysztof}. {Weekend to czas, kiedy najwięcej osób planuje urlopy na smartfonach i wybiera obiekty z natychmiastową rezerwacją online | Turyści coraz częściej rezerwują noclegi w telefonie i chcą potwierdzenia od ręki | Klienci wolą kliknąć termin i zapłacić BLIKiem niż dzwonić z pytaniami}. {Wdrażam kalendarze 24/7 bez prowizji pośredników | Tworzę proste narzędzia rezerwacji na smartfony | Buduję niezależne systemy dla kwater}. {Przygotować darmowe demo | Podesłać bezpłatny podgląd}, jak {wyglądałoby to | działałoby to} u Państwa?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Krzysztof z tej strony | Tu Krzysztof}. {Buduję dla gospodarzy kalendarze rezerwacji noclegów z płatnościami BLIK na telefon | Wdrażam dla obiektów moduły rezerwacji ze smartfona | Tworzę dla kwater bezpośrednie kalendarze online}. {System sam przyjmuje wpłaty 24/7 prosto na Państwa konto, bez prowizji dla portali | Goście rezerwują w kilkadziesiąt sekund, a 100% kwoty zostaje u Was | Nie musicie wisieć na telefonie w weekend}. {Mogę podesłać darmowe demo wizualne | Przygotować bezpłatny podgląd} {dla Państwa | u Państwa | pod Państwa obiekt}?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Tu Krzysztof | Z tej strony Krzysztof}. {Czy w Państwa obiekcie | Czy u Państwa | Czy w Państwa kwaterze} {goście mają już opcję, by | turyści mogą już | macie już wdrożoną możliwość, by} {rezerwować pobyty bezpośrednio z telefonu bez dzwonienia | kliknąć wolny termin i opłacić zadatek BLIKiem | sprawdzić grafik 24/7 i zapłacić ze smartfona}? {Gość klika termin, płaci zadatek, a 100% kwoty zostaje w Państwa kieszeni | Cały zysk trafia do Was bez prowizji portali | Zdejmujecie z głowy setki telefonów}. {Podesłać darmowe demo przygotowane pod Państwa obiekt | Przygotować bezpłatne demo wizualne}?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Krzysztof z tej strony | Tu Krzysztof}. {PORA: W sobotę | W sobotnie popołudnie | W sobotni wieczór} {konkretnie: | prosto do rzeczy: | krótka sprawa:} {wdrażam dla kwater systemy rezerwacji bezpośrednich na telefon (100% zysku bez prowizji portali) | pomagam obiektom noclegowym uruchomić kalendarze z BLIKiem 24/7 | buduję bezobsługowe moduły rezerwacji na smartfony}. {Przygotować darmowe demo wizualne | Mogę przygotować bezpłatny podgląd} {dla Państwa | u Państwa | pod Państwa obiekt}?""",

    # 6 = NIEDZIELA
    "6": """{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Tu Krzysztof | Krzysztof z tej strony | Z tej strony Krzysztof}. {W niedziele turyści masowo planują noclegi w telefonach i wolą od razu kliknąć wolny termin oraz wpłacić zadatek | W niedzielny czas najwięcej rodzin przegląda noclegi ze smartfona | Przed nowym tygodniem goście intensywnie szukają obiektów z rezerwacją online}. {Wdrażam kalendarze rezerwacji online 24/7 – 100% wpłat trafia na Państwa konto bez prowizji pośredników | Tworzę proste moduły rezerwacji z BLIKiem na smartfony | Uruchamiam dla kwater bezobsługowe kalendarze rezerwacji}, a {pełny zysk zostaje w Państwa kieszeni | oszczędzacie na prowizjach portali | nie musicie odbierać telefonów o wolne terminy}. {Podesłać darmowe demo wizualne | Mogę przygotować bezpłatny podgląd} {dla Państwa | u Państwa | pod Państwa obiekt}?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Krzysztof z tej strony | Tu Krzysztof}. {PORA: W niedzielę | W niedzielne popołudnie | W niedzielny wieczór} {krótko i konkretnie: | prosto do rzeczy: | krótka sprawa:} {pomagam obiektom noclegowym uruchomić bezpośrednie rezerwacje z telefonu | wdrażam dla gospodarzy proste kalendarze z płatnościami BLIK | pomagam kwaterom uniezależnić się od prowizji portali}. {Turyści rezerwują w kilkadziesiąt sekund z BLIKiem prosto do Państwa | Goście sami sprawdzają grafik i wpłacają zadatki 24/7 | Pieniądze natychmiast trafiają na Wasze konto}. {Mogę przygotować darmowe demo | Podesłać bezpłatny podgląd wizualny} {dla Państwa | u Państwa | pod Państwa obiekt}?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Tu Krzysztof | Z tej strony Krzysztof | Krzysztof z tej strony}. {Uruchamiam dla kwater i domków | Wdrażam dla gospodarzy | Buduję dla obiektów} {bezobsługowe kalendarze rezerwacji na telefon | proste systemy bezpośrednich rezerwacji online 24/7 | moduły z płatnościami BLIK bez pośredników}. {Zdejmują z głowy ciągłe odpisywanie na zapytania, a pełna kwota za pobyt zostaje u właściciela bez prowizji | Turyści rezerwują sami, a 100% zysku trafia bezpośrednio na Wasze konto | Koniec z ręcznym podawaniem numeru konta i sprawdzaniem kajetu}. {Przygotować darmowe demo | Podesłać bezpłatną wizualizację} {dla Państwa | u Państwa | pod Państwa obiekt}?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Z tej strony Krzysztof | Tu Krzysztof}. {PORA: W niedzielę | W niedzielne popołudnie | W niedzielny wieczór} {najwięcej osób rezerwuje wyjazdy ze smartfona i woli od razu opłacić zadatek | turyści wybierają obiekty z natychmiastową rezerwacją online na telefonie | goście wolą kliknąć termin i zapłacić BLIKiem niż czekać na telefon}. {Wdrażam dla gospodarzy niezależne kalendarze 24/7 z płatnościami BLIK, bez oddawania kilkunastu procent portalom | Buduję proste narzędzia rezerwacji na telefon dla kwater | Tworzę systemy rezerwacji bez prowizji}. {Podesłać darmowe demo wizualne | Mogę przygotować bezpłatny podgląd} {dla Państwa | u Państwa | pod Państwa obiekt}?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Krzysztof z tej strony | Tu Krzysztof}. {Buduję dla gospodarzy proste kalendarze rezerwacji noclegów | Wdrażam dla obiektów bezpośrednie moduły rezerwacji z telefonu | Przygotowuję dla kwater kalendarze 24/7 z BLIKiem}. {System przyjmuje zadatki całą dobę prosto na Państwa konto, a turyści rezerwują bez pośredników | Gość rezerwuje w 30 sekund ze smartfona, a 100% kwoty zostaje u Was | Zyskujecie pełny zysk bez prowizji portali i spokój od telefonów}. {Mogę podesłać darmowe demo | Podesłać bezpłatny podgląd}, jak {wyglądałoby to | działałoby to} u Państwa?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Tu Krzysztof | Z tej strony Krzysztof}. {Czy w Państwa obiekcie | Czy u Państwa w kwaterze | Czy w Państwa domkach} {goście mają już opcję, by | turyści mogą już | macie już wdrożoną opcję, by} {rezerwować pobyt bezpośrednio z telefonu bez dzwonienia | sprawdzić grafik i zapłacić zadatek BLIKiem online | zarezerwować wolny termin o dowolnej porze ze smartfona}? {Gość sam sprawdza grafik i płaci zadatek, a 100% zysku zostaje w Państwa kieszeni bez prowizji portali | Pieniądze natychmiast trafiają na Wasze konto bez pośredników | Oszczędzacie na prowizjach i nie musicie odbierać telefonów}. {Podesłać darmowe demo przygotowane pod Państwa obiekt | Przygotować bezpłatny podgląd wizualny}?
---
{PORA: Dzień dobry | Dzień dobry | Dobry wieczór}! {Krzysztof z tej strony | Tu Krzysztof}. {Przed startem nowego tygodnia krótko i do rzeczy: | Konkretna sprawa przed nowym tygodniem: | Na koniec weekendu krótkie pytanie:} {wdrażam dla kwater systemy rezerwacji bezpośrednich z telefonu (płatności 24/7 bez prowizji portali) | pomagam obiektom noclegowym uruchomić kalendarze z BLIKiem na smartfony | tworzę proste bezobsługowe moduły rezerwacji}. {100% zysku zostaje u Was, a goście rezerwują w kilkadziesiąt sekund | Pełna kwota trafia do Was bez prowizji portali | Oszczędzacie na prowizjach i zyskujecie święty spokój}. {Przygotować darmowe demo wizualne | Mogę przygotować darmowy podgląd} {dla Państwa | dla Państwa obiektu}?""",

}


# ──────────────────────────────────────────────
# ŚCIEŻKI DANYCH (TRWAŁY WOLUMEN COOLIFY)
# ──────────────────────────────────────────────
DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).resolve().parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = DATA_DIR / "sms_state.json"
SENT_NUMBERS_FILE = DATA_DIR / "sent_numbers.json"
OUTBOUND_SMS_LOG_FILE = DATA_DIR / "outbound_cold_sms.jsonl"
AUTOMATION_BACKEND_URL = os.environ.get(
    "AUTOMATION_BACKEND_URL",
    "http://brosystems-automation-backend:8000",
).rstrip("/")


def record_outbound_cold_sms_context(
    phone: str,
    clean_text: str,
    sim_label: str,
    name: str = "",
    city: str = "",
) -> None:
    """
    Zapisuje dokładną treść pierwszego wysłanego SMS-a dla Agenta AI w Chatwoocie:
    1. Trwale do lokalnego pliku JSONL na wolumenie,
    2. Nieblokująco (w osobnym wątku, timeout 2.5s) do automation-backend (/api/outbound-sms).
    """
    entry = {
        "phone": phone,
        "message_text": clean_text,
        "sim_label": sim_label,
        "name": name,
        "city": city,
        "sent_at": time.time(),
    }
    try:
        with OUTBOUND_SMS_LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        print(f"Ostrzeżenie zapisu outbound_cold_sms.jsonl: {exc}")

    def _notify_backend() -> None:
        for base_u in (
            AUTOMATION_BACKEND_URL,
            "https://brosystems.pl/podglad",
            "https://demo.brosystems.pl",
            "http://127.0.0.1:8000",
        ):
            if not base_u:
                continue
            try:
                r = requests.post(f"{base_u}/api/outbound-sms", json=entry, timeout=2.5)
                if r.status_code < 300:
                    break
            except Exception:
                continue

    threading.Thread(target=_notify_backend, daemon=True).start()

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
    "templates_version": TEMPLATES_VERSION,
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

            # Upewnij się, że wszystkie 7 dni tygodnia mają szablony oraz aktualną wersję bez oksymoronów
            raw_tpl_ver = s.get("templates_version")
            try:
                saved_tpl_ver = int(raw_tpl_ver) if raw_tpl_ver is not None else 0
            except (ValueError, TypeError):
                saved_tpl_ver = 0

            if not isinstance(state.get("daily_templates"), dict) or saved_tpl_ver < TEMPLATES_VERSION:
                state["daily_templates"] = DEFAULT_DAILY_TEMPLATES.copy()
                state["templates_version"] = TEMPLATES_VERSION
                _log("✨ Zaktualizowano szablony 7 dni do wersji v6 (Naturalny język bez sztucznej personalizacji {Name}, twarde powitanie pory dnia).")
                save_state()
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
            if saved_tpl_ver < TEMPLATES_VERSION:
                save_state()
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
# INTELIGENTNE POWITANIA I STRAŻNIK ANTY-OKSYMORONOWY
# ──────────────────────────────────────────────
DAYS_STEMS = {
    "poniedziałek": ("poniedziałkowy", "poniedziałkowe", "poniedziałkowego", "poniedziałkowym"),
    "wtorek": ("wtorkowy", "wtorkowe", "wtorkowego", "wtorkowym"),
    "środa": ("środowy", "środowe", "środowego", "środowym"),
    "czwartek": ("czwartkowy", "czwartkowe", "czwartkowego", "czwartkowym"),
    "piątek": ("piątkowy", "piątkowe", "piątkowego", "piątkowym"),
    "sobota": ("sobotni", "sobotnie", "sobotniego", "sobotnim"),
    "niedziela": ("niedzielny", "niedzielne", "niedzielnego", "niedzielnym"),
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
        slot_index = 0
    elif total_min < 17 * 60:
        greetings = ["Dzień dobry", "Witam serdecznie", "Witam", "Cześć"]
        pora_dnia = "popołudnie"
        pora_opis = "popołudnie"
        slot_index = 1
    else:
        # Od 17:00 (wieczór)
        greetings = ["Dobry wieczór", "Witam serdecznie", "Witam"]
        pora_dnia = "wieczór"
        pora_opis = "wieczór"
        slot_index = 2

    return {
        "dt": dt,
        "hour": hour,
        "total_min": total_min,
        "slot_index": slot_index,       # 0 = rano, 1 = popołudnie, 2 = wieczór
        "is_morning": slot_index == 0,
        "is_afternoon": slot_index == 1,
        "is_evening": slot_index == 2,
        "is_late_for_coffee": total_min >= 14 * 60 + 30,  # Od 14:30 zero wzmianek o kawie!
        "greetings": greetings,
        "greeting": random.choice(greetings),
        "pora_dnia": pora_dnia,
        "pora_opis": pora_opis,
    }


def adapt_time_of_day(text: str, dt: datetime | None = None) -> str:
    """
    Twardy Strażnik Anty-Oksymoronowy:
    1. Od 14:30 wycina wszelkie wzmianki o kawie ('spokojna kawa', 'przy kawie' itp.) zamieniając na 'chwilę oddechu' / 'w wolnej chwili'.
    2. Od 17:00 (wieczór) zamienia 'Dzień dobry' na 'Dobry wieczór' oraz wszystkie przypadki słów
       'poranek', 'przedpołudnie', 'koło południa', 'popołudnie' na naturalne odpowiedniki wieczorne.
    3. W popołudnie (12:00-17:00) zamienia zwroty poranne/przedpołudniowe (we wszystkich przypadkach) na popołudniowe.
    4. Rano (przed 12:00) pilnuje, by nie pojawił się 'Dobry wieczór', 'popołudnie' lub 'wieczór'.
    """
    tod = get_time_of_day_context(dt)
    is_morning = tod["is_morning"]
    is_afternoon = tod["is_afternoon"]
    is_evening = tod["is_evening"]
    no_coffee = tod["is_late_for_coffee"]

    def _replace_keep_case(pattern: str, replacement: str, string: str) -> str:
        def _cb(m):
            matched = m.group(0)
            rep = replacement
            if matched and matched[0].isupper():
                rep = rep[0].upper() + rep[1:]
            return rep
        return re.sub(pattern, _cb, string, flags=re.IGNORECASE)

    # ── 1. CAŁKOWITA ELIMINACJA "KAWY" PO GODZINIE 14:30 (POPOŁUDNIE I WIECZÓR) ──
    if no_coffee:
        text = _replace_keep_case(r"\bna\s+spokojniejszą\s+kawę\b", "na chwilę wytchnienia", text)
        text = _replace_keep_case(r"\bna\s+spokojną\s+kawę\s+i\s+podsumowanie\b", "na chwilę oddechu i podsumowanie", text)
        text = _replace_keep_case(r"\bna\s+(spokojną|poranną|szybką|małą|krótką)?\s*kawę\b", "na chwilę wytchnienia", text)
        text = _replace_keep_case(r"\bchwila\s+na\s+(spokojną\s+)?kawę\b", "chwila wytchnienia", text)
        text = _replace_keep_case(r"\bmoment\s+na\s+(spokojniejszą\s+|spokojną\s+)?kawę\b", "moment na chwilę spokoju", text)
        text = _replace_keep_case(
            r"\bprzy\s+(poniedziałkowej|wtorkowej|środowej|czwartkowej|piątkowej|sobotniej|niedzielnej|weekendowej|porannej|popołudniowej|spokojnej)?\s*kawie\b",
            "w wolnej chwili",
            text,
        )
        text = _replace_keep_case(r"\bkaw(a|y|ie|ę|ą)\b", "odpoczynek", text)

    # ── 2. ADAPTACJA POWITAŃ ──
    if is_evening:
        text = _replace_keep_case(r"\b[Dd]zień dobry\b", "Dobry wieczór", text)
    else:
        text = _replace_keep_case(r"\b[Dd]obry wieczór\b", "Dzień dobry", text)

    # ── 3. ADAPTACJA PÓR DNIA WE WSZYSTKICH PRZYPADKACH GRAMATYCZNYCH ──
    for day_noun, (masc, neut, gen, _) in DAYS_STEMS.items():
        prep_w = "we" if masc.startswith("wtork") else "w"
        if is_evening:
            # Mianownik / Biernik (np. wtorkowy poranek, wtorkowe przedpołudnie, wtorkowe popołudnie -> wtorkowy wieczór)
            text = _replace_keep_case(rf"\bwe?\s+{neut}\s+(przedpołudnie|popołudnie)\b", f"{prep_w} {masc} wieczór", text)
            text = _replace_keep_case(rf"\b{masc}\s+poranek\b", f"{masc} wieczór", text)
            text = _replace_keep_case(rf"\b{neut}\s+(przedpołudnie|popołudnie)\b", f"{masc} wieczór", text)
            # Dopełniacz (np. luźniejszego wtorkowego przedpołudnia -> spokojniejszego wtorkowego wieczoru)
            text = _replace_keep_case(rf"\b{gen}\s+(poranka|przedpołudnia|popołudnia)\b", f"{gen} wieczoru", text)
            text = _replace_keep_case(rf"\b{day_noun}\s+(o|około|koło|przed)\s+południa\b", f"{masc} wieczór", text)
        elif is_afternoon:
            # Mianownik / Biernik (np. wtorkowy poranek, wtorkowe przedpołudnie -> wtorkowe popołudnie)
            text = _replace_keep_case(rf"\bwe?\s+{neut}\s+przedpołudnie\b", f"{prep_w} {neut} popołudnie", text)
            text = _replace_keep_case(rf"\b{masc}\s+(poranek|wieczór)\b", f"{neut} popołudnie", text)
            text = _replace_keep_case(rf"\b{neut}\s+przedpołudnie\b", f"{neut} popołudnie", text)
            # Dopełniacz (np. wtorkowego przedpołudnia -> wtorkowego popołudnia)
            text = _replace_keep_case(rf"\b{gen}\s+(poranka|przedpołudnia|wieczoru)\b", f"{gen} popołudnia", text)
        elif is_morning:
            # Rano pilnuj, by nie wyszło "niedzielne popołudnie" czy "wtorkowy wieczór"
            text = _replace_keep_case(rf"\b{neut}\s+popołudnie\b", f"{neut} przedpołudnie", text)
            text = _replace_keep_case(rf"\b{masc}\s+wieczór\b", f"{masc} poranek", text)
            text = _replace_keep_case(rf"\b{gen}\s+(popołudnia|wieczoru)\b", f"{gen} przedpołudnia", text)

    # ── 4. OGÓLNE ZWROTY PORY DNIA BEZ PRZYMIOTNIKA DNIA ──
    if is_evening:
        text = _replace_keep_case(r"\bpora\s+(o|około|koło)\s+południa\b", "wieczorna pora", text)
        text = _replace_keep_case(r"\b(o|około|koło)\s+południa\b", "wieczorem", text)
        text = _replace_keep_case(r"\bprzed\s+południem\b", "wieczorem", text)
        text = _replace_keep_case(r"\bpo\s+południu\b", "wieczorem", text)
        text = _replace_keep_case(r"\bwe?\s+przedpołudnie\b", "wieczorem", text)
        text = _replace_keep_case(r"\bprzedpołudnia\b", "wieczoru", text)
        text = _replace_keep_case(r"\bprzedpołudnie\b", "wieczór", text)
        text = _replace_keep_case(r"\bpopołudnia\b", "wieczoru", text)
        text = _replace_keep_case(r"\bpopołudnie\b", "wieczór", text)
        text = _replace_keep_case(r"\bporanek\b", "wieczór", text)
        text = _replace_keep_case(r"\bporann(e|ych)\s+sprawy\b", "dzisiejsze sprawy", text)
    elif is_afternoon:
        text = _replace_keep_case(r"\bpora\s+(o|około|koło)\s+południa\b", "popołudniowa pora", text)
        text = _replace_keep_case(r"\bprzed\s+południem\b", "po południu", text)
        text = _replace_keep_case(r"\bwe?\s+przedpołudnie\b", "po południu", text)
        text = _replace_keep_case(r"\bprzedpołudnia\b", "popołudnia", text)
        text = _replace_keep_case(r"\bprzedpołudnie\b", "popołudnie", text)
        text = _replace_keep_case(r"\bporanek\b", "popołudnie", text)
        text = _replace_keep_case(r"\bporann(e|ych)\s+sprawy\b", "bieżące sprawy", text)

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
    smart_greeting = context.get("smart_greeting", state.get("smart_greeting_enabled", True))

    def replace_var(m):
        var_name = m.group(1).lower()
        fallback = m.group(2) if m.group(2) is not None else ""
        if var_name == "name":
            return name if name else fallback
        elif var_name == "city":
            return city if city else fallback
        return m.group(0)

    text = re.sub(r"\{(Name|City)(?::([^}]*))?\}", replace_var, text, flags=re.IGNORECASE)

    # 1. Warunkowe bloki pory dnia: {PORA: rano | popołudnie | wieczór}
    def replace_pora_block(m):
        parts = [p.strip() for p in m.group(1).split("|")]
        if not parts:
            return ""
        if not smart_greeting:
            return parts[0]
        idx = min(tod["slot_index"], len(parts) - 1)
        return parts[idx]

    text = re.sub(r"\{PORA:([^{}]+)\}", replace_pora_block, text, flags=re.IGNORECASE)

    # 2. Dynamiczne tagi pory dnia i powitania: {Powitanie}, {Greeting}, {Pora_dnia}, {Pora_opis}
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

    # 3. Strażnik anty-oksymoronowy (eliminuje "wieczorną kawę", "poranek" wieczorem itp.)
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
                    "message_text": text_spun,
                }
                record_outbound_cold_sms_context(
                    phone=phone,
                    clean_text=text_spun,
                    sim_label=sim_info["label"],
                    name=parsed.get("name", ""),
                    city=parsed.get("city", ""),
                )
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
            "templates_version": state.get("templates_version", TEMPLATES_VERSION),
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
            state["templates_version"] = TEMPLATES_VERSION
            _log("🔄 Przywrócono domyślne szablony SMS dla wszystkich 7 dni tygodnia.")
        elif day_key in DEFAULT_DAILY_TEMPLATES:
            state["daily_templates"][day_key] = DEFAULT_DAILY_TEMPLATES[day_key]
            state["templates_version"] = TEMPLATES_VERSION
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