<div align="center">

<img src="https://img.shields.io/badge/SkillMap-Live-success?style=for-the-badge" />
<img src="https://img.shields.io/badge/Django-6.0.3-092E20?style=for-the-badge&logo=django" />
<img src="https://img.shields.io/badge/React-18-61DAFB?style=for-the-badge&logo=react" />
<img src="https://img.shields.io/badge/PostgreSQL-Supabase-3ECF8E?style=for-the-badge&logo=supabase" />

# SkillMap

### Hyperlocal Skill Discovery Platform for India

**Find skilled people near you. Post your work. Get hired. No degree required.**

[🌐 Live Demo](https://skillmap-frontend-two.vercel.app) · [Backend API](https://skillmap-backend-production-cea2.up.railway.app) · [Frontend Repo](https://github.com/adityagarwal2005/skillmap-frontend)

</div>

---

## The Problem

India has millions of skilled people — developers, designers, bakers, photographers, carpenters — who are invisible to the people who need them. LinkedIn is built for corporates. Local economy still runs on word of mouth. Self-taught talent gets ignored.

**SkillMap fixes this.**

---

## What It Does

- 🔍 **Hyperlocal Discovery** — Find skilled people within your radius using Haversine-based geo search
- 📁 **Verified Portfolio** — Post your work. When you complete a job, it auto-creates a verified portfolio item
- 💼 **Freelance Marketplace** — Post jobs, apply, hire — with built-in conversation on assignment
- 🤝 **Collab Board** — Find teammates for equity, experience, or paid projects
- 💬 **Real-time Messaging** — Conversations auto-created on work assignment or collab acceptance
- 🔔 **Smart Feed** — Posts filtered by your skills and category, with trending algorithm
- ⭐ **Reviews + Ratings** — Verified reviews auto-update user rating

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.13, Django 6.0.3 |
| API | Django REST Framework, JWT Auth |
| Database | PostgreSQL (Supabase) |
| Frontend | React 18, Context API, Axios |
| Storage | Cloudinary |
| Backend Deploy | Railway |
| Frontend Deploy | Vercel |

---

## Architecture
User Browser
↓
Vercel (React Frontend)
↓  REST API calls
Railway (Django Backend)
↓  ORM queries
Supabase (PostgreSQL)
↓  file uploads
Cloudinary (Media Storage)

---

## Backend — 8 Django Apps, 50+ API Endpoints
users/          → Auth, profiles, skills, certificates, student profiles
skills/         → Categories, skills, tags, user skills
portfolio/      → Portfolio items, media, reactions, comments
work/           → Work requests, proposals, conversations, messages
feed/           → Smart feed, search (with stop-word filtering), trending
notifications/  → Real-time notifications across all events
reviews/        → Reviews with auto rating calculation
collab/         → Collab posts, applications, acceptance flow

### Key Technical Features

**Haversine Geo Search**
```python
def get_distance_km(lat1, lon1, lat2, lon2):
    R = 6371
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = sin(d_lat/2)**2 + cos(lat1) * cos(lat2) * sin(d_lon/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1-a))
```

**Smart Feed Algorithm**
- Filters by user's skills + category
- Stop-word filtering on search queries
- Relevance scoring across title, description, tags, skills
- Weekly trending based on reaction velocity

**Work Receipt Auto Portfolio**
```python
# When work request is closed:
PortfolioItem.objects.create(
    user=work_request.assigned_to,
    verified=True,
    verified_via_work=work_request,
)
```

**JWT with Custom Claims**
```python
# Every token carries user_id + username
# No DB lookup needed for basic auth
```

---

## Frontend — 15+ Pages
/                    → Smart feed (For You + Trending)
/profile/:userId     → Full profile with portfolio, certs, reviews
/create-post         → Post work with skills + tags
/post/:itemId        → Post detail with comments + reactions
/people              → Hyperlocal people search
/freelance           → Job board — post, apply, hire
/collab              → Collaboration board
/messages            → Two-panel chat
/notifications       → Activity feed
/settings            → Account management
/onboarding          → 4-step setup flow
/search              → Full search with filters

---

## API Sample

```bash
# Register
POST /users/register/
{ "username": "aditya", "email": "a@a.com", "password": "123" }

# Get smart feed
GET /feed/
Authorization: Bearer <token>

# Search with radius
GET /feed/search/?q=react&radius=10&latitude=28.6&longitude=77.2

# Post work
POST /portfolio/create/
{ "title": "...", "description": "...", "portfolio_type": "project", "skills": "React,Python" }

# Find people near me
GET /users/search/?category_id=1&latitude=28.6&longitude=77.2&radius=10
```

---

## Local Setup

**Backend**
```bash
git clone https://github.com/adityagarwal2005/skillmap-backend
cd skillmap-backend

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Create .env file (see .env.example)
python manage.py runserver
```

**Frontend**
```bash
git clone https://github.com/adityagarwal2005/skillmap-frontend
cd skillmap-frontend

npm install

# Create .env.local
# REACT_APP_API_URL=http://127.0.0.1:8000

npm start
```

---

## Environment Variables

```env
SECRET_KEY=
DEBUG=False
ALLOWED_HOSTS=
DATABASE_URL=
CORS_ALLOWED_ORIGINS=
CLOUDINARY_CLOUD_NAME=
CLOUDINARY_API_KEY=
CLOUDINARY_API_SECRET=
```

---

## Scalability Notes

Current implementation uses Haversine with bounding box pre-filter for geo search. Production scale path:
0–50k users    → Current Haversine (deployed)
50k–1M users   → Migrate to PostGIS spatial indexes on Supabase
1M–10M users   → Add Redis geospatial caching for hot city searches
10M+ users     → Dedicated geo microservice with H3 hexagonal indexing

---

## Built By

**Aditya Agarwal** — 3rd year B.Tech CSE, Chandigarh University

[GitHub](https://github.com/adityagarwal2005) · [LinkedIn](https://linkedin.com/in/aditya-agarwal-03294128a/)

---

<div align="center">
<sub>Built for real India — not just metros.</sub>
</div>
