import sys
import subprocess
import re
import threading
import time
import io
import locale
import shutil # Добавлен import shutil для проверки наличия команды dig

# --- ФУНКЦИЯ АВТОМАТИЧЕСКОЙ УСТАНОВКИ ЗАВИСИМОСТЕЙ ---
def install_dependencies():
    """Проверяет и устанавливает необходимые Python-пакеты (requests)."""
    try:
        import requests
        return requests
    except ImportError:
        print("\n\033[33m>>> УСТАНОВКА ЗАВИСИМОСТЕЙ...\033[0m")
        try:
            # Используем sys.executable для обеспечения запуска pip правильной версией Python
            subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
            print("\033[32m✅ requests успешно установлен.\033[0m\n")
            import requests
            return requests
        except subprocess.CalledProcessError:
            print("\033[41m!!! ОШИБКА: Не удалось установить библиотеку 'requests' через pip.\033[0m")
            print("Пожалуйста, установите ее вручную: pip install requests")
            sys.exit(1)

# Вызываем функцию перед основным кодом
requests = install_dependencies()
# --------------------------------------------------------------------


# --- ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ДЛЯ АНИМАЦИИ И ЛОКАЛИЗАЦИИ ---
animation_stop_event = threading.Event()
MIN_ANIMATION_TIME = 2.0
COLOR_CYCLE_CODES = ["32", "33", "36"] # Green, Yellow, Cyan
# Теперь 9 GeoIP-проверок
CHECK_COUNT = 9
# --------------------------------------------------------

# --- ЛОКАЛИЗАЦИЯ: ОПРЕДЕЛЕНИЕ ЯЗЫКА И СЛОВАРЬ ПЕРЕВОДОВ ---
SYSTEM_LANG = 'en'
try:
    lang_code, _ = locale.getdefaultlocale()
    if lang_code:
        SYSTEM_LANG = lang_code[:2].lower()
except Exception:
    pass

TRANSLATIONS = {
    'en': {
        "connecting": "Checking...",
        "country_code": "Country Code",
        "error_connection": "Connection or data retrieval error.",
        "final_check": "FINAL COMPLIANCE CHECK",
        "geoip_failure": "GEOIP FAILURE: Discrepancies or errors found.",
        "geoip_verification": "GEOIP VERIFICATION: %s out of %s databases see country %s.",
        "dns_leak_failure": "DNS LEAK FAILURE: GeoIP (%s) does not match DNS (%s)!",
        "system_passed": "SYSTEM PASSED ALL CHECKS. Access should be granted.",
        "vpn_failed": "VPN FAILED CHECK! Server change recommended.",
        "dns_leak_check": "CHECK 10: DNS LEAK",
        "ip_address": "IP ADDRESS",
        "target": "TARGET",
        "resolver_ip": "Resolver IP",
        "dns_geolocation": "DNS Geolocation",
        "failed_resolver": "Failed to get resolver IP.",
        "error_dns_geoip": "Error getting GeoIP for DNS resolver.",
        "dns_check_failed": "DNS check failed.",
        "dig_not_found": "⚠ 'dig' COMMAND NOT FOUND. Install: pkg install dnsutils",
        "could_not_get_ip": "Could not get main IP. Check internet connection.",
        "discrepancy": "!!! DISCREPANCY with main IP (%s)"
    },
    'ru': {
        "connecting": "Проверка...",
        "country_code": "Код страны",
        "error_connection": "Ошибка соединения или получения данных.",
        "final_check": "ФИНАЛЬНАЯ ПРОВЕРКА СООТВЕТСТВИЯ",
        "geoip_failure": "ПРОВАЛ GEOIP: Обнаружены расхождения или ошибки.",
        "geoip_verification": "ПРОВЕРКА GEOIP: %s из %s баз данных видят страну %s.",
        "dns_leak_failure": "ПРОВАЛ УТЕЧКИ DNS: GeoIP (%s) не совпадает с DNS (%s)!",
        "system_passed": "СИСТЕМА ПРОШЛА ВСЕ ПРОВЕРКИ. Доступ должен быть предоставлен.",
        "vpn_failed": "VPN НЕ ПРОШЕЛ ПРОВЕРКУ! Рекомендована смена сервера.",
        "dns_leak_check": "ПРОВЕРКА 10: УТЕЧКА DNS",
        "ip_address": "IP АДРЕС",
        "target": "ЦЕЛЬ",
        "resolver_ip": "IP Резолвера",
        "dns_geolocation": "Геолокация DNS",
        "failed_resolver": "Не удалось получить IP резолвера.",
        "error_dns_geoip": "Ошибка получения GeoIP для DNS резолвера.",
        "dns_check_failed": "Проверка DNS завершилась с ошибкой.",
        "dig_not_found": "⚠ КОМАНДА 'dig' НЕ НАЙДЕНА. Установите: pkg install dnsutils",
        "could_not_get_ip": "Не удалось получить основной IP. Проверьте подключение.",
        "discrepancy": "!!! РАСХОЖДЕНИЕ с основным IP (%s)"
    }
}

def _(text_id):
    """Возвращает перевод по ID текста."""
    lang_dict = TRANSLATIONS.get(SYSTEM_LANG, TRANSLATIONS['en'])
    return lang_dict.get(text_id, TRANSLATIONS['en'].get(text_id, f"MISSING_TRANSLATION:{text_id}"))
# --------------------------------------------------------------------

# Dictionary to store results
global_results = {}
primary_ip = ""
main_code = "N/A"

def print_colored(text, color_code):
    """Выводит цветной текст в Termux."""
    print(f"\033[{color_code}m{text}\033[0m")

def get_data(url, key_map=None):
    """Универсальная функция для запросов GeoIP."""
    try:
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

# --- ФУНКЦИЯ АНИМАЦИИ С ЦВЕТОВЫМ ЦИКЛОМ (Совместимая версия) ---
def spinner():
    """Анимация, имитирующая пульсацию/активность с изменением цвета."""
    
    # Надежная последовательность символов спиннера
    pulse_chars = ["|", "/", "-", "\\"] 
    
    while not animation_stop_event.is_set():
        # Циклическое изменение символа
        current_char = pulse_chars[int(time.time() * 4) % len(pulse_chars)] 
        
        # Циклическое изменение цвета
        color_index = int(time.time() * 8) % len(COLOR_CYCLE_CODES)
        color = COLOR_CYCLE_CODES[color_index]
        
        # Вывод строки с цветом
        sys.stdout.write(f"\r\033[{color}m🔌 [{_('connecting')}] {current_char}\033[0m")
        sys.stdout.flush()
        time.sleep(0.08)

    # Очищаем строку после завершения
    sys.stdout.write("\r" + " " * 30 + "\r")
    sys.stdout.flush()
# ------------------------------------------

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
    spinner_thread.join()
    
    # 5. Вывод результата
    if data and data.get('country_code'):
        code = data.get('country_code')
        global_results[name] = code
        print(f"{_('country_code')}: {code}")
        
        if main_code != "N/A" and code != main_code:
            print_colored(_('discrepancy') % main_code, "31")
    else:
        print_colored(_('error_connection'), "31")
    print("-" * 40)
    
def check_dns_leak():
    """Performs DNS Leak check using the dig command."""
    print_colored(f"--- {_('dns_leak_check')} ---", "1;37")
    
    # Проверка наличия команды 'dig'
    if not shutil.which('dig'):
        print_colored(_('dig_not_found'), "41")
        return "ERROR_MISSING_TOOL"
        
    try:
        process = subprocess.run(
            ['dig', '+short', 'whoami.akamai.net', '@resolver1.opendns.com'],
            capture_output=True,
            text=True,
            timeout=10
        )
        resolver_ip = process.stdout.splitlines()[0].strip()
        
        if not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', resolver_ip):
             print_colored(_('failed_resolver'), "31")
             return "ERROR"
             
        dns_geo_url = f'http://ip-api.com/json/{resolver_ip}?fields=countryCode'
        dns_geo_data = get_data(dns_geo_url, {'country_code': 'countryCode'})
        
        if dns_geo_data and dns_geo_data.get('country_code'):
            dns_code = dns_geo_data.get('country_code')
            print(f"{_('resolver_ip')}: {resolver_ip}")
            print(f"{_('dns_geolocation')}: {dns_code}")
            return dns_code
        
        print_colored(_('error_dns_geoip'), "31")
        return "ERROR"

    except Exception:
        print_colored(_('dns_check_failed'), "31")
        return "ERROR"

def check_compliance(dns_code):
    """Final check for IP and DNS consistency."""
    
    print_colored(f"\n--- {_('final_check')} ---", "1;37")
    
    # 1. GeoIP Consistency Check
    geoip_match = True
    successful_checks = 0
    for source, code in global_results.items():
        if code != main_code and code != "N/A" and code is not None:
            geoip_match = False
        if code != "N/A" and code is not None:
            successful_checks += 1
            
    if geoip_match and successful_checks > 0:
        print_colored(_('geoip_verification') % (successful_checks, CHECK_COUNT, main_code), "42")
    else:
        print_colored(_('geoip_failure'), "41")

    # 2. DNS Check
    if dns_code == "ERROR_MISSING_TOOL":
        # Пропускаем, так как уже выведено сообщение об ошибке
        pass
    elif dns_code != "ERROR" and dns_code != main_code:
        print_colored(_('dns_leak_failure') % (main_code, dns_code), "41")
    elif dns_code == main_code:
        print_colored(f"✅ DNS VERIFICATION: {_('dns_geolocation')} {_('country_code')}: {main_code}.", "42")
    
    # Условие прохождения
    if geoip_match and (dns_code == main_code or dns_code == "ERROR_MISSING_TOOL"):
         print_colored(f"\n🚀 {_('system_passed')}", "44")
    elif not geoip_match or (dns_code != main_code and dns_code != "ERROR" and dns_code != "ERROR_MISSING_TOOL"):
         print_colored(f"\n⚠ {_('vpn_failed')}", "43;30")

def main():
    global main_code, primary_ip
    
    ip_api_map = {'ip': 'query', 'country_code': 'countryCode'}
    ip_api_data = get_data('http://ip-api.com/json/?fields=countryCode,query', ip_api_map) 
    
    if not ip_api_data or not ip_api_data.get('country_code'):
        print_colored(_('could_not_get_ip'), "41")
        sys.exit(1)

    main_code = ip_api_data.get('country_code')
    primary_ip = ip_api_data.get('ip')
    global_results['Main'] = main_code
    
    print_colored(f"=== {_('ip_address')}: {primary_ip} | {_('target')}: {main_code} ===", "1;47;30")
    print("-" * 40)
    
    # --- 9 GeoIP Checks (ФИНАЛЬНЫЙ список) ---
    
    # 1
    check_geoip_and_register("1. Google/Facebook", 'http://ip-api.com/json/?fields=countryCode', {'country_code': 'countryCode'}, "1;36") 
    # 2
    check_geoip_and_register("2. Netflix/Twitch", 'https://ipinfo.io/json', {'country_code': 'country'}, "1;32") 
    # 3
    check_geoip_and_register("3. Cloudflare/OpenAI", 'https://www.cloudflare.com/cdn-cgi/trace', None, "1;33") 
    
    # 4 (Был 5)
    check_geoip_and_register("4. Banks/Security", 'https://api.ipregistry.co/?key=tryout', {'country_code': 'location.country.code'}, "1;34")
    
    # 5 (Был 8)
    check_geoip_and
