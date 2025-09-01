# -*- coding: utf-8 -*-
"""
Análise de produtividade (before/after) com base nos dashboards gerados:
- analises_projeto_lote/dashboard_commits.csv
- analises_projeto_lote/dashboard_authors.csv

Saídas:
- relatorios/tabelas/*.csv (tabelas agregadas)
- relatorios/figuras/*.png (gráficos)

Rodar:
    python3 analise_produtividade.py
"""

import os
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

# ---------------- Config ----------------
BASE = Path("")
COMMITS_CSV = BASE / "dashboard_commits.csv"
AUTHORS_CSV = BASE / "dashboard_authors.csv"

OUT_DIR = Path("relatorios")
OUT_TABS = OUT_DIR / "tabelas"
OUT_FIGS = OUT_DIR / "figuras"
OUT_TABS.mkdir(parents=True, exist_ok=True)
OUT_FIGS.mkdir(parents=True, exist_ok=True)

def to_num(s):
    return pd.to_numeric(s, errors="coerce").fillna(0)

def load_commits():
    if not COMMITS_CSV.exists():
        raise FileNotFoundError(f"Não encontrei {COMMITS_CSV}. Rode o analisador antes.")
    df = pd.read_csv(COMMITS_CSV)

    # Compatibilidade de nomes
    if "diff_added" in df.columns and "additions" not in df.columns:
        df["additions"] = to_num(df["diff_added"])
    else:
        df["additions"] = to_num(df.get("additions", 0))
    if "diff_removed" in df.columns and "deletions" not in df.columns:
        df["deletions"] = to_num(df["diff_removed"])
    else:
        df["deletions"] = to_num(df.get("deletions", 0))

    # Conversões numéricas úteis
    for col in [
        "before_nloc","after_nloc",
        "before_ccn_sum","after_ccn_sum",
        "before_ccn_mean","after_ccn_mean",
        "additions","deletions"
    ]:
        if col in df.columns:
            df[col] = to_num(df[col])

    # Derivadas
    if "delta_nloc" not in df.columns:
        df["delta_nloc"] = df["after_nloc"] - df["before_nloc"]
    if "delta_ccn_sum" not in df.columns and "before_ccn_sum" in df.columns and "after_ccn_sum" in df.columns:
        df["delta_ccn_sum"] = df["after_ccn_sum"] - df["before_ccn_sum"]
    if "delta_ccn_mean" not in df.columns and "before_ccn_mean" in df.columns and "after_ccn_mean" in df.columns:
        df["delta_ccn_mean"] = df["after_ccn_mean"] - df["before_ccn_mean"]

    # Proxy: linhas adicionadas por |ΔCCN|
    df["linhas_por_abs_delta_ccn"] = 0.0
    mask = df["delta_ccn_sum"].abs() > 0
    df.loc[mask, "linhas_por_abs_delta_ccn"] = (df.loc[mask, "additions"] / df.loc[mask, "delta_ccn_sum"].abs()).round(3)

    return df

def load_authors():
    if not AUTHORS_CSV.exists():
        # pode não existir se você ainda não rodou a versão incremental
        return None
    da = pd.read_csv(AUTHORS_CSV)
    for col in ["commits","sum_delta_ccn_sum","sum_delta_nloc","sum_additions","sum_deletions"]:
        if col in da.columns:
            da[col] = to_num(da[col])
    # recalcula proxy para robustez
    da["additions_por_delta_ccn_sum"] = 0.0
    m = da["sum_delta_ccn_sum"].abs() > 0
    da.loc[m, "additions_por_delta_ccn_sum"] = (da.loc[m, "sum_additions"] / da.loc[m, "sum_delta_ccn_sum"].abs()).round(3)
    return da

def salvar_csv(df: pd.DataFrame, nome: str):
    path = OUT_TABS / nome
    df.to_csv(path, index=False)
    print(f"[CSV] {path}")

def fig_save_show(ax, filename: str, tight=True):
    if tight:
        plt.tight_layout()
    out = OUT_FIGS / filename
    plt.savefig(out, dpi=150)
    print(f"[PNG] {out}")
    plt.show()

def analise_por_commit(df: pd.DataFrame):
    print("[INFO] Análise por commit…")

    # Tabela principal
    cols_show = [
        "repo","author","sha",
        "additions","deletions","delta_nloc",
        "before_ccn_sum","after_ccn_sum","delta_ccn_sum",
        "before_ccn_mean","after_ccn_mean","delta_ccn_mean",
        "linhas_por_abs_delta_ccn"
    ]
    cols_show = [c for c in cols_show if c in df.columns]
    salvar_csv(df[cols_show], "commits_tabela_principal.csv")

    # Scatter: ΔNLOC vs ΔCCN (cada commit)
    if {"delta_nloc","delta_ccn_sum"}.issubset(df.columns):
        ax = df.plot.scatter(x="delta_nloc", y="delta_ccn_sum", figsize=(8,6))
        ax.set_title("Commit: ΔNLOC vs ΔCCN (cada ponto = um commit)")
        ax.set_xlabel("ΔNLOC (after - before)")
        ax.set_ylabel("ΔCCN (after - before)")
        fig_save_show(ax, "commit_scatter_deltaNLOC_deltaCCN.png")

    # Boxplot de ΔCCN por autor (Top N autores por commits)
    if {"author","delta_ccn_sum"}.issubset(df.columns):
        top_counts = df["author"].value_counts().head(12).index.tolist()
        sub = df[df["author"].isin(top_counts)]
        ax = sub.boxplot(column="delta_ccn_sum", by="author", rot=45, figsize=(12,6))
        plt.title("Distribuição de ΔCCN por autor (Top 12 por volume)")
        plt.suptitle("")
        plt.ylabel("ΔCCN")
        fig_save_show(ax, "commit_boxplot_deltaCCN_por_autor.png", tight=False)

    # Histograma de linhas_por_abs_delta_ccn
    if "linhas_por_abs_delta_ccn" in df.columns:
        ax = df["linhas_por_abs_delta_ccn"].plot(kind="hist", bins=30, figsize=(8,5))
        ax.set_title("Distribuição: linhas adicionadas por |ΔCCN| (proxy de produtividade)")
        ax.set_xlabel("Linhas por |ΔCCN|")
        fig_save_show(ax, "commit_hist_proxy_produtividade.png")

def analise_por_autor(df: pd.DataFrame, da: pd.DataFrame):
    print("[INFO] Análise por autor…")

    # Se não houver dashboard por autor, agregamos a partir de commits
    if da is None:
        print("[AVISO] dashboard_authors.csv não encontrado — agregando a partir de commits.")
        grp = df.groupby("author").agg(
            commits=("sha","count"),
            sum_delta_ccn_sum=("delta_ccn_sum","sum"),
            sum_delta_nloc=("delta_nloc","sum"),
            sum_additions=("additions","sum"),
            sum_deletions=("deletions","sum")
        ).reset_index()
        grp["additions_por_delta_ccn_sum"] = 0.0
        mask = grp["sum_delta_ccn_sum"].abs() > 0
        grp.loc[mask, "additions_por_delta_ccn_sum"] = (
            grp.loc[mask, "sum_additions"] / grp.loc[mask, "sum_delta_ccn_sum"].abs()
        ).round(3)
        da = grp

    salvar_csv(da.sort_values("commits", ascending=False), "autores_tabela_resumo.csv")

    # Gráfico: commits por autor (top N)
    top_n = 20
    ax = da.sort_values("commits", ascending=False).head(top_n).plot(
        x="author", y="commits", kind="bar", figsize=(12,6))
    ax.set_title(f"Autores com mais commits analisados (Top {top_n})")
    ax.set_ylabel("Commits")
    fig_save_show(ax, "autores_top_commits.png")

    # Gráfico: additions/deletions por autor (ordenado por additions)
    ax = da.sort_values("sum_additions", ascending=False).head(top_n).plot(
        x="author", y=["sum_additions","sum_deletions"], kind="bar", figsize=(12,6))
    ax.set_title(f"Soma de linhas adicionadas/removidas por autor (Top {top_n} por additions)")
    ax.set_ylabel("Linhas")
    fig_save_show(ax, "autores_sum_additions_deletions.png")

    # Gráfico: proxy additions / |ΔCCN|
    ax = da.sort_values("additions_por_delta_ccn_sum", ascending=False).head(top_n).plot(
        x="author", y="additions_por_delta_ccn_sum", kind="bar", figsize=(12,6))
    ax.set_title(f"Additions por |ΔCCN| (Top {top_n}) — proxy de produtividade")
    ax.set_ylabel("Linhas por unidade de |ΔCCN|")
    fig_save_show(ax, "autores_proxy_produtividade.png")

    # (Opcional) média de additions por commit — se tiver commits.csv
    if {"author","additions"}.issubset(df.columns):
        extra = df.groupby("author").agg(media_additions_por_commit=("additions","mean")).reset_index()
        da2 = da.merge(extra, how="left", on="author")
        salvar_csv(da2, "autores_tabela_resumo_enriquecida.csv")
        ax = da2.sort_values("media_additions_por_commit", ascending=False).head(top_n).plot(
            x="author", y="media_additions_por_commit", kind="bar", figsize=(12,6))
        ax.set_title(f"Média de additions por commit por autor (Top {top_n})")
        ax.set_ylabel("Linhas/commit")
        fig_save_show(ax, "autores_media_additions_por_commit.png")

def main():
    print("[INFO] Carregando dashboards…")
    df = load_commits()
    da = load_authors()  # pode ser None

    # Salva uma amostra do dataset por commit
    salvar_csv(df.head(200), "amostra_commits.csv")

    # Análises
    analise_por_commit(df)
    analise_por_autor(df, da)

    print(f"\n[OK] Relatórios e figuras em: {OUT_DIR.resolve()}")

if __name__ == "__main__":
    main()

