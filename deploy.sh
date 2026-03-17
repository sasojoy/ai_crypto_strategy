#!/bin/bash

# Iteration 67 Deployment Script
echo "🚀 Starting Deployment (Iteration 67)..."

# 1. Force Sync with GitHub
echo "📥 Syncing with GitHub..."
git fetch --all
git reset --hard origin/main

# 2. Check and Install PM2 if missing
if ! command -v pm2 &> /dev/null; then
    echo "⚠️ PM2 not found. Attempting to install..."
    if command -v npm &> /dev/null; then
        npm install -g pm2
    else
        echo "❌ Error: npm is not installed. Please run fix_env.sh first."
        exit 1
    fi
fi

PM2_PATH="/usr/local/bin/pm2"
echo "✅ Using PM2 at: $PM2_PATH"

# 3. Install Python Dependencies
echo "🐍 Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt --no-cache-dir || echo "⚠️ Pip install had issues, continuing..."

# 4. Start Application with PM2
echo "🚀 Deploying market monitor with PM2..."
$PM2_PATH delete all || true
$PM2_PATH start ecosystem.config.js --name "Iteration67_Final"
$PM2_PATH save

echo "✅ PM2 Status Verification:"
$PM2_PATH list && echo "🚀 DEPLOYMENT COMPLETE" && exit 0
