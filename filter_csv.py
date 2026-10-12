import pandas as pd

# Wczytanie pliku CSV
df = pd.read_csv('merged_bez_strony.csv')

# Usunięcie pozycji bez telefonu (zakładając, że telefon do SMS jest w kolumnie telefon_sms)
# Pozostawiamy tylko wiersze, gdzie telefon_sms nie jest puste
df = df.dropna(subset=['telefon_sms'])

# Wyczyszczenie kolumny telefon_stacjonarny (usunięcie numerów stacjonarnych)
df['telefon_stacjonarny'] = ''

# Zapisanie do nowego pliku
df.to_csv('merged_bez_strony_z_telefonami_bez_stacjonarnych.csv', index=False)

print("Gotowe! Wynik zapisano w pliku merged_bez_strony_z_telefonami_bez_stacjonarnych.csv")
