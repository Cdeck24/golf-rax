import streamlit as st
import streamlit.components.v1 as components
import json
import os

# Set page config for a professional wide-screen look
st.set_page_config(
    page_title="TourAX Golf Analytics",
    page_icon="⛳",
    layout="wide",
    initial_sidebar_state="collapsed"
)

def load_golf_data(folder_path):
    """Reads all <year>-golf-data.json files and combines them into one list."""
    combined_data = []
    if not os.path.exists(folder_path):
        return []
    
    # Sort files to ensure chronological order if needed
    files = sorted([f for f in os.listdir(folder_path) if f.endswith('.json')])
    
    for filename in files:
        file_path = os.path.join(folder_path, filename)
        with open(file_path, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                # If the file is a list of tournaments, extend
                if isinstance(data, list):
                    combined_data.extend(data)
                else:
                    combined_data.append(data)
            except Exception as e:
                st.error(f"Error loading {filename}: {e}")
    
    return combined_data

# 1. Load the data from your local folder
raw_tournaments = load_golf_data('golf-otd')

# 2. Define the HTML/React wrapper
# We use CDN links for React, Babel (to transpile JSX on the fly), Tailwind, and Lucide Icons
html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <script src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
    <script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
    <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/lucide@latest"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&display=swap');
        body {{ font-family: 'Inter', sans-serif; background-color: #FDFDFD; }}
        .animate-in {{ animation: fadeIn 0.5s ease-out; }}
        @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(10px); }} to {{ opacity: 1; transform: translateY(0); }} }}
    </style>
</head>
<body>
    <div id="root"></div>

    <script type="text/babel">
        const {{ useState, useMemo, useEffect }} = React;
        
        // Injecting data from Streamlit/Python
        const RAW_DATA = {json.dumps(raw_tournaments)};

        // Lucide Icon Component Wrapper for CDN
        const Icon = ({{ name, size = 24, className = "" }}) => {{
            useEffect(() => {{
                if (window.lucide) window.lucide.createIcons();
            }}, [name]);
            return <i data-lucide={{name}} style={{ width: size, height: size }} className={{className}}></i>;
        }};

        // --- ENGINE LOGIC ---
        const AnalyticsEngine = {{
            calculateStability: (history) => {{
                if (!history || history.length < 2) return 50;
                const finishes = history.map(h => h.finish);
                const avg = finishes.reduce((a, b) => a + b, 0) / finishes.length;
                const variance = finishes.reduce((a, b) => a + Math.pow(b - avg, 2), 0) / finishes.length;
                const stdDev = Math.sqrt(variance);
                return Math.max(0, Math.min(100, Math.round(100 - (stdDev * 4.5))));
            }},
            calculateValueScore: (totalEarnings, events) => {{
                if (events === 0) return 0;
                const avg = totalEarnings / events;
                return Math.max(0, Math.min(100, Math.round((avg / 1500000) * 100)));
            }},
            processRawData: (tournaments) => {{
                const playersMap = {{}};
                tournaments.forEach(t => {{
                    t.leaderboard.forEach(entry => {{
                        const name = entry.player;
                        if (!playersMap[name]) {{
                            playersMap[name] = {{
                                id: Math.random().toString(36).substr(2, 9),
                                name,
                                country: entry.country || 'N/A',
                                wgr_rank: entry.wgr_rank || 999,
                                total_earnings: 0,
                                tournaments_played: 0,
                                wins: 0,
                                purse_dist: {{ "Major": 0, "Premium": 0, "Standard": 0 }},
                                history: []
                            }};
                        }}
                        const p = playersMap[name];
                        p.total_earnings += entry.earnings;
                        p.tournaments_played += 1;
                        if (entry.finish === 1) p.wins += 1;
                        p.purse_dist[t.type || 'Standard'] = (p.purse_dist[t.type || 'Standard'] || 0) + 1;
                        p.wgr_rank = Math.min(p.wgr_rank, entry.wgr_rank || 999);
                        p.history.push({{
                            tournament: t.tournament,
                            date: t.date,
                            finish: entry.finish,
                            earnings: entry.earnings,
                            type: t.type || 'Standard'
                        }});
                    }});
                }});
                return Object.values(playersMap).map(p => {{
                    p.history.sort((a, b) => new Date(b.date) - new Date(a.date));
                    p.stability = AnalyticsEngine.calculateStability(p.history);
                    p.value_score = AnalyticsEngine.calculateValueScore(p.total_earnings, p.tournaments_played);
                    p.top_10s = p.history.filter(h => h.finish <= 10).length;
                    return p;
                }}).sort((a, b) => b.total_earnings - a.total_earnings);
            }}
        }};

        // --- UI COMPONENTS ---
        const App = () => {{
            const [view, setView] = useState('dashboard');
            const [players, setPlayers] = useState([]);
            const [searchTerm, setSearchTerm] = useState('');
            const [selectedPlayer, setSelectedPlayer] = useState(null);

            useEffect(() => {{
                setPlayers(AnalyticsEngine.processRawData(RAW_DATA));
            }}, []);

            const filtered = players.filter(p => p.name.toLowerCase().includes(searchTerm.toLowerCase()));

            return (
                <div className="min-h-screen p-8">
                    <header className="flex justify-between items-center mb-12">
                        <div className="flex items-center gap-3">
                            <div className="bg-emerald-600 p-2 rounded-xl text-white">
                                <Icon name="target" />
                            </div>
                            <h1 className="text-3xl font-black tracking-tighter">TOURAX <span className="text-emerald-600">GOLF</span></h1>
                        </div>
                        <input 
                            className="bg-gray-100 px-6 py-3 rounded-2xl w-80 outline-none focus:ring-2 focus:ring-emerald-500"
                            placeholder="Search players..."
                            onChange={{(e) => setSearchTerm(e.target.value)}}
                        />
                    </header>

                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {{filtered.map(p => (
                            <div key={{p.id}} className="bg-white border p-8 rounded-[40px] shadow-sm hover:shadow-xl transition-all cursor-pointer" onClick={{() => setSelectedPlayer(p)}}>
                                <div className="flex gap-4 mb-6">
                                    <div className="w-14 h-14 bg-gray-900 rounded-2xl flex items-center justify-center text-white font-black text-xl">
                                        {{p.name[0]}}
                                    </div>
                                    <div>
                                        <h3 className="font-black text-lg text-gray-900">{{p.name}}</h3>
                                        <p className="text-xs font-bold text-emerald-600 uppercase tracking-widest">Rank #{{p.wgr_rank}}</p>
                                    </div>
                                </div>
                                <div className="grid grid-cols-2 gap-4">
                                    <div className="bg-gray-50 p-4 rounded-2xl">
                                        <p className="text-[10px] font-black text-gray-400 uppercase">Stability</p>
                                        <p className="text-xl font-black text-gray-900">{{p.stability}}%</p>
                                    </div>
                                    <div className="bg-gray-50 p-4 rounded-2xl">
                                        <p className="text-[10px] font-black text-gray-400 uppercase">Valuation</p>
                                        <p className="text-xl font-black text-emerald-600">{{p.value_score}}</p>
                                    </div>
                                </div>
                            </div>
                        ))}}
                    </div>

                    {{selectedPlayer && (
                        <div className="fixed inset-0 bg-black/60 backdrop-blur-md z-50 flex items-center justify-center p-4">
                            <div className="bg-white w-full max-w-4xl rounded-[48px] overflow-hidden flex h-[80vh] animate-in">
                                <div className="w-80 bg-gray-900 text-white p-10 flex flex-col justify-between">
                                    <div>
                                        <button onClick={{() => setSelectedPlayer(null)}} className="mb-8 p-2 bg-white/10 rounded-xl hover:bg-white/20">
                                            <Icon name="chevron-left" />
                                        </button>
                                        <h2 className="text-4xl font-black tracking-tighter mb-2 leading-tight">{{selectedPlayer.name}}</h2>
                                        <p className="text-emerald-400 font-black text-xs uppercase tracking-widest">{{selectedPlayer.country}}</p>
                                    </div>
                                    <div className="bg-white/5 p-6 rounded-3xl border border-white/10">
                                        <p className="text-[10px] font-black text-gray-500 uppercase mb-2">Total Earnings</p>
                                        <p className="text-2xl font-black">${{(selectedPlayer.total_earnings/1000000).toFixed(1)}}M</p>
                                    </div>
                                </div>
                                <div className="flex-grow p-10 overflow-y-auto">
                                    <h3 className="text-xl font-black mb-6">Transaction History</h3>
                                    <div className="space-y-3">
                                        {{selectedPlayer.history.map((h, i) => (
                                            <div key={{i}} className="flex items-center justify-between p-6 bg-gray-50 rounded-[32px] border">
                                                <div className="flex items-center gap-4">
                                                    <div className="w-10 h-10 bg-white border rounded-xl flex items-center justify-center font-black text-sm text-gray-400">
                                                        {{h.finish}}
                                                    </div>
                                                    <div>
                                                        <p className="font-black text-gray-900">{{h.tournament}}</p>
                                                        <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">{{h.date}}</p>
                                                    </div>
                                                </div>
                                                <p className="font-black text-lg text-emerald-600">${{(h.earnings/1000).toLocaleString()}}K</p>
                                            </div>
                                        ))}}
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}}
                </div>
            );
        }};

        const root = ReactDOM.createRoot(document.getElementById('root'));
        root.render(<App />);
    </script>
</body>
</html>
"""

# Render the application in Streamlit
if not raw_tournaments:
    st.warning("⚠️ No data found. Please ensure your JSON files are in the 'golf-otd' folder.")
else:
    components.html(html_content, height=1000, scrolling=True)
