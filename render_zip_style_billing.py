"""Render the three billing charts in the supplied ZIP's chart style.

The ZIP's original billing PNGs use older tariff amounts. Read the revised
settlement CSV to keep these pictures consistent with the report tables.
The original physical-energy PNGs (graphs 3, 5 and 6) are used unchanged.
"""
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

ROOT = Path(__file__).parent
summary = pd.read_csv(ROOT / 'data/revised_billing_summary.csv')
figdir = ROOT / 'figures'
labels = ['25°C mod.', '25°C on/off', '27°C mod.', '27°C on/off']
x = np.arange(4)
plt.rcParams.update({'font.size': 13, 'axes.titlesize': 16,
                     'axes.labelsize': 15, 'xtick.labelsize': 13,
                     'ytick.labelsize': 13, 'figure.dpi': 180})

def finish(fig, ax, path):
    ax.grid(axis='y', color='#b0b0b0', alpha=.7)
    ax.set_axisbelow(True)
    fig.savefig(figdir / path, dpi=220)
    plt.close(fig)

fig, ax = plt.subplots(figsize=(7.4, 3.8), layout='constrained')
ax.bar(x, summary.Net_Modelled_Charge_RM, color='#1f77b4')
ax.set_xticks(x, labels)
ax.set_title('October 2025 weather: hypothetical Solar ATAP bill')
ax.set_ylabel('Monthly electricity bill (RM)')
ax.set_ylim(0, 130)
finish(fig, ax, 'graph1_monthly_bill_comparison.png')

fig, ax = plt.subplots(figsize=(7.4, 3.8), layout='constrained')
ax.bar(x-.18, summary.Bill_Without_PV_RM, width=.36, label='Without PV', color='#1f77b4')
ax.bar(x+.18, summary.Net_Modelled_Charge_RM, width=.36,
       label='With PV + Solar ATAP', color='#ff7f0e')
ax.set_xticks(x, labels)
ax.set_title('Effect of rooftop PV and Solar ATAP on domestic bill')
ax.set_ylabel('Monthly electricity bill (RM)')
ax.legend(loc='upper right', fontsize=12)
finish(fig, ax, 'graph2_withoutPV_vs_ATAP.png')

r = summary.iloc[0]
components = ['Energy', 'AFA', 'Capacity', 'Network', 'Retail', 'Export credit']
values = [r.Energy_Charge_RM, r.AFA_Charge_RM, r.Capacity_Charge_RM,
          r.Network_Charge_RM, r.Retail_Charge_RM, -r.Export_Credit_RM]
fig, ax = plt.subplots(figsize=(7.4, 3.8), layout='constrained')
ax.bar(components, values, color=['#1f77b4']*5+['#148a68'])
ax.axhline(0, color='black', lw=.8)
ax.set_xticks(range(6), components, rotation=20)
ax.set_title('25°C modulating bill components and ATAP export credit')
ax.set_ylabel('Charge / credit (RM)')
finish(fig, ax, 'graph4_bill_components.png')
print(summary[['Net_Modelled_Charge_RM','Bill_Without_PV_RM','Export_Credit_RM']].round(2).to_string(index=False))
