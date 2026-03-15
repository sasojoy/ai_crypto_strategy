// Iteration 64.2 - Corrected Syntax for PM2.
module.exports = {
  apps : [{
    name: "Iteration64_Sniper",
    script: "src/market.py",
    env: {
      NODE_ENV: "production",
      PYTHONPATH: "."
    }
  }]
}
