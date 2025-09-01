# -*- coding: utf-8 -*-
"""
Gera um CSV de entradas (repo, sha, parent_sha, author) para o analisador em lote.

Uso:
  python3 coletar_commits_chatgpt_para_csv.py [--out entradas.csv] [--max-pages 10]

Pré-requisitos:
  - tokens.txt no mesmo diretório (um token por linha, PAT classic; sem escopos para público).
  - pip install colorama requests

Saída:
  CSV com cabeçalho: repo,sha,parent_sha,author
"""

import os
import csv
import time
import argparse
from typing import Dict, Any, List, Tuple
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from colorama import Fore, Style, init

init(autoreset=True)

GITHUB_API = "https://api.github.com"
SEARCH_Q = "chat.openai.com OR chatgpt.com"  # termo de busca na mensagem do commit
PER_PAGE = 100

# ---------- Tokens ----------
TOKENS: List[str] = []
TOKEN_INDEX = 0

def load_tokens(path="tokens.txt"):
    global TOKENS
    if not os.path.exists(path):
        raise RuntimeError(f"Arquivo {path} não encontrado. Crie com um token por linha.")
    with open(path, "r", encoding="utf-8") as f:
        TOKENS = [ln.strip() for ln in f if ln.strip()]
    if not TOKENS:
        raise RuntimeError("tokens.txt está vazio.")
    print(f"{Fore.CYAN}[INFO]{Style.RESET_ALL} {len(TOKENS)} token(s) carregado(s).")

def next_headers() -> Dict[str, str]:
    global TOKEN_INDEX
    token = TOKENS[TOKEN_INDEX]
    TOKEN_INDEX = (TOKEN_INDEX + 1) % len(TOKENS)
    print(f"{Fore.LIGHTBLACK_EX}[DEBUG]{Style.RESET_ALL} Rodízio de token: {TOKEN_INDEX+1}/{len(TOKENS)}")
    return {
        "Authorization": f"token {token}",
        # Necessário para /search/commits
        "Accept": "application/vnd.github.cloak-preview",
        "User-Agent": "chatgpt-commit-collector/1.0"
    }

# ---------- Sessão HTTP com retry ----------
SESSION = requests.Session()
retry = Retry(
    total=5, connect=5, read=5,
    backoff_factor=1.5,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset(["GET", "HEAD"])
)
adapter = HTTPAdapter(max_retries=retry, pool_connections=100, pool_maxsize=100)
SESSION.mount("https://", adapter)
SESSION.mount("http://", adapter)

def http_get(url, params=None, timeout=25):
    while True:
        try:
            r = SESSION.get(url, headers=next_headers(), params=params, timeout=timeout)
            if r.status_code == 403:
                # Pode ser secondary rate limit
                print(f"{Fore.YELLOW}[AVISO]{Style.RESET_ALL} 403 (rate limit). Aguardando 10 minutos e tentando novamente...")
                time.sleep(600)
                continue
            return r
        except requests.exceptions.ConnectionError as e:
            print(f"{Fore.RED}[REDE]{Style.RESET_ALL} Falha de conexão: {e}. Retentando em 5s...")
            time.sleep(5)
        except requests.exceptions.Timeout:
            print(f"{Fore.RED}[REDE]{Style.RESET_ALL} Timeout. Retentando em 5s...")
            time.sleep(5)

# ---------- Busca principal ----------
def buscar_commits(max_pages: int = 10) -> List[Dict[str, Any]]:
    """
    Busca commits cuja MENSAGEM contenha 'chat.openai.com' ou 'chatgpt.com'.
    Retorna itens com campos do endpoint /search/commits.
    """
    print(f"{Fore.CYAN}[INFO]{Style.RESET_ALL} Iniciando busca por commits (até {max_pages} páginas)…")
    url = f"{GITHUB_API}/search/commits"
    params = {
        "q": SEARCH_Q,
        "sort": "author-date",
        "order": "desc",
        "per_page": PER_PAGE,
        "page": 1
    }
    itens: List[Dict[str, Any]] = []

    for page in range(1, max_pages + 1):
        params["page"] = page
        print(f"{Fore.YELLOW}[PROGRESSO]{Style.RESET_ALL} Página {page}…")
        r = http_get(url, params=params)
        if r.status_code != 200:
            print(f"{Fore.RED}[ERRO]{Style.RESET_ALL} Search {r.status_code}: {r.text[:200]}")
            break

        data = r.json()
        page_items = data.get("items", [])
        if not page_items:
            print(f"{Fore.CYAN}[INFO]{Style.RESET_ALL} Sem mais resultados.")
            break

        itens.extend(page_items)
        print(f"{Fore.GREEN}[OK]{Style.RESET_ALL} +{len(page_items)} (acum: {len(itens)})")

        # respeitar paginação até 1000 (o /search para em 10 páginas)
        if "next" not in r.links:
            break

        time.sleep(1)  # reduzir chance de secondary rate limit

    print(f"{Fore.CYAN}[INFO]{Style.RESET_ALL} Total bruto: {len(itens)}")
    return itens

# ---------- Transformação para CSV do analisador ----------
def extrair_campos_para_csv(items: List[Dict[str, Any]]) -> List[Tuple[str, str, str, str]]:
    """
    Converte itens do search em tuplas (repo, sha, parent_sha, author).
    Deduplica por (repo, sha).
    """
    saida: List[Tuple[str, str, str, str]] = []
    vistos = set()

    for it in items:
        repo_full = (it.get("repository") or {}).get("full_name") or ""
        sha = it.get("sha") or ""
        # parent_sha vem dentro do commit expandido do search
        parents = it.get("parents") or []
        parent_sha = parents[0]["sha"] if parents else ""

        # author preferencialmente login; fallback para nome do commit
        author_login = (it.get("author") or {}).get("login")
        if author_login:
            author = author_login
        else:
            author = ((it.get("commit") or {}).get("author") or {}).get("name", "desconhecido")

        key = (repo_full, sha)
        if not repo_full or not sha or key in vistos:
            continue
        vistos.add(key)
        saida.append((repo_full, sha, parent_sha, author))

    return saida

def salvar_csv_lote(rows: List[Tuple[str, str, str, str]], out_path: str):
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["repo", "sha", "parent_sha", "author"])
        for r in rows:
            w.writerow(list(r))
    print(f"{Fore.BLUE}[CSV]{Style.RESET_ALL} Salvo em: {out_path}  ({len(rows)} linhas)")

# ---------- CLI ----------
def main():
    parser = argparse.ArgumentParser(description="Coletar commits com links do ChatGPT e gerar CSV para análise before/after.")
    parser.add_argument("--out", default="entradas.csv", help="Caminho do CSV de saída (padrão: entradas.csv)")
    parser.add_argument("--max-pages", type=int, default=10, help="Máximo de páginas a buscar (padrão: 10 = 1000 commits máx.)")
    args = parser.parse_args()

    load_tokens("tokens.txt")
    items = buscar_commits(max_pages=args.max_pages)
    rows = extrair_campos_para_csv(items)
    salvar_csv_lote(rows, args.out)

    print(f"{Fore.CYAN}[INFO]{Style.RESET_ALL} Pronto. Agora rode o analisador em lote com o CSV gerado:")
    print(f"       python3 analisar_lote_before_after.py {args.out}")

if __name__ == "__main__":
    main()

