@echo off
REM GreenPath — Start both backend and frontend

echo Starting GreenPath...

echo Installing backend dependencies...
start /B cmd /c "cd backend && pip install -r requirements.txt"

echo Installing frontend dependencies...
start /B cmd /c "cd frontend && npm install"

timeout /t 15 /nobreak > nul

echo Starting backend on port 8000...
start cmd /c "cd backend && uvicorn main:app --reload --port 8000"

timeout /t 3 /nobreak > nul

echo Starting frontend on port 3000...
start cmd /c "cd frontend && npm run dev"

echo.
echo =======================================
echo   GreenPath is running!
echo   Frontend: http://localhost:3000
echo   Backend:  http://localhost:8000
echo   API Docs: http://localhost:8000/docs
echo =======================================
echo.
