# 🗺️ GeoIP & DNS Leak Comprehensive VPN Checker (Termux Ready)

This Python script performs **11 independent GeoIP checks** and **1 critical DNS Leak test** to verify the true location and stability of your VPN connection. This tool helps diagnose why services like ChatGPT, Gemini, or streaming platforms might be blocking access despite the VPN being active.

## 🚀 Quick Start (Termux/Android)

Follow these steps directly in your **Termux** environment to install dependencies and run the script.

### 1. Prerequisites & Setup

Ensure you have Termux installed (preferably from F-Droid) and set up Git.

| Command | Purpose |
| :--- | :--- |
| `pkg update -y && pkg upgrade -y` | Updates Termux packages. |
| `pkg install python nano dnsutils -y` | Installs Python, `nano` (editor), and `dnsutils` (`dig`). |
| `pip install requests` | Installs the necessary Python library for API calls. |

   curl -s https://raw.githubusercontent.com/zootsman/GeoIP-VPN-Checker/beta/full_check.py | python
