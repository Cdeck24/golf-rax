import os
import time
import datetime
import io

import streamlit as st
import requests
import pandas as pd

# --- AUTH & CONFIGURATION ---
REAL_API_BASE = 'https://web.realsports.io'
REAL_VERSION = '27'
REAL_REFERER = 'https://realsports.io/'
DEFAULT_USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
)
DEFAULT_SEC_CH_UA = '"Chromium";v="125", "Not.A/Brand";v="24", "Google Chrome";v="125"'
DEVICE_NAME = 'Chrome on Windows'

# Your original values (local/private use only)
DEVICE_UUID = '0e497d76-7bd5-4cf5-b63c-f194d1d4cbcf'
REAL_AUTH_TOKEN = 'xnr5VpW3!ApZk8L2E!4fe6e26f-949f-4936-ae3e-16384878932f'


# --- HEADERS & TOKEN GENERATION ---
def build_headers(token: str) -> dict:
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
        'real-version': REAL_VERSION,
    }


def generate_request_token() -> str:
    salt = 'realwebapp'
    min_length = 16
    alphabet = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890'
    seps = 'cfhistuCFHISTU'

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

    def to_alphabet(num, alphabet_chars):
        result = []
        alphabet_len = len(alphabet_chars)
        while True:
            result.insert(0, alphabet_chars[num % alphabet_len])
            num = num // alphabet_len
            if num == 0:
                break
        return result

    salt_chars = list(salt)
    alphabet_chars = list(alphabet)
    seps_chars = list(seps)

    unique_alphabet = []
    seen = set()
    for char in alphabet_chars:
        if char not in seen:
            unique_alphabet.append(char)
            seen.add(char)

    alphabet_list = [c for c in unique_alphabet if c not in seps_chars]
    filtered_seps = [c for c in seps_chars if c in unique_alphabet]
    seps_list = shuffle(filtered_seps, salt_chars)

    if len(seps_list) == 0 or len(alphabet_list) / len(seps_list) > 3.5:
        seps_length = max(2, (len(alphabet_list) + 3) // 4)
        if seps_length > len(seps_list):
            diff = seps_length - len(seps_list)
            seps_list.extend(alphabet_list[:diff])
            alphabet_list = alphabet_list[diff:]
    alphabet_list = shuffle(alphabet_list, salt_chars)

    guard_count = max(1, len(alphabet_list) // 12)
    if len(alphabet_list) < 3:
        guards = seps_list[:guard_count]
        seps_list = seps_list[guard_count:]
    else:
        guards = alphabet_list[:guard_count]
        alphabet_list = alphabet_list[guard_count:]

    timestamp_ms = int(time.time() * 1000)
    numbers = [timestamp_ms]
    alphabet_working = list(alphabet_list)

    numbers_id_int = 0
    for i, number in enumerate(numbers):
        numbers_id_int += number % (i + 100)

    ret = [alphabet_working[numbers_id_int % len(alphabet_working)]]
    lottery = list(ret)

    for i, number in enumerate(numbers):
        buffer = lottery + salt_chars + alphabet_working
        alphabet_working = shuffle(alphabet_working, buffer)
        last = to_alphabet(number, alphabet_working)
        ret.extend(last)
        if i + 1 < len(numbers):
            char_code = ord(last[0])
            extra_number = number % (char_code + i)
            ret.append(seps_list[extra_number % len(seps_list)])

    if len(ret) < min_length:
        prefix_guard_index = (numbers_id_int + ord(ret[0])) % len(guards)
        ret.insert(0, guards[prefix_guard_index])
        if len(ret) < min_length:
            suffix_guard_index = (numbers_id_int + ord(ret[2])) % len(guards)
            ret.append(guards[suffix_guard_index])

    half_length = len(alphabet_working) // 2
    while len(ret) < min_length:
        alphabet_working = shuffle(alphabet_working, alphabet_working)
        ret = alphabet_working[half_length:] + ret + alphabet_working[:half_length]
        excess = len(ret) - min_length
        if excess > 0:
            half_of_excess = excess // 2
            ret = ret[half_of_excess:half_of_excess + min_length]

    return ''.join(ret)


# --- Page Configuration ---
st.set_page_config(page_title="Golf Rax", layout="wide")
st.title("⛳ Golf Rax – Player Rankings")
st.markdown(
    "View current golf player rankings from the RealSports API "
    "for the 2026 season."
)


# --- GLOBAL STORAGE ---
@st.cache_resource
class GlobalPlayerStore:
    def __init__(self):
        self.data = pd.DataFrame(
            columns=['Rank', 'Player', 'Team', 'Points', 'Active', 'Details', 'ID']
        )

    def update(self, new_df: pd.DataFrame):
        self.data = new_df

    def get(self) -> pd.DataFrame:
        return self.data


player_store = GlobalPlayerStore()


# --- Helper Functions ---
def get_fantasy_day() -> datetime.date:
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    us_time = utc_now - datetime.timedelta(hours=5)
    return us_time.date()


def fetch_golf_data(target_date: datetime.date):
    session = requests.Session()
    token = generate_request_token()
    session.headers.update(build_headers(token))

    golf_data = []
    date_str = str(target_date)

    url = (
        f"{REAL_API_BASE}/rankings/sport/golf/entity/player/"
        f"ranking/primary?season=2026"
    )

    try:
        r = session.get(url, timeout=10)
        if r.status_code != 200:
            st.error(f"API Error: {r.status_code} – {r.text}")
            return [], date_str

        data = r.json()
        if not isinstance(data, dict):
            st.error("Unexpected API response format.")
            return [], date_str

        # Your sample shows the list is under "items"
        raw_list = data.get("items", [])
        if not isinstance(raw_list, list):
            st.error("Expected 'items' to be a list in API response.")
            return [], date_str

        for idx, item in enumerate(raw_list, start=1):
            # item itself is the player record
            player = item

            full_name = (
                f"{player.get('firstName', '')} {player.get('lastName', '')}"
            ).strip()
            if not full_name:
                full_name = player.get('displayName') or "Unknown"

            # No 'details' field in your sample; keep placeholder logic
            details_text = ""

            rank = (
                item.get("value")      # ranking position from your JSON
                or item.get("rank")
                or item.get("position")
                or idx                 # fallback to list index if needed
            )
            points = (
                item.get("rating")     # rating string from your JSON
                or item.get("points")
                or item.get("score")
                or item.get("value")
            )

            # No explicit "active" field; treat as None
            active = None

            team_abbrev = player.get('team', {}).get('abbreviation')
            if not team_abbrev and 'teamId' in player:
                # We only have teamId in this endpoint; show that instead
                team_abbrev = f"Team {player.get('teamId')}"

            golf_data.append(
                {
                    "Rank": rank,
                    "Player": full_name,
                    "Team": team_abbrev or 'N/A',
                    "Points": points,
                    "Active": active,
                    "Details": details_text,
                    "ID": player.get('id', '')
                }
            )
    except Exception as e:
        st.error(f"API Request Failed: {e}")
        return [], date_str

    return golf_data, date_str


# --- Main UI ---
top_left, top_right = st.columns([1, 4])

with top_left:
    st.write("### Actions")
    fetch_btn = st.button("Refresh Rankings", type="primary")

with top_right:
    df_players = player_store.get()

    col_search, col_active = st.columns([3, 1])
    with col_search:
        search = st.text_input("Search players", "", placeholder="Type a name...")
    with col_active:
        active_only = st.checkbox("Active only", value=False)

    if fetch_btn:
        progress = st.progress(0)
        status = st.empty()
        try:
            status.text("Fetching golf rankings...")
            fetch_date = get_fantasy_day()
            data, date_str = fetch_golf_data(fetch_date)

            if data:
                df_new = pd.DataFrame(data)
                df_new = df_new.drop_duplicates(subset=['Player'], keep='first')

                if "Rank" in df_new.columns:
                    df_new = df_new.sort_values(
                        by=["Rank", "Player"], na_position="last"
                    )
                else:
                    df_new = df_new.sort_values(by="Player")

                df_new = df_new[
                    [
                        "Rank",
                        "Player",
                        "Team",
                        "Points",
                        "Active",
                        "Details",
                        "ID",
                    ]
                ]

                player_store.update(df_new)
                st.success(
                    f"✅ Fetched {len(df_new)} golfers for season 2026 "
                    f"(as of {date_str})"
                )
            else:
                st.warning(
                    "No players found. Check if the RealSports ranking "
                    "endpoint is returning data."
                )
        except Exception as e:
            st.error(f"Error: {e}")
        progress.empty()
        status.empty()

    df_players = player_store.get()
    if not df_players.empty:
        filtered = df_players.copy()

        if active_only and "Active" in filtered.columns:
            filtered = filtered[filtered["Active"] == True]

        if search:
            filtered = filtered[
                filtered["Player"].str.contains(search, case=False, na=False)
            ]

        st.write(f"### Player Rankings ({len(filtered)})")

        st.dataframe(
            filtered[["Rank", "Player", "Team", "Points"]],
            use_container_width=True,
            hide_index=True,
        )

        csv = filtered.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download as CSV",
            data=csv,
            file_name="golf_rankings.csv",
            mime="text/csv",
        )
    else:
        st.info("Click 'Refresh Rankings' to load the table.")
