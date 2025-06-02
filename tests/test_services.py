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
            "learning_preferences": {
                "preferred_learning_style": "visual",
                "time_availability": {
                    "hours_per_week": 6,
                    "preferred_schedule": "weekdays"
                }
            },
            "constraints": {
                "time_constraints": 9,
                "budget_constraints": 10
            },
            "background": {
                "education_level": "Bachelor's",
                "work_experience_years": "3",
                "current_role": "Software Developer",
                "industry": "Technology"
            }
        }
    )
    assert create_response.status_code == 200, "Failed to create context"
    
    # Test getting context
    get_response = requests.get(f"{CONTEXT_URL}/context/{user_id}")
    assert get_response.status_code == 200, "Failed to get context"
    
    context_data = get_response.json()
    assert "id" in context_data, "Context ID missing in response"
    assert isinstance(context_data["id"], int), "Context ID should be an integer"
    assert context_data["learning_preferences"]["preferred_learning_style"] == "visual", "Learning preferences not saved correctly"
    assert context_data["background"]["education_level"] == "Bachelor's", "Background not saved correctly"
    
    # Store the context ID for later comparison
    context_id = context_data["id"]
    
    # Get the context again to verify ID consistency
    second_get_response = requests.get(f"{CONTEXT_URL}/context/{user_id}")
    assert second_get_response.status_code == 200, "Failed to get context second time"
    second_context_data = second_get_response.json()
    assert second_context_data["id"] == context_id, "Context ID changed between requests"

def test_chatbot_service():
    """Test chatbot service endpoints"""
    user_id = f"test_user_{int(time.time())}"
    
    # First, create a context for the user
    context_data = {
        "user_id": user_id,
        "learning_preferences": {
            "preferred_learning_style": "hands-on",
            "time_availability": {
                "hours_per_week": 10,
                "preferred_schedule": "flexible"
            }
        },
        "constraints": {
            "time_constraints": 8,
            "budget_constraints": 15
        },
        "background": {
            "education_level": "Bachelor's",
            "work_experience_years": "2",
            "current_role": "Junior Developer",
            "industry": "Technology"
        },
        "skills": [
            {
                "id": 1,
                "name": "python",
                "category": "programming",
                "level": "intermediate",
                "description": "Python programming language proficiency"
            }
        ],
        "progresses": [
            {
                "target": {
                    "id": 1,
                    "title": "Backend Developer",
                    "type": "Career Path",
                    "description": "Backend development specialization",
                    "required_skills": [
                        {
                            "importance": "must have",
                            "skill": {
                                "id": 1,
                                "name": "python",
                                "category": "programming",
                                "level": "expert",
                                "description": "Advanced Python development"
                            }
                        }
                    ]
                },
                "learning_path": {
                    "id": 1,
                    "title": "Python Expert Path",
                    "description": "Advanced Python development path",
                    "progress": 60,
                    "completion_date": "2025-06-13T16:09:02.736Z",
                    "target_id": 1,
                    "learned_skills": [
                        {
                            "proficiency_level": "intermediate",
                            "resources": [
                                {
                                    "type": "course",
                                    "title": "Python Advanced Concepts",
                                    "url": "https://example.com",
                                    "price": "199.99",
                                    "estimated_hours": "40",
                                    "description": "Advanced Python programming concepts",
                                    "provider": "coursera"
                                }
                            ],
                            "status": "done",
                            "update_date": "2024-07-28T11:44:34.669Z",
                            "expected_output": "Can build complex applications using Python",
                            "skill": {
                                "id": 1,
                                "name": "python",
                                "category": "programming",
                                "level": "intermediate",
                                "description": "Python programming proficiency"
                            }
                        }
                    ],
                    "to_learn_skills": [
                        {
                            "proficiency_level": "expert",
                            "resources": [
                                {
                                    "type": "course",
                                    "title": "Python System Design",
                                    "url": "https://example.com",
                                    "price": "299.99",
                                    "estimated_hours": "60",
                                    "description": "System design with Python",
                                    "provider": "udemy"
                                }
                            ],
                            "status": "todo",
                            "expected_output": "Can design and implement complex systems",
                            "skill": {
                                "id": 2,
                                "name": "python",
                                "category": "programming",
                                "level": "expert",
                                "description": "Expert Python development"
                            }
                        }
                    ]
                }
            }
        ]
    }
    
    # Create context
    context_response = requests.post(
        f"{CONTEXT_URL}/context/{user_id}",
        json=context_data
    )
    assert context_response.status_code == 200, "Failed to create initial context"
    
    # Test getting context from chatbot service
    get_context_response = requests.get(f"{CHATBOT_URL}/context/{user_id}")
    assert get_context_response.status_code == 200, "Failed to get context from chatbot service"
    
    context_response_data = get_context_response.json()
    assert "id" in context_response_data, "Context ID missing in response"
    assert isinstance(context_response_data["id"], int), "Context ID should be an integer"
    assert "learning_preferences" in context_response_data, "Context response missing learning preferences"
    assert "skills" in context_response_data, "Context response missing skills"
    assert "progresses" in context_response_data, "Context response missing progresses"
    assert "history" in context_response_data, "Context response missing history"
    
    # Store the context ID
    context_id = context_response_data["id"]
    
    # Test getting context for non-existent user
    non_existent_user = "non_existent_user_123"
    error_response = requests.get(f"{CHATBOT_URL}/context/{non_existent_user}")
    assert error_response.status_code == 200, "Should return 200 with empty context for non-existent user"
    error_data = error_response.json()
    assert "id" in error_data, "Context ID missing in error response"
    assert isinstance(error_data["id"], int), "Context ID should be an integer"
    assert error_data["learning_preferences"] == {}, "Non-existent user should have empty learning preferences"
    assert error_data["history"] == [], "Non-existent user should have empty history"
    
    # Test asking a question
    question_response = requests.post(
        f"{CHATBOT_URL}/ask",
        json={
            "userId": user_id,
            "question": "What is my current learning progress?"
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
    assert updated_context["history"][0]["question"] == "What is my current learning progress?", "Question not found in context history"

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
        "learning_preferences": {
            "preferred_learning_style": "visual",
            "time_availability": {
                "hours_per_week": 6,
                "preferred_schedule": "weekdays"
            }
        },
        "constraints": {
            "time_constraints": 9,
            "budget_constraints": 10
        },
        "background": {
            "education_level": "Bachelor's",
            "work_experience_years": "3",
            "current_role": "Software Developer",
            "industry": "Technology"
        },
        "skills": [
            {
                "id": 1,
                "name": "python",
                "category": "programming",
                "level": "intermediate",
                "description": "Python programming language proficiency"
            },
            {
                "id": 2,
                "name": "javascript",
                "category": "programming",
                "level": "beginner",
                "description": "JavaScript programming language basics"
            }
        ],
        "progresses": [
            {
                "target": {
                    "id": 1,
                    "title": "Backend Developer",
                    "type": "Career Path",
                    "description": "Backend development specialization",
                    "required_skills": [
                        {
                            "importance": "must have",
                            "skill": {
                                "id": 1,
                                "name": "python",
                                "category": "programming",
                                "level": "expert",
                                "description": "Advanced Python development"
                            }
                        }
                    ]
                },
                "learning_path": {
                    "id": 1,
                    "title": "Python Expert Path",
                    "description": "Advanced Python development path",
                    "progress": 60,
                    "completion_date": "2025-06-13T16:09:02.736Z",
                    "target_id": 1,
                    "learned_skills": [
                        {
                            "proficiency_level": "intermediate",
                            "resources": [
                                {
                                    "type": "course",
                                    "title": "Python Advanced Concepts",
                                    "url": "https://example.com",
                                    "price": "199.99",
                                    "estimated_hours": "40",
                                    "description": "Advanced Python programming concepts",
                                    "provider": "coursera"
                                }
                            ],
                            "status": "done",
                            "update_date": "2024-07-28T11:44:34.669Z",
                            "expected_output": "Can build complex applications using Python",
                            "skill": {
                                "id": 1,
                                "name": "python",
                                "category": "programming",
                                "level": "intermediate",
                                "description": "Python programming proficiency"
                            }
                        }
                    ],
                    "to_learn_skills": [
                        {
                            "proficiency_level": "expert",
                            "resources": [
                                {
                                    "type": "course",
                                    "title": "Python System Design",
                                    "url": "https://example.com",
                                    "price": "299.99",
                                    "estimated_hours": "60",
                                    "description": "System design with Python",
                                    "provider": "udemy"
                                }
                            ],
                            "status": "todo",
                            "expected_output": "Can design and implement complex systems",
                            "skill": {
                                "id": 2,
                                "name": "python",
                                "category": "programming",
                                "level": "expert",
                                "description": "Expert Python development"
                            }
                        }
                    ]
                }
            }
        ]
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
    assert context_data["learning_preferences"]["preferred_learning_style"] == "visual", "Learning preferences not saved correctly"
    assert context_data["skills"][0]["name"] == "python", "Skills not saved correctly"
    assert context_data["progresses"][0]["learning_path"]["progress"] == 60, "Learning path progress not saved correctly"
    
    # 3. Simulate a learning journey with multiple interactions
    conversation_flow = [
        {
            "question": "What's my current learning progress in Python?",
            "verify": lambda answer: "60%" in answer or "intermediate" in answer.lower()
        },
        {
            "question": "What skills do I need to learn to become a Backend Developer?",
            "verify": lambda answer: "expert" in answer.lower() and "python" in answer.lower()
        },
        {
            "question": "What are my learning preferences and constraints?",
            "verify": lambda answer: "visual" in answer.lower() and "weekdays" in answer.lower()
        },
        {
            "question": "What's my next recommended course in the learning path?",
            "verify": lambda answer: "system design" in answer.lower() or "python" in answer.lower()
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
    assert len(final_context["skills"]) == 2, "Skills data lost from context"
    assert final_context["learning_preferences"]["preferred_learning_style"] == "visual", "Learning preferences data lost"
    assert final_context["progresses"][0]["learning_path"]["progress"] == 60, "Learning path progress data lost"
    
    # Verify history is included
    assert len(final_context["history"]) == len(conversation_flow), "History not properly included in context"
    assert final_context["history"][0]["question"] == conversation_flow[-1]["question"], "Most recent question not in context"

if __name__ == "__main__":
    print("Running tests...")
    pytest.main([__file__, "-v"]) 