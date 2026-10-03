from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


class ChatMessage(BaseModel):
    role: str
    text: str


class UserProfile(BaseModel):
    favorite_genres: List[str] = Field(default_factory=list)
    disliked_genres: List[str] = Field(default_factory=list)
    preferred_eras: List[str] = Field(default_factory=list)
    taste_description: Optional[str] = None


class MoodRequest(BaseModel):
    mood_text: str
    chat_history: List[ChatMessage] = Field(default_factory=list)
    user_profile: Optional[UserProfile] = None
    displayed_movie_ids: Optional[List[int]] = Field(default_factory=list)


class MovieCard(BaseModel):
    id: int
    title: str
    release_year: int
    imdb_rating: float
    runtime: int
    director: str
    director_of_photography: Optional[str] = "Unknown"
    music_composer: Optional[str] = "Unknown"
    poster_path: Optional[str] = None
    hybrid_summary: str


class ChattedRecommendationResponse(BaseModel):
    is_context_sufficient: bool
    ai_followup_chat: str
    recommendations: List[MovieCard] = Field(default_factory=list)


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str
    password: str = Field(..., min_length=6)


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    watcher_tier: str

    model_config = ConfigDict(from_attributes=True)


class WatchlistAction(BaseModel):
    user_id: int
    movie_id: int


class WatchedAction(BaseModel):
    user_id: int
    movie_id: int
    rating: Optional[float] = None
    critic_review: Optional[str] = None


class DislikeAction(BaseModel):
    user_id: int
    movie_id: int
    rejection_reason: str


class CompiledContextPayload(BaseModel):
    dense_search_query: str = Field(
        description="Dense continuous paragraph summarizing thematic, atmospheric, and stylistic preferences."
    )
    should_bypass_profile: bool = Field(
        description="True if the user requests something outside their typical taste profile."
    )