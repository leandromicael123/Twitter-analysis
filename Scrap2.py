import signal
import sys
import time
import re
import random
import pandas as pd
import metric_extraction as me
import urllib.parse
import metric_extraction
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.edge.options import Options as EdgeOptions  # ALTERAÇÃO
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException

# === Configurações ===
CHROMEDRIVER_PATH = r"C:\\Users\\ferol\\.wdm\\drivers\\chromedriver\\win64\\135.0.7049.95\\chromedriver-win32\\chromedriver.exe"
EDGEDRIVER_PATH    = r"C:\\Users\\ferol\\.wdm\\drivers\\edgedriver\\win64\\136.0.3240.14\\msedgedriver.exe"
USER_DATA_DIR     = r"C:\\Users\\ferol\\AppData\\Local\\Google\\Chrome\\User Data"
PROFILE           = "Default"
TWEETS_PER_CANDIDATE = 1000 # 
SCROLL_PAUSE      = 2
WAIT_TIMEOUT      = 30
WAIT_RETRY_MINUTES = 5
OUTPUT_CSV        = 'twitter/tweets_eleicoes.csv'

# Limites para alternância de query
MIN_TWEETS_BEFORE_SWITCH = 50
MAX_TWEETS_BEFORE_SWITCH = 300

candidates_queries = {
    'Inês de Sousa Real': ['PAN partido OR "Inês Sousa Real" OR "Pessoas-Animais-Natureza" -sexualidade -pansexual ',"PAN -sexualidade -pansexual"],
    'Rui Rocha': ["iniciativa liberal", "Rui Rocha", "#RuiRocha", "#IniciativaLiberal","#IL"],
    'Pedro Nuno Santos': [
        "partido socialista portugal", "PS",  "#PedroNunoSantos", "#PS", "Partido Socialista",
        "Pedro Nuno Santos PS", "Pedro Nuno Santos Partido Socialista"],

    'André Ventura': [
       "André Ventura","PartidoCHEGA", "chega", "CHEGA","chega!","#Chega","#AndréVentura","chega portugal"
    ],
    'Mariana Mortágua': [
         "BlocoDeEsquerda","Mariana Mortágua", "Bloco de Esquerda", "#MarianaMortágua", "#BE", "#BlocoDeEsquerda",
         "bloco de esquerda fundadores"
     ],
    'Paulo Raimundo': [
         "PCP_PT","Paulo Raimundo", "PCP", "#PauloRaimundo", "#PCP", "Partido Comunista Português",
         "Paulo Raimundo PCP", "Paulo Raimundo Partido Comunista Português"],
    'Rui Tavares': [
        "LIVREPT","Rui Tavares", "Livre", "#RuiTavares", "#Livre", "Rui Tavares Livre", 
        "Rui Tavares partido livre", "Rui Tavares partido livre", "Rui Tavares Livre"],
    'Luis Montenegro': [
        "Luis Montenegro", "PSD","Aliança Democrática","AD" ,"psd portugal", "#LuisMontenegro", "#PSD", "Partido Social Democrata",
        "Luis Montenegro PSD", "Luis Montenegro Partido Social Democrata"],
}

stop_scraping = False

# Handler de sinal para interrupção
def signal_handler(sig, frame):
    global stop_scraping
    print("\nInterrupção recebida: finalizando após o lote atual e salvando...")
    stop_scraping = True

signal.signal(signal.SIGINT, signal_handler)

def extrair_id(url):
    m = re.search(r"/status/(\d+)", url)
    return m.group(1) if m else None

multipliers = {'K': 1_000, 'M': 1_000_000, 'MIL': 1_000, 'MILHÃO': 1_000_000}

def parse_count(cnt):
    if not cnt: return 0
    cnt = cnt.strip().upper().replace(',', '.').replace(' ', '')
    m = re.match(r"([\d\.]+)([A-ZÀ-ú]+)?", cnt)
    if not m: return 0
    num, suf = m.groups(); val = float(num)
    if suf:
        for k, v in multipliers.items():
            if k in suf:
                return int(val * v)
    return int(val)

def get_tweet_data(el):
    try:
        time_el = el.find_element(By.TAG_NAME, 'time')
        href = el.find_element(By.XPATH, './/a[contains(@href, "/status/")]').get_attribute('href')
        user = el.find_element(By.CSS_SELECTOR, '[data-testid="User-Name"] span').text
        text = el.find_element(By.CSS_SELECTOR, '[data-testid="tweetText"]').text
        return {
            'id': extrair_id(href),
            'user': user,
            'text': text,
            'datetime': time_el.get_attribute('datetime'),
            'time': time_el.text
        }
    except Exception:
        return None

def get_metrics(el):
    out = {'replies': 0, 'retweets': 0, 'likes': 0, 'bookmarks': 0, 'views': 0}
    try:
        # Buscar o subelemento com a classe '.css-175oi2r' e 'role="group"'
        metrics_section = el.find_elements(By.XPATH, './/div[@role="group" and contains(@class, "css-175oi2r")]')
        if not metrics_section:
            print("Métricas não encontradas para este tweet.")  # Mensagem de erro opcional
            return out

        for part in metrics_section:
            aria_label = part.get_attribute('aria-label')  # Obter o atributo aria-label
            if aria_label:
                for metric in aria_label.split(','):  # Separar as métricas por vírgula
                    metric = metric.strip()
                    try:
                        num, name = metric.split(' ', 1)  # Dividir o número e o nome da métrica
                        cnt = parse_count(num)  # Converter o número para inteiro
                        nl = name.lower()

                        # Mapear as métricas para os campos correspondentes
                        if 'replies' in nl or 'respostas' in nl:
                            out['replies'] = cnt
                        elif 'repost' in nl or 'reposts' in nl or 'retweetar' in nl:
                            out['retweets'] = cnt
                        elif 'like' in nl or 'likes' in nl or 'curtidas' in nl:
                            out['likes'] = cnt
                        elif 'bookmark' in nl or 'bookmarks' in nl or 'item salvo' in nl:
                            out['bookmarks'] = cnt
                        elif 'views' in nl or 'visualizações' in nl:
                            out['views'] = cnt
                    except ValueError:
                        continue

    except NoSuchElementException:
        print("Erro: Não foi possível encontrar o subelemento de métricas.")  # Mensagem de erro opcional

    return out


def gerar_intervalos(start_date, end_date, days=7):
    current = start_date
    while current < end_date:
        nxt = current + timedelta(days=days)
        yield current.strftime('%Y-%m-%d'), min(nxt, end_date).strftime('%Y-%m-%d')
        current = nxt


def iniciar_driver(browser='chrome'):
    common_args = [
        f"--user-data-dir={USER_DATA_DIR}",
        f"--profile-directory={PROFILE}",
        "--disable-blink-features=AutomationControlled",
        "--lang=pt"
    ]
    if browser == 'chrome':
        opts = Options()
        for a in common_args: opts.add_argument(a)
        opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.5790.102 Safari/537.36")
        return webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=opts)
    else:
        opts = EdgeOptions()
        opts.use_chromium = True
        for a in common_args: opts.add_argument(a)
        opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.5790.102 Safari/537.36 Edg/115.0.1901.188")
        return webdriver.Edge(service=Service(EDGEDRIVER_PATH), options=opts)

# inicializa driver
current_browser = 'chrome'
driver = iniciar_driver(current_browser)
wait = WebDriverWait(driver, WAIT_TIMEOUT)
all_tweets = []
seen = set()
error_total = 0

try:
    # Verifica se estás autenticado no Twitter sem input()
    driver.get('https://twitter.com/home')
    time.sleep(5)
    page = driver.page_source
    if "Entrar" in page or "Log in" in page:
        print("⚠️ Não autenticado. Verifica o perfil do Chrome e reinicia.")
        driver.quit()
        sys.exit(1)

    search_filters = ['live', 'top']
    start = datetime.strptime("2024-09-01", "%Y-%m-%d")
    end = datetime.now()
    for candidato, hashtags in candidates_queries.items():
        if stop_scraping: break
        tweets_collected = 0  # Variável para contar os tweets coletados por candidato

        while tweets_collected < TWEETS_PER_CANDIDATE:
            # Embaralha as queries para garantir uma distribuição aleatória
            random.shuffle(hashtags)
            query_index = 0

            recent_start = max(start, end - timedelta(days=30))
            recent_int = list(gerar_intervalos(recent_start, end))
            print(f"Intervalos recentes: {recent_int}")
            # Intervalos para tweets antigos
            older_int = list(gerar_intervalos(start, recent_start))
            print(f"Intervalos antigos: {older_int}")
            # Define proporções para tweets recentes e antigos
            recent_target = int(TWEETS_PER_CANDIDATE * 0.75)  # 70% a 80%
            print(f"Proporção de tweets recentes: {recent_target}")
            older_target = TWEETS_PER_CANDIDATE - recent_target  # 20% a 30%
            print(f"Proporção de tweets antigos: {older_target}")

            while query_index < len(hashtags):
                if stop_scraping: break
                base_query = hashtags[query_index]
                error_streak = 0
                print(f"\n[Candidato: {candidato}] Query: {base_query} — Limite: {TWEETS_PER_CANDIDATE - tweets_collected} tweets restantes")

                for intervals, target in [(recent_int, recent_target), (older_int, older_target)]:
                    if stop_scraping: break
                    for d1, d2 in intervals:
                        if stop_scraping: break
                        if tweets_collected >= TWEETS_PER_CANDIDATE: break
                        full_query = f'{base_query} since:{d1} until:{d2} lang:pt'
                        q = urllib.parse.quote(full_query)
                        collected = 0
                        success = False

                        for f in search_filters:
                            if stop_scraping: break
                            try:
                                driver.get(f'https://twitter.com/search?q={q}&f={f}')
                                time.sleep(2 + random.random() * 2)

                                page = driver.page_source
                                if "Este navegador não é mais compatível" in page or "Please switch to a supported browser" in page:
                                    print(f"❗ Unsupported browser em {current_browser} — alternando.")
                                    current_browser = 'edge' if current_browser == 'chrome' else 'chrome'
                                    driver.quit()
                                    driver = iniciar_driver(current_browser)
                                    wait = WebDriverWait(driver, WAIT_TIMEOUT)
                                    driver.get(f'https://twitter.com/search?q={q}&f={f}')
                                    time.sleep(3)

                                last_h = driver.execute_script("return document.body.scrollHeight")
                                while tweets_collected < TWEETS_PER_CANDIDATE and collected < target and not stop_scraping:
                                    wait.until(EC.presence_of_all_elements_located((By.XPATH, '//article[@data-testid="tweet"]')))
                                    tweets = driver.find_elements(By.XPATH, '//article[@data-testid="tweet"]')
                                    for el in tweets:
                                        if stop_scraping: break
                                        try:
                                            el.find_element(By.XPATH, './/span[contains(text(), "Promov")]')
                                            continue
                                        except NoSuchElementException:
                                            pass
                                        data = get_tweet_data(el)
                                        if data and data['id'] not in seen:
                                            metrics = get_metrics(el)
                                            record = {**data, **metrics, 'query': full_query, 'candidate': candidato}
                                            all_tweets.append(record)
                                            seen.add(data['id'])
                                            collected += 1
                                            tweets_collected += 1
                                            print(f"...[{tweets_collected}/{TWEETS_PER_CANDIDATE}]")
                                            if tweets_collected >= TWEETS_PER_CANDIDATE:
                                                break

                                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                                    time.sleep(SCROLL_PAUSE + random.random())
                                    if collected >= target:
                                        success = True
                                        print(f"🔁 {collected} tweets coletados — mudar query.")
                                        break
                                    new_h = driver.execute_script("return document.body.scrollHeight")
                                    if new_h == last_h: break
                                    last_h = new_h

                                if success: break

                            except Exception as e:
                                error_streak += 1
                                error_total += 1
                                print(f"⚠ Erro: {e} (streak={error_streak})")
                                if error_streak >= 3:
                                    print("⚠ 3 erros seguidos — pular query.")
                                    success = True
                                    break
                                if error_total >= 5:
                                    print(f"🔄 Muitos erros — aguardando {WAIT_RETRY_MINUTES} minutos antes de retry.")
                                    time.sleep(WAIT_RETRY_MINUTES * 60)
                                    error_total = 0
                                    break

                        if success or stop_scraping: break

                query_index += 1


finally:
    driver.quit()
    if all_tweets:
        if pd.io.common.file_exists(OUTPUT_CSV):
            existing_df = pd.read_csv(OUTPUT_CSV, encoding='utf-8-sig')
            existing_ids = set(existing_df['id'].astype(str))
        else:
            existing_ids = set()

        new_tweets = [tweet for tweet in all_tweets if tweet['id'] not in existing_ids]
        if new_tweets:
            df = pd.DataFrame(new_tweets).drop_duplicates('id')
            df['datetime'] = pd.to_datetime(df['datetime'])
            df['date'] = df['datetime'].dt.date
            df['hour'] = df['datetime'].dt.time
            df.to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig', mode='a', header=False if existing_ids else True)
            print(f"Salvo {len(df)} novos tweets em {OUTPUT_CSV}")
        else:
            print("Nenhum tweet novo para salvar.")
    else:
        print("Nenhum tweet coletado.")
