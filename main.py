from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from bson import ObjectId
from datetime import datetime

# Local database import
from database import db, users_collection, tournaments_collection

app = FastAPI(title="Apex Battle Esports API")

# Enable CORS for Flutter Web & Mobile
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
    username: str | None = None
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
    game_mode: str = Field(default="SOLO")
    map_name: str = Field(default="Bermuda")
    entry_fee: int = Field(default=15, ge=0)
    prize_pool: int = Field(default=520, ge=0)
    max_slots: int = Field(default=50, ge=2, le=100)
    match_time: str = Field(default="10:00 AM")

class TournamentRegistration(BaseModel):
    tournament_id: str
    user_id: str
    utr: str

class RoomCredentialsUpdate(BaseModel):
    tournament_id: str
    room_id: str
    room_password: str

# ---------------------------------------------------------------------------
# 2. CORE & HEALTH ENDPOINTS
# ---------------------------------------------------------------------------
@app.get("/")
def read_root():
    return {"status": "online", "message": "Apex Battle Tournament API is Running!"}

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
# 3. AUTHENTICATION & SINGLE-PROFILE ROUTES (Diary Note Structure)
# ---------------------------------------------------------------------------
@app.post("/api/auth/register")
def register_account(user: UserAuth):
    existing = users_collection.find_one({"email": user.email})
    if existing:
        raise HTTPException(status_code=400, detail="Account pehle se bana hua hai!")

    # 5-digit formatted serial App ID auto generate
    total_users = users_collection.count_documents({}) + 1
    app_serial_id = str(total_users).zfill(5)

    new_user = {
        "app_serial_id": app_serial_id,
        "email": user.email,
        "password": user.password,
        "username": user.username or f"Player_{app_serial_id}",
        "game_uid": "Not Set",
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
    user_db = users_collection.find_one({"email": user.email, "password": user.password})
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
        user_name = payload.username or user_email.split("@")[0]

        # 1. MongoDB me check karo user pehle se hai ya nahi
        user = users_collection.find_one({"email": user_email})

        if not user:
            # 2. Agar bilkul naya user hai, standard schema ke sath MongoDB me register karo
            total_users = users_collection.count_documents({}) + 1
            app_serial_id = str(total_users).zfill(5)

            new_user = {
                "app_serial_id": app_serial_id,
                "email": user_email,
                "password": "",  # Google OAuth users ke liye raw password empty
                "auth_type": "google",
                "username": user_name,
                "game_uid": "Not Set",
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
        else:
            # 3. Existing user ki actual MongoDB details
            user_id = str(user["_id"])
            user_name = user.get("username", user_name)

        # 4. Success response Flutter ke liye
        return {
            "status": "success",
            "message": "Google authentication successful",
            "user_id": user_id,
            "email": user_email,
            "username": user_name,
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
# 4. TOURNAMENT ENGINE & AUTO-COPY REGISTRATION (Shortcut Flow)
# ---------------------------------------------------------------------------
@app.post("/api/tournaments/create")
def create_tournament(tourney: TournamentCreate):
    record = {
        "title": tourney.title,
        "game_mode": tourney.game_mode,
        "map_name": tourney.map_name,
        "entry_fee": tourney.entry_fee,
        "prize_pool": tourney.prize_pool,
        "max_slots": tourney.max_slots,
        "slots_booked": 0,
        "registered_teams": [],
        "match_time": tourney.match_time,
        "status": "UPCOMING",
        "room_id": "",
        "room_password": ""
    }
    res = tournaments_collection.insert_one(record)
    return {"status": "success", "tournament_id": str(res.inserted_id)}

@app.get("/api/tournaments")
def get_all_tournaments():
    tournaments = []
    for doc in tournaments_collection.find({}):
        tournaments.append({
            "id": str(doc["_id"]),
            "title": doc.get("title", "APEX SOLO BR"),
            "game_mode": doc.get("game_mode", "SOLO"),
            "map_name": doc.get("map_name", "Bermuda"),
            "entry_fee": doc.get("entry_fee", 15),
            "prize_pool": doc.get("prize_pool", 520),
            "max_slots": doc.get("max_slots", 50),
            "slots_booked": doc.get("slots_booked", 0),
            "match_time": doc.get("match_time", ""),
            "status": doc.get("status", "UPCOMING")
        })
    return {"tournaments": tournaments}

@app.post("/api/tournament/register")
def register_tournament_slot(reg: TournamentRegistration):
    try:
        u_oid = ObjectId(reg.user_id)
        t_oid = ObjectId(reg.tournament_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID format.")

    # 1. User profile se saara data auto-fetch karo
    user = users_collection.find_one({"_id": u_oid})
    if not user:
        raise HTTPException(status_code=404, detail="Player profile nahi mili!")

    # 2. Check tournament & slot availability
    tourney = tournaments_collection.find_one({"_id": t_oid})
    if not tourney:
        raise HTTPException(status_code=404, detail="Tournament nahi mila!")

    slots_booked = tourney.get("slots_booked", 0)
    slots_total = tourney.get("max_slots", 50)

    if slots_booked >= slots_total:
        raise HTTPException(status_code=400, detail="Lobby full ho chuki hai!")

    # Prevent duplicate entry in same room
    for participant in tourney.get("registered_teams", []):
        if participant.get("user_id") == str(u_oid):
            raise HTTPException(status_code=400, detail="Aap pehle se is match me register hain!")

    # 3. Next auto-slot calculate karo
    allotted_slot = slots_booked + 1

    # 4. Complete auto-bind snapshot (Diary Note requirement)
    slot_entry = {
        "slot_number": allotted_slot,
        "user_id": str(u_oid),
        "app_serial_id": user.get("app_serial_id", "00001"),
        "username": user.get("username", "Player"),
        "game_uid": user.get("game_uid", "Not Set"),
        "payout_upi": user.get("bank_details", {}).get("upi_id", "Not Set"),
        "utr": reg.utr,
        "registered_at": datetime.utcnow().isoformat()
    }

    # 5. Atomic push & increment
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
# 5. ROOM CREDENTIALS (Admin Update & User 15-Min Safe Fetch)
# ---------------------------------------------------------------------------
@app.post("/api/tournaments/set-room")
def set_room_credentials(payload: RoomCredentialsUpdate):
    try:
        t_oid = ObjectId(payload.tournament_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid Tournament ID.")

    tournaments_collection.update_one(
        {"_id": t_oid},
        {"$set": {
            "room_id": payload.room_id,
            "room_password": payload.room_password,
            "status": "LIVE"
        }}
    )
    return {"status": "success", "message": "Room details published."}

@app.get("/api/tournaments/{tournament_id}/room")
def get_room_details(tournament_id: str, user_id: str):
    try:
        t_oid = ObjectId(tournament_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID.")

    tourney = tournaments_collection.find_one({"_id": t_oid})
    if not tourney:
        raise HTTPException(status_code=404, detail="Tournament nahi mila!")

    # Check if user is in registered_teams
    registered = any(team.get("user_id") == user_id for team in tourney.get("registered_teams", []))
    if not registered:
        return {"status": "locked", "message": "Pehle match register karein tabhi Room ID unlock hogi."}

    return {
        "status": "unlocked",
        "room_id": tourney.get("room_id") or "Not ready",
        "room_password": tourney.get("room_password") or "Not ready"
    }
