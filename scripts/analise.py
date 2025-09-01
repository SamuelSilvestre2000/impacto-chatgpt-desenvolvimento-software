# -*- coding: utf-8 -*-
import os
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

# --------- caminhos possíveis ---------
CANDIDATOS = [
    Path("analises_projeto_lote/dashboard_commits.csv"),
    Path("dashboard_commits.csv"),
]

csv_path = None
for p in CANDIDATOS:
    if p.exists():
        csv_path = p
        break

if not csv_path:
    raise FileNotFoundError(
        "Não encontrei 'analises_projeto_lote/dashboard_commits.csv' nem 'dashboard_commits.csv'. "
        "Rode antes o analisador que gera o dashboard."
    )

print(f"[INFO] Lendo: {csv_path}")

df = pd.read_csv(csv_path)

if df.empty:
    raise SystemExit("[AVISO] O CSV está vazio. Nada para analisar.")

# --------- padronização de colunas ---------
# nomes esperados pelo script de análise
expected = {
    "repo", "sha", "author",
    "before_nloc","after_nloc",
    "before_ccn_mean","after_ccn_mean",
    "additions","deletions"
}

missing = [c for c in expected if c not in df.columns]
# Compatibilidade: alguns dashboards podem ter 'diff_added/diff_removed'
if "diff_added" in missing and "additions" in df.columns:
    df["diff_added"] = df["additions"]
    missing = [m for m in missing if m != "diff_added"]
if "diff_removed" in missing and "deletions" in df.columns:
    df["diff_removed"] = df["deletions"]
    missing = [m for m in missing if m != "diff_removed"]

# Se ainda não existirem diff_added/diff_removed, derive:
if "diff_added" not in df.columns:
    df["diff_added"] = df.get("additions", 0)
if "diff_removed" not in df.columns:
    df["diff_removed"] = df.get("deletions", 0)

# --------- garante tipos numéricos ---------
for col in ["diff_added","diff_removed","before_nloc","after_nloc","before_ccn_mean","after_ccn_mean"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

# --------- agrega por autor ---------
if "author" not in df.columns:
    raise KeyError("A coluna 'author' não existe no CSV. Verifique o dashboard gerado.")

df_author = df.groupby("author").agg({
    "sha": "count",
    "diff_added": "sum",
    "diff_removed": "sum",
    "before_nloc": "mean",
    "after_nloc": "mean",
    "before_ccn_mean": "mean",
    "after_ccn_mean": "mean"
}).rename(columns={"sha": "n_commits"}).reset_index()

print("[INFO] Tabela agregada por autor:")
print(df_author.head(20))

# --------- pasta de saída para gráficos ---------
out_dir = Path("graficos")
out_dir.mkdir(exist_ok=True)

# --------- gráfico 1: número de commits por autor ---------
ax = df_author.plot(x="author", y="n_commits", kind="bar", figsize=(12,6))
ax.set_title("Número de commits com ChatGPT por autor")
ax.set_ylabel("Commits")
plt.tight_layout()
plt.savefig(out_dir / "commits_por_autor.png", dpi=150)
plt.show()

# --------- gráfico 2: linhas adicionadas/removidas por autor ---------
ax = df_author.plot(x="author", y=["diff_added", "diff_removed"], kind="bar", figsize=(12,6))
ax.set_title("Linhas adicionadas/removidas por autor")
ax.set_ylabel("Linhas de código")
plt.tight_layout()
plt.savefig(out_dir / "linhas_add_remove_por_autor.png", dpi=150)
plt.show()

# --------- gráfico 3: complexidade média antes/depois por autor ---------
ax = df_author.plot(x="author", y=["before_ccn_mean", "after_ccn_mean"], kind="bar", figsize=(12,6))
ax.set_title("Complexidade média (before vs after) por autor")
ax.set_ylabel("CCN média")
plt.tight_layout()
plt.savefig(out_dir / "ccn_media_before_after_por_autor.png", dpi=150)
plt.show()

print(f"[OK] Gráficos salvos em: {out_dir.resolve()}")

