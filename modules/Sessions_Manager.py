import os
import pickle
import random
import pyfiglet
import requests
from time import sleep
from colorama import init, Fore
from fake_useragent import UserAgent

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
    banner = f.renderText('Manager')
    print(f'{random.choice(colors)}{banner}{Colors.RESET}')
    print(f'{Colors.RED}Session  Manager | Version: 1.0 | Author: Kev {Colors.RESET}\n')

DEFAULT_SESSION_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'session_file.txt')

def load_sessions(filename=None):
    """Load sessions from file"""
    if filename is None:
        filename = DEFAULT_SESSION_FILE
    sessions = []
    try:
        with open(filename, 'rb') as f:
            while True:
                try:
                    sessions.append(pickle.load(f))
                except EOFError:
                    break
    except FileNotFoundError:
        pass
    return sessions

def save_sessions(sessions, filename=None):
    """Save sessions to file"""
    if filename is None:
        filename = DEFAULT_SESSION_FILE
    with open(filename, 'wb') as f:
        for session in sessions:
            pickle.dump(session, f)

def get_userid(to_scrape_username, session_id=None):
    """Get user ID from Instagram API using topsearch and fallbacks."""
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

    # Method 1: Search via topsearch API
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
                        return str(u.get('pk'))
        except Exception:
            continue

    # Method 2: web_profile_info fallback
    url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={to_scrape_username}"
    try:
        response = requests.get(url, headers=headers, cookies=cookies or None, timeout=15)
        if response.status_code == 200:
            payload = response.json()
            return str(payload.get('data', {}).get('user', {}).get('id'))
    except Exception:
        pass

    return None

def verify_session(username, session_id):
    """Verify if a session ID is valid directly using authenticated endpoints"""
    headers = {
        'accept': '*/*',
        'accept-language': 'en-US,en;q=0.9',
        'referer': 'https://www.instagram.com/',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'x-ig-app-id': '936619743392459',
        'x-requested-with': 'XMLHttpRequest',
    }
    cookies = {'sessionid': session_id}

    # Primary check: verify session via web_form_data (fast & directly validates session)
    try:
        url = 'https://www.instagram.com/api/v1/accounts/edit/web_form_data/'
        response = requests.get(url, headers=headers, cookies=cookies, timeout=15)

        if hasattr(response, 'url') and response.url and 'login' in response.url.lower():
            return False, "Session is invalid or expired (redirected to login)"

        if response.status_code == 200:
            try:
                data = response.json()
                form_user = data.get('form_data', {}).get('username')
                if form_user:
                    if username and form_user.lower() != username.lower():
                        return True, f"Session is valid! (Logged in as @{form_user})"
                    return True, f"Session is valid for @{form_user}!"
            except (ValueError, AttributeError):
                pass
            return True, "Session is valid!"
        elif response.status_code in [401, 403]:
            return False, f"Session invalid or forbidden (HTTP {response.status_code})"
    except requests.exceptions.TooManyRedirects:
        return False, "Session is invalid or expired (redirect loop to login)"
    except Exception:
        pass

    # Secondary check: verify via friendship endpoint using user ID extracted from session_id
    try:
        user_id = session_id.split(':')[0].split('%3A')[0]
        if user_id.isdigit():
            url = f'https://www.instagram.com/api/v1/friendships/{user_id}/following/?count=5'
            resp = requests.get(url, headers=headers, cookies=cookies, timeout=15)
            if resp.status_code == 200:
                return True, "Session is valid!"
            elif resp.status_code == 401:
                return False, "Session is invalid or expired"
            elif resp.status_code == 403:
                return False, "Access forbidden (checkpoint/challenge required)"
    except Exception as e:
        return False, f"Request error: {str(e)}"

    return False, "Session verification failed (invalid or expired session)"

def add_sessions():
    """Add new sessions"""
    newly_added = []
    while True:
        try:
            clear_screen()
            show_banner()
            print(f"{UI.INFO} Adding new session (leave username empty to stop){Colors.RESET}")
            
            username = input(f"\n{UI.PLUS} Enter username: ").strip()
            if not username:
                break
                
            session_id = input(f"{UI.PLUS} Enter session ID: ").strip()
            if not session_id:
                print(f"{UI.ERROR} Session ID cannot be empty{Colors.RESET}")
                sleep(2)
                continue
                
            print(f"\n{UI.INFO} Verifying session...{Colors.RESET}")
            is_valid, message = verify_session(username, session_id)
            
            if is_valid:
                print(f"{UI.PLUS} {message}{Colors.RESET}")
                newly_added.append((username, session_id))
            else:
                print(f"{UI.ERROR} Session verification failed: {message}{Colors.RESET}")
                if "proxy" in message.lower():
                    print(f"{UI.WARNING} Consider using a residential proxy{Colors.RESET}")
            
            if input(f'\n{UI.INFO} Add more sessions? [y/n]: ').lower() != 'y':
                break
                
        except Exception as e:
            print(f'{UI.ERROR} Error: {str(e)}{Colors.RESET}')
            sleep(2)
    
    if newly_added:
        existing = load_sessions()
        all_sessions = existing + newly_added
        save_sessions(all_sessions)
        print(f'\n{UI.PLUS} Saved {len(newly_added)} new sessions in session_file.txt{Colors.RESET}')
    else:
        print(f'\n{UI.WARNING} No new sessions were added{Colors.RESET}')
    
    sleep(2)

def filter_invalid_sessions():
    """Filter out invalid sessions"""
    sessions = load_sessions()
    if not sessions:
        print(f'{UI.ERROR} No sessions found!{Colors.RESET}')
        sleep(2)
        return
    
    valid_sessions = []
    invalid_sessions = []
    
    for username, session_id in sessions:
        try:
            print(f'\n{UI.INFO} Checking session for {username}...{Colors.RESET}')
            is_valid, message = verify_session(username, session_id)
            
            if is_valid:
                print(f'{UI.PLUS} Valid session for {username}{Colors.RESET}')
                valid_sessions.append((username, session_id))
            else:
                print(f'{UI.ERROR} Invalid session for {username}: {message}{Colors.RESET}')
                invalid_sessions.append((username, session_id))
                
        except Exception as e:
            print(f'{UI.ERROR} Error checking {username}: {str(e)}{Colors.RESET}')
            valid_sessions.append((username, session_id))  # Keep session if unsure
    
    if invalid_sessions:
        save_sessions(valid_sessions)
        print(f'\n{UI.PLUS} Removed {len(invalid_sessions)} invalid sessions{Colors.RESET}')
    else:
        print(f'\n{UI.INFO} No invalid sessions found{Colors.RESET}')
    
    input(f'\n{UI.INFO} Press enter to continue...{Colors.RESET}')

def list_sessions():
    """List all sessions"""
    sessions = load_sessions()
    if not sessions:
        print(f'{UI.ERROR} No sessions found{Colors.RESET}')
    else:
        print(f'\n{Colors.CYAN}{"Username":<20} | {"Session ID":<32}{Colors.RESET}')
        print('-' * 60)
        for username, session_id in sessions:
            print(f'{username:<20} | {session_id:<32}')
        print(f'\n{UI.INFO} Total sessions: {len(sessions)}{Colors.RESET}')
    
    input(f'\n{UI.INFO} Press enter to continue...{Colors.RESET}')

def delete_session():
    """Delete a session"""
    sessions = load_sessions()
    if not sessions:
        print(f'{UI.ERROR} No sessions found{Colors.RESET}')
        sleep(2)
        return
    
    print(f'\n{UI.INFO} Select session to delete:{Colors.RESET}')
    for i, (username, _) in enumerate(sessions):
        print(f'{Colors.CYAN}[{i}] {username}{Colors.RESET}')
    
    try:
        choice = int(input(f'\n{UI.INFO} Enter choice: {Colors.RED}'))
        if 0 <= choice < len(sessions):
            username, session_id = sessions[choice]
            del sessions[choice]
            save_sessions(sessions)
            print(f'\n{UI.PLUS} Session deleted: {username}{Colors.RESET}')
        else:
            print(f'{UI.ERROR} Invalid selection{Colors.RESET}')
    except ValueError:
        print(f'{UI.ERROR} Please enter a number{Colors.RESET}')
    
    input(f'\n{UI.INFO} Press enter to continue...{Colors.RESET}')

def main():
    """Main application loop"""
    while True:
        clear_screen()
        show_banner()
        
        print(f'{Colors.CYAN}[1] Add new sessions')
        print(f'[2] Filter invalid sessions')
        print(f'[3] List all sessions')
        print(f'[4] Delete a session')
        print(f'[5] Exit{Colors.RESET}')
        
        try:
            choice = input(f'\n{UI.INFO} Enter your choice: {Colors.RED}').strip()
            
            if choice == '1':
                add_sessions()
            elif choice == '2':
                filter_invalid_sessions()
            elif choice == '3':
                list_sessions()
            elif choice == '4':
                delete_session()
            elif choice == '5':
                print(f'\n{UI.PLUS} Exiting...{Colors.RESET}')
                break
            else:
                print(f'{UI.ERROR} Invalid choice{Colors.RESET}')
                sleep(1)
        except KeyboardInterrupt:
            print(f'\n{Colors.RED}Goodbye!{Colors.RESET}')
            break

