from pytrends.request import TrendReq
import requests
import re
import time
import unicodedata

# Inicializar PyTrends
pytrends = TrendReq(hl='pt-PT', tz=360)

# Termos base para explorar — genéricos e ligados à política
termos_base =   ["PAN", "'Inês de sousa real'","Pessoas–Animais–Natureza"]


# Função para obter sugestões de autocomplete do Google
def google_suggestions(term):
    url = f"http://suggestqueries.google.com/complete/search?client=firefox&hl=pt&gl=pt&q={term}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return data[1]
    return []

# Função para converter string em hashtag
def to_hashtag(text):
    nfkd = unicodedata.normalize('NFKD', text)
    no_accents = "".join([c for c in nfkd if not unicodedata.combining(c)])
    clean = re.sub(r"[^A-Za-z0-9 ]+", "", no_accents)
    parts = clean.strip().split()
    return "#" + "".join([p.capitalize() for p in parts]) if parts else ""

# Obter termos populares a partir dos termos base
termos_populares = set()
for termo in termos_base:
    sugestoes = google_suggestions(termo)
    for s in sugestoes:
        termos_populares.add(s)
    time.sleep(0.5)

# Converter para hashtags e expressões OR
hashtags = [to_hashtag(t) for t in termos_populares if len(t) > 2]
termos_ou = [f'"{t}"' for t in termos_populares]
hashtags_ou = [h for h in hashtags if h != "#"]

# Montar a query para Twitter
query = f"({' OR '.join(termos_ou + hashtags_ou)}) since:2024-09-01 until:2025-04-21 lang:pt"

# Mostrar resultado
print("Query para Twitter:")
print(query)
