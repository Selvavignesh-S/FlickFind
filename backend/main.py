import os
import random
import traceback
from contextlib import asynccontextmanager
from typing import Optional, List

from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, text
from sqlalchemy.orm import Session
from google import genai
from google.genai import types

load_dotenv()

from schemas import (
    MoodRequest,
    ChattedRecommendationResponse,
    MovieCard,
    WatchlistAction,
    WatchedAction,
    DislikeAction,
    UserCreate,
    UserLogin,
    UserResponse,
    CompiledContextPayload,
)
from auth_utils import hash_user_password, verify_user_password
from ai_service import ai_engine
import database
import models

genai_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Cascade across available Gemini models if temporary 503 or 429 occurs
GEMINI_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-flash-latest",
    "gemini-3.8-flash",
]


def generate_gemini_content(contents, config=None):
    last_error = None
    for model_name in GEMINI_MODELS:
        try:
            return genai_client.models.generate_content(
                model=model_name,
                contents=contents,
                config=config,
            )
        except Exception as err:
            last_error = err
            error_str = str(err)
            if any(code in error_str for code in ["503", "404", "429", "UNAVAILABLE"]):
                continue
            raise err
    raise last_error


ALGORITHM_CONFIG = {
    "MIN_RATING": 6.0,
    "MIN_VOTES": 300,
    "MIN_RUNTIME": 60,
    "CANDIDATE_POOL_LIMIT": 35,
    "POPULARITY_MULTIPLIER": 0.05,
    "RATING_MULTIPLIER": 0.02,
    "LONG_TERM_PERSONA_WEIGHT": 0.3,
}

CONTEXT_COMPILER_PROMPT = (
    "You are an expert cinematic context extractor and routing gatekeeper. "
    "Review the following conversational stream history between a user and an AI film assistant.\n\n"
    "TASK 1: Extract all explicit and implicit movie preferences, emotional layers, pacing requests, "
    "atmospheres, visual descriptions and sonic elements mentioned across ALL turns of the dialogue "
    "into a single dense continuous search query paragraph for dense_search_query. "
    "Focus strictly on thematic elements, tone, and cinematic styles. "
    "Do not include introductory text.\n\n"
    "TASK 2: Evaluate should_bypass_profile. Set to true if the user explicitly or implicitly "
    "requests a change of pace, wants to ignore their profile, desires something completely "
    "new or different, or describes a direction that intentionally breaks from their usual preferences. "
    "Otherwise default to false.\n\n"
    "[CONVERSATION STREAM MEMORY]\n"
    "{formatted_history}"
)

CONCIERGE_SYSTEM_INSTRUCTION = (
    "You are FlickFind AI, a film recommendation engine that adapts to the user's unique cinema taste "
    "without any genre bias. You receive the full conversation history, a long-term user taste profile, "
    "and a candidate pool of mathematically matching movies from the local database.\n\n"
    "YOUR OBJECTIVE IS TO EXECUTE A SINGLE PASS EVALUATION:\n\n"
    "1. Context Sufficiency Check:\n"
    "   If the conversation lacks enough context (e.g. 'give me a movie'), set is_context_sufficient = false. "
    "   Ask targeted questions in ai_followup_chat. Leave recommendations empty.\n"
    "   If the context is concrete enough to pick films, set is_context_sufficient = true.\n\n"
    "2. Dynamic Profile Override and Selection (only if is_context_sufficient is true):\n"
    "   If the user wants something outside their usual taste, bypass profile constraints and select 5 films "
    "   matching their new intent from the candidates.\n"
    "   Otherwise favor Favorite Genres and filter out Disliked Genres. Only deviate if explicitly requested.\n\n"
    "3. Response Formulation:\n"
    "   In ai_followup_chat, write a punchy engaging intro for your picks in under 3 lines.\n"
    "   Map all 5 chosen movies to the schema EXACTLY from the candidate context. Do not hallucinate missing data.\n"
    "   For each movie write a compelling 2-to-3 sentence hybrid_summary explaining why it fits the mood. No spoilers."
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    ai_engine.load_model()
    yield


app = FastAPI(title="FlickFind API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Health ---

@app.get("/")
async def root():
    return {"status": "online", "message": "FlickFind API Active"}


@app.get("/api/v1/health/db")
async def check_database_health(db: Session = Depends(database.get_db)):
    try:
        db.execute(text("SELECT 1"))
        count = db.query(models.Movie).count()
        return {"database_status": "connected", "movies_indexed": count}
    except Exception as e:
        return {"database_status": "disconnected", "error": str(e)}


# --- Auth ---

@app.post("/api/v1/auth/register", response_model=UserResponse)
async def register_user(user_data: UserCreate, db: Session = Depends(database.get_db)):
    if db.query(models.User).filter(models.User.username == user_data.username).first():
        raise HTTPException(status_code=400, detail="Username is already taken.")

    if db.query(models.User).filter(models.User.email == user_data.email).first():
        raise HTTPException(status_code=400, detail="Email is already registered.")

    new_user = models.User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hash_user_password(user_data.password),
        watcher_tier="BASIC_WATCHER",
        persona_vector_data=[0.0] * 768,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@app.post("/api/v1/auth/login")
async def login_user(credentials: UserLogin, db: Session = Depends(database.get_db)):
    user = db.query(models.User).filter(models.User.username == credentials.username).first()
    if not user or not verify_user_password(credentials.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Invalid username or password.")

    return {
        "message": "Authentication successful",
        "user_id": user.id,
        "username": user.username,
        "watcher_tier": user.watcher_tier,
    }


# --- User Engagement ---

@app.post("/api/v1/user/watchlist", status_code=200)
async def toggle_watchlist_item(action: WatchlistAction, db: Session = Depends(database.get_db)):
    existing = db.query(models.UserWatchlist).filter(
        models.UserWatchlist.user_id == action.user_id,
        models.UserWatchlist.movie_id == action.movie_id,
    ).first()

    if existing:
        db.delete(existing)
        db.commit()
        return {"status": "removed", "message": "Movie removed from watchlist."}

    db.add(models.UserWatchlist(user_id=action.user_id, movie_id=action.movie_id))
    db.commit()
    return {"status": "added", "message": "Movie added to watchlist."}


@app.get("/api/v1/user/watchlist/{user_id}", response_model=List[MovieCard])
async def get_user_watchlist(user_id: int, db: Session = Depends(database.get_db)):
    try:
        movies = (
            db.query(models.Movie)
            .join(models.UserWatchlist, models.UserWatchlist.movie_id == models.Movie.id)
            .filter(models.UserWatchlist.user_id == user_id)
            .order_by(models.UserWatchlist.added_at.desc())
            .all()
        )
        return [
            MovieCard(
                id=m.id,
                title=m.title,
                release_year=m.release_year,
                imdb_rating=m.imdb_rating,
                runtime=m.runtime or 0,
                director=m.director or "Unknown Director",
                director_of_photography=m.director_of_photography or "Unknown",
                music_composer=m.music_composer or "Unknown",
                poster_path=m.poster_path,
                hybrid_summary=m.overview or "",
            )
            for m in movies
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch watchlist: {str(e)}")


@app.post("/api/v1/user/watched", status_code=200)
async def log_watched_movie(action: WatchedAction, db: Session = Depends(database.get_db)):
    db.add(models.UserWatchedHistory(
        user_id=action.user_id,
        movie_id=action.movie_id,
        rating=action.rating,
        critic_review=action.critic_review,
    ))

    user = db.query(models.User).filter(models.User.id == action.user_id).first()
    movie = db.query(models.Movie).filter(models.Movie.id == action.movie_id).first()

    if user and movie and movie.mood_vector_data is not None:
        # EMA: shift persona vector 15% toward the watched movie
        LEARNING_RATE = 0.15
        if user.persona_vector_data is None:
            user.persona_vector_data = [0.0] * 768

        user.persona_vector_data = [
            (1 - LEARNING_RATE) * u + LEARNING_RATE * m
            for u, m in zip(list(user.persona_vector_data), list(movie.mood_vector_data))
        ]

        total_watched = db.query(models.UserWatchedHistory).filter(
            models.UserWatchedHistory.user_id == action.user_id
        ).count()

        if total_watched >= 15:
            user.watcher_tier = "CRITIC"
        elif total_watched >= 5:
            user.watcher_tier = "DEEP_DIVER"
        else:
            user.watcher_tier = "BASIC_WATCHER"

    db.commit()
    return {
        "status": "success",
        "message": "Watch history recorded.",
        "updated_tier": user.watcher_tier if user else "BASIC_WATCHER",
    }


@app.post("/api/v1/user/dislike", status_code=200)
async def log_disliked_movie(action: DislikeAction, db: Session = Depends(database.get_db)):
    try:
        db.add(models.UserDislikedFilter(
            user_id=action.user_id,
            movie_id=action.movie_id,
            rejection_reason=action.rejection_reason,
        ))
        db.commit()

        if action.user_id and action.rejection_reason:
            user = db.query(models.User).filter(models.User.id == action.user_id).first()
            if user:
                negative_vector = ai_engine.generate_vector(action.rejection_reason)
                if user.persona_vector_data is None:
                    user.persona_vector_data = [0.0] * 768

                # Penalty adjustment: shift persona vector away from the rejected vibe
                PENALTY_RATE = 0.15
                user.persona_vector_data = [
                    c - (PENALTY_RATE * n)
                    for c, n in zip(user.persona_vector_data, negative_vector)
                ]
                db.commit()

        return {"status": "success", "message": "Dislike recorded and preference updated."}

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Dislike tracking failed: {str(e)}")


# --- Recommendations ---

@app.post("/api/v1/recommend/mood", response_model=ChattedRecommendationResponse)
async def analyze_mood_chat(
    request: MoodRequest,
    user_id: Optional[int] = None,
    db: Session = Depends(database.get_db),
):
    try:
        formatted_history = "".join(
            f"{msg.role.upper()}: {msg.text}\n" for msg in request.chat_history
        )
        formatted_history += f"USER CURRENT COMMAND: {request.mood_text}"

        # Pass 1: Extract dense semantic search query and evaluate profile bypass
        compile_response = generate_gemini_content(
            contents=CONTEXT_COMPILER_PROMPT.format(formatted_history=formatted_history),
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=CompiledContextPayload,
            ),
        )
        compiler_result = CompiledContextPayload.model_validate_json(compile_response.text)
        dense_query = compiler_result.dense_search_query.strip()
        bypass_profile = compiler_result.should_bypass_profile

        query_vector = ai_engine.generate_vector(dense_query)

        pop_w = 0.0 if bypass_profile else ALGORITHM_CONFIG["POPULARITY_MULTIPLIER"]
        rat_w = 0.0 if bypass_profile else ALGORITHM_CONFIG["RATING_MULTIPLIER"]

        persona_vector = None
        if user_id and not bypass_profile:
            user = db.query(models.User).filter(models.User.id == user_id).first()
            if user and user.persona_vector_data and any(v != 0.0 for v in user.persona_vector_data):
                persona_vector = user.persona_vector_data

        movie_query = db.query(models.Movie).filter(
            models.Movie.runtime >= ALGORITHM_CONFIG["MIN_RUNTIME"],
            models.Movie.imdb_rating >= ALGORITHM_CONFIG["MIN_RATING"],
            models.Movie.imdb_votes >= ALGORITHM_CONFIG["MIN_VOTES"],
        )

        if user_id:
            disliked_ids = [
                r[0] for r in db.query(models.UserDislikedFilter.movie_id)
                .filter(models.UserDislikedFilter.user_id == user_id)
                .all()
            ]
            if disliked_ids:
                movie_query = movie_query.filter(~models.Movie.id.in_(disliked_ids))

        if request.displayed_movie_ids:
            movie_query = movie_query.filter(~models.Movie.id.in_(request.displayed_movie_ids))

        prompt_distance = models.Movie.mood_vector_data.cosine_distance(query_vector)
        if persona_vector is not None:
            pw = ALGORITHM_CONFIG["LONG_TERM_PERSONA_WEIGHT"]
            sort_score = (
                (1.0 - pw) * prompt_distance
                + pw * models.Movie.mood_vector_data.cosine_distance(persona_vector)
            )
        else:
            sort_score = prompt_distance

        log_popularity = func.ln(models.Movie.popularity + 1)

        candidates = (
            movie_query
            .order_by(sort_score - (log_popularity * pop_w) - (models.Movie.imdb_rating * rat_w))
            .limit(ALGORITHM_CONFIG["CANDIDATE_POOL_LIMIT"])
            .all()
        )

        if not candidates:
            fallback = db.query(models.Movie)
            if request.displayed_movie_ids:
                fallback = fallback.filter(~models.Movie.id.in_(request.displayed_movie_ids))
            candidates = fallback.order_by(prompt_distance).limit(30).all()

        if not candidates:
            return ChattedRecommendationResponse(
                is_context_sufficient=True,
                ai_followup_chat="The movie database catalog appears empty. Please run the database seeder first.",
                recommendations=[],
            )

        top_5 = candidates[:5]
        pool = candidates[5:]
        sampled = top_5 + random.sample(pool, min(len(pool), 25))

        profile_context = "No profile constraints active."
        if request.user_profile:
            p = request.user_profile
            profile_context = (
                f"Favorite Genres: {p.favorite_genres} | "
                f"Disliked Genres: {p.disliked_genres} | "
                f"Preferred Eras: {p.preferred_eras}"
            )

        movie_context = "\n".join(
            f"ID: {m.id} | Title: {m.title} | Year: {m.release_year} | Rating: {m.imdb_rating} | "
            f"Runtime: {m.runtime}m | Genres: {m.genres or 'N/A'} | Director: {m.director or 'Unknown'} | "
            f"Cinematographer: {m.director_of_photography or 'Unknown'} | "
            f"Composer: {m.music_composer or 'Unknown'} | PosterPath: {m.poster_path or ''}"
            for m in sampled
        )

        generation_prompt = (
            f"[CONVERSATION STREAM MEMORY]\n{formatted_history}\n\n"
            f"[LONG-TERM USER PROFILE MATRIX]\n{profile_context}\n\n"
            f"[CANDIDATE CINEMATIC SELECTIONS AVAILABLE]\n{movie_context}\n\n"
            "Analyze the inputs above and output the final structured JSON package matching the response model."
        )

        # Pass 2: Concierge selection and structured summary generation
        ai_response = generate_gemini_content(
            contents=generation_prompt,
            config=types.GenerateContentConfig(
                system_instruction=CONCIERGE_SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                response_schema=ChattedRecommendationResponse,
            ),
        )

        result = ChattedRecommendationResponse.model_validate_json(ai_response.text)

        if result.is_context_sufficient and result.recommendations:
            selected_ids = {m.id for m in result.recommendations}
            for movie in sampled:
                if movie.id in selected_ids:
                    movie.hit_count += 1
            db.commit()

        return result

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Recommendation engine error: {str(e)}")
