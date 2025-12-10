import requests
import subprocess
import re
import sys
import concurrent.futures
from json import JSONDecodeError

# --- CONFIGURATION ---

# Таймаут для каждого HTTP-запроса
REQUEST_TIMEOUT = 7

# Список сервисов для проверки GeoIP
GEOIP_SERVICES = [
    {"name": "1. Google/Facebook", "url": "http://ip-api.com/json/?fields=countryCode", "key_map": {'country_code': 'countryCode'}},
    {"name": "2. Netflix/Twitch", "url": "https://ipinfo.io/json", "key_map": {'country_code': 'country'}},
    {"name": "3. Cloudflare/OpenAI", "url": "https://www.cloudflare.com/cdn-cgi/trace", "key_map": None},
    {"name": "4. Microsoft/Spotify", "url": "https://api.ip.sb/geoip", "key_map": {'country_code': 'country_code'}},
    {"name": "5. Banks/Security", "url": "https://api.ipregistry.co/?key=tryout", "key_map": {'country_code': 'location.country.code'}},
    {"name": "6. Forums/Gaming", "url": "https://extreme-ip-lookup.com/json/", "key_map": {'country_code': 'countryCode'}},
    {"name": "7. Cloud/CDN Check", "url": "https://ipapi.co/json/", "key_map": {'country_code': 'country_code'}},
    {"name": "8. Regional/Local Check", "url": "http://coo.su/api/ip.php?json=1", "key_map": {'country_code': 'country_code'}},
    {"name": "9. Professional GeoIP", "url": "https://ipwhois.io/json/", "key_map": {'country_code': 'country_code'}},
    {"name": "10. General Platform", "url": "https://ifconfig.co/json", "key_map": {'country_code': 'country_iso'}},
    {"name": "11. Basic Check", "url": "https://ifconfig.me/all.json", "key_map": {'country_code': 'country_code'}},
]

# --- HELPERS ---

def print_colored(text, color_code):
    """Выводит цветной текст в Termux."""
    print(f"\033[{color_code}m{text}\033[0m")

def get_country_from_data(data, key_map):
    """Извлекает код страны из данных, полученных от сервиса."""
    if not key_map:  # Обработка Cloudflare
        if isinstance(data, str):
            cf_data = {line.split('=')[0]: line.split('=')[1] for line in data.splitlines() if '=' in line}
            return cf_data.get('loc')
        return None

    keys = key_map.get('country_code', '').split('.')
    value = data
    for key in keys:
        if isinstance(value, dict):
            value = value.get(key)
        else:
            return None
    return value


# --- CORE FUNCTIONS ---

def fetch_geoip_data(service):
    """Выполняет один GeoIP-запрос и возвращает результат."""
    url = service["url"]
    key_map = service["key_map"]
    
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()  # Проверка на HTTP ошибки (4xx, 5xx)

        if 'json' in response.headers.get('Content-Type', '').lower():
            data = response.json()
        else:
            data = response.text # Для Cloudflare

        country_code = get_country_from_data(data, key_map)
        return {"name": service["name"], "code": country_code or "N/A", "status": "OK"}
    except requests.exceptions.Timeout:
        return {"name": service["name"], "code": "Timeout", "status": "ERROR"}
    except (requests.exceptions.RequestException, JSONDecodeError) as e:
        return {"name": service["name"], "code": "Error", "status": "ERROR"}


def check_dns_leak():
    """Выполняет проверку DNS Leak и возвращает геолокацию DNS-сервера."""
    print_colored("--- ПРОВЕРКА 12: УТЕЧКА DNS ---", "1;37")
    try:
        process = subprocess.run(
            ['dig', '+short', 'whoami.akamai.net', '@resolver1.opendns.com'],
            capture_output=True, text=True, timeout=10, check=True
        )
        resolver_ip = process.stdout.strip().splitlines()[0]

        if not re.match(r'^\d{1,3}(\.\d{1,3}){3}$', resolver_ip):
            print_colored("Не удалось получить IP-адрес резолвера.", "31")
            return "ERROR"
            
        # Используем уже написанную функцию для получения GeoIP
        dns_geo_service = {"name": "DNS", "url": f'http://ip-api.com/json/{resolver_ip}?fields=countryCode', "key_map": {'country_code': 'countryCode'}}
        result = fetch_geoip_data(dns_geo_service)
        
        if result["status"] == "OK":
            dns_code = result["code"]
            print(f"IP резолвера: {resolver_ip}")
            print(f"Геолокация DNS: {dns_code}")
            return dns_code
        else:
            print_colored("Ошибка получения GeoIP для DNS резолвера.", "31")
            return "ERROR"

    except FileNotFoundError:
        print_colored("⚠ КОМАНДА 'dig' НЕ НАЙДЕНА. Установите 'dnsutils' (pkg install dnsutils).", "41")
        return "ERROR"
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        print_colored("Проверка DNS завершилась с ошибкой.", "31")
        return "ERROR"

def final_summary(main_code, geoip_results, dns_code):
    """Выводит итоговую проверку соответствия IP и DNS."""
    print_colored("\n--- ИТОГОВАЯ ПРОВЕРКА СООТВЕТСТВИЯ ---", "1;37")
    
    successful_checks = 0
    mismatched_checks = 0
    
    for result in geoip_results:
        if result["status"] == "OK":
            successful_checks += 1
            if result["code"] != main_code:
                mismatched_checks += 1

    # 1. Проверка GeoIP
    if mismatched_checks == 0 and successful_checks > 0:
        print_colored(f"✅ GEOIP ВЕРИФИКАЦИЯ: {successful_checks} из {len(GEOIP_SERVICES)} баз видят страну {main_code}.", "42")
    else:
        print_colored(f"❌ GEOIP ПРОВАЛ: Обнаружены расхождения или ошибки. Успешных проверок: {successful_checks}/{len(GEOIP_SERVICES)}.", "41")

    # 2. Проверка DNS
    if dns_code != "ERROR" and dns_code != main_code:
        print_colored(f"❌ DNS LEAK ПРОВАЛ: GeoIP ({main_code}) не совпадает с DNS ({dns_code})!", "41")
    elif dns_code == main_code:
        print_colored(f"✅ DNS ВЕРИФИКАЦИЯ: DNS-сервер находится в стране {main_code}.", "42")
    
    # Общий вердикт
    if mismatched_checks == 0 and dns_code == main_code and successful_checks > 0:
         print_colored("\n🚀 СИСТЕМА ПРОШЛА ВСЕ ПРОВЕРКИ. Доступ должен быть открыт.", "44")
    else:
         print_colored("\n⚠ VPN НЕ ПРОШЕЛ ПРОВЕРКУ! Рекомендуется смена сервера.", "43;30")


def main():
    # --- 0. Получение основного IP и кода ---
    print_colored("--- Определение основного IP и страны ---", "1;37")
    main_ip_service = {
        "name": "Main IP", 
        "url": 'http://ip-api.com/json/?fields=countryCode,query', 
        "key_map": {'ip': 'query', 'country_code': 'countryCode'}
    }
    
    try:
        response = requests.get(main_ip_service["url"], timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        main_data = response.json()
        main_code = main_data.get('countryCode')
        primary_ip = main_data.get('query')

        if not all([main_code, primary_ip]):
            raise ValueError("Неполные данные от основного сервиса.")

    except (requests.exceptions.RequestException, ValueError, JSONDecodeError) as e:
        print_colored(f"Не удалось получить основной IP: {e}. Проверьте интернет-соединение.", "41")
        sys.exit(1)

    print_colored(f"=== IP АДРЕС: {primary_ip} | ЦЕЛЬ: {main_code} ===", "1;47;30")
    print("-" * 40)
    
    # --- 1. Параллельный запуск GeoIP проверок ---
    geoip_results = []
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_to_service = {executor.submit(fetch_geoip_data, service): service for service in GEOIP_SERVICES}
        for future in concurrent.futures.as_completed(future_to_service):
            result = future.result()
            geoip_results.append(result)

            # Динамический вывод результатов по мере их поступления
            print_colored(f"--- GeoIP: {result['name']} ---", "1;36")
            if result['status'] == 'OK':
                code = result['code']
                print(f"Код страны: {code}")
                if code != main_code and code != "N/A":
                    print_colored(f"!!! РАСХОЖДЕНИЕ с основным IP ({main_code})", "31")
            else:
                print_colored(f"Ошибка: {result['code']}", "31")
            print("-" * 40)

    # --- 2. Запуск проверки DNS Leak ---
    dns_code = check_dns_leak()
    print("-" * 40)

    # --- 3. Финальный вывод ---
    final_summary(main_code, geoip_results, dns_code)

if __name__ == "__main__":
    main()