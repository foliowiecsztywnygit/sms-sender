import pathlib, pandas as pd, re

scratch_dir = pathlib.Path(r"C:\Users\mzebr\.gemini\antigravity-ide\brain\648e176f-7d16-4598-8a25-0f1915a4c236\scratch")
df = pd.read_csv("merged_bez_strony.csv", encoding="utf-8")

def get_coords(u):
    if pd.isna(u): return None, None
    m = re.search(r"@([0-9\.]+),([0-9\.]+)", str(u))
    if m: return float(m.group(1)), float(m.group(2))
    return None, None

coords = [get_coords(u) for u in df["google_maps_url"]]
df["lat"] = [c[0] for c in coords]
df["lon"] = [c[1] for c in coords]

# Canonical Podhale places
podhale_canonical = [
    "Zakopane", "Kościelisko", "Witów", "Dzianisz",
    "Poronin", "Murzasichle", "Suche", "Ząb", "Małe Ciche", "Bustryk", "Nowe Bystre",
    "Bukowina Tatrzańska", "Białka Tatrzańska", "Brzegi", "Czarna Góra", "Groń", "Jurgów", "Rzepiska", "Leśnica",
    "Biały Dunajec", "Gliczarów Górny", "Gliczarów Dolny", "Sierockie", "Leszczyny",
    "Nowy Targ",
    "Gronków", "Ostrowsko", "Łopuszna", "Waksmund", "Klikuszowa", "Obidowa", "Pyzówka", "Lasek", "Krauszów",
    "Długopole", "Knurów", "Ludźmierz", "Morawczyna", "Nowa Biała", "Rogoźnik", "Szlembark", "Dębno", "Harklowa", "Krempachy",
    "Szaflary", "Bańska Niżna", "Bańska Wyżna", "Maruszyna", "Skrzypne", "Zaskale", "Bór",
    "Czarny Dunajec", "Chochołów", "Ciche", "Czerwienne", "Koniówka", "Odrowąż", "Piekielnik", "Pieniążkowice",
    "Podczerwone", "Podszkle", "Ratułów", "Stare Bystre", "Wróblówka", "Załuczne"
]

# Dictionary of standard inflections (miejscownik / w czym / gdzie)
inflections = {
    "Zakopane": "Zakopanem",
    "Kościelisko": "Kościelisku",
    "Witów": "Witowie",
    "Dzianisz": "Dzianiszu",
    "Poronin": "Poroninie",
    "Murzasichle": "Murzasichlu",
    "Suche": "Suchem",
    "Ząb": "Zębie",
    "Małe Ciche": "Małym Cichem",
    "Bustryk": "Bustryku",
    "Nowe Bystre": "Nowym Bystrem",
    "Bukowina Tatrzańska": "Bukowinie Tatrzańskiej",
    "Białka Tatrzańska": "Białce Tatrzańskiej",
    "Brzegi": "Brzegach",
    "Czarna Góra": "Czarnej Górze",
    "Groń": "Groniu",
    "Jurgów": "Jurgowie",
    "Rzepiska": "Rzepiskach",
    "Leśnica": "Leśnicy",
    "Biały Dunajec": "Białym Dunajcu",
    "Gliczarów Górny": "Gliczarowie Górnym",
    "Gliczarów Dolny": "Gliczarowie Dolnym",
    "Sierockie": "Sierockiem",
    "Leszczyny": "Leszczynach",
    "Nowy Targ": "Nowym Targu",
    "Gronków": "Gronkowie",
    "Ostrowsko": "Ostrowsku",
    "Łopuszna": "Łopusznej",
    "Waksmund": "Waksmundzie",
    "Klikuszowa": "Klikuszowej",
    "Obidowa": "Obidowej",
    "Pyzówka": "Pyzówce",
    "Lasek": "Lasku",
    "Krauszów": "Krauszowie",
    "Długopole": "Długopolu",
    "Knurów": "Knurowie",
    "Ludźmierz": "Ludźmierzu",
    "Morawczyna": "Morawczynie",
    "Nowa Biała": "Nowej Białej",
    "Rogoźnik": "Rogoźniku",
    "Szlembark": "Szlembarku",
    "Dębno": "Dębnie",
    "Harklowa": "Harklowej",
    "Krempachy": "Krempachach",
    "Szaflary": "Szaflarach",
    "Bańska Niżna": "Bańskiej Niżnej",
    "Bańska Wyżna": "Bańskiej Wyżnej",
    "Maruszyna": "Maruszynie",
    "Skrzypne": "Skrzypnem",
    "Zaskale": "Zaskalu",
    "Bór": "Borze",
    "Czarny Dunajec": "Czarnym Dunajcu",
    "Chochołów": "Chochołowie",
    "Ciche": "Cichem",
    "Czerwienne": "Czerwiennem",
    "Koniówka": "Koniówce",
    "Odrowąż": "Odrowążu",
    "Piekielnik": "Piekielniku",
    "Pieniążkowice": "Pieniążkowicach",
    "Podczerwone": "Podczerwonem",
    "Podszkle": "Podszklu",
    "Ratułów": "Ratułowie",
    "Stare Bystre": "Starym Bystrem",
    "Wróblówka": "Wróblówce",
    "Załuczne": "Załucznem"
}

def clean_and_match(row):
    p_orig = str(row["miejscowosc"]).strip() if pd.notna(row["miejscowosc"]) else ""
    p_clean = p_orig.replace("،", "").replace("|", " ").strip()
    
    # Check known coordinate fixes
    if row.name == 18842: # Domki Gliczarów
        return True, "Gliczarów Górny"
    if row.name == 18870: # Pokoje u Marii&Mariana Mąka
        return True, "Bańska Wyżna"
    if p_clean == "Zakopane":
        return True, "Zakopane"
    if p_clean == "parter" and 49.35 <= row["lat"] <= 49.45:
        return True, "Białka Tatrzańska"
    if p_clean == "Stanisława" and 49.25 <= row["lat"] <= 49.34:
        return True, "Kościelisko"
    if p_clean == "Boczne" and 49.25 <= row["lat"] <= 49.34:
        return True, "Zakopane"
    if p_clean == "Bolechowice" and 49.25 <= row["lat"] <= 49.34:
        return True, "Kościelisko"
        
    tokens = [t.strip() for t in re.split(r"[,/]", p_clean)]
    for tok in tokens:
        for c in podhale_canonical:
            if tok.lower() == c.lower():
                return True, c
                
    return False, None

matches = []
for idx, r in df.iterrows():
    is_p, matched_canonical = clean_and_match(r)
    matches.append((is_p, matched_canonical))

df["is_podhale"] = [m[0] for m in matches]
df["canonical_town"] = [m[1] for m in matches]

podhale_df = df[df["is_podhale"]].copy()
print(f"Total Podhale records found: {len(podhale_df)}")

# Filter to records with phone
podhale_with_phone = podhale_df[podhale_df["telefon_sms"].notna()].copy()
print(f"Podhale records with valid telefon_sms: {len(podhale_with_phone)}")
print(f"Unique telefon_sms count: {podhale_with_phone['telefon_sms'].nunique()}")

# Normalize miejscowosc and miejscowosc_odmieniona to clean canonical Polish forms
podhale_with_phone["miejscowosc"] = podhale_with_phone["canonical_town"]
podhale_with_phone["miejscowosc_odmieniona"] = podhale_with_phone["canonical_town"].map(inflections)

# Clear telefon_stacjonarny (same as filter_csv.py and rekordy_do_wysylki_od_6129.csv)
podhale_with_phone["telefon_stacjonarny"] = ""

# Drop helper columns
podhale_ready = podhale_with_phone[["nazwa", "miejscowosc", "miejscowosc_odmieniona", "telefon_sms", "telefon_stacjonarny", "google_maps_url", "place_id", "batch_nr", "zrodlo", "canonical_town"]].copy()

# Sort: first by ranking of towns (most offers to fewest offers), then by nazwa
city_counts = podhale_ready["canonical_town"].value_counts()
podhale_ready["city_rank"] = podhale_ready["canonical_town"].map(city_counts)
podhale_ready = podhale_ready.sort_values(by=["city_rank", "canonical_town", "nazwa"], ascending=[False, True, True])

# Clean helper columns before final save
podhale_final = podhale_ready.drop(columns=["canonical_town", "city_rank"])

# Save CSV
output_csv = pathlib.Path("rekordy_podhale_do_wysylki.csv")
podhale_final.to_csv(output_csv, index=False, encoding="utf-8")
print(f"Saved {len(podhale_final)} rows to {output_csv.resolve()}")

# Also generate city ranking summary
ranking_list = []
for c_name, cnt in city_counts.items():
    sub_c = podhale_ready[podhale_ready["canonical_town"] == c_name]
    u_nums = sub_c["telefon_sms"].nunique()
    ranking_list.append({"miejscowosc": c_name, "liczba_ofert": cnt, "unikalne_numery": u_nums})

ranking_df = pd.DataFrame(ranking_list)
output_ranking = pathlib.Path("miasta_ranking_podhale.csv")
ranking_df.to_csv(output_ranking, index=False, encoding="utf-8")
print(f"Saved ranking of {len(ranking_df)} towns to {output_ranking.resolve()}")
