import pdfplumber
import requests
import json
import os

API_BASE = "https://your-api-name.onrender.com"   # Replace with your actual Render URL
PDF_FOLDER = "pdfs"   # folder where you put your PDF files

def extract_text_from_pdf(pdf_path):
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
    
    # Call your API's /sage/parse-pdf endpoint
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
    
    # Insert questions into your database
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

if __name__ == "__main__":
    main()