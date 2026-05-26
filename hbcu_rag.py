#!/usr/bin/env python3
"""
hbcu_rag.py

Core RAG engine for HBCU AI.

Two-model pattern (mirrors CommPilot):
  CLASSIFIER_MODEL  — lightweight pass: understands the query, rewrites it
                      for retrieval, detects language
  ANSWER_MODEL      — generates the final grounded response from context

Commands:
  python hbcu_rag.py index  --kb kb/hbcu
  python hbcu_rag.py search --kb kb/hbcu --query "nursing programs in Alabama"
  python hbcu_rag.py answer --kb kb/hbcu --query "What HBCUs offer nursing in Virginia?"
"""

import argparse
import json
import os
import re
import sqlite3
import textwrap
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL       = "google/gemma-3-27b-it"
API_KEY_PATH        = Path("openrouter_api_key.txt")


def get_api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if key:
        return key
    if API_KEY_PATH.exists():
        return API_KEY_PATH.read_text(encoding="utf-8").strip()
    raise RuntimeError(
        "OpenRouter API key not found. Set OPENROUTER_API_KEY env var or create openrouter_api_key.txt"
    )


# ---------------------------------------------------------------------------
# Text utilities
# ---------------------------------------------------------------------------

def clean_text(value: str) -> str:
    if value is None:
        return ""
    replacements = [
        ("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"'),
        (" ", " "), ("–", "-"), ("—", "-"), ("�", ""),
    ]
    for old, new in replacements:
        value = value.replace(old, new)
    return value


def normalize_search_query(query: str) -> str:
    query = clean_text(query).lower()
    query = re.sub(r"[^a-z0-9.\s]+", " ", query)
    stopwords = {
        "what", "is", "are", "was", "were", "be", "been", "being",
        "the", "a", "an", "of", "on", "for", "to", "and", "or",
        "in", "at", "by", "with", "from", "as", "that", "this",
        "these", "those", "does", "do", "did", "about", "tell",
        "me", "explain", "hbcu", "hbcus", "college", "university",
        "school", "historically", "black",
        "give", "show", "list", "find", "get", "want", "need",
        "looking", "look", "can", "you", "i", "my", "all", "every",
        "some", "which", "where", "how", "who", "any", "have", "has",
    }
    terms = [t for t in query.split() if t not in stopwords and len(t) > 1]
    return " ".join(terms)


def save_run(kb_dir: Path, prefix: str, payload: dict):
    runs_dir = kb_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_path = runs_dir / f"{prefix}-{timestamp}.json"
    run_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return run_path


# ---------------------------------------------------------------------------
# School JSON → searchable text
# ---------------------------------------------------------------------------

def school_to_text(data: dict) -> str:
    lines = []

    name        = data.get("name", "")
    state       = data.get("state", "")
    school_type = data.get("type", "")
    founded     = data.get("year_founded", "")
    enrollment  = data.get("enrollment", "")
    status      = data.get("status", "open")

    lines.append(f"{name} is a {school_type} HBCU located in {state}.")
    if founded:
        lines.append(f"Founded in {founded}.")
    if enrollment and enrollment not in ("Not found",):
        lines.append(f"Total enrollment: {enrollment} students.")

    tuition = data.get("tuition", {})
    t_in  = tuition.get("in_state")
    t_out = tuition.get("out_of_state")
    t_rb  = tuition.get("room_board")
    if t_in and t_in not in ("Not found",):
        if t_in == t_out:
            fmt = f"${t_in:,}" if isinstance(t_in, int) else f"${t_in}"
            lines.append(f"Tuition: {fmt} per year.")
        else:
            in_fmt  = f"${t_in:,}"  if isinstance(t_in,  int) else f"${t_in}"
            out_fmt = f"${t_out:,}" if isinstance(t_out, int) else f"${t_out}"
            lines.append(f"In-state tuition: {in_fmt} per year. Out-of-state tuition: {out_fmt} per year.")
    if t_rb and t_rb not in ("Not found",):
        rb_fmt = f"${t_rb:,}" if isinstance(t_rb, int) else f"${t_rb}"
        lines.append(f"Room and board: {rb_fmt} per year.")

    programs = data.get("academics", {}).get("programs", [])
    if programs:
        lines.append(f"Popular majors and programs: {', '.join(programs)}.")

    student_body = data.get("academics", {}).get("student_body", "")
    if student_body:
        lines.append(f"Student body: {student_body}.")

    addr       = data.get("address", {})
    city       = addr.get("city", "")
    state_abbr = addr.get("state_abbr", "")
    if city and state_abbr:
        lines.append(f"Location: {city}, {state_abbr}.")

    contacts  = data.get("contacts", {})
    website   = contacts.get("website", "")
    phone     = contacts.get("main_phone", "")
    adm_phone = contacts.get("admissions_phone", "")
    adm_email = contacts.get("admissions_email", "")
    fa_phone  = contacts.get("financial_aid_phone", "")
    fa_email  = contacts.get("financial_aid_email", "")

    if website:   lines.append(f"Website: {website}")
    if phone     and phone     not in ("Not found",): lines.append(f"Main phone: {phone}")
    if adm_phone and adm_phone not in ("Not found",): lines.append(f"Admissions phone: {adm_phone}")
    if adm_email and adm_email not in ("Not found",): lines.append(f"Admissions email: {adm_email}")
    if fa_phone  and fa_phone  not in ("Not found",): lines.append(f"Financial aid phone: {fa_phone}")
    if fa_email  and fa_email  not in ("Not found",): lines.append(f"Financial aid email: {fa_email}")

    if status and status != "open":
        lines.append(f"Note: This institution's current status is {status}.")

    fed = data.get("federally_recognized")
    if fed is False:
        note = data.get("hbcu_designation_note",
                        "This institution is not on the U.S. Department of Education's official HBCU designation list.")
        lines.append(f"Federal HBCU designation: NOT on the U.S. Dept of Education official list. {note}")
    elif fed is True:
        lines.append("Federal HBCU designation: Officially recognized by the U.S. Department of Education.")

    region = data.get("region", "")
    if region:
        lines.append(f"Region: {region}.")

    level = data.get("institution_level", "")
    if level:
        lines.append(f"Institution level: {level}.")

    coords = data.get("coordinates", {})
    if coords.get("lat") and coords.get("lon"):
        lines.append(f"Coordinates: {coords['lat']}, {coords['lon']}.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------

def build_index(kb_dir: Path):
    index_dir = kb_dir / "index"
    index_dir.mkdir(parents=True, exist_ok=True)
    db_path = index_dir / "hbcu_fts.db"

    school_files = sorted(kb_dir.glob("*.json"))
    if not school_files:
        raise SystemExit(f"No JSON files found in {kb_dir}")

    records = []
    for path in school_files:
        data = json.loads(path.read_text(encoding="utf-8"))
        records.append({
            "filename":  path.name,
            "school_id": data.get("school_id", path.stem),
            "name":      data.get("name", ""),
            "state":     data.get("state", ""),
            "type":      data.get("type", ""),
            "programs":  ", ".join(data.get("academics", {}).get("programs", [])),
            "website":   data.get("contacts", {}).get("website", ""),
            "status":    data.get("status", "open"),
            "text":      school_to_text(data),
        })

    conn = sqlite3.connect(db_path)
    cur  = conn.cursor()

    cur.execute("DROP TABLE IF EXISTS schools")
    cur.execute("DROP TABLE IF EXISTS school_fts")

    cur.execute("""
        CREATE TABLE schools (
            id INTEGER PRIMARY KEY,
            filename TEXT NOT NULL,
            school_id TEXT,
            name TEXT,
            state TEXT,
            type TEXT,
            programs TEXT,
            website TEXT,
            status TEXT,
            text TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE VIRTUAL TABLE school_fts USING fts5(
            name, state, type, programs, text,
            content='schools', content_rowid='id'
        )
    """)

    for rec in records:
        cur.execute(
            "INSERT INTO schools (filename,school_id,name,state,type,programs,website,status,text) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (rec["filename"], rec["school_id"], rec["name"], rec["state"],
             rec["type"], rec["programs"], rec["website"], rec["status"], rec["text"]),
        )

    cur.execute("""
        INSERT INTO school_fts(rowid,name,state,type,programs,text)
        SELECT id,name,state,type,programs,text FROM schools
    """)

    conn.commit()
    conn.close()
    print(f"Indexed {len(records)} schools → {db_path}")
    return db_path


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def _run_fts(cur, query: str, top_k: int):
    cur.execute("""
        SELECT schools.filename, schools.school_id, schools.name, schools.state,
               schools.type, schools.programs, schools.website, schools.status, schools.text,
               snippet(school_fts, 4, '[', ']', '...', 48) AS snippet,
               bm25(school_fts) AS rank
        FROM school_fts
        JOIN schools ON schools.id = school_fts.rowid
        WHERE school_fts MATCH ?
        ORDER BY rank
        LIMIT ?
    """, (query, top_k))
    return [dict(row) for row in cur.fetchall()]


def search_index(kb_dir: Path, query: str, top_k: int = 5):
    db_path = kb_dir / "index" / "hbcu_fts.db"
    if not db_path.exists():
        raise SystemExit(f"Index not found: {db_path}. Run: python hbcu_rag.py index --kb {kb_dir}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur  = conn.cursor()

    safe = normalize_search_query(query)
    if not safe:
        safe = " ".join(re.findall(r"[A-Za-z0-9]+", clean_text(query)))

    rows = []
    for attempt in [
        safe,
        " OR ".join(safe.split()) if len(safe.split()) > 1 else None,
        " OR ".join(f'"{t}"' for t in safe.split()) if safe.split() else None,
    ]:
        if attempt and not rows:
            try:
                rows = _run_fts(cur, attempt, top_k)
            except sqlite3.OperationalError:
                pass

    conn.close()
    return rows


def filter_by_enrollment(kb_dir: Path, enrollment_min=None, enrollment_max=None,
                          state_filter=None, type_filter=None, top_k: int = 5) -> list:
    """Scan school JSON files and return those matching enrollment bounds."""
    results = []
    for path in sorted(kb_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("status") == "closed":
            continue

        enrollment = data.get("enrollment")
        if not isinstance(enrollment, (int, float)):
            continue
        enrollment = int(enrollment)

        if enrollment_max is not None and enrollment > enrollment_max:
            continue
        if enrollment_min is not None and enrollment < enrollment_min:
            continue

        if state_filter:
            school_state = data.get("state", "").lower()
            if state_filter.lower() not in school_state:
                continue

        if type_filter:
            if data.get("type", "").lower() != type_filter.lower():
                continue

        results.append((enrollment, path, data))

    # Sort smallest-first for "under X" queries, largest-first for "over X"
    reverse = enrollment_min is not None and enrollment_max is None
    results.sort(key=lambda x: x[0], reverse=reverse)

    blocks = []
    for enrollment, path, data in results[:top_k]:
        blocks.append({
            "filename":             path.name,
            "school_id":            data.get("school_id", path.stem),
            "name":                 data.get("name", ""),
            "state":                data.get("state", ""),
            "type":                 data.get("type", ""),
            "programs":             ", ".join(data.get("academics", {}).get("programs", [])),
            "website":              data.get("contacts", {}).get("website", ""),
            "status":               data.get("status", "open"),
            "snippet":              f"Enrollment: {enrollment} students.",
            "excerpt":              school_to_text(data),
            "federally_recognized": data.get("federally_recognized"),
            "hbcu_designation_note":data.get("hbcu_designation_note", ""),
            "region":               data.get("region", ""),
            "institution_level":    data.get("institution_level", ""),
            "coordinates":          data.get("coordinates", {}),
            "enrollment":           enrollment,
            "tuition":              data.get("tuition", {}),
        })
    return blocks


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math
    R = 3958.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def filter_by_proximity(kb_dir: Path, lat: float, lon: float,
                         nearby_states: list = None, top_k: int = 5,
                         type_filter: str = None, program_filter: str = None) -> list:
    """Return open schools sorted by distance from (lat, lon), optionally filtered to nearby_states."""
    results = []
    state_set = {s.lower() for s in nearby_states} if nearby_states else None

    for path in sorted(kb_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("status") == "closed":
            continue

        coords = data.get("coordinates", {})
        slat, slon = coords.get("lat"), coords.get("lon")
        if slat is None or slon is None:
            continue

        if state_set:
            school_state = data.get("state", "").lower()
            if not any(s in school_state for s in state_set):
                continue

        if type_filter and data.get("type", "").lower() != type_filter.lower():
            continue

        if program_filter:
            programs = " ".join(data.get("academics", {}).get("programs", [])).lower()
            if program_filter.lower() not in programs:
                continue

        distance = _haversine_miles(lat, lon, slat, slon)
        results.append((distance, path, data))

    results.sort(key=lambda x: x[0])

    blocks = []
    for distance, path, data in results[:top_k]:
        blocks.append({
            "filename":             path.name,
            "school_id":            data.get("school_id", path.stem),
            "name":                 data.get("name", ""),
            "state":                data.get("state", ""),
            "type":                 data.get("type", ""),
            "programs":             ", ".join(data.get("academics", {}).get("programs", [])),
            "website":              data.get("contacts", {}).get("website", ""),
            "status":               data.get("status", "open"),
            "snippet":              f"Approximately {int(distance)} miles away.",
            "excerpt":              school_to_text(data),
            "federally_recognized": data.get("federally_recognized"),
            "hbcu_designation_note":data.get("hbcu_designation_note", ""),
            "region":               data.get("region", ""),
            "institution_level":    data.get("institution_level", ""),
            "coordinates":          data.get("coordinates", {}),
            "enrollment":           data.get("enrollment"),
            "tuition":              data.get("tuition", {}),
            "distance_miles":       int(distance),
        })
    return blocks


def build_context_blocks(kb_dir: Path, query: str, top_k: int, max_chars: int = 2200,
                          classification: dict = None):
    if classification:
        # Proximity query — sort by distance from referenced location
        if classification.get("proximity_query") and classification.get("proximity_lat") and classification.get("proximity_lon"):
            return filter_by_proximity(
                kb_dir=kb_dir,
                lat=classification["proximity_lat"],
                lon=classification["proximity_lon"],
                nearby_states=classification.get("nearby_states"),
                top_k=top_k,
                type_filter=classification.get("type_filter"),
                program_filter=classification.get("program_filter"),
            )

        # Enrollment bounds — direct JSON filtering
        enroll_max = classification.get("enrollment_max")
        enroll_min = classification.get("enrollment_min")
        if enroll_max is not None or enroll_min is not None:
            return filter_by_enrollment(
                kb_dir=kb_dir,
                enrollment_min=enroll_min,
                enrollment_max=enroll_max,
                state_filter=classification.get("state_filter"),
                type_filter=classification.get("type_filter"),
                top_k=top_k,
            )

    results = search_index(kb_dir, query, top_k)
    blocks  = []
    for row in results:
        # Load the original JSON to get fields not stored in FTS
        school_path = kb_dir / row.get("filename", "")
        extra = {}
        if school_path.exists():
            raw = json.loads(school_path.read_text(encoding="utf-8"))
            extra = {
                "federally_recognized": raw.get("federally_recognized"),
                "hbcu_designation_note": raw.get("hbcu_designation_note", ""),
                "region":               raw.get("region", ""),
                "institution_level":    raw.get("institution_level", ""),
                "coordinates":          raw.get("coordinates", {}),
                "enrollment":           raw.get("enrollment"),
                "tuition":              raw.get("tuition", {}),
            }
        blocks.append({
            "filename":  row.get("filename", ""),
            "school_id": row.get("school_id", ""),
            "name":      row.get("name", ""),
            "state":     row.get("state", ""),
            "type":      row.get("type", ""),
            "programs":  row.get("programs", ""),
            "website":   row.get("website", ""),
            "status":    row.get("status", ""),
            "snippet":   row.get("snippet", ""),
            "excerpt":   row.get("text", "")[:max_chars].strip(),
            **extra,
        })
    return blocks


# ---------------------------------------------------------------------------
# Model calls
# ---------------------------------------------------------------------------

def call_model(base_url: str, model: str, messages: list,
               api_key: str = "", temperature: float = 0.2, timeout: int = 180) -> str:
    url     = base_url.rstrip("/") + "/chat/completions"
    payload = {"model": model, "messages": messages, "temperature": temperature, "stream": False}
    data    = json.dumps(payload).encode("utf-8")

    auth_header = f"Bearer {api_key}" if api_key else "Bearer local-not-needed"

    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", "Authorization": auth_header},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} from model: {e.read().decode('utf-8', errors='replace')}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Could not reach model endpoint: {e}") from e
    except TimeoutError as e:
        raise RuntimeError(f"Model timed out after {timeout}s") from e

    try:
        return result["choices"][0]["message"]["content"]
    except KeyError as e:
        raise RuntimeError("Unexpected model response:\n" + json.dumps(result, indent=2)) from e


# ---------------------------------------------------------------------------
# CLASSIFIER MODEL — understands and rewrites the query for retrieval
# ---------------------------------------------------------------------------

def classify_query(query: str, base_url: str, model: str, api_key: str,
                   timeout: int = 60) -> dict:
    """
    Uses the classifier model to:
      1. Rewrite the student's natural-language question into a terse
         retrieval query optimised for FTS keyword search
      2. Identify key search dimensions (state, type, programs, size)
      3. Detect proximity intent ("near X", "close to Y", "within driving distance")
      4. Detect language

    Returns a dict with: retrieval_query, detected_language, confidence,
    state_filter, type_filter, program_filter,
    enrollment_max, enrollment_min,
    proximity_query, proximity_lat, proximity_lon, nearby_states
    """
    system = """You are a query understanding assistant for an HBCU (Historically Black College and University) database.

Given a student's question, return ONLY valid JSON with these exact keys:
  retrieval_query   - a short English keyword string for full-text search (remove filler words, keep nouns/subjects). If the question is only about enrollment size with no other topic, use "HBCU enrollment students".
  detected_language - the language of the original question (English, Spanish, French, Haitian Creole, or Unknown)
  confidence        - your confidence level: high, medium, or low
  state_filter      - US state name if the question asks about a specific state, else null
  type_filter       - "public" or "private" if specified, else null
  program_filter    - main academic program/major mentioned, else null
  enrollment_max    - integer upper bound on enrollment if mentioned (e.g. "under 2000" → 2000), else null
  enrollment_min    - integer lower bound on enrollment if mentioned (e.g. "over 5000" → 5000), else null
  return_all        - true if the student is asking for ALL schools matching a criterion (e.g. "all law schools", "all schools in Texas", "every HBCU in Virginia"), else false
  proximity_query   - true if the question asks about proximity/location ("near", "close to", "within driving distance", "around", "in the area of"), else false
  proximity_lat     - decimal latitude of the referenced city/state if proximity_query is true, else null
  proximity_lon     - decimal longitude of the referenced city/state if proximity_query is true, else null
  nearby_states     - list of US state names that border or are very close to the referenced location (include the state itself if named), else null

Example input: "What affordable HBCUs in Virginia offer nursing?"
Example output:
{
  "retrieval_query": "nursing Virginia affordable tuition",
  "detected_language": "English",
  "confidence": "high",
  "state_filter": "Virginia",
  "type_filter": null,
  "program_filter": "Nursing",
  "enrollment_max": null,
  "enrollment_min": null,
  "return_all": false,
  "proximity_query": false,
  "proximity_lat": null,
  "proximity_lon": null,
  "nearby_states": null
}

Example input: "Give me all the law schools"
Example output:
{
  "retrieval_query": "law",
  "detected_language": "English",
  "confidence": "high",
  "state_filter": null,
  "type_filter": null,
  "program_filter": "Law",
  "enrollment_max": null,
  "enrollment_min": null,
  "return_all": true,
  "proximity_query": false,
  "proximity_lat": null,
  "proximity_lon": null,
  "nearby_states": null
}

Example input: "HBCUs near Indiana"
Example output:
{
  "retrieval_query": "HBCU Midwest",
  "detected_language": "English",
  "confidence": "high",
  "state_filter": null,
  "type_filter": null,
  "program_filter": null,
  "enrollment_max": null,
  "enrollment_min": null,
  "proximity_query": true,
  "proximity_lat": 39.7684,
  "proximity_lon": -86.1581,
  "nearby_states": ["Indiana", "Illinois", "Ohio", "Kentucky", "Michigan"]
}

Example input: "Small HBCUs under 2000 students"
Example output:
{
  "retrieval_query": "HBCU enrollment students",
  "detected_language": "English",
  "confidence": "high",
  "state_filter": null,
  "type_filter": null,
  "program_filter": null,
  "enrollment_max": 2000,
  "enrollment_min": null,
  "proximity_query": false,
  "proximity_lat": null,
  "proximity_lon": null,
  "nearby_states": null
}

Return ONLY the JSON object. No explanation, no markdown."""

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Student question:\n{query}"},
    ]

    raw = call_model(
        base_url=base_url, model=model, messages=messages,
        api_key=api_key, temperature=0.0, timeout=timeout,
    )

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                data = {}
        else:
            data = {}

    return {
        "retrieval_query":   data.get("retrieval_query", normalize_search_query(query)) or normalize_search_query(query),
        "detected_language": data.get("detected_language", "English") or "English",
        "confidence":        data.get("confidence", "low"),
        "state_filter":      data.get("state_filter"),
        "type_filter":       data.get("type_filter"),
        "program_filter":    data.get("program_filter"),
        "enrollment_max":    data.get("enrollment_max"),
        "enrollment_min":    data.get("enrollment_min"),
        "return_all":        bool(data.get("return_all", False)),
        "proximity_query":   bool(data.get("proximity_query", False)),
        "proximity_lat":     data.get("proximity_lat"),
        "proximity_lon":     data.get("proximity_lon"),
        "nearby_states":     data.get("nearby_states"),
        "raw":               raw,
    }


# ---------------------------------------------------------------------------
# ANSWER MODEL — generates grounded response from retrieved context
# ---------------------------------------------------------------------------

def build_answer_prompt(original_question: str, retrieval_question: str,
                        context_blocks: list, output_language: str = "English") -> list:
    context_text = ""
    for i, block in enumerate(context_blocks, 1):
        context_text += f"\n--- School {i}: {block['name']} ({block['state']}) ---\n"
        context_text += block["excerpt"] + "\n"

    lang_note = "" if output_language in ("English", "Unknown", "") else \
        f"\nIMPORTANT: Respond in {output_language}."

    system = f"""You are an expert advisor helping prospective students learn about Historically Black Colleges and Universities (HBCUs).

Answer the student's question using only the school information provided. Be specific — include school names, tuition figures, enrollment numbers, majors, and contact details when relevant.

If the answer cannot be determined from the provided information, say so honestly. Do not guess or invent data.

Keep your answer clear, warm, and encouraging. Students are making important decisions about their education.{lang_note}"""

    user = f"""Student question: {original_question}

School information:
{context_text}

Please answer the student's question based on the above information."""

    return [
        {"role": "system", "content": system},
        {"role": "user",   "content": user},
    ]


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

def index_command(args):
    build_index(Path(args.kb))


def search_command(args):
    results = search_index(Path(args.kb), args.query, args.top_k)
    if not results:
        print("No matches found.")
        print(f"Normalized: {normalize_search_query(args.query)}")
        return
    print(f"\nQuery: {args.query}")
    print(f"Normalized: {normalize_search_query(args.query)}\n")
    for i, row in enumerate(results, 1):
        print(f"{i}. {row['name']} — {row['state']}")
        print(f"   Programs: {row['programs']}")
        print(f"   Snippet: {row['snippet']}")
        print()


def answer_command(args):
    kb_dir  = Path(args.kb)
    api_key = get_api_key()

    print(f"[classifier] Analysing query with {args.classifier_model}...")
    classification = classify_query(
        query=args.query,
        base_url=args.base_url,
        model=args.classifier_model,
        api_key=api_key,
        timeout=args.timeout,
    )
    retrieval_query   = classification["retrieval_query"]
    detected_language = classification["detected_language"]
    print(f"[classifier] retrieval_query='{retrieval_query}' language={detected_language}")

    context_blocks = build_context_blocks(kb_dir, retrieval_query, args.top_k,
                                          classification=classification)
    if not context_blocks:
        print("No matching schools found.")
        return

    print(f"[retrieval]  {len(context_blocks)} schools matched")
    print(f"[answer]     Generating response with {args.answer_model}...\n")

    messages = build_answer_prompt(
        original_question=args.query,
        retrieval_question=retrieval_query,
        context_blocks=context_blocks,
        output_language=detected_language,
    )

    answer = call_model(
        base_url=args.base_url,
        model=args.answer_model,
        messages=messages,
        api_key=api_key,
        temperature=args.temperature,
        timeout=args.timeout,
    )

    print("ANSWER")
    print("=" * 60)
    print(textwrap.fill(answer, width=100))

    save_run(kb_dir, "answer_cli", {
        "created_at":       datetime.now().isoformat(timespec="seconds"),
        "original_query":   args.query,
        "retrieval_query":  retrieval_query,
        "detected_language": detected_language,
        "classification":   classification,
        "classifier_model": args.classifier_model,
        "answer_model":     args.answer_model,
        "context":          context_blocks,
        "answer":           answer,
    })


def main():
    parser = argparse.ArgumentParser(description="HBCU AI — RAG over HBCU data")
    sub    = parser.add_subparsers(dest="command", required=True)

    p_index = sub.add_parser("index", help="Build FTS index from school JSON files")
    p_index.add_argument("--kb", default="kb/hbcu")
    p_index.set_defaults(func=index_command)

    p_search = sub.add_parser("search", help="Search the index")
    p_search.add_argument("--kb", default="kb/hbcu")
    p_search.add_argument("--query", required=True)
    p_search.add_argument("--top-k", type=int, default=5)
    p_search.set_defaults(func=search_command)

    p_answer = sub.add_parser("answer", help="Classify query + retrieve + generate answer")
    p_answer.add_argument("--kb",               default="kb/hbcu")
    p_answer.add_argument("--query",            required=True)
    p_answer.add_argument("--classifier-model", default=DEFAULT_MODEL)
    p_answer.add_argument("--answer-model",     default=DEFAULT_MODEL)
    p_answer.add_argument("--base-url",         default=OPENROUTER_BASE_URL)
    p_answer.add_argument("--top-k",            type=int,   default=5)
    p_answer.add_argument("--temperature",      type=float, default=0.2)
    p_answer.add_argument("--timeout",          type=int,   default=180)
    p_answer.set_defaults(func=answer_command)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
