import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from bson import ObjectId
from datetime import datetime
from typing import Optional

# Local database import
from database import db, users_collection, tournaments_collection

app = FastAPI(title="Apex Battle Esports API")

# Enable CORS for Flutter Web & Mobile & Admin Dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# 1. PYDANTIC SCHEMAS
# ---------------------------------------------------------------------------
class UserAuth(BaseModel):
    email: str
    password: str
    username: str | None = None

class GoogleAuthRequest(BaseModel):
    email: str
    game_uid: str
    password: str
    username: str | None = None
    avatar: str | None = None
    id_token: str | None = None

class BankDetailsUpdate(BaseModel):
    user_id: str
    upi_id: str
    account_number: str = ""
    ifsc_code: str = ""

class GameUidUpdate(BaseModel):
    user_id: str
    game_uid: str

class SocialsUpdate(BaseModel):
    user_id: str
    youtube: str = ""
    instagram: str = ""

class TournamentCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=50)
    mode: str = Field(default="SOLO")
    game_mode: str = Field(default="SOLO")
    map_name: str = Field(default="Bermuda")
    room_code: str = Field(default="ROOM-101")
    entry_fee: int = Field(default=19, ge=0)
    prize_pool: int = Field(default=349, ge=0)
    slots_total: Optional[int] = None
    max_slots: Optional[int] = None
    match_time: str = Field(default="")

class TournamentRegistration(BaseModel):
    tournament_id: str
    user_id: str
    utr: str
    slot_number: Optional[int] = None

class RoomCredentialsUpdate(BaseModel):
    tournament_id: Optional[str] = None
    room_id: str
    room_password: str

class HackerReportCreate(BaseModel):
    reporter_id: str = ""
    app_serial_id: str = "00001"
    target_uid: str
    room_code: str
    reason: str = ""

# ---------------------------------------------------------------------------
# 2. CORE, HEALTH & ADMIN DASHBOARD HOSTING
# ---------------------------------------------------------------------------
@app.get("/")
def read_root():
    return {"status": "online", "message": "Apex Battle Tournament API is Running!"}

@app.get("/admin", response_class=HTMLResponse)
async def serve_admin_panel():
    file_path = os.path.join(os.path.dirname(__file__), "admin.html")
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), status_code=200)
    return HTMLResponse(
        content="<h2>admin.html file nahi mili! File ko main.py ke bagal me rakhein.</h2>",
        status_code=404
    )

@app.get("/api/test-db")
def test_db():
    user_count = users_collection.count_documents({})
    tourney_count = tournaments_collection.count_documents({})
    return {
        "database_status": "connected",
        "total_users": user_count,
        "total_tournaments": tourney_count
    }

# ---------------------------------------------------------------------------
# 3. AUTHENTICATION & PROFILE ROUTES
# ---------------------------------------------------------------------------
@app.post("/api/auth/register")
def register_account(user: UserAuth):
    existing = users_collection.find_one({"email": user.email.lower().strip()})
    if existing:
        raise HTTPException(status_code=400, detail="Account pehle se bana hua hai!")

    total_users = users_collection.count_documents({}) + 1
    app_serial_id = str(total_users).zfill(5)

    new_user = {
        "app_serial_id": app_serial_id,
        "email": user.email.lower().strip(),
        "password": user.password,
        "username": user.username or f"Player_{app_serial_id}",
        "game_uid": "Not Set",
        "auth_type": "standard",
        "avatar": "",
        "bank_details": {
            "payout_type": "UPI",
            "upi_id": "Not Set",
            "account_number": "Not Set",
            "ifsc_code": "Not Set"
        },
        "socials": {
            "youtube": "@ApexBattle",
            "instagram": "@apex_player"
        },
        "wallet_balance": 100,
        "total_earned": 0,
        "created_at": datetime.utcnow().isoformat()
    }
    res = users_collection.insert_one(new_user)
    return {
        "status": "success",
        "message": "Account successfully created!",
        "user_id": str(res.inserted_id),
        "app_serial_id": app_serial_id
    }

@app.post("/api/auth/login")
def login_account(user: UserAuth):
    user_email = user.email.lower().strip()
    user_db = users_collection.find_one({"email": user_email, "password": user.password})
    if not user_db:
        raise HTTPException(status_code=401, detail="Galat Email ya Password!")

    user_db["_id"] = str(user_db["_id"])
    user_db.pop("password", None)
    return {
        "status": "success",
        "message": "Login successful",
        "user": user_db
    }

@app.post("/api/auth/google")
def google_auth(payload: GoogleAuthRequest):
    try:
        user_email = payload.email.lower().strip()
        user_pwd = payload.password.strip()
        incoming_uid = payload.game_uid.strip()

        if not user_pwd or not incoming_uid:
            raise HTTPException(status_code=400, detail="UID aur Password dono compulsory hain!")

        user_name = payload.username or user_email.split("@")[0]
        user = users_collection.find_one({"email": user_email})

        if not user:
            total_users = users_collection.count_documents({}) + 1
            app_serial_id = str(total_users).zfill(5)

            new_user = {
                "app_serial_id": app_serial_id,
                "email": user_email,
                "password": user_pwd,
                "auth_type": "google_hybrid",
                "username": user_name,
                "game_uid": incoming_uid,
                "avatar": payload.avatar or "",
                "bank_details": {
                    "payout_type": "UPI",
                    "upi_id": "Not Set",
                    "account_number": "Not Set",
                    "ifsc_code": "Not Set"
                },
                "socials": {
                    "youtube": "@ApexBattle",
                    "instagram": "@apex_player"
                },
                "wallet_balance": 100,
                "total_earned": 0,
                "created_at": datetime.utcnow().isoformat()
            }
            res = users_collection.insert_one(new_user)
            if not res.inserted_id:
                raise HTTPException(status_code=500, detail="Database insertion failed!")

            user_id = str(res.inserted_id)
            current_app_serial = app_serial_id
            current_game_uid = incoming_uid
        else:
            user_id = str(user["_id"])
            current_app_serial = user.get("app_serial_id", "00001")
            
            update_data = {"password": user_pwd}
            if incoming_uid and incoming_uid != "Not Set":
                update_data["game_uid"] = incoming_uid
                current_game_uid = incoming_uid
            else:
                current_game_uid = user.get("game_uid", "Not Set")

            users_collection.update_one({"_id": user["_id"]}, {"$set": update_data})
            user_name = user.get("username", user_name)

        return {
            "status": "success",
            "message": "User registered in MongoDB with Password & UID",
            "user_id": user_id,
            "email": user_email,
            "username": user_name,
            "game_uid": current_game_uid,
            "app_serial_id": current_app_serial,
            "token": f"bearer_{user_id}"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.get("/api/user/profile/{user_id}")
def fetch_user_profile(user_id: str):
    try:
        user = users_collection.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise HTTPException(status_code=404, detail="User nahi mila")
        user["_id"] = str(user["_id"])
        user.pop("password", None)
        return user
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/user/update-bank")
def update_bank(data: BankDetailsUpdate):
    try:
        users_collection.update_one(
            {"_id": ObjectId(data.user_id)},
            {"$set": {
                "bank_details.upi_id": data.upi_id,
                "bank_details.account_number": data.account_number,
                "bank_details.ifsc_code": data.ifsc_code
            }}
        )
        return {"status": "success", "message": "Bank details updated!"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/user/update-game-uid")
def update_game_uid(data: GameUidUpdate):
    try:
        users_collection.update_one(
            {"_id": ObjectId(data.user_id)},
            {"$set": {"game_uid": data.game_uid}}
        )
        return {"status": "success", "message": "Game UID updated!"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/user/update-socials")
def update_socials(data: SocialsUpdate):
    try:
        users_collection.update_one(
            {"_id": ObjectId(data.user_id)},
            {"$set": {
                "socials.youtube": data.youtube,
                "socials.instagram": data.instagram
            }}
        )
        return {"status": "success", "message": "Social handles updated!"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ---------------------------------------------------------------------------
# 4. TOURNAMENT ENGINE (FLUTTER + ADMIN DUAL ROUTING)
# ---------------------------------------------------------------------------
def _process_create_tournament(tourney: TournamentCreate):
    mode_val = (tourney.mode or tourney.game_mode or "SOLO").upper()
    
    if tourney.slots_total:
        slots = tourney.slots_total
    elif tourney.max_slots:
        slots = tourney.max_slots
    else:
        slots = 12 if mode_val == "SQUAD" else (24 if mode_val == "DUO" else (8 if mode_val == "CS" else 48))

    match_time_val = tourney.match_time
    if not match_time_val:
        match_time_val = datetime.utcnow().isoformat()

    record = {
        "title": tourney.title,
        "mode": mode_val,
        "game_mode": mode_val,
        "map_name": tourney.map_name,
        "room_code": tourney.room_code.upper() if tourney.room_code else "ROOM-101",
        "entry_fee": tourney.entry_fee,
        "prize_pool": tourney.prize_pool,
        "slots_total": slots,
        "max_slots": slots,
        "slots_booked": 0,
        "registered_teams": [],
        "match_time": match_time_val,
        "status": "UPCOMING",
        "room_id": "TBD",
        "room_password": "TBD",
        "created_at": datetime.utcnow().isoformat()
    }
    res = tournaments_collection.insert_one(record)
    return {"status": "success", "tournament_id": str(res.inserted_id), "id": str(res.inserted_id)}

# Supports /api/tournaments/create, /api/tournament/create & /api/admin/tournament/create
@app.post("/api/tournaments/create")
@app.post("/api/tournament/create")
@app.post("/api/admin/tournament/create")
def create_tournament_endpoint(tourney: TournamentCreate):
    return _process_create_tournament(tourney)

@app.get("/api/tournaments")
def get_all_tournaments(user_id: str | None = Query(None)):
    tournaments = []
    for doc in tournaments_collection.find({}):
        user_registration = None
        if user_id:
            for team in doc.get("registered_teams", []):
                if str(team.get("user_id")) == str(user_id):
                    user_registration = team
                    break

        mode_name = (doc.get("mode") or doc.get("game_mode") or "SOLO").upper()
        total_slots = doc.get("slots_total") or doc.get("max_slots") or 48

        tournaments.append({
            "id": str(doc["_id"]),
            "_id": str(doc["_id"]),
            "room_code": doc.get("room_code", "ROOM-101"),
            "roomCode": doc.get("room_code", "ROOM-101"),
            "title": doc.get("title", f"APEX {mode_name} BATTLE"),
            "mode": mode_name,
            "game_mode": mode_name,
            "map_name": doc.get("map_name", "Bermuda"),
            "entry_fee": doc.get("entry_fee", 19),
            "prize_pool": doc.get("prize_pool", 349),
            "slots_total": total_slots,
            "max_slots": total_slots,
            "slots_booked": doc.get("slots_booked", 0),
            "registered_teams": doc.get("registered_teams", []),
            "match_time": doc.get("match_time", ""),
            "status": doc.get("status", "UPCOMING"),
            "room_id": doc.get("room_id", "TBD"),
            "room_password": doc.get("room_password", "TBD"),
            "is_registered": user_registration is not None,
            "my_slot": user_registration.get("slot_number") if user_registration else None
        })
    return {"status": "success", "tournaments": tournaments}

@app.post("/api/tournament/register")
def register_tournament_slot(reg: TournamentRegistration):
    try:
        u_oid = ObjectId(reg.user_id)
        t_oid = ObjectId(reg.tournament_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID format.")

    user = users_collection.find_one({"_id": u_oid})
    if not user:
        raise HTTPException(status_code=404, detail="Player profile nahi mili!")

    tourney = tournaments_collection.find_one({"_id": t_oid})
    if not tourney:
        raise HTTPException(status_code=404, detail="Tournament nahi mila!")

    slots_booked = tourney.get("slots_booked", 0)
    slots_total = tourney.get("slots_total") or tourney.get("max_slots") or 48

    if slots_booked >= slots_total:
        raise HTTPException(status_code=400, detail="Lobby full ho chuki hai!")

    for participant in tourney.get("registered_teams", []):
        if participant.get("user_id") == str(u_oid):
            raise HTTPException(status_code=400, detail="Aap pehle se is match me register hain!")

    allotted_slot = reg.slot_number if reg.slot_number else (slots_booked + 1)

    slot_entry = {
        "slot_number": allotted_slot,
        "user_id": str(u_oid),
        "app_serial_id": user.get("app_serial_id", "00001"),
        "username": user.get("username", "Player"),
        "game_uid": user.get("game_uid", "Not Set"),
        "payout_upi": user.get("bank_details", {}).get("upi_id", "Not Set"),
        "utr": reg.utr,
        "verified": True,
        "registered_at": datetime.utcnow().isoformat()
    }

    tournaments_collection.update_one(
        {"_id": t_oid},
        {
            "$inc": {"slots_booked": 1},
            "$push": {"registered_teams": slot_entry}
        }
    )

    return {
        "status": "success",
        "message": f"Slot #{allotted_slot} booked successfully!",
        "allottedSlot": allotted_slot
    }

# ---------------------------------------------------------------------------
# 5. ROOM CREDENTIALS (ADMIN SET & APP UNLOCK)
# ---------------------------------------------------------------------------
def _process_set_room(t_id_str: str, room_id: str, room_password: str):
    try:
        t_oid = ObjectId(t_id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid Tournament ID.")

    res = tournaments_collection.update_one(
        {"_id": t_oid},
        {"$set": {
            "room_id": room_id,
            "room_password": room_password,
            "status": "UNLOCKED"
        }}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Match not found")

    return {"status": "success", "message": "Room ID & Pass broadcasted to all players!"}

@app.post("/api/tournaments/set-room")
@app.put("/api/admin/room-credentials")
def set_room_credentials_endpoint(payload: RoomCredentialsUpdate):
    if not payload.tournament_id:
        raise HTTPException(status_code=400, detail="Tournament ID is required.")
    return _process_set_room(payload.tournament_id, payload.room_id, payload.room_password)

@app.post("/api/tournament/{tournament_id}/room")
def set_room_by_path(tournament_id: str, payload: RoomCredentialsUpdate):
    return _process_set_room(tournament_id, payload.room_id, payload.room_password)

@app.get("/api/tournaments/{tournament_id}/room")
def get_room_details(tournament_id: str, user_id: str):
    try:
        t_oid = ObjectId(tournament_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID.")

    tourney = tournaments_collection.find_one({"_id": t_oid})
    if not tourney:
        raise HTTPException(status_code=404, detail="Tournament nahi mila!")

    registered = any(str(team.get("user_id")) == str(user_id) for team in tourney.get("registered_teams", []))
    if not registered:
        return {"status": "locked", "message": "Pehle match register karein tabhi Room ID unlock hogi."}

    room_id = tourney.get("room_id")
    room_pass = tourney.get("room_password")

    if tourney.get("status") in ["UNLOCKED", "LIVE"] and room_id and room_id != "TBD":
        return {
            "status": "unlocked",
            "room_id": room_id,
            "room_password": room_pass
        }

    return {
        "status": "locked",
        "message": "Room password match se 15m pehle show hoga."
    }

# ---------------------------------------------------------------------------
# 6. ANTI-CHEAT / HACKER REPORT ENDPOINT
# ---------------------------------------------------------------------------
@app.post("/api/anti-cheat/report")
def submit_hacker_report(report: HackerReportCreate):
    report_doc = {
        "reporter_id": report.reporter_id,
        "app_serial_id": report.app_serial_id,
        "target_uid": report.target_uid,
        "room_code": report.room_code,
        "reason": report.reason,
        "status": "UNDER_REVIEW",
        "created_at": datetime.utcnow().isoformat()
    }
    db["hacker_reports"].insert_one(report_doc)
    return {"status": "success", "message": "Report logged for hardware review."}
