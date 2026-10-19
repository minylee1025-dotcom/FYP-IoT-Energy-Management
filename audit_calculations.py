"""Check frozen case outputs and run deterministic sensitivity checks.

Does not retrieve new weather, edit existing data or alter any figure.
Run: python audit_calculations.py
Dependencies: numpy, pandas. Units: h, kW, kWh, degrees C, RM.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
CASES = [(25, 'baseline'), (25, 'onoff'), (27, 'baseline'), (27, 'onoff')]

def replay(df, target, mode, r=2., c=5., pv_scale=1.):
    a = np.exp(-.5/(r*c))
    cop = 2.64/.86
    t, on = 25., False
    powers, temperatures = [], []
    for to, q in zip(df.Outdoor_Temperature_C, df.Internal_Heat_Gain_kW):
        if mode == 'baseline':
            power = np.clip(((1-a)*(to+r*q)+a*t-target)/((1-a)*r*cop), 0, 2.58)
        else:
            if t >= target+1: on = True
            elif t <= target-.5: on = False
            power = 2.58 if on else 0.
        t = (1-a)*(to+r*q-r*cop*power)+a*t
        powers.append(power)
        temperatures.append(t)
    p = np.array(powers)
    pv = np.clip(df.PV_Power_kW.to_numpy()*pv_scale, 0, 5)
    load = df.Base_Load_kW.to_numpy()+p
    imported = .5*np.maximum(load-pv, 0).sum()
    exported = .5*np.maximum(pv-load, 0).sum()
    return dict(AC_kWh=.5*p.sum(), Import_kWh=imported, Export_kWh=exported,
                Net_RM=max(0, .481*imported+10-.2703*min(imported, exported))), p, np.array(temperatures)

checks, sensitivity, settlements = [], [], []
scenarios = [('Nominal',{}), ('R -20%',{'r':1.6}), ('R +20%',{'r':2.4}),
             ('C -20%',{'c':4.}), ('C +20%',{'c':6.}),
             ('PV -10%',{'pv_scale':.9}), ('PV +10%',{'pv_scale':1.1})]
for target, mode in CASES:
    name = f'{target}C {mode}'
    df = pd.read_csv(DATA/f'monthly_{target}C_{mode}.csv')
    assert len(df) == 1487
    assert pd.to_datetime(df.Time).diff().dropna().eq(pd.Timedelta(minutes=30)).all()
    result, power, temp = replay(df,target,mode)
    p_error = np.max(abs(power-df.AC_Power_kW))
    t_error = np.max(abs(temp-df.Indoor_Temperature_C))
    balance = (df.Household_Energy_kWh+df.Grid_Export_kWh-df.Grid_Import_kWh-df.PV_Energy_kWh).abs().max()
    assert p_error < 1e-9 and t_error < 1e-9 and balance < 1e-9
    assert not ((df.Grid_Import_kWh>1e-9)&(df.Grid_Export_kWh>1e-9)).any()
    checks.append(dict(case=name, rows=len(df), max_power_error=p_error,
                       max_temperature_error=t_error, max_interval_balance_error=balance))
    for scenario, params in scenarios:
        result, _, _ = replay(df,target,mode,**params)
        sensitivity.append(dict(scenario=scenario,case=name,**result))
    i,e = df.Grid_Import_kWh.sum(), df.Grid_Export_kWh.sum()
    for credit_rate in [0., .25, .2703]:
        settlements.append(dict(case=name,credit_rate=credit_rate,
             Net_RM=max(0,.481*i+10-credit_rate*min(i,e)),
             Export_credit_RM=credit_rate*min(i,e)))
pd.DataFrame(sensitivity).to_csv(DATA/'audit_sensitivity.csv',index=False)
pd.DataFrame(settlements).to_csv(DATA/'audit_credit_scenarios.csv',index=False)
(DATA/'audit_checks.json').write_text(json.dumps(checks,indent=2)+'\n')
print(pd.DataFrame(sensitivity).pivot(index='scenario',columns='case',values='Net_RM').round(2).to_string())
print(pd.DataFrame(settlements).pivot(index='credit_rate',columns='case',values='Net_RM').round(2).to_string())
print('All frozen-input replay, interval balance and flow-direction checks passed.')
