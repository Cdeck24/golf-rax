import time
import datetime

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


def create_session() -> requests.Session:
    session = requests.Session()
    token = generate_request_token()
    session.headers.update(build_headers(token))
    return session


# --- Page Configuration ---
st.set_page_config(page_title="Golf Earnings 2014–2026", layout="wide")
st.title("⛳ Golf Rax – Multi‑Season Earnings (2014–2026)")
st.markdown(
    "Build a table of golf earnings per player and season using RealSports endpoints."
)


# --- GLOBAL STORAGE ---
@st.cache_resource
class EarningsStore:
    def __init__(self):
        self.multi = pd.DataFrame(
            columns=[
                "Player",
                "Team",
                "PrimaryRanking",
                "PlayerID",
                "Season",
                "SeasonLabel",
                "TotalEarnings",
            ]
        )

    def update_multi(self, df: pd.DataFrame):
        self.multi = df

    def get_multi(self) -> pd.DataFrame:
        return self.multi


earnings_store = EarningsStore()


# --- Load IDs from All_Golfer_IDs.csv ---
@st.cache_data
def load_golfer_ids():
    # If the file is in the working directory:
    df_ids = pd.read_csv("All_Golfer_IDs.csv")
    df_ids = df_ids.dropna(subset=["ID"])
    df_ids["ID"] = df_ids["ID"].astype(int)
    return df_ids[["Player", "Team", "PrimaryRanking", "ID"]]


# --- Single-player earnings fetch for a given season ---
def fetch_player_earnings(player_id: int, season: int):
    session = create_session()

    url = (
        f"{REAL_API_BASE}/userpassearnings/golf/season/{season}/"
        f"entity/player/{player_id}"
    )

    try:
        r = session.get(url, timeout=10)
        if r.status_code != 200:
            return None

        data = r.json()
        earnings_list = data.get("earnings", [])
        info = data.get("info", {}) or {}
        total = info.get("total", 0)

        return {
            "Season": season,
            "PlayerID": player_id,
            "TotalEarnings": total,
            "SeasonLabel": info.get("seasonLabel"),
            "RawEarnings": earnings_list,
        }
    except Exception:
        return None


# --- Build earnings for all players, all seasons 2014–2026 ---
def build_all_golf_earnings_multi_season(start_season: int = 2014, end_season: int = 2026):
    df_ids = load_golfer_ids()
    seasons = list(range(start_season, end_season + 1))

    results = []

    total_steps = len(df_ids) * len(seasons)
    step = 0
    progress = st.progress(0)
    status = st.empty()

    for _, row in df_ids.iterrows():
        player_id = int(row["ID"])
        player_name = row["Player"]

        for season in seasons:
            step += 1
            status.text(
                f"Fetching earnings for {player_name} ({player_id}) – "
                f"Season {season} [{step}/{total_steps}]..."
            )

            rec = fetch_player_earnings(player_id, season=season)
            if rec is not None:
                results.append(
                    {
                        "Player": player_name,
                        "Team": row["Team"],
                        "PrimaryRanking": row["PrimaryRanking"],
                        "PlayerID": player_id,
                        "Season": season,
                        "SeasonLabel": rec["SeasonLabel"],
                        "TotalEarnings": rec["TotalEarnings"],
                    }
                )

            progress.progress(step / total_steps)
            time.sleep(0.05)  # throttle a bit

    progress.empty()
    status.empty()

    if not results:
        return pd.DataFrame(
            columns=[
                "Player",
                "Team",
                "PrimaryRanking",
                "PlayerID",
                "Season",
                "SeasonLabel",
                "TotalEarnings",
            ]
        )

    df = pd.DataFrame(results)
    return df


# --- UI ---
top_left, top_right = st.columns([1, 4])

with top_left:
    st.write("### Actions")
    build_multi_btn = st.button("Build earnings 2014–2026", type="primary")

with top_right:
    if build_multi_btn:
        df_multi = build_all_golf_earnings_multi_season(2014, 2026)
        earnings_store.update_multi(df_multi)

    df_multi = earnings_store.get_multi()

    if not df_multi.empty:
        # Controls
        col_season, col_search = st.columns([1, 3])
        with col_season:
            season_filter = st.selectbox(
                "Filter by season",
                options=["All"] + sorted(df_multi["Season"].dropna().unique().tolist()),
                index=0,
            )
        with col_search:
            name_filter = st.text_input(
                "Search by player name", "", placeholder="Type part of a name..."
            )

        df_view = df_multi.copy()
        if season_filter != "All":
            df_view = df_view[df_view["Season"] == season_filter]

        if name_filter:
            df_view = df_view[
                df_view["Player"].str.contains(name_filter, case=False, na=False)
            ]

        df_view = df_view.sort_values(
            by=["Season", "TotalEarnings", "Player"],
            ascending=[True, False, True],
        )

        st.write(
            f"Rows: {len(df_view)} (player × season; 2014–2026 with any earnings)"
        )
        st.dataframe(
            df_view[
                [
                    "Season",
                    "Player",
                    "Team",
                    "PrimaryRanking",
                    "PlayerID",
                    "TotalEarnings",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )

        csv_multi = df_view.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download filtered earnings as CSV",
            data=csv_multi,
            file_name="golf_all_earnings_2014_2026_filtered.csv",
            mime="text/csv",
        )
    else:
        st.info("Click 'Build earnings 2014–2026' to start fetching data.")
