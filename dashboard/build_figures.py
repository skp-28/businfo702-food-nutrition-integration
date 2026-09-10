"""
BUSINFO 702 - Section 7 Visual Analytics
Generates Figures 2-7 from warehouse.db, grayscale, distinct markers/line
styles so no chart depends on colour alone to be readable.
"""

import sqlite3
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

DB = "warehouse.db"
conn = sqlite3.connect(DB)

plt.rcParams.update({
    "font.size": 10,
    "axes.edgecolor": "black",
    "axes.labelcolor": "black",
    "text.color": "black",
    "xtick.color": "black",
    "ytick.color": "black",
    "figure.facecolor": "white",
    "axes.facecolor": "white",
})

GRAY_DARK = "#1a1a1a"
GRAY_MID = "#666666"
GRAY_LIGHT = "#aaaaaa"


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
    top10.loc[len(top10)] = ["All other countries", other_n]
    top10["share_pct"] = 100 * top10["n"] / total

    fig, ax = plt.subplots(figsize=(9, 5.5))
    colors = [GRAY_DARK] * (len(top10) - 1) + [GRAY_LIGHT]
    hatches = [""] * (len(top10) - 1) + ["//"]
    bars = ax.bar(top10["country_name"], top10["share_pct"], color=colors, edgecolor="black")
    for bar, hatch in zip(bars, hatches):
        bar.set_hatch(hatch)

    for bar, pct in zip(bars, top10["share_pct"]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.8,
                 f"{pct:.1f}%", ha="center", va="bottom", fontsize=8)

    ax.set_ylabel("Share of positively-priced observations (%)")
    ax.set_title("Figure 2. Share of Positively-Priced Price Observations by Country\n"
                  "(Top 10 countries + all other countries)")
    ax.set_xticks(range(len(top10)))
    ax.set_xticklabels(top10["country_name"], rotation=40, ha="right")
    ax.set_ylim(0, max(top10["share_pct"]) * 1.15)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig("Figure2_price_observations_by_country.png", dpi=200)
    plt.close(fig)
    print("Figure 2 saved. n countries (incl. bucket):", len(top10), "| total obs:", total)


# =============================================================================
# FIGURE 3 - Categorised vs Uncategorised share of DIM_PRODUCT
# =============================================================================
def figure3():
    q = """
        SELECT
            CASE WHEN category_top = 'Uncategorised' THEN 'Uncategorised' ELSE 'Categorised' END AS status,
            COUNT(*) AS n
        FROM DIM_PRODUCT
        GROUP BY status
    """
    df = pd.read_sql(q, conn)
    total = df["n"].sum()
    df["pct"] = 100 * df["n"] / total
    df = df.set_index("status").loc[["Categorised", "Uncategorised"]].reset_index()

    fig, ax = plt.subplots(figsize=(8, 4.5))
    left = 0
    colors = [GRAY_DARK, GRAY_LIGHT]
    hatches = ["", "//"]
    for (_, row), color, hatch in zip(df.iterrows(), colors, hatches):
        ax.barh(["DIM_PRODUCT"], [row["pct"]], left=left, color=color,
                 edgecolor="black", hatch=hatch,
                 label=f"{row['status']} ({row['n']:,} products, {row['pct']:.1f}%)")
        ax.text(left + row["pct"] / 2, 0, f"{row['pct']:.1f}%",
                 ha="center", va="center", fontsize=11,
                 color="white" if color == GRAY_DARK else "black")
        left += row["pct"]

    ax.set_xlim(0, 100)
    ax.set_xlabel("Share of products (%)")
    ax.set_title(f"Figure 3. Categorised vs Uncategorised Products in DIM_PRODUCT (n = {total:,})")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.25), ncol=1, frameon=False)
    ax.spines[["top", "right", "left"]].set_visible(False)
    fig.tight_layout()
    fig.savefig("Figure3_categorised_vs_uncategorised.png", dpi=200)
    plt.close(fig)
    print("Figure 3 saved. total n:", total, "breakdown:", dict(zip(df["status"], df["n"])))


# =============================================================================
# FIGURE 4 - Bubble chart: avg price vs coefficient of variation, by category
#             (France, EUR, price > 0, category_top != 'Uncategorised', n >= 200)
# =============================================================================
def figure4():
    q = """
        SELECT dp.category_top AS category, fp.price AS price
        FROM FACT_PRICE fp
        JOIN DIM_PRODUCT dp ON fp.product_key = dp.product_key
        JOIN DIM_COUNTRY dc ON fp.country_key = dc.country_key
        WHERE dc.iso3 = 'FRA' AND fp.currency = 'EUR' AND fp.price > 0
          AND dp.category_top != 'Uncategorised'
    """
    df = pd.read_sql(q, conn)
    grp = df.groupby("category")["price"].agg(["mean", "std", "count"]).reset_index()
    grp = grp[grp["count"] >= 200].copy()
    grp["cv_pct"] = 100 * grp["std"] / grp["mean"]

    fig, ax = plt.subplots(figsize=(10, 7))
    sizes = 15 + 300 * (grp["count"] - grp["count"].min()) / (grp["count"].max() - grp["count"].min())
    ax.scatter(grp["mean"], grp["cv_pct"], s=sizes, facecolor=GRAY_MID,
               edgecolor="black", alpha=0.75, linewidth=1)

    # label the largest few bubbles and any clear outliers to keep it legible
    label_set = pd.concat([
        grp.nlargest(6, "count"),
        grp.nlargest(3, "cv_pct"),
        grp.nlargest(3, "mean"),
    ]).drop_duplicates(subset="category")
    for _, row in label_set.iterrows():
        ax.annotate(row["category"], (row["mean"], row["cv_pct"]),
                     fontsize=7, xytext=(5, 5), textcoords="offset points")

    ax.set_xlabel("Average price, EUR")
    ax.set_ylabel("Coefficient of variation (%)")
    ax.set_title("Figure 4. Average Price vs Price Variability by Category (France, EUR)\n"
                  f"Bubble size = number of price observations (n \u2265 200 per category, {len(grp)} categories shown)")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig("Figure4_price_vs_cv_bubble.png", dpi=200)
    plt.close(fig)
    print("Figure 4 saved. categories included:", len(grp))


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

    fig, ax = plt.subplots(figsize=(9, 5.5))
    series_style = [
        ("avg_price", "Retail price (avg, EUR)", "o", "-"),
        ("cost_healthy_diet_ppp", "Healthy-diet cost (PPP)", "s", "--"),
        ("gdp_per_capita", "GDP per capita", "^", ":"),
    ]
    for col, label, marker, ls in series_style:
        ax.plot(pct_change.index, pct_change[col], marker=marker, linestyle=ls,
                 color="black", markerfacecolor="white", markeredgecolor="black",
                 linewidth=1.5, markersize=7, label=label)

    ax.axhline(0, color="gray", linewidth=0.8, linestyle="-")
    ax.set_xlabel("Year")
    ax.set_ylabel("Year-over-year change (%)")
    ax.set_title("Figure 5. Year-over-Year % Change: Retail Price, Healthy-Diet Cost\n"
                  "and GDP per Capita (France, 2019\u20132025)")
    ax.set_xticks(range(2019, 2026))
    ax.legend(frameon=False, loc="best")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig("Figure5_france_yoy_change.png", dpi=200)
    plt.close(fig)
    print("Figure 5 saved. Years with data:", list(pct_change.index))
    print(pct_change)


# =============================================================================
# FIGURE 6 - Healthy-diet cost as % of GDP per capita, by income group
#             (2017-2025)
# =============================================================================
def figure6():
    q = """
        SELECT dc.income_group AS income_group, fe.year_key AS year,
               fe.cost_healthy_diet_ppp, fe.gdp_per_capita
        FROM FACT_COUNTRY_ECONOMIC fe
        JOIN DIM_COUNTRY dc ON fe.country_key = dc.country_key
        WHERE dc.income_group IN ('Lower-middle income', 'Upper-middle income', 'High income')
          AND fe.cost_healthy_diet_ppp IS NOT NULL AND fe.gdp_per_capita > 0
    """
    df = pd.read_sql(q, conn)
    df["cost_pct_gdp"] = 100 * df["cost_healthy_diet_ppp"] / df["gdp_per_capita"]
    grp = df.groupby(["income_group", "year"])["cost_pct_gdp"].mean().reset_index()

    fig, ax = plt.subplots(figsize=(9, 5.5))
    series_style = [
        ("Lower-middle income", "o", "-"),
        ("Upper-middle income", "s", "--"),
        ("High income", "^", ":"),
    ]
    for group, marker, ls in series_style:
        sub = grp[grp["income_group"] == group].sort_values("year")
        ax.plot(sub["year"], sub["cost_pct_gdp"], marker=marker, linestyle=ls,
                 color="black", markerfacecolor="white", markeredgecolor="black",
                 linewidth=1.5, markersize=7, label=group)

    ax.set_xlabel("Year")
    ax.set_ylabel("Healthy-diet cost as % of GDP per capita")
    ax.set_title("Figure 6. Healthy-Diet Cost as a Share of GDP per Capita,\nby Income Group (2017\u20132025)")
    ax.set_xticks(range(2017, 2026))
    ax.legend(frameon=False, loc="best")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig("Figure6_diet_cost_pct_gdp_by_income_group.png", dpi=200)
    plt.close(fig)
    print("Figure 6 saved. rows used:", len(df))


# =============================================================================
# FIGURE 7 - GDP per capita (log) vs % unable to afford healthy diet, 2023
#             coloured/shaped by income group, named exceptions labelled
# =============================================================================
def figure7():
    q = """
        SELECT dc.country_name, dc.income_group,
               fe.gdp_per_capita, fe.pct_cannot_afford_healthy_diet
        FROM FACT_COUNTRY_ECONOMIC fe
        JOIN DIM_COUNTRY dc ON fe.country_key = dc.country_key
        WHERE fe.year_key = 2023
          AND fe.gdp_per_capita IS NOT NULL
          AND fe.pct_cannot_afford_healthy_diet IS NOT NULL
          AND dc.income_group != 'Unknown'
    """
    df = pd.read_sql(q, conn)

    fig, ax = plt.subplots(figsize=(10, 7))
    group_style = [
        ("High income", "o", GRAY_DARK),
        ("Upper-middle income", "s", GRAY_MID),
        ("Lower-middle income", "^", GRAY_LIGHT),
    ]
    for group, marker, color in group_style:
        sub = df[df["income_group"] == group]
        ax.scatter(sub["gdp_per_capita"], sub["pct_cannot_afford_healthy_diet"],
                   marker=marker, s=70, facecolor=color, edgecolor="black",
                   linewidth=0.8, label=f"{group} (n={len(sub)})", zorder=3)

    exceptions = ["Hungary", "Israel", "West Bank and Gaza"]
    for name in exceptions:
        row = df[df["country_name"] == name]
        if row.empty:
            continue
        r = row.iloc[0]
        ax.annotate(name, (r["gdp_per_capita"], r["pct_cannot_afford_healthy_diet"]),
                     fontsize=9, fontweight="bold", xytext=(8, 8),
                     textcoords="offset points",
                     arrowprops=dict(arrowstyle="-", color="black", lw=0.8))
        ax.scatter([r["gdp_per_capita"]], [r["pct_cannot_afford_healthy_diet"]],
                   marker="*", s=220, facecolor="black", edgecolor="black", zorder=5)

    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    ax.set_xlabel("GDP per capita, PPP current international $ (log scale)")
    ax.set_ylabel("% of population unable to afford a healthy diet")
    ax.set_title(f"Figure 7. GDP per Capita vs Healthy-Diet Unaffordability, 2023 (n = {len(df)})\n"
                  "Named points mark exceptions to the general income/affordability pattern")
    ax.legend(frameon=False, loc="upper right")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig("Figure7_gdp_vs_unaffordability_2023.png", dpi=200)
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
