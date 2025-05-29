import pytest
import requests
import psycopg2
import time
from datetime import datetime
import os

# Configuration
CHATBOT_HOST = os.getenv("CHATBOT_HOST", "localhost")
CONTEXT_HOST = os.getenv("CONTEXT_HOST", "localhost")
DB_HOST = os.getenv("DB_HOST", "localhost")

CHATBOT_URL = f"http://{CHATBOT_HOST}:8000"
CONTEXT_URL = f"http://{CONTEXT_HOST}:8001"
DB_CONFIG = {
    "dbname": "chatbot",
    "user": "postgres",
    "password": "postgres",
    "host": DB_HOST,
    "port": "5432"
}

def wait_for_postgres():
    """Wait for PostgreSQL to be ready"""
    max_attempts = 10
    for attempt in range(max_attempts):
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            conn.close()
            return True
        except psycopg2.OperationalError:
            if attempt < max_attempts - 1:
                time.sleep(2)
                continue
            raise
    return False

def test_database_connection():
    """Test database connectivity and table existence"""
    try:
        # Wait for PostgreSQL to be ready
        assert wait_for_postgres(), "Failed to connect to PostgreSQL after multiple attempts"
        
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        # Check if required tables exist
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('chat_history', 'contexts')
        """)
        tables = [table[0] for table in cur.fetchall()]
        
        assert 'chat_history' in tables, "chat_history table not found"
        assert 'contexts' in tables, "contexts table not found"
        
        cur.close()
        conn.close()
    except Exception as e:
        pytest.fail(f"Database connection failed: {str(e)}")

def test_context_service():
    """Test context service endpoints"""
    user_id = f"test_user_{int(time.time())}"
    
    # Test creating context
    create_response = requests.post(
        f"{CONTEXT_URL}/context/{user_id}",
        json={
            "user_id": user_id,
            "preferences": {
                "language": "en",
                "style": "friendly"
            }
        }
    )
    assert create_response.status_code == 200, "Failed to create context"
    
    # Test getting context
    get_response = requests.get(f"{CONTEXT_URL}/context/{user_id}")
    assert get_response.status_code == 200, "Failed to get context"
    
    context_data = get_response.json()
    assert context_data["user_id"] == user_id, "User ID mismatch"
    assert context_data["preferences"]["language"] == "en", "Preferences not saved correctly"

def test_chatbot_service():
    """Test chatbot service endpoints"""
    user_id = f"test_user_{int(time.time())}"
    
    # Test asking a question
    question_response = requests.post(
        f"{CHATBOT_URL}/ask",
        json={
            "userId": user_id,
            "question": "Hello! How are you?"
        }
    )
    assert question_response.status_code == 200, "Failed to get response from chatbot"
    assert "answer" in question_response.json(), "Response missing answer field"
    
    # Test getting chat history
    history_response = requests.get(f"{CHATBOT_URL}/history/{user_id}")
    assert history_response.status_code == 200, "Failed to get chat history"
    assert isinstance(history_response.json(), list), "Chat history should be a list"

def test_end_to_end_flow():
    """Test the complete flow from context creation to chat history"""
    user_id = f"test_user_{int(time.time())}"
    
    # 1. Create context
    context_response = requests.post(
        f"{CONTEXT_URL}/context/{user_id}",
        json={
            "user_id": user_id,
            "preferences": {
                "language": "en",
                "style": "professional"
            }
        }
    )
    assert context_response.status_code == 200, "Failed to create context"
    
    # 2. Send multiple messages
    questions = [
        "What is machine learning?",
        "Can you explain neural networks?",
        "How does deep learning work?"
    ]
    
    for question in questions:
        response = requests.post(
            f"{CHATBOT_URL}/ask",
            json={
                "userId": user_id,
                "question": question
            }
        )
        assert response.status_code == 200, f"Failed to get response for question: {question}"
        time.sleep(1)  # Add small delay between requests
    
    # 3. Verify chat history
    history_response = requests.get(f"{CHATBOT_URL}/history/{user_id}")
    assert history_response.status_code == 200, "Failed to get chat history"
    
    history = history_response.json()
    assert len(history) > 0, "Chat history is empty"
    
    # Verify the most recent questions are in the history
    history_questions = [item["question"] for item in history]
    for question in questions:
        assert question in history_questions, f"Question '{question}' not found in history"

if __name__ == "__main__":
    print("Running tests...")
    pytest.main([__file__, "-v"]) 