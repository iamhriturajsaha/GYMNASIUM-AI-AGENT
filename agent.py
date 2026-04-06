import os
import logging
import datetime
import asyncio
import google.cloud.logging
from google.cloud import datastore
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
from mcp.server.fastmcp import FastMCP 
from google.adk import Agent
from google.adk.agents import SequentialAgent
from google.adk.tools.tool_context import ToolContext

# LOGGING
try:
    cloud_logging_client = google.cloud.logging.Client()
    cloud_logging_client.setup_logging()
except Exception:
    logging.basicConfig(level=logging.INFO)
load_dotenv()
model_name = os.getenv("MODEL", "gemini-1.5-flash")

# DATABASE
db = datastore.Client()
mcp = FastMCP("GymnasiumTools")

# TOOLS
@mcp.tool()
def add_workout(exercise: str, reps: int, sets: int) -> str:
    """Log a new workout session."""
    try:
        key = db.key('Workout')
        workout = datastore.Entity(key=key)
        workout.update({
            'exercise': exercise,
            'reps': reps,
            'sets': sets,
            'created_at': datetime.datetime.now()
        })
        db.put(workout)
        return f"🏋️ Workout '{exercise}' logged (ID: {workout.key.id})"
    except Exception as e:
        logging.error(f"DB Error: {e}")
        return f"Database Error: {str(e)}"
@mcp.tool()
def list_workouts() -> str:
    """List all workout sessions."""
    try:
        query = db.query(kind='Workout')
        workouts = list(query.fetch())
        if not workouts:
            return "No workouts logged yet."
        res = ["📊 Workout History:"]
        for w in workouts:
            res.append(
                f"{w.get('exercise')} - {w.get('sets')} sets x {w.get('reps')} reps (ID: {w.key.id})"
            )
        return "\n".join(res)
    except Exception as e:
        return f"Database Error: {str(e)}"
@mcp.tool()
def log_fitness_progress(weight: float, note: str) -> str:
    """Log body weight and fitness notes."""
    try:
        key = db.key('FitnessLog')
        entry = datastore.Entity(key=key)
        entry.update({
            'weight': weight,
            'note': note,
            'date': datetime.datetime.now()
        })
        db.put(entry)
        return f"📈 Progress logged: {weight} kg"
    except Exception as e:
        return f"Database Error: {str(e)}"
@mcp.tool()
def get_progress() -> str:
    """Retrieve fitness progress logs."""
    try:
        query = db.query(kind='FitnessLog')
        logs = list(query.fetch())
        if not logs:
            return "No progress data found."
        res = ["📉 Fitness Progress:"]
        for log in logs:
            res.append(f"{log.get('weight')} kg - {log.get('note')}")
        return "\n".join(res)
    except Exception as e:
        return f"Database Error: {str(e)}"

# AGENTS
def add_prompt_to_state(tool_context: ToolContext, prompt: str):
    tool_context.state["PROMPT"] = prompt
    return {"status": "ok"}
def gym_instruction(ctx):
    user_prompt = ctx.state.get("PROMPT", "Welcome the user.")
    return f"""
You are Gymnasium AI Coach 🏋️‍♂️
Your responsibilities:
- Help users track workouts
- Suggest exercises
- Log fitness progress
- Keep responses motivating and actionable
User request: {user_prompt}
Always:
- Be concise
- Suggest workouts when relevant
- Use tools when needed
"""
def root_instruction(ctx):
    raw_input = ctx.state.get("user_input", "Hello")
    return f"""
1. Save this user input using 'add_prompt_to_state': {raw_input}
2. Hand off control to the 'workflow' agent.
"""
gym_agent = Agent(
    name="gym_coach",
    model=model_name,
    instruction=gym_instruction,
    tools=[add_workout, list_workouts, log_fitness_progress, get_progress]
)
workflow = SequentialAgent(
    name="workflow",
    sub_agents=[gym_agent]
)
root_agent = Agent(
    name="root",
    model=model_name,
    instruction=root_instruction,
    tools=[add_prompt_to_state],
    sub_agents=[workflow]
)

# API
app = FastAPI()
class UserRequest(BaseModel):
    prompt: str
@app.post("/api/v1/gymnasium/chat")
async def chat(request: UserRequest):
    try:
        final_reply = ""
        async for event in root_agent.run_async({"user_input": request.prompt}):
            if hasattr(event, 'text') and event.text:
                final_reply = event.text
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
