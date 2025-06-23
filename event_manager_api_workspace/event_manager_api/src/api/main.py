from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date, datetime
import sqlite3
import os


# App-level metadata and OpenAPI tags for better documentation
app = FastAPI(
    title="Event Manager API",
    description="Backend API for event management providing CRUD endpoints for events.",
    version="1.0.0",
    openapi_tags=[{"name": "Events", "description": "CRUD for event management"}]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "event_manager.db")
DATABASE_PATH = os.path.abspath(DATABASE_PATH)


def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            date TEXT NOT NULL,
            location TEXT NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()


init_db()


# Pydantic models


class EventBase(BaseModel):
    name: str = Field(..., description="Name of the event", example="Board Game Night")
    description: Optional[str] = Field(
        None, description="Description of the event", example="An evening with tabletop games"
    )
    event_date: date = Field(
        ...,
        alias="date",
        description="Date of the event",
        example="2024-07-13",
    )
    location: str = Field(..., description="Location of the event", example="Central Hall")


class EventCreate(EventBase):
    pass


class EventUpdate(BaseModel):
    name: Optional[str] = Field(
        None, description="Name of the event"
    )
    description: Optional[str] = Field(
        None, description="Description of the event"
    )
    event_date: Optional[date] = Field(
        None, alias="date", description="Date of the event"
    )
    location: Optional[str] = Field(
        None, description="Location of the event"
    )


class Event(EventBase):
    id: int = Field(..., description="Unique event ID", example=1)


# Endpoints


@app.get("/", tags=["Health"])
def health_check():
    """Health check endpoint to verify API status."""
    return {"message": "Healthy"}


# PUBLIC_INTERFACE
@app.post(
    "/events/",
    status_code=201,
    response_model=Event,
    tags=["Events"],
    summary="Create Event",
    description="Create a new event",
)
def create_event(event: EventCreate):
    """Create a new event."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO events (name, description, date, location) VALUES (?, ?, ?, ?)",
        (
            event.name,
            event.description,
            event.event_date.isoformat(),
            event.location,
        ),
    )
    event_id = cur.lastrowid
    conn.commit()
    conn.close()
    return Event(id=event_id, **event.dict())


# PUBLIC_INTERFACE
@app.get(
    "/events/",
    response_model=List[Event],
    tags=["Events"],
    summary="List Events",
    description="Retrieve a list of all events",
)
def list_events():
    """Retrieve a list of all events."""
    conn = get_db_connection()
    events = conn.execute("SELECT * FROM events").fetchall()
    conn.close()
    event_objs = []
    for row in events:
        # Split the date parsing line to respect E501
        date_obj = datetime.strptime(
            row["date"], "%Y-%m-%d"
        ).date()
        event_objs.append(
            Event(
                id=row["id"],
                name=row["name"],
                description=row["description"],
                event_date=date_obj,
                location=row["location"],
            )
        )
    return event_objs


# PUBLIC_INTERFACE
@app.get(
    "/events/{event_id}",
    response_model=Event,
    tags=["Events"],
    summary="Get Event",
    description="Retrieve details of a specific event by ID",
)
def get_event(event_id: int):
    """Get details about a specific event by ID."""
    conn = get_db_connection()
    row = conn.execute(
        "SELECT * FROM events WHERE id = ?",
        (event_id,),
    ).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return Event(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        event_date=datetime.strptime(row["date"], "%Y-%m-%d").date(),
        location=row["location"],
    )


# PUBLIC_INTERFACE
@app.put(
    "/events/{event_id}",
    response_model=Event,
    tags=["Events"],
    summary="Update Event",
    description="Update all attributes of an existing event by ID",
)
def update_event(event_id: int, event: EventCreate):
    """Update all details of an event by ID."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE events SET name = ?, description = ?, date = ?, location = ? WHERE id = ?",
        (
            event.name,
            event.description,
            event.event_date.isoformat(),
            event.location,
            event_id,
        ),
    )
    conn.commit()
    if cur.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Event not found")
    conn.close()
    return Event(id=event_id, **event.dict())


# PUBLIC_INTERFACE
@app.patch(
    "/events/{event_id}",
    response_model=Event,
    tags=["Events"],
    summary="Partially Update Event",
    description="Partially update one or more attributes of an existing event by ID",
)
def partial_update_event(event_id: int, event: EventUpdate):
    """Update one or more fields of an event by ID."""
    conn = get_db_connection()
    row = conn.execute(
        "SELECT * FROM events WHERE id = ?",
        (event_id,),
    ).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Event not found")
    updated_data = {
        **dict(row),
        **{
            (k if k != "date" else "event_date"): v
            for k, v in event.dict(exclude_unset=True, by_alias=True).items()
            if v is not None
        },
    }
    cur = conn.cursor()
    updated_event_date = (
        updated_data["event_date"]
        if isinstance(updated_data["event_date"], str)
        else updated_data["event_date"].isoformat()
    )
    cur.execute(
        "UPDATE events SET name = ?, description = ?, date = ?, location = ? WHERE id = ?",
        (
            updated_data["name"],
            updated_data["description"],
            updated_event_date,
            updated_data["location"],
            event_id,
        ),
    )
    conn.commit()
    conn.close()
    event_date_val = (
        datetime.strptime(updated_data["event_date"], "%Y-%m-%d").date()
        if isinstance(updated_data["event_date"], str)
        else updated_data["event_date"]
    )
    return Event(
        id=event_id,
        name=updated_data["name"],
        description=updated_data["description"],
        event_date=event_date_val,
        location=updated_data["location"],
    )


# PUBLIC_INTERFACE
@app.delete(
    "/events/{event_id}",
    status_code=204,
    tags=["Events"],
    summary="Delete Event",
    description="Delete an event by ID",
)
def delete_event(event_id: int):
    """Delete an event by ID."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM events WHERE id = ?", (event_id,))
    conn.commit()
    if cur.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Event not found")
    conn.close()
    return JSONResponse(status_code=status.HTTP_204_NO_CONTENT)
