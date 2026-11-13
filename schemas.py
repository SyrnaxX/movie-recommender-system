# The Rule Book
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

## TMDB DATA MODELS (What we get from the internet)
class TMDBMovieCard(BaseModel):
    tmdb_id : int
    title : str
    poster_url : Optional[str] = None
    release_date : Optional[str] = None
    vote_average : Optional[float] = None
class TMDBMovieDetails(BaseModel):
    """Movie details returned when a user selects a movie."""
    tmdb_id: int
    title: str
    overview: Optional[str] = None
    release_date: Optional[str] = None
    poster_url: Optional[str] = None
    backdrop_url: Optional[str] = None
    genres: List[Dict[str, Any]] = Field(default_factory=list)

# Recommendation Models
class TFIDFRecItem(BaseModel):
    title: str
    score: float
    tmdb: Optional[TMDBMovieCard] = None

# Bundle Response
class SearchBundleResponse(BaseModel):
    query: str
    movie_details: TMDBMovieDetails
    tfidf_recommendations: List[TFIDFRecItem]
    genre_recommendations: List[TMDBMovieCard]