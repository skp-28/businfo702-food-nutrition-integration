"""
BUSINFO 702 - Section 7 Visual Analytics
Generates Figures 2-7 from warehouse.db. Kept grayscale/monochrome to match
the report's stated design (distinct markers/line styles, not colour alone,
for print- and colourblind-safety), but refined for readability: cleaner
typography, subtle gridlines, resolved label overlaps, and merged
French/English/German duplicate category labels (a data-quality issue
already documented in the ELT notes) in Figure 4.
"""

import sqlite3
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
try:
    from adjustText import adjust_text
    HAVE_ADJUST_TEXT = True
except ImportError:
    HAVE_ADJUST_TEXT = False

DB = "warehouse.db"
conn = sqlite3.connect(DB)

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 11,
    "axes.titlesize": 14,
    "axes.titleweight": "bold",
    "axes.labelsize": 11,
    "axes.edgecolor": "#333333",
    "axes.labelcolor": "#222222",
    "text.color": "#222222",
    "xtick.color": "#333333",
    "ytick.color": "#333333",
    "xtick.labelsize": 9.5,
    "ytick.labelsize": 9.5,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "axes.grid": True,
    "grid.color": "#e3e3e3",
    "grid.linewidth": 0.7,
    "axes.axisbelow": True,
    "legend.fontsize": 9.5,
    "legend.frameon": False,
})

INK = "#1a1a1a"
GRAY_DARK = "#2b2b2b"
GRAY_MID = "#6e6e6e"
GRAY_LIGHT = "#a8a8a8"
ACCENT_HATCH = "#c9c9c9"

# Known duplicate category labels across French / English / German source
# text, folded to one canonical English label for readability (documented
# issue: Open Food Facts category text was not translated during cleaning).
CATEGORY_TRANSLATION = {
    "Aliments et boissons à base de végétaux": "Plant-based foods and beverages",
    "Pflanzliche Lebensmittel und Getränke": "Plant-based foods and beverages",
    "Plant-based foods and beverages": "Plant-based foods and beverages",
    "Produits laitiers": "Dairies",
    "Dairies": "Dairies",
    "Viandes et dérivés": "Meats and their products",
    "Meats and their products": "Meats and their products",
    "Boissons": "Beverages",
    "Boissons et préparations de boissons": "Beverages",
    "Beverages and beverages preparations": "Beverages",
    "Beverages": "Beverages",
    "Produits de la mer": "Seafood",
    "Seafood": "Seafood",
    "Plats préparés": "Meals",
    "Meals": "Meals",
    "Petit-déjeuners": "Breakfasts",
    "Breakfasts": "Breakfasts",
    "Surgelés": "Frozen foods",
    "Frozen foods": "Frozen foods",
    "snacks": "Snacks",
    "Snacks": "Snacks",
    "Produits d'élevages": "Farming products",
    "Farming products": "Farming products",
    "Édulcorants": "Sweeteners",
    "Sandwichs": "Sandwiches",
    "Produits à tartiner": "Spreads",
}


def style_axes(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#333333")
    ax.tick_params(length=3)


def add_subtitle(fig, title, subtitle):
    fig.suptitle(title, fontsize=14, fontweight="bold", color=INK, y=0.99)
    fig.text(0.5, 0.945, subtitle, fontsize=10, color="#555555", ha="center")


# =============================================================================
# FIGURE 2 - Share of positively-priced FACT_PRICE observations by country
# =============================================================================
def figure2():
    q = """
        SELECT dc.country_name, COUNT(*) AS n
        FROM FACT_PRICE fp
        JOIN DIM_COUNTRY dc ON fp.country_key = dc.country_key
        WHERE fp.price > 0 AND fp.country_key IS NOT NULL
        GROUP BY dc.country_name
        ORDER BY n DESC
    """
    df = pd.read_sql(q, conn)
    total = df["n"].sum()

    top10 = df.head(10).copy()
    other_n = df["n"].iloc[10:].sum()
    top10.loc[len(top10)] = ["All other countries (92)", other_n]
    top10["share_pct"] = 100 * top10["n"] / total

    fig, ax = plt.subplots(figsize=(9.5, 5.8))
    colors = [GRAY_DARK] * (len(top10) - 1) + [GRAY_LIGHT]
    hatches = [""] * (len(top10) - 1) + ["//"]
    bars = ax.bar(top10["country_name"], top10["share_pct"], color=colors,
                  edgecolor="white", linewidth=0.6, width=0.68)
    for bar, hatch in zip(bars, hatches):
        bar.set_hatch(hatch)

    for bar, pct in zip(bars, top10["share_pct"]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.9,
                 f"{pct:.1f}%", ha="center", va="bottom", fontsize=9, color=INK)

    ax.set_ylabel("Share of positively-priced observations (%)")
    add_subtitle(fig, "Price evidence is concentrated in a small number of countries",
                 "Share of positively-priced FACT_PRICE observations by country (top 10 + all others)")
    ax.set_xticks(range(len(top10)))
    ax.set_xticklabels(top10["country_name"], rotation=35, ha="right")
    ax.set_ylim(0, max(top10["share_pct"]) * 1.15)
    style_axes(ax)
    ax.grid(axis="x", visible=False)
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    fig.savefig("Figure2_price_observations_by_country.png", dpi=220)
    plt.close(fig)
    print("Figure 2 saved. n countries (incl. bucket):", len(top10), "| total obs:", total)


# =============================================================================
# FIGURE 3 - Categorised vs Uncategorised share of DIM_PRODUCT
# =============================================================================
def figure3():
    q = """
        SELECT
            CASE WHEN dcat.category_top = 'Uncategorised' THEN 'Uncategorised' ELSE 'Categorised' END AS status,
            COUNT(*) AS n
        FROM DIM_PRODUCT dp
        JOIN DIM_CATEGORY dcat ON dp.category_key = dcat.category_key
        GROUP BY status
    """
    df = pd.read_sql(q, conn)
    total = df["n"].sum()
    df["pct"] = 100 * df["n"] / total
    df = df.set_index("status").loc[["Categorised", "Uncategorised"]].reset_index()

    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    left = 0
    colors = [GRAY_DARK, GRAY_LIGHT]
    hatches = ["", "//"]
    for (_, row), color, hatch in zip(df.iterrows(), colors, hatches):
        ax.barh(["DIM_PRODUCT"], [row["pct"]], left=left, color=color, height=0.55,
                 edgecolor="white", linewidth=0.8, hatch=hatch,
                 label=f"{row['status']} ({row['n']:,} products, {row['pct']:.1f}%)")
        ax.text(left + row["pct"] / 2, 0, f"{row['pct']:.1f}%",
                 ha="center", va="center", fontsize=12, fontweight="bold",
                 color="white" if color == GRAY_DARK else INK)
        left += row["pct"]

    ax.set_xlim(0, 100)
    ax.set_xlabel("Share of products (%)")
    ax.set_yticks([])
    fig.subplots_adjust(top=0.72, bottom=0.32)
    fig.suptitle("Almost half of products lack a usable category", fontsize=14, fontweight="bold", color=INK, y=0.97)
    fig.text(0.5, 0.85, f"Categorised vs Uncategorised share of DIM_PRODUCT (n = {total:,})",
             fontsize=10, color="#555555", ha="center")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.32), ncol=1, frameon=False)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.grid(visible=False)
    fig.savefig("Figure3_categorised_vs_uncategorised.png", dpi=220)
    plt.close(fig)
    print("Figure 3 saved. total n:", total, "breakdown:", dict(zip(df["status"], df["n"])))


# =============================================================================
# FIGURE 4 - Bubble chart: avg price vs coefficient of variation, by category
#             (France, EUR, price > 0, category_top != 'Uncategorised', n >= 200)
#             Duplicate French/English/German category labels merged.
# =============================================================================
def figure4():
    q = """
        SELECT dcat.category_top AS category, fp.price AS price
        FROM FACT_PRICE fp
        JOIN DIM_PRODUCT dp ON fp.product_key = dp.product_key
        JOIN DIM_CATEGORY dcat ON dp.category_key = dcat.category_key
        JOIN DIM_COUNTRY dc ON fp.country_key = dc.country_key
        WHERE dc.iso3 = 'FRA' AND fp.currency = 'EUR' AND fp.price > 0
          AND dcat.category_top != 'Uncategorised'
    """
    df = pd.read_sql(q, conn)
    df["category"] = df["category"].map(lambda c: CATEGORY_TRANSLATION.get(c, c))

    grp = df.groupby("category")["price"].agg(["mean", "std", "count"]).reset_index()
    grp = grp[grp["count"] >= 200].copy()
    grp["cv_pct"] = 100 * grp["std"] / grp["mean"]

    fig, ax = plt.subplots(figsize=(10.5, 7.5))
    sizes = 25 + 500 * (grp["count"] - grp["count"].min()) / (grp["count"].max() - grp["count"].min())
    ax.scatter(grp["mean"], grp["cv_pct"], s=sizes, facecolor=GRAY_MID,
               edgecolor=INK, alpha=0.72, linewidth=1.1, zorder=3)

    texts = []
    for _, row in grp.iterrows():
        texts.append(ax.text(row["mean"], row["cv_pct"], row["category"],
                              fontsize=8.5, color=INK, zorder=4))

    if HAVE_ADJUST_TEXT:
        adjust_text(texts, ax=ax,
                    arrowprops=dict(arrowstyle="-", color="#999999", lw=0.6),
                    expand_text=(1.15, 1.3), expand_points=(1.2, 1.4))

    ax.set_xlabel("Average price, EUR")
    ax.set_ylabel("Coefficient of variation (%)")
    add_subtitle(fig, "The most expensive categories are not necessarily the most volatile",
                 f"Average price vs price variability by category, France/EUR "
                 f"(n \u2265 200 per category, {len(grp)} categories after merging duplicate labels)")
    style_axes(ax)
    fig.tight_layout(rect=[0, 0, 1, 0.91])
    fig.savefig("Figure4_price_vs_cv_bubble.png", dpi=220)
    plt.close(fig)
    print("Figure 4 saved. categories included after merge:", len(grp))


# =============================================================================
# FIGURE 5 - YoY % change: retail price, healthy-diet cost, GDP per capita
#             (France only, 2019-2025)
# =============================================================================
def figure5():
    price_q = """
        SELECT dd.year AS year, AVG(fp.price) AS avg_price
        FROM FACT_PRICE fp
        JOIN DIM_DATE dd ON fp.date_key = dd.date_key
        JOIN DIM_COUNTRY dc ON fp.country_key = dc.country_key
        WHERE dc.iso3 = 'FRA' AND fp.currency = 'EUR' AND fp.price > 0
          AND dd.year BETWEEN 2018 AND 2025
        GROUP BY dd.year
        ORDER BY dd.year
    """
    econ_q = """
        SELECT fe.year_key AS year, fe.cost_healthy_diet_ppp, fe.gdp_per_capita
        FROM FACT_COUNTRY_ECONOMIC fe
        JOIN DIM_COUNTRY dc ON fe.country_key = dc.country_key
        WHERE dc.iso3 = 'FRA' AND fe.year_key BETWEEN 2018 AND 2025
        ORDER BY fe.year_key
    """
    price_df = pd.read_sql(price_q, conn).set_index("year")
    econ_df = pd.read_sql(econ_q, conn).set_index("year")
    merged = price_df.join(econ_df, how="outer").sort_index()

    pct_change = merged.pct_change() * 100
    pct_change = pct_change.loc[2019:2025]

    fig, ax = plt.subplots(figsize=(9.5, 5.8))
    series_style = [
        ("avg_price", "Retail price (avg, EUR)", "o", "-"),
        ("cost_healthy_diet_ppp", "Healthy-diet cost (PPP)", "s", "--"),
        ("gdp_per_capita", "GDP per capita", "^", ":"),
    ]
    for col, label, marker, ls in series_style:
        ax.plot(pct_change.index, pct_change[col], marker=marker, linestyle=ls,
                 color=INK, markerfacecolor="white", markeredgecolor=INK,
                 linewidth=1.8, markersize=7.5, label=label)

    ax.axhline(0, color="#999999", linewidth=0.8, linestyle="-")
    ax.set_xlabel("Year")
    ax.set_ylabel("Year-over-year change (%)")
    add_subtitle(fig, "France: retail and economic measures show different growth timing",
                 "Year-over-year % change: retail price, healthy-diet cost, GDP per capita (2019\u20132025)")
    ax.set_xticks(range(2019, 2026))
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), borderaxespad=0)
    style_axes(ax)
    fig.tight_layout(rect=[0, 0, 0.82, 0.91])
    fig.savefig("Figure5_france_yoy_change.png", dpi=220)
    plt.close(fig)
    print("Figure 5 saved. Years with data:", list(pct_change.index))


# =============================================================================
# FIGURE 6 - Healthy-diet cost as % of GDP per capita, by income group
#             (2017-2025)
# =============================================================================
def figure6():
    q = """
        SELECT ig.label AS income_group, fe.year_key AS year,
               fe.cost_healthy_diet_ppp, fe.gdp_per_capita
        FROM FACT_COUNTRY_ECONOMIC fe
        JOIN DIM_COUNTRY dc ON fe.country_key = dc.country_key
        JOIN DIM_INCOME_GROUP ig ON dc.income_group_key = ig.income_group_key
        WHERE ig.label IN ('Lower-middle income', 'Upper-middle income', 'High income')
          AND fe.cost_healthy_diet_ppp IS NOT NULL AND fe.gdp_per_capita > 0
    """
    df = pd.read_sql(q, conn)
    df["cost_pct_gdp"] = 100 * (df["cost_healthy_diet_ppp"] * 365.0) / df["gdp_per_capita"]
    grp = df.groupby(["income_group", "year"])["cost_pct_gdp"].mean().reset_index()

    fig, ax = plt.subplots(figsize=(9.5, 5.8))
    series_style = [
        ("Lower-middle income", "o", "-"),
        ("Upper-middle income", "s", "--"),
        ("High income", "^", ":"),
    ]
    for group, marker, ls in series_style:
        sub = grp[grp["income_group"] == group].sort_values("year")
        line, = ax.plot(sub["year"], sub["cost_pct_gdp"], marker=marker, linestyle=ls,
                 color=INK, markerfacecolor="white", markeredgecolor=INK,
                 linewidth=1.8, markersize=7.5, label=group)
        last = sub.iloc[-1]
        ax.annotate(f"{last['cost_pct_gdp']:.1f}%", (last["year"], last["cost_pct_gdp"]),
                     xytext=(8, 0), textcoords="offset points", va="center",
                     fontsize=9, color=INK)

    ax.set_xlabel("Year")
    ax.set_ylabel("Healthy-diet cost as % of GDP per capita (annualised)")
    add_subtitle(fig, "Healthy-diet burden remains far higher in lower-income economies",
                 "Healthy-diet cost as a share of GDP per capita, by income group (2017\u20132025)")
    ax.set_xticks(range(2017, 2026))
    ax.set_xlim(2016.6, 2026.6)
    ax.legend(loc="center left", bbox_to_anchor=(0.02, 0.5))
    style_axes(ax)
    fig.tight_layout(rect=[0, 0, 1, 0.91])
    fig.savefig("Figure6_diet_cost_pct_gdp_by_income_group.png", dpi=220)
    plt.close(fig)
    print("Figure 6 saved. rows used:", len(df))


# =============================================================================
# FIGURE 7 - GDP per capita (log) vs % unable to afford healthy diet, 2023
#             coloured/shaped by income group, named exceptions labelled
# =============================================================================
def figure7():
    q = """
        SELECT dc.country_name, ig.label AS income_group,
               fe.gdp_per_capita, fe.pct_cannot_afford_healthy_diet
        FROM FACT_COUNTRY_ECONOMIC fe
        JOIN DIM_COUNTRY dc ON fe.country_key = dc.country_key
        JOIN DIM_INCOME_GROUP ig ON dc.income_group_key = ig.income_group_key
        WHERE fe.year_key = 2023
          AND fe.gdp_per_capita IS NOT NULL
          AND fe.pct_cannot_afford_healthy_diet IS NOT NULL
          AND ig.label != 'Unknown'
    """
    df = pd.read_sql(q, conn)

    fig, ax = plt.subplots(figsize=(10.5, 7.5))
    group_style = [
        ("High income", "o", GRAY_DARK),
        ("Upper-middle income", "s", GRAY_MID),
        ("Lower-middle income", "^", GRAY_LIGHT),
    ]
    for group, marker, color in group_style:
        sub = df[df["income_group"] == group]
        ax.scatter(sub["gdp_per_capita"], sub["pct_cannot_afford_healthy_diet"],
                   marker=marker, s=75, facecolor=color, edgecolor=INK,
                   linewidth=0.7, alpha=0.85, label=f"{group} (n={len(sub)})", zorder=3)

    exceptions = ["Hungary", "Israel", "West Bank and Gaza"]
    for name in exceptions:
        row = df[df["country_name"] == name]
        if row.empty:
            continue
        r = row.iloc[0]
        ax.annotate(name, (r["gdp_per_capita"], r["pct_cannot_afford_healthy_diet"]),
                     fontsize=9.5, fontweight="bold", xytext=(10, 10),
                     textcoords="offset points", color=INK,
                     arrowprops=dict(arrowstyle="-", color=INK, lw=0.8))
        ax.scatter([r["gdp_per_capita"]], [r["pct_cannot_afford_healthy_diet"]],
                   marker="*", s=260, facecolor=INK, edgecolor=INK, zorder=5)

    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    ax.set_xlabel("GDP per capita, PPP current international $ (log scale)")
    ax.set_ylabel("% of population unable to afford a healthy diet")
    add_subtitle(fig, "Higher economic capacity is associated with lower diet unaffordability",
                 f"GDP per capita vs healthy-diet unaffordability, 2023 (n = {len(df)}); "
                 "named points mark exceptions to the general pattern")
    ax.legend(loc="upper right")
    style_axes(ax)
    fig.tight_layout(rect=[0, 0, 1, 0.90])
    fig.savefig("Figure7_gdp_vs_unaffordability_2023.png", dpi=220)
    plt.close(fig)
    print("Figure 7 saved. n =", len(df), "| breakdown:", df["income_group"].value_counts().to_dict())


if __name__ == "__main__":
    figure2()
    figure3()
    figure4()
    figure5()
    figure6()
    figure7()
    conn.close()
    print("\nAll six figures generated.")
