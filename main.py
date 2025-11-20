import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from bson import ObjectId

from database import db, create_document, get_documents

app = FastAPI(title="UniVerse API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Utilities ----------

def oid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id format")


def serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
    if doc is None:
        return doc
    d = dict(doc)
    if "_id" in d:
        d["id"] = str(d.pop("_id"))
    # Convert datetimes to isoformat
    for k, v in list(d.items()):
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d


def hash_password(password: str) -> str:
    import hashlib
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


ALLOWED_COLLECTIONS = {
    "beacons": "beacon",
    "resources": "resource",
    "tutors": "tutor",
    "clubs": "club",
    "events": "event",
    "lostfound": "lostfound",
    "market": "market",
}


# ---------- Models ----------

class SignupRequest(BaseModel):
    student_id: str
    name: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    identifier: str  # email or student_id
    password: str


class CreateItemRequest(BaseModel):
    title: str
    description: Optional[str] = None
    owner_id: Optional[str] = None
    owner_name: Optional[str] = None
    location: Optional[str] = None
    subject: Optional[str] = None
    price: Optional[float] = None
    condition: Optional[str] = None
    url: Optional[str] = None
    tags: Optional[List[str]] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    rate_per_hour: Optional[float] = None
    availability: Optional[str] = None
    status: Optional[str] = None


# ---------- Routes ----------

@app.get("/")
def root():
    return {"name": "UniVerse API", "status": "ok"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set",
        "database_name": "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            try:
                cols = db.list_collection_names()
                response["collections"] = cols
                response["database"] = "✅ Connected & Working"
                response["connection_status"] = "Connected"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response


# ----- Auth -----

@app.post("/signup")
def signup(payload: SignupRequest):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    existing = db["user"].find_one({"$or": [{"student_id": payload.student_id}, {"email": payload.email}]})
    if existing:
        raise HTTPException(status_code=400, detail="Account already exists")
    user_doc = {
        "student_id": payload.student_id,
        "name": payload.name,
        "email": payload.email,
        "password_hash": hash_password(payload.password),
        "avatar_url": None,
        "bio": None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    result = db["user"].insert_one(user_doc)
    return {"id": str(result.inserted_id), "message": "Signup successful"}


@app.post("/login")
def login(payload: LoginRequest):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    user = db["user"].find_one({
        "$or": [
            {"email": payload.identifier},
            {"student_id": payload.identifier}
        ]
    })
    if not user or user.get("password_hash") != hash_password(payload.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = str(uuid4())
    session_doc = {
        "user_id": str(user.get("_id")),
        "token": token,
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(days=7)
    }
    db["session"].insert_one(session_doc)
    return {"token": token, "user": serialize(user)}


# ----- Data fetch endpoints -----

def build_filter(q: Optional[str], location: Optional[str], subject: Optional[str]) -> Dict[str, Any]:
    f: Dict[str, Any] = {}
    if q:
        f["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
            {"description": {"$regex": q, "$options": "i"}},
        ]
    if location:
        f["location"] = {"$regex": location, "$options": "i"}
    if subject:
        f["subject"] = {"$regex": subject, "$options": "i"}
    return f


@app.get("/beacons")
@app.get("/resources")
@app.get("/tutors")
@app.get("/clubs")
@app.get("/events")
@app.get("/lostfound")
@app.get("/market")
def list_items(
    q: Optional[str] = Query(default=None),
    location: Optional[str] = Query(default=None),
    subject: Optional[str] = Query(default=None),
):
    # Determine which path was called
    path = "events"  # default for type checker
    # Using request scope via dependency isn't necessary; FastAPI provides app.router
    # We'll infer from function name via app.router after startup isn't straightforward here,
    # easier approach: this handler will be mounted for each route and FastAPI stores the matched path in request.
    from fastapi import Request

    async def inner(request: Request):
        endpoint_name = request.url.path.strip("/") or ""
        if endpoint_name not in ALLOWED_COLLECTIONS:
            raise HTTPException(status_code=404, detail="Unknown endpoint")
        collection = ALLOWED_COLLECTIONS[endpoint_name]
        filt = build_filter(q, location, subject)
        items = db[collection].find(filt).sort("created_at", -1)
        return [serialize(doc) for doc in items]

    # FastAPI will call inner with the Request
    # However, since we're not in async path, convert to ASGI via dependency. Simpler: re-declare below routes explicitly.
    return {"detail": "Improper call"}


# Re-declare explicit list endpoints to avoid request injection complexity
@app.get("/beacons", tags=["academic"], summary="List academic beacons")
def list_beacons(q: Optional[str] = None, location: Optional[str] = None, subject: Optional[str] = None):
    filt = build_filter(q, location, subject)
    items = db["beacon"].find(filt).sort("created_at", -1)
    return [serialize(x) for x in items]


@app.get("/resources", tags=["academic"], summary="List study resources")
def list_resources(q: Optional[str] = None, location: Optional[str] = None, subject: Optional[str] = None):
    filt = build_filter(q, location, subject)
    items = db["resource"].find(filt).sort("created_at", -1)
    return [serialize(x) for x in items]


@app.get("/tutors", tags=["academic"], summary="List tutors")
def list_tutors(q: Optional[str] = None, location: Optional[str] = None, subject: Optional[str] = None):
    filt = build_filter(q, location, subject)
    items = db["tutor"].find(filt).sort("created_at", -1)
    return [serialize(x) for x in items]


@app.get("/clubs", tags=["community"], summary="List clubs")
def list_clubs(q: Optional[str] = None, location: Optional[str] = None):
    filt = build_filter(q, location, None)
    items = db["club"].find(filt).sort("created_at", -1)
    return [serialize(x) for x in items]


@app.get("/events", tags=["community"], summary="List events")
def list_events(q: Optional[str] = None, location: Optional[str] = None):
    filt = build_filter(q, location, None)
    items = db["event"].find(filt).sort("start_time", 1)
    return [serialize(x) for x in items]


@app.get("/lostfound", tags=["community"], summary="List lost & found items")
def list_lostfound(q: Optional[str] = None, location: Optional[str] = None, subject: Optional[str] = None):
    filt = build_filter(q, location, subject)
    items = db["lostfound"].find(filt).sort("created_at", -1)
    return [serialize(x) for x in items]


@app.get("/market", tags=["market"], summary="List marketplace items")
def list_market(q: Optional[str] = None, location: Optional[str] = None):
    filt = build_filter(q, location, None)
    items = db["market"].find(filt).sort("created_at", -1)
    return [serialize(x) for x in items]


# ----- Create (dynamic) -----
@app.post("/{endpoint}")
def create_item(endpoint: str, payload: CreateItemRequest):
    if endpoint not in ALLOWED_COLLECTIONS:
        raise HTTPException(status_code=404, detail="Unknown endpoint")
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")

    doc = {k: v for k, v in payload.model_dump().items() if v is not None}
    doc["created_at"] = datetime.utcnow()
    doc["updated_at"] = datetime.utcnow()
    inserted = db[ALLOWED_COLLECTIONS[endpoint]].insert_one(doc)
    created = db[ALLOWED_COLLECTIONS[endpoint]].find_one({"_id": inserted.inserted_id})
    return serialize(created)


# ----- Delete -----
@app.delete("/{endpoint}/{item_id}")
def delete_item(endpoint: str, item_id: str):
    if endpoint not in ALLOWED_COLLECTIONS:
        raise HTTPException(status_code=404, detail="Unknown endpoint")
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    res = db[ALLOWED_COLLECTIONS[endpoint]].delete_one({"_id": oid(item_id)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"success": True}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
