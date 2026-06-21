# GenAI BI Platform

A modern, interactive, and fully responsive Business Intelligence (BI) platform powered by Generative AI. This platform enables users to upload CSV/Excel datasets, securely authenticate, and type natural language questions to generate SQL queries, retrieve data from the database, and render interactive analytical charts and 3D visual experiences.

---

## 🚀 Live Demo URLs

* **Frontend App**: [https://genaibi.vercel.app](https://genaibi.vercel.app)
* **Backend API**: [https://genaibi-backend.vercel.app](https://genaibi-backend.vercel.app)

---

## 🌟 Key Features

* **Natural Language to SQL (NL -> SQL)**: Enter plain English queries (e.g., *"Show me total sales by region"*), and the AI engine generates, validates, and runs the SQL query against your uploaded dataset.
* **Interactive Chart Visualizations**: Query results are dynamically rendered into beautiful, interactive charts (Bar, Line, Area, Pie) powered by Recharts.
* **Premium Netflix-Style UI/UX**: Immersive dark-theme design featuring deep black and charcoal tones with sharp crimson accents, custom interactive hover transitions, and responsive mobile optimization.
* **Immersive 3D Graphics**: Implemented a responsive 3D visualization preview block using **React Three Fiber** and **Three.js** on the landing page.
* **Dataset Management**: Drag-and-drop file upload (`CSV`, `Excel`) to automatically clean and create relational tables in the SQLite database.
* **Query History Tracker**: Re-run or review past queries in a dedicated history log.
* **Secure Authentication**: Protected routes using JWT tokens for registration and login operations.
* **Mobile-First Responsive Design**: Adaptive design for all screen resolutions (Mobile: 320px–480px, Tablet: 481px–768px, Laptop: 769px–1024px, Desktop: 1025px–1440px, Ultra-wide: 1441px+). All interactive buttons and inputs guarantee a touch-friendly hit target (minimum 44px height).

---

## 🛠️ Technology Stack

### Frontend
* **Core**: React (v18), React Router (v6)
* **Styling**: TailwindCSS, Vanilla CSS, Custom Clamp Typography
* **Animations**: Framer Motion
* **3D Graphics**: Three.js, `@react-three/fiber`, `@react-three/drei`
* **Charts**: Recharts
* **State & Network**: Axios, Context API, React Hot Toast

### Backend
* **Framework**: FastAPI (Python)
* **Database**: SQLite, SQLAlchemy ORM
* **Data Processing**: Pandas, OpenPyXL, NumPy
* **Security**: JWT tokens (`python-jose`, `passlib`, `bcrypt`)
* **Server**: Uvicorn

---

## 📂 Project Structure

```text
genai-bi-platform/
├── backend/                  # FastAPI Backend
│   ├── main.py               # Main application entry point & API endpoints
│   ├── ai_engine.py          # NL -> SQL translation logic (OpenAI & Fallback)
│   ├── database.py           # SQLAlchemy setup and DB session helpers
│   ├── models.py             # Database schemas & ORM models
│   ├── schemas.py            # Pydantic schemas for data validation
│   ├── data_cleaner.py       # Pandas utility to parse/clean uploaded CSV/Excel
│   ├── auth.py               # Password hashing & JWT generation
│   ├── sql_validator.py      # Basic SQL parsing and validation checks
│   ├── requirements.txt      # Python dependencies list
│   └── genai_bi.db           # Local SQLite database file
│
├── frontend/                 # React Frontend
│   ├── public/               # Public assets, icons, and favicon.svg
│   ├── src/
│   │   ├── api/              # Axios instance configured with JWT & global auth filters
│   │   ├── components/       # Reusable components (Navbar, Chart, FileUpload, etc.)
│   │   ├── context/          # Context providers (AuthContext)
│   │   ├── pages/            # Page layouts (Landing, Login, Dashboard, History, etc.)
│   │   ├── App.js            # App routes & layout wrapper
│   │   ├── index.css         # Global design tokens, responsive typography clamps
│   │   └── index.js          # App entrypoint
│   ├── tailwind.config.js    # Tailwind styling theme configurations
│   └── vercel.json           # Vercel SPA routing & build configs
```

---

## 🔧 Local Development Setup

### Prerequisites
* **Node.js** (v18+ recommended)
* **Python** (v3.10+ recommended)

### 1. Backend Setup
1. Open a terminal and navigate to the `backend` folder:
   ```bash
   cd backend
   ```
2. Create and activate a Python virtual environment:
   ```bash
   python -m venv .venv
   # On Windows:
   .venv\Scripts\activate
   # On macOS/Linux:
   source .venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Create a `.env` file in the `backend` folder (based on `.env.example`) and add your configuration details:
   ```env
   DATABASE_URL=sqlite:///genai_bi.db
   SECRET_KEY=your_jwt_secret_key_here
   OPENAI_API_KEY=your_openai_api_key_here   # Optional: For advanced GPT-based NL-to-SQL
   ```
5. Start the FastAPI development server:
   ```bash
   python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
   ```
   The backend API documentation will be available at `http://127.0.0.1:8000/docs`.

### 2. Frontend Setup
1. Open a new terminal and navigate to the `frontend` folder:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Create a `.env` file in the `frontend` folder:
   ```env
   REACT_APP_API_URL=http://localhost:8000
   ```
4. Start the React development server:
   ```bash
   npm start
   ```
   The application will run locally at `http://localhost:3000`.

---

## 🌐 Production Deployment (Vercel)

Both the frontend and backend are configured to run as production applications on Vercel:

1. **Backend API**: Deployed as serverless functions.
2. **Frontend App**: Deployed with routing rules configured to forward API calls to the production backend URL using the Vercel project environment variable:
   * Key: `REACT_APP_API_URL`
   * Value: `https://genaibi-backend.vercel.app`
