module.exports = {
  apps : [{
    name: "H16_PREDATOR_V133_PRO",
    script: "./src/market.py",
    cwd: "/workspace/ai_crypto_strategy",
    env: {
      "PYTHONPATH": ".",
      "DRY_RUN": "True"
    },
    interpreter: "./venv/bin/python3",
    autorestart: true,
    watch: false,
    max_memory_restart: '1G'
  }]
}
