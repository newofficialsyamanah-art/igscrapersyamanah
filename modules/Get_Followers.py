import json
import os
import random
import time
import requests
from fake_useragent import UserAgent
import pyfiglet
from colorama import init, Fore
import pickle
import sys

init()

class Colors:
    RED = Fore.RED
    GREEN = Fore.LIGHTGREEN_EX
    YELLOW = Fore.YELLOW
    CYAN = Fore.CYAN
    WHITE = Fore.WHITE
    RESET = Fore.RESET

class UI:
    PLUS = f"{Colors.GREEN}[+]{Colors.RESET}"
    WARNING = f"{Colors.YELLOW}[!]{Colors.RESET}"
    ERROR = f"{Colors.RED}[!]{Colors.RESET}"
    INFO = f"{Colors.CYAN}[i]{Colors.RESET}"

colors = [Colors.GREEN, Colors.RED, Colors.WHITE, Colors.CYAN, Colors.YELLOW]

def clear_screen():
    """Cross-platform screen clearing"""
    os.system('cls' if os.name == 'nt' else 'clear')

def show_banner():
    """Display the application banner"""
    f = pyfiglet.Figlet(font='slant')
    banner = f.renderText('Followers')
    print(f'{Colors.YELLOW}{banner}{Colors.RESET}')
    print(f'{Colors.RED}Followers Scraper | Version: 1.0 | Author: Kev {Colors.RESET}\n')

def load_accounts(filename='session_file.txt'):
    """Load accounts from file with enhanced error handling"""
    accounts = []
    try:
        with open(filename, 'rb') as f:
            while True:
                try:
                    account_data = pickle.load(f)
                    if len(account_data) >= 1:  # Ensure we have username and session id
                        accounts.append(account_data)
                    else:
                        print(f"{UI.WARNING} Invalid account data format: {account_data}")
                except EOFError:
                    break
                except Exception as e:
                    print(f"{UI.ERROR} Error loading account: {e}")
                    continue
    except FileNotFoundError:
        print(f"{UI.ERROR}{Colors.RED} Account file not found: {filename}{Colors.RESET}")
    except Exception as e:
        print(f"{UI.ERROR}{Colors.RED} Failed to load accounts: {e}{Colors.RESET}")
    
    if not accounts:
        print(f"{UI.ERROR}{Colors.RED} No valid accounts loaded!{Colors.RESET}")
        sys.exit(1)
        
    return accounts

def select_account(accounts):
    """Prompt user to select an account"""
    if not accounts:
        print(f"{Colors.RED}No accounts found in session_file.txt{Colors.RESET}")
        sys.exit(1)
        
    print(f"\n{Colors.CYAN}Available accounts:{Colors.RESET}")
    for i, acc in enumerate(accounts):
        # Safely access account information - assuming each account is a tuple/list
        try:
            username = acc[2]  # Try to get username from index 2
            print(f"  {Colors.GREEN}[{i}] {username}{Colors.RESET}")
        except IndexError:
            # If index 2 doesn't exist, try to get first element
            username = acc[0] if len(acc) > 0 else "Unknown"
            print(f"  {Colors.GREEN}[{i}] {username}{Colors.RESET}")
    
    while True:
        try:
            choice = int(input(f"\n{Colors.GREEN}Select account (0-{len(accounts)-1}): {Colors.RESET}"))
            if 0 <= choice < len(accounts):
                return accounts[choice]
            print(f"{Colors.RED}Invalid selection.{Colors.RESET}")
        except ValueError:
            print(f"{Colors.RED}Please enter a number.{Colors.RESET}")

def main_menu():
    """Display main menu and get user choice"""
    print(f"{Colors.YELLOW}Choose an option:{Colors.RESET}")
    print(f"  {Colors.GREEN}[1] Scrape new account{Colors.RESET}")
    print(f"  {Colors.GREEN}[2] Resume download{Colors.RESET}")
    
    while True:
        try:
            choice = int(input(f"\n{Colors.GREEN}Enter your choice (1-2): {Colors.RESET}"))
            if choice in [1, 2]:
                return choice
            print(f"{Colors.RED}Invalid choice. Please enter 1 or 2.{Colors.RESET}")
        except ValueError:
            print(f"{Colors.RED}Please enter a number.{Colors.RESET}")

def get_temp_folders():
    """Get all folders in FOLLOWERS_DATA that have temp files"""
    followers_base = 'FOLLOWERS_DATA'
    if not os.path.exists(followers_base):
        return []
    
    temp_folders = []
    for folder in os.listdir(followers_base):
        folder_path = os.path.join(followers_base, folder)
        temp_file = os.path.join(folder_path, 'temp.json')
        if os.path.isdir(folder_path) and os.path.exists(temp_file):
            try:
                with open(temp_file, 'r') as f:
                    temp_data = json.load(f)
                temp_folders.append({
                    'username': folder,
                    'temp_data': temp_data
                })
            except Exception as e:
                print(f"{UI.WARNING} Error reading temp file for {folder}: {e}")
                continue
    
    return temp_folders

def select_resume_folder(temp_folders):
    """Let user select which folder to resume downloading"""
    if not temp_folders:
        print(f"{Colors.RED}No folders with temp files found!{Colors.RESET}")
        return None
    
    print(f"\n{Colors.CYAN}Available downloads to resume:{Colors.RESET}")
    for i, folder_info in enumerate(temp_folders):
        temp_data = folder_info['temp_data']
        print(f"  {Colors.GREEN}[{i}] {folder_info['username']}{Colors.RESET}")
        print(f"      Previous download: {temp_data['downloaded']}")
        print(f"      Scrape limit: {temp_data['scrape_limit']}")
    
    while True:
        try:
            choice = int(input(f"\n{Colors.GREEN}Select folder (0-{len(temp_folders)-1}): {Colors.RESET}"))
            if 0 <= choice < len(temp_folders):
                selected = temp_folders[choice]
                
                change_limit = input(f"{Colors.YELLOW}Change scrape limit? (y/n): {Colors.RESET}").lower()
                if change_limit == 'y':
                    while True:
                        try:
                            new_limit = int(input(f"{Colors.GREEN}Enter new scrape limit: {Colors.RESET}"))
                            selected['temp_data']['scrape_limit'] = new_limit
                            break
                        except ValueError:
                            print(f"{Colors.RED}Please enter a valid number.{Colors.RESET}")
                
                return selected
            print(f"{Colors.RED}Invalid selection.{Colors.RESET}")
        except ValueError:
            print(f"{Colors.RED}Please enter a number.{Colors.RESET}")

def save_temp_file(username, max_id, downloaded, scrape_limit):
    """Save temporary file for resume functionality"""
    temp_data = {
        'max_id': max_id,
        'downloaded': downloaded,
        'scrape_limit': scrape_limit
    }
    
    followers_dir = os.path.join('FOLLOWERS_DATA', username)
    os.makedirs(followers_dir,exist_ok=True)
    temp_file = os.path.join(followers_dir, 'temp.json')
    
    try:
        with open(temp_file, 'w') as f:
            json.dump(temp_data, f)
    except Exception as e:
        print(f"{UI.ERROR} Error saving temp file: {e}")

def remove_temp_file(username):
    """Remove temp file after successful completion"""
    followers_dir = os.path.join('FOLLOWERS_DATA', username)
    temp_file = os.path.join(followers_dir, 'temp.json')
    
    try:
        if os.path.exists(temp_file):
            os.remove(temp_file)
            print(f"{UI.PLUS} Temp file removed successfully")
    except Exception as e:
        print(f"{UI.WARNING} Could not remove temp file: {e}")

def load_existing_data(data_json_file):
    """Load existing JSON data if file exists"""
    existing_data = []
    if os.path.exists(data_json_file):
        try:
            with open(data_json_file, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
            print(f"{UI.INFO} Loaded {len(existing_data)} existing records")
        except Exception as e:
            print(f"{UI.WARNING} Error loading existing data: {e}")
    
    return existing_data

def get_userid(to_scrape_username, session_id=None, http_session=None, log_callback=None, **kwargs):
    """Get user ID and follower count from Instagram using topsearch and profile fallbacks."""
    print(f'\n{Colors.GREEN}Getting userid for @{to_scrape_username}...{Colors.RESET}\n')
    headers = {
        "authority": "www.instagram.com",
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "referer": f"https://www.instagram.com/{to_scrape_username}/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        'x-ig-app-id': '936619743392459', 
        "x-requested-with": "XMLHttpRequest"
    }
    cookies = {"sessionid": session_id} if session_id else {}

    # Method 1: Web search API (reliable and does not trigger 429)
    search_urls = [
        f"https://www.instagram.com/api/v1/web/search/topsearch/?context=blended&query={to_scrape_username}",
        f"https://www.instagram.com/web/search/topsearch/?query={to_scrape_username}"
    ]
    for url in search_urls:
        try:
            resp = requests.get(url, headers=headers, cookies=cookies or None, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get('users', []):
                    u = item.get('user', {})
                    if u.get('username', '').lower() == to_scrape_username.lower():
                        return str(u.get('pk')), None
        except Exception:
            continue

    # Method 2: Googlebot pre-rendered profile page fallback (immune to 429)
    try:
        gb_headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
            'Accept-Language': 'en-US,en;q=0.9'
        }
        r = requests.get(f'https://www.instagram.com/{to_scrape_username}/', headers=gb_headers, timeout=8)
        if r.status_code == 200:
            import re
            m = re.search(r'\"xig_user_by_igid_v2\":(\{.*?\})\s*,\s*\"xig_logged_out', r.text)
            if m:
                u_data = json.loads(m.group(1))
                return str(u_data.get('pk')), u_data.get('follower_count')
    except Exception:
        pass

    # Method 3: web_profile_info fallback
    url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={to_scrape_username}"
    try:
        response = requests.get(url, headers=headers, cookies=cookies or None, timeout=15)
        if response.status_code == 200:
            payload = response.json()
            user_data = payload.get('data', {}).get('user', {})
            return str(user_data.get('id')), user_data.get('edge_followed_by', {}).get('count')
    except Exception as e:
        print(f"{UI.WARNING} Error loading user info: {e}")

    return None, None

def req(params, user_id, username, session_id, max_retries=3, http_session=None, log_callback=None):
    """Make request to Instagram API with retries and backoff"""
    cookies = {'sessionid': session_id}
    headers = {
        'accept': '*/*',
        'accept-language': 'en-US,en;q=0.8',
        'cache-control': 'no-cache',
        'pragma': 'no-cache',
        'priority': 'u=1, i',
        'referer': f'https://www.instagram.com/{username}/followers/',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-model': '""',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'sec-gpc': '1',
        'user-agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        'x-ig-app-id': '936619743392459',
        'x-requested-with': 'XMLHttpRequest',
    }
    url = f'https://www.instagram.com/api/v1/friendships/{user_id}/followers/'
    client = http_session if http_session is not None else requests

    for attempt in range(1, max_retries + 1):
        try:
            response = client.get(url, headers=headers, cookies=cookies, params=params, timeout=12)
            if response.status_code == 200:
                return response
            elif response.status_code == 429:
                wait_time = attempt * 4
                msg = f"Rate limited (429). Menunggu {wait_time}s... (Percobaan {attempt}/{max_retries})"
                print(f"\n{UI.WARNING} {msg}")
                if log_callback:
                    log_callback(f"[!] {msg}")
                time.sleep(wait_time)
            else:
                msg = f"Request Instagram status {response.status_code}"
                print(f"\n{UI.ERROR} {msg}")
                if log_callback:
                    log_callback(f"[!] {msg}")
                time.sleep(1.5)
        except Exception as e:
            msg = f"Network timeout/error: {str(e)[:60]}. Mencoba ulang..."
            print(f"\n{UI.WARNING} {msg}")
            if log_callback:
                log_callback(f"[!] {msg}")
            time.sleep(2)

    return None

def get_data(user_id, followers, username, session_id, scrape_amount, resume_data=None):
    """Main scraping function with resume capability"""
    users = []
    existing_ids = set()
    
    data_json_file = os.path.join('FOLLOWERS_DATA', username, 'followers.json')
    
    if resume_data:
        existing_data = load_existing_data(data_json_file)
        users.extend(existing_data)
        existing_ids = {user['id'] for user in existing_data if 'id' in user}
        print(f"{UI.INFO} Resuming from {len(users)} existing users")
    
    params = {
        'count': '25',
        'search_surface': 'follow_list_page',
    }
    
    if resume_data and resume_data.get('max_id'):
        params['max_id'] = resume_data['max_id']
    
    try:
        def get_users(data):
            new_users = []
            for user in data.get('users', []):
                if user.get('id') not in existing_ids:
                    new_users.append(user)
                    existing_ids.add(user.get('id'))
            users.extend(new_users)
        
        print(f"{Colors.GREEN}Scraping started ....\n{Colors.RESET}")
        response = req(params, user_id, username, session_id)
        
        if response and response.status_code == 200:
            result = response.json()
            get_users(result)
            print(f"{UI.PLUS} Added {len(users)} new users")
            
            if result.get('page_size') == 50 and not result.get('big_list'):
                print(f'{Colors.YELLOW}\nCan\'t scrape more than 50 followers, {username} is verified\n{Colors.RESET}')
                remove_temp_file(username)
        else:
            status = response.status_code if response else 'timeout/failed'
            print(f"{UI.ERROR} Error: Status code {status}")
            return users

        scrape_limit = resume_data['scrape_limit'] if resume_data else scrape_amount
        limit_text = "All" if scrape_limit == float('inf') else str(scrape_limit)
        print(f"{Colors.CYAN}Scraping [{limit_text}] Users\n{Colors.RESET}")

        while (result.get('next_max_id') and result.get('big_list')):
            try:
                params['max_id'] = result.get('next_max_id')

                save_temp_file(username, params['max_id'], len(users), scrape_limit)

                resp = req(params, user_id, username, session_id)
                if resp and resp.status_code == 200:
                    result = resp.json()
                    get_users(result)
                else:
                    status = resp.status_code if resp else 'timeout/failed'
                    print(f"{UI.ERROR} Error: Status code {status}")
                    break
                    
            except Exception as e:
                print(f"{UI.ERROR} Error during scraping: {e}")
                break
                
            if len(users) >= scrape_limit:
                remove_temp_file(username)
                break
                
            time.sleep(random.randint(3, 5))
            print(f'{Colors.GREEN}Scraped [{len(users)}]/[{limit_text}] {username}\'s followers{Colors.RESET}', end='\r')
            
        return users
    except Exception as e:
        print(f"{UI.ERROR} Error in get_data: {e}")
        return users
def write_json_data(data, username, append_mode=False):
    """Write unique followers users data to a JSON file"""
    followers_dir = os.path.join('FOLLOWERS_DATA', username)
    os.makedirs(followers_dir, exist_ok=True)
    data_json_file = os.path.join(followers_dir, 'followers.json')
    
    if append_mode:
        existing_data = load_existing_data(data_json_file)
        existing_ids = {user['id'] for user in existing_data if 'id' in user}
        
        for user in data:
            if user.get('id') not in existing_ids:
                existing_data.append(user)
                existing_ids.add(user.get('id'))
        
        data = existing_data
    
    unique_data = {}
    for item in data:
        if 'id' in item:
            unique_data.setdefault(item['id'], item)
    
    filtered_data = list(unique_data.values())
    print(f'\n\n{Colors.GREEN}Saved {len(filtered_data)} usernames\n{Colors.RESET}')
    
    try:
        with open(data_json_file, 'w', encoding='utf-8') as f:
            f.write('[\n')
            for i, item in enumerate(filtered_data):
                json_str = json.dumps(item, ensure_ascii=False)
                if i < len(filtered_data) - 1:
                    json_str += ','
                f.write(json_str + '\n')
            f.write(']')
        
        print(f"{UI.PLUS} Data saved to: {data_json_file}")
        return True
        
    except Exception as e:
        print(f"{UI.ERROR} Error writing data to file: {str(e)}\n")
        return False


def main():
    clear_screen()
    show_banner()
    
    accounts = load_accounts()
    selected_account = select_account(accounts)
    session_id = selected_account[1]  # Assuming session_id is at index 1
    
    choice = main_menu()
    
    try:
        if choice == 1:
            # Scrape new account
            username = input(f"{Colors.GREEN}Enter the account username: {Colors.RESET}")
            filename = 'Followers_scraped.txt'
            username_exists = False
            if os.path.exists(filename):
                with open(filename, 'r') as f:
                    for line in f:
                        if line.strip() == username:
                            username_exists = True
                            break
            if not username_exists:
                with open(filename, 'a') as f:
                    f.write(username + '\n')
            
            user_id, followers_count = get_userid(username, session_id=session_id)
            if not user_id:
                print(f"{UI.ERROR} Failed to find user ID for @{username}. Please check the username and try again.{Colors.RESET}")
                input(f"\n{UI.INFO} Press enter to continue...{Colors.RESET}")
                return

            if followers_count is not None:
                print(f'\n{Colors.CYAN}@{username} has [{followers_count}] followers{Colors.RESET}\n')
                prompt = f"Enter amount to scrape (0 for all {followers_count}): "
            else:
                print(f'\n{Colors.CYAN}Found @{username} (User ID: {user_id}){Colors.RESET}\n')
                prompt = "Enter amount to scrape (0 for all): "

            try:
                val = input(f"{Colors.GREEN}{prompt}{Colors.RESET}").strip()
                scrape_amount = int(val) if val.isdigit() else 0
            except ValueError:
                scrape_amount = 0

            if scrape_amount <= 0:
                scrape_amount = followers_count if (followers_count and followers_count > 0) else float('inf')

            scraped_data = get_data(user_id, followers_count, username, session_id, scrape_amount)

            if write_json_data(scraped_data, username):
                print(f"{UI.PLUS} Scraping completed successfully!")
            input(f"\n{UI.INFO} Press enter to continue...{Colors.RESET}")

        elif choice == 2:
            # Resume download
            temp_folders = get_temp_folders()

            if not temp_folders:
                print(f"{Colors.RED}No downloads to resume found!{Colors.RESET}")
                input(f"\n{UI.INFO} Press enter to continue...{Colors.RESET}")
                return

            selected_folder = select_resume_folder(temp_folders)
            if not selected_folder:
                return

            username = selected_folder['username']
            resume_data = selected_folder['temp_data']

            print(f"\n{Colors.CYAN}Resuming download for: @{username}{Colors.RESET}")

            user_id, followers_count = get_userid(username, session_id=session_id)
            if not user_id:
                print(f"{UI.ERROR} Failed to find user ID for @{username}.{Colors.RESET}")
                input(f"\n{UI.INFO} Press enter to continue...{Colors.RESET}")
                return

            scraped_data = get_data(user_id, followers_count, username, session_id, resume_data['scrape_limit'], resume_data)

            if write_json_data(scraped_data, username, append_mode=True):
                print(f"{UI.PLUS} Resume download completed successfully!")
            input(f"\n{UI.INFO} Press enter to continue...{Colors.RESET}")
    except KeyboardInterrupt:
        print(f'\n{Colors.GREEN}Goodbye!{Colors.RESET}')
        sys.exit(0)
