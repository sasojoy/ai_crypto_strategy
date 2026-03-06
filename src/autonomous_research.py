import os
import json
import pandas as pd
import google.generativeai as genai
from datetime import datetime
from src.evaluate import get_full_report

# Configure Gemini API
api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=api_key)

def log_research(message):
    os.makedirs('logs', exist_ok=True)
    with open('logs/research_dialog.log', 'a', encoding='utf-8') as f:
        f.write(f"[{datetime.now().isoformat()}] {message}\n")

def quality_gate(results, params):
    """
    自省評審模組 (The Judge Logic) - Iteration 14
    防止過度擬合、生存參數限制、樣本門檻。
    """
    log_research("--- Judge Logic: Quality Gate Check (Iteration 14) ---")

    # 1. 生存參數限制: sl_mult >= 2.5
    if params.get('sl_mult', 0) < 2.5:
        log_research(f"REJECTED: sl_mult {params['sl_mult']} < 2.5 (Too narrow)")
        return False, "止損倍數過窄 (sl_mult < 2.5)"

    total_trades = sum(res['train']['trades'] + res['test']['trades'] for res in results.values())
    # 2. 樣本門檻: 總交易次數 > 20 (Increased for 120d window)
    if total_trades <= 20:
        log_research(f"REJECTED: Total trades {total_trades} <= 20 (Statistically insignificant)")
        return False, f"樣本數不足 ({total_trades} 次交易)"

    for sym, res in results.items():
        tr = res['train']
        ts = res['test']

        # 3. 滾動窗口驗證: 兩段時間皆必須維持正報酬
        if tr['profit'] <= 0 or ts['profit'] <= 0:
            log_research(f"REJECTED: {sym} failed positive profit check (Train: {tr['profit']}, Test: {ts['profit']})")
            return False, f"{sym} 未能在訓練與測試期皆維持正報酬"

        # 4. 防止過度擬合: Test Net Profit < Train Net Profit * 20% 或 Test Win Rate < 30%
        if ts['profit'] < (tr['profit'] * 0.20):
            log_research(f"REJECTED: {sym} Overfitting (Test Profit {ts['profit']} < 20% of Train Profit {tr['profit']})")
            return False, f"{sym} 疑似過度擬合 (測試集利潤低於訓練集 20%)"

        if ts['win_rate'] < 0.30:
            log_research(f"REJECTED: {sym} Low Win Rate (Test WR {ts['win_rate']*100:.2f}% < 30%)")
            return False, f"{sym} 測試集勝率過低 (< 30%)"

    log_research("PASSED: Quality Gate Check.")
    return True, "Passed"

def ask_gemini_for_params(context, iteration_count, warning=""):
    model = genai.GenerativeModel('gemini-pro-latest')
    prompt = f"""
    You are an expert AI Crypto Quantitative Researcher.
    Current Market Context and Performance (Iteration {iteration_count}):
    {json.dumps(context, indent=2)}

    {warning}

    Task:
    Analyze the performance across BTC/USDT, ETH/USDT, and SOL/USDT.
    Suggest 3 sets of optimized parameters to improve Win Rate and reduce Max Drawdown.

    New Strategy Components:
    - ADX Filter: Use adx_min (20-30) to ensure trend strength.
    - Bollinger Bands: Use bb_std (1.5-2.5) for dynamic exit/volatility filter.
    - RSI Pullback: Standard RSI threshold (20-50).
    - EMA Trend: Fast (10-100) and Slow (100-300).

    Constraints:
    - RSI threshold: 20-50
    - SL multiplier: 2.5-5.0 ATR (MANDATORY: sl_mult must be >= 2.5)
    - ADX Min: 20-35
    - BB Std: 1.5-2.5\n    - Advanced Management: Scaling out 50% at BB Upper, Move to Breakeven, and EMA 20 Trailing Stop for remaining 50%.

    Return ONLY a JSON list of 3 objects with keys: rsi_th, ema_f, ema_s, sl_mult, macd_confirm, adx_min, bb_std, reason.
    """

    log_research(f"Sending prompt to Gemini (Iteration {iteration_count})...")
    response = model.generate_content(prompt)
    try:
        text = response.text
        if "```json" in text: text = text.split("```json")[1].split("```")[0]
        return json.loads(text)
    except Exception as e:
        log_research(f"Error parsing Gemini response: {e}")
        return None

def run_autonomous_research():
    log_research("Starting Autonomous Research Loop (Iteration 14) with ADX/BB...")
    iteration = 15
    warning = ""

    for attempt in range(3):
        log_research(f"Attempt {attempt + 1}/3")

        symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
        context = {}
        for sym in symbols:
            res = get_full_report(symbol=sym, macd_confirm=True)
            if res: context[sym] = res['report_str']

        suggestions = ask_gemini_for_params(context, iteration, warning)
        if not suggestions: continue

        for sug in suggestions:
            log_research(f"Testing Suggestion: {sug['reason']}")
            sym_results = {}
            for sym in symbols:
                res = get_full_report(
                    symbol=sym,
                    rsi_th=sug['rsi_th'],
                    ema_f=sug['ema_f'],
                    ema_s=sug['ema_s'],
                    sl_mult=sug['sl_mult'],
                    macd_confirm=sug['macd_confirm'],
                    adx_min=sug.get('adx_min', 25),
                    bb_std=sug.get('bb_std', 2)
                )
                if res: sym_results[sym] = res

            passed, reason = quality_gate(sym_results, sug)
            if passed:
                sug['version'] = f"Iteration {iteration}"
                with open('config/params.json', 'w') as f:
                    json.dump(sug, f, indent=2)

                path = 'STRATEGY_RELEASE_NOTES.md'
                date_str = datetime.now().strftime('%Y-%m-%d')
                new_entry = f"""
## Iteration {iteration} - ADX & Bollinger Bands (Self-Evolved)
- **Date**: {date_str}
- **Logic**: {sug['reason']}
- **Judge Status**: Passed Quality Gate (Anti-Overfit, SL >= 2.5, Trades > 20, ADX Filter)
- **Parameters**: RSI={sug['rsi_th']}, EMA_F={sug['ema_f']}, EMA_S={sug['ema_s']}, SL={sug['sl_mult']}, ADX_Min={sug.get('adx_min', 25)}, BB_Std={sug.get('bb_std', 2)}
- **Performance**:
"""
                for sym, res in sym_results.items():
                    new_entry += f"### {sym}\n{res['report_str']}\n"

                if os.path.exists(path):
                    with open(path, 'r', encoding='utf-8') as f: content = f.read()
                else: content = "# Strategy Release Notes\n"
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(content.replace("# Strategy Release Notes\n", "# Strategy Release Notes\n" + new_entry))

                log_research(f"Successfully deployed Iteration {iteration}")
                return

        warning = "警告：上一次生成的參數在 OOS 測試中表現極差（過度擬合或樣本不足），請放寬止損區間並尋找更具通用性的趨勢信號。"
        log_research("No suggestions passed Quality Gate. Retrying with warning...")

    log_research("Autonomous Research Loop failed after 3 attempts.")

if __name__ == "__main__":
    run_autonomous_research()
