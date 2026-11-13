import os
from typing import Optional, List, Dict, Any, Tuple
import joblib
import numpy as np
import pandas as pd
import httpx
from fastapi import HTTPException
from dotenv import load_dotenv

# Import the schemas we just created
from schemas import TMDBMovieCard, TMDBMovieDetails, TFIDFRecItem

# ============================================================
# 1. ENVIRONMENT & GLOBAL VARIABLES
# ============================================================
load_dotenv()
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMG_500 = "https://image.tmdb.org/t/p/w500"

if not TMDB_API_KEY:
    raise RuntimeError("TMDB_API_KEY missing. Put it in .env as TMDB_API_KEY=xxxx")

# Global variables to hold our ML models in RAM
df: Optional[pd.DataFrame] = None
indices_obj: Any = None
tfidf_matrix: Any = None
TITLE_TO_IDX: Optional[Dict[str, int]] = None

# ============================================================
# 2. STARTUP: LOAD PICKLES (Runs ONCE when server starts)
# ============================================================
def load_pickles():
    """Loads all heavy files into global memory so requests are instant."""
    global df, indices_obj, tfidf_matrix, TITLE_TO_IDX
    
    # Find the folder where this file lives
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    
    df = joblib.load(os.path.join(BASE_DIR, "models", "data.pkl"))
    indices_obj = joblib.load(os.path.join(BASE_DIR, "models", "indices.pkl"))
    tfidf_matrix = joblib.load(os.path.join(BASE_DIR, "models", "tfidf_matrix.pkl"))

    # Build a fast lookup dictionary: {"avengers": 147, "toy story": 862}
    TITLE_TO_IDX = {}
    if isinstance(indices_obj, dict):
        for k, v in indices_obj.items():
            TITLE_TO_IDX[str(k).strip().lower()] = int(v)
    else:
        # Fallback if it's a Pandas Series
        for k, v in indices_obj.items():
            TITLE_TO_IDX[str(k).strip().lower()] = int(v)

# ============================================================
# 3. TMDB API HELPERS (Asynchronous for speed)
# ============================================================
def make_img_url(path: Optional[str]) -> Optional[str]:
    """Converts a partial TMDB path (e.g., '/abc.jpg') to a full URL."""
    if not path: return None
    return f"{TMDB_IMG_500}{path}"

async def tmdb_get(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    BACKSTORY: 'async' means while we wait for TMDB to reply, 
    the server can help other users. It doesn't freeze!
    """
    params["api_key"] = TMDB_API_KEY
    try:
        # httpx is the modern, async version of the 'requests' library
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(f"{TMDB_BASE}{path}", params=params)
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"TMDB network error: {e}")
    
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"TMDB API error: {r.text}")
    return r.json()

async def tmdb_search_first(query: str) -> Optional[dict]:
    """Searches TMDB and returns only the very first (best) match."""
    data = await tmdb_get("/search/movie", {"query": query, "language": "en-US", "page": 1})
    results = data.get("results", [])
    return results[0] if results else None

async def attach_tmdb_card_by_title(title: str) -> Optional[TMDBMovieCard]:
    """Takes a local movie title, searches TMDB, and returns a card with a poster."""
    try:
        m = await tmdb_search_first(title)
        if not m: return None
        return TMDBMovieCard(
            tmdb_id=int(m["id"]),
            title=m.get("title") or title,
            poster_url=make_img_url(m.get("poster_path")),
            release_date=m.get("release_date"),
            vote_average=m.get("vote_average"),
        )
    except Exception:
        return None # Fail silently so the whole app doesn't crash

# ============================================================
# 4. TF-IDF ML LOGIC
# ============================================================
def tfidf_recommend_titles(query_title: str, top_n: int = 10) -> List[Tuple[str, float]]:
    """Finds similar movies using cosine similarity on the pre-loaded matrix."""
    global df, tfidf_matrix, TITLE_TO_IDX
    
    # 1. Normalize the input (lowercase, strip spaces)
    key = str(query_title).strip().lower()
    if key not in TITLE_TO_IDX:
        raise HTTPException(status_code=404, detail=f"Movie '{query_title}' not found in local dataset")
    
    idx = TITLE_TO_IDX[key]
    
    # 2. Calculate Cosine Similarity
    # qv is the vector of our chosen movie. We multiply it by the whole matrix.
    qv = tfidf_matrix[idx]
    scores = (tfidf_matrix @ qv.T).toarray().ravel()
    
    # 3. Sort scores from highest to lowest
    order = np.argsort(-scores)
    
    # 4. Gather top N results, skipping the movie itself (idx)
    out: List[Tuple[str, float]] = []
    for i in order:
        if int(i) == int(idx):
            continue
        try:
            title_i = str(df.iloc[int(i)]["title"])
            out.append((title_i, float(scores[int(i)])))
            if len(out) >= top_n:
                break
        except Exception:
            continue
    return out