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
TWEETS_PER_CANDIDATE = 250
SCROLL_PAUSE      = 2
WAIT_TIMEOUT      = 30
WAIT_RETRY_MINUTES = 5
OUTPUT_CSV        = 'twitter/tweets_eleicoes.csv'

# Limites para alternância de query
MIN_TWEETS_BEFORE_SWITCH = 50
MAX_TWEETS_BEFORE_SWITCH = 200

candidates_queries = {
    'André Ventura': ["André Ventura", "chega", "CHEGA", "chega!", "#Chega", "#AndréVentura", "chega portugal"],
    'Mariana Mortágua': ["Mariana Mortágua", "Bloco de Esquerda", "#MarianaMortágua", "#BE", "#BlocoDeEsquerda", "bloco de esquerda fundadores"],
    'Paulo Raimundo': ["Paulo Raimundo", "PCP", "#PauloRaimundo", "#PCP", "Partido Comunista Português", "Paulo Raimundo PCP", "Paulo Raimundo Partido Comunista Português"],
    'Rui Tavares': ["Rui Tavares", "Livre", "#RuiTavares", "#Livre", "Rui Tavares Livre", "Rui Tavares partido livre"],
    'Rui Rocha': ["iniciativa liberal", "Rui Rocha", "#RuiRocha", "#IniciativaLiberal"],
    'Pedro Nuno Santos': ["Pedro Nuno Santos", "PS", "#PedroNunoSantos", "#PS", "Partido Socialista", "Pedro Nuno Santos PS", "Pedro Nuno Santos Partido Socialista"],
    'Luis Montenegro': ["Luis Montenegro", "PSD", "#LuisMontenegro", "#PSD", "Partido Social Democrata", "Luis Montenegro PSD", "Luis Montenegro Partido Social Democrata"],
    'Inês de Sousa Real': ["Inês de Sousa Real", "PEV", "#InêsDeSousaReal", "#PEV", "Partido Ecologista Os Verdes", "Inês de Sousa Real PEV", "Inês de Sousa Real Partido Ecologista Os Verdes"],
}

stop_scraping = False

# Handler de sinal para interrupção
def signal_handler(sig, frame):
    global stop_scraping
    print("\nInterrupção recebida: finalizando após o lote atual e salvando...")
    stop_scraping = True
signal.signal(signal.SIGINT, signal_handler)

# funções auxiliares
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
        return {'id': extrair_id(href), 'user': user, 'text': text, 'datetime': time_el.get_attribute('datetime'), 'time': time_el.text}
    except:
        return None


def get_metrics(el):
    out = {'replies': 0, 'retweets': 0, 'likes': 0, 'bookmarks': 0, 'views': 0}
    try:
        parts = el.find_elements(By.XPATH, './/div[@role="group" and contains(@class, "css-175oi2r")]')
        for part in parts:
            aria = part.get_attribute('aria-label')
            if not aria: continue
            for metric in aria.split(','):
                try:
                    num, name = metric.strip().split(' ', 1)
                    cnt = parse_count(num); nl = name.lower()
                    if 'respostas' in nl: out['replies'] = cnt
                    elif 'retweet' in nl: out['retweets'] = cnt
                    elif 'curtida' in nl or 'like' in nl: out['likes'] = cnt
                    elif 'salvo' in nl or 'bookmark' in nl: out['bookmarks'] = cnt
                    elif 'visualização' in nl or 'view' in nl: out['views'] = cnt
                except: pass
    except: pass
    return out


def gerar_intervalos(start_date, end_date, days=7):
    current = start_date
    while current < end_date:
        nxt = current + timedelta(days=days)
        yield current.strftime('%Y-%m-%d'), min(nxt, end_date).strftime('%Y-%m-%d')
        current = nxt


def iniciar_driver(browser='chrome'):
    args = [f"--user-data-dir={USER_DATA_DIR}", f"--profile-directory={PROFILE}", "--disable-blink-features=AutomationControlled", "--lang=pt"]
    if browser=='chrome':
        opts=Options(); [opts.add_argument(a) for a in args]
        opts.add_argument("user-agent=Mozilla/5.0 ... Chrome/115.0.5790.102 Safari/537.36")
        return webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=opts)
    else:
        opts=EdgeOptions(); opts.use_chromium=True; [opts.add_argument(a) for a in args]
        opts.add_argument("user-agent=Mozilla/5.0 ... Edg/115.0.1901.188")
        return webdriver.Edge(service=Service(EDGEDRIVER_PATH), options=opts)

# inicialização e scraping
current_browser='chrome'; driver=iniciar_driver(current_browser); wait=WebDriverWait(driver,WAIT_TIMEOUT)
all_tweets=[]; seen=set(); error_total=0; error_streak=0
try:
    driver.get('https://twitter.com/home')
    time.sleep(5)
    if any(x in driver.page_source for x in ["Entrar", "Log in"]):
        print("⚠️ Não autenticado.")
        driver.quit()
        sys.exit(1)

    filters = ['live', 'top']
    start = datetime.strptime("2024-09-01", "%Y-%m-%d")
    end = datetime.strptime("2025-04-26", "%Y-%m-%d")

    for candidato, hashtags in candidates_queries.items():
        if stop_scraping:
            break

        tweets_collected = 0
        query_index = 0
        random.shuffle(hashtags)
        recent_target = int(TWEETS_PER_CANDIDATE * 0.75)
        older_target = TWEETS_PER_CANDIDATE - recent_target
        recent_start = max(start, end - timedelta(days=30))
        recent_int = list(gerar_intervalos(recent_start, end))
        older_int = list(gerar_intervalos(start, recent_start))

        for phase, intervals, pt in [('recent', recent_int, recent_target), ('older', older_int, older_target)]:
            phase_count = 0
            print(f"[ {candidato} ] Fase {phase} meta {pt}")

            for d1, d2 in intervals:
                if stop_scraping or phase_count >= pt:
                    break

                try:
                    qtxt = urllib.parse.quote(f"{hashtags[query_index % len(hashtags)]} since:{d1} until:{d2} lang:pt")
                    for f in filters:
                        if stop_scraping or phase_count >= pt:
                            break

                        driver.get(f'https://twitter.com/search?q={qtxt}&f={f}')
                        time.sleep(2 + random.random() * 2)

                        if "não é mais compatível" in driver.page_source:
                            current_browser = 'edge' if current_browser == 'chrome' else 'chrome'
                            driver.quit()
                            driver = iniciar_driver(current_browser)
                            wait = WebDriverWait(driver, WAIT_TIMEOUT)
                            driver.get(f'https://twitter.com/search?q={qtxt}&f={f}')
                            time.sleep(3)

                        last_h = driver.execute_script("return document.body.scrollHeight")
                        while phase_count < pt and tweets_collected < TWEETS_PER_CANDIDATE and not stop_scraping:
                            wait.until(EC.presence_of_all_elements_located((By.XPATH, '//article[@data-testid="tweet"]')))
                            for el in driver.find_elements(By.XPATH, '//article[@data-testid="tweet"]'):
                                if stop_scraping or phase_count >= pt:
                                    break
                                if el.find_elements(By.XPATH, './/span[contains(text(),"Promov")]'):
                                    continue
                                data = get_tweet_data(el)
                                if data and data['id'] not in seen:
                                    seen.add(data['id'])
                                    metrics = get_metrics(el)
                                    all_tweets.append({**data, **metrics, 'query': f"since:{d1} until:{d2}", 'candidate': candidato})
                                    phase_count += 1
                                    tweets_collected += 1
                                    print(f"...[{tweets_collected}/{TWEETS_PER_CANDIDATE}] ({phase}:{phase_count}/{pt})")

                            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                            time.sleep(SCROLL_PAUSE + random.random())
                            new_h = driver.execute_script("return document.body.scrollHeight")
                            if new_h == last_h:
                                break
                            last_h = new_h

                except Exception as e:
                    error_streak += 1
                    error_total += 1
                    print(f"⚠ Erro: {e} (streak={error_streak})")
                    if error_streak >= 3:
                        print("⚠ 3 erros seguidos — pular query.")
                        break
                    if error_total >= 5:
                        print(f"🔄 Muitos erros — aguardando {WAIT_RETRY_MINUTES} minutos antes de retry.")
                        time.sleep(WAIT_RETRY_MINUTES * 60)
                        error_total = 0
                        break

            # Compensar tweets faltantes para a fase atual
            if phase_count < pt and not stop_scraping:
                print(f"Compensando {pt - phase_count} tweets para a fase {phase}")
                for d1, d2 in gerar_intervalos(start, end):
                    if phase_count >= pt or tweets_collected >= TWEETS_PER_CANDIDATE:
                        break

                    try:
                        qtxt = urllib.parse.quote(f"{hashtags[query_index % len(hashtags)]} since:{d1} until:{d2} lang:pt")
                        for f in filters:
                            if phase_count >= pt or tweets_collected >= TWEETS_PER_CANDIDATE:
                                break

                            driver.get(f'https://twitter.com/search?q={qtxt}&f={f}')
                            time.sleep(2 + random.random() * 2)

                            last_h = driver.execute_script("return document.body.scrollHeight")
                            while phase_count < pt and tweets_collected < TWEETS_PER_CANDIDATE and not stop_scraping:
                                wait.until(EC.presence_of_all_elements_located((By.XPATH, '//article[@data-testid="tweet"]')))
                                for el in driver.find_elements(By.XPATH, '//article[@data-testid="tweet"]'):
                                    if stop_scraping:
                                        break
                                    if el.find_elements(By.XPATH, './/span[contains(text(),"Promov")]'):
                                        continue
                                    data = get_tweet_data(el)
                                    if data and data['id'] not in seen:
                                        seen.add(data['id'])
                                        metrics = get_metrics(el)
                                        all_tweets.append({**data, **metrics, 'query': f"since:{d1} until:{d2}", 'candidate': candidato})
                                        phase_count += 1
                                        tweets_collected += 1
                                        print(f"...[{tweets_collected}/{TWEETS_PER_CANDIDATE}] comp ({phase}:{phase_count}/{pt})")

                                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                                time.sleep(SCROLL_PAUSE + random.random())
                                new_h = driver.execute_script("return document.body.scrollHeight")
                                if new_h == last_h:
                                    break

                    except Exception as e:
                        error_streak += 1
                        error_total += 1
                        print(f"⚠ Erro: {e} (streak={error_streak})")
                        if error_streak >= 3:
                            print("⚠ 3 erros seguidos — pular query.")
                            break
                        if error_total >= 5:
                            print(f"🔄 Muitos erros — aguardando {WAIT_RETRY_MINUTES} minutos antes de retry.")
                            time.sleep(WAIT_RETRY_MINUTES * 60)
                            error_total = 0
                            break

finally:
    driver.quit()
    if all_tweets:
        df = pd.DataFrame(all_tweets).drop_duplicates('id')
        df['datetime'] = pd.to_datetime(df['datetime'])
        df['date'] = df['datetime'].dt.date
        df['hour'] = df['datetime'].dt.time
        df.to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig')
        print(f"Salvo {len(df)} tweets em {OUTPUT_CSV}")
    else:
        print("Nenhum tweet coletado.")
