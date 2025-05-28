from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import databases
import sqlalchemy
from datetime import datetime

# Database URL
DATABASE_URL = "sqlite:///./context.db"

# Database instance
database = databases.Database(DATABASE_URL)

# SQLAlchemy
metadata = sqlalchemy.MetaData()

# Define the contexts table
contexts = sqlalchemy.Table(
    "contexts",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column("user_id", sqlalchemy.String, index=True),
    sqlalchemy.Column("preferences", sqlalchemy.JSON),
    sqlalchemy.Column("history", sqlalchemy.JSON),
    sqlalchemy.Column("updated_at", sqlalchemy.DateTime),
)

app = FastAPI(title="Context Service")

class Context(BaseModel):
    user_id: str
    preferences: dict = {}
    history: List[dict] = []

@app.on_event("startup")
async def startup():
    await database.connect()
    # Create tables
    engine = sqlalchemy.create_engine(DATABASE_URL)
    metadata.create_all(engine)

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()

@app.get("/context/{user_id}")
async def get_context(user_id: str):
    query = contexts.select().where(contexts.c.user_id == user_id)
    result = await database.fetch_one(query)
    
    if result is None:
        # Create new context if it doesn't exist
        new_context = {
            "user_id": user_id,
            "preferences": {},
            "history": [],
            "updated_at": datetime.utcnow()
        }
        await database.execute(contexts.insert().values(**new_context))
        return new_context
    
    return {
        "user_id": result["user_id"],
        "preferences": result["preferences"],
        "history": result["history"]
    }

@app.post("/context/{user_id}")
async def update_context(user_id: str, context: Context):
    values = {
        "preferences": context.preferences,
        "history": context.history,
        "updated_at": datetime.utcnow()
    }
    
    query = contexts.update().where(contexts.c.user_id == user_id).values(**values)
    await database.execute(query)
    
    return {"status": "success", "message": "Context updated successfully"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001) 