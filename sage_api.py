import pdfplumber
import requests
import json
import os

# ------------------------------------------------------------
# CONFIGURATION – CHANGE THESE TWO LINES
# ------------------------------------------------------------
API_BASE = "https://your-api-name.onrender.com"   # Your Render URL
PDF_FOLDER = "pdfs"                               # Folder containing your PDF files
# ------------------------------------------------------------

def extract_text_from_pdf(pdf_path):
    """Extract all text from a PDF file."""
    full_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"
    return full_text

def process_pdf(pdf_path, topic="civil_engineering"):
    print(f"Processing: {pdf_path}")
    raw_text = extract_text_from_pdf(pdf_path)
    
    # Step 1: Parse the raw text using your API
    parse_resp = requests.post(f"{API_BASE}/sage/parse-pdf", json={
        "raw_text": raw_text,
        "topic": topic
    })
    if parse_resp.status_code != 200:
        print(f"  Parse failed: {parse_resp.status_code} – {parse_resp.text}")
        return 0
    
    parsed = parse_resp.json()
    questions = parsed.get("parsed_questions", [])
    if not questions:
        print("  No questions found in this PDF.")
        return 0
    
    # Step 2: Insert questions into database
    insert_payload = {"data": questions}
    insert_resp = requests.post(f"{API_BASE}/sage/insert", json=insert_payload)
    if insert_resp.status_code == 200:
        result = insert_resp.json()
        inserted = result.get("status", "")
        print(f"  {inserted}")
        return len(questions)
    else:
        print(f"  Insert failed: {insert_resp.status_code}")
        return 0

def main():
    if not os.path.exists(PDF_FOLDER):
        os.makedirs(PDF_FOLDER)
        print(f"Created folder '{PDF_FOLDER}'. Place your PDF files there and run again.")
        return
    
    pdf_files = [f for f in os.listdir(PDF_FOLDER) if f.lower().endswith('.pdf')]
    if not pdf_files:
        print(f"No PDF files found in '{PDF_FOLDER}'. Add your SSC JE/ESE PDFs there.")
        return
    
    total_questions = 0
    for pdf_file in pdf_files:
        pdf_path = os.path.join(PDF_FOLDER, pdf_file)
        q_count = process_pdf(pdf_path)
        total_questions += q_count
    
    print(f"\n✅ Done! Total questions inserted: {total_questions}")
class PDFTextReq(BaseModel):
    raw_text: str
    topic: str = "general"

@app.post("/sage/parse-pdf")
def parse_pdf(req: PDFTextReq):
    """
    Extract MCQs from raw PDF text that follows format:
    Q{number}. ... A) ... B) ... C) ... D) ... Correct Answer: X
    """
    pattern = r"(Q\d+\..*?Correct Answer:\s*([A-D]))"
    matches = re.findall(pattern, req.raw_text, re.DOTALL)
    parsed = []
    for block, ans in matches:
        # Extract question text (everything before first A) )
        q_text = re.split(r"A\)", block)[0]
        q_text = re.sub(r"Q\d+\.", "", q_text).strip()
        # Extract options
        options = re.findall(r"([A-D])\)\s*(.*?)(?=[A-D]\)|$)", block, re.DOTALL)
        opt_dict = {k: v.strip() for k, v in options[:4] if k in "ABCD"}
        if not opt_dict:
            continue
        parsed.append({
            "topic": req.topic,
            "difficulty": "medium",   # default; you can adjust later
            "text": q_text,
            "options": opt_dict,
            "correct": ans,
            "source": "pyq_pdf"
        })
    return {"parsed_questions": parsed}
if __name__ == "__main__":
    main()