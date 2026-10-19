"""Recompute the paper's simplified tariff scenario from the saved interval cases.

The underlying October 2025 weather, AC, PV and grid flows are unchanged.
This is an illustrative, uniform-rate comparison, not an official account bill.
"""
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).parent
DATA = ROOT / "data"
FIG = ROOT / "figures"
ENERGY, AFA, CAPACITY, NETWORK, RETAIL = .2703, .0367, .0455, .1285, 10.0
IMPORT_RATE = ENERGY + AFA + CAPACITY + NETWORK

cases = [
    ("25°C mod.", 25, "Baseline", "monthly_25C_baseline.csv"),
    ("25°C on/off", 25, "ON/OFF", "monthly_25C_onoff.csv"),
    ("27°C mod.", 27, "Baseline", "monthly_27C_baseline.csv"),
    ("27°C on/off", 27, "ON/OFF", "monthly_27C_onoff.csv"),
]

rows = []
for label, target, control, filename in cases:
    df = pd.read_csv(DATA / filename)
    imported = df.Grid_Import_kWh.sum()
    exported = df.Grid_Export_kWh.sum()
    household = df.Household_Energy_kWh.sum()
    pv = df.PV_Energy_kWh.sum()
    credited = min(imported, exported)
    row = dict(label=label, Setpoint_C=target, Control=control,
               AC_Energy_kWh=df.AC_Energy_kWh.sum(), Household_Energy_kWh=household,
               PV_Energy_kWh=pv, Grid_Import_kWh=imported,
               Grid_Export_kWh=exported, Credited_Export_kWh=credited,
               Bill_Without_PV_RM=household * IMPORT_RATE + RETAIL,
               Energy_Charge_RM=imported * ENERGY,
               AFA_Charge_RM=imported * AFA,
               Capacity_Charge_RM=imported * CAPACITY,
               Network_Charge_RM=imported * NETWORK,
               Retail_Charge_RM=RETAIL,
               Export_Credit_RM=credited * ENERGY)
    row["Gross_Import_Charge_RM"] = imported * IMPORT_RATE + RETAIL
    row["Net_Modelled_Charge_RM"] = max(0, row["Gross_Import_Charge_RM"] - row["Export_Credit_RM"])
    row["PV_Operating_Difference_RM"] = row["Bill_Without_PV_RM"] - row["Net_Modelled_Charge_RM"]
    assert abs(household + exported - imported - pv) < 1e-6
    rows.append(row)

summary = pd.DataFrame(rows)
summary.to_csv(DATA / "revised_billing_summary.csv", index=False)

plt.rcParams.update({"font.size": 11, "axes.titlesize": 12, "figure.dpi": 180})
colors = ["#2374ab", "#509dc4", "#087f59", "#43a684"]

fig, ax = plt.subplots(figsize=(7.4, 3.8), layout="constrained")
bars = ax.bar(summary.label, summary.Net_Modelled_Charge_RM, color=colors)
ax.bar_label(bars, fmt="RM %.2f", padding=3)
ax.set_ylabel("Net modelled monthly charge (RM)")
ax.set_ylim(0, 130)
fig.savefig(FIG / "graph1_monthly_bill_comparison.png", dpi=220)
plt.close(fig)

fig, ax = plt.subplots(figsize=(7.4, 3.8), layout="constrained")
x = range(4)
ax.bar([a - .18 for a in x], summary.Bill_Without_PV_RM, width=.36, label="No PV", color="#53697e")
ax.bar([a + .18 for a in x], summary.Net_Modelled_Charge_RM, width=.36, label="PV and export credit", color="#148a68")
ax.set_xticks(list(x), summary.label)
ax.set_ylabel("Modelled monthly operating charge (RM)")
ax.legend(fontsize=10)
fig.savefig(FIG / "graph2_withoutPV_vs_ATAP.png", dpi=220)
plt.close(fig)

fig, ax = plt.subplots(figsize=(7.4, 3.8), layout="constrained")
first = summary.iloc[0]
labels = ["Energy", "AFA", "Capacity", "Network", "Retail", "Export credit"]
values = [first.Energy_Charge_RM, first.AFA_Charge_RM,
          first.Capacity_Charge_RM, first.Network_Charge_RM,
          first.Retail_Charge_RM, -first.Export_Credit_RM]
ax.bar(labels, values, color=["#2374ab"] * 5 + ["#148a68"])
ax.axhline(0, color="black", lw=.7)
ax.set_ylabel("Charge (+) or credit (−), RM")
ax.tick_params(axis="x", rotation=25)
fig.savefig(FIG / "graph4_bill_components.png", dpi=220)
plt.close(fig)

# Redraw the three physical-energy plots with readable labels. Values still
# come from the saved original simulation, not from the tariff calculation.
fig, ax = plt.subplots(figsize=(7.4, 3.8), layout="constrained")
bars = ax.bar(summary.label, summary.AC_Energy_kWh, color=colors)
ax.bar_label(bars, fmt="%.1f", padding=3)
ax.set_ylabel("Monthly AC electricity (kWh)")
ax.set_ylim(0, 410)
fig.savefig(FIG / "graph3_monthly_ac_energy.png", dpi=220)
plt.close(fig)

case25 = pd.read_csv(DATA / "monthly_25C_baseline.csv", parse_dates=["Time"])
days = [("Sunny weekday", "2025-10-31"), ("Rainy weekday", "2025-10-23"),
        ("Sunny weekend", "2025-10-26"), ("Rainy weekend", "2025-10-12")]
for filename, column, ylabel in [
    ("graph5_representative_day_pv.png", "PV_Power_kW", "Estimated PV power (kW)"),
    ("graph6_representative_grid_import.png", "Grid_Import_kW", "Grid import power (kW)"),
]:
    fig, ax = plt.subplots(figsize=(8, 3.9), layout="constrained")
    for label, date in days:
        day = case25.loc[case25.Time.dt.strftime("%Y-%m-%d") == date]
        hour = day.Time.dt.hour + day.Time.dt.minute / 60
        ax.plot(hour, day[column], lw=1.9, label=label)
    ax.set_xlim(0, 24)
    ax.set_xticks(range(0, 25, 3))
    ax.set_xlabel("Local time (hour)")
    ax.set_ylabel(ylabel)
    ax.grid(alpha=.25)
    ax.legend(ncol=2, loc="upper right", fontsize=10)
    fig.savefig(FIG / filename, dpi=220)
    plt.close(fig)

print(summary[["label", "Gross_Import_Charge_RM", "Export_Credit_RM",
               "Net_Modelled_Charge_RM", "Bill_Without_PV_RM"]].round(2).to_string(index=False))
