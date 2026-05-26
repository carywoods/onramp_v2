"""
Flask web server for HBCU AI.

Usage:
    flask run --host=0.0.0.0 --port=5000
    gunicorn --bind 0.0.0.0:5000 app:app

Environment variables:
    KB_DIR            path to school JSON files (default: kb/hbcu)
    BASE_URL          OpenAI-compatible endpoint (default: OpenRouter)
    CLASSIFIER_MODEL  model for query understanding (default: google/gemma-3-27b-it)
    ANSWER_MODEL      model for response generation (default: google/gemma-3-27b-it)
    TOP_K             number of schools to retrieve (default: 5)
    OPENROUTER_API_KEY  overrides openrouter_api_key.txt
"""

import os
import smtplib
import ssl
from datetime import datetime
from email.mime.text import MIMEText
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from hbcu_rag import (
    OPENROUTER_BASE_URL,
    DEFAULT_MODEL,
    build_answer_prompt,
    build_context_blocks,
    call_model,
    classify_query,
    get_api_key,
    normalize_search_query,
    save_run,
)

app = Flask(__name__)

KB_DIR           = Path(os.environ.get("KB_DIR", "kb/hbcu"))
BASE_URL         = os.environ.get("BASE_URL", OPENROUTER_BASE_URL)
CLASSIFIER_MODEL = os.environ.get("CLASSIFIER_MODEL", DEFAULT_MODEL)
ANSWER_MODEL     = os.environ.get("ANSWER_MODEL",     DEFAULT_MODEL)
TOP_K            = int(os.environ.get("TOP_K", 5))

SMTP_HOST        = os.environ.get("SMTP_HOST", "")
SMTP_PORT        = int(os.environ.get("SMTP_PORT", 465))
SMTP_USER        = os.environ.get("SMTP_USER", "")
SMTP_PASS        = os.environ.get("SMTP_PASS", "")
SUGGEST_FROM     = os.environ.get("SUGGEST_FROM", SMTP_USER)
SUGGEST_TO       = os.environ.get("SUGGEST_TO", "")


@app.route("/health")
def health():
    return jsonify({
        "status":           "ok",
        "service":          "hbcu-ai",
        "kb_dir":           str(KB_DIR),
        "classifier_model": CLASSIFIER_MODEL,
        "answer_model":     ANSWER_MODEL,
    })


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/team")
def team():
    return render_template("team.html")


@app.route("/api/search", methods=["POST"])
def search():
    data  = request.json
    query = data.get("query", "")
    top_k = data.get("top_k", TOP_K)

    if not query:
        return jsonify({"error": "Query is required"}), 400

    try:
        context_blocks = build_context_blocks(KB_DIR, query, top_k)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({
        "query":            query,
        "normalized_query": normalize_search_query(query),
        "results":          context_blocks,
    })


@app.route("/api/answer", methods=["POST"])
def answer():
    data             = request.json
    query            = data.get("query", "")
    classifier_model = data.get("classifier_model", CLASSIFIER_MODEL)
    answer_model     = data.get("answer_model",     ANSWER_MODEL)
    base_url         = data.get("base_url",         BASE_URL)
    top_k            = data.get("top_k",            TOP_K)
    temperature      = data.get("temperature",      0.2)
    timeout          = data.get("timeout",          180)

    if not query:
        return jsonify({"error": "Query is required"}), 400

    try:
        api_key = get_api_key()
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500

    # --- Stage 1: Classifier model understands and rewrites the query ---
    try:
        classification    = classify_query(
            query=query,
            base_url=base_url,
            model=classifier_model,
            api_key=api_key,
            timeout=timeout,
        )
        retrieval_query   = classification["retrieval_query"]
        detected_language = classification["detected_language"]
    except Exception as e:
        # Fallback: use basic normalisation if classifier fails
        retrieval_query   = normalize_search_query(query)
        detected_language = "English"
        classification    = {"error": str(e), "fallback": True}

    # --- Stage 2: FTS retrieval (or enrollment filter) using classifier output ---
    if classification.get("return_all"):
        top_k = 120  # return full KB when user asks for "all"
    try:
        context_blocks = build_context_blocks(KB_DIR, retrieval_query, top_k,
                                              classification=classification)
    except Exception as e:
        return jsonify({"error": f"Retrieval failed: {e}"}), 500

    if not context_blocks:
        return jsonify({
            "error":           "No matching schools found for that question.",
            "retrieval_query": retrieval_query,
            "classification":  classification,
        }), 404

    # --- Stage 3: Answer model generates grounded response ---
    messages = build_answer_prompt(
        original_question=query,
        retrieval_question=retrieval_query,
        context_blocks=context_blocks,
        output_language=detected_language,
    )

    try:
        answer_text = call_model(
            base_url=base_url,
            model=answer_model,
            messages=messages,
            api_key=api_key,
            temperature=temperature,
            timeout=timeout,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    try:
        save_run(KB_DIR, "answer_web", {
            "created_at":        datetime.now().isoformat(timespec="seconds"),
            "original_query":    query,
            "retrieval_query":   retrieval_query,
            "detected_language": detected_language,
            "classification":    classification,
            "classifier_model":  classifier_model,
            "answer_model":      answer_model,
            "top_k":             top_k,
            "temperature":       temperature,
            "context":           context_blocks,
            "answer":            answer_text,
        })
    except Exception as e:
        print(f"Warning: could not save run log: {e}")

    return jsonify({
        "answer":            answer_text,
        "context":           context_blocks,
        "retrieval_query":   retrieval_query,
        "detected_language": detected_language,
        "classifier_model":  classifier_model,
        "answer_model":      answer_model,
        "classification":    classification,
    })


@app.route("/api/suggest", methods=["POST"])
def suggest():
    data        = request.json
    school      = (data.get("school") or "").strip()
    field       = (data.get("field") or "").strip()
    correction  = (data.get("correction") or "").strip()
    submitter   = (data.get("email") or "").strip()

    if not school or not correction:
        return jsonify({"error": "School name and correction are required."}), 400

    body = f"""On Ramp — Data Correction Submission
{'=' * 50}
School:      {school}
Field:       {field or 'Not specified'}
Correction:  {correction}
Submitted by: {submitter or 'Anonymous'}
Timestamp:   {datetime.now().isoformat(timespec='seconds')}
"""

    try:
        msg = MIMEText(body)
        msg["Subject"] = f"On Ramp correction: {school}"
        msg["From"]    = SUGGEST_FROM
        msg["To"]      = SUGGEST_TO

        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx) as server:
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SUGGEST_FROM, SUGGEST_TO, msg.as_string())
    except Exception as e:
        print(f"[suggest] email error: {e}")
        return jsonify({"error": "Could not send submission. Please try again later."}), 500

    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
