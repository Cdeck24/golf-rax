import streamlit as st
import requests
import datetime
import pandas as pd
import io
import time

# --- AUTH & CONFIGURATION ---
REAL_API_BASE = 'https://web.realsports.io'
REAL_VERSION = '27'
REAL_REFERER = 'https://realsports.io/'
DEFAULT_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
DEFAULT_SEC_CH_UA = '"Chromium";v="125", "Not.A/Brand";v="24", "Google Chrome";v="125"'
DEVICE_NAME = 'Chrome on Windows'
DEVICE_UUID = '0e497d76-7bd5-4cf5-b63c-f194d1d4cbcf'
REAL_AUTH_TOKEN = 'xnr5VpW3!ApZk8L2E!4fe6e26f-949f-4936-ae3e-16384878932f'

# --- HEADERS & TOKEN GENERATION ---
def build_headers(token):
    return {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'DNT': '1',
        'Origin': 'https://realsports.io',
        'Referer': REAL_REFERER,
        'User-Agent': DEFAULT_USER_AGENT,
        'sec-ch-ua': DEFAULT_SEC_CH_UA,
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'real-auth-info': REAL_AUTH_TOKEN,
        'real-device-name': DEVICE_NAME,
        'real-device-type': 'desktop_web',
        'real-device-uuid': DEVICE_UUID,
        'real-request-token': token,
        'real-version': REAL_VERSION
    }

def generate_request_token():
    # Configuration
    salt = 'realwebapp'
    min_length = 16
    alphabet = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890'
    seps = 'cfhistuCFHISTU'

    # shuffle
    def shuffle(alphabet_chars, salt_chars):
        if len(salt_chars) == 0:
            return alphabet_chars
        transformed = list(alphabet_chars)
        v = 0
        p = 0
        for i in range(len(transformed) - 1, 0, -1):
            v %= len(salt_chars)
            integer = ord(salt_chars[v])
            p += integer
            j = (integer + v + p) % i
            transformed[i], transformed[j] = transformed[j], transformed[i]
            v += 1
        return transformed

    #convert number to alphabet representation
    def to_alphabet(num, alphabet_chars):
        result = []
        alphabet_len = len(alphabet_chars)
        while True:
            result.insert(0, alphabet_chars[num % alphabet_len])
            num = num // alphabet_len
            if num == 0:
                break
        return result

    # Initialize alphabet and seps
    salt_chars = list(salt)
    alphabet_chars = list(alphabet)
    seps_chars = list(seps)

    # Get unique alphabet
    unique_alphabet = []
    seen = set()
    for char in alphabet_chars:
        if char not in seen:
            unique_alphabet.append(char)
            seen.add(char)

    # Remove seps from alphabet
    alphabet_list = [c for c in unique_alphabet if c not in seps_chars]

    # Filter seps
    filtered_seps = [c for c in seps_chars if c in unique_alphabet]
    seps_list = shuffle(filtered_seps, salt_chars)

    # Adjust seps and alphabet
    if len(seps_list) == 0 or len(alphabet_list) / len(seps_list) > 3.5:
        seps_length = max(2, (len(alphabet_list) + 3) // 4)
        if seps_length > len(seps_list):
            diff = seps_length - len(seps_list)
            seps_list.extend(alphabet_list[:diff])
            alphabet_list = alphabet_list[diff:]

    alphabet_list = shuffle(alphabet_list, salt_chars)

    # Setup guards
    guard_count = max(1, len(alphabet_list) // 12)
    if len(alphabet_list) < 3:
        guards = seps_list[:guard_count]
        seps_list = seps_list[guard_count:]
    else:
        guards = alphabet_list[:guard_count]
        alphabet_list = alphabet_list[guard_count:]

    # Encode timestamp
    timestamp_ms = int(time.time() * 1000)
    numbers = [timestamp_ms]

    alphabet_working = list(alphabet_list)

    # Calculate numbersIdInt
    numbers_id_int = 0
    for i, number in enumerate(numbers):
        numbers_id_int += number % (i + 100)

    # Lottery character
    ret = [alphabet_working[numbers_id_int % len(alphabet_working)]]
    lottery = list(ret)

    # Encode each number
    for i, number in enumerate(numbers):
        buffer = lottery + salt_chars + alphabet_working
        alphabet_working = shuffle(alphabet_working, buffer)
        last = to_alphabet(number, alphabet_working)
        ret.extend(last)

        if i + 1 < len(numbers):
            char_code = ord(last[0])
            extra_number = number % (char_code + i)
            ret.append(seps_list[extra_number % len(seps_list)])

    # Ensure minimum length
    if len(ret) < min_length:
        prefix_guard_index = (numbers_id_int + ord(ret[0])) % len(guards)
        ret.insert(0, guards[prefix_guard_index])
        if len(ret) < min_length:
            suffix_guard_index = (numbers_id_int + ord(ret[2])) % len(guards)
            ret.append(guards[suffix_guard_index])

    # Extend to minimum length with shuffling
    half_length = len(alphabet_working) // 2
    while len(ret) < min_length:
        alphabet_working = shuffle(alphabet_working, alphabet_working)
        ret = alphabet_working[half_length:] + ret + alphabet_working[:half_length]
        excess = len(ret) - min_length
        if excess > 0:
            half_of_excess = excess // 2
            ret = ret[half_of_excess:half_of_excess + min_length]

    return ''.join(ret)

token = generate_request_token()
HEADERS = build_headers(token)

# --- Page Configuration ---
st.set_page_config(page_title="Golf Player List", layout="wide")

st.title("⛳ Golf Player List")
st.markdown("""
This tool fetches all active golfers from the RealSports API for the current day.
""")

# --- GLOBAL STORAGE ---
@st.cache_resource
class GlobalPlayerStore:
    def __init__(self):
        self.data = pd.DataFrame(columns=['Player Name', 'Team', 'Details', 'ID'])
    
    def update(self, new_df):
        self.data = new_df
        
    def get(self):
        return self.data

player_store = GlobalPlayerStore()

# --- Helper Functions ---
def get_fantasy_day():
    """Returns the current date in US Eastern Time."""
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    us_time = utc_now - datetime.timedelta(hours=5)
    return us_time.date()

def fetch_golf_data(target_date):
    session = requests.Session()
    session.headers.update(HEADERS)
    golf_data = []
    
    active_date_str = str(target_date)
    
    # Updated to Ranking URL as requested
    url = "https://web.realsports.io/rankings/sport/golf/entity/player/ranking/primary?season=2026"
    
    try:
        r = session.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            raw_list = []
            
            # Robust Parsing: Handle List or Dictionary response
            if isinstance(data, list):
                raw_list = data
            elif isinstance(data, dict):
                # Try common keys found in ranking APIs
                raw_list = data.get("players") or data.get("rankings") or data.get("data") or []
            
            for item in raw_list:
                # Ranking endpoints often nest the actual player object inside a 'player' key
                # Search endpoints usually have it at the top level
                # This line handles both cases safely
                player = item.get('player', item)
                
                # Check for basic required fields
                if not isinstance(player, dict):
                    continue

                full_name = f"{player.get('firstName', '')} {player.get('lastName', '')}".strip()
                if not full_name:
                    full_name = player.get('displayName') or "Unknown"
                
                details_text = ""
                details = player.get("details")
                if details and isinstance(details, list) and len(details) > 0 and "text" in details[0]:
                    details_text = details[0]["text"]
                
                golf_data.append({
                    "Player Name": full_name,
                    "Team": player.get('team', {}).get('abbreviation', 'N/A'),
                    "Details": details_text,
                    "ID": player.get('id', '')
                })
    except Exception as e:
        st.error(f"API Request Failed: {e}")
        pass
            
    return golf_data, active_date_str

# --- Main UI ---

col1, col2 = st.columns([1, 4])

with col1:
    st.write("### Actions")
    fetch_btn = st.button("Fetch All Golfers", type="primary")

with col2:
    if fetch_btn:
        progress = st.progress(0)
        status = st.empty()
        try:
            status.text("Fetching Golf data...")
            fetch_date = get_fantasy_day()
            data, date_str = fetch_golf_data(fetch_date)
            
            if data:
                df_new = pd.DataFrame(data)
                # Dedup
                df_new = df_new.drop_duplicates(subset=['Player Name'], keep='first')
                df_new = df_new.sort_values(by="Player Name")
                player_store.update(df_new)
                st.success(f"✅ Fetched {len(df_new)} Golfers for {date_str}")
            else:
                st.warning("No players found. Is there a tournament active today?")
                
        except Exception as e:
            st.error(f"Error: {e}")
        
        progress.empty()
        status.empty()

    # Display Data
    df_players = player_store.get()

    if not df_players.empty:
        st.write(f"### Player List ({len(df_players)})")
        st.dataframe(
            df_players, 
            use_container_width=True,
            hide_index=True
        )
        
        # Download CSV
        csv = df_players.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download as CSV",
            data=csv,
            file_name='golf_players.csv',
            mime='text/csv',
        )
    else:
        st.info("Click 'Fetch All Golfers' to see the list.")
