
#!/bin/bash

echo "🛠️ [Iteration 75.0] Starting Environment Self-Healing..."

# 1. Create necessary directories
echo "📁 Creating directories..."
mkdir -p data logs models config trading_data

# 2. Clean up Python cache
echo "🧹 Cleaning up __pycache__..."
find . -type d -name "__pycache__" -exec rm -rf {} +

# 3. Install core libraries
echo "📦 Installing core libraries (Python 3.10 compatible)..."
pip install --upgrade pip
pip install pandas numpy ccxt joblib python-dotenv
pip install scikit-learn==1.7.2

# 4. Verify installation
echo "✅ Environment Setup Complete!"
python --version
pip list | grep -E "pandas|numpy|scikit-learn|ccxt"
