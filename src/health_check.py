
import os
import subprocess
import requests
from datetime import datetime

def check_git_status():
    """Task A: Check Git Remote vs Local sync status"""
    try:
        subprocess.run(["git", "fetch"], check=True, capture_output=True)
        status = subprocess.run(["git", "status", "-uno"], check=True, capture_output=True, text=True).stdout
        if "Your branch is up to date" in status:
            return "✅ Git: Synchronized"
        else:
            return "⚠️ Git: Out of sync or local changes pending"
    except Exception as e:
        return f"❌ Git Check Failed: {str(e)}"

def check_token_validity():
    """Task B: Verify GITHUB_TOKEN validity"""
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        return "❌ Token: GITHUB_TOKEN not found in environment"
    
    headers = {"Authorization": f"token {token}"}
    try:
        response = requests.get("https://api.github.com/user", headers=headers)
        if response.status_code == 200:
            return "✅ Token: Valid"
        elif response.status_code == 403:
            return "❌ Token: 403 Forbidden (Expired or insufficient scopes)"
        else:
            return f"⚠️ Token: Unexpected status {response.status_code}"
    except Exception as e:
        return f"❌ Token Check Failed: {str(e)}"

def check_pm2_restarts():
    """Task C: Check for frequent PM2 restarts"""
    try:
        # Check PM2 list for restart count
        result = subprocess.run(["pm2", "jlist"], capture_output=True, text=True)
        if result.returncode != 0:
            return "⚠️ PM2: Not found or not running"
        
        import json
        data = json.loads(result.stdout)
        report = []
        for proc in data:
            name = proc.get('name')
            restarts = proc.get('pm2_env', {}).get('restart_time', 0)
            status = proc.get('pm2_env', {}).get('status')
            if restarts > 10:
                report.append(f"⚠️ {name}: {restarts} restarts (High)")
            else:
                report.append(f"✅ {name}: {status} ({restarts} restarts)")
        return " | ".join(report) if report else "✅ PM2: Stable"
    except Exception as e:
        return f"❌ PM2 Check Failed: {str(e)}"

def run_full_health_check():
    results = [
        f"--- Health Check {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---",
        check_git_status(),
        check_token_validity(),
        check_pm2_restarts()
    ]
    return "\n".join(results)

if __name__ == "__main__":
    print(run_full_health_check())
