"""Explicit account sizing and currency exposure; never infer account inputs."""
from dataclasses import dataclass
import numpy as np
import pandas as pd

@dataclass(frozen=True)
class AccountInputs:
    account_currency: str
    initial_equity: float
    stop_risk_fraction: float
    pip_value_per_lot_in_account: dict
    units_per_lot: dict
    currency_to_account_quotes: dict
    lot_steps: dict
    minimum_lots: dict
    maximum_lots: dict

    def __post_init__(self):
        if self.initial_equity<=0 or not 0<self.stop_risk_fraction<=.02:
            raise ValueError('Require positive initial equity and a stop-risk budget <=2%')
        if not self.account_currency or not all((self.pip_value_per_lot_in_account,self.units_per_lot,self.currency_to_account_quotes,self.lot_steps)):
            raise ValueError('Account currency, broker pip values, lot sizes/steps and conversion quotes are required')


def position_lots(account,symbol,stop_pips,*,equity=None,cost_pips=0.):
    if symbol not in account.pip_value_per_lot_in_account:raise ValueError('Missing broker pip value in account currency')
    pip_value=account.pip_value_per_lot_in_account[symbol];step=account.lot_steps[symbol]
    if min(stop_pips,pip_value,step)<=0:raise ValueError('A positive executable stop and broker lot step are required')
    budget=(equity or account.initial_equity)*account.stop_risk_fraction
    lots=np.floor(budget/((stop_pips+cost_pips)*pip_value)/step)*step
    if lots<account.minimum_lots[symbol]:return 0.
    return min(float(lots),account.maximum_lots[symbol])


def currency_exposure(positions,account):
    """Signed currency inventory in explicit units and account money equivalent."""
    exposure={}
    for r in positions.to_dict('records'):
        sym=r['Symbol'].replace('/','')
        if len(sym)!=6:raise ValueError('Currency exposure requires explicit six-letter FX pairs')
        if sym not in account.units_per_lot:raise ValueError('Missing contract size')
        units=r['lots']*account.units_per_lot[sym]*(1 if r['entry_side']=='BUY' else -1)
        base,quote=sym[:3],sym[3:]
        exposure[base]=exposure.get(base,0)+units
        exposure[quote]=exposure.get(quote,0)-units*r['entry_price']
    rows=[]
    for currency,units in exposure.items():
        if currency not in account.currency_to_account_quotes:raise ValueError('Missing currency conversion quote: '+currency)
        rows.append({'currency':currency,'signed_units':units,'account_currency_equivalent':units*account.currency_to_account_quotes[currency]})
    return pd.DataFrame(rows)


def diagnostic_kelly(win_probability,mean_win,mean_loss):
    if not 0<=win_probability<=1 or min(mean_win,mean_loss)<=0:raise ValueError('Invalid estimated payout inputs')
    raw=win_probability-(1-win_probability)/(mean_win/mean_loss)
    return {'binary_approximation':raw,'nonnegative_reference_fraction':max(0.,raw),'allocation_authorized':False}


def bounded_log_growth_fraction(returns,max_fraction=.25):
    """Single uncorrelated return diagnostic; cannot size a correlated FX book."""
    r=np.asarray(returns,float)
    if not len(r) or not np.isfinite(r).all() or r.min()<-1:raise ValueError('Require bounded-loss account returns')
    grid=np.linspace(0,max_fraction,251)
    growth=np.array([np.log1p(f*r).mean() for f in grid])
    return float(grid[np.argmax(growth)])
