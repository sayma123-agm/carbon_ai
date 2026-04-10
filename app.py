from flask import Flask, render_template, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import math, uuid, json, random

app = Flask(__name__)
app.secret_key = 'ecotrace-gps-2026'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///ecotrace.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ─── MODELS ──────────────────────────────────────────────────────────────────
class GPSLog(db.Model):
    id       = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id  = db.Column(db.String(36))
    lat      = db.Column(db.Float)
    lng      = db.Column(db.Float)
    speed    = db.Column(db.Float, default=0)       # km/h
    mode     = db.Column(db.String(30))             # auto-detected transport mode
    co2_kg   = db.Column(db.Float, default=0)
    distance = db.Column(db.Float, default=0)       # km
    place    = db.Column(db.String(100))
    ts       = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id, 'lat': self.lat, 'lng': self.lng,
            'speed': self.speed, 'mode': self.mode, 'co2_kg': self.co2_kg,
            'distance': self.distance, 'place': self.place,
            'ts': self.ts.strftime('%H:%M'), 'date': self.ts.strftime('%Y-%m-%d')
        }

# ─── KAGGLE-INSPIRED BENGALURU GPS DATASET ───────────────────────────────────
# Based on real Bengaluru mobility dataset patterns (Kaggle: Bengaluru Urban Mobility)
# GPS traces for a typical IT professional commute

BENGALURU_PLACES = {
    # (lat, lng, place_name, area_type)
    "home_koramangala":   (12.9352, 77.6245, "Koramangala 4th Block", "residential"),
    "home_hsr":           (12.9121, 77.6446, "HSR Layout Sector 2",   "residential"),
    "home_whitefield":    (12.9698, 77.7499, "Whitefield",            "residential"),
    "home_jp_nagar":      (12.9063, 77.5857, "JP Nagar 6th Phase",    "residential"),
    "office_ecospace":    (12.9352, 77.6870, "Ecospace Tech Park",     "office"),
    "office_manyata":     (13.0464, 77.6194, "Manyata Tech Park",      "office"),
    "office_ubs":         (12.9270, 77.6740, "UB City Office",         "office"),
    "office_electronic":  (12.9698, 77.7499, "Electronics City",       "office"),
    "gym_koramangala":    (12.9340, 77.6270, "Cult.fit Koramangala",   "gym"),
    "cafe_indiranagar":   (12.9784, 77.6408, "Indiranagar Coffee",     "leisure"),
    "mall_forum":         (12.9214, 77.6070, "Forum Mall Koramangala", "shopping"),
    "metro_majestic":     (12.9767, 77.5713, "KSR City Station",       "transit"),
    "restaurant_mg_road": (12.9719, 77.6094, "MG Road Restaurant",     "food"),
    "hospital_fortis":    (12.9254, 77.5951, "Fortis Hospital",        "medical"),
    "park_cubbon":        (12.9763, 77.5929, "Cubbon Park",            "leisure"),
}

# 5 dummy users with full-day GPS traces (Kaggle dataset simulation)
DUMMY_USERS = {
    "usr_arjun": {
        "name": "Arjun Sharma", "age": 28, "city": "Bengaluru", "avatar": "👨‍💻",
        "profession": "Software Engineer", "company": "Infosys Ecospace",
        "preferred_mode": "car_petrol",
        "home": "home_koramangala", "office": "office_ecospace",
    },
    "usr_priya": {
        "name": "Priya Nair", "age": 31, "city": "Bengaluru", "avatar": "👩‍💼",
        "profession": "Product Manager", "company": "Manyata Tech Park",
        "preferred_mode": "metro_subway",
        "home": "home_hsr", "office": "office_manyata",
    },
    "usr_rahul": {
        "name": "Rahul Verma", "age": 25, "city": "Bengaluru", "avatar": "👨‍🎓",
        "profession": "Data Analyst", "company": "UB City",
        "preferred_mode": "motorcycle",
        "home": "home_jp_nagar", "office": "office_ubs",
    },
    "usr_sneha": {
        "name": "Sneha Reddy", "age": 34, "city": "Bengaluru", "avatar": "👩‍🔬",
        "profession": "ML Engineer", "company": "Electronics City",
        "preferred_mode": "bus",
        "home": "home_whitefield", "office": "office_electronic",
    },
    "usr_vikram": {
        "name": "Vikram Patel", "age": 29, "city": "Bengaluru", "avatar": "👨‍⚕️",
        "profession": "Consultant", "company": "Manyata Tech Park",
        "preferred_mode": "car_electric",
        "home": "home_hsr", "office": "office_manyata",
    },
}

# Transport mode emission factors & speed profiles (Kaggle: Urban Mobility CO2 Dataset)
TRANSPORT_MODES = {
    "walking":        {"factor": 0.000, "speed_range": (3,6),   "label": "Walking",     "icon": "🚶", "color": "#4ade80"},
    "bicycle":        {"factor": 0.000, "speed_range": (10,20), "label": "Cycling",     "icon": "🚲", "color": "#22c55e"},
    "bus":            {"factor": 0.089, "speed_range": (15,35), "label": "Bus",         "icon": "🚌", "color": "#2dd4bf"},
    "metro_subway":   {"factor": 0.028, "speed_range": (30,60), "label": "Metro",       "icon": "🚇", "color": "#818cf8"},
    "auto_rickshaw":  {"factor": 0.131, "speed_range": (20,35), "label": "Auto",        "icon": "🛺", "color": "#fb923c"},
    "motorcycle":     {"factor": 0.113, "speed_range": (30,55), "label": "Bike",        "icon": "🏍️", "color": "#fbbf24"},
    "car_petrol":     {"factor": 0.210, "speed_range": (20,60), "label": "Car (Petrol)","icon": "🚗", "color": "#f87171"},
    "car_diesel":     {"factor": 0.171, "speed_range": (20,60), "label": "Car (Diesel)","icon": "🚙", "color": "#fb7185"},
    "car_electric":   {"factor": 0.050, "speed_range": (25,65), "label": "EV",          "icon": "⚡", "color": "#a3e635"},
    "cab_ola_uber":   {"factor": 0.158, "speed_range": (20,50), "label": "Cab",         "icon": "🟡", "color": "#fde047"},
}

def haversine(lat1, lng1, lat2, lng2):
    R = 6371
    dlat = math.radians(lat2-lat1)
    dlng = math.radians(lng2-lng1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlng/2)**2
    return R * 2 * math.asin(math.sqrt(a))

def auto_detect_mode(speed_kmh):
    """Auto-detect transport mode from GPS speed (as real GPS trackers do)"""
    if speed_kmh < 2:   return "stationary"
    if speed_kmh < 7:   return "walking"
    if speed_kmh < 22:  return "bicycle"
    if speed_kmh < 40:  return "bus"
    return "car_petrol"

def interpolate_gps(lat1, lng1, lat2, lng2, steps=8):
    """Generate intermediate GPS points between two locations"""
    points = []
    for i in range(steps+1):
        t = i / steps
        noise_lat = random.gauss(0, 0.0002)
        noise_lng = random.gauss(0, 0.0002)
        points.append((
            lat1 + (lat2-lat1)*t + noise_lat,
            lng1 + (lng2-lng1)*t + noise_lng
        ))
    return points

def generate_daily_schedule(user_id, date=None):
    """Generate a full day GPS trace for a user — Kaggle dataset simulation"""
    if date is None:
        date = datetime.utcnow().date()

    user = DUMMY_USERS.get(user_id, DUMMY_USERS["usr_arjun"])
    home_key   = user["home"]
    office_key = user["office"]
    mode_key   = user["preferred_mode"]
    mode_info  = TRANSPORT_MODES[mode_key]

    home_data   = BENGALURU_PLACES[home_key]
    office_data = BENGALURU_PLACES[office_key]

    # Typical IT professional schedule in Bengaluru
    schedule = [
        # (hour, min, from_key, to_key, mode, activity_label)
        (6,  30, home_key,           home_key,          "walking",     "Morning walk/jog"),
        (8,  15, home_key,           office_key,        mode_key,      "Morning commute"),
        (13, 0,  office_key,         "restaurant_mg_road","walking",   "Lunch"),
        (13, 45, "restaurant_mg_road", office_key,      "walking",     "Back to office"),
        (18, 30, office_key,         home_key,          mode_key,      "Evening commute"),
        (19, 30, home_key,           "gym_koramangala", "walking",     "Gym"),
        (21, 0,  "gym_koramangala",  home_key,          "walking",     "Return home"),
    ]

    # Add weekend extras
    if date.weekday() >= 5:
        schedule.append((11, 0, home_key, "mall_forum", "cab_ola_uber", "Weekend outing"))
        schedule.append((14, 30, "mall_forum", "cafe_indiranagar", "car_petrol", "Cafe visit"))

    trips = []
    for hour, minute, from_k, to_k, seg_mode, label in schedule:
        if from_k == to_k and seg_mode == "walking":
            # Short walk near home
            from_lat, from_lng = BENGALURU_PLACES[from_k][0], BENGALURU_PLACES[from_k][1]
            to_lat = from_lat + random.uniform(0.003, 0.008)
            to_lng = from_lng + random.uniform(0.003, 0.008)
        else:
            from_lat, from_lng = BENGALURU_PLACES[from_k][0], BENGALURU_PLACES[from_k][1]
            to_lat, to_lng     = BENGALURU_PLACES[to_k][0],   BENGALURU_PLACES[to_k][1]

        dist = haversine(from_lat, from_lng, to_lat, to_lng)
        m_info = TRANSPORT_MODES.get(seg_mode, TRANSPORT_MODES["walking"])
        speed  = random.uniform(*m_info["speed_range"])
        co2    = dist * m_info["factor"]
        duration_min = max(int((dist / speed) * 60), 1)

        gps_points = interpolate_gps(from_lat, from_lng, to_lat, to_lng, steps=6)

        trips.append({
            "time":  f"{hour:02d}:{minute:02d}",
            "hour":  hour, "minute": minute,
            "from_place": BENGALURU_PLACES.get(from_k, ('','','Unknown',''))[2],
            "to_place":   BENGALURU_PLACES.get(to_k,   ('','','Unknown',''))[2],
            "mode":     seg_mode,
            "mode_label": m_info["label"],
            "mode_icon":  m_info["icon"],
            "mode_color": m_info["color"],
            "distance":   round(dist, 2),
            "speed":      round(speed, 1),
            "co2_kg":     round(co2, 4),
            "duration":   duration_min,
            "label":      label,
            "from_lat": from_lat, "from_lng": from_lng,
            "to_lat":   to_lat,   "to_lng":   to_lng,
            "gps_trace": [[p[0], p[1]] for p in gps_points]
        })

    return trips

def get_week_summary(user_id):
    """Generate 7-day summary for charts"""
    days = []
    for i in range(6, -1, -1):
        date = (datetime.utcnow() - timedelta(days=i)).date()
        trips = generate_daily_schedule(user_id, date)
        total_co2  = sum(t["co2_kg"] for t in trips)
        total_dist = sum(t["distance"] for t in trips)
        day_label  = date.strftime("%a")
        days.append({
            "day": day_label, "date": str(date),
            "co2": round(total_co2, 3),
            "distance": round(total_dist, 2),
            "trips": len(trips)
        })
    return days

def get_carbon_score(monthly_kg):
    if monthly_kg < 50:  return 96, "🌟 Excellent"
    if monthly_kg < 150: return 82, "✅ Good"
    if monthly_kg < 300: return 60, "⚠️ Average"
    if monthly_kg < 500: return 38, "🔴 High"
    return 15, "💀 Critical"

def get_mode_recommendations(trips):
    """AI engine: analyse trips and recommend mode switches"""
    recs = []
    car_trips = [t for t in trips if "car_petrol" in t["mode"] or "car_diesel" in t["mode"]]
    long_trips = [t for t in trips if t["distance"] > 8]
    walk_potential = [t for t in trips if 0.5 < t["distance"] < 2 and t["mode"] not in ["walking","bicycle"]]

    total_co2 = sum(t["co2_kg"] for t in trips)
    saved = 0

    if car_trips:
        save = sum(t["co2_kg"] for t in car_trips) * 0.87
        saved += save
        recs.append({
            "title": "Switch to Metro for Commute",
            "desc": f"Your {len(car_trips)} car trips today could use the Namma Metro. Metro emits 87% less CO₂ per km than petrol cars.",
            "saving": round(save, 3),
            "icon": "🚇", "priority": "high", "color": "#818cf8"
        })

    if long_trips:
        save = sum(t["co2_kg"] for t in long_trips) * 0.6
        saved += save
        recs.append({
            "title": "Carpool for Long Trips",
            "desc": f"Your {len(long_trips)} long-distance trips (>8km) are ideal for carpooling — splits your footprint by 2-4×.",
            "saving": round(save, 3),
            "icon": "🤝", "priority": "medium", "color": "#fbbf24"
        })

    if walk_potential:
        recs.append({
            "title": "Walk Short Distances",
            "desc": f"{len(walk_potential)} trips under 2km could be walked — zero emissions, free cardio.",
            "saving": round(sum(t["co2_kg"] for t in walk_potential), 3),
            "icon": "🚶", "priority": "low", "color": "#4ade80"
        })

    return recs, round(saved, 3)

# ─── ROUTES ──────────────────────────────────────────────────────────────────
@app.before_request
def ensure_session():
    if 'user_id' not in session:
        session['user_id'] = "usr_arjun"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/users')
def get_users():
    return jsonify({uid: {**u, 'id': uid} for uid, u in DUMMY_USERS.items()})

@app.route('/api/set_user/<user_id>')
def set_user(user_id):
    if user_id in DUMMY_USERS:
        session['user_id'] = user_id
    return jsonify({'ok': True, 'user': DUMMY_USERS.get(user_id)})

@app.route('/api/modes')
def get_modes():
    return jsonify(TRANSPORT_MODES)

@app.route('/api/gps/live')
def gps_live():
    """Simulate live GPS position (auto-advances through daily schedule)"""
    uid = session.get('user_id', 'usr_arjun')
    now = datetime.utcnow()
    hour = now.hour + now.minute/60
    trips = generate_daily_schedule(uid)

    current_trip = None
    for t in trips:
        t_hour = t["hour"] + t["minute"]/60
        t_end  = t_hour + t["duration"]/60
        if t_hour <= hour < t_end:
            frac = (hour - t_hour) / max((t_end - t_hour), 0.01)
            frac = min(max(frac, 0), 1)
            idx  = int(frac * (len(t["gps_trace"])-1))
            pt   = t["gps_trace"][idx]
            current_trip = {**t, "current_lat": pt[0], "current_lng": pt[1], "progress": round(frac*100)}
            break

    if not current_trip and trips:
        last = trips[-1]
        current_trip = {**last, "current_lat": last["to_lat"], "current_lng": last["to_lng"], "progress": 100}

    return jsonify(current_trip)

@app.route('/api/schedule')
def get_schedule():
    uid = session.get('user_id', 'usr_arjun')
    trips = generate_daily_schedule(uid)
    recs, total_saved = get_mode_recommendations(trips)

    total_co2  = sum(t["co2_kg"] for t in trips)
    total_dist = sum(t["distance"] for t in trips)
    score, score_label = get_carbon_score(total_co2 * 22)

    mode_breakdown = {}
    for t in trips:
        m = t["mode"]
        if m not in mode_breakdown:
            mode_breakdown[m] = {"co2": 0, "dist": 0, "trips": 0, "label": t["mode_label"], "icon": t["mode_icon"], "color": t["mode_color"]}
        mode_breakdown[m]["co2"]   += t["co2_kg"]
        mode_breakdown[m]["dist"]  += t["distance"]
        mode_breakdown[m]["trips"] += 1

    return jsonify({
        "user": DUMMY_USERS[uid],
        "trips": trips,
        "total_co2": round(total_co2, 4),
        "total_distance": round(total_dist, 2),
        "trip_count": len(trips),
        "mode_breakdown": mode_breakdown,
        "recommendations": recs,
        "total_saved": total_saved,
        "score": score,
        "score_label": score_label
    })

@app.route('/api/week')
def get_week():
    uid = session.get('user_id', 'usr_arjun')
    return jsonify(get_week_summary(uid))

@app.route('/api/set_mode', methods=['POST'])
def set_mode():
    """Change transport mode for commute — recalculate CO₂"""
    data = request.get_json()
    uid  = session.get('user_id', 'usr_arjun')
    new_mode = data.get('mode')
    if new_mode not in TRANSPORT_MODES:
        return jsonify({'error': 'invalid mode'}), 400
    DUMMY_USERS[uid]['preferred_mode'] = new_mode
    trips = generate_daily_schedule(uid)
    total_co2 = sum(t["co2_kg"] for t in trips)
    return jsonify({
        'ok': True, 'new_mode': new_mode,
        'new_total_co2': round(total_co2, 4),
        'mode_info': TRANSPORT_MODES[new_mode]
    })

@app.route('/api/compare_modes')
def compare_modes():
    """Show CO₂ for each possible mode for today's commute"""
    uid  = session.get('user_id', 'usr_arjun')
    user = DUMMY_USERS[uid]
    home_data   = BENGALURU_PLACES[user["home"]]
    office_data = BENGALURU_PLACES[user["office"]]
    dist = haversine(home_data[0], home_data[1], office_data[0], office_data[1])

    comparisons = []
    for mode_key, info in TRANSPORT_MODES.items():
        co2 = dist * info["factor"]
        comparisons.append({
            "mode": mode_key, "label": info["label"], "icon": info["icon"],
            "color": info["color"], "co2": round(co2, 4),
            "distance": round(dist, 2),
            "is_current": mode_key == user["preferred_mode"]
        })
    comparisons.sort(key=lambda x: x["co2"])
    return jsonify(comparisons)

@app.route('/api/gps/history')
def gps_history():
    """Return full day GPS trace for map rendering"""
    uid = session.get('user_id', 'usr_arjun')
    trips = generate_daily_schedule(uid)
    all_points = []
    for t in trips:
        for pt in t["gps_trace"]:
            all_points.append({"lat": pt[0], "lng": pt[1], "mode": t["mode"], "color": t["mode_color"]})
    return jsonify(all_points)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)