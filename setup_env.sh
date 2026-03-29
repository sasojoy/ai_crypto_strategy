
#!/bin/bash

echo "🛠️ [Iteration 81.0] Starting Environment Self-Healing..."

# 1. Create necessary directories
echo "📁 Creating directories..."
mkdir -p data logs models config trading_data
# Ensure data and logs exist in the current directory
mkdir -p data logs

# 2. Clean up Python cache
echo "🧹 Cleaning up __pycache__..."
rm -rf src/__pycache__
find . -type d -name "__pycache__" -exec rm -rf {} +

# 3. Install core libraries
echo "📦 Installing core libraries (Python 3.10 compatible)..."
pip install --upgrade pip
pip install -r requirements.txt

# 4. Verify installation
echo "✅ Environment Setup Complete!"
python --version
pip list | grep -E "pandas|numpy|scikit-learn|ccxt|pandas-ta"
