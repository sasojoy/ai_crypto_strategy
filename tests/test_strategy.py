
import pytest
import os
import json
import pandas as pd
from datetime import datetime
from src.market import manage_positions, DATA_DIR

@pytest.fixture
def mock_order_state(tmp_path, mocker):
    # Setup a temporary data directory for testing
    test_data_dir = tmp_path / "trading_data"
    test_data_dir.mkdir()
    mocker.patch('src.market.DATA_DIR', str(test_data_dir))
    
    symbol = "ETH/USDT"
    state = {
        "symbol": "ETH/USDT",
        "status": "Open",
        "side": "LONG",
        "entry_price": 2000.0,
        "entry_time": datetime.utcnow().isoformat(),
        "pos_size": 1.0,
        "atr": 50.0,
        "sl_price": 1900.0, # 2.0 * ATR
        "tp_price": 2150.0, # 1.5 R/R
        "is_partial_closed": False,
        "sl_order_id": "sim-sl-123"
    }
    
    state_path = test_data_dir / f"order_state_{symbol.replace('/', '_')}.json"
    with open(state_path, 'w') as f:
        json.dump(state, f)
        
    return state, state_path

def test_partial_profit_taking_at_1_5_rr(mock_order_state, mocker):
    state, state_path = mock_order_state
    
    # Mock prices_rsi to simulate price reaching 1.5 R/R
    # ATR = 50.0
    # SL dist = 50.0 * 2.0 = 100.0
    # 1.5 R/R price = 2000 + (100.0 * 1.5) = 2150
    mock_prices = {
        "ETH/USDT": {
            "price": 2155.0,
            "adx": 25,
            "rsi": 50,
            "atr": 50.0
        }
    }
    
    # Mock fetch_15m_data to return some dummy data for EMA calculation
    mocker.patch('src.market.fetch_15m_data', return_value=pd.DataFrame({
        'close': [2100]*20,
        'high': [2110]*20,
        'low': [2090]*20,
        'volume': [1000]*20
    }))
    
    # Mock update_balance and send_telegram_msg
    mock_update_balance = mocker.patch('src.market.update_balance')
    mocker.patch('src.market.send_telegram_msg')
    
    # Run manage_positions
    manage_positions(mock_prices)
    
    # Load updated state
    with open(state_path, 'r') as f:
        updated_state = json.load(f)
    
    # ASSERTIONS (Expected to FAIL currently)
    # 1. Should have closed 50% of position
    assert updated_state['pos_size'] == 0.5, "Position size should be reduced by 50%"
    assert updated_state['is_partial_closed'] is True, "is_partial_closed flag should be True"
    
    # 2. SL should be moved to breakeven (Entry + small buffer for fees)
    # Entry is 2000.0. Breakeven should be >= 2000.0
    assert updated_state['sl_price'] >= 2000.0, f"SL price {updated_state['sl_price']} should be moved to breakeven (>= 2000.0)"
    
    # 3. update_balance should have been called for the 50% profit
    mock_update_balance.assert_called()
