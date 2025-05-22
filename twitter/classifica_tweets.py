#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Classifica tweets com Ollama em lotes, escrevendo o resultado num CSV.
Autor: Leandro (revisto)
"""

import os
import json
import requests
import pandas as pd
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
MODEL_NAME = "deepseek-coder:6.7b-instruct"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
TIMEOUT_S  = 60          # segundos
BATCH_SIZE = 10
CSV_IN     = "prediction/treino.csv"
CSV_OUT    = "treino_classificado.csv"

# ---------------------------------------------------------------------------
# Prompt base (formato JSON ⇒ mais fácil de analisar)
# ---------------------------------------------------------------------------
PROMPT_BASE = """Classifica cada tweet segundo as regras:

- Se o tweet falar de UM candidato/partido específico português, devolve esse nome exato (ex.: André Ventura).
- Se mencionar MAIS de um candidato/partido, devolve uma lista JSON, ex.: ["André Ventura","Mariana Mortágua"].
- Se for política geral (sem nomes), devolve o número 1.
- Se não for política, devolve o número 0.

Responde APENAS em JSON, sem texto extra.

Tweets:
{tweets}
"""

# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def check_ollama_alive() -> None:
    """Falha cedo se o servidor Ollama não responder."""
    try:
        requests.get(OLLAMA_URL.replace("/api/generate", "/"), timeout=5)
    except requests.exceptions.RequestException as exc:
        raise SystemExit(
            f"❌ Não consegui contactar o servidor Ollama em {OLLAMA_URL}\n"
            f"Detalhe: {exc}\n"
            "Corre `ollama serve` (ou ajusta a variável OLLAMA_URL) e volta a tentar."
        )

def build_prompt(batch: list[str]) -> str:
    """Cria o prompt colocando cada tweet numa linha com hífen."""
    tweets_fmt = "\n".join(f"- {t}" for t in batch)
    return PROMPT_BASE.format(tweets=tweets_fmt)

def call_ollama(prompt: str) -> str:
    """Faz o POST e devolve o conteúdo da mensagem."""
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0}
    }
    r = requests.post(OLLAMA_URL, json=payload, timeout=TIMEOUT_S)
    r.raise_for_status()
    body = r.json()

    # Compatibilidade com versões antigas (campo 'response')
    return body.get("response") or body["message"]["content"]

def parse_json_lines(response_text: str, expected: int) -> list[str | None]:
    """
    Cada linha deve ser JSON válido com a chave 'classificacao'.
    Se falhar, devolve None na posição correspondente.
    """
    resultados: list[str | None] = []
    for line in response_text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            resultados.append(data["classificacao"])
        except Exception:
            resultados.append(None)

    # Ajusta tamanho
    if len(resultados) < expected:
        resultados.extend([None] * (expected - len(resultados)))
    elif len(resultados) > expected:
        resultados = resultados[:expected]

    return resultados

# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------
def classifica_batch(batch: list[str]) -> list[str | None]:
    """Classifica um lote de tweets e devolve lista de rótulos."""
    prompt = build_prompt(batch)
    resposta = call_ollama(prompt)
    return parse_json_lines(resposta, expected=len(batch))

def processa_dataframe(df: pd.DataFrame) -> pd.Series:
    """Percorre o DataFrame em lotes e devolve uma Series com as classificações."""
    resultados: list[str | None] = []
    it = range(0, len(df), BATCH_SIZE)
    for i in tqdm(it, desc="Classificando"):
        lote = df["text"].iloc[i : i + BATCH_SIZE].tolist()
        resultados.extend(classifica_batch(lote))
    return pd.Series(resultados, index=df.index, name="candidato_previsto")

# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------
def main() -> None:
    check_ollama_alive()

    df = pd.read_csv(CSV_IN, delimiter=",")
    df["candidato_previsto"] = processa_dataframe(df)
    df[["text", "candidate", "candidato_previsto"]].to_csv(
        CSV_OUT, index=False, sep=","
    )
    print(f"✅ Ficheiro '{CSV_OUT}' criado com sucesso!")

if __name__ == "__main__":
    main()
