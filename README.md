# Twitter-analysis
Este projeto tem como objetivo analisar tweets relacionados à política portuguesa, utilizando ferramentas de ciência de dados, machine learning e processamento de linguagem natural.

## Objetivo
Classificar tweets sobre política portuguesa usando modelos de IA.
Gerar estatísticas e previsões eleitorais a partir dos dados dos tweets.
Organizar e documentar os resultados para facilitar estudos e análises futuras.

Estrutura do Projeto

Text
twitter/

├── classifica_tweets.py           # Script principal de classificação de tweets usando Ollama

├── prediction/

│   └── treino.csv                 # Base de dados de tweets para treino/classificação
├── previsao_eleitoral_features.csv# Estatísticas agregadas dos candidatos
Principais Funcionalidades
## Classificação de Tweets:
O arquivo classifica_tweets.py automatiza a classificação de tweets segundo regras específicas, usando o modelo deepseek-coder:6.7b-instruct via Ollama.
## Base de Dados:
O arquivo prediction/treino.csv contém tweets e seus respectivos candidatos, utilizado para treinamento e avaliação dos modelos.
## Análise Estatística:
O arquivo previsao_eleitoral_features.csv apresenta várias métricas dos candidatos, como polaridade média dos tweets, engajamento, distribuição temporal e proporção de sentimentos.
Como Usar
Configurar o ambiente:

## Instale as dependências necessárias (Python, pandas, requests, tqdm).
Execute o servidor Ollama localmente.
Ajuste variáveis de ambiente conforme necessário.
Executar a classificação:

bash
python twitter/classifica_tweets.py
O script lê os tweets do arquivo CSV, envia em lotes para o modelo de IA e salva os resultados classificados em um novo arquivo.
Explorar os resultados:

## Analise os CSVs gerados para visualizar estatísticas e classificações dos tweets por candidato.
Requisitos
Python 3.x
Pandas
Requests
Tqdm
Servidor Ollama configurado localmente
Autor
Leandro Micael
Projeto aberto para contribuições e melhorias.

