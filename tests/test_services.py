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
    
    # First, create a context for the user
    context_data = {
        "user_id": user_id,
        "preferences": {
            "current_skills": [
                {
                    "name": "Python",
                    "proficiency": "intermediate",
                    "last_used": "2024-02-15",
                    "years_experience": 2
                }
            ],
            "recommended_skills": [
                {
                    "name": "FastAPI",
                    "reason": "Complements Python backend development",
                    "priority": "high",
                    "estimated_time": "2 weeks"
                }
            ],
            "learning_behavior": {
                "preferred_learning_style": "hands-on",
                "learning_pace": "moderate"
            }
        }
    }
    
    create_context_response = requests.post(
        f"{CONTEXT_URL}/context/{user_id}",
        json=context_data
    )
    assert create_context_response.status_code == 200, "Failed to create context"
    
    # Test getting context from chatbot service
    get_context_response = requests.get(f"{CHATBOT_URL}/context/{user_id}")
    assert get_context_response.status_code == 200, "Failed to get context from chatbot service"
    
    context_response_data = get_context_response.json()
    assert context_response_data["user_id"] == user_id, "User ID mismatch in context response"
    assert "preferences" in context_response_data, "Context response missing preferences"
    assert "history" in context_response_data, "Context response missing history"
    
    # Test getting context for non-existent user
    non_existent_user = "non_existent_user_123"
    error_response = requests.get(f"{CHATBOT_URL}/context/{non_existent_user}")
    assert error_response.status_code == 200, "Should return 200 with empty context for non-existent user"
    error_data = error_response.json()
    assert error_data["user_id"] == non_existent_user, "User ID mismatch in error response"
    assert error_data["preferences"] == {}, "Non-existent user should have empty preferences"
    assert error_data["history"] == [], "Non-existent user should have empty history"
    
    # Test asking a question
    question_response = requests.post(
        f"{CHATBOT_URL}/ask",
        json={
            "userId": user_id,
            "question": "What are my current recommended courses?"
        }
    )
    assert question_response.status_code == 200, "Failed to get response from chatbot"
    assert "answer" in question_response.json(), "Response missing answer field"
    
    # Test getting chat history
    history_response = requests.get(f"{CHATBOT_URL}/history/{user_id}")
    assert history_response.status_code == 200, "Failed to get chat history"
    assert isinstance(history_response.json(), list), "Chat history should be a list"
    
    # Verify the context is updated with the chat history
    updated_context_response = requests.get(f"{CHATBOT_URL}/context/{user_id}")
    assert updated_context_response.status_code == 200, "Failed to get updated context"
    updated_context = updated_context_response.json()
    assert len(updated_context["history"]) > 0, "Chat history should be included in context"
    assert updated_context["history"][0]["question"] == "What are my current recommended courses?", "Question not found in context history"

def test_context_error_handling():
    """Test error handling for context endpoints"""
    # Test with invalid user ID format
    invalid_user_id = "user@123"  # assuming @ is not allowed in user IDs
    error_response = requests.get(f"{CHATBOT_URL}/context/{invalid_user_id}")
    assert error_response.status_code == 200, "Should handle invalid user ID gracefully"
    
    # Test with very long user ID
    long_user_id = "a" * 1000  # extremely long user ID
    error_response = requests.get(f"{CHATBOT_URL}/context/{long_user_id}")
    assert error_response.status_code == 200, "Should handle long user ID gracefully"
    
    # Test with empty user ID
    empty_user_id = ""
    error_response = requests.get(f"{CHATBOT_URL}/context/{empty_user_id}")
    assert error_response.status_code == 404, "Should return 404 for empty user ID"

def test_end_to_end_flow():
    """Test the complete flow from context creation to chat history and context updates"""
    user_id = f"test_user_{int(time.time())}"
    
    # 1. Create initial context with user's background
    initial_context = {
        "user_id": user_id,
        "preferences": {
            "current_skills": [
                {
                    "name": "Python",
                    "proficiency": "intermediate",
                    "last_used": "2024-02-15",
                    "years_experience": 2
                },
                {
                    "name": "JavaScript",
                    "proficiency": "beginner",
                    "last_used": "2024-01-10",
                    "years_experience": 0.5
                }
            ],
            "recommended_skills": [
                {
                    "name": "FastAPI",
                    "reason": "Complements Python backend development",
                    "priority": "high",
                    "estimated_time": "2 weeks"
                },
                {
                    "name": "React",
                    "reason": "Popular frontend framework",
                    "priority": "medium",
                    "estimated_time": "4 weeks"
                }
            ],
            "learning_behavior": {
                "preferred_learning_style": "hands-on",
                "learning_pace": "moderate",
                "study_habits": {
                    "average_session_duration": "45 minutes",
                    "preferred_time_of_day": "evening",
                    "sessions_per_week": 4
                }
            },
            "learning_progress": {
                "current_courses": [
                    {
                        "course_id": "PY201",
                        "title": "Advanced Python Programming",
                        "progress": 0.6,
                        "start_date": "2024-02-01"
                    }
                ],
                "completed_courses": [
                    {
                        "course_id": "PY101",
                        "title": "Python Basics",
                        "completion_date": "2024-01-15",
                        "grade": "A"
                    }
                ]
            }
        }
    }
    
    # Create context
    context_response = requests.post(
        f"{CONTEXT_URL}/context/{user_id}",
        json=initial_context
    )
    assert context_response.status_code == 200, "Failed to create initial context"
    
    # 2. Verify context was created correctly
    get_context_response = requests.get(f"{CHATBOT_URL}/context/{user_id}")
    assert get_context_response.status_code == 200, "Failed to get context"
    context_data = get_context_response.json()
    assert context_data["preferences"]["current_skills"][0]["name"] == "Python", "Context not saved correctly"
    
    # 3. Simulate a learning journey with multiple interactions
    conversation_flow = [
        {
            "question": "What are my recommended next courses based on my current skills?",
            "verify": lambda answer: "FastAPI" in answer and "React" in answer
        },
        {
            "question": "Can you tell me about my current progress in Advanced Python Programming?",
            "verify": lambda answer: "60%" in answer or "0.6" in answer
        },
        {
            "question": "What's my learning pace and preferred study time?",
            "verify": lambda answer: "evening" in answer.lower() and "moderate" in answer.lower()
        },
        {
            "question": "How am I doing in my JavaScript learning journey?",
            "verify": lambda answer: "beginner" in answer.lower()
        }
    ]
    
    # Send questions and verify responses
    for interaction in conversation_flow:
        # Ask question
        response = requests.post(
            f"{CHATBOT_URL}/ask",
            json={
                "userId": user_id,
                "question": interaction["question"]
            }
        )
        assert response.status_code == 200, f"Failed to get response for question: {interaction['question']}"
        answer = response.json()["answer"]
        assert interaction["verify"](answer), f"Response doesn't match expected content for question: {interaction['question']}"
        time.sleep(1)  # Add small delay between requests
    
    # 4. Verify chat history is complete
    history_response = requests.get(f"{CHATBOT_URL}/history/{user_id}")
    assert history_response.status_code == 200, "Failed to get chat history"
    history = history_response.json()
    assert len(history) == len(conversation_flow), "Chat history length doesn't match conversation flow"
    
    # 5. Verify final context includes chat history
    final_context_response = requests.get(f"{CHATBOT_URL}/context/{user_id}")
    assert final_context_response.status_code == 200, "Failed to get final context"
    final_context = final_context_response.json()
    
    # Verify context still has original data
    assert len(final_context["preferences"]["current_skills"]) == 2, "Skills data lost from context"
    assert final_context["preferences"]["learning_behavior"]["preferred_learning_style"] == "hands-on", "Learning behavior data lost"
    
    # Verify history is included
    assert len(final_context["history"]) == len(conversation_flow), "History not properly included in context"
    assert final_context["history"][0]["question"] == conversation_flow[-1]["question"], "Most recent question not in context"

if __name__ == "__main__":
    print("Running tests...")
    pytest.main([__file__, "-v"]) 