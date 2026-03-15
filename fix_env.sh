
#!/bin/bash

# Iteration 64.1 Environment Fix Script
echo "🛠️ Fixing GCE Environment..."

# 1. Update System
sudo apt-get update

# 2. Install Node.js and npm (if missing or broken)
echo "📦 Installing Node.js and npm..."
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# 3. Reinstall PM2 globally
echo "🚀 Reinstalling PM2..."
sudo npm install -g pm2

# 4. Verify Installations
echo "🔍 Verifying installations..."
node -v
npm -v
pm2 -v

echo "✅ Environment fix complete! Now you can run ./deploy.sh"

