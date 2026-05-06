# -*- coding: utf-8 -*-
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
import uuid
import time
import json
import os

app = FastAPI(title="SAGE Universal API", version="3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB = "sage.db"

# -------------------------------------------------------------
# Embedded questions (now with 'subject' field)
# -------------------------------------------------------------
EMBEDDED_QUESTIONS = [
    {
        "subject": "Civil",
        "topic": "concrete_technology",
        "difficulty": "easy",
        "text": "The specific surface area of aggregate is defined as:",
        "options": {"A": "Total surface area per unit weight", "B": "Total surface area per unit volume of concrete", "C": "Surface area of one particle", "D": "Area of voids"},
        "correct": "A",
        "explanation": "Standard definition: total surface area per unit mass (or weight) of aggregate.",
        "source": "SSC JE 2023"
    },
    {
        "subject": "Civil",
        "topic": "concrete_technology",
        "difficulty": "medium",
        "text": "If the fineness modulus of fine aggregate increases, workability (with same w/c ratio) will:",
        "options": {"A": "Increase", "B": "Decrease", "C": "Not change", "D": "First increase then decrease"},
        "correct": "A",
        "explanation": "Higher fineness modulus means coarser sand → lower specific surface area → higher workability.",
        "source": "SSC JE 2023"
    }
]

# -------------------------------------------------------------
# Database initialization (with upgrade for subject column)
# -------------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id TEXT PRIMARY KEY,
            subject TEXT,
            topic TEXT,
            difficulty TEXT,
            text TEXT,
            options TEXT,
            correct TEXT,
            explanation TEXT,
            source TEXT
        )
    """)
    # Add subject column if upgrading from old schema
    try:
        cur.execute("ALTER TABLE questions ADD COLUMN subject TEXT")
    except sqlite3.OperationalError:
        pass
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            user_id TEXT,
            exam_pattern TEXT,
            difficulty TEXT,
            score INTEGER DEFAULT 0,
            count INTEGER DEFAULT 0,
            start_time REAL,
            status TEXT DEFAULT 'active'
        )
    """)
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM questions")
    if cur.fetchone()[0] == 0:
        for q in EMBEDDED_QUESTIONS:
            qid = str(uuid.uuid4())
            cur.execute("""
                INSERT INTO questions (id, subject, topic, difficulty, text, options, correct, explanation, source)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (qid, q["subject"], q["topic"], q["difficulty"], q["text"],
                  json.dumps(q["options"]), q["correct"], q["explanation"], q["source"]))
        conn.commit()
    conn.close()

init_db()

# -------------------------------------------------------------
# Pydantic models
# -------------------------------------------------------------
class StartReq(BaseModel):
    user_id: str
    exam_pattern: str
    subjects: list
    num_questions: int = 10
    difficulty: str = "medium"

class AnswerReq(BaseModel):
    session_id: str
    question_id: str
    answer: str
    time_taken_seconds: float = 0.0

class EndReq(BaseModel):
    session_id: str

class BulkInsertReq(BaseModel):
    data: list

class AddQuestionReq(BaseModel):
    subject: str
    topic: str
    difficulty: str
    text: str
    options: dict
    correct: str
    explanation: str
    source: str = "manual"

# -------------------------------------------------------------
# Helper functions
# -------------------------------------------------------------
def get_conn():
    return sqlite3.connect(DB)

def get_question(subjects, difficulty):
    conn = get_conn()
    cur = conn.cursor()
    placeholders = ",".join("?" for _ in subjects)
    cur.execute(f"""
        SELECT * FROM questions
        WHERE subject IN ({placeholders}) AND difficulty = ?
        ORDER BY RANDOM()
        LIMIT 1
    """, subjects + [difficulty])
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row[0],
        "subject": row[1],
        "topic": row[2],
        "text": row[4],
        "options": json.loads(row[5]),
        "difficulty": row[3],
        "source": row[8]
    }

def compute_rank(acc):
    if acc >= 0.9: return "Iron Man"
    if acc >= 0.75: return "A"
    if acc >= 0.6: return "B"
    if acc >= 0.4: return "C"
    return "D"

# -------------------------------------------------------------
# API Endpoints
# -------------------------------------------------------------
@app.get("/")
def root():
    return {"message": "SAGE Universal API - Adaptive Exam Engine"}

@app.post("/sage/start")
def start(req: StartReq):
    session_id = str(uuid.uuid4())
    start_time = time.time()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO sessions (session_id, user_id, exam_pattern, difficulty, score, count, start_time, status)
        VALUES (?,?,?,?,?,?,?,?)
    """, (session_id, req.user_id, req.exam_pattern, req.difficulty, 0, 0, start_time, "active"))
    conn.commit()
    conn.close()
    q = get_question(req.subjects, req.difficulty)
    if not q:
        raise HTTPException(404, f"No questions found for subjects {req.subjects} at {req.difficulty} difficulty.")
    return {"session_id": session_id, "question": q, "total_questions": req.num_questions}

@app.post("/sage/answer")
def answer(req: AnswerReq):
    conn = get_conn()
    cur = conn.cursor()
    sess = cur.execute("SELECT * FROM sessions WHERE session_id=?", (req.session_id,)).fetchone()
    if not sess:
        raise HTTPException(404, "Session not found")
    q = cur.execute("SELECT * FROM questions WHERE id=?", (req.question_id,)).fetchone()
    if not q:
        raise HTTPException(404, "Question not found")
    is_correct = req.answer.strip().upper() == q[6]
    new_score = sess[4] + (1 if is_correct else 0)
    new_count = sess[5] + 1
    cur.execute("UPDATE sessions SET score=?, count=? WHERE session_id=?", (new_score, new_count, req.session_id))
    conn.commit()
    acc = new_score / new_count if new_count else 0
    if acc > 0.7:
        next_diff = "hard"
    elif acc > 0.4:
        next_diff = "medium"
    else:
        next_diff = "easy"
    # For simplicity, we assume subjects are stored as JSON in session; but for brevity, we use previous subject
    # You can extend this as needed.
    next_q = get_question([q[1]], next_diff)  # using the same subject as current question
    if not next_q:
        next_q = get_question([q[1]], "medium")
    conn.close()
    return {
        "correct": is_correct,
        "explanation": q[7],
        "score": new_score,
        "questions_attempted": new_count,
        "next_question": next_q
    }

@app.post("/sage/end")
def end(req: EndReq):
    conn = get_conn()
    cur = conn.cursor()
    sess = cur.execute("SELECT * FROM sessions WHERE session_id=?", (req.session_id,)).fetchone()
    if not sess:
        raise HTTPException(404, "Session not found")
    duration = time.time() - sess[6]
    total_q = sess[5]
    score = sess[4]
    acc = score / total_q if total_q > 0 else 0
    rank = compute_rank(acc)
    cur.execute("UPDATE sessions SET status='ended' WHERE session_id=?", (req.session_id,))
    conn.commit()
    conn.close()
    return {
        "score": score,
        "questions_attempted": total_q,
        "accuracy": round(acc, 4),
        "rank": rank,
        "time_seconds": round(duration, 2),
        "time_minutes": round(duration / 60, 2)
    }

@app.post("/sage/insert")
def insert_bulk(req: BulkInsertReq):
    conn = get_conn()
    cur = conn.cursor()
    inserted = 0
    for q in req.data:
        qid = str(uuid.uuid4())
        try:
            cur.execute("""
                INSERT INTO questions (id, subject, topic, difficulty, text, options, correct, explanation, source)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (qid,
                  q.get("subject", "General"),
                  q.get("topic", "general"),
                  q.get("difficulty", "medium"),
                  q["text"],
                  json.dumps(q.get("options", {})),
                  q.get("correct", "A"),
                  q.get("explanation", ""),
                  q.get("source", "manual")))
            inserted += 1
        except Exception as e:
            print(f"Insert error: {e}")
    conn.commit()
    conn.close()
    return {"status": f"Inserted {inserted} questions"}

# -------------------------------------------------------------
# NEW endpoint: add a single question interactively
# -------------------------------------------------------------
@app.post("/sage/add_question")
def add_question(req: AddQuestionReq):
    conn = get_conn()
    cur = conn.cursor()
    qid = str(uuid.uuid4())
    try:
        cur.execute("""
            INSERT INTO questions (id, subject, topic, difficulty, text, options, correct, explanation, source)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (qid, req.subject, req.topic, req.difficulty, req.text,
              json.dumps(req.options), req.correct, req.explanation, req.source))
        conn.commit()
        return {"status": "success", "question_id": qid}
    except Exception as e:
        raise HTTPException(500, f"Failed to insert: {e}")
    finally:
        conn.close()

# -------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("sage_api:app", host="0.0.0.0", port=8000, reload=True)