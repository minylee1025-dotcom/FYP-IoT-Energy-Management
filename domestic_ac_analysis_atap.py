"""
domestic_ac_analysis_atap.py

Domestic FYP case study with:
- October 2025 residential weather simulation (retrospective hypothetical ATAP billing)
- Sunny/rainy weekday/weekend representative days
- 1R1C residential thermal model
- 3 x 1 HP AC
- 25 C vs 27 C
- Baseline modulating AC vs ON/OFF control
- Simplified rooftop-PV estimate for billing only
- Simplified Domestic (General) bill using lecturer-specified charges
- Solar ATAP export credit

IMPORTANT
---------
1. The existing PV forecasting code is NOT modified by this script.
2. The PV calculation here is only a simple billing-side estimate based on
   measured/archived shortwave radiation. Replace it later with your separate
   PV forecast output if desired.
3. THERMAL_R, THERMAL_C, internal gains, household base-load profile, and PV
   size are modelling assumptions and should be calibrated/justified.
4. Per lecturer instruction, this billing model includes ONLY:
      Energy + AFA + Capacity + Network + Retail
   It intentionally excludes SST, KWTBB, EEI and other charges.
5. For Domestic Solar ATAP, exported electricity is credited using the Energy
   Charge only. Credited export is limited here to imported energy within the
   same monthly billing period. MAQ/technical limits are not modelled.
"""

import os
import math
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import requests


# ============================================================
# 1. GENERAL SETTINGS
# ============================================================

LATITUDE = 3.0734
LONGITUDE = 101.5217

# Residential weather study period. Solar ATAP was not yet active in October 2025;
# its billing rules below are applied only as a hypothetical comparison.
START_DATE = "2025-10-01"
END_DATE = "2025-10-31"

DT_H = 0.5  # 30 minutes

OUTPUT_DIR = "Domestic_ATAP_Output_Oct2025"
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ============================================================
# 2. TEMPERATURE CONTROL SETTINGS
# ============================================================

SETPOINTS_C = [25.0, 27.0]

# Starting indoor temperature for the monthly simulation
T_INITIAL_C = 25.0

# ON/OFF hysteresis around each selected setpoint
# 25 C example:
#   ON  at 26.0 C
#   OFF at 24.5 C
ON_OFFSET_C = 1.0
OFF_OFFSET_C = -0.5


# ============================================================
# 3. 1R1C THERMAL MODEL PARAMETERS
# ============================================================

# PRELIMINARY ASSUMPTIONS - calibrate/justify later.
THERMAL_R_C_PER_KW = 2.0
THERMAL_C_KWH_PER_C = 5.0

# Base residential internal gain
Q_GAIN_BASE_KW = 0.5


# ============================================================
# 4. RESIDENTIAL OCCUPANCY / INTERNAL GAIN
# ============================================================

ENABLE_OCCUPANCY_PROFILE = True


def internal_gain_kw(timestamp):
    """
    Simple residential occupancy/internal-gain assumption.

    Weekday:
      00:00-07:00  lower internal gain
      07:00-09:00  home
      09:00-18:00  reduced occupancy
      18:00-24:00  home

    Weekend:
      00:00-08:00  lower gain
      08:00-24:00  more daytime occupancy

    These multipliers are assumptions, not measured household data.
    """

    if not ENABLE_OCCUPANCY_PROFILE:
        return Q_GAIN_BASE_KW

    hour = timestamp.hour
    is_weekend = timestamp.dayofweek >= 5

    if not is_weekend:
        if 0 <= hour < 7:
            multiplier = 0.6
        elif 7 <= hour < 9:
            multiplier = 1.0
        elif 9 <= hour < 18:
            multiplier = 0.4
        else:
            multiplier = 1.0
    else:
        if 0 <= hour < 8:
            multiplier = 0.6
        else:
            multiplier = 1.0

    return Q_GAIN_BASE_KW * multiplier


# ============================================================
# 5. HOUSEHOLD NON-AC BASE LOAD
# ============================================================

# This is needed because ATAP billing depends on total household demand,
# not AC demand alone.
#
# The values below are only a simple residential profile assumption.
# Replace with measured household load when available.

def household_base_load_kw(timestamp):
    """
    Assumed household electrical load EXCLUDING air conditioning.
    Returns kW.

    Weekday:
      Night           0.35 kW
      Morning         0.70 kW
      Work/study hrs  0.30 kW
      Evening         0.90 kW
      Late night      0.50 kW

    Weekend:
      Higher daytime household occupancy is assumed.
    """

    hour = timestamp.hour
    is_weekend = timestamp.dayofweek >= 5

    if not is_weekend:
        if 0 <= hour < 6:
            return 0.35
        elif 6 <= hour < 9:
            return 0.70
        elif 9 <= hour < 17:
            return 0.30
        elif 17 <= hour < 23:
            return 0.90
        else:
            return 0.50

    else:
        if 0 <= hour < 7:
            return 0.35
        elif 7 <= hour < 10:
            return 0.80
        elif 10 <= hour < 18:
            return 0.65
        elif 18 <= hour < 23:
            return 0.95
        else:
            return 0.50


# ============================================================
# 6. AIR CONDITIONER PARAMETERS
# ============================================================

# Project requirement: 3 x 1 HP AC
NUMBER_OF_AC = 3

# Reference 1 HP unit used in the previous analysis:
# ~2.64 kW thermal cooling, ~0.86 kW electrical input
AC_COOLING_KW_PER_UNIT = 2.64
AC_INPUT_KW_PER_UNIT = 0.86

TOTAL_AC_COOLING_KW = NUMBER_OF_AC * AC_COOLING_KW_PER_UNIT
TOTAL_AC_INPUT_KW = NUMBER_OF_AC * AC_INPUT_KW_PER_UNIT

# Rated-point COP
AC_COP = AC_COOLING_KW_PER_UNIT / AC_INPUT_KW_PER_UNIT


# ============================================================
# 7. SIMPLE ROOFTOP PV MODEL FOR BILLING
# ============================================================

# This DOES NOT replace your separate PV forecasting model.
# It only gives this billing script a self-contained PV estimate.

PV_SIZE_KWP = 5.0

# Aggregate PV system loss assumption for simplified calculation.
PV_SYSTEM_LOSS_FRACTION = 0.14

# Nominal reference irradiance
REFERENCE_IRRADIANCE_WM2 = 1000.0


def estimate_pv_power_kw(irradiance_wm2):
    """
    Very simple PV billing-side estimate:

        P_pv = PV_size * (G / 1000) * (1 - losses)

    Clipped to the installed DC rating.

    Replace this column later with your actual PV forecast output if desired.
    """
    p = (
        PV_SIZE_KWP
        * (irradiance_wm2 / REFERENCE_IRRADIANCE_WM2)
        * (1.0 - PV_SYSTEM_LOSS_FRACTION)
    )

    return np.clip(p, 0.0, PV_SIZE_KWP)


# ============================================================
# 8. ILLUSTRATIVE DOMESTIC TARIFF / RETROSPECTIVE ATAP SCENARIO
# ============================================================

# Only the lecturer-requested charges are included.
# October 2025 weather is paired with a later hypothetical Solar ATAP settlement.
# The simplified calculation intentionally does not apply actual account exemptions.

ENERGY_RATE_RM_PER_KWH = 0.2703  # domestic general, modelled monthly use below 1,500 kWh
AFA_RATE_RM_PER_KWH = 0.0367       # September 2026 rate, used here uniformly as a scenario
CAPACITY_RATE_RM_PER_KWH = 0.0455
NETWORK_RATE_RM_PER_KWH = 0.1285
RETAIL_RM_PER_MONTH = 10.00

# Total import variable rate used for the simplified bill
IMPORT_VARIABLE_RATE_RM_PER_KWH = (
    ENERGY_RATE_RM_PER_KWH
    + AFA_RATE_RM_PER_KWH
    + CAPACITY_RATE_RM_PER_KWH
    + NETWORK_RATE_RM_PER_KWH
)

# Domestic Solar ATAP export credit uses Energy Charge only.
ATAP_EXPORT_CREDIT_RM_PER_KWH = ENERGY_RATE_RM_PER_KWH


# ============================================================
# 9. SUNNY / RAINY CLASSIFICATION
# ============================================================

SUNNY_MAX_RAIN_MM = 0.5
RAINY_MIN_RAIN_MM = 1.0


# ============================================================
# 10. DOWNLOAD WEATHER
# ============================================================

def get_weather_data():
    url = "https://archive-api.open-meteo.com/v1/archive"

    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "start_date": START_DATE,
        "end_date": END_DATE,
        "hourly": "temperature_2m,shortwave_radiation,precipitation",
        "timezone": "Asia/Kuala_Lumpur",
    }

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()

    data = response.json()

    hourly = pd.DataFrame({
        "Time": pd.to_datetime(data["hourly"]["time"]),
        "Outdoor_Temperature_C": data["hourly"]["temperature_2m"],
        "Solar_Irradiance_Wm2": data["hourly"]["shortwave_radiation"],
        "Precipitation_mm": data["hourly"]["precipitation"],
    })

    hourly = hourly.set_index("Time")

    # Temperature + irradiance: interpolate to 30 min.
    weather = (
        hourly[
            ["Outdoor_Temperature_C", "Solar_Irradiance_Wm2"]
        ]
        .resample("30min")
        .interpolate("linear")
    )

    # Hourly precipitation accumulation is split equally into the
    # two 30-min intervals so daily totals are preserved.
    rain = (
        hourly[["Precipitation_mm"]]
        .resample("30min")
        .ffill()
        / 2.0
    )

    weather = weather.join(rain).reset_index()

    weather["Base_Load_kW"] = weather["Time"].apply(
        household_base_load_kw
    )

    weather["Internal_Heat_Gain_kW"] = weather["Time"].apply(
        internal_gain_kw
    )

    weather["PV_Power_kW"] = estimate_pv_power_kw(
        weather["Solar_Irradiance_Wm2"]
    )

    return weather


# ============================================================
# 11. THERMAL MODEL
# ============================================================

def decay_factor():
    return math.exp(
        -DT_H / (
            THERMAL_R_C_PER_KW
            * THERMAL_C_KWH_PER_C
        )
    )


def simulate_baseline(weather, setpoint):
    """
    Baseline modulating controller.

    Calculates the AC electrical power required at each 30-min step
    to bring the NEXT indoor temperature toward the selected setpoint.
    """

    a = decay_factor()
    t_in = T_INITIAL_C

    indoor = []
    ac_power = []
    ac_energy = []
    required_steady_power = []

    for _, row in weather.iterrows():

        t_out = row["Outdoor_Temperature_C"]
        q_gain = row["Internal_Heat_Gain_kW"]

        # Steady-state required AC electrical power
        p_steady = (
            t_out
            + THERMAL_R_C_PER_KW * q_gain
            - setpoint
        ) / (
            THERMAL_R_C_PER_KW
            * AC_COP
        )

        p_steady = max(0.0, p_steady)

        # Dynamic power required for the next timestep
        denominator = (
            (1 - a)
            * THERMAL_R_C_PER_KW
            * AC_COP
        )

        p_required = (
            (1 - a)
            * (
                t_out
                + THERMAL_R_C_PER_KW * q_gain
            )
            + a * t_in
            - setpoint
        ) / denominator

        p_required = max(0.0, p_required)

        # AC cannot exceed installed electrical input capacity
        p_ac = min(
            p_required,
            TOTAL_AC_INPUT_KW
        )

        q_ac = AC_COP * p_ac

        t_next = (
            (1 - a)
            * (
                t_out
                + THERMAL_R_C_PER_KW * q_gain
                - THERMAL_R_C_PER_KW * q_ac
            )
            + a * t_in
        )

        indoor.append(t_next)
        ac_power.append(p_ac)
        ac_energy.append(p_ac * DT_H)
        required_steady_power.append(p_steady)

        t_in = t_next

    result = weather.copy()

    result["Indoor_Temperature_C"] = indoor
    result["AC_Power_kW"] = ac_power
    result["AC_Energy_kWh"] = ac_energy
    result["Required_Steady_AC_Power_kW"] = required_steady_power

    return result


def simulate_onoff(weather, setpoint):
    """
    ON/OFF controller.

    Example at 25 C:
        AC ON  when Tin >= 26.0 C
        AC OFF when Tin <= 24.5 C
    """

    a = decay_factor()

    t_in = T_INITIAL_C
    ac_on = False

    t_on = setpoint + ON_OFFSET_C
    t_off = setpoint + OFF_OFFSET_C

    indoor = []
    ac_status = []
    ac_power = []
    ac_energy = []

    for _, row in weather.iterrows():

        t_out = row["Outdoor_Temperature_C"]
        q_gain = row["Internal_Heat_Gain_kW"]

        if t_in >= t_on:
            ac_on = True
        elif t_in <= t_off:
            ac_on = False

        p_ac = TOTAL_AC_INPUT_KW if ac_on else 0.0
        q_ac = AC_COP * p_ac

        t_next = (
            (1 - a)
            * (
                t_out
                + THERMAL_R_C_PER_KW * q_gain
                - THERMAL_R_C_PER_KW * q_ac
            )
            + a * t_in
        )

        indoor.append(t_next)
        ac_status.append(int(ac_on))
        ac_power.append(p_ac)
        ac_energy.append(p_ac * DT_H)

        t_in = t_next

    result = weather.copy()

    result["Indoor_Temperature_C"] = indoor
    result["AC_Status"] = ac_status
    result["AC_Power_kW"] = ac_power
    result["AC_Energy_kWh"] = ac_energy

    return result


# ============================================================
# 12. GRID IMPORT / EXPORT
# ============================================================

def add_grid_flows(result):
    """
    Total household load:
        Base load + AC load

    PV first serves the household locally.

    Import:
        max(load - PV, 0)

    Export:
        max(PV - load, 0)
    """

    x = result.copy()

    x["Total_Household_Load_kW"] = (
        x["Base_Load_kW"]
        + x["AC_Power_kW"]
    )

    x["Grid_Import_kW"] = np.maximum(
        x["Total_Household_Load_kW"]
        - x["PV_Power_kW"],
        0.0
    )

    x["Grid_Export_kW"] = np.maximum(
        x["PV_Power_kW"]
        - x["Total_Household_Load_kW"],
        0.0
    )

    x["Grid_Import_kWh"] = (
        x["Grid_Import_kW"] * DT_H
    )

    x["Grid_Export_kWh"] = (
        x["Grid_Export_kW"] * DT_H
    )

    x["Household_Energy_kWh"] = (
        x["Total_Household_Load_kW"] * DT_H
    )

    x["PV_Energy_kWh"] = (
        x["PV_Power_kW"] * DT_H
    )

    return x


# ============================================================
# 13. BILL CALCULATION
# ============================================================

def calculate_monthly_bill(result):
    """
    Simplified lecturer-requested bill.

    INCLUDED:
        Energy
        AFA
        Capacity
        Network
        Retail RM10/month

    EXCLUDED:
        SST
        KWTBB
        EEI
        Other charges

    Domestic Solar ATAP:
        export credit = credited export energy * Energy Charge

    Export credited here is capped at monthly imported energy.
    """

    import_kwh = result["Grid_Import_kWh"].sum()
    export_kwh = result["Grid_Export_kWh"].sum()

    # Same-billing-period credit limit used in this simplified model
    credited_export_kwh = min(
        export_kwh,
        import_kwh
    )

    energy_charge = (
        import_kwh
        * ENERGY_RATE_RM_PER_KWH
    )

    afa_charge = (
        import_kwh
        * AFA_RATE_RM_PER_KWH
    )

    capacity_charge = (
        import_kwh
        * CAPACITY_RATE_RM_PER_KWH
    )

    network_charge = (
        import_kwh
        * NETWORK_RATE_RM_PER_KWH
    )

    retail_charge = RETAIL_RM_PER_MONTH

    atap_export_credit = (
        credited_export_kwh
        * ATAP_EXPORT_CREDIT_RM_PER_KWH
    )

    gross_bill = (
        energy_charge
        + afa_charge
        + capacity_charge
        + network_charge
        + retail_charge
    )

    net_bill = max(
        0.0,
        gross_bill - atap_export_credit
    )

    return {
        "Import_kWh": import_kwh,
        "Export_kWh": export_kwh,
        "Credited_Export_kWh": credited_export_kwh,

        "Energy_Charge_RM": energy_charge,
        "AFA_Charge_RM": afa_charge,
        "Capacity_Charge_RM": capacity_charge,
        "Network_Charge_RM": network_charge,
        "Retail_Charge_RM": retail_charge,

        "Gross_Bill_RM": gross_bill,
        "ATAP_Export_Credit_RM": atap_export_credit,
        "Net_Bill_RM": net_bill,
    }


# ============================================================
# 14. NO-PV REFERENCE BILL
# ============================================================

def calculate_no_pv_bill(result):
    """
    Reference bill if the same household/AC load had no rooftop PV.
    No ATAP export is possible.
    """

    load_kwh = result["Household_Energy_kWh"].sum()

    energy_charge = (
        load_kwh
        * ENERGY_RATE_RM_PER_KWH
    )

    afa_charge = (
        load_kwh
        * AFA_RATE_RM_PER_KWH
    )

    capacity_charge = (
        load_kwh
        * CAPACITY_RATE_RM_PER_KWH
    )

    network_charge = (
        load_kwh
        * NETWORK_RATE_RM_PER_KWH
    )

    gross = (
        energy_charge
        + afa_charge
        + capacity_charge
        + network_charge
        + RETAIL_RM_PER_MONTH
    )

    return gross


# ============================================================
# 15. REPRESENTATIVE DAY CLASSIFICATION
# ============================================================

def daily_summary(weather):
    x = weather.copy()

    x["Date"] = x["Time"].dt.date

    x["Day_Type"] = np.where(
        x["Time"].dt.dayofweek < 5,
        "Weekday",
        "Weekend"
    )

    daily = (
        x.groupby(
            ["Date", "Day_Type"],
            as_index=False
        )
        .agg(
            Daily_Solar_kWh_m2=(
                "Solar_Irradiance_Wm2",
                lambda s: s.sum() * DT_H / 1000.0
            ),
            Daily_Precipitation_mm=(
                "Precipitation_mm",
                "sum"
            ),
            Average_Temperature_C=(
                "Outdoor_Temperature_C",
                "mean"
            ),
            Maximum_Temperature_C=(
                "Outdoor_Temperature_C",
                "max"
            ),
            Estimated_PV_Energy_kWh=(
                "PV_Power_kW",
                lambda s: s.sum() * DT_H
            ),
        )
    )

    return daily


def select_representative_days(daily):
    selected = {}

    for day_type in ["Weekday", "Weekend"]:

        subset = daily[
            daily["Day_Type"] == day_type
        ].copy()

        # Sunny:
        # low/no rain, then choose highest solar energy
        sunny_candidates = subset[
            subset["Daily_Precipitation_mm"]
            <= SUNNY_MAX_RAIN_MM
        ]

        if sunny_candidates.empty:
            sunny_candidates = subset.copy()

        sunny = (
            sunny_candidates
            .sort_values(
                [
                    "Daily_Solar_kWh_m2",
                    "Daily_Precipitation_mm"
                ],
                ascending=[False, True]
            )
            .iloc[0]
        )

        # Rainy:
        # actual rainfall, then choose the largest daily total
        rainy_candidates = subset[
            subset["Daily_Precipitation_mm"]
            >= RAINY_MIN_RAIN_MM
        ]

        if rainy_candidates.empty:
            rainy_candidates = subset.copy()

        rainy = (
            rainy_candidates
            .sort_values(
                [
                    "Daily_Precipitation_mm",
                    "Daily_Solar_kWh_m2"
                ],
                ascending=[False, True]
            )
            .iloc[0]
        )

        selected[
            f"Sunny {day_type}"
        ] = sunny["Date"]

        selected[
            f"Rainy {day_type}"
        ] = rainy["Date"]

    return selected


# ============================================================
# 16. RUN MONTHLY ANALYSIS
# ============================================================

def main():

    print(f"Downloading historical weather: {START_DATE} to {END_DATE}...")
    print("NOTE: Solar ATAP billing is hypothetical for October 2025; tariff rates are scenario assumptions.")
    weather = get_weather_data()

    print("\n========================================")
    print("TARIFF USED")
    print("========================================")
    print(f"Energy     : RM {ENERGY_RATE_RM_PER_KWH:.4f}/kWh")
    print(f"AFA assumed: RM {AFA_RATE_RM_PER_KWH:.4f}/kWh")
    print(f"Capacity   : RM {CAPACITY_RATE_RM_PER_KWH:.4f}/kWh")
    print(f"Network    : RM {NETWORK_RATE_RM_PER_KWH:.4f}/kWh")
    print(f"Retail     : RM {RETAIL_RM_PER_MONTH:.2f}/month")
    print(
        f"Total variable import rate: "
        f"RM {IMPORT_VARIABLE_RATE_RM_PER_KWH:.4f}/kWh"
    )
    print(
        f"Domestic ATAP export credit: "
        f"RM {ATAP_EXPORT_CREDIT_RM_PER_KWH:.4f}/kWh"
    )

    # --------------------------------------------------------
    # Representative weather days
    # --------------------------------------------------------

    daily = daily_summary(weather)

    daily.to_csv(
        os.path.join(
            OUTPUT_DIR,
            "daily_weather_summary.csv"
        ),
        index=False
    )

    selected_days = select_representative_days(
        daily
    )

    print("\n========================================")
    print("REPRESENTATIVE DAYS")
    print("========================================")

    for scenario, date in selected_days.items():

        r = daily[
            daily["Date"] == date
        ].iloc[0]

        print(
            f"{scenario}: {date} | "
            f"solar={r['Daily_Solar_kWh_m2']:.2f} kWh/m2/day | "
            f"rain={r['Daily_Precipitation_mm']:.2f} mm | "
            f"PV={r['Estimated_PV_Energy_kWh']:.2f} kWh"
        )

    # --------------------------------------------------------
    # Monthly thermal/control scenarios
    # --------------------------------------------------------

    results = {}
    bill_rows = []

    for setpoint in SETPOINTS_C:

        baseline = simulate_baseline(
            weather,
            setpoint
        )

        onoff = simulate_onoff(
            weather,
            setpoint
        )

        baseline = add_grid_flows(
            baseline
        )

        onoff = add_grid_flows(
            onoff
        )

        bill_baseline = calculate_monthly_bill(
            baseline
        )

        bill_onoff = calculate_monthly_bill(
            onoff
        )

        no_pv_baseline_bill = calculate_no_pv_bill(
            baseline
        )

        no_pv_onoff_bill = calculate_no_pv_bill(
            onoff
        )

        results[setpoint] = {
            "baseline": baseline,
            "onoff": onoff,
            "bill_baseline": bill_baseline,
            "bill_onoff": bill_onoff,
            "no_pv_baseline_bill": no_pv_baseline_bill,
            "no_pv_onoff_bill": no_pv_onoff_bill,
        }

        for control_name, df_result, bill, no_pv_bill in [

            (
                "Baseline",
                baseline,
                bill_baseline,
                no_pv_baseline_bill
            ),

            (
                "ON/OFF",
                onoff,
                bill_onoff,
                no_pv_onoff_bill
            )
        ]:

            bill_rows.append({

                "Setpoint_C":
                    setpoint,

                "Control":
                    control_name,

                "AC_Energy_kWh":
                    df_result[
                        "AC_Energy_kWh"
                    ].sum(),

                "Household_Energy_kWh":
                    df_result[
                        "Household_Energy_kWh"
                    ].sum(),

                "PV_Energy_kWh":
                    df_result[
                        "PV_Energy_kWh"
                    ].sum(),

                "Grid_Import_kWh":
                    bill["Import_kWh"],

                "Grid_Export_kWh":
                    bill["Export_kWh"],

                "Credited_Export_kWh":
                    bill[
                        "Credited_Export_kWh"
                    ],

                "Bill_Without_PV_RM":
                    no_pv_bill,

                "Energy_Charge_RM":
                    bill["Energy_Charge_RM"],

                "AFA_Charge_RM":
                    bill["AFA_Charge_RM"],

                "Capacity_Charge_RM":
                    bill["Capacity_Charge_RM"],

                "Network_Charge_RM":
                    bill["Network_Charge_RM"],

                "Retail_Charge_RM":
                    bill["Retail_Charge_RM"],

                "ATAP_Export_Credit_RM":
                    bill[
                        "ATAP_Export_Credit_RM"
                    ],

                "Bill_With_ATAP_RM":
                    bill["Net_Bill_RM"],

                "PV_ATAP_Saving_RM":
                    no_pv_bill
                    - bill["Net_Bill_RM"],
            })

        # Save timestep results
        baseline.to_csv(
            os.path.join(
                OUTPUT_DIR,
                f"monthly_{int(setpoint)}C_baseline.csv"
            ),
            index=False
        )

        onoff.to_csv(
            os.path.join(
                OUTPUT_DIR,
                f"monthly_{int(setpoint)}C_onoff.csv"
            ),
            index=False
        )

    bill_summary = pd.DataFrame(
        bill_rows
    )

    bill_summary.to_csv(
        os.path.join(
            OUTPUT_DIR,
            "monthly_bill_summary.csv"
        ),
        index=False
    )

    # --------------------------------------------------------
    # Calculate important reductions
    # --------------------------------------------------------

    b25 = results[25.0]["bill_baseline"]["Net_Bill_RM"]
    o25 = results[25.0]["bill_onoff"]["Net_Bill_RM"]

    b27 = results[27.0]["bill_baseline"]["Net_Bill_RM"]
    o27 = results[27.0]["bill_onoff"]["Net_Bill_RM"]

    reduction_onoff_25 = b25 - o25
    reduction_onoff_25_pct = (
        100 * reduction_onoff_25 / b25
        if b25 > 0
        else 0.0
    )

    reduction_setpoint = b25 - b27
    reduction_setpoint_pct = (
        100 * reduction_setpoint / b25
        if b25 > 0
        else 0.0
    )

    reduction_combined = b25 - o27
    reduction_combined_pct = (
        100 * reduction_combined / b25
        if b25 > 0
        else 0.0
    )

    print("\n========================================")
    print("MONTHLY BILL SUMMARY")
    print("========================================")
    print(bill_summary.to_string(index=False))

    print("\n========================================")
    print("MAIN BILL REDUCTIONS")
    print("========================================")

    print(
        f"25C baseline bill with ATAP: "
        f"RM {b25:.2f}"
    )

    print(
        f"25C ON/OFF bill with ATAP: "
        f"RM {o25:.2f}"
    )

    print(
        f"ON/OFF saving at 25C: "
        f"RM {reduction_onoff_25:.2f} "
        f"({reduction_onoff_25_pct:.2f}%)"
    )

    print(
        f"\n27C baseline bill with ATAP: "
        f"RM {b27:.2f}"
    )

    print(
        f"25C -> 27C baseline bill saving: "
        f"RM {reduction_setpoint:.2f} "
        f"({reduction_setpoint_pct:.2f}%)"
    )

    print(
        f"\n27C + ON/OFF bill with ATAP: "
        f"RM {o27:.2f}"
    )

    print(
        f"Combined saving vs 25C baseline: "
        f"RM {reduction_combined:.2f} "
        f"({reduction_combined_pct:.2f}%)"
    )

    # ========================================================
    # GRAPH 1
    # MONTHLY BILL - 25C AND 27C, BASELINE VS ON/OFF
    # ========================================================

    labels = [
        "25C Baseline",
        "25C ON/OFF",
        "27C Baseline",
        "27C ON/OFF"
    ]

    bills = [
        b25,
        o25,
        b27,
        o27
    ]

    plt.figure(
        figsize=(10, 6)
    )

    plt.bar(
        labels,
        bills
    )

    plt.ylabel(
        "Monthly Electricity Bill (RM)"
    )

    plt.title(
        "October 2025 Weather: Hypothetical Solar ATAP Bill"
    )

    plt.grid(
        axis="y"
    )

    plt.tight_layout()

    plt.savefig(
        os.path.join(
            OUTPUT_DIR,
            "graph1_monthly_bill_comparison.png"
        ),
        dpi=300
    )

    plt.show()

    # ========================================================
    # GRAPH 2
    # WITHOUT PV VS WITH ATAP
    # ========================================================

    no_pv_bills = [
        results[25.0]["no_pv_baseline_bill"],
        results[25.0]["no_pv_onoff_bill"],
        results[27.0]["no_pv_baseline_bill"],
        results[27.0]["no_pv_onoff_bill"],
    ]

    atap_bills = [
        b25,
        o25,
        b27,
        o27
    ]

    x = np.arange(
        len(labels)
    )

    width = 0.35

    plt.figure(
        figsize=(11, 6)
    )

    plt.bar(
        x - width / 2,
        no_pv_bills,
        width,
        label="Without PV"
    )

    plt.bar(
        x + width / 2,
        atap_bills,
        width,
        label="With PV + Solar ATAP"
    )

    plt.xticks(
        x,
        labels,
        rotation=15
    )

    plt.ylabel(
        "Monthly Electricity Bill (RM)"
    )

    plt.title(
        "Effect of Rooftop PV and Solar ATAP on Domestic Bill"
    )

    plt.legend()

    plt.grid(
        axis="y"
    )

    plt.tight_layout()

    plt.savefig(
        os.path.join(
            OUTPUT_DIR,
            "graph2_withoutPV_vs_ATAP.png"
        ),
        dpi=300
    )

    plt.show()

    # ========================================================
    # GRAPH 3
    # MONTHLY AC ENERGY
    # ========================================================

    ac_energy = [

        results[25.0][
            "baseline"
        ]["AC_Energy_kWh"].sum(),

        results[25.0][
            "onoff"
        ]["AC_Energy_kWh"].sum(),

        results[27.0][
            "baseline"
        ]["AC_Energy_kWh"].sum(),

        results[27.0][
            "onoff"
        ]["AC_Energy_kWh"].sum(),
    ]

    plt.figure(
        figsize=(10, 6)
    )

    plt.bar(
        labels,
        ac_energy
    )

    plt.ylabel(
        "Monthly AC Electrical Energy (kWh)"
    )

    plt.title(
        "Monthly AC Energy Consumption"
    )

    plt.grid(
        axis="y"
    )

    plt.tight_layout()

    plt.savefig(
        os.path.join(
            OUTPUT_DIR,
            "graph3_monthly_ac_energy.png"
        ),
        dpi=300
    )

    plt.show()

    # ========================================================
    # GRAPH 4
    # BILL COMPONENTS FOR 25C BASELINE
    # ========================================================

    bill25 = results[
        25.0
    ]["bill_baseline"]

    component_names = [
        "Energy",
        "AFA",
        "Capacity",
        "Network",
        "Retail"
    ]

    component_values = [
        bill25["Energy_Charge_RM"],
        bill25["AFA_Charge_RM"],
        bill25["Capacity_Charge_RM"],
        bill25["Network_Charge_RM"],
        bill25["Retail_Charge_RM"]
    ]

    plt.figure(
        figsize=(9, 6)
    )

    plt.bar(
        component_names,
        component_values
    )

    plt.ylabel(
        "Charge (RM)"
    )

    plt.title(
        "25C Baseline Bill Components Before ATAP Export Credit"
    )

    plt.grid(
        axis="y"
    )

    plt.tight_layout()

    plt.savefig(
        os.path.join(
            OUTPUT_DIR,
            "graph4_bill_components.png"
        ),
        dpi=300
    )

    plt.show()

    # ========================================================
    # GRAPH 5
    # REPRESENTATIVE DAY PV: SUNNY/RAINY WEEKDAY/WEEKEND
    # ========================================================

    plt.figure(
        figsize=(12, 6)
    )

    for scenario, selected_date in selected_days.items():

        day = weather[
            weather["Time"].dt.date
            == selected_date
        ]

        hours = (
            day["Time"].dt.hour
            + day["Time"].dt.minute / 60
        )

        plt.plot(
            hours,
            day["PV_Power_kW"],
            label=scenario
        )

    plt.xlabel(
        "Time of Day (hour)"
    )

    plt.ylabel(
        "Estimated Rooftop PV Power (kW)"
    )

    plt.title(
        "Representative Sunny/Rainy Weekday and Weekend PV"
    )

    plt.xticks(
        np.arange(0, 25, 2)
    )

    plt.legend()

    plt.grid()

    plt.tight_layout()

    plt.savefig(
        os.path.join(
            OUTPUT_DIR,
            "graph5_representative_day_pv.png"
        ),
        dpi=300
    )

    plt.show()

    # ========================================================
    # GRAPH 6
    # REPRESENTATIVE DAY GRID IMPORT - 25C BASELINE
    # ========================================================

    monthly_25_baseline = results[
        25.0
    ]["baseline"]

    plt.figure(
        figsize=(12, 6)
    )

    for scenario, selected_date in selected_days.items():

        day = monthly_25_baseline[
            monthly_25_baseline[
                "Time"
            ].dt.date == selected_date
        ]

        hours = (
            day["Time"].dt.hour
            + day["Time"].dt.minute / 60
        )

        plt.plot(
            hours,
            day["Grid_Import_kW"],
            label=scenario
        )

    plt.xlabel(
        "Time of Day (hour)"
    )

    plt.ylabel(
        "Grid Import Power (kW)"
    )

    plt.title(
        "25C Baseline Grid Import: Four Representative Days"
    )

    plt.xticks(
        np.arange(0, 25, 2)
    )

    plt.legend()

    plt.grid()

    plt.tight_layout()

    plt.savefig(
        os.path.join(
            OUTPUT_DIR,
            "graph6_representative_grid_import.png"
        ),
        dpi=300
    )

    plt.show()

    print(
        f"\nAll outputs saved to: {OUTPUT_DIR}"
    )


if __name__ == "__main__":
    main()
