import requests
import subprocess
import re
import sys

# Словарь для хранения результатов и сравнения
global_results = {}
primary_ip = ""
main_code = "N/A"
CHECK_COUNT = 11

def print_colored(text, color_code):
    """Выводит цветной текст в Termux."""
    print(f"\033[{color_code}m{text}\033[0m")

def get_data(url, key_map=None):
    """Универсальная функция для GeoIP запросов."""
    try:
        response = requests.get(url, timeout=7)
        
        # Обработка JSON
        if 'json' in response.headers.get('Content-Type', '').lower():
            data = response.json()
            if key_map:
                # Универсальная обработка вложенных ключей
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
        
        # Обработка Cloudflare (не JSON)
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

def check_geoip_and_register(name, url, key_map, color):
    """Выполняет GeoIP проверку, регистрирует результат и выводит его."""
    data = get_data(url, key_map)
    
    print_colored(f"--- GeoIP: {name} ---", color)
    
    if data and data.get('country_code'):
        code = data.get('country_code')
        global_results[name] = code
        print(f"Код страны: {code}")
        
        # Сравнение с основной страной
        if main_code != "N/A" and code != main_code:
            print_colored(f"!!! РАСХОЖДЕНИЕ с основным IP ({main_code})", "31")
    else:
        print_colored("Ошибка соединения или получения данных.", "31")
    print("-" * 40)
    
def check_dns_leak():
    """Выполняет проверку DNS Leak через команду dig."""
    print_colored("--- ПРОВЕРКА 12: УТЕЧКА DNS ---", "1;37")
    
    try:
        process = subprocess.run(
            ['dig', '+short', 'whoami.akamai.net', '@resolver1.opendns.com'],
            capture_output=True,
            text=True,
            timeout=10
        )
        resolver_ip = process.stdout.splitlines()[0].strip()
        
        if not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', resolver_ip):
             print_colored("Не удалось получить IP-адрес резолвера.", "31")
             return "ERROR"
             
        dns_geo_url = f'http://ip-api.com/json/{resolver_ip}?fields=countryCode'
        dns_geo_data = get_data(dns_geo_url, {'country_code': 'countryCode'})
        
        if dns_geo_data and dns_geo_data.get('country_code'):
            dns_code = dns_geo_data.get('country_code')
            print(f"IP резолвера: {resolver_ip}")
            print(f"Геолокация DNS: {dns_code}")
            return dns_code
        
        print_colored("Ошибка получения GeoIP для DNS резолвера.", "31")
        return "ERROR"

    except FileNotFoundError:
        print_colored("⚠ КОМАНДА 'dig' НЕ НАЙДЕНА.", "41")
        return "ERROR"
    except Exception:
        print_colored("Проверка DNS завершилась с ошибкой.", "31")
        return "ERROR"

def check_compliance(dns_code):
    """Итоговая проверка соответствия IP и DNS."""
    
    print_colored("\n--- ИТОГОВАЯ ПРОВЕРКА СООТВЕТСТВИЯ ---", "1;37")
    
    # 1. Проверка соответствия всех GeoIP стран
    geoip_match = True
    successful_checks = 0
    for source, code in global_results.items():
        if code != main_code and code != "N/A" and code is not None:
            geoip_match = False
        if code != "N/A" and code is not None:
            successful_checks += 1
            
    if geoip_match and successful_checks > 0:
        print_colored(f"✅ GEOIP ВЕРИФИКАЦИЯ: {successful_checks} из {CHECK_COUNT} баз видят страну {main_code}.", "42")
    else:
        print_colored(f"❌ GEOIP ПРОВАЛ: Обнаружены расхождения или ошибки. Успешных проверок: {successful_checks}/{CHECK_COUNT}.", "41")

    # 2. Проверка DNS
    if dns_code != "ERROR" and dns_code != main_code:
        print_colored(f"❌ DNS LEAK ПРОВАЛ: GeoIP ({main_code}) не совпадает с DNS ({dns_code})!", "41")
    elif dns_code == main_code:
        print_colored(f"✅ DNS ВЕРИФИКАЦИЯ: DNS-сервер находится в стране {main_code}.", "42")
    
    if geoip_match and dns_code == main_code:
         print_colored("\n🚀 СИСТЕМА ПРОШЛА ВСЕ ПРОВЕРКИ. Доступ должен быть открыт.", "44")
    elif not geoip_match or dns_code != main_code:
         print_colored("\n⚠ VPN НЕ ПРОШЕЛ ПРОВЕРКУ! Рекомендуется смена сервера.", "43;30")

def main():
    global main_code, primary_ip
    
    # --- 0. Получение основного IP и кода ---
    ip_api_map = {'ip': 'query', 'country_code': 'countryCode'}
    ip_api_data = get_data('http://ip-api.com/json/?fields=countryCode,query', ip_api_map)
    
    if not ip_api_data or not ip_api_data.get('country_code'):
        print_colored("Не удалось получить основной IP. Проверьте интернет-соединение.", "41")
        sys.exit(1)

    main_code = ip_api_data.get('country_code')
    primary_ip = ip_api_data.get('ip')
    global_results['Основной'] = main_code
    
    print_colored(f"=== IP АДРЕС: {primary_ip} | ЦЕЛЬ: {main_code} ===", "1;47;30")
    print("-" * 40)
    
    # --- Запуск 11 GeoIP проверок ---
    
    # 1. Google, YouTube, Facebook, Xbox (База 1)
    check_geoip_and_register("1. Google/Facebook", 'http://ip-api.com/json/?fields=countryCode', {'country_code': 'countryCode'}, "1;36") 
    
    # 2. Netflix, Amazon, Twitch (База 2)
    check_geoip_and_register("2. Netflix/Twitch", 'https://ipinfo.io/json', {'country_code': 'country'}, "1;32") 
    
    # 3. OpenAI, ChatGPT, Discord (Инфраструктура)
    check_geoip_and_register("3. Cloudflare/OpenAI", 'https://www.cloudflare.com/cdn-cgi/trace', None, "1;33") 

    # 4. Microsoft, Spotify, Apple (База 3)
    check_geoip_and_register("4. Microsoft/Spotify", 'https://api.ip.sb/geoip', {'country_code': 'country_code'}, "1;35") 

    # 5. Банки / High Security (База 4)
    check_geoip_and_register("5. Banks/Security", 'https://api.ipregistry.co/?key=tryout', {'country_code': 'location.country.code'}, "1;34")

    # 6. Форумы / Средние сайты (База 5)
    check_geoip_and_register("6. Forums/Gaming", 'https://extreme-ip-lookup.com/json/', {'country_code': 'countryCode'}, "1;37")
    
    # 7. Облачные сервисы (База 6)
    check_geoip_and_register("7. Cloud/CDN Check", 'https://ipapi.co/json/', {'country_code': 'country_code'}, "1;31") 
    
    # 8. Региональные сервисы (База 7)
    check_geoip_and_register("8. Regional/Local Check", 'http://coo.su/api/ip.php?json=1', {'country_code': 'country_code'}, "1;33") 

    # --- НОВЫЕ ПРОВЕРКИ ---

    # 9. Проф. GeoIP (База 8)
    check_geoip_and_register("9. Professional GeoIP", 'https://ipwhois.io/json/', {'country_code': 'country_code'}, "1;37") 
    
    # 10. Общая платформа (База 9)
    check_geoip_and_register("10. General Platform", 'https://ifconfig.co/json', {'country_code': 'country_iso'}, "1;32") 
    
    # 11. Базовая проверка (База 10)
    check_geoip_and_register("11. Basic Check", 'https://ifconfig.me/all.json', {'country_code': 'country_code'}, "1;36") 

    # --- Запуск проверки DNS Leak ---
    dns_code = check_dns_leak()

    # --- Финальный вывод ---
    check_compliance(dns_code)

if __name__ == "__main__":
    main()
