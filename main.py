import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from pydantic import BaseModel
from bson.objectid import ObjectId

from database import db
from schemas import CurdEntry

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _serialize(doc: dict) -> dict:
    if not doc:
        return doc
    d = {**doc}
    if "_id" in d:
        d["id"] = str(d.pop("_id"))
    # Convert datetime to ISO strings if present
    for k, v in list(d.items()):
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
    return d


@app.get("/")
def read_root():
    return {"message": "Curd Tracker Backend Running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set",
        "database_name": "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": [],
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["connection_status"] = "Connected"
            response["collections"] = db.list_collection_names()
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response


# --------- CURD ENTRIES API ---------
COLL = "curdentry"


class CurdEntryOut(CurdEntry):
    id: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@app.get("/api/entries", response_model=List[CurdEntryOut])
def list_entries():
    if db is None:
        return []
    docs = db[COLL].find().sort([("date", -1), ("time", -1)])
    return [_serialize(d) for d in docs]


@app.post("/api/entries", response_model=CurdEntryOut)
def create_entry(entry: CurdEntry):
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    from database import create_document
    new_id = create_document(COLL, entry)
    doc = db[COLL].find_one({"_id": ObjectId(new_id)})
    return _serialize(doc)


class CurdEntryUpdate(BaseModel):
    date: Optional[str] = None
    time: Optional[str] = None
    quantity: Optional[float] = None
    amount: Optional[float] = None


@app.put("/api/entries/{entry_id}", response_model=CurdEntryOut)
def update_entry(entry_id: str, payload: CurdEntryUpdate):
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    try:
        oid = ObjectId(entry_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")

    updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if not updates:
        doc = db[COLL].find_one({"_id": oid})
        if not doc:
            raise HTTPException(status_code=404, detail="Not found")
        return _serialize(doc)

    from datetime import datetime, timezone
    updates["updated_at"] = datetime.now(timezone.utc)

    res = db[COLL].update_one({"_id": oid}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    doc = db[COLL].find_one({"_id": oid})
    return _serialize(doc)


@app.delete("/api/entries/{entry_id}")
def delete_entry(entry_id: str):
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    try:
        oid = ObjectId(entry_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")
    res = db[COLL].delete_one({"_id": oid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
