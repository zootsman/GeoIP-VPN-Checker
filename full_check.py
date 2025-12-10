import requests
import subprocess
import re
import sys
import concurrent.futures
from json import JSONDecodeError

# --- CONFIGURATION ---

REQUEST_TIMEOUT = 15

GEOIP_SERVICES = [
    # --- Tier 1: High-Traffic Services (Google, Netflix, Cloudflare) ---
    {"name": "1. Google Services", "url": "http://ip-api.com/json/?fields=countryCode", "key_map": {'country_code': 'countryCode'}},
    {"name": "2. Netflix/Prime Video", "url": "https://ipinfo.io/json", "key_map": {'country_code': 'country'}},
    {"name": "3. OpenAI/Discord (Cloudflare)", "url": "https://www.cloudflare.com/cdn-cgi/trace", "key_map": None},
    
    # --- Tier 2: Common Platforms & CDNs (Microsoft, Apple, etc.) ---
    {"name": "4. Microsoft/Xbox/Spotify", "url": "https://api.ip.sb/geoip", "key_map": {'country_code': 'country_code'}},
    {"name": "5. Apple/Disney+", "url": "https://ifconfig.co/json", "key_map": {'country_code': 'country_iso'}},
    {"name": "6. Basic CDN Check", "url": "https://ifconfig.me/all.json", "key_map": {'country_code': 'country_code'}},

    # --- Tier 3: Security & Financial Services ---
    {"name": "7. High-Security/Banks", "url": "https://api.ipregistry.co/?key=tryout", "key_map": {'country_code': 'location.country.code'}},
    {"name": "8. Alternate Security Check", "url": "http://ipwho.is/", "key_map": {'country_code': 'country_code'}},

    # --- Tier 4: General Purpose & Public APIs ---
    {"name": "9. Extreme IP Lookup", "url": "https://extreme-ip-lookup.com/json/", "key_map": {'country_code': 'countryCode'}},
    {"name": "10. Country.is API", "url": "https://api.country.is/", "key_map": {'country_code': 'country'}},
    {"name": "11. Nekudo API", "url": "http://geoip.nekudo.com/api/", "key_map": {'country_code': 'country.code'}},
    {"name": "12. GeoJS API", "url": "https://get.geojs.io/v1/ip/country.json", "key_map": {'country_code': 'country'}},
    {"name": "13. BigDataCloud API", "url": "https://api.bigdatacloud.net/data/ip-geolocation", "key_map": {'country_code': 'country.code'}},
    {"name": "14. ReallyFreeGeoIP API", "url": "https://reallyfreegeoip.org/json/", "key_map": {'country_code': 'country_code'}},
    {"name": "15. Vuiz.net API", "url": "https://geoip.vuiz.net/api/", "key_map": {'country_code': 'country_code'}},

    # --- Tier 5: Regional/Less Common Services (may fail) ---
    {"name": "16. Regional Check (coo.su)", "url": "http://coo.su/api/ip.php?json=1", "key_map": {'country_code': 'country_code'}},
    {"name": "17. ipapi.co (may fail)", "url": "https://ipapi.co/json/", "key_map": {'country_code': 'country_code'}},
    {"name": "18. ipwhois.io (may fail)", "url": "https://ipwhois.io/json/", "key_map": {'country_code': 'country_code'}},
]

DNS_RESOLVERS = [
    {"name": "OpenDNS", "ip": "208.67.222.222"},
    {"name": "Google", "ip": "8.8.8.8"},
    {"name": "Cloudflare", "ip": "1.1.1.1"},
    {"name": "Quad9", "ip": "9.9.9.9"},
]


# --- HELPERS ---

def print_colored(text, color_code):
    """Выводит цветной текст в Termux."""
    print(f"\033[{color_code}m{text}\033[0m")

def get_country_from_data(data, key_map):
    """Извлекает код страны из данных, полученных от сервиса."""
    if not key_map:
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
        response.raise_for_status()
        data = response.json() if 'json' in response.headers.get('Content-Type', '').lower() else response.text
        code = get_country_from_data(data, key_map)
        return {"name": service["name"], "code": code or "N/A", "status": "OK"}
    except requests.exceptions.Timeout:
        return {"name": service["name"], "code": "Timeout", "status": "ERROR"}
    except (requests.exceptions.RequestException, JSONDecodeError):
        return {"name": service["name"], "code": "Error", "status": "ERROR"}

def run_single_dns_check(resolver):
    """Выполняет проверку DNS через один резолвер."""
    try:
        process = subprocess.run(
            ['dig', '+short', 'whoami.akamai.net', f'@{resolver["ip"]}'],
            capture_output=True, text=True, timeout=10, check=True
        )
        lines = process.stdout.strip().splitlines()
        if not lines or not re.match(r'^\d{1,3}(\.\d{1,3}){3}$', lines[0]):
            return {"name": resolver["name"], "ip": "N/A", "code": "Error", "status": "ERROR"}
        
        resolver_ip = lines[0]
        dns_geo_service = {"name": "DNS_Geo", "url": f'http://ip-api.com/json/{resolver_ip}?fields=countryCode', "key_map": {'country_code': 'countryCode'}}
        result = fetch_geoip_data(dns_geo_service)
        
        return {"name": resolver["name"], "ip": resolver_ip, "code": result["code"], "status": result["status"]}
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return {"name": resolver["name"], "ip": "N/A", "code": "Cmd Error", "status": "ERROR"}

def final_summary(main_code, geoip_results, dns_results):
    """Выводит итоговую проверку соответствия IP и DNS."""
    print_colored("\n--- ИТОГОВАЯ ПРОВЕРКА СООТВЕТСТВИЯ ---", "1;37")
    
    # 1. Проверка GeoIP
    successful_geoip = sum(1 for r in geoip_results if r["status"] == "OK")
    mismatched_geoip = sum(1 for r in geoip_results if r["status"] == "OK" and r["code"] != main_code)
    if mismatched_geoip == 0 and successful_geoip > 0:
        print_colored(f"✅ GEOIP ВЕРИФИКАЦИЯ: {successful_geoip} из {len(GEOIP_SERVICES)} баз видят страну {main_code}.", "42")
    else:
        print_colored(f"❌ GEOIP ПРОВАЛ: Обнаружены расхождения ({mismatched_geoip}) или ошибки. Успешных проверок: {successful_geoip}/{len(GEOIP_SERVICES)}.", "41")

    # 2. Проверка DNS
    successful_dns = sum(1 for r in dns_results if r["status"] == "OK")
    leaking_dns = [r for r in dns_results if r["status"] == "OK" and r["code"] != main_code]
    if not leaking_dns and successful_dns > 0:
        print_colored(f"✅ DNS ВЕРИФИКАЦИЯ: {successful_dns}/{len(DNS_RESOLVERS)} DNS-серверов находятся в стране {main_code}.", "42")
    else:
        for leak in leaking_dns:
            print_colored(f"❌ DNS LEAK ПРОВАЛ: GeoIP ({main_code}) не совпадает с DNS ({leak['name']} - {leak['code']})!", "41")
    
    # Общий вердикт
    if mismatched_geoip == 0 and not leaking_dns and successful_geoip > 0 and successful_dns > 0:
         print_colored("\n🚀 СИСТЕМА ПРОШЛА ВСЕ ПРОВЕРКИ. Доступ должен быть открыт.", "44")
    else:
         print_colored("\n⚠ VPN НЕ ПРОШЕЛ ПРОВЕРКУ! Рекомендуется смена сервера.", "43;30")

def main():
    try:
        subprocess.run(['dig'], capture_output=True, text=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print_colored("⚠ КОМАНДА 'dig' НЕ НАЙДЕНА ИЛИ НЕ РАБОТАЕТ. Установите 'dnsutils' (pkg install dnsutils).", "41")
        sys.exit(1)

    print_colored("--- Определение основного IP и страны ---", "1;37")
    main_ip_service = {"name": "Main IP", "url": 'http://ip-api.com/json/?fields=countryCode,query'}
    try:
        response = requests.get(main_ip_service["url"], timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        main_data = response.json()
        main_code, primary_ip = main_data.get('countryCode'), main_data.get('query')
        if not all([main_code, primary_ip]): raise ValueError("Неполные данные.")
    except (requests.exceptions.RequestException, ValueError, JSONDecodeError) as e:
        print_colored(f"Не удалось получить основной IP: {e}. Проверьте интернет.", "41")
        sys.exit(1)

    print_colored(f"=== IP АДРЕС: {primary_ip} | ЦЕЛЬ: {main_code} ===", "1;47;30")
    print("-" * 40)
    
    print(f"\n--- ЗАПУСК {len(GEOIP_SERVICES)} GEOIP ПРОВЕРОК ---")
    geoip_results = []
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_to_service = {executor.submit(fetch_geoip_data, service): service for service in GEOIP_SERVICES}
        for future in sorted(concurrent.futures.as_completed(future_to_service), key=lambda f: GEOIP_SERVICES.index(future_to_service[f])):
            result = future.result()
            geoip_results.append(result)
            print_colored(f"--- {result['name']} ---", "1;36")
            if result['status'] == 'OK':
                print(f"Код страны: {result['code']}")
                if result['code'] not in (main_code, "N/A"): print_colored(f"!!! РАСХОЖДЕНИЕ с основным IP ({main_code})", "31")
            else:
                print_colored(f"Ошибка: {result['code']}", "31")
            print("-" * 25)

    print(f"\n--- ЗАПУСК {len(DNS_RESOLVERS)} ПРОВЕРОК НА УТЕЧКУ DNS ---")
    dns_results = []
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_to_resolver = {executor.submit(run_single_dns_check, res): res for res in DNS_RESOLVERS}
        for future in sorted(concurrent.futures.as_completed(future_to_resolver), key=lambda f: DNS_RESOLVERS.index(future_to_resolver[f])):
            result = future.result()
            dns_results.append(result)
            print_colored(f"--- DNS: {result['name']} ({result.get('ip', 'N/A')}) ---", "1;35")
            if result['status'] == 'OK':
                print(f"Геолокация DNS: {result['code']}")
                if result['code'] != main_code: print_colored(f"!!! РАСХОЖДЕНИЕ с основным IP ({main_code})", "31")
            else:
                print_colored(f"Ошибка: {result['code']}", "31")
            print("-" * 25)

    final_summary(main_code, geoip_results, dns_results)

if __name__ == "__main__":
    main()
