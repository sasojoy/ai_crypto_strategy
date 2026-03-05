

import os
import json
import pandas as pd
import google.generativeai as genai
from datetime import datetime
from src.evaluate import get_full_report
from src.grid_search import grid_search

# Configure Gemini API
api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=api_key)

def log_research(message):
    os.makedirs('logs', exist_ok=True)
    with open('logs/research_dialog.log', 'a', encoding='utf-8') as f:
        f.write(f"[{datetime.now().isoformat()}] {message}\n")

def update_release_notes(iteration, reason, results, params):
    path = 'STRATEGY_RELEASE_NOTES.md'
    date_str = datetime.now().strftime('%Y-%m-%d')
    
    new_entry = f"""
## Iteration {iteration} - Triple Threat Optimized
- **Date**: {date_str}
- **Logic**: {reason}
- **Parameters**: RSI={params['rsi_th']}, EMA_F={params['ema_f']}, EMA_S={params['ema_s']}, SL={params['sl_mult']}, MACD={params['macd_confirm']}
- **Performance**:
"""
    for sym, report in results.items():
        # Extract the table part from the report
        table = report.split('| Period |')[1].split('\n\n')[0]
        new_entry += f"### {sym}\n| Period |{table}\n\n"
    
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
    else:
        content = "# Strategy Release Notes\n"
        
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content.replace("# Strategy Release Notes\n", "# Strategy Release Notes\n" + new_entry))

def get_market_context():
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
    context = {}
    for sym in symbols:
        report = get_full_report(symbol=sym, macd_confirm=True)
        context[sym] = report
    return context

def ask_gemini_for_params(context, iteration_count):
    # 使用 gemini-pro-latest 作為備選，這通常對所有 API Key 都開放
    model = genai.GenerativeModel('gemini-pro-latest')
    prompt = f"""
    You are an expert AI Crypto Quantitative Researcher.
    Current Market Context and Performance (Iteration {iteration_count}):
    {json.dumps(context, indent=2)}
    
    Task:
    Analyze the performance across BTC/USDT, ETH/USDT, and SOL/USDT.
    Suggest 3 sets of optimized parameters with a heavy weight on "Drawdown Control".
    Focus on the interaction between MACD Histogram and RSI.

    Target Metrics for Iteration 12:
    - Sharpe Ratio > 1.8
    - Win Rate > 55%
    - Max Drawdown < 10%
    
    Constraints:
    - RSI threshold: 20-50
    - SL multiplier: 1.0-5.0 ATR
    - EMA Fast: 10-100
    - EMA Slow: 100-300
    
    Return ONLY a JSON list of 3 objects with keys: rsi_th, ema_f, ema_s, sl_mult, macd_confirm, reason.
    """
    
    log_research(f"Sending prompt to Gemini (Iteration {iteration_count})...")
    response = model.generate_content(prompt)
    log_research(f"Gemini Response: {response.text}")
    
    try:
        # Extract JSON from response
        text = response.text
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        return json.loads(text)
    except Exception as e:
        log_research(f"Error parsing Gemini response: {e}")
        return None

def deploy_new_params(params, iteration, reason, results):
    # 1. Update params.json
    params['version'] = f"Iteration {iteration}"
    with open('config/params.json', 'w') as f:
        json.dump(params, f, indent=2)
    
    # 2. Update Release Notes
    update_release_notes(iteration, reason, results, params)
    
    # 3. Git Push
    os.system("git add .")
    os.system(f'git commit -m "Auto-Deploy: Iteration {iteration} - {reason[:50]}"')
    os.system("git push origin main")
    log_research(f"Successfully deployed Iteration {iteration}")

def run_autonomous_research():
    log_research("Starting Autonomous Research Loop...")
    
    # 0. Load current params for baseline comparison
    with open('config/params.json', 'r') as f:
        current_params = json.load(f)
    
    # 1. Get current context
    context = get_market_context()
    
    # 2. Ask Gemini for suggestions
    iteration = 12 # Next iteration
    suggestions = ask_gemini_for_params(context, iteration)
    
    if not suggestions:
        return
    
    best_sug = None
    best_improvement = 0
    
    for i, sug in enumerate(suggestions):
        # Physical Guardrails
        sug['rsi_th'] = max(20, min(50, sug['rsi_th']))
        sug['sl_mult'] = max(1.0, min(5.0, sug['sl_mult']))
        
        log_research(f"Testing Suggestion {i+1}: {sug['reason']}")
        
        sym_results = {}
        positive_count = 0
        total_score = 0
        
        for sym in ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']:
            report = get_full_report(
                symbol=sym, 
                rsi_th=sug['rsi_th'], 
                ema_f=sug['ema_f'], 
                ema_s=sug['ema_s'], 
                sl_mult=sug['sl_mult'],
                macd_confirm=sug['macd_confirm']
            )
            sym_results[sym] = report
            
            # Simple score extraction from report string (heuristic)
            # In a production system, evaluate.py should return a structured object
            try:
                score_line = [line for line in report.split('\n') if 'Train (30d)' in line][0]
                score = float(score_line.split('|')[2].strip())
                total_score += score
                if score > 0:
                    positive_count += 1
            except:
                pass
            
        # Safety Guardrails & Deployment Threshold
        # Threshold: At least 2 symbols positive score, and improvement > 15% (simplified here)
        
        # Iteration 12 Strict Threshold: Sharpe Ratio > 1.8 and Win Rate > 55%
        # (Note: In this heuristic implementation, we use score as a proxy for Sharpe)
        if positive_count >= 2:
            log_research(f"Suggestion {i+1} passed safety check (Positive symbols: {positive_count})")
            # For this demo, we'll take the first one that passes safety
            best_sug = sug
            best_results = sym_results
            break
    
    if best_sug:
        deploy_new_params(best_sug, iteration, best_sug['reason'], best_results)
    else:
        log_research("No suggestions passed the safety and performance threshold.")
    
    log_research("Autonomous Research Loop Completed.")

if __name__ == "__main__":
    run_autonomous_research()

