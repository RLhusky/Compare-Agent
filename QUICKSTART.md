# Quick Start Guide

## Prerequisites

1. **Redis** - Must be running (backend requires it at startup)
2. **Python 3.11+** with pip
3. **Node.js** with npm (already installed)

## Setup Steps

### 1. Install Backend Dependencies
```bash
pip install -e .
```

### 2. Start Redis
```bash
# macOS (if installed via Homebrew)
brew services start redis

# Or run directly
redis-server

# Or use Docker
docker run -d -p 6379:6379 redis:latest
```

### 3. Verify Environment Files
- `frontend/.env.local` should exist with `NEXT_PUBLIC_API_URL=http://localhost:8000`
- `backend/.env` should exist (already created with placeholder API keys)

**Note:** API keys are placeholders. Real API calls won't work until you add real keys, but the app will start.

### 4. Start Backend (Terminal 1)
```bash
uvicorn main:app --reload --port 8000
```

### 5. Start Frontend (Terminal 2)
```bash
cd frontend
npm run dev
```

## What Works Without Real API Keys

✅ Frontend will load and connect to backend  
✅ Backend will start and accept requests  
✅ Health checks will work  
❌ Actual product comparisons will fail (needs real Perplexity & Grok API keys)

## Troubleshooting

**Backend won't start:**
- Check Redis is running: `redis-cli ping` (should return `PONG`)
- Check port 8000 is available

**Frontend can't connect:**
- Verify backend is running on `http://localhost:8000`
- Check `frontend/.env.local` has correct API URL
- Check browser console for CORS errors

**API calls fail:**
- Add real API keys to `backend/.env`:
  - `PERPLEXITY_API_KEY=your_key_here`
  - `GROK_API_KEY=your_key_here`

