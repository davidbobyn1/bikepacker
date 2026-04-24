# Bikepacker — AI Trip Planner

An AI-native bikepacking trip planner. Describe your ideal ride in plain language and get 3 complete trip plans with interactive maps, day-by-day itineraries, overnight options, and downloadable GPX files.

## Stack

- **Backend**: Python / FastAPI / PostgreSQL (PostGIS)
- **Frontend**: React (CRA) / TypeScript / Tailwind CSS / MapLibre GL
- **AI**: Claude (Anthropic) for trip parsing and narrative generation
- **Routing**: Mapbox Directions API
- **Enrichment**: Strava Segments API

## Local Development

### Prerequisites
- Python 3.11+
- Node.js 18+
- Docker (for PostgreSQL)

### Setup

1. **Clone and configure**
   ```bash
   git clone https://github.com/davidbobyn1/bikepacker.git
   cd bikepacker
   cp .env.template .env
   # Fill in your API keys in .env
   ```

2. **Start the database**
   ```bash
   docker compose up -d
   ```

3. **Start the backend**
   ```bash
   pip install -r requirements.txt
   python -m uvicorn backend.main:app --reload
   # Runs on http://localhost:8000
   ```

4. **Start the frontend**
   ```bash
   cd frontend
   npm install
   npm start
   # Runs on http://localhost:3000
   ```

## Deployment

- **Backend**: Railway (connect GitHub repo, add env vars, add PostgreSQL plugin)
- **Frontend**: Vercel (connect GitHub repo, set root directory to `frontend`)
