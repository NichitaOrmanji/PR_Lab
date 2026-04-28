@echo off
echo Stopping and removing containers...
docker rm -f db backend frontend
docker network rm lab3-net
echo Done!
pause
