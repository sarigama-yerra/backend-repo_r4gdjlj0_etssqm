import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import Project, Block

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Gamma-style backend running"}

@app.get("/api/schema")
def get_schema():
    # Return list of available schema names for viewer
    return {"schemas": ["project", "block"]}

# -------- Projects --------

@app.post("/api/projects", response_model=dict)
def create_project(project: Project):
    try:
        project_id = create_document("project", project)
        return {"id": project_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/projects", response_model=List[dict])
def list_projects():
    try:
        items = get_documents("project")
        # stringify ids
        for it in items:
            it["id"] = str(it.pop("_id"))
        return items
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------- Blocks --------

class BlockCreate(BaseModel):
    project_id: str
    type: str
    content: str = ""
    order: int = 0

@app.post("/api/blocks", response_model=dict)
def create_block(payload: BlockCreate):
    try:
        # basic project existence check
        proj = db["project"].find_one({"_id": ObjectId(payload.project_id)})
        if not proj:
            raise HTTPException(status_code=404, detail="Project not found")
        block = Block(
            project_id=payload.project_id,
            type=payload.type,
            content=payload.content,
            order=payload.order,
        )
        block_id = create_document("block", block)
        return {"id": block_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/blocks/{project_id}", response_model=List[dict])
def list_blocks(project_id: str):
    try:
        items = get_documents("block", {"project_id": project_id})
        for it in items:
            it["id"] = str(it.pop("_id"))
        # sort by order then id
        items.sort(key=lambda x: (x.get("order", 0), x.get("id")))
        return items
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------- Publish (share) --------

class PublishPayload(BaseModel):
    slug: str

@app.post("/api/projects/{project_id}/publish")
def publish_project(project_id: str, payload: PublishPayload):
    try:
        # ensure slug unique
        existing = db["project"].find_one({"slug": payload.slug})
        if existing and str(existing.get("_id")) != project_id:
            raise HTTPException(status_code=409, detail="Slug already in use")
        db["project"].update_one(
            {"_id": ObjectId(project_id)},
            {"$set": {"slug": payload.slug, "published": True}},
        )
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/p/{slug}")
def view_published(slug: str):
    try:
        proj = db["project"].find_one({"slug": slug, "published": True})
        if not proj:
            raise HTTPException(status_code=404, detail="Not found")
        proj["id"] = str(proj.pop("_id"))
        blocks = list(db["block"].find({"project_id": proj["id"]}))
        for b in blocks:
            b["id"] = str(b.pop("_id"))
        blocks.sort(key=lambda x: x.get("order", 0))
        return {"project": proj, "blocks": blocks}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Existing diagnostic endpoint
@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    import os as _os
    response["database_url"] = "✅ Set" if _os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if _os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
