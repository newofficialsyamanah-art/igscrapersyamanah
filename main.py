import os
import sys
import random
import pyfiglet
from colorama import init, Fore
from time import sleep
from modules import Sessions_Manager,Get_Followers,Get_Following


init() 

lg = Fore.LIGHTGREEN_EX
w = Fore.WHITE
cy = Fore.CYAN
ye = Fore.YELLOW 
r = Fore.RED
rs = Fore.RESET
colors = [lg, r, w, cy, ye]

def clear_screen():
    """Cross-platform screen clearing"""
    os.system('cls' if os.name == 'nt' else 'clear')

def show_banner():
    """Display the application banner"""
    f = pyfiglet.Figlet(font='slant',width=300)
    banner = f.renderText('IG Tools')
    print(f'{random.choice(colors)}{banner}{rs}')
    print(f'{r}  Instagram Scrapers Suite |Version: 1.0 | Author: hendardev {rs}\n')

def main_menu():
    """Display main menu and handle user input"""
    while True:
        clear_screen()
        show_banner()
        
        print(f'{lg}[1] Session Manager')
        print(f'[2] Follower Scraper (CLI)')
        print(f'[3] Following Scraper')
        print(f'[4] Launch Web UI Dashboard (Browser)')
        print(f'[5] Exit{rs}')
        
        try:
            choice = input(f'\n{lg}Enter your choice: {r}').strip()
            
            if choice == '1':
                Sessions_Manager.main()
            elif choice == '2':
                Get_Followers.main()
            elif choice == '3':
                Get_Following.main()
                input('\nPress Enter to return to main menu...')
            elif choice == '4':
                import webbrowser
                import subprocess
                print(f'\n{cy}[*] Membuka Web UI Dashboard di http://localhost:5000 ...{rs}')
                try:
                    webbrowser.open('http://localhost:5000')
                except Exception:
                    pass
                # Run app.py directly
                os.system(f'"{sys.executable}" app.py')
            elif choice == '5':
                print(f'\n{lg}Goodbye!{rs}')
                sys.exit(0)
            else:
                print(f'{r}[!] Invalid choice{rs}')
                sleep(1)
        except KeyboardInterrupt:
            print(f'\n{lg}Goodbye!{rs}')
            sys.exit(0)

if __name__ == '__main__':
    main_menu()