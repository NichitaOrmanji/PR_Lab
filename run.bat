@echo off
echo === DOCKERLAB3: Starting all containers ===

echo [1/5] Creating network...
docker network create lab3-net

echo [2/5] Starting PostgreSQL...
docker run -d ^
  --name db ^
  --network lab3-net ^
  -e POSTGRES_DB=tododb ^
  -e POSTGRES_USER=postgres ^
  -e POSTGRES_PASSWORD=postgres ^
  -v "%cd%\db\init.sql:/docker-entrypoint-initdb.d/init.sql" ^
  -p 5432:5432 ^
  postgres:15-alpine

echo Waiting for DB to start...
timeout /t 6 /nobreak

echo [3/5] Building backend...
docker build -t image_backend ./backend

echo [4/5] Starting backend...
docker run -d ^
  --name backend ^
  --network lab3-net ^
  -e DB_HOST=db ^
  -e DB_NAME=tododb ^
  -e DB_USER=postgres ^
  -e DB_PASS=postgres ^
  -e SMTP_HOST=smtp.gmail.com ^
  -e SMTP_PORT=587 ^
  -e SMTP_USER=testuser198626123@gmail.com ^
  -e SMTP_PASS=vbrnzjzwbflhoecu ^
  -e IMAP_HOST=imap.gmail.com ^
  -e IMAP_PORT=993 ^
  -e POP3_HOST=pop.gmail.com ^
  -e POP3_PORT=995 ^
  -p 5000:5000 ^
  image_backend

echo [5/5] Building and starting frontend...
docker build -t image_frontend ./frontend

docker run -d ^
  --name frontend ^
  --network lab3-net ^
  -p 8080:80 ^
  image_frontend

echo.
echo === Done! ===
echo   App:  http://localhost:8080
echo   API:  http://localhost:5000/tasks
echo.
pause
