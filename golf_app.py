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
        self.rankings = pd.DataFrame(
            columns=['Rank', 'Player', 'Team', 'Points', 'Active', 'Details', 'ID']
        )
        self.all_players = pd.DataFrame(
            columns=['Player', 'Team', 'ID', 'Sport']
        )

    def update_rankings(self, new_df: pd.DataFrame):
        self.rankings = new_df

    def update_all_players(self, new_df: pd.DataFrame):
        self.all_players = new_df

    def get_rankings(self) -> pd.DataFrame:
        return self.rankings

    def get_all_players(self) -> pd.DataFrame:
        return self.all_players


player_store = GlobalPlayerStore()


# --- Helper Functions ---
def get_fantasy_day() -> datetime.date:
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    us_time = utc_now - datetime.timedelta(hours=5)
    return us_time.date()


def create_session() -> requests.Session:
    session = requests.Session()
    token = generate_request_token()
    session.headers.update(build_headers(token))
    return session


def fetch_golf_rankings(target_date: datetime.date):
    session = create_session()
    golf_data = []
    date_str = str(target_date)

    url = (
        f"{REAL_API_BASE}/rankings/sport/golf/entity/player/"
        f"ranking/primary?season=2026"
    )

    try:
        r = session.get(url, timeout=10)
        if r.status_code != 200:
            st.error(f"Rankings API Error: {r.status_code} – {r.text}")
            return [], date_str

        data = r.json()
        if not isinstance(data, dict):
            st.error("Unexpected rankings API response format.")
            return [], date_str

        raw_list = data.get("items", [])
        if not isinstance(raw_list, list):
            st.error("Expected 'items' list in rankings response.")
            return [], date_str

        for idx, item in enumerate(raw_list, start=1):
            player = item

            full_name = (
                f"{player.get('firstName', '')} {player.get('lastName', '')}"
            ).strip()
            if not full_name:
                full_name = player.get('displayName') or "Unknown"

            details_text = ""

            rank = (
                item.get("value")
                or item.get("rank")
                or item.get("position")
                or idx
            )
            points = (
                item.get("rating")
                or item.get("points")
                or item.get("score")
                or item.get("value")
            )

            active = None

            team_abbrev = player.get('team', {}).get('abbreviation')
            if not team_abbrev and 'teamId' in player:
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
        st.error(f"Rankings API Request Failed: {e}")
        return [], date_str

    return golf_data, date_str


def fetch_all_golf_players():
    """
    Uses the golf players search endpoint you found:
    https://web.realsports.io/players/sport/golf/search?includeNoOneOption=false
    """
    session = create_session()
    url = (
        f"{REAL_API_BASE}/players/sport/golf/search"
        f"?includeNoOneOption=false"
    )

    players = []

    try:
        r = session.get(url, timeout=15)
        if r.status_code != 200:
            st.error(f"Players API Error: {r.status_code} – {r.text}")
            return []

        data = r.json()
        # You may want to print once while testing:
        # st.write("DEBUG players response:", data)

        # Guessing structure similar to rankings: list under "items"
        raw_list = data.get("items", [])
        if not isinstance(raw_list, list):
            # fallback: if the API returns directly a list
            if isinstance(data, list):
                raw_list = data
            else:
                st.error("Expected 'items' list in players response.")
                return []

        for item in raw_list:
            player = item

            full_name = (
                f"{player.get('firstName', '')} {player.get('lastName', '')}"
            ).strip()
            if not full_name:
                full_name = player.get('displayName') or "Unknown"

            team_abbrev = player.get('team', {}).get('abbreviation')
            if not team_abbrev and 'teamId' in player:
                team_abbrev = f"Team {player.get('teamId')}"

            players.append(
                {
                    "Player": full_name,
                    "Team": team_abbrev or "N/A",
                    "ID": player.get("id", ""),
                    "Sport": player.get("sport", "golf"),
                }
            )
    except Exception as e:
        st.error(f"Players API Request Failed: {e}")
        return []

    return players


# --- Main UI ---
top_left, top_right = st.columns([1, 4])

with top_left:
    st.write("### Actions")
    fetch_rankings_btn = st.button("Refresh Rankings", type="primary")
    fetch_all_players_btn = st.button("Load All Players")

with top_right:
    df_rankings = player_store.get_rankings()
    df_all_players = player_store.get_all_players()

    col_search, col_active = st.columns([3, 1])
    with col_search:
        search = st.text_input("Search players", "", placeholder="Type a name...")
    with col_active:
        active_only = st.checkbox("Active only (rankings)", value=False)

    # --- Fetch rankings ---
    if fetch_rankings_btn:
        progress = st.progress(0)
        status = st.empty()
        try:
            status.text("Fetching golf rankings...")
            fetch_date = get_fantasy_day()
            data, date_str = fetch_golf_rankings(fetch_date)

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

                player_store.update_rankings(df_new)
                st.success(
                    f"✅ Fetched {len(df_new)} golfers for season 2026 "
                    f"(as of {date_str})"
                )
            else:
                st.warning(
                    "No players found in rankings. "
                    "Check if the RealSports ranking endpoint is returning data."
                )
        except Exception as e:
            st.error(f"Rankings Error: {e}")
        progress.empty()
        status.empty()

    # --- Fetch all players ---
    if fetch_all_players_btn:
        progress = st.progress(0)
        status = st.empty()
        try:
            status.text("Fetching all golf players...")
            all_players = fetch_all_golf_players()
            if all_players:
                df_all = pd.DataFrame(all_players)
                df_all = df_all.drop_duplicates(subset=['Player', 'ID'], keep='first')
                df_all = df_all.sort_values(by=["Player"])
                player_store.update_all_players(df_all)
                st.success(f"✅ Loaded {len(df_all)} golf players")
            else:
                st.warning(
                    "No players returned from the players search endpoint."
                )
        except Exception as e:
            st.error(f"Players Error: {e}")
        progress.empty()
        status.empty()

    # --- Display rankings table ---
    df_rankings = player_store.get_rankings()
    if not df_rankings.empty:
        filtered_rankings = df_rankings.copy()

        if active_only and "Active" in filtered_rankings.columns:
            filtered_rankings = filtered_rankings[filtered_rankings["Active"] == True]

        if search:
            filtered_rankings = filtered_rankings[
                filtered_rankings["Player"].str.contains(search, case=False, na=False)
            ]

        st.write(f"### Player Rankings ({len(filtered_rankings)})")
        st.dataframe(
            filtered_rankings[["Rank", "Player", "Team", "Points"]],
            use_container_width=True,
            hide_index=True,
        )

        csv_rank = filtered_rankings.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download Rankings as CSV",
            data=csv_rank,
            file_name="golf_rankings.csv",
            mime="text/csv",
        )
    else:
        st.info("Click 'Refresh Rankings' to load the rankings table.")

    # --- Display all players table ---
    df_all_players = player_store.get_all_players()
    if not df_all_players.empty:
        df_all_filtered = df_all_players.copy()

        if search:
            df_all_filtered = df_all_filtered[
                df_all_filtered["Player"].str.contains(search, case=False, na=False)
            ]

        st.write(f"### All Golf Players ({len(df_all_filtered)})")
        st.dataframe(
            df_all_filtered[["Player", "Team", "ID"]],
            use_container_width=True,
            hide_index=True,
        )

        csv_all = df_all_filtered.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download All Players as CSV",
            data=csv_all,
            file_name="golf_all_players.csv",
            mime="text/csv",
        )
