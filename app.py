from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import List

# Import our Brain and our Rulebook
from user_input import (
    load_pickles, 
    tfidf_recommend_titles, 
    attach_tmdb_card_by_title,
    tmdb_search_first,
)
from schemas import (
    TMDBMovieDetails, 
    TFIDFRecItem, 
    SearchBundleResponse
)

# ============================================================
# 1. APP INITIALIZATION & MIDDLEWARE
# ============================================================
app = FastAPI(title="Movie Recommender API", version="3.0")

# BACKSTORY: Browsers block frontend (Streamlit, port 8501) from talking 
# to backend (FastAPI, port 8000) for security. CORS is the "bouncer" 
# that says "It's okay, I trust this frontend."
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all (use specific URLs in real production)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# 2. STARTUP EVENT
# ============================================================
# BACKSTORY: This runs exactly ONCE when you type 'uvicorn app:app --reload'.
# It's the perfect time to load heavy .pkl files into RAM before any user arrives.
@app.on_event("startup")
def startup_event():
    print("Loading ML models into memory...")
    load_pickles()
    print("Models loaded successfully!")

# ============================================================
# 3. API ROUTES (The Endpoints)
# ============================================================

@app.get("/health")
def health_check():
    """Simple ping to check if the server is alive."""
    return {"status": "ok", "message": "API is running smoothly!"}

@app.get("/recommend/tfidf")
async def recommend_tfidf(title: str = Query(..., min_length=1), top_n: int = Query(10, ge=1, le=50)):
    """Pure local TF-IDF recommendations (no TMDB posters attached)."""
    recs = tfidf_recommend_titles(title, top_n=top_n)
    return [{"title": t, "score": round(s, 4)} for t, s in recs]

@app.get("/movie/search", response_model=SearchBundleResponse)
async def search_bundle(
    query: str = Query(..., min_length=1),
    tfidf_top_n: int = Query(5, ge=1, le=30),
):
    """
    THE MAIN EVENT: 
    1. Finds the movie on TMDB.
    2. Gets local TF-IDF recommendations and attaches TMDB posters to them.
    3. Returns everything in one neat package for Streamlit.
    """
    # 1. Get best match from TMDB
    best = await tmdb_search_first(query)
    if not best:
        raise HTTPException(status_code=404, detail=f"No movie found for: {query}")
    
    tmdb_id = int(best["id"])
    
    # Build the details object
    details = TMDBMovieDetails(
        tmdb_id=tmdb_id,
        title=best.get("title", ""),
        overview=best.get("overview"),
        release_date=best.get("release_date"),
        poster_url=f"https://image.tmdb.org/t/p/w500{best.get('poster_path')}" if best.get('poster_path') else None,
        backdrop_url=f"https://image.tmdb.org/t/p/original{best.get('backdrop_path')}" if best.get('backdrop_path') else None,
        genres=[] # Simplified for this example
    )

    # 2. Get Local TF-IDF Recommendations & attach posters
    tfidf_items: List[TFIDFRecItem] = []
    try:
        recs = tfidf_recommend_titles(details.title, top_n=tfidf_top_n)
        for title, score in recs:
            # This is the magic: we search TMDB for the local title to get its poster!
            card = await attach_tmdb_card_by_title(title)
            tfidf_items.append(TFIDFRecItem(title=title, score=round(score, 4), tmdb=card))
    except Exception as e:
        print(f"TF-IDF fallback error: {e}")

    # 3. Return the bundled response
    return SearchBundleResponse(
        query=query,
        movie_details=details,
        tfidf_recommendations=tfidf_items,
        genre_recommendations=[] # Can be added later using TMDB /discover endpoint
    )