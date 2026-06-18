import os
import logging
import datetime
import sqlite3
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
from google.adk import Agent
from google.adk.agents import SequentialAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.tool_context import ToolContext

# LOGGING
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
load_dotenv()

# MODEL SETUP (Groq via LiteLLM)
GROQ_MODEL = LiteLlm(model=f"groq/{os.getenv('MODEL', 'llama-3.3-70b-versatile')}")

# DATABASE SETUP (SQLite for Render compatibility)
def get_db():
    conn = sqlite3.connect("gymnasium.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS workouts 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, exercise TEXT, reps INTEGER, sets INTEGER, created_at TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS progress
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, weight REAL, note TEXT, created_at TEXT)''')
        conn.commit()

init_db()

# TOOLS
def add_workout(exercise: str, reps: int, sets: int) -> str:
    """Log a new workout session."""
    try:
        with get_db() as conn:
            cursor = conn.execute(
                "INSERT INTO workouts (exercise, reps, sets, created_at) VALUES (?, ?, ?, ?)",
                (exercise, reps, sets, datetime.datetime.now().isoformat())
            )
            conn.commit()
            return f"🏋️ Workout '{exercise}' logged (ID: {cursor.lastrowid})"
    except Exception as e:
        logging.error(f"DB Error: {e}")
        return f"Database Error: {str(e)}"

def list_workouts() -> str:
    """List all workout sessions."""
    try:
        with get_db() as conn:
            workouts = conn.execute("SELECT * FROM workouts ORDER BY id DESC LIMIT 10").fetchall()
            if not workouts:
                return "No workouts logged yet."
            res = ["📊 Recent Workout History:"]
            for w in workouts:
                res.append(f"{w['exercise']} - {w['sets']} sets x {w['reps']} reps")
            return "\n".join(res)
    except Exception as e:
        return f"Database Error: {str(e)}"

def log_fitness_progress(weight: float, note: str) -> str:
    """Log body weight and fitness notes."""
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO progress (weight, note, created_at) VALUES (?, ?, ?)",
                (weight, note, datetime.datetime.now().isoformat())
            )
            conn.commit()
            return f"📈 Progress logged: {weight} kg"
    except Exception as e:
        return f"Database Error: {str(e)}"

def get_progress() -> str:
    """Retrieve fitness progress logs."""
    try:
        with get_db() as conn:
            logs = conn.execute("SELECT * FROM progress ORDER BY id DESC LIMIT 5").fetchall()
            if not logs:
                return "No progress data found."
            res = ["📉 Recent Fitness Progress:"]
            for log in logs:
                res.append(f"{log['weight']} kg - {log['note']}")
            return "\n".join(res)
    except Exception as e:
        return f"Database Error: {str(e)}"

# AGENT
gym_agent = Agent(
    name="gym_coach",
    model=GROQ_MODEL,
    description="A friendly fitness coach that tracks workouts and fitness progress.",
    instruction="""
    You are Roman, a friendly and motivating AI fitness coach.
    
    Your responsibilities:
    - Welcome users and answer general questions warmly.
    - Help users track workouts and suggest exercises.
    - Log fitness progress and provide actionable feedback.
    
    Always:
    - Be concise and highly motivating.
    - Ask clarifying questions if the workout details (like reps or sets) are missing.
    - CRITICAL: Never output raw `<function>` tags. If you need to log something, strictly use the native tool calling feature.
    """,
    tools=[add_workout, list_workouts, log_fitness_progress, get_progress]
)

# API
app = FastAPI()

class UserRequest(BaseModel):
    prompt: str

@app.post("/api/v1/gymnasium/chat")
async def chat(request: UserRequest):
    try:
        final_reply = ""
        async for event in gym_agent.run_async({"user_input": request.prompt}):
            if hasattr(event, 'text') and event.text:
                final_reply += event.text
        return {
            "status": "success",
            "reply": final_reply if final_reply else "Workout processed 💪"
        }
    except Exception as e:
        logging.error(f"Chat Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
