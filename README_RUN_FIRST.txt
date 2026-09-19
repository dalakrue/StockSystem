ADX Quant Pro — Top-30 Three-Selector Fast Field 3 Upgrade (2026-07-29)

Windows launch:
1. Extract this ZIP.
2. Open Command Prompt in the extracted folder.
3. Install dependencies once:
   python -m pip install -r requirements.txt
4. Start the app:
   streamlit run app.py

Recommended workflow:
1. Open Settings. The automatic/default timeframe is now H1.
2. Select symbols in any one, two, or all three selectors.
3. Use First Best 10, Second Best 10, and the Selector 3
   "Third Best 10 — Spread <25 + DXY" choices when useful.
4. Choose either workflow:
   A) Existing workflow: Load the selected symbols, then click Super Quick.
   B) New one-click workflow: click
      "Load & Update Latest Candles + Run Super Quick".
      This refreshes the latest completed candles and starts Super Quick without
      restarting the app.
5. Super Quick calculates these compact Field 3 sections for every loaded symbol:
   - Regime Age Ranking — Candle After Regime Start Only
     (ranked only by Higher regime start age)
   - Middle Regime Age Ranking — Candle After Middle Regime Start Only
     (ranked only by Middle regime start age)
   - Higher Standard Summary
6. Click Quick for the deferred Lower/Middle summary tables, final cross-symbol
   ranking, Field 10/11, AI, research and trust-history calculations.

Field 3 color rules:
- Green row = Top 5 rank.
- Red row = Last 5 rank.
- Blue whole row in the Higher-age table = Lower, Middle and Higher Regime Bias
  are all the same.
- Blue whole row in the Middle-age table = Middle Regime Bias and Lower Regime
  Bias are the same.

Important:
- The normal Super Quick button makes zero new market API requests and uses
  candles already validated by Settings.
- The new Load & Update button intentionally refreshes data first, then runs the
  same fast Super Quick calculation.
- If no newer completed candle exists, the unchanged fast result can be reused.
- Rank 1 means the newest/recent regime start: the smallest completed-candle age.
