import requests
import subprocess
import re
import sys
import threading
import time
import io # Добавлено для совместимости

# --- ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ДЛЯ АНИМАЦИИ И СЧЕТА ---
animation_stop_event = threading.Event()
MIN_ANIMATION_TIME = 2.0 # Минимальное время анимации в секундах
# ---------------------------------------------

# Dictionary to store results
global_results = {}
primary_ip = ""
main_code = "N/A"
CHECK_COUNT = 11

def print_colored(text, color_code):
    """Выводит цветной текст в Termux."""
    print(f"\033[{color_code}m{text}\033[0m")

def get_data(url, key_map=None):
    """Универсальная функция для запросов GeoIP."""
    try:
        # Уменьшаем таймаут, так как мы его компенсируем минимальным временем анимации
        response = requests.get(url, timeout=5) 
        
        if 'json' in response.headers.get('Content-Type', '').lower():
            data = response.json()
            if key_map:
                keys = key_map.get('country_code', '').split('.')
                value = data
                for key in keys:
                    if isinstance(value, dict):
                        value = value.get(key)
                    else:
                        value = None
                        break
                
                mapped_data = {'country_code': value}
                mapped_data['ip'] = data.get(key_map.get('ip'))
                return mapped_data

            return data
        
        if 'cloudflare' in url:
            cf_data = {}
            for line in response.text.splitlines():
                if '=' in line:
                    key, val = line.split('=', 1)
                    cf_data[key] = val
            return {'country_code': cf_data.get('loc', 'N/A')}
        return None
    except Exception:
        return None

# --- ФУНКЦИЯ АНИМАЦИИ ---
def spinner():
    """Анимация, имитирующая передачу данных."""
    chars = ["|", "/", "-", "\\"]
    
    # Символ начала "провода"
    sys.stdout.write("🔌 [Checking...]")
    
    while not animation_stop_event.is_set():
        # Перемещаемся в начало строки для обновления спиннера
        sys.stdout.write(f"\r🔌 [Checking...] {chars[int(time.time() * 4) % len(chars)]}")
        sys.stdout.flush()
        time.sleep(0.1)

    # Очищаем строку после завершения, чтобы не мешать выводу результата
    sys.stdout.write("\r" + " " * 30 + "\r")
    sys.stdout.flush()
# -------------------------

def check_geoip_and_register(name, url, key_map, color):
    """
    Выполняет проверку GeoIP с принудительной минимальной анимацией 2.0 секунды.
    """
    global animation_stop_event
    
    print_colored(f"--- GeoIP: {name} ---", color)
    
    # 1. Запись времени начала и запуск анимации
    start_time = time.time()
    animation_stop_event.clear()
    spinner_thread = threading.Thread(target=spinner)
    spinner_thread.start()
    
    # 2. Блокирующий запрос GeoIP
    data = get_data(url, key_map)
    
    # 3. Принудительная задержка (если запрос пришел быстро)
    elapsed_time = time.time() - start_time
    
    if elapsed_time < MIN_ANIMATION_TIME:
        time_to_sleep = MIN_ANIMATION_TIME - elapsed_time
        time.sleep(time_to_sleep)
        
    # 4. Остановка потока анимации
    animation_stop_event.set()
    spinner_thread.join() # Ждем завершения потока анимации
    
    # 5. Вывод результата
    if data and data.get('country_code'):
        code = data.get('country_code')
        global_results[name] = code
        print(f"Country Code: {code}")
        
        if main_code != "N/A" and code != main_code:
            print_colored(f"!!! DISCREPANCY with main IP ({main_code})", "31")
    else:
        print_colored("Connection or data retrieval error.", "31")
    print("-" * 40)
    
def check_dns_leak():
    """Performs DNS Leak check using the dig command."""
    print_colored("--- CHECK 12: DNS LEAK ---", "1;37")
    
    try:
        process = subprocess.run(
            ['dig', '+short', 'whoami.akamai.net', '@resolver1.opendns.com'],
            capture_output=True,
            text=True,
            timeout=10
        )
        resolver_ip = process.stdout.splitlines()[0].strip()
        
        if not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', resolver_ip):
             print_colored("Failed to get resolver IP.", "31")
             return "ERROR"
             
        dns_geo_url = f'http://ip-api.com/json/{resolver_ip}?fields=countryCode'
        dns_geo_data = get_data(dns_geo_url, {'country_code': 'countryCode'})
        
        if dns_geo_data and dns_geo_data.get('country_code'):
            dns_code = dns_geo_data.get('country_code')
            print(f"Resolver IP: {resolver_ip}")
            print(f"DNS Geolocation: {dns_code}")
            return dns_code
        
        print_colored("Error getting GeoIP for DNS resolver.", "31")
        return "ERROR"

    except FileNotFoundError:
        print_colored("⚠ 'dig' COMMAND NOT FOUND. Install: pkg install dnsutils", "41")
        return "ERROR"
    except Exception:
        print_colored("DNS check failed.", "31")
        return "ERROR"

def check_compliance(dns_code):
    """Final check for IP and DNS consistency."""
    
    print_colored("\n--- FINAL COMPLIANCE CHECK ---", "1;37")
    
    # 1. GeoIP Consistency Check
    geoip_match = True
    successful_checks = 0
    for source, code in global_results.items():
        if code != main_code and code != "N/A" and code is not None:
            geoip_match = False
        if code != "N/A" and code is not None:
            successful_checks += 1
            
    if geoip_match and successful_checks > 0:
        print_colored(f"✅ GEOIP VERIFICATION: {successful_checks} out of {CHECK_COUNT} databases see country {main_code}.", "42")
    else:
        print_colored(f"❌ GEOIP FAILURE: Discrepancies or errors found. Successful checks: {successful_checks}/{CHECK_COUNT}.", "41")

    # 2. DNS Check
    if dns_code != "ERROR" and dns_code != main_code:
        print_colored(f"❌ DNS LEAK FAILURE: GeoIP ({main_code}) does not match DNS ({dns_code})!", "41")
    elif dns_code == main_code:
        print_colored(f"✅ DNS VERIFICATION: DNS server is located in country {main_code}.", "42")
    
    if geoip_match and dns_code == main_code:
         print_colored("\n🚀 SYSTEM PASSED ALL CHECKS. Access should be granted.", "44")
    elif not geoip_match or dns_code != main_code:
         print_colored("\n⚠ VPN FAILED CHECK! Server change recommended.", "43;30")

def main():
    global main_code, primary_ip
    
    ip_api_map = {'ip': 'query', 'country_code': 'countryCode'}
    # Используем get_data для первой проверки без анимации
    ip_api_data = get_data('http://ip-api.com/json/?fields=countryCode,query', ip_api_map) 
    
    if not ip_api_data or not ip_api_data.get('country_code'):
        print_colored("Could not get main IP. Check internet connection.", "41")
        sys.exit(1)

    main_code = ip_api_data.get('country_code')
    primary_ip = ip_api_data.get('ip')
    global_results['Main'] = main_code
    
    print_colored(f"=== IP ADDRESS: {primary_ip} | TARGET: {main_code} ===", "1;47;30")
    print("-" * 40)
    
    # --- 11 GeoIP Checks (с анимацией) ---
    
    check_geoip_and_register("1. Google/Facebook", 'http://ip-api.com/json/?fields=countryCode', {'country_code': 'countryCode'}, "1;36") 
    check_geoip_and_register("2. Netflix/Twitch", 'https://ipinfo.io/json', {'country_code': 'country'}, "1;32") 
    check_geoip_and_register("3. Cloudflare/OpenAI", 'https://www.cloudflare.com/cdn-cgi/trace', None, "1;33") 
    check_geoip_and_register("4. Microsoft/Spotify", 'https://api.ip.sb/geoip', {'country_code': 'country_code'}, "1;35") 
    check_geoip_and_register("5. Banks/Security", 'https://api.ipregistry.co/?key=tryout', {'country_code': 'location.country.code'}, "1;34")
    check_geoip_and_register("6. Forums/Gaming", 'https://extreme-ip-lookup.com/json/', {'country_code': 'countryCode'}, "1;37")
    check_geoip_and_register("7. Cloud/CDN Check", 'https://ipapi.co/json/', {'country_code': 'country_code'}, "1;31") 
    check_geoip_and_register("8. Regional/Local Check", 'http://coo.su/api/ip.php?json=1', {'country_code': 'country_code'}, "1;33") 
    check_geoip_and_register("9. Professional GeoIP", 'https://ipwhois.io/json/', {'country_code': 'country_code'}, "1;37") 
    check_geoip_and_register("10. General Platform", 'https://ifconfig.co/json', {'country_code': 'country_iso'}, "1;32") 
    check_geoip_and_register("11. Basic Check", 'https://ifconfig.me/all.json', {'country_code': 'country_code'}, "1;36") 

    # --- DNS Leak Check (без анимации, т.к. использует dig) ---
    dns_code = check_dns_leak()

    # --- Final Output ---
    check_compliance(dns_code)

if __name__ == "__main__":
    main()

