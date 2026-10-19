# IoT-Based Smart Energy Management for Residential Homes under Malaysia’s ATAP Initiative

This project investigates how air-conditioning (AC) control and rooftop photovoltaic (PV) generation affect residential electricity consumption, grid imports, exports and electricity charges.

The Python simulation compares four AC operating cases using October 2025 weather for a location near Shah Alam, Malaysia. The project also includes a Raspberry Pi and Home Assistant prototype for device monitoring and AC control, documented in the accompanying report.

## Simulation cases

The study compares:

1. 25°C with modulating AC control
2. 25°C with on/off AC control
3. 27°C with modulating AC control
4. 27°C with on/off AC control

The model uses 30-minute intervals, a simplified building thermal model and a 5-kWp PV system.

## Repository contents

| File or folder | Description |
|---|---|
| `domestic_ac_analysis_atap.py` | Main weather, AC, PV and electricity-charge simulation |
| `audit_calculations.py` | Reproduces the saved control results, checks energy balances and performs sensitivity analysis |
| `rebill_from_case_csv.py` | Recalculates electricity charges from the saved simulation data |
| `render_zip_style_billing.py` | Generates billing charts from the revised billing summary |
| `data/` | Saved simulation data, summaries and analysis outputs |
| `figures/` | Figures used to present the results |

## Requirements

Install Python and the required packages:

```bash
python -m pip install numpy pandas matplotlib requests
```

## Running the analysis

Open a terminal in the project folder.

### Check the saved results

To check the saved simulation results and run the sensitivity analysis:

```bash
python audit_calculations.py
```

This uses the existing files in `data/` and does not require a new weather download.

### Run the main simulation

```bash
python domestic_ac_analysis_atap.py
```

The main script requires an internet connection to retrieve archived weather. It saves its outputs in:

```text
Domestic_ATAP_Output_Oct2025/
```

### Recalculate billing and regenerate billing figures

```bash
python rebill_from_case_csv.py
python render_zip_style_billing.py
```

These commands use the saved data in `data/`, update the billing outputs and overwrite the corresponding figures.

## Main outputs

- AC electricity consumption
- Modeled indoor temperature
- Estimated PV generation
- Grid import and export energy
- Eligible export credit and net electricity charges
- Comparisons between sunny and rainy weekdays and weekends
- Sensitivity to thermal parameters, PV output and export-credit assumptions

## Billing assumptions

The illustrative calculation uses:

- Import charge: RM0.4810/kWh
- Eligible export credit: RM0.2703/kWh
- Monthly retail charge: RM10

Eligible exports are capped at monthly imported energy in the simplified calculation. Later Solar ATAP settlement assumptions are applied to October 2025 weather as a hypothetical comparison.

## IoT prototype

The associated prototype uses Raspberry Pi, Home Assistant, Tuya devices and a Node-RED/IAMMETER monitoring feed. The report documents the setup and dashboard screenshots.

The Python results are simulations. Connecting the simulated control policies to synchronized household measurements is a subsequent implementation stage.

## Data coverage

The saved dataset contains 1,487 half-hour intervals and ends at 23:00 on 31 October 2025. The final 23:30 interval is omitted consistently across all four cases.

The sensitivity tests explore changes in selected assumptions; they are not statistical confidence intervals or field-validation results.
