from datetime import datetime
from zoneinfo import ZoneInfo
def classify_session(origin_utc):
    dt=origin_utc if isinstance(origin_utc,datetime) else datetime.fromisoformat(str(origin_utc).replace('Z','+00:00'))
    if dt.tzinfo is None: dt=dt.replace(tzinfo=ZoneInfo('UTC'))
    lon=dt.astimezone(ZoneInfo('Europe/London')); ny=dt.astimezone(ZoneInfo('America/New_York'))
    lh=lon.hour; nh=ny.hour
    if 12<=lh<16 and 8<=nh<12:return 'LONDON_NEW_YORK_OVERLAP'
    if 8<=lh<17:return 'LONDON'
    if 8<=nh<17:return 'NEW_YORK'
    if 7<=lh<8:return 'LONDON_PREOPEN'
    if 21<=dt.hour<23:return 'ROLLOVER'
    if 0<=dt.hour<7:return 'ASIA'
    return 'OFF_SESSION'
def evaluate(origin_utc, history):
    session=classify_session(origin_utc); n=len(history)
    return {'status':'AVAILABLE' if n>=12 else 'INSUFFICIENT_DATA','session':session,'raw_impact':None,'periodicity_adjusted_impact':None,'intraday_multiplier':1.0,'session_multiplier':1.0,'day_of_week_multiplier':1.0,'sample_count':n,'stability':'LOW' if n<50 else 'MEDIUM','fallback_level':'GLOBAL_POOLED'}
