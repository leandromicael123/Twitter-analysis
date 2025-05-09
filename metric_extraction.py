import signal
import sys
import time
import re
import random
import pandas as pd
import metric_extraction as me
import urllib.parse
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.edge.options import Options as EdgeOptions  # ALTERAÇÃO
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException

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
                        elif 'views' in nl or 'views' in nl or 'visualizações' in nl:
                            out['views'] = cnt
                    except ValueError:
                        continue

    except NoSuchElementException:
        print("Erro: Não foi possível encontrar o subelemento de métricas.")  # Mensagem de erro opcional

    return out

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
