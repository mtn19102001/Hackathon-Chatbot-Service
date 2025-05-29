from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
import databases
import sqlalchemy
from datetime import datetime
import os
from dotenv import load_dotenv
import json

# Load environment variables
load_dotenv()

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://ntmt01@localhost/chatbot")

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
    sqlalchemy.Column("preferences", sqlalchemy.JSON, nullable=False, server_default='{}'),
    sqlalchemy.Column("updated_at", sqlalchemy.DateTime),
)

# Define the chat history table
chat_history = sqlalchemy.Table(
    "chat_history",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column("user_id", sqlalchemy.String, index=True),
    sqlalchemy.Column("question", sqlalchemy.Text),
    sqlalchemy.Column("answer", sqlalchemy.Text),
    sqlalchemy.Column("created_at", sqlalchemy.DateTime),
)

app = FastAPI(
    title="Context Service",
    description="A service that manages user context and chat history for the chatbot",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

class ChatHistoryItem(BaseModel):
    question: str = Field(..., description="The user's question")
    answer: str = Field(..., description="The chatbot's answer")
    created_at: str = Field(..., description="Timestamp of the chat message")

class Context(BaseModel):
    user_id: str = Field(..., description="Unique identifier for the user", example="user123")
    preferences: Dict = Field(default={}, description="User preferences and settings")

    class Config:
        schema_extra = {
            "example": {
                "user_id": "user123",
                "preferences": {
                    "language": "en",
                    "expertise_level": "intermediate"
                }
            }
        }

class ChatMessage(BaseModel):
    user_id: str = Field(..., description="Unique identifier for the user")
    question: str = Field(..., description="The user's question")
    answer: str = Field(..., description="The chatbot's answer")

    class Config:
        schema_extra = {
            "example": {
                "user_id": "user123",
                "question": "What is machine learning?",
                "answer": "Machine learning is a subset of artificial intelligence..."
            }
        }

class ContextResponse(BaseModel):
    user_id: str = Field(..., description="Unique identifier for the user")
    preferences: Dict = Field(..., description="User preferences and settings")
    history: List[ChatHistoryItem] = Field(..., description="Recent chat history")

@app.on_event("startup")
async def startup():
    print("Connecting to database:", DATABASE_URL)
    await database.connect()
    # Create tables
    engine = sqlalchemy.create_engine(DATABASE_URL)
    print("Creating tables...")
    metadata.create_all(engine)
    print("Tables created successfully")

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()

@app.get("/context/{user_id}", 
    response_model=ContextResponse,
    summary="Get user context and chat history",
    description="Retrieve a user's context, preferences, and recent chat history. If the user doesn't exist, a new context will be created.",
    tags=["Context"]
)
async def get_context(user_id: str):
    try:
        # Get user context
        query = contexts.select().where(contexts.c.user_id == user_id)
        result = await database.fetch_one(query)
        
        # Get recent chat history
        history_query = chat_history.select()\
            .where(chat_history.c.user_id == user_id)\
            .order_by(chat_history.c.created_at.desc())\
            .limit(10)
        history = await database.fetch_all(history_query)
        
        if result is None:
            # Create new context if it doesn't exist
            new_context = {
                "user_id": user_id,
                "preferences": {},
                "updated_at": datetime.utcnow()
            }
            await database.execute(contexts.insert().values(**new_context))
            preferences = {}
        else:
            # Get preferences from the database result
            try:
                # Try to get preferences as a dictionary
                preferences = dict(result.preferences)
                print("Retrieved preferences:", preferences)
            except (TypeError, ValueError):
                # If conversion fails, try to parse as JSON string
                if isinstance(result.preferences, str):
                    try:
                        preferences = json.loads(result.preferences)
                    except json.JSONDecodeError:
                        preferences = {}
                else:
                    preferences = {}
        
        response = ContextResponse(
            user_id=user_id,
            preferences=preferences,
            history=[
                ChatHistoryItem(
                    question=h.question,
                    answer=h.answer,
                    created_at=h.created_at.isoformat()
                )
                for h in history
            ] if history else []
        )
        print("Response:", response.dict())
        return response
    except Exception as e:
        print("Error in get_context:", str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/context/{user_id}",
    summary="Update user context",
    description="Update a user's preferences and settings",
    tags=["Context"]
)
async def update_context(user_id: str, context: Context):
    print(f"Updating context for user {user_id} with preferences:", context.preferences)
    # Check if user exists
    query = contexts.select().where(contexts.c.user_id == user_id)
    result = await database.fetch_one(query)
    
    values = {
        "preferences": context.preferences,
        "updated_at": datetime.utcnow()
    }
    
    if result is None:
        print("Creating new user context")
        # Create new user context
        values["user_id"] = user_id
        await database.execute(contexts.insert().values(**values))
    else:
        print("Updating existing user context")
        # Update existing user context
        await database.execute(
            contexts.update()
            .where(contexts.c.user_id == user_id)
            .values(**values)
        )
    
    # Verify the update
    result = await database.fetch_one(contexts.select().where(contexts.c.user_id == user_id))
    print("Updated context:", result)
    
    return {"status": "success", "message": "Context updated successfully"}

@app.post("/chat/{user_id}",
    summary="Store chat message",
    description="Store a chat interaction (question and answer) for a user",
    tags=["Chat History"]
)
async def add_chat_message(user_id: str, message: ChatMessage):
    values = {
        "user_id": user_id,
        "question": message.question,
        "answer": message.answer,
        "created_at": datetime.utcnow()
    }
    
    await database.execute(chat_history.insert().values(**values))
    return {"status": "success", "message": "Chat message added successfully"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001) 