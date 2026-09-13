# Heat Surgeon

Takes one real street, pulls its measured satellite surface temperature, calibrates a heat model on its neighbourhood, and searches redesign layouts under space and budget constraints.

Specification: [SPEC.md](SPEC.md). Working rules: [CLAUDE.md](CLAUDE.md).

## Setup

Backend (Python 3.11):

```bash
cd backend
py -3.11 -m venv .venv
.venv\Scripts\activate        # Windows; source .venv/bin/activate elsewhere
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
pytest -q
```

Frontend (Node 20+):

```bash
cd frontend
npm install
npm run dev
npm run typecheck
```
