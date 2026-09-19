from __future__ import annotations
VARIANTS=("existing production system","equal-weight fusion","dynamic weighting only","dynamic plus conditional reliability","dynamic plus reliability plus changepoint control","full ARCEF-SV")
def build():
    return [{"variant":v,"direction_accuracy":None,"balanced_accuracy":None,"macro_f1":None,"brier_score":None,"log_loss":None,"calibration_error":None,"interval_coverage":None,"interval_width":None,"expected_value":None,"maximum_drawdown":None,"decision_turnover":None,"wait_frequency":None,"buy_frequency":None,"sell_frequency":None,"pbo":None,"status":"requires settled walk-forward sample"} for v in VARIANTS]
